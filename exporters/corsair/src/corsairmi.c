/* 
 * minimal program to read out data from Corsair RMi and HXi series of PSUs
 * tested on RM650i, RM750i, HX1000i
 *
 * Copyright (c) notaz, 2016
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *     * Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above copyright
 *       notice, this list of conditions and the following disclaimer in the
 *       documentation and/or other materials provided with the distribution.
 *     * Neither the name of the organization nor the
 *       names of its contributors may be used to endorse or promote products
 *       derived from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
/*
 * register list from SIV by Ray Hinchliffe
 *
 * left unimplemented:
 * 3a fan mode
 * 3b fan pwm
 * 81 fan status
 * f0 fan1 mode
 *
 * left unknown:
 * 40: e6 d3 00 ... (15.6; const?)
 * 44: 1a d2 00 ... ( 8.4; const?)
 * 46: 2c f1 00 ... (75.0; const?)
 * 4f: 46 00 ...
 * 7a: 00 ...
 * 7b: 00 ...
 * 7d: 00 ...
 * 7e: c0 00 ...
 * c4: 01 00 ...
 * d4: b9 bd eb fe 00 ... (32bit const?)
 * d8: 02 00 ...
 * d9: 00 ...
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>
#include <math.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <errno.h>
#include <linux/hidraw.h>


#define PROMETHEUS 1
#define PROMETHEUS_PREFIX "corsair_"
#define GREEN_LIGHT "green_equipment_power_consumption_va"

static const uint16_t products[] = {
	0x1c0a, /* RM650i */
	0x1c0b, /* RM750i */
	0x1c0c, /* RM850i */
	0x1c0d, /* RM1000i */
	0x1c04, /* HX650i */
	0x1c05, /* HX750i */
	0x1c06, /* HX850i */
	0x1c07, /* HX1000i */
	0x1c08, /* HX1200i */
};

static void dump(const uint8_t *buf, size_t size)
{
	size_t i, j;

	for (i = 0; i < size; i += 16) {
		for (j = 0; j < 16; j++) {
			if (i + j < size)
				printf(" %02x", buf[i + j]);
			else
				fputs("   ", stdout);
		}
		fputs("  ", stdout);
		for (j = 0; j < 16; j++) {
			if (i + j < size) {
				uint8_t c = buf[i + j];
				printf("%c", 0x20 <= c && c <= 0x7f ? c : '.');
			}
			else
				break;
		}
		puts("");
	}
}

static void send_recv_cmd(int fd, uint8_t b0, uint8_t b1, uint8_t b2,
	void *buf, size_t buf_size)
{
	uint8_t buf_w[65], buf_r[64];
	ssize_t ret;

	memset(buf_w, 0, sizeof(buf_w));
	buf_w[1] = b0;
	buf_w[2] = b1;
	buf_w[3] = b2;
	ret = write(fd, buf_w, sizeof(buf_w));
	if (ret != sizeof(buf_w)) {
		fprintf(stderr, "write %zd/%zd: ", ret, sizeof(buf_w));
		perror(NULL);
		exit(1);
	}

	ret = read(fd, buf_r, sizeof(buf_r));
	if (ret != sizeof(buf_r)) {
		fprintf(stderr, "read %zd/%zd: ", ret, sizeof(buf_r));
		perror(NULL);
		if (ret > 0)
			dump(buf_r, ret);
		exit(1);
	}

	if (buf_r[0] != b0 || buf_r[1] != b1) {
		fprintf(stderr, "unexpected response %02x %02x "
				"to cmd %02x %02x %02x\n",
				buf_r[0], buf_r[1], b0, b1, b2);
		dump(buf_r, sizeof(buf_r));
		exit(1);
	}

	if (buf != NULL && buf_size > 0) {
		if (buf_size > sizeof(buf_r) - 2)
			buf_size = sizeof(buf_r) - 2;
		memcpy(buf, buf_r + 2, buf_size);
	}
}

static void read_reg(int fd, uint8_t reg, void *buf, size_t buf_size)
{
	send_recv_cmd(fd, 0x03, reg, 0x00, buf, buf_size);
}

static void read_reg16(int fd, uint8_t reg, uint16_t *v)
{
	send_recv_cmd(fd, 0x03, reg, 0x00, v, sizeof(*v));
	// FIXME: big endian host
}

static void read_reg32(int fd, uint8_t reg, uint32_t *v)
{
	send_recv_cmd(fd, 0x03, reg, 0x00, v, sizeof(*v));
	// FIXME: big endian host
}

static double mkv(uint16_t v16)
{
	int p = (int)(int16_t)v16 >> 11;
	int v = ((int)v16 << 21) >> 21;

	return (double)v * pow(2.0, p);
}

