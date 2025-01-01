// Copyright (c) Acconeer AB, 2022-2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <pthread.h>
#include <semaphore.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include "acc_config.h"
#include "acc_definitions_a121.h"
#include "acc_definitions_common.h"
#include "acc_hal_definitions_a121.h"
#include "acc_hal_integration_a121.h"
#include "acc_integration.h"
#include "acc_integration_log.h"
#include "acc_processing.h"
#include "acc_rss_a121.h"
#include "acc_sensor.h"
#include "acc_version.h"
#include "IRadarSensor.h"
#include "ripple_api_port_definitions.h"

#define MODULE "RIPPLE_API_PORT"

#define MIN_SENSOR_INTERRUPT_TIMEOUT_MS (100U)
#define CAL_BUFFER_SIZE                 (4096U)
#define CAL_TIMEOUT_MS                  (1000U)
#define LOG_BUFFER_MAX_SIZE             (150)
#define MAX_NBR_CONFIG_SLOTS            (1U)


typedef struct
{
	RadarLogCB log_callback;
	void       *log_callback_data;

	RadarBurstReadyCB burst_ready_callback;
	void              *burst_ready_callback_data;
} radar_callbacks_t;

typedef struct RadarHandleImpl
{
	acc_sensor_id_t  sensor_id;
	acc_config_t     *config;
	acc_sensor_t     *sensor;
	acc_processing_t *processing;

	acc_cal_result_t cal_result;
	void             *buffer;
	uint32_t         buffer_size;

	acc_processing_metadata_t proc_meta;
	acc_processing_result_t   proc_result;

	radar_callbacks_t callbacks;
	RadarLogLevel     radar_log_level;

	RadarState current_state;
	uint32_t   sequence_number;

	uint32_t sensor_timeout_ms;
	bool     is_burst_ready;
} AccRadarHandle;

typedef struct
{
	uint32_t group;
	uint32_t id;
	uint32_t min_value;
	uint32_t max_value;
} radar_param_range_t;

typedef struct
{
	AccRadarHandle  *radar_handle;
	sem_t           read_sem;
	sem_t           meas_sem;
	bool            stop_run;
	RadarReturnCode radar_status;
} sensor_thread_data_t;


//-----------------------------
// Private declarations
//-----------------------------


static const radar_param_range_t main_param_range[] =
{
	{ RADAR_PARAM_GROUP_COMMON, RADAR_PARAM_AFTERBURST_POWER_MODE,  0U, 2U },
	{ RADAR_PARAM_GROUP_COMMON, RADAR_PARAM_BURST_PERIOD_US,        0U, UINT32_MAX },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_INTERSWEEP_POWER_MODE, 0U, 2U },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_SWEEP_PERIOD_US,       0U, UINT32_MAX },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_SWEEPS_PER_BURST,      1U, UINT32_MAX },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_SAMPLES_PER_SWEEP,     1U, UINT32_MAX },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_START_OFFSET,          0U, UINT32_MAX },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_PRF_IDX,               ACC_RADAR_PRF_19_5_MHZ, ACC_RADAR_PRF_5_2_MHZ },
};

static const radar_param_range_t rx_param_range[] =
{
	{ RADAR_PARAM_GROUP_PULSED, PULSED_RX_PARAM_VGA_IDX, 0U, 23U },
};

static const radar_param_range_t vendor_param_range[] =
{
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_STEP_LENGTH, 1U, UINT32_MAX },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_HWAAS,       1U, 511U },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_PROFILE,     ACC_RADAR_PROFILE_1, ACC_RADAR_PROFILE_5 },
	{ RADAR_PARAM_GROUP_PULSED, PULSED_PARAM_ENABLE_TX,   0U, 1U },
};

static const int num_main_params = sizeof(main_param_range) / sizeof(main_param_range[0]);

static const int num_rx_params = sizeof(rx_param_range) / sizeof(rx_param_range[0]);

static const int num_vendor_params = sizeof(vendor_param_range) / sizeof(vendor_param_range[0]);

static const Version api_version =
{
	.major = 2U,
	.minor = 0U,
	.patch = 0U,
	.build = 1U,
};

static const SensorInfo sensor_info =
{
	.name           = "A121",
	.vendor         = "Acconeer",
	.device_id      = 0x1210,
	.radar_type     = RTYPE_PULSED,
	.driver_version = api_version,
};

static pthread_t sensor_thread_handle;

static sensor_thread_data_t sensor_thread_data;


/*
 * This static handle is needed since we don't have any way of propagating
 * user data through the RSS log framework
 */
static RadarHandle *log_radar_handle = NULL;

static void radar_handle_cleanup(RadarHandle *radar_handle);


static acc_config_idle_state_t to_idle_state(uint32_t value);


static uint32_t from_idle_state(acc_config_idle_state_t idle_state);


static acc_config_profile_t to_profile(uint32_t value);


static uint32_t from_profile(acc_config_profile_t profile);


static acc_config_prf_t to_prf(uint32_t value);


static uint32_t from_prf(acc_config_prf_t prf);


static bool get_param_range(const radar_param_range_t *param_range, uint16_t nbr_params, uint32_t param_group, uint32_t param_id,
                            uint32_t *min_value, uint32_t *max_value);


static bool is_param_valid(const radar_param_range_t *param_range, uint16_t nbr_params, uint32_t param_group, uint32_t param_id, uint32_t value);


static void print_api_usage(RadarHandle *handle, const char *function);


static void *sensor_thread(void *param);


//-----------------------------
// Public definitions
//-----------------------------


