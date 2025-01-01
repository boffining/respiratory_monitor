BUILD_ALL += $(OUT_DIR)/example_detector_presence

$(OUT_DIR)/example_detector_presence: \
					$(OUT_OBJ_DIR)/example_detector_presence.o \
					libacconeer_a121.a \
					libacc_detector_presence_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
