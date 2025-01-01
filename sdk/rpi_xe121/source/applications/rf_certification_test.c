// Copyright (c) Acconeer AB, 2022-2023
// All rights reserved
// This file is subject to the terms and conditions defined in the file
// 'LICENSES/license_acconeer.txt', (BSD 3-Clause License) which is part
// of this source code package.

#include <stdint.h>
#include <stdlib.h>

#include "acc_rf_certification.h"

#include <signal.h>

/**
 * @brief Handle interrupt signals
 *
 * @param signum Signal number sent
 */
static void signal_handler(int signum);

int main(int argc, char *argv[]);

int main(int argc, char *argv[])
{
	signal(SIGINT, signal_handler);
	signal(SIGTERM, signal_handler);

	if (!acc_rf_certification_args(argc, argv))
	{
		return EXIT_FAILURE;
	}

	return EXIT_SUCCESS;
}

void signal_handler(int signum)
{
	(void)signum;
	acc_rf_certification_stop_set();
}