RadarReturnCode radarInit(void)
{
	printf("Acconeer software version %s\n", acc_version_get());

	const acc_hal_a121_t *hal = acc_hal_rss_integration_get_implementation();

	if (!acc_rss_hal_register(hal))
	{
		return RC_ERROR;
	}

	return RC_OK;
}


RadarReturnCode radarDeinit(void)
{
	return RC_OK;
}


RadarHandle *radarCreate(int32_t id)
{
	RadarHandle *radar_handle = acc_integration_mem_alloc(sizeof(*radar_handle));

	bool status = radar_handle != NULL;

	if (status)
	{
		memset(radar_handle, 0, sizeof(*radar_handle));

		radar_handle->radar_log_level = RLOG_OFF;
		radar_handle->current_state   = RSTATE_OFF;
		radar_handle->sequence_number = 0;
		radar_handle->sensor_id       = id;

		log_radar_handle = radar_handle;

		radar_handle->config = acc_config_create();
		if (radar_handle->config == NULL)
		{
			status = false;
		}
	}

	if (status)
	{
		// Enable phase enhancement
		acc_config_phase_enhancement_set(radar_handle->config, true);

		acc_hal_integration_sensor_supply_on(radar_handle->sensor_id);
		acc_hal_integration_sensor_enable(radar_handle->sensor_id);

		radar_handle->sensor = acc_sensor_create(radar_handle->sensor_id);
		if (radar_handle->sensor == NULL)
		{
			status = false;
		}

		if (status)
		{
			bool    cal_complete = false;
			uint8_t cal_buffer[CAL_BUFFER_SIZE];

			do
			{
				status = acc_sensor_calibrate(radar_handle->sensor, &cal_complete, &radar_handle->cal_result, cal_buffer,
				                              CAL_BUFFER_SIZE);

				if (status && !cal_complete)
				{
					status = acc_hal_integration_wait_for_sensor_interrupt(radar_handle->sensor_id, CAL_TIMEOUT_MS);
				}
			} while (status && !cal_complete);
		}

		acc_hal_integration_sensor_disable(radar_handle->sensor_id);
		acc_hal_integration_sensor_supply_off(radar_handle->sensor_id);
	}

	if (!status)
	{
		radar_handle_cleanup(radar_handle);
		radar_handle = NULL;
	}

	return radar_handle;
}


RadarReturnCode radarDestroy(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		log_radar_handle = NULL;
		radar_handle_cleanup(handle);
	}

	return rc;
}


RadarReturnCode radarGetState(RadarHandle *handle, RadarState *state)
{
	RadarReturnCode rc = (handle != NULL && state != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		*state = handle->current_state;
	}

	return rc;
}


RadarReturnCode radarTurnOn(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->current_state != RSTATE_OFF)
		{
			ACC_LOG_ERROR("%s only supported from state OFF", __func__);
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		acc_hal_integration_sensor_supply_on(handle->sensor_id);
		acc_hal_integration_sensor_enable(handle->sensor_id);

		handle->current_state = RSTATE_IDLE;

		rc = acc_sensor_prepare(handle->sensor, handle->config, &handle->cal_result, handle->buffer, handle->buffer_size) ? RC_OK : RC_ERROR;
	}

	return rc;
}


RadarReturnCode radarTurnOff(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		// Special case if coming from sleep (hibernation)
		// to correctly leave hibernation
		if (handle->current_state == RSTATE_SLEEP)
		{
			rc = radarWakeUp(handle);
		}
	}

	if (rc == RC_OK)
	{
		acc_hal_integration_sensor_disable(handle->sensor_id);
		acc_hal_integration_sensor_supply_off(handle->sensor_id);

		handle->current_state = RSTATE_OFF;
	}

	return rc;
}


RadarReturnCode radarGoSleep(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->current_state != RSTATE_IDLE)
		{
			ACC_LOG_ERROR("%s only supported from state IDLE", __func__);
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		if (!acc_sensor_hibernate_on(handle->sensor))
		{
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		acc_hal_integration_sensor_disable(handle->sensor_id);
		handle->current_state = RSTATE_SLEEP;
	}

	return rc;
}


RadarReturnCode radarWakeUp(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->current_state != RSTATE_SLEEP)
		{
			ACC_LOG_ERROR("%s only supported from state SLEEP", __func__);
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		acc_hal_integration_sensor_enable(handle->sensor_id);

		if (!acc_sensor_hibernate_off(handle->sensor))
		{
			rc = RC_BAD_STATE;
		}

		handle->current_state = RSTATE_IDLE;
	}

	return rc;
}


RadarReturnCode radarGetNumConfigSlots(RadarHandle *handle, uint8_t *num_slots)
{
	RadarReturnCode rc = (handle != NULL && num_slots != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->processing != NULL)
		{
			*num_slots = 1;
		}
		else
		{
			*num_slots = 0;
		}
	}

	return rc;
}


RadarReturnCode radarGetMaxActiveConfigSlots(RadarHandle *handle, uint8_t *num_slots)
{
	RadarReturnCode rc = (handle != NULL && num_slots != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		*num_slots = MAX_NBR_CONFIG_SLOTS;
	}

	return rc;
}


RadarReturnCode radarActivateConfig(RadarHandle *handle, uint8_t slot_id)
{
	(void)slot_id;

	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = acc_rss_get_buffer_size(handle->config, &handle->buffer_size) ? RC_OK : RC_BAD_INPUT;
	}

	if (rc == RC_OK)
	{
		handle->buffer = acc_integration_mem_alloc(handle->buffer_size);

		rc = (handle->buffer != NULL) ? RC_OK : RC_RES_LIMIT;
	}

	if (rc == RC_OK)
	{
		handle->processing = acc_processing_create(handle->config, &handle->proc_meta);

		rc = (handle->processing != NULL) ? RC_OK : RC_ERROR;
	}

	return rc;
}


