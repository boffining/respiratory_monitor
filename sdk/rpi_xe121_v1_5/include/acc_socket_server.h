// Copyright (c) Acconeer AB, 2023
// All rights reserved

#ifndef ACC_SOCKET_SERVER_H_
#define ACC_SOCKET_SERVER_H_

#include <poll.h>
#include <stdbool.h>
#include <stddef.h>

/**
 * @brief Function pointer type for the input_data_function
 *
 * @param[in] data The data to be written
 * @param[in] size The size of the data in bytes
 */
typedef void (input_data_function_t)(const void *data, size_t size);

/**
 * @brief The socket server instance
 */
typedef struct
{
	int                   server_socket;
	int                   client_socket;
	struct pollfd         poll_set[1];
	input_data_function_t *input_data_func;
	void                  *buffer;
	size_t                buffer_size;
} acc_socket_server_t;

/**
 * @brief Open a socket server on a specified tcp port
 *
 * @param[in, out] socket_server The socket server instance
 * @param[in] server_port The TCP/IP port number
 * @param[in] buffer_size The wanted buffer size
 *
 * @return true if no error occurred
 */
bool acc_socket_server_open(acc_socket_server_t *socket_server, int server_port, size_t buffer_size);


/**
 * @brief Close a socket server
 *
 * @param[in] socket_server The socket server instance
 */
void acc_socket_server_close(acc_socket_server_t *socket_server);


/**
 * @brief Wait for a client to connect, blocking function
 *
 * @param[in] socket_server The socket server instance
 *
 * @return true if no error occurred
 */
bool acc_socket_server_wait_for_client(acc_socket_server_t *socket_server);


/**
 * @brief Close the client socket
 *
 * @param[in] socket_server The socket server instance
 */
void acc_socket_server_client_close(acc_socket_server_t *socket_server);


/**
 * @brief Wait for a socket event, return after a timeout
 *
 * This function will call the 'input_data_function' with the from the socket read data
 *
 * @param[in] socket_server The socket server instance
 * @param[in] blocking The call will block until a socket event occurs
 * @param[in] timeout_us The timeout for when the function should return
 *
 * @return true if no error occurred
 */
bool acc_socket_server_poll_events(acc_socket_server_t *socket_server, bool blocking, size_t timeout_us);


/**
 * @brief Setup data handler function
 *
 * @param[in] socket_server The socket server instance
 * @param[in] input_data_func The function to be called when data arrives on the socket
 *
 * @return true if no error occurred
 */
void acc_socket_server_set_input_data_func(acc_socket_server_t *socket_server, input_data_function_t *input_data_func);


/**
 * @brief Write data to the socket
 *
 * @param[in] socket_server The socket server instance
 * @param[in] data The data to be written
 * @param[in] size The size of the data in bytes
 */
void acc_socket_server_setup_write_data(acc_socket_server_t *socket_server, const void *data, size_t size);


#endif
