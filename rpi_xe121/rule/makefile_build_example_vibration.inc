
BUILD_ALL += $(OUT_DIR)/example_vibration

$(OUT_DIR)/example_vibration: \
					$(OUT_OBJ_DIR)/example_vibration.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
