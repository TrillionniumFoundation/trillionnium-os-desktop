# Original owner probe: real Cargo prerequisite evidence

**Completed results: real Rust 1.95 Cargo metadata resolved the external probe
against the unchanged original Hepta owner libraries, its resolved lock passed
the original-lock identity/checksum subset check, and the actual probe passed
`cargo check` against that original graph. A subsequent original Agentd
`cargo check`, including its App Server graph, also passed.** Final executable
linking and original daemon launch remain
**`not_run`** in the recorded results. No fixture, extracted DTO, replacement
owner, model turn or device effect is presented as original-process acceptance.

The original source is fixed at
[`f8c9419df6ddeb36ff8b522a50219981fb8d9345`](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/f8c9419df6ddeb36ff8b522a50219981fb8d9345),
tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`, with original Cargo.lock SHA256
`8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`.
The successful resolution receipt records the same clean source before and
after the actual Cargo command.

## Attempts and qualification

All times are UTC on 2026-10-17. Failed attempts remain separate and unedited.

| Recorded attempt | Time | Outcome and scope |
| --- | --- | --- |
| [Toolchain bootstrap](original-r4-bootstrap.json) | 12:11:26–12:11:34 | Official Rustup `toolchain install 1.95.0 --profile minimal` exited 0 in the new isolated temporary environment; `original_agentd_run` is false |
| [First metadata attempt](original-r4-probe-resolution/receipt.json) | 12:26:05 | Cargo exit 101; [stderr](original-r4-probe-resolution/cargo-metadata.stderr.log) says `rustc -vV` was never executed because the command could not be found; stdout is the preserved empty file |
| [Corrected metadata attempt](original-r4-probe-resolution-02/receipt.json) | 12:26:38–12:26:54 | Cargo exit 0; 733 metadata packages and 733 resolve nodes; lock subset check passed; original source and lock unchanged |
| [First compile-check wrapper](original-r4-probe-check-01/receipt.json) | 12:30:05–12:30:06 | Prerequisite `AssertionError` before any Cargo check command or resource sample was recorded; no Rust compile result |
| [Corrected compiler check](original-r4-probe-check-02/receipt.json) | 12:31:09–12:36:39 | Actual Rust 1.95 `cargo check` exited 0; [raw log](original-r4-probe-check-02/cargo-check.log) ends `Finished dev-small ... in 5m 28s`; original source and resolved lock unchanged |
| [Original Agentd compiler check](original-r4-agentd-check-01/receipt.json) | 12:39:47–12:46:37 | Actual original Agentd bin selection passed `cargo check --no-default-features`; exit 0 and [raw log](original-r4-agentd-check-01/cargo-check.log) reports 6m 48s; final link/runtime both `not_run` |

The first compile wrapper failure was reported by its executor as an ambiguous
CMake wheel selector matching two legitimate manylinux distributions. The raw
receipt retains the empty `AssertionError` detail; that explanation is an
execution diagnosis, not a Cargo compiler message or a dependency-build
failure. The corrected wrapper's separate receipt and log preserve its later
actual compiler-check pass without overwriting the earlier prerequisite failure.

The toolchain bootstrap receipt retains its original temporary log path. That
Rustup installation log is not included in this archive; the receipt proves
the recorded installation result, not an independent binary provenance audit.

## What the successful metadata run proves

The [generated manifest](original-r4-probe-resolution-02/generated-Cargo.toml)
selects the original `hepta-contracts`, `hepta-fleet`, `hepta-paths`, and
`hepta-supervisor` libraries, with Supervisor default features disabled. It
preserves explicit resolver 2, the original dev/dev-small profiles, and rebased
original patches. The original workspace lock was copied as a seed into this
separate external root. Cargo then performed real resolution, and the gate's
actual lock check accepted the resulting shared dependency identities and
checksums. Only the new `hepta-original-observer-probe` package may be absent
from the original lock.

The command is retained as an argument array in the receipt. It used
`rustup run 1.95.0 cargo metadata --format-version 1 --manifest-path ...` and did
not specify `--filter-platform`. Therefore **733 describes that external
probe's metadata result**, not the minimal Agentd graph, compiled Rust units,
Linux-only link inputs, or an established memory/disk lower bound. The probe
uses the original owner libraries, but its graph does not build the Agentd
executable or exercise the process assertions.

The [resolved lock](original-r4-probe-resolution-02/resolved-Cargo.lock) has
SHA256 `9d1de5fab85aa6400a1d178e1791b3b01453b1b2b37e2b986bbe97cad55ceec1`.
The receipt observed filesystem free space changing from 4,612,005,888 to
3,539,832,832 bytes during this attempt. These are filesystem observations,
not a measured complete build footprint or guaranteed compiler allowance.

## What the successful compiler check proves

The actual command, including paths, is in
[original-r4-probe-check-02/receipt.json](original-r4-probe-check-02/receipt.json):

```sh
rustup run 1.95.0 cargo check --locked --profile dev-small \
  --manifest-path /absolute/generated-probe/Cargo.toml -j1
