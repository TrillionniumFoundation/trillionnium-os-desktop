# Use the upstream developer targets with our small initramfs. This overlay
# avoids the upstream Nix rootfs/data-disk prerequisites without editing them.
.PHONY: initramfs install_osdk
initramfs: check_vdso
	@test -s "$(A01_INITRAMFS)"

# Override the binary recipe as well: upstream's recipe recursively invokes
# make without this overlay, which would otherwise drop --locked.
$(CARGO_OSDK): $(OSDK_SRC_FILES)
	@OSDK_LOCAL_DEV=1 cargo install --locked cargo-osdk --path osdk

install_osdk:
	@OSDK_LOCAL_DEV=1 cargo install --locked cargo-osdk --path osdk

override CARGO_OSDK_BUILD_ARGS := --release --boot-method=vmm-direct --grub-boot-protocol=multiboot --initramfs="$(A01_INITRAMFS)" --kcmd-args="loglevel=info" --kcmd-args="earlycon" --kcmd-args="console=ttyS0" --qemu-exe="$(A01_QEMU_WRAPPER)"

# The overlay replaces upstream BUILD_ARGS, including its expansion of COMMON
# args. Forward the selected profile here as well; setting FEATURES alone would
# silently produce the ordinary QueryAbi-only kernel.
ifneq ($(filter-out 0 1,$(HEPTA_G1C_TRUSTED_OBSERVE) $(HEPTA_G1D_TRUSTED_CONTROL) $(HEPTA_G2_NATIVE_AGENTD)),)
$(error trusted profile flags must be 0 or 1)
endif
ifneq ($(word 2,$(filter 1,$(HEPTA_G1C_TRUSTED_OBSERVE) $(HEPTA_G1D_TRUSTED_CONTROL) $(HEPTA_G2_NATIVE_AGENTD))),)
$(error select at most one trusted build profile)
endif
ifeq ($(HEPTA_G1C_TRUSTED_OBSERVE),1)
override CARGO_OSDK_BUILD_ARGS += --features=g1c-trusted-observe
else ifeq ($(HEPTA_G1D_TRUSTED_CONTROL),1)
override CARGO_OSDK_BUILD_ARGS += --features=g1d-trusted-control
else ifeq ($(HEPTA_G2_NATIVE_AGENTD),1)
override CARGO_OSDK_BUILD_ARGS += --features=g2-native-agentd
endif
ifneq ($(filter 1,$(HEPTA_G1C_TRUSTED_OBSERVE) $(HEPTA_G1D_TRUSTED_CONTROL) $(HEPTA_G2_NATIVE_AGENTD)),)
# Preserve the upstream recipe and prerequisites, but retain its actual OSDK
# argv in kernel.log for this explicitly qualified build profile.
kernel:
	cd kernel && cargo osdk build $(CARGO_OSDK_BUILD_ARGS)
endif
