import fcntl
import time
import sys
import struct


def crc8(str):
  crc_val = 0xff
  while str:
    crc_val ^= ord(str[0])
    bit = 0
    while bit < 8:
      crc_val = crc_val * 2
      if crc_val >= 256:
        crc_val = crc_val & 0xff
        crc_val = crc_val ^ 0x31
      bit += 1
    str = str[1:]
  return crc_val

def check_crc(triplet_string):
    if len(triplet_string) % 3 != 0:
        return False, ""

    return_str = ""
    for i in range(0, len(triplet_string), 3):
        if crc8(triplet_string[i:i+2]) != ord(triplet_string[i+2]):
            return False, ""
        return_str += triplet_string[i:i+2]

    return True, return_str


class Sgp30Sense:
    DEV_ADDR = 0x58
    IOCTL_I2C_SLAVE = 0x703
    I2C_DEV_NAME = "/dev/i2c-1"

    GET_DEV_ID_CMD = "3682".decode('hex')
    INIT_MEASUREMENT_CMD = "2003".decode('hex')
    MEASURE_CMD = "2008".decode('hex')
    GET_BASELINE_CMD = "2015".decode('hex')
    SET_BASELINE_CMD = "201e".decode('hex')

    BASELINE_FILENAME = "sgp30_baseline.bin"
    BASELINE_STRUCT = ">HH"

    def __init__(self):
        self.file_descr = open (self.I2C_DEV_NAME, "r+b", 0)
        fcntl.ioctl(self.file_descr.fileno(), self.IOCTL_I2C_SLAVE, self.DEV_ADDR)

    def get_name(self):
        return "sgp30"

    def get_dev_id(self):
        attempts = 3

        while attempts > 0:
            self.file_descr.write(self.GET_DEV_ID_CMD)
            time.sleep(0.01)
            dev_id = self.file_descr.read(9)
            res, ret_dev_id = check_crc(dev_id)
            if res == True:
                return ret_dev_id
            attempts += 1

        return None

    def init_measurement(self):
        self.file_descr.write(self.INIT_MEASUREMENT_CMD)

    def measure(self):
        self.file_descr.write(self.MEASURE_CMD)
        time.sleep(0.01)
        raw_measurement = self.file_descr.read(6)

        res, measurement = check_crc(raw_measurement)
        if res == False:
            return None

        eco2_value = ord(measurement[0]) * 0x100 + ord(measurement[1])
        etvoc_value = ord(measurement[2]) * 0x100 + ord(measurement[3])

        return eco2_value, etvoc_value

    def get_baseline(self):
        self.file_descr.write(self.GET_BASELINE_CMD)
        time.sleep(0.01)
        raw_baseline = self.file_descr.read(6)

        res, baselines = check_crc(raw_baseline)
        if res == False:
            return None

        eco2_baseline = ord(baselines[0]) * 0x100 + ord(baselines[1])
        etvoc_baseline = ord(baselines[2]) * 0x100 + ord(baselines[3])

        return eco2_baseline, etvoc_baseline

    def set_baseline(self, eco2_baseline, etvoc_baseline):
        raw_eco2_baseline = chr((eco2_baseline / 0x100) & 0xff) + chr(eco2_baseline & 0xff)
        raw_eco2_baseline += chr(crc8(raw_eco2_baseline))
        raw_etvoc_baseline = chr((etvoc_baseline / 0x100) & 0xff) + chr(etvoc_baseline & 0xff)
        raw_etvoc_baseline += chr(crc8(raw_etvoc_baseline))

        self.file_descr.write(self.SET_BASELINE_CMD + raw_eco2_baseline + raw_etvoc_baseline)

        time.sleep(0.01)

    def save_baseline(self):
        baseline = self.get_baseline()
        if baseline is None:
            return False

        eco2_baseline, etvoc_baseline = baseline
        baseline_bin = struct.pack(self.BASELINE_STRUCT, eco2_baseline, etvoc_baseline)
        #print "Saving baseline %u,%u" % (eco2_baseline, etvoc_baseline)

        baseline_file = open(self.BASELINE_FILENAME, "wb")
        baseline_file.write(baseline_bin)
        baseline_file.close()

        return True

    def restore_baseline(self):
        try:
            baseline_file = open(self.BASELINE_FILENAME, "rb")
        except IOError:
            return False

        baseline_bin = baseline_file.read()
        baseline_file.close()

        (eco2_baseline, etvoc_baseline) = struct.unpack(self.BASELINE_STRUCT, baseline_bin)
        #print "Restoring baseline to %u,%u" % (eco2_baseline, etvoc_baseline)

        self.set_baseline(eco2_baseline, etvoc_baseline)

        return True


if __name__ == "__main__":
    sgp30_obj = Sgp30Sense()

    dev_id = sgp30_obj.get_dev_id()
    if dev_id is None:
        print "Error getting dev ID"
        sys.exit()

    print "Device ID:", dev_id.encode('hex')

    print "Initializing..."
    sgp30_obj.init_measurement()

    while True:
        time.sleep(1)
        sensor_data = sgp30_obj.measure()
        if sensor_data is None:
            continue
        eco2_val, etvoc_val = sensor_data
        print "eCO2:", eco2_val, "eTVOC:", etvoc_val

