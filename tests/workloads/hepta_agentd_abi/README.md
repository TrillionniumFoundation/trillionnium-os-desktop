# Original Agentd ordinary Linux ABI preflight

This runner executes the unchanged, frozen original Agentd ELF in an isolated ordinary Asterinas QEMU guest. Its narrow success boundary is dynamic loading, Rust `main`, and the expected refusal of an empty environment. That boundary passed in the retained 2026-10-22 run. It does not start or qualify the daemon, original owner, G2 transaction path, production configuration, or complete F.

The runner is **disabled by default**. `--execute` is required to construct its disposable payload image and start QEMU. Agentd, `ldd`, and the dynamic loader are never executed on the host.

## Source and expected result

The original binary currently has no `--help` or `--version` branch. `main.rs` calls `AgentdConfig::from_process_environment()` before argument parsing and before entering the asynchronous runtime. With an empty environment, configuration rejects the missing `HEPTA_FLEET_ROOT` before registry loading or acquiring the writer lock.

The expected child result is:

```text
stdout: empty
stderr: Error: invalid agentd configuration: HEPTA_FLEET_ROOT is required\n
exit: 1
```

`source-review.json` retains Git blob IDs and SHA256 values for the original startup source, reviewed at Hepta commit `eefc858f4c15149f017a60642cf36b58d82d5529`. A supplied frozen binary may come from a later source commit, but its manifest must bind the same five reviewed startup files. Changed startup code requires a new review; it cannot silently inherit this oracle.

## Files

| File | Role |
| --- | --- |
| `run_agentd_abi.py` | Disabled-default staging, input checks, QEMU invocation and exact result oracle |
| `agentd_abi_probe.c` | Small static guest launcher: empty-environment `execve`, actual `waitpid`, separate bounded stdout/stderr records |
| `cpio_codec.py` | Unchanged copy of the existing `tests/organ_backend/run_guest_probe.py` newc helper; only `pack`/`unpack` are used |
| `source-review.json` | Original source identities and source-derived refusal contract |
| `test_agentd_abi.py` | Host-side input, ELF-closure, initramfs-preservation, result-integrity and execution-receipt controls |

The four runtime files are byte-for-byte identical to the first candidate runtime bundle. The test uses the repository-relative accepted A01 initramfs fixture at `support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz`.

## Host validation gate

From repository root, on x86_64 Linux with Python 3 and `readelf`:

```sh
python3 -I -B -m unittest discover \
  -s tests/workloads/hepta_agentd_abi -p test_agentd_abi.py -v
python3 -I -B tests/workloads/hepta_agentd_abi/run_agentd_abi.py
```

The tests read the host's `/bin/true` ELF and system shared libraries to check closure staging; they never execute that ELF. The last command verifies disabled behavior and does not produce a native acceptance result. A CI job running these commands is a host-control gate only. It must not imply that the private frozen binary or QEMU smoke ran.

The accompanying `.github/workflows/hepta-agentd-abi-host.yml` checks the exact PR head on Ubuntu 24.04, requires all 11 control regressions with zero skips, compiles the launcher with `-static -Wall -Wextra -Werror`, and checks the clean checkout and existing empty root README invariant. It only triggers for this module or that workflow. Compilation does not execute the launcher, Agentd, or QEMU. A newly integrated workflow needs its own actual CI result; the retained host test result below is local validation.

## Frozen input

The producer must first copy the intended completed binary into a new task-owned directory and verify its expected digest. Do not point this profile at an actively changing Cargo output. The runner takes that directory's manifest and an explicit manifest SHA256, preserving the actual build and published source identities separately.

Required manifest shape:

```json
{
  "schema": "hepta.agentd-frozen-input.v1",
  "binary": {"path": "agentd.elf", "bytes": 0, "sha256": "ACTUAL_SHA256", "profile": "ACTUAL_PROFILE"},
  "build_source": {"head": "ACTUAL_BUILD_COMMIT", "tree": "ACTUAL_BUILD_TREE"},
  "published_source": null,
  "source_files": []
}
```

