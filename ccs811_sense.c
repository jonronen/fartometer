#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <stdio.h>
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <time.h>


static int dev_file_desc;
static const unsigned int MAX_ATTEMPTS = 3;

static const unsigned int CONTINUOUS_MODE = 1;
static const unsigned int MODE_SHIFT = 4;
static const unsigned int MODE_MASK = 0x70;
static const unsigned char MODE_REG = 1;

static const unsigned char DEV_ID_REG = 0x20;
static const unsigned char EXPECTED_DEV_ID = 0x81;

static const char baseline_filename[] = "ccs811_baseline.bin";
static const mode_t baseline_mode_flags = S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH;

static time_t last_baseline_time;

static void open_device(const char *devname, unsigned char addr)
{
	dev_file_desc = open(devname, O_RDWR);
	if (dev_file_desc < 0) {
		printf("Error opening file\n");
		exit(0);
	}
	if (ioctl(dev_file_desc, I2C_SLAVE, addr)) {
		printf("Error in ioctl\n");
		exit(0);
	}
}

static int get_saved_baseline(unsigned short *baseline)
{
	int retval = 0;

	int baseline_file_desc = open(baseline_filename, O_RDWR);
	if (baseline_file_desc < 0) {
		printf("No baseline saved\n");
		int create_err = creat(baseline_filename, baseline_mode_flags);
		if (create_err >= 0)
			close(create_err);
		*baseline = 0;
		return -1;
	}
	retval = read(baseline_file_desc, baseline, sizeof(unsigned short));
	if (retval != sizeof(unsigned short)) {
		retval = errno;
		printf("Error reading baseline: %d\n", retval);
		*baseline = 0;
	}
	else {
		retval = 0;
	}
	close(baseline_file_desc);
	return retval;
}

static int read_byte(unsigned char regaddr, unsigned char *ret)
{
	int err;
	unsigned int attempt = 0;

	do {
		err = write(dev_file_desc, &regaddr, 1);
		if (err != 1) {
			printf("Error in write: %d\n", errno);
			usleep(100);
			continue;
		}
		err = read(dev_file_desc, ret, 1);
		if (err != 1) {
			printf("Error in read: %d\n", errno);
			usleep(100);
			continue;
		}
	}
	while (err < 0 && attempt++ < MAX_ATTEMPTS);

	return (err > 0 ? 0 : err);
}

int read_buff(unsigned char reg, void *data, unsigned int size)
{
	int err;
	unsigned int attempt = 0;

	do {
		err = write(dev_file_desc, &reg, 1);
		if (err != 1) {
			printf("Error writing register address: %d\n", errno);
			usleep(100);
			continue;
		}
		err = read(dev_file_desc, data, size);
		if (err != (int)size) {
			printf("Error reading %u bytes: %d\n", size, errno);
			usleep(100);
			continue;
		}
	} while (err < 0 && attempt++ < MAX_ATTEMPTS);

	return (err > 0 ? 0 : err);
}

int send_buff(unsigned char reg, const void *data, unsigned int size)
{
	unsigned char buf[9];
	int err;
	unsigned int attempt = 0;

	buf[0] = reg;
	memcpy(&buf[1], data, size);

	do {
		err = write(dev_file_desc, buf, size+1);
		if (err != (int)size+1) {
			printf("Error writing buffer: %d\n", errno);
			usleep(100);
			continue;
		}
	} while (err < 0 && attempt++ < MAX_ATTEMPTS);

	return (err > 0 ? 0 : err);
}

static bool status_has_err(unsigned char status)
{
	return ((status & 0x01) != 0);
}

static bool status_has_data(unsigned char status)
{
	return ((status & 0x08) != 0);
}

static bool is_app_loaded(unsigned char status)
{
	return ((status & 0x80) != 0);
}

static void set_mode()
{
	unsigned char data = CONTINUOUS_MODE << MODE_SHIFT;
	printf("Setting mode to %u\n", CONTINUOUS_MODE);
	send_buff(MODE_REG, &data, sizeof(data));
}

static bool correct_mode(unsigned char mode_byte)
{
	if ((mode_byte & MODE_MASK) >> MODE_SHIFT != CONTINUOUS_MODE) {
		printf("Incorrect mode: 0x%02x\n", (mode_byte & MODE_MASK) >> MODE_SHIFT);
		return false;
	}
	return true;
}

static int device_reset()
{
	unsigned char buf[4] = {0x11, 0xe5, 0x72, 0x8a};
	unsigned char dev_id;
	int err;

	printf("Resetting device...\n");

	last_baseline_time = time(NULL);

	send_buff(0xff, buf, sizeof(buf));
	usleep(1000);

	if (read_byte(DEV_ID_REG, &dev_id)) {
		printf("Error reading dev ID\n");
		return -1;
	}
	if (dev_id != EXPECTED_DEV_ID) {
		printf("Wrong HW ID 0x%02x\n", dev_id);
		return -1;
	}
	err = send_buff(0xf4, NULL, 0);
	usleep(1000);

	return err;
}

static void restore_baseline()
{
	unsigned short baseline_value;

	int err = get_saved_baseline(&baseline_value);
	if (err) {
		return;
	}

	send_buff(0x11, &baseline_value, sizeof(baseline_value));
}

static void save_baseline()
{
	unsigned short baseline;

	if (read_buff(0x11, &baseline, sizeof(baseline))) {
		printf("Error reading baseling. Not saving\n");
		return;
	}

	int baseline_file_desc = open(baseline_filename, O_RDWR | O_CREAT, baseline_mode_flags);
	if (baseline_file_desc < 0) {
		printf("Error opening baseline file: %d\n", errno);
		return;
	}
	int retval = write(baseline_file_desc, &baseline, sizeof(baseline));
	if (retval != sizeof(baseline)) {
		printf("Error writing baseline: %d\n", errno);
	}
	close(baseline_file_desc);
}

int main()
{
	open_device("/dev/i2c-1", 0x5a);
	last_baseline_time = time(NULL);

	while (1) {
		unsigned char status, mode, dev_err_num;
		int err = read_byte(0, &status);

		if (err || !is_app_loaded(status)) {
			device_reset();
			restore_baseline();
			continue;
		}

		err = read_byte(1, &mode);
		if (err || !correct_mode(mode)) {
			set_mode();
			continue;
		}

		if (status_has_err(status)) {
			err = read_byte(0xe0, &dev_err_num);
			if (!err)
				printf("Device error number: 0x%02x\n", dev_err_num);
			continue;
		}

		if (!status_has_data(status)) {
			sleep(1);
			continue;
		}

		unsigned char buf[8];
		err = read_buff(0x02, buf, sizeof(buf));
		if (!err) {
			unsigned int raw_value = (unsigned int)buf[6] * 0x100 + buf[7];
			printf("eCO2=%u "
				"eTVOC=%u "
				"status=0x%02x "
				"ERR=0x%02x "
				"RAW=%u,%u\n",
				(unsigned int)buf[0] * 0x100 + buf[1],
				(unsigned int)buf[2] * 0x100 + buf[3],
				buf[4], buf[5],
				(raw_value & 0xfc00) >> 10, raw_value & 0x3ff);
		}

		sleep(1);

		if (time(NULL) - last_baseline_time > 24 * 3600) {
			save_baseline();
		}
	}

	return 0;
}

