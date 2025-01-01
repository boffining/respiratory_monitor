BUILD_ALL += $(OUT_DIR)/example_service_multiple_configurations

$(OUT_DIR)/example_service_multiple_configurations : \
					$(OUT_OBJ_DIR)/example_service_multiple_configurations.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
