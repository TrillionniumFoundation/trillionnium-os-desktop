# Exact kernel configuration binding repair

This packet retains the original failed binding and the successful independent
binding for Linux `6.18.64-p4ctx6182`. It corrects one configuration comparison:
`CONFIG_MTD_NAND_DISKONCHIP_PROBE_ADDRESS=0` becomes `#define ... 0x0` under
the actual Linux Kconfig HEX writer. All 10,145 generated CONFIG macros are
still compared; strings, other numeric types, symbol sets and duplicate checks
are unchanged.

The candidate first reads the original complete full-source manifest and the
exact Kconfig type definition and C writer. Both complete semantic source files
are pinned by bytes, SHA-256 and original F9. Only this proven HEX symbol gets
the same missing-prefix transformation as `print_symbol_for_c`. The raw config,
header, source and their original hashes are unchanged. Twelve source controls
reproduce the original failure, compare the complete real config/header pair,
and reject value changes, quoted values, unproven numeric normalization,
missing/extra/duplicate symbols, and changed semantic source inputs.

## Actual execution

The independently reviewed candidate was staged as ordinary `qq` into a new
private directory on `ai395`. The four staged files were independently read
back in full. The original failed directory and its receipts were retained.

The one authorized manager invocation completed in durable job
`1a1f3241531-ffbe-ca5` with exit 0. Its worker spent 60.227 seconds and read
104,872 files / 11,723,017,383 bytes. The complete source membership, nine kernel
artifacts and all 6,797 built and staged modules retained their checked input
identities. The actual worker and manager recorded successful final bookends,
PIDFD wait/reap, unit/cgroup retirement and reacquisition/release of both
original serials. The later independent read-only observation confirmed
retirement and unchanged historical failure receipts.

`execution/HELD-BINDING.json`, `BINDING-RESULT.json`, and `BINDING-TERMINAL.json`
are exact original JSON bytes, including integer nanosecond identities. Their
SHA-256 values are respectively `b3c406e7cab11fc9eba2a213880e0a615eaaaab36b59f72c8095bb62e7bff9ea`,
`fa19db074891780c2245de844ed028b5e7c27172533157e7f79806442eb4d41e`, and
`62cfa4afef97c6c9adca17d0d5169225cf42bd6e7906d4a76bd754688a903fd0`.

The actual output remains `HELD_COMPLETE_FULL_BOUND_VM_NOT_AUTHORIZED`.
No compiler or VM was invoked. This repaired metadata prerequisite grants no
native-exit ABI, provider, Android runtime, or production qualification.
`FROZEN-INPUT-MANIFEST.json` and `STAGED-INPUTS.json` remain earlier preparation
records with their original non-execution fields; the subsequent execution
records do not rewrite that history.

## Offline source replay

Run from any checkout:

```sh
python3 -I -B compat/android/pocket4/kernel-native-exit-config-binding-20261119/source_replay.py
```

The replay verifies the complete file inventory, exact original evidence bytes,
source-to-execution pins, recorded complete binding scope, resource/retirement
facts, and all twelve source controls. It opens only this packet and launches
only its source test file. It does not rerun the 11.72 GB host binding, read any
referenced host path, acquire a serial, invoke systemd or a compiler, start a VM,
or grant live custody. No private signing-key bodies are included.

## Subsequent work

`VM-NEXT-PLAN.md` describes the unexecuted next steps. The old 160 active plus
100 inactive ABI cases must be run on this new kernel in a separately reviewed
deployment. They do not qualify the new native-exit interface. The preserved
32-row native-exit catalog remains `NOT_IMPLEMENTED_NOT_RUN` throughout.