RadarReturnCode radarDeactivateConfig(RadarHandle *handle, uint8_t slot_id)
{
	(void)slot_id;

	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->processing != NULL)
		{
			acc_processing_destroy(handle->processing);
			handle->processing = NULL;
		}

		if (handle->buffer != NULL)
		{
			acc_integration_mem_free(handle->buffer);
			handle->buffer = NULL;
		}
	}

	return rc;
}


RadarReturnCode radarIsActiveConfig(RadarHandle *handle, uint8_t slot_id, bool *is_active)
{
	(void)handle;
	(void)slot_id;
	(void)is_active;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetMainParam(RadarHandle *handle, uint8_t slot_id, RadarMainParam param, uint32_t *value)
{
	(void)slot_id;

	RadarReturnCode rc = (handle != NULL && value != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (param.group == RADAR_PARAM_GROUP_COMMON)
		{
			switch (param.id)
			{
				case RADAR_PARAM_AFTERBURST_POWER_MODE:
				{
					acc_config_idle_state_t idle_state = acc_config_inter_frame_idle_state_get(handle->config);
					*value = from_idle_state(idle_state);
					break;
				}
				case RADAR_PARAM_BURST_PERIOD_US:
				{
					// Note that an update rate of '0' means that the sensor will only be limited by
					// the rate that the host acknowledge and reads out the measurement data.
					float update_rate = acc_config_frame_rate_get(handle->config);
					*value = (update_rate == 0.0f) ? 0 : (uint32_t)(1.0e6f / update_rate);
					break;
				}
				default:
				{
					rc = RC_BAD_INPUT;
					break;
				}
			}
		}
		else if (param.group == RADAR_PARAM_GROUP_PULSED)
		{
			switch (param.id)
			{
				case PULSED_PARAM_SWEEP_PERIOD_US:
				{
					// Note that a sweep rate of '0' means that the sensor will produce
					// sweeps as fast as possible.
					float sweep_rate = acc_config_sweep_rate_get(handle->config);
					*value = (sweep_rate == 0.0f) ? 0 : (uint32_t)(1.0e6f / sweep_rate);
					break;
				}
				case PULSED_PARAM_SWEEPS_PER_BURST:
				{
					*value = acc_config_sweeps_per_frame_get(handle->config);
					break;
				}
				case PULSED_PARAM_SAMPLES_PER_SWEEP:
				{
					*value = acc_config_num_points_get(handle->config);
					break;
				}
				case PULSED_PARAM_INTERSWEEP_POWER_MODE:
				{
					acc_config_idle_state_t idle_state = acc_config_inter_sweep_idle_state_get(handle->config);
					*value = from_idle_state(idle_state);
					break;
				}
				case PULSED_PARAM_START_OFFSET:
				{
					// Note that negative start points will not behave as expected
					// due to implicit conversion here
					*value = acc_config_start_point_get(handle->config);
					break;
				}
				case PULSED_PARAM_PRF_IDX:
				{
					acc_config_prf_t prf = acc_config_prf_get(handle->config);
					*value = from_prf(prf);
					break;
				}
				default:
				{
					rc = RC_BAD_INPUT;
					break;
				}
			}
		}
		else
		{
			rc = RC_BAD_INPUT;
		}
	}

	return rc;
}


RadarReturnCode radarSetMainParam(RadarHandle *handle, uint8_t slot_id, RadarMainParam param, uint32_t value)
{
	(void)slot_id;

	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = is_param_valid(main_param_range, num_main_params, param.group, param.id, value) ? RC_OK : RC_BAD_INPUT;
	}

	if (rc == RC_OK)
	{
		if (param.group == RADAR_PARAM_GROUP_COMMON)
		{
			switch (param.id)
			{
				case RADAR_PARAM_AFTERBURST_POWER_MODE:
				{
					acc_config_idle_state_t idle_state = to_idle_state(value);
					acc_config_inter_frame_idle_state_set(handle->config, idle_state);
					break;
				}
				case RADAR_PARAM_BURST_PERIOD_US:
				{
					// Note that an update rate of '0' means that the sensor will only be limited by
					// the rate that the host acknowledge and reads out the measurement data.
					float update_rate = (value == 0) ? 0.0f : 1.0e6f / (float)value;
					acc_config_frame_rate_set(handle->config, update_rate);
					break;
				}
				default:
				{
					rc = RC_BAD_INPUT;
					break;
				}
			}
		}
		else if (param.group == RADAR_PARAM_GROUP_PULSED)
		{
			switch (param.id)
			{
				case PULSED_PARAM_SWEEP_PERIOD_US:
				{
					// Note that a sweep rate of '0' means that the sensor will produce
					// sweeps as fast as possible.
					float sweep_rate = (value == 0) ? 0.0f : 1.0e6f / (float)value;
					acc_config_sweep_rate_set(handle->config, sweep_rate);
					break;
				}
				case PULSED_PARAM_SWEEPS_PER_BURST:
				{
					acc_config_sweeps_per_frame_set(handle->config, value);
					break;
				}
				case PULSED_PARAM_SAMPLES_PER_SWEEP:
				{
					acc_config_num_points_set(handle->config, value);
					break;
				}
				case PULSED_PARAM_INTERSWEEP_POWER_MODE:
				{
					acc_config_idle_state_t idle_state = to_idle_state(value);
					acc_config_inter_sweep_idle_state_set(handle->config, idle_state);
					break;
				}
				case PULSED_PARAM_START_OFFSET:
				{
					// Note that negative start points will not behave as expected
					// due to implicit conversion here
					acc_config_start_point_set(handle->config, value);
					break;
				}
				case PULSED_PARAM_PRF_IDX:
				{
					acc_config_prf_t prf = to_prf(value);
					acc_config_prf_set(handle->config, prf);
					break;
				}
				default:
				{
					rc = RC_BAD_INPUT;
					break;
				}
			}
		}
		else
		{
			rc = RC_BAD_INPUT;
		}
	}

	return rc;
}


