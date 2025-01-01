// Copyright (c) Acconeer AB, 2020-2024
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "IRadarSensor.h"
#include "ripple_api_port_definitions.h"

/** \example example_ripple.c
 * @brief This is an example of how to use the Ripple API with the Acconeer sensor.
 * @n
 * The example executes as follows:
 *   - Start the radar with a specific configuration
 *   - Read out data five times and print the result
 *   - Stop the radar
 */

// Main parameters
#define BURST_PERIOD_US       (30000) // 33 Hz update rate
#define SWEEP_PERIOD_US       (0)     // Produce sweeps as fast as possible
#define SWEEPS_PER_BURST      (8)
#define SAMPLES_PER_SWEEP     (20)
#define AFTERBURST_POWER_MODE (0) // 0 means deepest power mode
#define INTERSWEEP_POWER_MODE (2) // 0 means most shallow power mode
#define START_POINT           (80)

// RX parameters
#define RECEIVER_GAIN (16)

// Vendor specific parameters
#define STEP_LENGTH (8)
#define HWAAS       (8)
#define PROFILE     (ACC_RADAR_PROFILE_3)
#define PRF         (ACC_RADAR_PRF_15_6_MHZ)
#define ENABLE_TX   (1)

/**
 *
 * Range calculations using above settings:
 *
 * The 'base' step length for the A121 radar is 2.5 mm.
 * start_point: 80 * 2.5 mm = 20 cm
 * step_length: 8 * 2.5 mm = 2 cm
 * samples_per_sweep: 20 * 8 * 2.5 mm = 40 cm
 *
 * So the range window used in the example is
 * 20 cm - 60 cm with 2 cm spacing.
 *
 */

// General macros
#define SENSOR_ID          (1U)
#define SLOT_ID            (SENSOR_ID) // Only allow one configuration
#define ANTENNA_MASK       (1)         // Only one channel on A121
#define BURST_LENGTH       (SWEEPS_PER_BURST * SAMPLES_PER_SWEEP)
#define BUFFER_SIZE        (BURST_LENGTH * 4)    // Each sample is 4 bytes long
#define TIMEOUT_US         (BURST_PERIOD_US * 4) // Set timeout to four periods
#define MAX_DATA_ENTRY_LEN 15                    // "-32000+-32000i" + zero termination

// Struct used to interpret radar data from A121
typedef struct
{
	int16_t real;
	int16_t imag;
} int16_complex_t;

// Helper structs to hold config params.
typedef struct
{
	RadarMainParam param;
	uint32_t       value;
} radar_main_params_t;

typedef struct
{
	RadarRxParam param;
	uint32_t     value;
} radar_rx_params_t;

typedef struct
{
	RadarVendorParam param;
	uint32_t         value;
} vendor_params_t;

// Configure radar.
static const radar_main_params_t main_params[] = {
    {{RADAR_PARAM_GROUP_COMMON, RADAR_PARAM_AFTERBURST_POWER_MODE}, AFTERBURST_POWER_MODE},
    {{RADAR_PARAM_GROUP_COMMON, RADAR_PARAM_BURST_PERIOD_US}, BURST_PERIOD_US},
    {{RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_INTERSWEEP_POWER_MODE}, INTERSWEEP_POWER_MODE},
    {{RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_SWEEP_PERIOD_US}, SWEEP_PERIOD_US},
    {{RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_SWEEPS_PER_BURST}, SWEEPS_PER_BURST},
    {{RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_SAMPLES_PER_SWEEP}, SAMPLES_PER_SWEEP},
    {{RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_START_OFFSET}, START_POINT},
    {{RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_PRF_IDX}, PRF},
};

static const radar_rx_params_t rx_params[] = {
    {{RADAR_PARAM_GROUP_PULSED, PULSED_RX_PARAM_VGA_IDX}, RECEIVER_GAIN},
};

static const vendor_params_t vendor_params[] = {
    {PULSED_PARAM_STEP_LENGTH, STEP_LENGTH},
    {PULSED_PARAM_HWAAS, HWAAS},
    {PULSED_PARAM_PROFILE, PROFILE},
    {PULSED_PARAM_ENABLE_TX, ENABLE_TX},
};

static const int num_main_params = sizeof(main_params) / sizeof(main_params[0]);

static const int num_rx_params = sizeof(rx_params) / sizeof(rx_params[0]);

static const int num_vendor_params = sizeof(vendor_params) / sizeof(vendor_params[0]);

static void print_data(int16_complex_t *data, uint16_t burst_length, uint16_t sweeps_per_burst);

static void on_log_cb(RadarLogLevel level, const char *file, const char *function, int line, void *user_data, const char *message)
{
	(void)user_data;
	(void)function;
	(void)line;

	if (level == RLOG_DBG)
	{
		printf("RADAR DBG %s: %s\n", file, message);
	}
	else if (level == RLOG_INF)
	{
		printf("RADAR INFO %s: %s\n", file, message);
	}
	else if (level == RLOG_ERR)
	{
		printf("RADAR ERR %s: %s\n", file, message);
	}
}

static volatile bool burst_ready = false;

static void on_burst_ready_cb(void *user_data)
{
	(void)user_data;
	burst_ready = true;
}

int main(int argc, char *argv[]);

