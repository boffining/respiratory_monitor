TOOLS_PREFIX     := arm-linux-gnueabihf-
TOOLS_AR         ?= $(TOOLS_PREFIX)ar
TOOLS_AS         ?= $(TOOLS_PREFIX)as
TOOLS_CC         ?= $(TOOLS_PREFIX)gcc
TOOLS_OBJDUMP    ?= $(TOOLS_PREFIX)objdump
TOOLS_OBJCOPY    ?= $(TOOLS_PREFIX)objcopy
TOOLS_SIZE       ?= $(TOOLS_PREFIX)size

TARGET_OS           := linux
TARGET_ARCHITECTURE := armv7l

ARFLAGS := cr

CFLAGS += -DTARGET_ARCH_armv7l -std=c99 -pedantic -Wall -Werror -Wextra -Wdouble-promotion -Wstrict-prototypes -Wcast-qual -Wmissing-prototypes -Winit-self -Wpointer-arith -Wshadow -MMD -MP -O3 -g -fPIC -fno-var-tracking-assignments -ffunction-sections -fdata-sections
CFLAGS += -D_GNU_SOURCE

# Override optimization level
ifneq ($(ACC_CFG_OPTIM_LEVEL),)
	CFLAGS  += $(ACC_CFG_OPTIM_LEVEL)
endif

LDFLAGS += -Wl,--gc-sections

# Wrappers that enable cross-compiling on Ubuntu 18 and latest versions of Debian.
LDFLAGS += -Wl,--wrap=expf
LDFLAGS += -Wl,--wrap=logf
LDFLAGS += -Wl,--wrap=powf

LDLIBS += -ldl -lm -lrt
