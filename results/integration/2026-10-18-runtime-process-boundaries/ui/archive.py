#!/usr/bin/env python3
"""Package existing R9 UI attempts without running tests or changing raw receipts."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

BASE = Path(__file__).resolve().parent
STAGE = BASE / 'archive-stage'
ATTEMPTS = {
    'red-01': (101, 'Actual false-freshness regression: one passed, one failed.'),
    'green-01': (0, 'Initial implementation: three matching focused tests passed.'),
    'test-01': (101, 'Compilation stopped at the missing new field in an existing core cfg(test) fixture; no workspace tests executed.'),
    'test-02': (0, 'Initial full workspace: 137 passed, two real-font tests ignored.'),
    'fmt-01': (0, 'Initial formatting check passed.'),
    'clippy-01': (101, 'Strict large_enum_variant rejected the enlarged inline optional clock; not waived.'),
    'test-03': (0, 'Final boxed-clock full workspace: 137 passed, two real-font tests ignored.'),
    'fmt-02': (0, 'Final formatting check passed.'),
    'clippy-02': (0, 'Final workspace/all-target strict Clippy passed.'),
    'build-01': (0, 'Four production bins built; independently inventoried as ELF64 x86-64.'),
}


def identity(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def read_json(path):
    return json.loads(path.read_text())


def main():
    review = Path(sys.argv[1])
    assert review.is_file()
    STAGE.mkdir()
    compressed = []
    snapshot_bindings = []
    attempts = []

    def copy(source, relative):
        destination = STAGE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        assert destination.read_bytes() == source.read_bytes()

    def compress(source, relative):
        raw = source.read_bytes()
        stored = gzip.compress(raw, compresslevel=9, mtime=0)
        assert gzip.decompress(stored) == raw
        destination = STAGE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(stored)
        compressed.append({'original_path': str(source), 'raw': identity(raw),
                           'stored_path': relative, 'stored': identity(stored),
                           'encoding': 'gzip, mtime=0', 'decompressed_byte_equal': True})

    for label, (expected_exit, interpretation) in ATTEMPTS.items():
        attempt = BASE / label
        receipt = read_json(attempt / 'receipt.json')
        assert receipt['exit_code'] == expected_exit and receipt['source_equal'] is True
        assert read_json(attempt / 'source-before.json') == read_json(attempt / 'source-after.json')
        raw = (attempt / 'stdout-stderr.log').read_bytes()
        assert identity(raw) == {'sha256': receipt['log_sha256'], 'bytes': receipt['log_bytes']}
        for name in ['receipt.json', 'launch.json', 'source-before.json', 'source-after.json']:
            copy(attempt / name, f'attempts/{label}/{name}')
        for name in ['preserved-test-elf.json', 'test-counts.json', 'production-binaries.json']:
            if (attempt / name).is_file():
                copy(attempt / name, f'attempts/{label}/{name}')
        compress(attempt / 'stdout-stderr.log', f'attempts/{label}/stdout-stderr.log.gz')
        compress(attempt / 'source.patch', f'attempts/{label}/source.patch.gz')
        for source in sorted((attempt / 'source').rglob('*.rs')):
            raw = source.read_bytes()
            sha = identity(raw)['sha256']
            relative = f'source-snapshots/{sha}.rs'
            destination = STAGE / relative
            if not destination.exists():
                copy(source, relative)
            assert destination.read_bytes() == raw
            snapshot_bindings.append({'attempt': label,
                                      'original_source_path': source.relative_to(attempt / 'source').as_posix(),
                                      'stored_path': relative, **identity(raw)})
        attempts.append({'label': label, 'exit_code': expected_exit,
                         'interpretation': interpretation, 'receipt_path': f'attempts/{label}/receipt.json'})

    for name in ['run.py', 'collect_final.py', 'archive.py', 'final-source.json']:
        copy(BASE / name, name)
    compress(BASE / 'final-source.patch', 'final-source.patch.gz')
    copy(review, 'independent-review.json')
    final = read_json(BASE / 'final-source.json')
    bins = read_json(BASE / 'build-01/production-binaries.json')['binaries']
    bin_rows = '\n'.join(f"| `{name}` | {entry['bytes']:,} | `{entry['sha256']}` |"
                         for name, entry in bins.items())
    readme = f'''# R9 Runtime total-age correction — source-bound Rust evidence

The final Runtime freshness implementation passed **137 Rust tests**, with
**two real-host-font tests ignored**, strict all-target Clippy, formatting,
and the locked build of all four production UI executables. The failure
baseline and intermediate compile/lint failures remain in this archive.

## Proven defect and correction

The deterministic negative test sends a Snapshot through the actual Desktop
response queue and renders the actual egui status. The successful runtime
sample has Session age **6,000 ms**, IPC round trip **20 ms**, and response
queue delay **1,991 ms**: its conservative monotonic total is **8,011 ms**.
Wall-clock rollback makes the same sample appear only 6,000 ms old. RED
actually rendered `Hepta: OBSERVED · READ ONLY`. The exact 7,000 ms control
passed in the same RED command; the regression failed. This proves the
visible predicate accepted an old sample, without a compositor or Agentd
execution claim.

Session now times the complete successful runtime read from its start and
publishes a separate nonzero successful-read sequence and upward-rounded age.
Failed reads and independent known-run reads do not renew that sample. Shell
binds it to Session, AgentId, spawn and PID, then combines the source age,
full IPC round trip and post-receipt queue age. Same-source repeated samples
retain the maximum advancing bound, without rejuvenation or repeated RTT
addition. A same-Session frame missing history cannot erase that bound.
Invalid or absent ages fail closed. The visible and runtime-layout predicates
share the same clock, while the run projection remains independently sampled.

Strict Clippy exposed an enlarged Response variant after adding the inline
optional clock. The final implementation boxes only that optional metadata;
its JSON object and timing semantics are unchanged. No lint was suppressed.
New Runtime snapshots add clock metadata even without a known run: deploy
matching Session, Shell and ctl versions. New Shell treats old missing-clock
history as unknown; old strict decoders reject the new field.

## Executed source identity

The initial RED command executed at HEAD
`777196f826f45183f43a6c74c630f70df4adf4cc` plus its retained four-file source
patch. The parent subsequently committed that exact RED scaffold/tests as
`00796f6f6e10027e12b83d37d9ab4b8ab913f72e`. This later commit was not the
HEAD recorded by the execution. Each attempt retains its original HEAD,
patch, per-file SHA-256, command, compiler identity and raw-log hash.

Final test-03, fmt-02, clippy-02 and build-01 all executed at HEAD
`{final['head_at_execution']}` plus the final working source, with identical
before/after source inventories. This is a candidate based on main f9e306f,
not a claim that 09cf was main. Their complete UI and observer source closure
SHA-256 is `{final['compiled_closure_sha256']}`.
`final-source.json` separately binds the eight changed implementation/test/
documentation paths. A later integration or publication commit must keep its
own identity; these executions are not relabeled as that later HEAD.

The closure includes tracked UI sources/manifests/lock, the Session's
`services/hepta-os/src` path dependency and its two manifests, and the UDS
fixture JSON. Four original source-file snapshots from each attempt are
stored by content hash, with all original paths in `archive-manifest.json`.
The exact patches preserve the remaining changes against each recorded HEAD.

## Actual attempts

| Attempt | Actual outcome |
| --- | --- |
| red-01 | Exit 101; 1 passed / 1 failed. Actual false-fresh status at total age 8,011 ms. |
| green-01 | Exit 0; 3 matching focused tests passed, including the added independent-run case. |
| test-01 | Exit 101 before workspace tests: an existing core test fixture needed the newly optional field in its Rust struct literal. |
| test-02 | Exit 0; 137 passed / 2 ignored on the initial unboxed implementation. |
| fmt-01 | Exit 0 on the initial implementation. |
| clippy-01 | Exit 101: `large_enum_variant`; no suppression or widened public Response representation. |
| test-03 | Exit 0; 137 passed / 2 ignored on the final boxed implementation. |
| fmt-02 | Exit 0 on the same final source. |
| clippy-02 | Exit 0 with `--workspace --all-targets -- -D warnings` on the same final source. |
| build-01 | Exit 0; all four production bins on the same final source. |

All attempts have `source_equal: true`. A compile error is not reported as a
failed behavioral test, and the initial GREEN results are not substituted for
the final boxed-source results.

## Final counts, read from test-03

| Actual test binary | Passed | Ignored |
| --- | ---: | ---: |
| trill-app-window unit | 11 | 1 |
| trill-ctl unit | 2 | 0 |
| trill-session unit | 30 | 0 |
| hepta_observer integration | 2 | 0 |
| hepta_run integration | 4 | 0 |
| ipc_reconnect integration | 1 | 0 |
| trill-shell unit | 63 | 1 |
| trill-ui-core unit | 24 | 0 |
| trill-ui-core doc-tests | 0 | 0 |
| **Total** | **137** | **2** |

The two ignored cases require `TRILL_UI_TEST_CJK_FONT` selecting a real host
font; this R9 gate did not run them. The real Session executable with scripted
fixed-v2 UDS responses verifies the complete slow runtime read, independent
slow known-run read, null/missing-run semantics, old-spawn failure and two
later failed polls preserving the runtime sequence while its age advances.
Desktop/egui regressions also cover 7,000/7,001 boundaries, invalid ages,
rollback, Session/source changes, missing-history middle frames, sequence
regression and visible/layout agreement.

## Four production outputs

| Executable | Bytes | SHA-256 |
| --- | ---: | --- |
{bin_rows}

`attempts/build-01/production-binaries.json` records actual paths, ELF64
little-endian x86-64 headers, hashes, build-launch binding and source before/
after. `receipt.json.shell_executables` is the runner's inventory and may also
include the test executable; it is not a four-bin list. The actual final
Shell test ELF is separately identified by
`attempts/test-03/preserved-test-elf.json`. ELF bodies and Cargo caches are
excluded from this archive; RED, initial GREEN and final test ELF copies were
retained only in the original local attempt directories.

## Exact commands and environment

All commands ran from the repository root with the fixed private Rust 1.88
installation. `launch.json` contains the absolute Cargo path and tool hashes.

```sh
cargo test --manifest-path ui/Cargo.toml --locked -p trill-shell runtime_total_age_ -- --nocapture
cargo test --manifest-path ui/Cargo.toml --locked --workspace
cargo fmt --manifest-path ui/Cargo.toml --all -- --check
cargo clippy --manifest-path ui/Cargo.toml --locked --workspace --all-targets -- -D warnings
cargo build --manifest-path ui/Cargo.toml --locked --workspace --bins
```

Task-owned executable RAM paths were `CARGO_HOME=/dev/shm/trill-r9-cargo`
and `CARGO_TARGET_DIR=/dev/shm/trill-r9-target-ui`, with jobs 2,
`CARGO_PROFILE_DEV_DEBUG=0`, `CARGO_PROFILE_TEST_DEBUG=0`, and
`CARGO_INCREMENTAL=0`. The helper retains a 1,200-second owned-process-group
deadline. No timeout occurred in these attempts.

## Stored bytes and scope

Every raw stdout/stderr log and source patch is stored as gzip with mtime 0.
`archive-manifest.json` records each original raw SHA/byte length and its
stored path/SHA/byte length. Packaging verified every decompressed value
against the original bytes; original receipts and raw attempt files were
not edited. Source snapshots are exact, deduplicated text. `SHA256SUMS`
covers every stored file except itself. `independent-review.json` is a
separate read-only source/artifact review, not an extra test execution.

This package qualifies Rust behavior, typed Session IPC with a scripted peer,
egui drawing/layout predicates and native executable construction. It does
not contain a new original Agentd run, compositor pixels, model execution,
issuer admission or desktop/mobile device effects. Earlier original/native
evidence keeps its original source and binaries.
'''
    (STAGE / 'README.md').write_text(readme)
    payloads = {path.relative_to(STAGE).as_posix(): identity(path.read_bytes())
                for path in sorted(STAGE.rglob('*')) if path.is_file()}
    manifest = {'schema': 'r9_ui_runtime_total_age_archive_v1',
                'payload_files': payloads, 'payload_file_count': len(payloads),
                'published_file_count_including_manifest_and_sums': len(payloads) + 2,
                'compressed_storage': compressed,
                'source_snapshot_bindings': snapshot_bindings,
                'attempts': attempts,
                'scope': 'Stored archive payloads only; original raw attempts, executable copies and Cargo caches are not published.'}
    write_json(STAGE / 'archive-manifest.json', manifest)
    stored = {path.relative_to(STAGE).as_posix(): identity(path.read_bytes())
              for path in sorted(STAGE.rglob('*')) if path.is_file()}
    (STAGE / 'SHA256SUMS').write_text(''.join(f"{entry['sha256']}  {name}\n"
                                            for name, entry in stored.items()))
    final_stored = {path.relative_to(STAGE).as_posix(): identity(path.read_bytes())
                    for path in sorted(STAGE.rglob('*')) if path.is_file()}
    assert len(final_stored) == manifest['published_file_count_including_manifest_and_sums']
    for item in compressed:
        raw = gzip.decompress((STAGE / item['stored_path']).read_bytes())
        assert identity(raw) == item['raw']
        assert raw == Path(item['original_path']).read_bytes()
    canonical = json.dumps(final_stored, sort_keys=True, separators=(',', ':')).encode()
    seal = {'stage': str(STAGE), 'files': len(final_stored),
            'bytes': sum(item['bytes'] for item in final_stored.values()),
            'stored_inventory_sha256': identity(canonical)['sha256'],
            'sha256sums': final_stored['SHA256SUMS'],
            'manifest': final_stored['archive-manifest.json'],
            'compressed_artifacts': len(compressed),
            'decompressed_all_equal_to_original': True,
            'excluded': ['ELF bodies', 'Cargo cache', 'raw duplicate logs and patches']}
    write_json(BASE / 'archive-seal.json', seal)
    print(json.dumps(seal, sort_keys=True))


if __name__ == '__main__':
    main()
