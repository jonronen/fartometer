import fcntl
import time
import sys
import struct


class Ccs811Sense:
    DEV_ADDR = 0x5a
    IOCTL_I2C_SLAVE = 0x703
    I2C_DEV_NAME = "/dev/i2c-1"

    BASELINE_FILENAME = "ccs811_baseline.bin"
    BASELINE_CMD = 0x11

    def __init__(self):
        self.file_descr = open (self.I2C_DEV_NAME, "r+b", 0)
        fcntl.ioctl(self.file_descr.fileno(), self.IOCTL_I2C_SLAVE, self.DEV_ADDR)

    def read_byte(self, byte_cmd):
        self.file_descr.write(chr(byte_cmd))
        time.sleep(0.01)
        return ord(self.file_descr.read(1))

    def get_status(self):
        STATUS_CMD = 0
        return self.read_byte(STATUS_CMD)

    def get_measurement_mode(self):
        MODE_CMD = 1
        return (self.read_byte(MODE_CMD) & 0x70) >> 4

    def get_app_ver(self):
        APP_VER_CMD = 0x24
        self.file_descr.write(chr(APP_VER_CMD))
        app_ver = self.file_descr.read(2)
        return int(app_ver.encode('hex'), 16)

    def device_reset(self):
        RESET_CMD = "ff11e5728a".decode('hex')

        print "Resetting device..."

        self.file_descr.write("ff11e5728a".decode('hex'))
        time.sleep(0.01)

        HW_ID_CMD = 0x20
        hw_id = read_byte(HW_ID_CMD)
        if (hw_id != 0x81):
            print "Wrong HW ID 0x%02x" % hw_id
            return

        self.file_descr.write(chr(0xf4))
        time.sleep(0.01)

    def init_measurement(self):
        MEASUREMENT_MODE = 1

        while (self.get_status() & 0x80) == 0:
            print "Starting CCS811 application..."
            APP_START_CMD = 0xF4
            self.file_descr.write(chr(APP_START_CMD))
            time.sleep(0.01)

        while self.get_measurement_mode() != MEASUREMENT_MODE:
            print "Setting mode to", MEASUREMENT_MODE
            SET_MODE_CMD = "0110".decode('hex')
            self.file_descr.write(SET_MODE_CMD)

        print "App version:", hex(self.get_app_ver())


    def measure(self):
        MEASURE_CMD = 2

        self.file_descr.write(chr(MEASURE_CMD))
        time.sleep(0.01)
        measurement = self.file_descr.read(8)

        eco2_value = ord(measurement[0]) * 0x100 + ord(measurement[1])
        etvoc_value = ord(measurement[2]) * 0x100 + ord(measurement[3])
        err = ord(measurement[5])
        if err & 1:
            print "Error in taking measurement:", ord(measurement[4])
            return None

        return eco2_value, etvoc_value

    def save_baseline():
        self.file_descr.write(chr(self.BASELINE_CMD))
        time.sleep(0.01)
        baseline = self.file_descr.read(2)

        baseline_file = open(self.BASELINE_FILENAME, "wb")
        baseline_file.write(baseline)
        baseline_file.close()

        return True

    def restore_baseline():
        try:
            baseline_file = open(BASELINE_FILENAME, "rb")
        except IOError:
            return False

        baseline_bin = baseline_file.read(2)
        baseline_file.close()

        if len(baseline_bin) < 2:
            return False

        self.file_descr.write(chr(BASELINE_CMD) + baseline_bin)
        time.sleep(0.01)

        return True


if __name__ == "__main__":
    ccs811_obj = Ccs811Sense()

    print "Initializing..."
    ccs811_obj.init_measurement()

    while True:
        time.sleep(1)
        sensor_data = ccs811_obj.measure()
        if sensor_data is None:
            continue
        eco2_val, etvoc_val = sensor_data
        print "eCO2:", eco2_val, "eTVOC:", etvoc_val

