
BUILD_ALL += $(OUT_DIR)/example_diagnostic_test

$(OUT_DIR)/example_diagnostic_test : \
					$(OUT_OBJ_DIR)/example_diagnostic_test.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
