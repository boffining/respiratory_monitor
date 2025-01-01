// Copyright (c) Acconeer AB, 2024
// All rights reserved

#ifndef ACC_TIME_H_
#define ACC_TIME_H_

#include <stdint.h>


/**
 * @brief Get current time
 *
 * Uses all bits before wrapping, i.e.: it counts
 * upwards to 2^32 - 1 and then 0 again.
 *
 * @returns Current time as milliseconds
 */
uint32_t acc_time_get(void);


#endif
