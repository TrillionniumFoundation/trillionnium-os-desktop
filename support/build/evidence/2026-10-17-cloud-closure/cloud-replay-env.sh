# Source from a selected project worktree in this already restored cloud.
# These are the actual N1 dependency/tool settings; not a package installer.
unset CARGO_INCREMENTAL ASTER_BUILD_TIMESTAMP SOURCE_DATE_EPOCH OSDK_BUILD_USERNAME OSDK_BUILD_HOSTNAME CARGO_ENCODED_RUSTFLAGS CARGO_TARGET_DIR RUSTFLAGS RUSTC_WRAPPER RUSTC_WORKSPACE_WRAPPER A01_KERNEL_WORKER A01_REPRO_POLICY MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MAKELEVEL A01_RUN_DIR
export A01_BUSYBOX=/workspace/scratch/ae1a8cf05419/native-tools/root/usr/bin/busybox
export A01_QEMU_BIOS=/workspace/scratch/ae1a8cf05419/native-tools/root/usr/share/seabios/bios-256k.bin
export A01_QEMU_DATA_DIR=/workspace/scratch/ae1a8cf05419/native-tools/root/usr/share/qemu
export A01_QEMU_TIMEOUT=300
export CARGO_BUILD_JOBS=2
export CARGO_HOME=/workspace/scratch/ae1a8cf05419/toolchains/cargo
export CARGO_NET_GIT_FETCH_WITH_CLI=true
export LD_LIBRARY_PATH=/workspace/scratch/ae1a8cf05419/native-tools/root/usr/lib/x86_64-linux-gnu:/workspace/scratch/ae1a8cf05419/native-tools/root/lib/x86_64-linux-gnu:/workspace/scratch/ae1a8cf05419/native-tools/root/usr/lib/llvm-18/lib
export PATH=/workspace/scratch/ae1a8cf05419/toolchains/cargo/bin:/workspace/scratch/ae1a8cf05419/native-tools/root/usr/bin:/workspace/scratch/ae1a8cf05419/native-tools/root/usr/lib/llvm-18/bin:/root/.codex/tmp/arg0/codex-arg0z2lg97:/opt/codex/codex-path:/opt/codex/runtimes/codex-primary-runtime/dependencies/bin/override:/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin:/opt/codex/runtimes/codex-primary-runtime/dependencies/node/bin:/opt/codex/runtimes/codex-primary-runtime/dependencies/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/codex/runtimes/codex-primary-runtime/dependencies/bin/fallback
export PKG_CONFIG_LIBDIR=/workspace/scratch/ae1a8cf05419/native-tools/root/usr/lib/x86_64-linux-gnu/pkgconfig:/workspace/scratch/ae1a8cf05419/native-tools/root/usr/share/pkgconfig
export PKG_CONFIG_SYSROOT_DIR=/workspace/scratch/ae1a8cf05419/native-tools/root
export QEMU_MODULE_DIR=/workspace/scratch/ae1a8cf05419/native-tools/root/usr/lib/x86_64-linux-gnu/qemu
export RUSTUP_HOME=/workspace/scratch/ae1a8cf05419/toolchains/rustup
export RUSTUP_TOOLCHAIN=nightly-2026-07-21
export VDSO_LIBRARY_DIR=/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop/support/build/out/linux-vdso
export CARGO_TARGET_DIR="$PWD/kernel/asterinas/target"
