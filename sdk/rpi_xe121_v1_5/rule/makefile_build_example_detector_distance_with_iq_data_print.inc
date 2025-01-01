

BUILD_TARGET = example_detector_distance_with_iq_data_print

BUILD_ALL += $(OUT_DIR)/$(BUILD_TARGET)

$(OUT_DIR)/$(BUILD_TARGET): \
					$(OUT_OBJ_DIR)/$(BUILD_TARGET).o \
					libacconeer_a121.a \
					libacc_detector_distance_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
