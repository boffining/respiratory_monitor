// Copyright (c) Acconeer AB, 2022-2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "acc_definitions_common.h"
#include "acc_hal_definitions_a121.h"
#include "acc_hal_integration_a121.h"
#include "acc_integration.h"
#include "acc_integration_log.h"
#include "acc_libgpiod.h"
#include "acc_libspi.h"

#define SENSOR_COUNT (5) /**< @brief The number of sensors available on the board */

#define PIN_SPI_SEL0 (17) /**< @brief SPI S1 enable BCM:18 J5:11 */
#define PIN_SPI_SEL1 (27) /**< @brief SPI S1 enable BCM:18 J5:13 */
#define PIN_SPI_SEL2 (22) /**< @brief SPI S1 enable BCM:18 J5:15 */

#define PIN_SEN_EN1_3V3 (5)  /**< @brief Gpio Enable S1 BCM:23 J5:29 */
#define PIN_SEN_EN2_3V3 (20) /**< @brief Gpio Enable S2 BCM:5 J5:38 */
#define PIN_SEN_EN3_3V3 (25) /**< @brief Gpio Enable S3 BCM:12 J5:22 */
#define PIN_SEN_EN4_3V3 (24) /**< @brief Gpio Enable S4 BCM:26 J5:18 */
#define PIN_SEN_EN5_3V3 (23) /**< @brief Gpio Enable S4 BCM:26 J5:16 */

#define PIN_SEN_INT1_3V3 (26) /**< @brief Gpio Interrupt S1 BCM:20 J5:37, connect to sensor 1 GPIO 5 */
#define PIN_SEN_INT2_3V3 (16) /**< @brief Gpio Interrupt S2 BCM:21 J5:36, connect to sensor 2 GPIO 5 */
#define PIN_SEN_INT3_3V3 (13) /**< @brief Gpio Interrupt S3 BCM:24 J5:33, connect to sensor 3 GPIO 5 */
#define PIN_SEN_INT4_3V3 (12) /**< @brief Gpio Interrupt S4 BCM:25 J5:32, connect to sensor 4 GPIO 5 */
#define PIN_SEN_INT5_3V3 (6)  /**< @brief Gpio Interrupt S5 BCM:25 J5:31, connect to sensor 5 GPIO 5 */

#define ACC_BOARD_SPI_SPEED (15000000) /**< @brief The SPI speed of this board */
#define ACC_BOARD_BUS       (0)        /**< @brief The SPI bus of this board */
#define ACC_BOARD_CS        (0)        /**< @brief The SPI device of the board */

typedef struct
{
	const int enable_pin;
	const int interrupt_pin;
} acc_sensor_info_t;

acc_sensor_info_t sensor_infos[SENSOR_COUNT] = {
    {PIN_SEN_EN1_3V3, PIN_SEN_INT1_3V3},
    {PIN_SEN_EN2_3V3, PIN_SEN_INT2_3V3},
    {PIN_SEN_EN3_3V3, PIN_SEN_INT3_3V3},
    {PIN_SEN_EN4_3V3, PIN_SEN_INT4_3V3},
    {PIN_SEN_EN5_3V3, PIN_SEN_INT5_3V3},
};

static const gpio_config_t pin_config[] = {{PIN_SPI_SEL0, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SPI_SEL1, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SPI_SEL2, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SEN_EN1_3V3, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SEN_EN2_3V3, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SEN_EN3_3V3, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SEN_EN4_3V3, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SEN_EN5_3V3, GPIO_DIR_OUTPUT_LOW},
                                           {PIN_SEN_INT1_3V3, GPIO_DIR_INPUT_INTERRUPT},
                                           {PIN_SEN_INT2_3V3, GPIO_DIR_INPUT_INTERRUPT},
                                           {PIN_SEN_INT3_3V3, GPIO_DIR_INPUT_INTERRUPT},
                                           {PIN_SEN_INT4_3V3, GPIO_DIR_INPUT_INTERRUPT},
                                           {PIN_SEN_INT5_3V3, GPIO_DIR_INPUT_INTERRUPT},
                                           {0, GPIO_DIR_UNKNOWN}};

static uint32_t spi_speed = ACC_BOARD_SPI_SPEED;

static pthread_mutex_t spi_mutex;

static void board_deinit(void)
{
	acc_libgpiod_deinit();

	acc_libspi_deinit();
	pthread_mutex_destroy(&spi_mutex);
}

static bool acc_board_init(void)
{
	static bool init_done = false;
	bool        result    = true;

	if (init_done)
	{
		return true;
	}

	if (atexit(board_deinit))
	{
		fprintf(stderr, "Unable to set exit function 'board_deinit()'\n");
		result = false;
	}

	if (result)
	{
		result = acc_libspi_init();
	}

	if (result)
	{
		int res = pthread_mutex_init(&spi_mutex, NULL);
		if (res != 0)
		{
			printf("pthread_mutex_init failed: %s\n", strerror(res));
			result = false;
		}
	}

	if (result)
	{
		result = acc_libgpiod_init(pin_config);
	}

	if (result)
	{
		init_done = true;
	}

	return result;
}

