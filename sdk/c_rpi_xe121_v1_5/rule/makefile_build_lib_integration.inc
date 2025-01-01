BUILD_LIBS += $(OUT_LIB_DIR)/libintegration.a

$(OUT_LIB_DIR)/libintegration.a: \
			$(addprefix $(OUT_OBJ_DIR)/,$(notdir $(patsubst %.c,%.o,$(sort $(wildcard source/integration/*.c)))))

	@echo "    Creating archive $(notdir $@)"
	$(SUPPRESS)rm -f $@
	$(SUPPRESS)$(TOOLS_AR) $(ARFLAGS) $@ $^