int main(int argc, char *argv[])
{
	(void)argc;
	(void)argv;

	RadarHandle *radar_handle = NULL;
	SensorInfo   sensor_info;

	Version ripple_version = radarGetRadarApiVersion();
	printf("Ripple version v%u.%u.%u (build: %u)\n", ripple_version.major, ripple_version.minor, ripple_version.patch, ripple_version.build);

	if (radarInit() != RC_OK)
	{
		printf("radarInit() failed\n");
		return EXIT_FAILURE;
	}

	radar_handle = radarCreate(SENSOR_ID);

	if (radar_handle == NULL)
	{
		printf("radarCreate() failed\n");
		return EXIT_FAILURE;
	}

	if (radarGetSensorInfo(radar_handle, &sensor_info) != RC_OK)
	{
		printf("radarGetSensorInfo() failed\n");
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	printf("Sensor info: %s %s (0x%x), radar type: %u\n", sensor_info.vendor, sensor_info.name, sensor_info.device_id, sensor_info.radar_type);

	if (radarSetLogLevel(radar_handle, RLOG_DBG) != RC_OK)
	{
		printf("radarSetLogLevel() failed\n");
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	if (radarSetLogCb(radar_handle, on_log_cb, NULL) != RC_OK)
	{
		printf("radarSetLogCb() failed\n");
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	if (radarSetBurstReadyCb(radar_handle, on_burst_ready_cb, NULL) != RC_OK)
	{
		printf("radarSetBurstReadyCb() failed\n");
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	// Set main params
	for (uint16_t i = 0; i < num_main_params; i++)
	{
		RadarMainParam param = main_params[i].param;
		uint32_t       value = main_params[i].value;

		if (radarSetMainParam(radar_handle, SLOT_ID, param, value) != RC_OK)
		{
			printf("radarSetMainParam() failed\n");
			radarDestroy(radar_handle);
			return EXIT_FAILURE;
		}
	}

	// Set RX params
	for (uint16_t i = 0; i < num_rx_params; i++)
	{
		RadarRxParam param = rx_params[i].param;
		uint32_t     value = rx_params[i].value;

		if (radarSetRxParam(radar_handle, SLOT_ID, ANTENNA_MASK, param, value) != RC_OK)
		{
			printf("radarSetRxParam() failed\n");
			radarDestroy(radar_handle);
			return EXIT_FAILURE;
		}
	}

	// Set vendor params
	for (uint16_t i = 0; i < num_vendor_params; i++)
	{
		RadarVendorParam param = vendor_params[i].param;
		uint32_t         value = vendor_params[i].value;

		if (radarSetVendorParam(radar_handle, SLOT_ID, param, value) != RC_OK)
		{
			printf("radarSetVendorParam() failed\n");
			radarDestroy(radar_handle);
			return EXIT_FAILURE;
		}
	}

	// Should not start the radar
	if (radarActivateConfig(radar_handle, SLOT_ID) != RC_OK)
	{
		printf("radarActivateConfig() failed\n");
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	radarLogSensorDetails(radar_handle);

	if (radarTurnOn(radar_handle) != RC_OK)
	{
		printf("radarTurnOn() failed\n");
		radarDeactivateConfig(radar_handle, SLOT_ID);
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	if (radarStartDataStreaming(radar_handle) != RC_OK)
	{
		printf("radarStartDataStreaming() failed\n");
		radarTurnOff(radar_handle);
		radarDeactivateConfig(radar_handle, SLOT_ID);
		radarDestroy(radar_handle);
		return EXIT_FAILURE;
	}

	bool             status       = true;
	RadarBurstFormat burst_format = {0};
	uint8_t          buffer[BUFFER_SIZE];
	uint32_t         bytes_read;
	struct timespec  timeout;

	timeout.tv_sec  = 0;
	timeout.tv_nsec = TIMEOUT_US; // tv_nsec is in us until multiplication below
	while (timeout.tv_nsec >= 1000000)
	{
		timeout.tv_sec++;
		timeout.tv_nsec -= 1000000;
	}
	timeout.tv_nsec *= 1000;

	for (uint16_t i = 0; i < 5; i++)
	{
		while (!burst_ready)
		{
			// WAIT for data
		}
		burst_ready = false;
		bytes_read  = BUFFER_SIZE;

		if (radarReadBurst(radar_handle, &burst_format, buffer, &bytes_read, timeout) != RC_OK)
		{
			printf("radarReadBurst() failed\n");
			status = false;
			break;
		}

		// Range doppler processing could be performed here (not done in the sensor HW)

		print_data((int16_complex_t *)buffer, BURST_LENGTH, SWEEPS_PER_BURST);
	}

	radarStopDataStreaming(radar_handle);
	radarTurnOff(radar_handle);
	radarDeactivateConfig(radar_handle, SLOT_ID);
	radarDestroy(radar_handle);
	radarDeinit();

	if (status)
	{
		printf("Application finished OK\n");
	}

	return EXIT_SUCCESS;
}

void print_data(int16_complex_t *data, uint16_t burst_length, uint16_t sweeps_per_burst)
{
	printf("Radar burst:\n");

	uint16_t sweep_length = burst_length / sweeps_per_burst;
	char     buffer[MAX_DATA_ENTRY_LEN];

	for (uint16_t sweep = 0; sweep < sweeps_per_burst; sweep++)
	{
		printf("Sweep %u:\n", (unsigned int)(sweep + 1));

		for (uint16_t i = 0; i < sweep_length; i++)
		{
			snprintf(
			    buffer, sizeof(buffer), "%" PRIi16 "+%" PRIi16 "i", data[(sweep * sweep_length) + i].real, data[(sweep * sweep_length) + i].imag);
			printf("%14s ", buffer);
		}

		printf("\n");
	}

	printf("\n");
}
