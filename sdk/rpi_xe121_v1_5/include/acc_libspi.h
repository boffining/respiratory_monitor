// Copyright (c) Acconeer AB, 2021
// All rights reserved

#ifndef ACC_LIBSPI_H_
#define ACC_LIBSPI_H_
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


#define MAX_SPI_TRANSFER_SIZE 4095


/**
 * Initialize the SPI library.
 *
 * @return true if successful
 */
bool acc_libspi_init(void);


/**
 * Deinitialize the SPI library and free any allocated resources.
 */
void acc_libspi_deinit(void);


/**
 * Transfer data over the SPI interface
 *
 * @param[in] speed The speed in Hz of the SPI clock
 * @param[in,out] buffer The data to send and receive
 * @param[in] buffer_size The size of the data to be sent in bytes
 */
bool acc_libspi_transfer(uint32_t speed, uint8_t *buffer, size_t buffer_size);

#endif
