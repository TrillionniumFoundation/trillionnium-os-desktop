# Use the upstream developer targets with our small initramfs. This overlay
# avoids the upstream Nix rootfs/data-disk prerequisites without editing them.
.PHONY: initramfs install_osdk $(CARGO_OSDK)
initramfs: check_vdso
	@test -s "$(A01_INITRAMFS)"

# Override the binary recipe as well: upstream's recipe recursively invokes
# make without this overlay, which would otherwise drop --locked.
$(CARGO_OSDK): $(OSDK_SRC_FILES)
	@test -n "$(A01_OSDK_INSTALL_ROOT)" || { echo 'A01_OSDK_INSTALL_ROOT is required' >&2; exit 2; }
	@OSDK_LOCAL_DEV=1 cargo install --locked --root "$(A01_OSDK_INSTALL_ROOT)" cargo-osdk --path osdk
	@sha256sum "$(CARGO_OSDK)" > "$(A01_OSDK_INSTALL_ROOT)/cargo-osdk.sha256"

install_osdk:
	@test -n "$(A01_OSDK_INSTALL_ROOT)" || { echo 'A01_OSDK_INSTALL_ROOT is required' >&2; exit 2; }
	@OSDK_LOCAL_DEV=1 cargo install --locked --root "$(A01_OSDK_INSTALL_ROOT)" cargo-osdk --path osdk
	@sha256sum "$(CARGO_OSDK)" > "$(A01_OSDK_INSTALL_ROOT)/cargo-osdk.sha256"

override CARGO_OSDK_BUILD_ARGS := --release --boot-method=vmm-direct --grub-boot-protocol=multiboot --initramfs="$(A01_INITRAMFS)" --kcmd-args="loglevel=info" --kcmd-args="earlycon" --kcmd-args="console=ttyS0" --qemu-exe="$(A01_QEMU_WRAPPER)"

# The overlay replaces upstream BUILD_ARGS, including its expansion of COMMON
# args. Forward the selected profile here as well; setting FEATURES alone would
# silently produce the ordinary QueryAbi-only kernel.
ifneq ($(filter-out 0 1,$(HEPTA_G1C_TRUSTED_OBSERVE) $(HEPTA_G1D_TRUSTED_CONTROL)),)
$(error trusted profile flags must be 0 or 1)
endif
ifeq ($(HEPTA_G1C_TRUSTED_OBSERVE)$(HEPTA_G1D_TRUSTED_CONTROL),11)
$(error select at most one G1-c/G1-d build profile)
endif
ifeq ($(HEPTA_G1C_TRUSTED_OBSERVE),1)
override CARGO_OSDK_BUILD_ARGS += --features=g1c-trusted-observe
else ifeq ($(HEPTA_G1D_TRUSTED_CONTROL),1)
override CARGO_OSDK_BUILD_ARGS += --features=g1d-trusted-control
endif
ifneq ($(filter 1,$(HEPTA_G1C_TRUSTED_OBSERVE) $(HEPTA_G1D_TRUSTED_CONTROL)),)
# Preserve the upstream recipe and prerequisites, but retain its actual OSDK
# argv in kernel.log for this explicitly qualified build profile.
kernel:
	cd kernel && cargo osdk build $(CARGO_OSDK_BUILD_ARGS)
endif

# Keep the symbol ELF with debug info; only the boot ELF is stripped. The
# recorder passes the runner-owned listener FD into QEMU without rebinding.
.PHONY: gdb_server
gdb_server: initramfs $(CARGO_OSDK)
	@cd kernel && cargo osdk run $(CARGO_OSDK_BUILD_ARGS) --strip-elf --gdb-server "wait-client,addr=127.0.0.1:$(A01_GDB_PORT)"
