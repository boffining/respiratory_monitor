BUILD_ALL += $(OUT_DIR)/example_control_helper

$(OUT_DIR)/example_control_helper: \
					$(OUT_OBJ_DIR)/example_control_helper.o \
					$(OUT_OBJ_DIR)/acc_control_helper.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
