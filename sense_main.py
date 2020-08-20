import sgp30_sense
import time
import sys


WARMUP_TIME = 20 * 60 # 20 minutes
PRINT_INTERVAL = 10 * 60 # 10 minutes
BASELINE_INTERVAL = 24 * 60 * 60 # 1 day


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

    eco2_statistics = SensorStatistics()
    etvoc_statistics = SensorStatistics()

    sgp30_sense.init_measurement(file_descr)
    #sgp30_sense.set_baseline(file_descr, eco2_baseline, etvoc_baseline)

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
            eco2_stats = eco2_statistics.get_statistics()
            eco2_statistics.reset()
            if eco2_stats is not None:
                print "eCO2 max:", eco2_stats["max"], "eCO2 min:", eco2_stats["min"], "eCO2 avg:", eco2_stats["avg"]
            etvoc_stats = etvoc_statistics.get_statistics()
            etvoc_statistics.reset()
            if etvoc_stats is not None:
                print "TVOC max:", etvoc_stats["max"], "TVOC min:", etvoc_stats["min"], "TVOC avg:", etvoc_stats["avg"]
            stats_round_start = now

        if now - baseline_timestamp > BASELINE_INTERVAL:
            print "Baseline:", sgp30_sense.get_baseline(file_descr)
            baseline_timestamp = now

