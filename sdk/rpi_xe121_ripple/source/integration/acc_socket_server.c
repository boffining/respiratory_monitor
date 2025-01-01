// Copyright (c) Acconeer AB, 2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "acc_socket_server.h"

#define US_TICKS_PER_SECOND (1000000)
#define NS_PER_TICKS        (1000)


bool acc_socket_server_open(acc_socket_server_t *socket_server, int server_port, size_t buffer_size)
{
	int                s;
	struct sockaddr_in addr;

	socket_server->buffer_size = buffer_size;
	socket_server->buffer      = malloc(buffer_size);

	if (socket_server->buffer == NULL)
	{
		fprintf(stderr, "ERROR: Memory allocation error\n");
		return false;
	}

	if ((s = socket(AF_INET, SOCK_STREAM, 0)) < 0)
	{
		fprintf(stderr, "ERROR: socket(AF_INET, SOCK_STREAM, 0): (%u) %s\n", errno, strerror(errno));
		free(socket_server->buffer);
		socket_server->buffer = NULL;
		return false;
	}

	if (setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &(int){1 }, sizeof(int)) < 0)
	{
		fprintf(stderr, "ERROR: setsockopt(SO_REUSEADDR): (%u) %s\n", errno, strerror(errno));
	}

	memset(&addr, 0, sizeof(addr));
	addr.sin_family      = AF_INET;
	addr.sin_addr.s_addr = INADDR_ANY;
	addr.sin_port        = htons(server_port);

	if (bind(s, (struct sockaddr *)&addr, sizeof(addr)) < 0)
	{
		fprintf(stderr, "ERROR: bind(): (%u) %s\n", errno, strerror(errno));
		close(s);
		free(socket_server->buffer);
		socket_server->buffer = NULL;
		return false;
	}

	if (listen(s, 10) < 0)
	{
		fprintf(stderr, "ERROR: listen(): (%u) %s\n", errno, strerror(errno));
		close(s);
		free(socket_server->buffer);
		socket_server->buffer = NULL;
		return false;
	}

	socket_server->server_socket = s;
	socket_server->client_socket = -1;

	return true;
}


void acc_socket_server_close(acc_socket_server_t *socket_server)
{
	if (socket_server->client_socket > 0)
	{
		close(socket_server->client_socket);
	}

	close(socket_server->server_socket);
	free(socket_server->buffer);
}


bool acc_socket_server_wait_for_client(acc_socket_server_t *socket_server)
{
	/* Blocking wait for accept */
	socket_server->client_socket = accept(socket_server->server_socket, NULL, NULL);

	if (socket_server->client_socket < 0)
	{
		return false;
	}

	if (setsockopt(socket_server->client_socket, SOL_SOCKET, SO_KEEPALIVE, &(int){1 }, sizeof(int)) < 0)
	{
		fprintf(stderr, "ERROR:setsockopt(SO_KEEPALIVE): (%u) %s\n", errno, strerror(errno));
	}

	if (setsockopt(socket_server->client_socket, IPPROTO_TCP, TCP_NODELAY, &(int){1 }, sizeof(int)) < 0)
	{
		fprintf(stderr, "ERROR:setsockopt(TCP_NODELAY): (%u) %s\n", errno, strerror(errno));
	}

	if (setsockopt(socket_server->client_socket, SOL_SOCKET, SO_SNDBUF, &(int){200000 }, sizeof(int)) < 0)
	{
		fprintf(stderr, "ERROR:setsockopt(SO_SNDBUF): (%u) %s\n", errno, strerror(errno));
	}

	socket_server->poll_set[0].fd     = socket_server->client_socket;
	socket_server->poll_set[0].events = POLLIN;

	return true;
}


void acc_socket_server_client_close(acc_socket_server_t *socket_server)
{
	/* Close client socket if there was any */
	if (socket_server->client_socket > 0)
	{
		close(socket_server->client_socket);
		socket_server->client_socket = -1;
	}
}


bool acc_socket_server_poll_events(acc_socket_server_t *socket_server, bool blocking, size_t timeout_us)
{
	bool success = true;

	struct timespec poll_wait      = { 0 };
	struct timespec *poll_wait_ptr = &poll_wait;

	if (blocking)
	{
		poll_wait_ptr = NULL;
	}
	else
	{
		poll_wait.tv_sec  = timeout_us / US_TICKS_PER_SECOND;
		poll_wait.tv_nsec = (timeout_us % US_TICKS_PER_SECOND) * NS_PER_TICKS;
	}

	if (socket_server->client_socket > 0)
	{
		/* Wait for poll_wait time or until a socket event occurs */
		int nof_events = ppoll(socket_server->poll_set, 1, poll_wait_ptr, NULL);

		if (nof_events > 0)
		{
			short returned_event = socket_server->poll_set[0].revents;
			if (returned_event & POLLERR)
			{
				/* Socket error, break */
				success = false;
			}
			else if (returned_event & POLLIN)
			{
				int len = read(socket_server->client_socket, socket_server->buffer, socket_server->buffer_size);
				if (len >= 1)
				{
					/* Put data from socket */
					if (socket_server->input_data_func != NULL)
					{
						socket_server->input_data_func(socket_server->buffer, len);
					}
				}
				else if (len == 0)
				{
					/* Client socket disconnected */
					success = false;
				}
				else
				{
					/* Interrupted by signal */
					success = false;
				}
			}
		}
		else
		{
			/* POLL TIMEOUT or POLL ERROR, just continue */
		}
	}
	else
	{
		/* Client socket has been closed */
		success = false;
	}

	return success;
}


void acc_socket_server_set_input_data_func(acc_socket_server_t *socket_server, input_data_function_t *input_data_func)
{
	socket_server->input_data_func = input_data_func;
}


void acc_socket_server_setup_write_data(acc_socket_server_t *socket_server, const void *data, size_t size)
{
	if (socket_server->client_socket > 0)
	{
		bool result = write(socket_server->client_socket, data, size) == (ssize_t)size;

		if (!result)
		{
			fprintf(stderr, "ERROR: socket(AF_INET, SOCK_STREAM, 0): (%u) %s\n", errno, strerror(errno));
			close(socket_server->client_socket);
			socket_server->client_socket = -1;
		}
	}
}