#if PROMETHEUS
static void print_prometheus_reg(int fd, uint8_t reg, const char *fmt, ...)
{
	uint16_t val;
	va_list ap;

	read_reg16(fd, reg, &val);

	printf(PROMETHEUS_PREFIX);
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	printf(" %.1f\n", mkv(val));
}
#else
static void print_std_reg(int fd, uint8_t reg, const char *fmt, ...)
{
	size_t len = 0;
	uint16_t val;
	va_list ap;

	read_reg16(fd, reg, &val);

	va_start(ap, fmt);
	len += vprintf(fmt, ap);
	len += printf(": ");
	va_end(ap);
	for (; len < 16; len++)
		fputs(" ", stdout);

	printf("%5.1f\n", mkv(val));
}
#endif

static int try_open_device(const char *name, int report_errors)
{
	struct hidraw_devinfo info;
	int found = 0;
	int i, ret, fd;

	fd = open(name, O_RDWR);
	if (fd == -1) {
		if (report_errors) {
			fprintf(stderr, "open %s: ", name);
			perror(NULL);
		}
		return -1;
	}

	memset(&info, 0, sizeof(info));
	ret = ioctl(fd, HIDIOCGRAWINFO, &info);
	if (ret != 0) {
		perror("HIDIOCGRAWINFO");
		goto out;
	}

	if (info.vendor != 0x1b1c)
		goto out;

	for (i = 0; i < sizeof(products) / sizeof(products[0]); i++) {
		if (info.product == products[i]) {
			found = 1;
			break;
		}
	}

out:
	if (!found) {
		if (report_errors)
			fprintf(stderr, "unexpected device: %04hx:%04hx\n",
				info.vendor, info.product);
		close(fd);
		fd = -1;
	}
	return fd;
}

void dump_names(int fd)
{
	char name[64];
	char vendor[64];
	char product[64];

	bzero(name, sizeof(name));
	bzero(vendor, sizeof(vendor));
       	bzero(product, sizeof(product));

	send_recv_cmd(fd, 0xfe, 0x03, 0x00, name, sizeof(name) - 1);
	read_reg(fd, 0x99, vendor, sizeof(vendor) - 1);
	read_reg(fd, 0x9a, product, sizeof(product) - 1);
#if PROMETHEUS
	printf("# HELP " PROMETHEUS_PREFIX "hardware_info Hardware info\n");
	printf("# TYPE " PROMETHEUS_PREFIX "hardware_info gauge\n");
	printf(PROMETHEUS_PREFIX "hardware_info{name=\"%s\",vendor=\"%s\",product=\"%s\"} 1\n", name, vendor, product);
#else
	printf("name:           '%s'\n", name);
	printf("vendor:         '%s'\n", vendor);
	printf("product:        '%s'\n", product);
#endif
}

void dump_times(int fd)
{
	uint32_t powered;
	uint32_t uptime;

	read_reg32(fd, 0xd1, &powered);
	read_reg32(fd, 0xd2, &uptime);
#if PROMETHEUS
	printf("# HELP " PROMETHEUS_PREFIX "powered_seconds Global time powered in seconds\n");
	printf("# TYPE " PROMETHEUS_PREFIX "powered_seconds gauge\n");
	printf(PROMETHEUS_PREFIX "powered_seconds %u\n", powered);
	printf("# HELP " PROMETHEUS_PREFIX "uptime_seconds Current uptime in seconds\n");
	printf("# TYPE " PROMETHEUS_PREFIX "uptime_seconds gauge\n");
	printf(PROMETHEUS_PREFIX "uptime_seconds %u\n", uptime);
#else
	printf("powered:        %u (%dd. %dh)\n",
		v32, v32 / (24*60*60), v32 / (60*60) % 24);
	printf("uptime:         %u (%dd. %dh)\n",
		v32, v32 / (24*60*60), v32 / (60*60) % 24);
#endif
}

void dump_temps(int fd)
{
#if PROMETHEUS
	printf("# HELP " PROMETHEUS_PREFIX "temperature_celsius Temperature in seconds\n");
	printf("# TYPE " PROMETHEUS_PREFIX "temperature_celsius gauge\n");
	print_prometheus_reg(fd, 0x8d, "temperature_celsius{sensor=\"1\"}");
	print_prometheus_reg(fd, 0x8e, "temperature_celsius{sensor=\"2\"}");
#else
	print_std_reg(fd, 0x8d, "temp1");
	print_std_reg(fd, 0x8e, "temp2");
#endif
}

void dump_fan(int fd)
{
#if PROMETHEUS
	printf("# HELP " PROMETHEUS_PREFIX "fan_rpm Fan speed\n");
	printf("# TYPE " PROMETHEUS_PREFIX "fan_rpm gauge\n");
	print_prometheus_reg(fd, 0x8d, "fan_rpm");
#else
	print_std_reg(fd, 0x90, "fan rpm");
#endif
}

