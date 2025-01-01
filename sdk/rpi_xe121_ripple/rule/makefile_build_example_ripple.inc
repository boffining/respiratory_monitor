# Remove some compiler options to make Ripple API compile
# Assume this is the only makefile using below objects
CFLAGS-$(OUT_OBJ_DIR)/example_ripple.o += -Wno-pedantic
CFLAGS-$(OUT_OBJ_DIR)/ripple_api_port.o += -Wno-pedantic

LDLIBS += -pthread

BUILD_ALL += $(OUT_DIR)/example_ripple

$(OUT_DIR)/example_ripple : \
					$(OUT_OBJ_DIR)/example_ripple.o \
					$(OUT_OBJ_DIR)/ripple_api_port.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
