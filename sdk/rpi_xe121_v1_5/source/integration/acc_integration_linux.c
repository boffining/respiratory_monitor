// Copyright (c) Acconeer AB, 2019-2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include "acc_integration.h"

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>


void acc_integration_sleep_us(uint32_t time_usec)
{
	int             ret = 0;
	struct timespec ts;
	struct timespec remain;

	if (time_usec == 0)
	{
		time_usec = 1;
	}

	ts.tv_sec  = time_usec / 1000000;
	ts.tv_nsec = (time_usec % 1000000) * 1000;

	do
	{
		ret = clock_nanosleep(CLOCK_MONOTONIC, 0, &ts, &remain);
		ts  = remain;
	} while (ret == EINTR);
}


void acc_integration_sleep_ms(uint32_t time_msec)
{
	acc_integration_sleep_us(time_msec * 1000);
}


uint32_t acc_integration_get_time(void)
{
	struct timespec time_ts = {0};

	clock_gettime(CLOCK_MONOTONIC, &time_ts);
	return time_ts.tv_sec * 1000 + time_ts.tv_nsec / 1000000;
}


void *acc_integration_mem_alloc(size_t size)
{
	return malloc(size);
}


void *acc_integration_mem_calloc(size_t nmemb, size_t size)
{
	return calloc(nmemb, size);
}


void acc_integration_mem_free(void *ptr)
{
	free(ptr);
}
