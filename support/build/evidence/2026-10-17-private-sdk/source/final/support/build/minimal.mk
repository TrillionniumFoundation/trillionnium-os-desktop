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

# Keep the symbol ELF with debug info; only the boot ELF is stripped. The
# recorder passes the runner-owned listener FD into QEMU without rebinding.
.PHONY: gdb_server
gdb_server: initramfs $(CARGO_OSDK)
	@cd kernel && cargo osdk run $(CARGO_OSDK_BUILD_ARGS) --strip-elf --gdb-server "wait-client,addr=127.0.0.1:$(A01_GDB_PORT)"
