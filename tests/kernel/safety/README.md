# Owned kernel safety regressions

See `support/kernel-safety/README.md` for implementation semantics, scope exclusions and commands. `run.py` is a development evidence runner; it accepts and hashes working bytes, builds the ordinary kernel, and runs the probes only inside an isolated, bounded QEMU guest. Every probe must return zero. Exit 77 is setup unavailable and is a failure of qualification, not a pass.

- `commoncap_probe.c`: owned same-ID/dumpable child with extra permitted CAP_CHOWN; denied maps read, then allowed after capability drop.
- `socket_snapshot_probe.c`: real SO_PEERCRED/SO_PEERGROUPS retained after ID/group mutation; fresh sockets reflect new values.
- `anon_budget_probe.c`: actual anonymous/private-file/tail faults, descendant COW, final-reference refund after RCU observations, SIGSEGV and event increment at the ceiling, sibling recovery, and four concurrent allocators against live limit updates.
- `lifecycle/*.c`: real dumpability state and credential/exec/fork/CLONE_VM/proc lifecycle; old open descriptors cannot follow a replacement image.
- `ptrace_dumpable_probe.c`: same-ID unprivileged TRACEME relationship; peek denied/allowed/denied over dumpability 0→1→0.

Use `run.py --smp 2` or `--smp 4` to exercise actual multiprocessor guest scheduling. Refund checks allow bounded quiescent observations; they do not promise a wall-clock bound when a CPU is stalled. Private VMO tail behavior is an existing Asterinas behavior, not a claim of Linux beyond-EOF compatibility.

Do not run `anon_budget_probe.c` on a production host. The runner supplies its own transient guest cgroup hierarchy.

## CI reuse

[A06](../../../.github/workflows/a06-kernel.yml) runs this suite with 2 and 4 CPUs immediately after its ordinary QueryAbi product build. `--product-evidence /absolute/a06-queryabi-candidate` validates that completed receipt, the exact clean Git head/tree and all three source snapshots, the original boot artifacts, raw QueryAbi completion and QEMU binary before reuse. It does not rebuild the kernel. Both guests run even if one fails, and the workflow always uploads their raw logs, source/artifact hashes and retained guest inputs.

The CI host uses the existing pinned Rust setup, GCC 13 and the same QEMU as the ordinary boot. `--cc` and `--qemu` make those executable choices explicit. Without `--product-evidence`, the original development mode still builds and boots the current working bytes. Neither mode establishes full memory isolation, HOS2 resource authorization, hardware support or production qualification.

`python3 -I -B tests/kernel/safety/test_runner.py` and its `-O` variant check the reuse gate, artifact/source tampering and guest assembly. They are harness tests, separate from the real guest probes.
