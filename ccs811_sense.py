import fcntl
import time
import sys
import struct


def read_byte(file_descr, byte_cmd):
    file_descr.write(chr(byte_cmd))
    time.sleep(0.01)
    return ord(file_descr.read(1))

def get_status(file_descr):
    STATUS_CMD = 0
    return read_byte(file_descr, STATUS_CMD)

def get_measurement_mode(file_descr):
    MODE_CMD = 1
    return (read_byte(file_descr, MODE_CMD) & 0x70) >> 4

def get_app_ver(file_descr):
    APP_VER_CMD = 0x24
    file_descr.write(chr(APP_VER_CMD))
    app_ver = file_descr.read(2)
    return int(app_ver.encode('hex'), 16)

def device_reset(file_descr):
    RESET_CMD = "ff11e5728a".decode('hex')

    print "Resetting device..."

    file_descr.write("ff11e5728a".decode('hex'))
    time.sleep(0.01)

    HW_ID_CMD = 0x20
    hw_id = read_byte(file_descr, HW_ID_CMD)
    if (hw_id != 0x81):
        print "Wrong HW ID 0x%02x" % hw_id
        return

    file_descr.write(chr(0xf4))
    time.sleep(0.01)

def init_measurement(file_descr):
    MEASUREMENT_MODE = 1

    while (get_status(file_descr) & 0x80) == 0:
        print "Starting CCS811 application..."
        APP_START_CMD = 0xF4
        file_descr.write(chr(APP_START_CMD))
        time.sleep(0.01)

    while get_measurement_mode(file_descr) != MEASUREMENT_MODE:
        print "Setting mode to", MEASUREMENT_MODE
        SET_MODE_CMD = "0110".decode('hex')
        file_descr.write(SET_MODE_CMD)

    print "App version:", hex(get_app_ver(file_descr))


def measure(file_descr):
    MEASURE_CMD = 2

    file_descr.write(chr(MEASURE_CMD))
    time.sleep(0.01)
    measurement = file_descr.read(8)

    eco2_value = ord(measurement[0]) * 0x100 + ord(measurement[1])
    etvoc_value = ord(measurement[2]) * 0x100 + ord(measurement[3])
    err = ord(measurement[5])
    if err & 1:
        print "Error in taking measurement:", ord(measurement[4])
        return None

    return eco2_value, etvoc_value

BASELINE_FILENAME = "ccs811_baseline.bin"
BASELINE_CMD = 0x11

def save_baseline(file_descr):
    file_descr.write(chr(BASELINE_CMD))
    time.sleep(0.01)
    baseline = file_descr.read(2)

    baseline_file = open(BASELINE_FILENAME, "wb")
    baseline_file.write(baseline)
    baseline_file.close()

    return True

def restore_baseline(file_descr):
    try:
        baseline_file = open(BASELINE_FILENAME, "rb")
    except IOError:
        return False

    baseline_bin = baseline_file.read(2)
    baseline_file.close()

    if len(baseline_bin) < 2:
        return False

    file_descr.write(chr(BASELINE_CMD) + baseline_bin)
    time.sleep(0.01)

    return True


DEV_ADDR = 0x5a
IOCTL_I2C_SLAVE = 0x703
I2C_DEV_NAME = "/dev/i2c-1"

def ccs811_init():
    file_descr = open (I2C_DEV_NAME, "r+b", 0)
    fcntl.ioctl(file_descr.fileno(), IOCTL_I2C_SLAVE, DEV_ADDR)

    return file_descr

if __name__ == "__main__":
    file_descr = ccs811_init()

    print "Initializing..."
    init_measurement(file_descr)

    while True:
        time.sleep(1)
        sensor_data = measure(file_descr)
        if sensor_data is None:
            continue
        eco2_val, etvoc_val = sensor_data
        print "eCO2:", eco2_val, "eTVOC:", etvoc_val