The example deliberately cannot pass. Supply real values and the five Rust source records (`path`, `git_blob`, `sha256`) for Agentd `main.rs`, `config.rs`, `error.rs`, and hepta-paths `lib.rs`, `fleet.rs`. Their reviewed identities are in `source-review.json`. If publication exists, `published_source` contains its actual full commit and tree; the tree must match the build tree. An unpublished input keeps this field null.

## Optional native smoke

From repository root, substitute actual absolute artifact paths and retained hashes:

```sh
python3 -I -B tests/workloads/hepta_agentd_abi/run_agentd_abi.py --execute \
  --input-manifest /absolute/frozen-input/manifest.json \
  --expected-input-manifest-sha256 ACTUAL_MANIFEST_SHA256 \
  --kernel /absolute/ordinary-queryabi/product-kernel.elf \
  --expected-kernel-sha256 8170402aaa7408eb2c4ab1ade2cd1d9641ef03ccbd37631aaec775528df2ede7 \
  --initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --bios /usr/share/seabios/bios-256k.bin \
  --qemu /usr/bin/qemu-system-x86_64 \
  --expected-qemu-sha256 ACTUAL_QEMU_BINARY_SHA256 \
  --cc /usr/bin/gcc-13 \
  --output /absolute/new-agentd-abi-result
```

This initial profile pins the already tested ordinary kernel from OS commit `85d394f99c73ad3194d57c876712ac01b59d90ca`, tree `7389c0a3f982983087953f75de7042fc058be088`. A later kernel needs a separately retained source/build/qualification identity before changing this profile's pin.

The runner recursively inspects `DT_NEEDED` with `readelf`, copies the binary and resolved shared libraries into a fresh ext2 image, and records their SHA256 values. Its original PT_INTERP path is supplied inside the guest. The large Agentd ELF remains on the disk; only the small static launcher enters the existing bounded initramfs.

QEMU uses TCG, one vCPU, 2 GiB by default, no NIC, no user configuration, no host filesystem sharing, and only that newly created read-only image. No host mount, loop device or chroot is used. The guest child receives no CLI flags or environment variables. It cannot obtain fleet state, providers, grants or credentials from the host.

## Evidence and qualification

Passing requires exact nonce-bound records in order; empty stdout; the expected stderr byte-for-byte; ordinary child exit 1; launcher exit 0; original init and boot markers exactly once; actual QEMU exit 33; no timeout, oversized serial output or kernel panic; and unchanged input manifest, frozen binary and payload image. Missing libraries, exec failure, signals, duplicate/stale records and altered diagnostics fail.

Retain the entire output directory, especially `result.json`, `serial.log`, `invocation.json`, `runtime-inputs.json`, the input manifest, tool hashes, symbol-version output and format/compile logs. `executed=true` is set immediately after successful QEMU process creation, so subsequent collection failures remain real failed executions. A pass retains `production=false`, `daemon_started=false`, `original_owner_runtime=false`, `g2_completed=false` and `f_completed=false`.

### Actual 2026-10-22 native result

The [retained evidence](../../../results/integration/2026-10-22-agentd-ordinary-abi/README.md) contains the original result, invocation, dependency closure and complete compressed serial, together with an independent replay of this exact oracle. The four runtime files match the executed bundle byte-for-byte. The repository relocation changed only the test fixture path; all 11 host controls passed with no skips.

