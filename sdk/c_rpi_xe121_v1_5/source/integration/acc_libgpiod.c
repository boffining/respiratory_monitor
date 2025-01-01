// Copyright (c) Acconeer AB, 2019-2022
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.
#include <assert.h>
#include <stdio.h>
#include <time.h>

#include "gpiod.h"

#include "acc_libgpiod.h"

/**
 * @brief Number of GPIO pins on the raspberry pi
 */
#define GPIO_PIN_COUNT    28
#define RPI_GPIO_CHIPNAME "gpiochip0"
#define GPIOD_CONSUMER    "Acconeer"

static gpio_pin_t        gpios[GPIO_PIN_COUNT];
static struct gpiod_chip *chip;


static bool gpio_open(int pin, gpio_direction_t direction)
{
	gpios[pin].line = gpiod_chip_get_line(chip, pin);
	if (gpios[pin].line == NULL)
	{
		perror("Failed opening line");
		return false;
	}

	gpios[pin].direction = direction;

	int res;

	switch (direction)
	{
		case GPIO_DIR_INPUT_INTERRUPT:
			res = gpiod_line_request_rising_edge_events(gpios[pin].line,
			                                            GPIOD_CONSUMER);
			break;
		case GPIO_DIR_OUTPUT_LOW:
		case GPIO_DIR_OUTPUT_HIGH:
			res = gpiod_line_request_output(gpios[pin].line,
			                                GPIOD_CONSUMER,
			                                direction == GPIO_DIR_OUTPUT_HIGH ? PIN_HIGH : PIN_LOW);
			break;
		default:
			res = -1;
			assert(false);
	}

	if (res != 0)
	{
		perror("gpiod_line_request_ failed");
		return false;
	}

	return true;
}


bool acc_libgpiod_init(const gpio_config_t *pin_config)
{
	int pin = 0;

	for (pin = 0; pin < GPIO_PIN_COUNT; pin++)
	{
		gpios[pin].direction = GPIO_DIR_UNKNOWN;
	}

	chip = gpiod_chip_open_by_name(RPI_GPIO_CHIPNAME);
	if (chip == NULL)
	{
		perror("gpiod_chip_open_by_name failed");
		return false;
	}

	pin = 0;
	while (pin_config[pin].direction != GPIO_DIR_UNKNOWN)
	{
		if (!gpio_open(pin_config[pin].pin, pin_config[pin].direction))
		{
			return false;
		}

		pin++;
	}
	return true;
}


void acc_libgpiod_deinit(void)
{
	if (chip != NULL)
	{
		for (int pin = 0; pin < GPIO_PIN_COUNT; pin++)
		{
			if (gpios[pin].direction != GPIO_DIR_UNKNOWN)
			{
				gpiod_line_release(gpios[pin].line);
				gpios[pin].direction = GPIO_DIR_UNKNOWN;
			}
		}

		gpiod_chip_close(chip);
		chip = NULL;
	}
}


bool acc_libgpiod_set(int pin, gpio_pin_value_t value)
{
	assert((gpios[pin].direction == GPIO_DIR_OUTPUT_HIGH) ||
	       (gpios[pin].direction == GPIO_DIR_OUTPUT_LOW));

	int res = gpiod_line_set_value(gpios[pin].line, value);
	if (res != 0)
	{
		perror("gpiod_line_set_value failed");
		return false;
	}

	return true;
}


static unsigned int get_elapsed_ms(struct timespec *start)
{
	struct timespec now;

	clock_gettime(CLOCK_MONOTONIC, &now);
	int elapsed = (((now.tv_sec - start->tv_sec) * 1000) +
	               (now.tv_nsec - start->tv_nsec) / 1000000);
	assert(elapsed >= 0);
	return elapsed;
}


bool acc_libgpiod_wait_for_interrupt(int pin, uint32_t timeout_ms)
{
	assert(gpios[pin].direction == GPIO_DIR_INPUT_INTERRUPT);

	struct timespec start;
	clock_gettime(CLOCK_MONOTONIC, &start);

	int pin_value = gpiod_line_get_value(gpios[pin].line);
	assert(pin_value >= 0);

	unsigned int elapsed_ms = get_elapsed_ms(&start);

	while ((pin_value != PIN_HIGH) && (elapsed_ms < timeout_ms))
	{
		timeout_ms -= elapsed_ms;
		time_t          secs = timeout_ms / 1000;
		long            ns   = (timeout_ms % 1000) * 1000000;
		struct timespec ts   = { secs, ns };
		int             res  = gpiod_line_event_wait(gpios[pin].line, &ts);
		if (res < 0)
		{
			perror("gpiod_line_event_wait failed");
			assert(true);
		}
		else if (res == 0)
		{
			// Timeout
			break;
		}
		else
		{
			// Wait complete, check which event we got.
			struct gpiod_line_event event;
			res = gpiod_line_event_read(gpios[pin].line, &event);
			if (res != 0)
			{
				perror("gpiod_line_event_read failed");
				assert(true);
			}

			if (event.event_type != GPIOD_LINE_EVENT_RISING_EDGE)
			{
				// The enums were renumbered between v1.0 and v1.1, make sure gpiod.h matches
				// the shared library version if this happens.
				fprintf(stderr, "Unexpected event_type: %d (expected %d), library version mismatch?\n",
				        event.event_type, GPIOD_LINE_EVENT_RISING_EDGE);
				assert(true);
			}

			pin_value = gpiod_line_get_value(gpios[pin].line);
			if (pin_value < 0)
			{
				perror("gpiod_line_get_value failed");
				assert(true);
			}
		}

		elapsed_ms = get_elapsed_ms(&start);
	}
	return pin_value == PIN_HIGH;
}
