BUILD_ALL += $(OUT_DIR)/example_service_calibration_caching

$(OUT_DIR)/example_service_calibration_caching: \
					$(OUT_OBJ_DIR)/example_service_calibration_caching.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
