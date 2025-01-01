
BUILD_ALL += $(OUT_DIR)/example_surface_velocity

$(OUT_DIR)/example_surface_velocity: \
					$(OUT_OBJ_DIR)/example_surface_velocity.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					$(OUT_OBJ_DIR)/acc_processing_helpers.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
