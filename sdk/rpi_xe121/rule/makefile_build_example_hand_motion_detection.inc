BUILD_ALL += $(OUT_DIR)/example_hand_motion_detection

$(OUT_DIR)/example_hand_motion_detection: \
					$(OUT_OBJ_DIR)/example_hand_motion_detection_main.o \
					$(OUT_OBJ_DIR)/example_hand_motion_detection.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					libacconeer_a121.a \
					libacc_detector_presence_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
