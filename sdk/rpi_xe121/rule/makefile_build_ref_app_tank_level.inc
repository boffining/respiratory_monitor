BUILD_ALL += $(OUT_DIR)/ref_app_tank_level

$(OUT_DIR)/ref_app_tank_level: \
					$(OUT_OBJ_DIR)/ref_app_tank_level.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					libacconeer_a121.a \
					libacc_detector_distance_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
