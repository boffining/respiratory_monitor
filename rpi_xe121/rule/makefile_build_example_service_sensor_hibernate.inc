BUILD_ALL += $(OUT_DIR)/example_service_sensor_hibernate

$(OUT_DIR)/example_service_sensor_hibernate : \
					$(OUT_OBJ_DIR)/example_service_sensor_hibernate.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