RadarReturnCode radarGetMainParamRange(RadarHandle *handle, RadarMainParam param, uint32_t *min_value, uint32_t *max_value)
{
	RadarReturnCode rc = (handle != NULL && min_value != NULL && max_value != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = get_param_range(main_param_range, num_main_params, param.group, param.id, min_value, max_value) ? RC_OK : RC_BAD_INPUT;
	}

	return rc;
}


RadarReturnCode radarGetTxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarTxParam param, uint32_t *value)
{
	(void)handle;
	(void)slot_id;
	(void)antenna_mask;
	(void)param;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarSetTxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarTxParam param, uint32_t value)
{
	(void)handle;
	(void)slot_id;
	(void)antenna_mask;
	(void)param;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetRxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarRxParam param, uint32_t *value)
{
	(void)slot_id;
	(void)antenna_mask;

	RadarReturnCode rc = (handle != NULL && value != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (param.group == RADAR_PARAM_GROUP_PULSED)
		{
			switch (param.id)
			{
				case PULSED_RX_PARAM_VGA_IDX:
				{
					*value = acc_config_receiver_gain_get(handle->config);
					break;
				}
				default:
				{
					rc = RC_BAD_INPUT;
					break;
				}
			}
		}
		else
		{
			rc = RC_BAD_INPUT;
		}
	}

	return rc;
}


RadarReturnCode radarSetRxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarRxParam param, uint32_t value)
{
	(void)slot_id;
	(void)antenna_mask;

	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = is_param_valid(rx_param_range, num_rx_params, param.group, param.id, value) ? RC_OK : RC_BAD_INPUT;
	}

	if (rc == RC_OK)
	{
		if (param.group == RADAR_PARAM_GROUP_PULSED)
		{
			switch (param.id)
			{
				case PULSED_RX_PARAM_VGA_IDX:
				{
					acc_config_receiver_gain_set(handle->config, value);
					break;
				}
				default:
				{
					rc = RC_BAD_INPUT;
					break;
				}
			}
		}
		else
		{
			rc = RC_BAD_INPUT;
		}
	}

	return rc;
}


RadarReturnCode radarGetTxParamRange(RadarHandle *handle, RadarTxParam id, uint32_t *min_value, uint32_t *max_value)
{
	(void)handle;
	(void)id;
	(void)min_value;
	(void)max_value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetRxParamRange(RadarHandle *handle, RadarRxParam param, uint32_t *min_value, uint32_t *max_value)
{
	RadarReturnCode rc = (handle != NULL && min_value != NULL && max_value != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = get_param_range(rx_param_range, num_rx_params, param.group, param.id, min_value, max_value) ? RC_OK : RC_BAD_INPUT;
	}

	return rc;
}


RadarReturnCode radarGetVendorParam(RadarHandle *handle, uint8_t slot_id, RadarVendorParam param, uint32_t *value)
{
	(void)slot_id;

	RadarReturnCode rc = (handle != NULL && value != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		switch (param)
		{
			case PULSED_PARAM_STEP_LENGTH:
			{
				*value = acc_config_step_length_get(handle->config);
				break;
			}
			case PULSED_PARAM_HWAAS:
			{
				*value = acc_config_hwaas_get(handle->config);
				break;
			}
			case PULSED_PARAM_PROFILE:
			{
				acc_config_profile_t profile = acc_config_profile_get(handle->config);
				*value = from_profile(profile);
				break;
			}
			case PULSED_PARAM_ENABLE_TX:
			{
				*value = acc_config_enable_tx_get(handle->config) ? 1U : 0U;
				break;
			}
			default:
				rc = RC_BAD_INPUT;
				break;
		}
	}

	return rc;
}


RadarReturnCode radarSetVendorParam(RadarHandle *handle, uint8_t slot_id, RadarVendorParam param, uint32_t value)
{
	(void)slot_id;

	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = is_param_valid(vendor_param_range, num_vendor_params, RADAR_PARAM_GROUP_PULSED, param, value) ? RC_OK : RC_BAD_INPUT;
	}

	if (rc == RC_OK)
	{
		switch (param)
		{
			case PULSED_PARAM_STEP_LENGTH:
			{
				acc_config_step_length_set(handle->config, value);
				break;
			}
			case PULSED_PARAM_HWAAS:
			{
				acc_config_hwaas_set(handle->config, value);
				break;
			}
			case PULSED_PARAM_PROFILE:
			{
				acc_config_profile_t profile = to_profile(value);
				acc_config_profile_set(handle->config, profile);
				break;
			}
			case PULSED_PARAM_ENABLE_TX:
			{
				acc_config_enable_tx_set(handle->config, value == 0U ? false : true);
				break;
			}
			default:
				rc = RC_BAD_INPUT;
				break;
		}
	}

	return rc;
}


