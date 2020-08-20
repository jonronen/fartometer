import sgp30_sense
import time
import sys
import awscrt
import awsiot
import argparse


WARMUP_TIME = 20 * 60 # 20 minutes
PRINT_INTERVAL = 10 * 60 # 10 minutes
BASELINE_INTERVAL = 8 * 60 * 60 # 8 hours


def get_location():
    LOCATION_FILE = "location.txt"

    try:
        f = open(LOCATION_FILE, "rt")
    except IOError:
        return "Default Location"

    return f.read().strip()


class SensorStatistics:
    def __init__(self):
        self.reset()

    def reset(self):
        self.max = 0
        self.min = 0xffffffff
        self.aggr = 0
        self.samples = 0

    def process(self, sample):
        if sample > self.max:
            self.max = sample
        if sample < self.min:
            self.min = sample
        self.samples += 1
        self.aggr += sample

    def get_statistics(self):
        if self.samples == 0:
            return None
        return {"min": self.min, "max": self.max, "avg": self.aggr / self.samples}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send sensor reports through MQTT")
    parser.add_argument('--endpoint', required=True, help="Your AWS IoT custom endpoint, not including a port. " +
                                                          "Ex: \"abcd123456wxyz-ats.iot.us-east-1.amazonaws.com\"")
    parser.add_argument('--cert', required=True, help="File path to your client certificate, in PEM format.")
    parser.add_argument('--key', required=True, help="File path to your private key, in PEM format.")
    parser.add_argument('--root-ca', required=True, help="File path to root certificate authority, in PEM format. " +
                                          "Necessary if MQTT server uses a certificate that's not already in " +
                                          "your trust store.")
    parser.add_argument('--client-id', required=True, help="Client ID for MQTT connection.")
    parser.add_argument('--dry-run', action="store_true", help="Client ID for MQTT connection.")

    args = parser.parse_args()

    event_loop_group = awscrt.io.EventLoopGroup(1)
    host_resolver = awscrt.io.DefaultHostResolver(event_loop_group)
    client_bootstrap = awscrt.io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_conn = awsiot.mqtt_connection_builder.mtls_from_path(
        endpoint=args.endpoint,
        cert_filepath=args.cert,
        pri_key_filepath=args.key,
        ca_filepath=args.root_ca,
        client_id=args.client_id,
        client_bootstrap=client_bootstrap)

    connect_future = mqtt_conn.connect()
    connect_future.result()

    file_descr = sgp30_sense.sgp30_init()
    dev_id = sgp30_sense.get_dev_id(file_descr)
    if dev_id is None:
        print "Error getting device ID"
        sys.exit()
    print "Device ID:", dev_id.encode('hex')

    time_start = time.time()
    baseline_timestamp = time_start
    warmup_start = time_start
    stats_round_start = time_start

    warmup_done = False

    location = get_location()

    eco2_statistics = SensorStatistics()
    etvoc_statistics = SensorStatistics()

    sgp30_sense.init_measurement(file_descr)
    sgp30_sense.restore_baseline(file_descr)

    while True:
        time.sleep(1)
        meas_data = sgp30_sense.measure(file_descr)
        if meas_data is None:
            continue
        eco2_val, etvoc_val = meas_data
        #print "eco2:", eco2_val, "etvoc:", etvoc_val

        now = time.time()
        if warmup_done == False and now - warmup_start > WARMUP_TIME:
            warmup_done = True
            stats_round_start = now
            baseline_timestamp = now

        if warmup_done:
            eco2_statistics.process(eco2_val)
            etvoc_statistics.process(etvoc_val)

        if now - stats_round_start > PRINT_INTERVAL:
            json_obj = {"sensor": "sgp30", "location": location}

            eco2_stats = eco2_statistics.get_statistics()
            eco2_statistics.reset()
            etvoc_stats = etvoc_statistics.get_statistics()
            etvoc_statistics.reset()

            stats_round_start = now

            if eco2_stats is None or etvoc_stats is None:
                continue

            json_obj["eco2_min"] = eco2_stats["min"]
            json_obj["eco2_max"] = eco2_stats["max"]
            json_obj["eco2"] = eco2_stats["avg"]
            json_obj["etvoc_min"] = etvoc_stats["min"]
            json_obj["etvoc_max"] = etvoc_stats["max"]
            json_obj["etvoc"] = etvoc_stats["avg"]

            print "Sending", str(json_obj)

            if not args.dry_run:
                mqtt_future, packet_id = mqtt_conn.publish(
                    topic="sensor_report",
                    payload=str(json_obj),
                    qos=awscrt.mqtt.QoS.AT_LEAST_ONCE)
                mqtt_future.result()

        if now - baseline_timestamp > BASELINE_INTERVAL:
            if sgp30_sense.save_baseline(file_descr):
                baseline_timestamp = now

