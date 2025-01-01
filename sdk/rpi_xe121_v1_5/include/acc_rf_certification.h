// Copyright (c) Acconeer AB, 2022-2023
// All rights reserved

#ifndef ACC_RF_CERTIFICATION_H_
#define ACC_RF_CERTIFICATION_H_

#include <stdbool.h>
#include <stdint.h>

/**
 * @brief Execute RF certification test
 *
 * @param[in] argc Argument count
 * @param[in] argv Argument vector
 * @return true if executed successfully, otherwise false
 */
bool acc_rf_certification_args(int argc, char *argv[]);


/**
 * @brief Stops the testing (only applicable for a linux host)
 */
void acc_rf_certification_stop_set(void);


/**
 * @brief Execute RF certification TX emission test
 *
 * @param[in] iterations The number of iterations, set to 0 to run infinite number of iterations
 * @return true if executed successfully, otherwise false
 */
bool acc_rf_certification_tx_emission(uint32_t iterations);


/**
 * @brief Execute RF certification RX spurious emission test
 *
 * @param[in] iterations The number of iterations, set to 0 to run infinite number of iterations
 * @return true if executed successfully, otherwise false
 */
bool acc_rf_certification_rx_spurious_emission(uint32_t iterations);


/**
 * @brief Execute RF certification RX interference performance test
 *
 * @param[in] iterations The number of iterations, set to 0 to run infinite number of iterations
 * @return true if executed successfully, otherwise false
 */
bool acc_rf_certification_rx_interference_performance(uint32_t iterations);


#endif
