BUILD_ALL += $(OUT_DIR)/ref_app_breathing

$(OUT_DIR)/ref_app_breathing: \
					$(OUT_OBJ_DIR)/ref_app_breathing_main.o \
					$(OUT_OBJ_DIR)/ref_app_breathing.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					libacconeer_a121.a \
					libacc_detector_presence_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
