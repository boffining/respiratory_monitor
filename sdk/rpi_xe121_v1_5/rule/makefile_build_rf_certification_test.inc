BUILD_ALL += $(OUT_DIR)/rf_certification_test

$(OUT_DIR)/rf_certification_test : \
					$(OUT_OBJ_DIR)/rf_certification_test.o \
					libacc_rf_certification_a121.a \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
