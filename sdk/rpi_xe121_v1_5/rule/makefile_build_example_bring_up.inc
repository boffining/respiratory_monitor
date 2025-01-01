
BUILD_ALL += $(OUT_DIR)/example_bring_up

$(OUT_DIR)/example_bring_up : \
					$(OUT_OBJ_DIR)/example_bring_up.o \
					libacconeer_a121.a \
					libintegration.a \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
