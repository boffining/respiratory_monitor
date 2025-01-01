BUILD_ALL += $(OUT_DIR)/example_waste_level

$(OUT_DIR)/example_waste_level: \
					$(OUT_OBJ_DIR)/example_waste_level_main.o \
					$(OUT_OBJ_DIR)/example_waste_level.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
