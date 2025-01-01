// Copyright (c) Acconeer AB, 2019-2021
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/spi/spidev.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "acc_libspi.h"

#define ACC_BOARD_SPI_BUS 0
#define SPIDEV_PATH      "/dev/spidev%u.%u"
#define ACC_BOARD_SPI_CS 0

static int spi_fd = -1;


bool acc_libspi_init(void)
{
	uint32_t mode   = SPI_MODE_0;
	bool     result = true;
	char     spidev[sizeof(SPIDEV_PATH) + 2];

	snprintf(spidev, sizeof(spidev), SPIDEV_PATH, ACC_BOARD_SPI_BUS, ACC_BOARD_SPI_CS);

	spi_fd = open(spidev, O_RDWR);

	if (spi_fd < 0)
	{
		printf("Unable to open SPI (%u, %u): %s\n", ACC_BOARD_SPI_BUS, ACC_BOARD_SPI_CS, strerror(errno));
		result = false;
	}

	if (result)
	{
		if (ioctl(spi_fd, SPI_IOC_RD_MODE32, &mode) < 0)
		{
			printf("Could not set SPI (read) mode %u\n", mode);
			result = false;
		}
	}

	if (result)
	{
		if (ioctl(spi_fd, SPI_IOC_WR_MODE32, &mode) < 0)
		{
			printf("Could not set SPI (write) mode %u\n", mode);
			result = false;
		}
	}

	return result;
}


void acc_libspi_deinit(void)
{
	if (spi_fd >= 0)
	{
		close(spi_fd);
		spi_fd = -1;
	}
}


bool acc_libspi_transfer(uint32_t speed, uint8_t *buffer, size_t buffer_size)
{
	bool                    result       = true;
	struct spi_ioc_transfer spi_transfer = {
		.tx_buf        = (uintptr_t)buffer,
		.rx_buf        = (uintptr_t)buffer,
		.len           = buffer_size,
		.delay_usecs   = 0,
		.speed_hz      = speed,
		.bits_per_word = 8,
		.cs_change     = 0,
		.pad           = 0,
	};

	int ret_val = ioctl(spi_fd, SPI_IOC_MESSAGE(1), &spi_transfer);

	if (ret_val < 0)
	{
		perror("SPI transfer failure");
		result = false;
	}

	return result;
}
