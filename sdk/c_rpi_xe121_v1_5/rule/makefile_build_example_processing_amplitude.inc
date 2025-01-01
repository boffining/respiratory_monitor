BUILD_ALL += $(OUT_DIR)/example_processing_amplitude

$(OUT_DIR)/example_processing_amplitude: \
					$(OUT_OBJ_DIR)/example_processing_amplitude.o \
					$(OUT_OBJ_DIR)/acc_control_helper.o \
					$(OUT_OBJ_DIR)/acc_processing_helpers.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