```

It used the already resolved probe root and warm target from the earlier
metadata attempt. The original Supervisor/Fleet/Contracts/Paths libraries and
the exact external probe source passed the real compiler check. The resolved
lock hash was identical before and after, and the original checkout, tree and
lock were clean and unchanged. The receipt also records the selected CMake
3.28.3 distribution URL, size, SHA256 and actual version output.

The raw log retains the unused-patch warnings and five warnings from the
unchanged original Supervisor library. No source was rewritten to remove them.
This result confirms the real probe's public API usage. `cargo check` does not
qualify the final linked probe or Agentd executable, an actual owner lifecycle
transition, daemon observation, Session connection or model/device effects.

The narrow wrapper had a 900-second deadline and a 700 MiB temporary-filesystem
reserve; it did not execute the full Agentd gate with a reduced threshold.
Its 330 resource samples report whole-cgroup `memory.current` and accumulated
`memory.peak`, not this compiler process's peak memory. The latter can include
activity before the command. The minimum observed filesystem free space was
2,553,098,240 bytes. The warm cache, sampled filesystem values and shared cgroup
counters cannot establish a cold original Agentd build/link minimum.

## What the successful original Agentd check proves

This later command ran against the original workspace and original lock, with
the unchanged real Agentd bin selection:

```sh
rustup run 1.95.0 cargo check --locked --profile dev-small \
  --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1
```

The [receipt](original-r4-agentd-check-01/receipt.json) records exit 0 and the
same original commit, tree and Cargo.lock hash before and afterward. The
[raw log](original-r4-agentd-check-01/cargo-check.log) includes original
`codex-app-server`, `codex-app-server-client` and `codex-hepta-agentd` checking,
retains the original warnings, and reports `Finished ... in 6m 48s`. This is a
real check of the Agentd source graph, not the external probe alone. Its receipt
keeps `original_agentd_link` and `original_agentd_runtime` as `not_run`; no
completed runnable binary, private Agentd launch or process observation is
qualified by it.

The target and dependencies were already warm from the successful probe check.
There are 410 resource samples, and final/minimum-observed temporary filesystem
free space is 1,234,903,040 bytes. `memory.current`, accumulated `memory.peak`
and the wrapper's per-sample estimate are observations of the shared cgroup.
They are not this compiler process's measured peak or a cold build requirement.
In particular, `maximum_observed_nonreclaimable_bytes = 7,516,192,768` is the
wrapper's configured 7 GiB stop threshold, not an observed maximum. The wrapper
also kept a 700 MiB filesystem reserve and 900-second deadline. These narrow
check bounds never replace the unchanged 8 GiB full build/runtime gate.

## Archive identity and exact bytes

[archive_manifest.json](archive_manifest.json) records the original absolute
path, original byte count/SHA256, archive byte count/SHA256, and encoding for
each copied or compressed payload. Receipts, stderr logs, the generated
manifest, and resolved lock were copied byte for byte. They retain original
paths and commit IDs rather than being rewritten for this evidence commit.

The successful [metadata stdout](original-r4-probe-resolution-02/cargo-metadata.stdout.json.gz)
is gzip-compressed with a zero timestamp and empty embedded filename. The
uncompressed bytes are unchanged:

| Representation | Bytes | SHA256 |
| --- | ---: | --- |
| Original Cargo stdout | 3,539,591 | `65475512fa779e7957e10d382b5dba6d72208bda57b1a860edd3cbdffe5ac916` |
| Stored lossless gzip | 267,413 | `da7ff31da997c0615156452b767ca39205eda61edb8d11599e7f59119c57d7a1` |

[source_binding.json](source_binding.json) separately records checks against
the exact local Git objects named by the execution receipts. Metadata ran with
desktop commit `160e11b1402a3ba6b91a50fa4c99f4a2fd100f18`; both compile-check
wrappers recorded `755c635a141739c292c7a5f9755d08361feff78e`. Their gate and
probe file bytes both match the evidence parent `017007369daf2c5067fe7a00507aa18e6a09f809`:

- `run_original_agentd.py`: SHA256
  `fff0b1228d6f02da4f5a02c3a1af3eb1e5f9aa55f5b7021b8db997934d5e5ceb`.
- `original_agentd_probe.rs`: SHA256
  `6620f550cbfa4fa9561df375d8bf52208bd342c8530319818cd4b5cf351c2beb`.

The Agentd check also recorded desktop helper revision `755c635a` and the same
gate SHA256. Its source-binding entry records that helper and the separate
fixed-original target; it does not treat the external probe as that Cargo
command's target.

This supplement binds source bytes; it does not alter the original receipts or
claim that every file in those desktop commits was executed. Stacked remote
integration can assign different commit IDs to identical source bytes. Match
the content hashes rather than substituting a later commit in an old receipt.

Check archive integrity from the repository root without invoking Cargo,
creating a process fixture, or launching a daemon:

```sh
python3 - <<'PY'
from pathlib import Path
import gzip, hashlib, json
root = Path('tests/integration/hepta/evidence/2026-10-17-original-probe')
manifest = json.loads((root / 'archive_manifest.json').read_bytes())
for entry in manifest['files']:
    data = (root / entry['path']).read_bytes()
    assert len(data) == entry['archived_bytes']
    assert hashlib.sha256(data).hexdigest() == entry['archived_sha256']
    raw = gzip.decompress(data) if entry['encoding'] == 'gzip' else data
    assert len(raw) == entry['original_bytes']
    assert hashlib.sha256(raw).hexdigest() == entry['original_sha256']
print('archive bytes verified; this does not run the qualification')
PY
```

## Remaining original-process gate

The standalone [original Agentd gate](../../ORIGINAL_AGENTD.md) still requires
its unchanged **8 GiB free-disk admission estimate**, fixed complete source,
both original and observer toolchains, native dependencies, locked builds and
actual process assertions. The narrow metadata/check environment does not
claim that full preflight passed or lower that threshold. Only a completed
`run_original_agentd.py --execute` report with both `status: passed` and
`live_agentd_acceptance: passed` can qualify original Agentd observation.

The archived earlier manifest and process-guard receipts remain unchanged.
This evidence addition performs no new Rust build, test rerun or daemon launch.