| Input or outcome | Retained identity or result |
| --- | --- |
| Original Agentd build and published commit | `6d6097da843f5831dfaf9cee3530da512d072a15` |
| Original Agentd source tree | `f722fbe5f24275c324089be720559a40901105f3` |
| Frozen original ELF | 484,463,504 bytes; SHA256 `228d2e07583d0d27cf5750a6ba169254380fb4d49f1fdc21adcc04001fc3252f` |
| Binary profile | `dev; debug=0; incremental=0; Rust 1.95.0` |
| Ordinary kernel | OS `85d394f99c73ad3194d57c876712ac01b59d90ca`; ELF SHA256 `8170402aaa7408eb2c4ab1ade2cd1d9641ef03ccbd37631aaec775528df2ede7` |
| Actual child result | Empty stdout; exact missing-`HEPTA_FLEET_ROOT` stderr; exit 1 |
| Guest completion | Launcher exit 0; original boot marker; actual QEMU exit 33; no timeout or panic |
| Payload integrity | Remote execution rehashed the payload and frozen inputs unchanged; payload SHA256 `029f024f79f0e85cfb2ec53269b093077d64c163923817cdaddffff94eefbced` |
| Complete raw serial | 7,287,706 bytes, 21,537 lines; SHA256 `0567b1b7a03ca4d9f5c09d5113970bb3512fc976457d68e492cab2c7463dcd74` |

**The run was not free of I/O errors.** After the child's successful oracle markers, shutdown `SYS_SYNC` produced one `failed to do Write ... IoError` and two `writeback I/O failed ... IoError` diagnostics, followed by `SYS_REBOOT` and QEMU exit 33. These three diagnostics remain in the complete serial and the independent replay report. The current ext2 read paths can dirty atime on a read-only filesystem, its sync chain attempts writeback, and the virtio block driver does not negotiate the RO feature. The read-only QEMU backend rejects the write; the unchanged image proves this run did not persist it. The narrow loader/config oracle does not qualify correct read-only filesystem semantics or error-free shutdown. Keep this defect visible and fix its owners separately; making this payload writable would remove the negative boundary exercised here.

The serial also contains 25 `Unimplemented syscall number: 334` warnings (`rseq` on x86_64). The tested programs continue past the unsupported call and reach the exact expected outcome. This is evidence of a working fallback for this startup, not implemented `rseq` support.

### Next daemon-start boundary

Use a separate gate for the next stage and retain this exact refusal gate. Its inputs need a fresh writable guest state image and the original FleetRegistry/Supervisor fixture built against the intended final Hepta tree. The existing fixture initializes an empty canonical registry, registers the real agent manifest and workspace, writes the existing no-turn test configuration into the registered home, and starts the original command through `Supervisor` and `UnixProcessDriver`. That driver must assign the generation, working directory and registered environment; do not replace the original owner with hand-written fleet JSON or injected identity values.

The next source review must cover that exact tree's original process driver, runtime/store initialization and migrations before claiming daemon startup. Then require real startup/liveness and orderly stop evidence in the guest, plus the actual writable-store and socket outcomes reached by that fixture. A later restart/durability gate remains separate. This refusal result has not exercised fleet loading, writer locking, store initialization, socket binding, model work, or any device action.

The later daemon stage should reuse the original FleetRegistry/Supervisor fixture after binding it to the actual final source. The existing `tests/integration/hepta/run_original_agentd.py` remains pinned to historical `f8c9419`; this new control gate does not upgrade that historical execution to the new source combination.


### Follow-up: repaired initial read-only ext2 atime

The [2026-10-22 ext2 follow-up](../../../results/integration/2026-10-22-ext2-rdonly/README.md) separately qualifies source `9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd`, tree `eeae4dc1ef546d408b55c98310e99e3156f08207`, and ordinary kernel SHA256 `8bda1c4876cbfbca0c441adb2d3ac4a91c4b3ff2e9faadedcb3d43503a0b6c09`. Its retained runner changes only the three kernel identity constants and one diagnostic string; the frozen original Agentd ELF, manifest, dependency closure and oracle are unchanged. The complete new serial has zero Write BIO, block/writeback errors or IoError, with the original sync/reboot and child1/QEMU33 result.

The original runner and first-run records in this module retain their original pin and observed errors. Use the follow-up packet's reviewed runner and explicit new kernel identity to reproduce the repaired run; do not silently substitute a kernel in this frozen profile. The repair concerns automatic atime on initially filesystem-wide read-only ext2, not full VFS/virtio/remount semantics. It still stops at configuration refusal and does not start the original daemon, async runtime or owner.
