BUILD_ALL += $(OUT_DIR)/example_processing_static_presence

$(OUT_DIR)/example_processing_static_presence: \
					$(OUT_OBJ_DIR)/example_processing_static_presence.o \
					$(OUT_OBJ_DIR)/acc_control_helper.o \
					$(OUT_OBJ_DIR)/acc_processing_helpers.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
