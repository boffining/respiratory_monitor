// Copyright (c) Acconeer AB, 2021
// All rights reserved

#ifndef ACC_LIBGPIOD_H_
#define ACC_LIBGPIOD_H_

#include <stdbool.h>
#include <stdint.h>

typedef enum
{
	PIN_LOW  = 0,
	PIN_HIGH = 1,
} gpio_pin_value_t;

typedef enum
{
	GPIO_DIR_UNKNOWN,
	GPIO_DIR_INPUT_INTERRUPT,
	GPIO_DIR_OUTPUT_HIGH,
	GPIO_DIR_OUTPUT_LOW,
} gpio_direction_t;

typedef struct
{
	unsigned int     pin;
	gpio_direction_t direction;
} gpio_config_t;

typedef struct
{
	struct gpiod_line *line;
	gpio_direction_t   direction;
} gpio_pin_t;

/**
 * Initialize gpio and configure a list of gpios
 *
 * Free any resources allocated with this cll by calling acc_libgpiod_deinit()
 *
 * @param[in] pin_config An array of pin configs, last entry should be terminated
 *                       with the direction set to GPIO_DIR_UNKNOWN.
 *
 * @return true if successful
 */
bool acc_libgpiod_init(const gpio_config_t *pin_config);

/**
 * Deinitialize gpio and free resources
 */
void acc_libgpiod_deinit(void);

/**
 * Set a gpio output pin
 *
 * The pin must have been initialized as GPIO_DIR_OUTPUT_HIGH or GPIO_DIR_OUTPUT_LOW.
 *
 * @param[in] pin The pin
 * @param[in] value The value
 *
 * @return true if successful
 */
bool acc_libgpiod_set(int pin, gpio_pin_value_t value);

/**
 * Wait for an interrupt
 *
 * This function waits for an rising edge interrupt and then verifies that
 * the interrupt pin is high. If it is not high it will wait again for
 * another interrupt. This extra loop makes sure that this function does
 * not return true if the interrupt pin is low (could be caused by a
 * previous interrupt that occurred before or during sensor initialization).
 *
 * This function asserts that the pin previously has been initialized as
 * GPIO_DIR_INPUT_INTERRUPT. It also asserts that all gpio operations
 * are successfully.
 *
 * @param[in] pin The pin.
 * @param[in] timeout_ms Maximum time in milliseconds to wait for an interrupt
 *
 * @return true if an interrupt was received within timeout
 */
bool acc_libgpiod_wait_for_interrupt(int pin, uint32_t timeout_ms);

#endif
