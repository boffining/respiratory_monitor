// Copyright (c) Acconeer AB, 2021-2024
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "acc_definitions_common.h"
#include "acc_exploration_server_base.h"
#include "acc_integration_log.h"
#include "acc_socket_server.h"
#include "acc_time.h"

#define LOG_BUFFER_MAX_SIZE 150
#define LOG_FORMAT          "%02u:%02u:%02u.%03u (%c) (%s) %s\n"

#define DEFAULT_TCP_IP_PORT       (6110)
#define US_TICKS_PER_SECOND       (1000000)
#define NS_PER_TICKS              (1000)
#define MAIN_THREAD_IDLE_SLEEP_US (200000)
#define MAX_COMMAND_SIZE          (10 * 1024)

static char   command_buffer[MAX_COMMAND_SIZE];
volatile bool exploration_server_shutdown = false;

acc_socket_server_t socket_server = {0};

/**
 * @brief Write data to socket
 *
 * @param[in] data pointer to data
 * @param[in] size data size in bytes
 *
 * @return true if successful
 */
static void write_data_func(const void *data, uint32_t size);

/**
 * @brief Get tick
 *
 * @return The current tick
 */
static uint32_t get_tick(void);

/**
 * @brief Check if shutdown should be initiated
 *
 * @return true if shutdown should be initiated
 */
static bool do_shutdown(void);

const exploration_server_interface_t server_if = {
    .write            = write_data_func,
    .restart_input    = NULL,
    .set_baudrate     = NULL,
    .max_baudrate     = 0,
    .get_tick         = get_tick,
    .ticks_per_second = US_TICKS_PER_SECOND, /* us ticks are used in this integration */
};

static void set_shutdown(bool shutdown)
{
	exploration_server_shutdown = shutdown;
}

static void cleanup(void)
{
	acc_exploration_server_deinit();
}

static void write_data_func(const void *data, uint32_t size)
{
	acc_socket_server_setup_write_data(&socket_server, data, size);
}

static void input_data_function(const void *data, size_t size)
{
	/* Put data from socket */
	acc_exploration_server_put_buffer_from_client(data, size);
}

static bool do_shutdown(void)
{
	return exploration_server_shutdown;
}

static uint32_t get_tick(void)
{
	struct timespec time_ts = {0};

	/* us ticks are used in this integration */
	clock_gettime(CLOCK_MONOTONIC, &time_ts);
	return (uint32_t)(time_ts.tv_sec * 1000000 + time_ts.tv_nsec / 1000);
}

static void main_sig_handler(int sig)
{
	printf("\nMain thread interrupted [%d]\n", sig);
	signal(sig, SIG_IGN);
	set_shutdown(true);
}

static void print_usage(char *application_name)
{
	fprintf(stderr, "Usage: %s [OPTION]...\n", application_name);
	fprintf(stderr, "\n");
	fprintf(stderr, "-h, --help                      this help\n");
	fprintf(stderr, "-l, --log-level                 the log level (debug/warning/info/verbose/error)\n");
	fprintf(stderr, "-p, --port                      the TCP/IP port to use\n");
}

