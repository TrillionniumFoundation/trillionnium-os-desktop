# Local UDP error regression

This profile checks the local connected-UDP error path that blocked the original
Hepta Agentd's runtime shutdown. It runs the upstream-style C regression on Linux
and then runs **the same static ELF** on the ordinary A06 product kernel. It does
not build a second kernel, install a trusted initial image, change resolver
configuration, or change the original Supervisor's five-second stop grace.

## Entry points and coverage

The source is
`kernel/asterinas/test/initramfs/src/regression/network/udp_local_error.c`.
The common regression Makefile discovers `*.c`, but execution is explicit in
`network/run_test.sh`; the new `./udp_local_error` entry enables the upstream full
regression route. A06 uses a minimal initramfs with `AUTO_TEST=none`, so it also
needs its own explicit Linux/native workload step.

| Case | Checks |
| --- | ---: |
| Connected error is read once; delivery recovers | 11 |
| `recv` consumes the pending error | 7 |
| `send` consumes the pending error | 8 |
| Unconnected socket ignores the error without `IP_RECVERR` | 4 |
| Connected socket ignores an error for another destination | 8 |
| Self-delivery has no error | 5 |
| **Total** | **43** |

The test retains its five-second process alarm, 500 ms readiness bounds, and
20 ms negative observation bounds. It reserves the destination port while
binding the sender to a different local port, then closes the reservation.
This prevents the closed-port control from accidentally sending to itself.

`udp_local_error.expected.stderr` is the original successful Linux transcript:
49 lines, consisting of 43 individual checks and six summaries. Its SHA-256 is
`67178f9fdbe1e761bc9daad11b88f183658fc8ef7693c77db471464a627ac085`.
The transcript was recorded for the unchanged C source at ordinary UDP fix
commit `c8f0c88ecb640117686ff05f850a73e60688eac7`, tree
`641c6627ba9aaf79ca3506154831a6c51abe521f`. It is a fixed parser input, not a
claim that a future CI run passed.

## Reproduce

Run from a clean reviewed checkout. Keep all output directories outside that
checkout. The compiler, static glibc development files, QEMU 8.2.2, and pinned
SeaBIOS/initramfs inputs are the existing Ubuntu 24.04 A06 dependencies.

```sh
head=$(git rev-parse HEAD)
tree=$(git rev-parse HEAD^{tree})
out=/absolute/path/to/a/new/udp-evidence
mkdir "$out"

python3 -I -B -m unittest discover -s tests/workloads/linux \
  -p 'test_udp_local_error_guest.py' -v
python3 -I -B -O -m unittest discover -s tests/workloads/linux \
  -p 'test_udp_local_error_guest.py' -v

python3 -I -B tests/workloads/linux/run_udp_local_error_guest.py reference \
  --expected-source-head "$head" --expected-source-tree "$tree" \
  --cc /usr/bin/gcc-13 --output "$out/linux"

read -r probe_sha probe_name < "$out/linux/probe.sha256"
test "$probe_name" = probe.elf
python3 -I -B tests/workloads/linux/run_udp_local_error_guest.py guest \
  --linux-reference "$out/linux" --expected-probe-sha256 "$probe_sha" \
  --product-evidence /absolute/path/to/a06-queryabi-candidate \
  --expected-source-head "$head" --expected-source-tree "$tree" \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --output "$out/guest"
```

The product evidence must already have passed
`tests/kernel/control/run_queryabi_candidate_guest.py` for this same clean head
and tree. A06 supplies its existing `a06-queryabi-candidate` directory, so this
additional workload does not repeat the kernel build or replace its original
ordinary boot and QueryAbi gates.

## Acceptance and failure evidence

The Linux stage copies the tracked C source/header and runner inputs, compiles
one static x86-64 ELF, records the actual compiler exit, and freezes the ELF
digest before execution. It uses a fresh process group and records the actual
Linux exit independently of the parser. Acceptance requires exit 0, no timeout,
empty stdout, and the exact fixed stderr transcript. A compile error, signal,
missing status, or partially captured result remains a failure.

The guest stage revalidates that Linux record, copies the exact retained ELF,
and admits the existing ordinary product using its source snapshots, boot and
QueryAbi receipt, and frozen kernel hash. No `--cfg ktest` or stop tracing is
accepted. A fresh nonce brackets the probe in the original initramfs. Acceptance
requires actual QEMU status 33, no timeout, all 49 test lines in order, the
nonce-bound probe exit 0, the original boot marker after that exit, and unchanged
input bytes. Only terminal escape codes and CR/LF presentation are normalized.
Missing/duplicate checks, malformed output, failed checks paired with a false
zero-failure summary, reordered completion, and panic/tracing records fail.

The new Python tests exercise these failure decisions and static-ELF admission
without using a socket or pretending to provide a native kernel result. Both
ordinary and optimized Python execution must pass. The maintained C source
remains the authority for the syscall assertions and their timing bounds.

## Retained artifacts

A06's `always()` artifact upload includes `a06-udp-checks`, `a06-udp-linux`, and
`a06-udp-guest`, including failed runs. The original `a06-queryabi-candidate`
product evidence stays in that same A06 artifact.

| Directory | Required raw evidence |
| --- | --- |
| `a06-udp-checks` | Normal and `-O` parser/transport-admission test logs |
| `a06-udp-linux` | Frozen sources, C/header, probe ELF/digest, compiler argv/stdout/stderr/actual exit, pre-execution `input.json`, Linux argv/stdout/stderr/actual exit, `result.json` |
| `a06-udp-guest` | Frozen sources, identical probe ELF, ordinary kernel/BIOS/initramfs, pre-execution nonce/input receipt, QEMU argv/stdout/stderr/actual exit, `result.json` |
| `a06-queryabi-candidate` | Original ordinary build/boot and QueryAbi receipts, raw serial logs, kernel bytes, complete before/after source snapshots |

For repository evidence publication, retain the CI run ID and exact source
head/tree, hash every raw file before packaging, and store the small manifest
and verdict with the immutable raw archive reference under
`results/integration/<date>-udp-local-error/`. Do not replace failed evidence or
reconstruct raw execution receipts from a passing summary. A compressed archive
may use a different container format; the manifest must describe the original
uncompressed file bytes. Build caches are not qualification evidence.

This workload proves the six local UDP cases only. Remote ICMP delivery,
extended `IP_RECVERR` queues, original Hepta lifecycle qualification, trusted
post-exec authority, hardware readiness, and power-loss durability require their
own evidence. The earlier diagnostic Agentd causal run and the later clean
H1-product lifecycle qualification must retain separate source and ELF bindings.
