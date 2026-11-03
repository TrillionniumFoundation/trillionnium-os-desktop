# Controlled non-dumpable process isolation failure

The same static C probe used only its own single child, public sentinel and
known /dev/null descriptor. On Linux7.0, actual UID1000, zero effective/permitted
capabilities and NoNewPrivs1, SET0/SET1/SET0/ordinary-exec produced the expected
dumpability and eight sensitive access decisions; the child was reaped.

On the prebuilt 6c26 ordinary Asterinas kernel, actual UID60001/caps0/NNP1,
SET0 still allowed maps, four-byte sentinel memory, controlled environment,
auxv, descriptor readlink and pidfd_getfd of that same child. GET stayed0 after
SET1 and ordinary exec. Raw QEMU33 in0.968s is not success: the probe exited42
and confirmed the defect. The child was reaped. PTRACE_ATTACH returned EIO
because it is unimplemented; process_vm_readv returned ENOSYS. Neither is
reported as an implemented bypass, and no unrelated process was accessed.

The relevant sixteen source files are byte-identical between the audited d4f0
and actual prebuilt6c26 source. Original compile failure, final C/helper, Linux
JSONL, native serial, command/shape/source identities and hashes are preserved.
Official Linux source is referenced by original URL/hash rather than vendored.
No compiler target, ELF, disk, private state or unrelated process data is copied.

The P1 repair must provide real image-owned dumpability across clone/fork/exec
and credentials, actual proc/pidfd access gates and correct per-open image
lifetime. A Host startup prctl/readback on the old stub does not establish
isolation. Fixed-kernel, privileged-exec and credential-race qualification remain
open until their separate actual tests pass.

See [the complete manifest](publication.json).
