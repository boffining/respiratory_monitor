// Copyright (c) Acconeer AB, 2016-2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.


#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "algorithm_basic_utils.h"

//-----------------------------
// Private declarations
//-----------------------------


//-----------------------------
// Public definitions
//-----------------------------


uint32_t algorithm_basic_util_crc32(const uint8_t *input, size_t len)
{
	const uint32_t divisor = 0xEDB88320U;
	uint32_t       crc     = 0xFFFFFFFFU;

	for (size_t i = 0; i < len; i++)
	{
		crc ^= (uint32_t)input[i];
		for (size_t k = 8U; k > 0U; k--)
		{
			if ((crc & 1U) != 0U)
			{
				crc = (crc >> 1U) ^ divisor;
			}
			else
			{
				crc = crc >> 1U;
			}
		}
	}

	return crc ^ 0xFFFFFFFFU;
}
