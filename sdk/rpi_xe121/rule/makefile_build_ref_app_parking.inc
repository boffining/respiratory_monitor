BUILD_ALL += $(OUT_DIR)/ref_app_parking

$(OUT_DIR)/ref_app_parking: \
					$(OUT_OBJ_DIR)/ref_app_parking_main.o \
					$(OUT_OBJ_DIR)/ref_app_parking.o \
					$(OUT_OBJ_DIR)/acc_algorithm.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
