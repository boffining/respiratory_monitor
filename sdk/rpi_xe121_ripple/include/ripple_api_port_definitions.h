// Copyright (c) Acconeer AB, 2022-2023
// All rights reserved

#ifndef RIPPLE_API_PORT_DEFINITIONS_H_
#define RIPPLE_API_PORT_DEFINITIONS_H_

typedef enum RadarVendorParamImpl
{
	PULSED_PARAM_STEP_LENGTH = 0,
	PULSED_PARAM_HWAAS       = 1,
	PULSED_PARAM_PROFILE     = 2,
	PULSED_PARAM_ENABLE_TX   = 3
} AccRadarVendorParam;

typedef enum
{
	ACC_RADAR_PROFILE_1 = 1,
	ACC_RADAR_PROFILE_2 = 2,
	ACC_RADAR_PROFILE_3 = 3,
	ACC_RADAR_PROFILE_4 = 4,
	ACC_RADAR_PROFILE_5 = 5,
} AccRadarVendorParamProfile_t;

typedef enum
{
	ACC_RADAR_PRF_19_5_MHZ = 0,
	ACC_RADAR_PRF_15_6_MHZ = 1,
	ACC_RADAR_PRF_13_0_MHZ = 2,
	ACC_RADAR_PRF_8_7_MHZ  = 3,
	ACC_RADAR_PRF_6_5_MHZ  = 4,
	ACC_RADAR_PRF_5_2_MHZ  = 5,
} AccRadarVendorParamPRF_t;

#endif