int main(int argc, char *argv[])
{
	static struct option long_options[] = {
	    {"help", no_argument, 0, 'h'}, {"log-level", required_argument, 0, 'l'}, {"port", required_argument, 0, 'p'}, {NULL, 0, NULL, 0}};

	int character_code;
	int option_index = 0;

	acc_log_level_t log_level   = ACC_LOG_LEVEL_INFO;
	int             tcp_ip_port = DEFAULT_TCP_IP_PORT;

	while ((character_code = getopt_long(argc, argv, "h?l:p:", long_options, &option_index)) != -1)
	{
		switch (character_code)
		{
			case 'h':
			case '?':
			{
				print_usage(basename(argv[0]));
				return EXIT_FAILURE;
			}
			case 'l':
			{
				if (strcmp(optarg, "debug") == 0)
				{
					log_level = ACC_LOG_LEVEL_DEBUG;
				}
				else if (strcmp(optarg, "verbose") == 0)
				{
					log_level = ACC_LOG_LEVEL_VERBOSE;
				}
				else if (strcmp(optarg, "info") == 0)
				{
					log_level = ACC_LOG_LEVEL_INFO;
				}
				else if (strcmp(optarg, "warning") == 0)
				{
					log_level = ACC_LOG_LEVEL_WARNING;
				}
				else if (strcmp(optarg, "error") == 0)
				{
					log_level = ACC_LOG_LEVEL_ERROR;
				}
				else
				{
					fprintf(stderr, "ERROR: Unknown log-level '%s'\n", optarg);
					return EXIT_FAILURE;
				}

				break;
			}
			case 'p':
			{
				int value = atoi(optarg);
				if (value > 0)
				{
					tcp_ip_port = value;
					printf("Overriding tcp/ip port (%d)\n", tcp_ip_port);
				}
				else
				{
					fprintf(stderr, "ERROR: Invalid tcp/ip port '%s'\n", optarg);
					return EXIT_FAILURE;
				}
			}
			default:
				break;
		}
	}

	if (!acc_exploration_server_init(command_buffer, sizeof(command_buffer), "linux", log_level))
	{
		return EXIT_FAILURE;
	}

	/* setup signal handler */
	struct sigaction sa = {0};

	sa.sa_handler = main_sig_handler;
	if (sigaction(SIGINT, &sa, NULL) < 0)
	{
		fprintf(stderr, "ERROR: sigaction\n");
		cleanup();
		return EXIT_FAILURE;
	}

	/* Ignore broken pipe shutdown, default behavior is to close application */
	signal(SIGPIPE, SIG_IGN);

	printf("Starting server (port=%d)\n", tcp_ip_port);

	if (!acc_socket_server_open(&socket_server, tcp_ip_port, MAX_COMMAND_SIZE))
	{
		fprintf(stderr, "ERROR: Could not create socket server\n");
		cleanup();
		return EXIT_FAILURE;
	}

	acc_socket_server_set_input_data_func(&socket_server, input_data_function);

	while (!do_shutdown())
	{
		printf("Waiting for new connections...\n");
		fflush(stdout);

		/* Close client socket if there was any */
		acc_socket_server_client_close(&socket_server);

		/* Stop streaming if there was any */
		acc_exploration_server_stop_streaming();

		/* Blocking accept */
		if (!acc_socket_server_wait_for_client(&socket_server))
		{
			/* No valid accept, continue and try again... */
			continue;
		}

		printf("Got new connection.\n");
		printf("Listening for command...\n");

		while (!do_shutdown())
		{
			/* Default state is idle */
			acc_exploration_server_state_t state = ACC_EXPLORATION_SERVER_WAITING;

			/* Default wait time is zero */
			int32_t ticks_until_next = 0;
			bool    blocking_poll    = false;

			bool success = acc_exploration_server_process(&server_if, &state, &ticks_until_next);

			if (!success)
			{
				fprintf(stderr, "ERROR: acc_exploration_server_process (%u) %s\n", errno, strerror(errno));
				break;
			}

			switch (state)
			{
				case ACC_EXPLORATION_SERVER_STOPPED:
					set_shutdown(true);
					/* Stop received, do not wait for more events (continue) */
					continue;
				case ACC_EXPLORATION_SERVER_WAITING:
					/* Wait blocking until an event occurs */
					blocking_poll = true;
					break;
				case ACC_EXPLORATION_SERVER_STREAMING:
					/* Wait full amount of us (or until a socket event occurs) */
					break;
			}

			if (!acc_socket_server_poll_events(&socket_server, blocking_poll, ticks_until_next))
			{
				/* Socket disconnected or other error */
				break;
			}
		}
	}

	acc_socket_server_client_close(&socket_server);

	acc_socket_server_close(&socket_server);

	cleanup();
	printf("Shutdown complete.\n");

	return EXIT_SUCCESS;
}

void acc_integration_log(acc_log_level_t level, const char *module, const char *format, ...)
{
	char    log_buffer[LOG_BUFFER_MAX_SIZE];
	va_list ap;

	va_start(ap, format);
	int ret = vsnprintf(log_buffer, LOG_BUFFER_MAX_SIZE, format, ap);

	va_end(ap);

	if (ret >= LOG_BUFFER_MAX_SIZE)
	{
		log_buffer[LOG_BUFFER_MAX_SIZE - 4] = '.';
		log_buffer[LOG_BUFFER_MAX_SIZE - 3] = '.';
		log_buffer[LOG_BUFFER_MAX_SIZE - 2] = '.';
		log_buffer[LOG_BUFFER_MAX_SIZE - 1] = 0;
	}

	/* Embedded logs to exploration server */
	acc_exploration_server_send_log(server_if.write, level, module, log_buffer);

	/* Linux server will also log to stdout */
	uint32_t time_ms = acc_time_get();
	char     level_ch;

	unsigned int timestamp    = time_ms;
	unsigned int hours        = timestamp / 1000 / 60 / 60;
	unsigned int minutes      = timestamp / 1000 / 60 % 60;
	unsigned int seconds      = timestamp / 1000 % 60;
	unsigned int milliseconds = timestamp % 1000;

	level_ch = (level <= ACC_LOG_LEVEL_DEBUG) ? "EWIVD"[level] : '?';
	printf(LOG_FORMAT, hours, minutes, seconds, milliseconds, level_ch, module, log_buffer);

	fflush(stdout);
}