static bool acc_board_spi_select(acc_sensor_id_t sensor_id)
{
	assert(sensor_id <= SENSOR_COUNT);

	gpio_pin_value_t sel0 = PIN_LOW;
	gpio_pin_value_t sel1 = PIN_LOW;
	gpio_pin_value_t sel2 = PIN_LOW;

	switch (sensor_id)
	{
		case 1:
			break;
		case 2:
			sel0 = PIN_HIGH;
			break;
		case 3:
			sel1 = PIN_HIGH;
			break;
		case 4:
			sel0 = PIN_HIGH;
			sel1 = PIN_HIGH;
			break;
		case 5:
			sel2 = PIN_HIGH;
			break;
	}

	if (!acc_libgpiod_set(PIN_SPI_SEL0, sel0))
	{
		fprintf(stderr, "%s: Unable to set level on spi_sel0\n", __func__);
		return false;
	}

	if (!acc_libgpiod_set(PIN_SPI_SEL1, sel1))
	{
		fprintf(stderr, "%s: Unable to set level on spi_sel1\n", __func__);
		return false;
	}

	if (!acc_libgpiod_set(PIN_SPI_SEL2, sel2))
	{
		fprintf(stderr, "%s: Unable to set level on spi_sel2\n", __func__);
		return false;
	}

	return true;
}

static void acc_board_sensor_transfer(acc_sensor_id_t sensor_id, uint8_t *buffer, size_t buffer_length)
{
	assert(sensor_id <= SENSOR_COUNT);
	bool result = pthread_mutex_lock(&spi_mutex) == 0;
	assert(result);

	result = acc_board_spi_select(sensor_id);
	assert(result);

	result = acc_libspi_transfer(spi_speed, buffer, buffer_length);
	assert(result);

	result = pthread_mutex_unlock(&spi_mutex) == 0;
	assert(result);
	(void)result;
}

void acc_hal_integration_sensor_supply_on(acc_sensor_id_t sensor_id)
{
	assert(sensor_id <= SENSOR_COUNT);
	// It is not possible to control the supply on the xe121
	(void)sensor_id;
}

static void sensor_reset_hibernation_state(acc_sensor_id_t sensor_id)
{
	// Enable-disable toggle will reset the hibernation state
	acc_hal_integration_sensor_enable(sensor_id);
	acc_hal_integration_sensor_disable(sensor_id);
}

void acc_hal_integration_sensor_supply_off(acc_sensor_id_t sensor_id)
{
	// It is not possible to control the supply on the xe121

	// If the sensor cannot be powered off, like in this integration,
	// the hibernation state must be reset during the supply off sequence
	sensor_reset_hibernation_state(sensor_id);
}

void acc_hal_integration_sensor_enable(acc_sensor_id_t sensor_id)
{
	assert(sensor_id <= SENSOR_COUNT);
	acc_sensor_info_t *sensor_info = &sensor_infos[sensor_id - 1];

	if (!acc_libgpiod_set(sensor_info->enable_pin, PIN_HIGH))
	{
		fprintf(stderr, "%s: Unable to activate enable_pin for sensor %" PRIsensor_id ".\n", __func__, sensor_id);
		assert(false);
	}

	// Wait 2 ms to make sure that the sensor crystal has time to stabilize
	acc_integration_sleep_ms(2);
}

void acc_hal_integration_sensor_disable(acc_sensor_id_t sensor_id)
{
	assert(sensor_id <= SENSOR_COUNT);
	acc_sensor_info_t *sensor_info = &sensor_infos[sensor_id - 1];

	// Disable sensor
	if (!acc_libgpiod_set(sensor_info->enable_pin, PIN_LOW))
	{
		fprintf(stderr, "%s: Unable to deactivate enable_pin for sensor %" PRIsensor_id ".\n", __func__, sensor_id);
		assert(false);
	}

	// Wait after disable to leave the sensor in a known state
	// in case the application intends to enable the sensor directly
	acc_integration_sleep_ms(2);
}

bool acc_hal_integration_wait_for_sensor_interrupt(acc_sensor_id_t sensor_id, uint32_t timeout_ms)
{
	assert(sensor_id <= SENSOR_COUNT);
	return acc_libgpiod_wait_for_interrupt(sensor_infos[sensor_id - 1].interrupt_pin, timeout_ms);
}

uint16_t acc_hal_integration_sensor_count(void)
{
	return SENSOR_COUNT;
}

const acc_hal_a121_t *acc_hal_rss_integration_get_implementation(void)
{
	if (!acc_board_init())
	{
		return NULL;
	}

	static const acc_hal_a121_t val = {
	    .max_spi_transfer_size = MAX_SPI_TRANSFER_SIZE,

	    .mem_alloc = malloc,
	    .mem_free  = free,

	    .transfer = acc_board_sensor_transfer,
	    .log      = acc_integration_log,

	    .optimization.transfer16 = NULL,
	};

	return &val;
}