void dump_global_power(int fd)
{
#if PROMETHEUS
	uint16_t volts;
	uint16_t watts;

	read_reg16(fd, 0x88, &volts);
	read_reg16(fd, 0xee, &watts);

	printf("# HELP " PROMETHEUS_PREFIX "global_supply_volts Global power supply volts\n");
	printf("# TYPE " PROMETHEUS_PREFIX "global_supply_volts gauge\n");
	printf(PROMETHEUS_PREFIX "global_supply_volts %.1f\n", mkv(volts));
	printf("# HELP " PROMETHEUS_PREFIX "global_power_watts Global power used in watts\n");
	printf("# TYPE " PROMETHEUS_PREFIX "global_power_watts gauge\n");
	printf(PROMETHEUS_PREFIX "global_power_watts %.1f\n", mkv(watts));
	printf("# HELP " PROMETHEUS_PREFIX GREEN_LIGHT " Global power used in watts\n");
	printf("# TYPE " PROMETHEUS_PREFIX GREEN_LIGHT " gauge\n");
	printf(PROMETHEUS_PREFIX GREEN_LIGHT " %.1f\n", mkv(watts));
#else
	print_std_reg(fd, 0x88, "supply volts");
	print_std_reg(fd, 0xee, "total watts");
#endif
}

void dump_powers(int fd)
{
#if PROMETHEUS
	uint8_t osel;
        uint32_t val;
        double volts[3];
        double amps[3];
        double watts[3];

	for (osel = 0; osel < 3; osel++) {
		// reg0 write (output select)
		send_recv_cmd(fd, 0x02, 0x00, osel, NULL, 0);
		read_reg32(fd, 0x8b, &val);
		volts[osel] = mkv(val);
		read_reg32(fd, 0x8c, &val);
		amps[osel] = mkv(val);
		read_reg32(fd, 0x96, &val);
		watts[osel] = mkv(val);
	}
	printf("# HELP " PROMETHEUS_PREFIX "output_volts single output in volts\n");
	printf("# TYPE " PROMETHEUS_PREFIX "output_volts gauge\n");
	for (osel = 0; osel < 3; osel++)
            printf(PROMETHEUS_PREFIX "output_volts{ouput=\"%u\"} %.1f\n", osel, volts[osel]);
	printf("# HELP " PROMETHEUS_PREFIX "output_amperes single output in amperes\n");
	printf("# TYPE " PROMETHEUS_PREFIX "output_amperes gauge\n");
	for (osel = 0; osel < 3; osel++)
            printf(PROMETHEUS_PREFIX "output_amperes{ouput=\"%u\"} %.1f\n", osel, amps[osel]);
	printf("# HELP " PROMETHEUS_PREFIX "output_watts single output power in watts\n");
	printf("# TYPE " PROMETHEUS_PREFIX "output_watts gauge\n");
	for (osel = 0; osel < 3; osel++)
            printf(PROMETHEUS_PREFIX "output_watts{ouput=\"%u\"} %.1f\n", osel, watts[osel]);
#else
	uint8_t osel;

	for (osel = 0; osel < 3; osel++) {
		// reg0 write (output select)
		send_recv_cmd(fd, 0x02, 0x00, osel, NULL, 0);
		print_std_reg(fd, 0x8b, "output%u volts", osel);
		print_std_reg(fd, 0x8c, "output%u amps", osel);
		print_std_reg(fd, 0x96, "output%u watts", osel);
	}
#endif
}


int main(int argc, char *argv[])
{
	int had_eacces = 0;
	int i, fd;

	if (argc > 1) {
		if (argv[1][0] == '-' || argc != 2) {
			fprintf(stderr, "usage:\n");
			fprintf(stderr, "%s [/dev/hidrawN]\n", argv[0]);
			return 1;
		}
		fd = try_open_device(argv[1], 1);
	}
	else {
		char name[63];

		for (i = 0; i < 16; i++) {
			snprintf(name, sizeof(name), "/dev/hidraw%d", i);
			fd = try_open_device(name, 0);
			if (fd != -1)
				break;
			if (errno == EACCES)
				had_eacces = 1;
		}
		if (fd == -1) {
			fprintf(stderr, "No compatible devices found.\n");
			if (had_eacces)
				fprintf(stderr, "At least one device "
					"could not be checked because "
					"of lack of permissions for "
					"/dev/hidraw*.\n");
		}
	}

	if (fd == -1)
		return 1;

	dump_names(fd);
	dump_times(fd);
	dump_temps(fd);
	dump_fan(fd);
	dump_global_power(fd);
	dump_powers(fd);

	send_recv_cmd(fd, 0x02, 0x00, 0x00, NULL, 0);

	close(fd);
	return 0;
}