RadarReturnCode radarGetVendorParamRange(RadarHandle *handle, RadarVendorParam id, uint32_t *min_value, uint32_t *max_value)
{
	RadarReturnCode rc = (handle != NULL && min_value != NULL && max_value != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		rc = get_param_range(vendor_param_range, num_vendor_params, RADAR_PARAM_GROUP_PULSED,
		                     id, min_value, max_value) ? RC_OK : RC_BAD_INPUT;
	}

	return rc;
}


RadarReturnCode radarGetVendorTxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarVendorTxParam id, uint32_t *value)
{
	(void)handle;
	(void)slot_id;
	(void)antenna_mask;
	(void)id;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarSetVendorTxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarVendorTxParam id, uint32_t value)
{
	(void)handle;
	(void)slot_id;
	(void)antenna_mask;
	(void)id;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetVendorTxParamRange(RadarHandle *handle, RadarVendorTxParam id, uint32_t *min_value, uint32_t *max_value)
{
	(void)handle;
	(void)id;
	(void)min_value;
	(void)max_value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetVendorRxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarVendorRxParam id, uint32_t *value)
{
	(void)handle;
	(void)slot_id;
	(void)antenna_mask;
	(void)id;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarSetVendorRxParam(RadarHandle *handle, uint8_t slot_id, uint32_t antenna_mask, RadarVendorRxParam id, uint32_t value)
{
	(void)handle;
	(void)slot_id;
	(void)antenna_mask;
	(void)id;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetVendorRxParamRange(RadarHandle *handle, RadarVendorRxParam id, uint32_t *min_value, uint32_t *max_value)
{
	(void)handle;
	(void)id;
	(void)min_value;
	(void)max_value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarStartDataStreaming(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->current_state != RSTATE_IDLE)
		{
			ACC_LOG_ERROR("%s only supported from state IDLE", __func__);
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		float frame_rate = acc_config_frame_rate_get(handle->config);
		if (frame_rate == 0.0f)
		{
			// Set the timeout to a fixed 2s if no frame rate is requested
			handle->sensor_timeout_ms = 2000;
		}
		else
		{
			// Set timeout to four periods
			handle->sensor_timeout_ms = (uint32_t)(1.0e6f / frame_rate) * 4;
		}
	}

	if (rc == RC_OK)
	{
		handle->current_state           = RSTATE_ACTIVE;
		sensor_thread_data.radar_handle = handle;
		sensor_thread_data.stop_run     = false;
		sensor_thread_data.radar_status = RC_OK;

		if (sem_init(&sensor_thread_data.meas_sem, 0, 0))
		{
			ACC_LOG_ERROR("Failed to create measurement semaphore");
			rc = RC_RES_LIMIT;
		}
	}

	if (rc == RC_OK)
	{
		if (sem_init(&sensor_thread_data.read_sem, 0, 0))
		{
			ACC_LOG_ERROR("Failed to create read semaphore");
			rc = RC_RES_LIMIT;
		}
	}

	if (rc == RC_OK)
	{
		if (pthread_create(&sensor_thread_handle, NULL, sensor_thread, (void *)&sensor_thread_data) != 0)
		{
			ACC_LOG_ERROR("Failed to create sensor thread");
			rc = RC_RES_LIMIT;
		}
	}

	return rc;
}


RadarReturnCode radarStopDataStreaming(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->current_state != RSTATE_ACTIVE)
		{
			ACC_LOG_ERROR("%s only supported from state ACTIVE", __func__);
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		sensor_thread_data.stop_run = true;
		sem_post(&sensor_thread_data.meas_sem);
		sem_post(&sensor_thread_data.read_sem);
		pthread_join(sensor_thread_handle, NULL);
		sem_destroy(&sensor_thread_data.meas_sem);
		sem_destroy(&sensor_thread_data.read_sem);
		handle->current_state = RSTATE_IDLE;
	}

	return rc;
}


RadarReturnCode radarIsBurstReady(RadarHandle *handle, bool *is_ready)
{
	RadarReturnCode rc = (handle != NULL && is_ready != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		*is_ready = handle->is_burst_ready;
	}

	return rc;
}


RadarReturnCode radarReadBurst(RadarHandle *handle, RadarBurstFormat *format, uint8_t *buffer, uint32_t *read_bytes, struct timespec timeout)
{
	RadarReturnCode rc = (handle != NULL && format != NULL && buffer != NULL && read_bytes != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		if (handle->current_state != RSTATE_ACTIVE)
		{
			ACC_LOG_ERROR("%s only supported from state ACTIVE", __func__);
			rc = RC_BAD_STATE;
		}
	}

	if (rc == RC_OK)
	{
		struct timeval  tv;
		struct timespec ts;

		if (gettimeofday(&tv, NULL) == 0)
		{
			ts.tv_sec = tv.tv_sec + timeout.tv_sec;
			if (timeout.tv_nsec == 0)
			{
				// Avoid division by zero
				timeout.tv_nsec = 1;
			}

			// ts.tv_nsec is in usec until multiplication below
			ts.tv_nsec = tv.tv_usec + (timeout.tv_nsec / 1000);

			while (ts.tv_nsec >= 1000000)
			{
				ts.tv_sec++;
				ts.tv_nsec -= 1000000;
			}
			ts.tv_nsec *= 1000;

			if (sem_timedwait(&sensor_thread_data.meas_sem, &ts) == -1)
			{
				rc = RC_TIMEOUT;
			}

			if (rc == RC_OK)
			{
				rc = sensor_thread_data.radar_status;
			}
		}
		else
		{
			rc = RC_ERROR;
		}
	}

	if (rc == RC_OK)
	{
		size_t frame_data_length_bytes = handle->proc_meta.frame_data_length * sizeof(*handle->proc_result.frame);
		if (frame_data_length_bytes < *read_bytes)
		{
			*read_bytes = frame_data_length_bytes;
		}

		memcpy(buffer, handle->proc_result.frame, *read_bytes);

		sem_post(&sensor_thread_data.read_sem);

		format->sequence_number         = handle->sequence_number++;
		format->radar_type              = RTYPE_PULSED;
		format->config_id               = 1U;
		format->sample_data_type        = RSAMPLE_DTYPE_CFLOAT;
		format->bits_per_sample         = 32;
		format->num_channels            = 1U;
		format->is_channels_interleaved = 0U;
		format->is_big_endian           = 1U;

		format->custom.pusled.samples_per_sweep = acc_config_num_points_get(handle->config);
		format->custom.pusled.sweeps_per_burst  = acc_config_sweeps_per_frame_get(handle->config);
	}

	return rc;
}


RadarReturnCode radarSetBurstReadyCb(RadarHandle *handle, RadarBurstReadyCB cb, void *user_data)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		handle->callbacks.burst_ready_callback      = cb;
		handle->callbacks.burst_ready_callback_data = user_data;
	}

	return rc;
}


