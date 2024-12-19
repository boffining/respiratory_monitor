BUILD_ALL += out/acc_exploration_server_a121

out/acc_exploration_server_a121 : \
					$(OUT_OBJ_DIR)/acc_exploration_server_linux.o \
					$(OUT_OBJ_DIR)/acc_socket_server.o \
					libacconeer_exploration_server_a121.a \
					libacconeer_a121.a \
					$(OUT_OBJ_DIR)/acc_integration_linux.o \
					$(addprefix $(OUT_OBJ_DIR)/,$(notdir $(patsubst %.c,%.o,$(sort $(wildcard source/integration/acc_board_*.c))))) \
					$(addprefix $(OUT_OBJ_DIR)/,$(notdir $(patsubst %.c,%.o,$(sort $(wildcard source/integration/acc_lib*.c))))) \

	@echo "    Linking $(notdir $@)"
	$(SUPPRESS)mkdir -p out
	$(SUPPRESS)$(LINK.o) -Wl,--start-group $^ -Wl,--end-group $(LDLIBS) -o $@
