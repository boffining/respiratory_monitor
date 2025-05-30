// Copyright (c) Acconeer AB, 2022-2024
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

/** \example example_processing_noncoherent_mean.c
 * @brief example_processing_noncoherent_mean.c
 * Example program that shows how to calculate the non-coherent mean of the values in
 * an A121 sparse IQ frame with multiple sweeps.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "acc_config.h"
#include "acc_definitions_a121.h"
#include "acc_hal_definitions_a121.h"
#include "acc_hal_integration_a121.h"
#include "acc_integration_log.h"
#include "acc_rss_a121.h"
#include "acc_version.h"

#include "acc_processing_helpers.h"

#define SENSOR_ID (1U)

#define SWEEPS_PER_FRAME 16

static void update_configuration(acc_config_t *config);

int main(int argc, char *argv[]);

int main(int argc, char *argv[])
{
	(void)argc;
	(void)argv;

	acc_control_helper_t control_helper_state = {0};

	printf("Acconeer software version %s\n", acc_version_get());

	const acc_hal_a121_t *hal = acc_hal_rss_integration_get_implementation();

	if (!acc_rss_hal_register(hal))
	{
		return EXIT_FAILURE;
	}

	bool res = acc_control_helper_create(&control_helper_state, SENSOR_ID);

	if (!res)
	{
		printf("acc_control_helper_create() failed\n");
		return EXIT_FAILURE;
	}

	update_configuration(control_helper_state.config);

	res = acc_control_helper_activate(&control_helper_state);

	if (!res)
	{
		printf("acc_control_helper_activate() failed\n");
		acc_control_helper_destroy(&control_helper_state);
		return EXIT_FAILURE;
	}

	uint32_t sweep_data_length   = control_helper_state.proc_meta.sweep_data_length;
	uint32_t point_vector_length = SWEEPS_PER_FRAME;

	acc_vector_float_t *current_sweep_noncoherent_mean_amplitude = acc_vector_float_alloc(sweep_data_length);
	acc_vector_iq_t    *point_vector                             = acc_vector_iq_alloc(point_vector_length);

	bool mem_ok = (current_sweep_noncoherent_mean_amplitude != NULL) && (point_vector != NULL);
	if (!mem_ok)
	{
		printf("Memory allocation for vectors failed\n");
	}
	else
	{
		uint32_t iterations = 25U;
		for (uint32_t i = 0U; i < iterations; i++)
		{
			if (!acc_control_helper_get_next(&control_helper_state))
			{
				printf("acc_control_helper_get_next() failed\n");
				break;
			}

			// The acc_vector_iq_noncoherent_mean calculates the non-coherent mean by taking the mean value
			// of the complex vector elements and then return the absabsolute value of the mean
			// non-coherent mean = (z=0..n) mean(sqrt(real(z)^2 + imag(z)^2))

			for (uint32_t p = 0U; p < sweep_data_length; p++)
			{
				acc_get_iq_point_vector(&control_helper_state, p, point_vector);
				current_sweep_noncoherent_mean_amplitude->data[p] = acc_vector_iq_noncoherent_mean_amplitude(point_vector);
			}

			acc_vector_float_print("Non-coherent mean amplitude", current_sweep_noncoherent_mean_amplitude);

			uint32_t max_peak_index = acc_vector_float_argmax(current_sweep_noncoherent_mean_amplitude);
			printf("Highest peak index: %" PRIu32 ", peak ampliude %" PRIfloat "\n",
			       max_peak_index,
			       ACC_LOG_FLOAT_TO_INTEGER(current_sweep_noncoherent_mean_amplitude->data[max_peak_index]));
		}
	}

	acc_vector_iq_free(point_vector);
	acc_vector_float_free(current_sweep_noncoherent_mean_amplitude);
	acc_control_helper_destroy(&control_helper_state);

	printf("Application finished OK\n");

	return EXIT_SUCCESS;
}

static void update_configuration(acc_config_t *config)
{
	int32_t  start_point = 100; // start at 250 mm
	uint16_t step_length = 2;   // 2*2.5 mm = 5 mm
	uint16_t num_points  = 100; // range length 2*100*2.5 mm = 500 mm

	acc_config_start_point_set(config, start_point);
	acc_config_num_points_set(config, num_points);
	acc_config_step_length_set(config, step_length);
	acc_config_profile_set(config, ACC_CONFIG_PROFILE_2);
	acc_config_hwaas_set(config, 30);
	// The processing in this example assumes that sweeps_per_frame > 1
	acc_config_sweeps_per_frame_set(config, SWEEPS_PER_FRAME);
	acc_config_prf_set(config, ACC_CONFIG_PRF_13_0_MHZ);
}
