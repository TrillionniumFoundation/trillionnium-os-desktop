# Successful debug3 retry

The real third attempt **passed** on source `31170ffb2ab6d18a85051d426e5d85a83f1b2abf`, tree `3bef60f628add169a08af75a81dac8c26bcca1da`. Actual tool session **39476 completed exit 0**; that outer tool also fetched/switched source before invoking the controller. Controller, driver and GDB each exited 0. All five owned leaders were reaped with status 0.

GDB hit `__ostd_main` at **0xffffffff88422f10**, read 32 live entry bytes matching both the boot snapshot and retained symbol ELF, then detached. The actual QEMU guest reached the complete single-CPU Asterinas initramfs boot and exited raw33. Complete serial SHA256 is `3363db54a8da156395dbd9995a0dff6bb517c3f259373204f886a485e5363460`.

This attempt reused the target populated by debug2. The driver log contains **zero Compiling lines** and reports release completion in **0.20s**. It is a genuine subsequent launch and debugger/boot acceptance, not a fresh empty-target build. Kernel source tree identity between debug2 and debug3 was checked; the same symbol and boot ELF bytes were reused. No new kernel-mode regression test run is claimed here.

Unlike the failed previous attempt, the wrapper passed the retained exclusive snapshot pathname to QEMU. Its complete boot ELF is retained **once** as `run/boot/artifacts-g0lyeygd/kernel.elf` inside `raw.tar.gz`: **5,975,720 bytes**, SHA256 `fbe81c0e2deae705d61d77ccaaf604e2bf1ca30e4541de71d263af6ecc62ec1b`. Archive extraction, full hash, length and entry bytes were verified. Firmware and initramfs snapshot bytes are also in that raw archive.

The **111,689,912-byte** symbol ELF has SHA256 `06c320f0799d4f8afcb610046dceae64b3cc9885aa64537bc24ce0219c67eaf3`. It is the exact symbol preserved from debug2 in `../debug-failures/artifacts/symbol-storage.json`. `symbol-artifact-reference.json` binds that ordered chunk manifest, gzip and raw ELF hashes. The 27MB gzip is not duplicated in this directory. Reassembly and symbol entry bytes were independently checked against those retained chunks.

The separate fresh live-artifact check completed exit 0 and is retained as `controllers/debug3-postcheck.json`. At that observation, both the snapshot and original source pathname still held the fbe81c0 bytes. No actual source replacement during debug3 is claimed. The historical debug2 mismatch remains a failure in its own archive.

Before retry, the pre-existing foreign generated manifest was preserved with RENAME_NOREPLACE under the workspace lock. `controllers/` retains the actual custody bytes, original preservation/stat/hash receipt, read-only copy receipt, `run-final-debug.py`, and the invoked `run-validation.py`. Its writer remains unknown; preservation does not assign a cause or process.

`raw.tar.gz` contains every file from the completed debug3 controller and run directories, with member SHA256/size/mode in `raw-archive-members.json`. `readable/` exposes the core results, command/environment, GDB/control, boot records and full serial directly. Original bytes, terminal escapes and line endings are unchanged. The raw archive also retains original duplicate initramfs locations as produced by the run.

`source/` retains 68 exact Git source/control files, including all 63 source hashes recorded in the debug3 environment; blob IDs, Git modes and SHA256 all match the exact source revision. The complete repository remains identified by commit/tree.

The full closure-debug denominator across both sibling directories is **3 attempts, 1 complete pass, 2 failures**, with **2 actual QEMU guests, both raw33**. The first attempt never launched a guest. Success here does not rewrite earlier failures or establish broader kernel/HOS2/SMP acceptance. `SHA256SUMS` covers all retained files except itself.