RadarReturnCode radarSetLogCb(RadarHandle *handle, RadarLogCB cb, void *user_data)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		handle->callbacks.log_callback      = cb;
		handle->callbacks.log_callback_data = user_data;
	}

	return rc;
}


RadarReturnCode radarSetRegisterSetCb(RadarHandle *handle, RadarRegisterSetCB cb, void *user_data)
{
	(void)handle;
	(void)cb;
	(void)user_data;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarCheckCountryCode(RadarHandle *handle, const char *country_code)
{
	(void)handle;
	(void)country_code;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetSensorInfo(RadarHandle *handle, SensorInfo *info)
{
	RadarReturnCode rc = (handle != NULL && info != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		*info = sensor_info;
	}

	return rc;
}


Version radarGetRadarApiVersion(void)
{
	return api_version;
}


RadarReturnCode radarLogSensorDetails(RadarHandle *handle)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		acc_config_log(handle->config);
	}

	return rc;
}


RadarReturnCode radarGetTxPosition(RadarHandle *handle, uint32_t tx_mask, int32_t *x, int32_t *y, int32_t *z)
{
	(void)handle;
	(void)tx_mask;
	(void)x;
	(void)y;
	(void)z;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetRxPosition(RadarHandle *handle, uint32_t rx_mask, int32_t *x, int32_t *y, int32_t *z)
{
	(void)handle;
	(void)rx_mask;
	(void)x;
	(void)y;
	(void)z;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarSetLogLevel(RadarHandle *handle, RadarLogLevel level)
{
	RadarReturnCode rc = (handle != NULL) ? RC_OK : RC_BAD_INPUT;

	if (rc == RC_OK)
	{
		handle->radar_log_level = level;
	}

	return rc;
}


RadarReturnCode radarGetAllRegisters(RadarHandle *handle, uint32_t *addresses, uint32_t *values, uint32_t *count)
{
	(void)handle;
	(void)addresses;
	(void)values;
	(void)count;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarGetRegister(RadarHandle *handle, uint32_t address, uint32_t *value)
{
	(void)handle;
	(void)address;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


RadarReturnCode radarSetRegister(RadarHandle *handle, uint32_t address, uint32_t value)
{
	(void)handle;
	(void)address;
	(void)value;

	print_api_usage(handle, __func__);

	return RC_UNSUPPORTED;
}


//-----------------------------
// Private definitions
//-----------------------------


static void *sensor_thread(void *param)
{
	sensor_thread_data_t *thread_data = (sensor_thread_data_t *)param;
	RadarHandle          *handle      = thread_data->radar_handle;
	RadarReturnCode      rc           = (handle != NULL) ? RC_OK : RC_ERROR;

	if (rc != RC_OK)
	{
		return NULL;
	}

	rc = acc_sensor_measure(handle->sensor) ? RC_OK : RC_ERROR;

	while (true)
	{
		if (rc == RC_OK)
		{
			rc = acc_hal_integration_wait_for_sensor_interrupt(handle->sensor_id, handle->sensor_timeout_ms) ? RC_OK : RC_TIMEOUT;
		}

		if (rc == RC_OK)
		{
			rc = acc_sensor_read(handle->sensor, handle->buffer, handle->buffer_size) ? RC_OK : RC_ERROR;
		}

		if (rc == RC_OK)
		{
			acc_processing_execute(handle->processing, handle->buffer, &handle->proc_result);
		}

		if (rc == RC_OK)
		{
			rc = acc_sensor_measure(handle->sensor) ? RC_OK : RC_ERROR;
		}

		if (rc == RC_OK && handle->callbacks.burst_ready_callback != NULL)
		{
			handle->callbacks.burst_ready_callback(handle->callbacks.burst_ready_callback_data);
		}

		if (rc == RC_OK)
		{
			handle->is_burst_ready = true;
			sem_post(&thread_data->meas_sem);
			sem_wait(&thread_data->read_sem);
			handle->is_burst_ready = false;
		}

		if (rc != RC_OK)
		{
			thread_data->radar_status = rc;
			sem_post(&thread_data->meas_sem);
			break;
		}

		if (thread_data->stop_run)
		{
			break;
		}
	}

	return NULL;
}


static void radar_handle_cleanup(RadarHandle *radar_handle)
{
	if (radar_handle != NULL)
	{
		if (radar_handle->config != NULL)
		{
			acc_config_destroy(radar_handle->config);
		}

		if (radar_handle->sensor != NULL)
		{
			acc_sensor_destroy(radar_handle->sensor);
		}

		if (radar_handle->processing != NULL)
		{
			acc_processing_destroy(radar_handle->processing);
		}

		acc_integration_mem_free(radar_handle);
	}
}


static acc_config_idle_state_t to_idle_state(uint32_t value)
{
	// Note that 0 means the deepest state where as much of the sensor hardware as
	// possible can be shut down
	acc_config_idle_state_t idle_state = ACC_CONFIG_IDLE_STATE_READY;

	if (value == 0)
	{
		idle_state = ACC_CONFIG_IDLE_STATE_DEEP_SLEEP;
	}
	else if (value == 1)
	{
		idle_state = ACC_CONFIG_IDLE_STATE_SLEEP;
	}

	return idle_state;
}


static uint32_t from_idle_state(acc_config_idle_state_t idle_state)
{
	uint32_t res;

	switch (idle_state)
	{
		case ACC_CONFIG_IDLE_STATE_DEEP_SLEEP:
			res = 0;
			break;
		case ACC_CONFIG_IDLE_STATE_SLEEP:
			res = 1;
			break;
		case ACC_CONFIG_IDLE_STATE_READY:
			res = 2;
			break;
		default:
			res = 0;
			break;
	}

	return res;
}


static acc_config_profile_t to_profile(uint32_t value)
{
	acc_config_profile_t profile = ACC_CONFIG_PROFILE_3;

	if (value == ACC_RADAR_PROFILE_1)
	{
		profile = ACC_CONFIG_PROFILE_1;
	}
	else if (value == ACC_RADAR_PROFILE_2)
	{
		profile = ACC_CONFIG_PROFILE_2;
	}
	else if (value == ACC_RADAR_PROFILE_4)
	{
		profile = ACC_CONFIG_PROFILE_4;
	}
	else if (value == ACC_RADAR_PROFILE_5)
	{
		profile = ACC_CONFIG_PROFILE_5;
	}

	return profile;
}


static uint32_t from_profile(acc_config_profile_t profile)
{
	uint32_t res;

	switch (profile)
	{
		case ACC_CONFIG_PROFILE_1:
			res = ACC_RADAR_PROFILE_1;
			break;
		case ACC_CONFIG_PROFILE_2:
			res = ACC_RADAR_PROFILE_2;
			break;
		case ACC_CONFIG_PROFILE_4:
			res = ACC_RADAR_PROFILE_4;
			break;
		case ACC_CONFIG_PROFILE_5:
			res = ACC_RADAR_PROFILE_5;
			break;
		case ACC_CONFIG_PROFILE_3:
		default:
			res = ACC_RADAR_PROFILE_3;
			break;
	}

	return res;
}


static acc_config_prf_t to_prf(uint32_t value)
{
	acc_config_prf_t prf;

	if (value == ACC_RADAR_PRF_19_5_MHZ)
	{
		prf = ACC_CONFIG_PRF_19_5_MHZ;
	}
	else if (value == ACC_RADAR_PRF_15_6_MHZ)
	{
		prf = ACC_CONFIG_PRF_15_6_MHZ;
	}
	else if (value == ACC_RADAR_PRF_13_0_MHZ)
	{
		prf = ACC_CONFIG_PRF_13_0_MHZ;
	}
	else if (value == ACC_RADAR_PRF_8_7_MHZ)
	{
		prf = ACC_CONFIG_PRF_8_7_MHZ;
	}
	else if (value == ACC_RADAR_PRF_6_5_MHZ)
	{
		prf = ACC_CONFIG_PRF_6_5_MHZ;
	}
	else if (value == ACC_RADAR_PRF_5_2_MHZ)
	{
		prf = ACC_CONFIG_PRF_5_2_MHZ;
	}
	else
	{
		prf = ACC_CONFIG_PRF_15_6_MHZ;
	}

	return prf;
}


static uint32_t from_prf(acc_config_prf_t prf)
{
	uint32_t res;

	switch (prf)
	{
		case ACC_CONFIG_PRF_19_5_MHZ:
			res = ACC_RADAR_PRF_19_5_MHZ;
			break;
		case ACC_CONFIG_PRF_13_0_MHZ:
			res = ACC_RADAR_PRF_13_0_MHZ;
			break;
		case ACC_CONFIG_PRF_8_7_MHZ:
			res = ACC_RADAR_PRF_8_7_MHZ;
			break;
		case ACC_CONFIG_PRF_6_5_MHZ:
			res = ACC_RADAR_PRF_6_5_MHZ;
			break;
		case ACC_CONFIG_PRF_5_2_MHZ:
			res = ACC_RADAR_PRF_5_2_MHZ;
			break;
		case ACC_CONFIG_PRF_15_6_MHZ:
		default:
			res = ACC_RADAR_PRF_15_6_MHZ;
			break;
	}

	return res;
}


static bool get_param_range(const radar_param_range_t *param_range, uint16_t nbr_params, uint32_t param_group, uint32_t param_id,
                            uint32_t *min_value, uint32_t *max_value)
{
	bool result = false;

	for (uint16_t i = 0; i < nbr_params; i++)
	{
		if (param_range[i].group == param_group && param_range[i].id == param_id)
		{
			*min_value = param_range[i].min_value;
			*max_value = param_range[i].max_value;
			result     = true;

			break;
		}
	}

	return result;
}


static bool is_param_valid(const radar_param_range_t *param_range, uint16_t nbr_params, uint32_t param_group, uint32_t param_id, uint32_t value)
{
	uint32_t min_value;
	uint32_t max_value;

	bool result = get_param_range(param_range, nbr_params, param_group, param_id, &min_value, &max_value);

	if (result)
	{
		if (value < min_value || value > max_value)
		{
			result = false;
		}
	}

	return result;
}


static void print_api_usage(RadarHandle *handle, const char *function)
{
	(void)handle;

	ACC_LOG_ERROR("%s is not currently implemented", function);
	ACC_LOG_ERROR("The program flow supported is the following:");
	ACC_LOG_ERROR("Initialization:");
	ACC_LOG_ERROR("  radarInit");
	ACC_LOG_ERROR("  radarCreate             - Sensor calibration will be done as part of this function");
	ACC_LOG_ERROR("  radarSetLogLevel");
	ACC_LOG_ERROR("  radarSetLogCb");
	ACC_LOG_ERROR("  radarSetBurstReadyCb");
	ACC_LOG_ERROR("  radarSetMainParam");
	ACC_LOG_ERROR("  radarSetTxParam");
	ACC_LOG_ERROR("  radarSetRxParam");
	ACC_LOG_ERROR("  radarSetVendorParam");
	ACC_LOG_ERROR("  radarActivateConfig");
	ACC_LOG_ERROR("  radarLogSensorDetails");
	ACC_LOG_ERROR(" ");
	ACC_LOG_ERROR("Radar control");
	ACC_LOG_ERROR("  radarTurnOn             - Sensor will be enabled and ready to start streaming data");
	ACC_LOG_ERROR("  radarStartDataStreaming - Will start measuring at the requested burst rate");
	ACC_LOG_ERROR("  on RadarBurstReadyCB    - Indicates that a new burst is ready");
	ACC_LOG_ERROR("  radarReadBurst          - Read burst");
	ACC_LOG_ERROR("  radarStopDataStreaming  - Will wait for any pending measurements to complete");
	ACC_LOG_ERROR("  radarTurnOff            - Sensor will be disabled");
	ACC_LOG_ERROR(" ");
	ACC_LOG_ERROR("Deinitialization:");
	ACC_LOG_ERROR("  radarDeactivateConfig");
	ACC_LOG_ERROR("  radarDestroy");
	ACC_LOG_ERROR("  radarDeinit");
	ACC_LOG_ERROR(" ");
	ACC_LOG_ERROR("Sleep mode:");
	ACC_LOG_ERROR("  radarGoSleep            - This will make sensor enter hibernation");
	ACC_LOG_ERROR("  radarWakeUp             - This will make sensor exit hibernation");
	ACC_LOG_ERROR("Information:");
	ACC_LOG_ERROR("  radarGetState");
	ACC_LOG_ERROR("  radarGetNumConfigSlots");
	ACC_LOG_ERROR("  radarGetMaxActiveConfigSlots");
	ACC_LOG_ERROR("  radarGetMainParam");
	ACC_LOG_ERROR("  radarGetMainParamRange");
	ACC_LOG_ERROR("  radarGetRxParam");
	ACC_LOG_ERROR("  radarGetRxParamRange");
	ACC_LOG_ERROR("  radarGetVendorParam");
	ACC_LOG_ERROR("  radarGetVendorParamRange");
	ACC_LOG_ERROR("  radarIsBurstReady");
	ACC_LOG_ERROR("  radarGetSensorInfo");
	ACC_LOG_ERROR("  radarGetRadarApiVersion");
}


void acc_integration_log(acc_log_level_t level, const char *module, const char *format, ...)
{
	char    log_buffer[LOG_BUFFER_MAX_SIZE];
	va_list ap;

	if (log_radar_handle != NULL && log_radar_handle->callbacks.log_callback != NULL && log_radar_handle->radar_log_level > RLOG_OFF)
	{
		va_start(ap, format);

		int ret = vsnprintf(log_buffer, LOG_BUFFER_MAX_SIZE, format, ap);

		if (ret >= LOG_BUFFER_MAX_SIZE)
		{
			log_buffer[LOG_BUFFER_MAX_SIZE - 4] = '.';
			log_buffer[LOG_BUFFER_MAX_SIZE - 3] = '.';
			log_buffer[LOG_BUFFER_MAX_SIZE - 2] = '.';
			log_buffer[LOG_BUFFER_MAX_SIZE - 1] = 0;
		}

		RadarLogLevel radar_log_level = ACC_LOG_LEVEL_ERROR;

		if (level == ACC_LOG_LEVEL_ERROR)
		{
			radar_log_level = RLOG_ERR;
		}
		else if (level == ACC_LOG_LEVEL_WARNING)
		{
			radar_log_level = RLOG_WRN;
		}
		else if (level == ACC_LOG_LEVEL_INFO || level == ACC_LOG_LEVEL_VERBOSE)
		{
			radar_log_level = RLOG_INF;
		}
		else if (level == ACC_LOG_LEVEL_DEBUG)
		{
			radar_log_level = RLOG_DBG;
		}

		if (log_radar_handle->radar_log_level >= radar_log_level)
		{
			log_radar_handle->callbacks.log_callback(radar_log_level, module, "", 0,
			                                         log_radar_handle->callbacks.log_callback_data, log_buffer);
		}

		va_end(ap);
	}
}
