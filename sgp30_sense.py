import fcntl
import time
import sys


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


def get_dev_id(file_descr):
    GET_DEV_ID_CMD = "3682".decode('hex')

    attempts = 3
    while attempts > 0:
        file_descr.write(GET_DEV_ID_CMD)
        time.sleep(0.01)
        dev_id = file_descr.read(9)
        res, ret_dev_id = check_crc(dev_id)
        if res == True:
            return ret_dev_id
        attempts += 1

    return None

def init_measurement(file_descr):
    INIT_MEASUREMENT_CMD = "2003".decode('hex')
    file_descr.write(INIT_MEASUREMENT_CMD)

def measure(file_descr):
    MEASURE_CMD = "2008".decode('hex')

    file_descr.write(MEASURE_CMD)
    time.sleep(0.01)
    raw_measurement = file_descr.read(6)

    res, measurement = check_crc(raw_measurement)
    if res == False:
        return None

    eco2_value = ord(measurement[0]) * 0x100 + ord(measurement[1])
    etvoc_value = ord(measurement[2]) * 0x100 + ord(measurement[3])

    return eco2_value, etvoc_value

def get_baseline(file_descr):
    GET_BASELINE_CMD = "2015".decode('hex')

    file_descr.write(GET_BASELINE_CMD)
    time.sleep(0.01)
    raw_baseline = file_descr.read(6)

    res, baselines = check_crc(raw_baseline)
    if res == False:
        return None

    eco2_baseline = ord(baselines[0]) * 0x100 + ord(baselines[1])
    etvoc_baseline = ord(baselines[2]) * 0x100 + ord(baselines[3])

    return eco2_baseline, etvoc_baseline

def set_baseline(file_descr, eco2_baseline, etvoc_baseline):
    SET_BASELINE_CMD = "201e".decode('hex')

    raw_eco2_baseline = chr((eco2_baseline / 0x100) & 0xff) + chr(eco2_baseline & 0xff)
    raw_eco2_baseline += chr(crc8(raw_eco2_baseline))
    raw_etvoc_baseline = chr((etvoc_baseline / 0x100) & 0xff) + chr(etvoc_baseline & 0xff)
    raw_etvoc_baseline += chr(crc8(raw_etvoc_baseline))

    file_descr.write(SET_BASELINE_CMD + raw_eco2_baseline + raw_etvoc_baseline)

    time.sleep(0.01)


DEV_ADDR = 0x58
IOCTL_I2C_SLAVE = 0x703
I2C_DEV_NAME = "/dev/i2c-1"

def sgp30_init():
    file_descr = open (I2C_DEV_NAME, "r+b", 0)
    fcntl.ioctl(file_descr.fileno(), IOCTL_I2C_SLAVE, DEV_ADDR)

    return file_descr

if __name__ == "__main__":
    file_descr = sgp30_init()

    dev_id = get_dev_id(file_descr)
    if dev_id is None:
        print "Error getting dev ID"
        sys.exit()

    print "Device ID:", dev_id.encode('hex')

    print "Initializing..."
    init_measurement(file_descr)

    while True:
        time.sleep(1)
        sensor_data = measure(file_descr)
        if sensor_data is None:
            continue
        eco2_val, etvoc_val = sensor_data
        print "eCO2:", eco2_val, "eTVOC:", etvoc_val

