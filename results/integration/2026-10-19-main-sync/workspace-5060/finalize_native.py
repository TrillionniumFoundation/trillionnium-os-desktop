#!/usr/bin/env python3
"""Seal the two current native PNGs, source bindings and preserved environment failure."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent


def identity(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    capture = BASE / 'capture-02'
    outer = read(capture / 'receipt.json')
    inner = read(capture / 'inside/capture-receipt.json')
    binding = read(capture / 'inside/input-binding.json')
    assert outer['status'] == 'completed' and outer['exit_code'] == 0
    assert all(outer[key] is True for key in ['product_source_unchanged', 'harness_source_unchanged', 'executable_bytes_unchanged'])
    assert outer['namespace_guard_armed_after'] is False
    assert inner['status'] == 'completed_native_capture_requires_independent_visual_review'
    assert len(inner['screenshots']) == 2 and len(inner['actions']) == 3
    assert len(inner['cleanup']) == 3 and all(row['guard_armed_after'] is False for row in inner['cleanup'])
    assert all(not row['snapshot']['tasks'] for row in inner['snapshot_observations'])
    assert all(row['snapshot']['session_instance'] == inner['session_a']['instance'] for row in inner['snapshot_observations'])
    assert all(row['snapshot']['hepta']['connection'] == 'not_configured' for row in inner['snapshot_observations'])
    for row in inner['screenshots']:
        raw = (capture / 'inside' / row['file']).read_bytes()
        assert identity(raw) == {'sha256': row['sha256'], 'bytes': row['bytes']}
        assert raw[:8] == b'\x89PNG\r\n\x1a\n'
        assert row['width'] == 1440 and row['height'] == 1000 and row['shell'] == inner['shell']

    spec = importlib.util.spec_from_file_location('r9_native_bound_helper', BASE / 'harness02/tests/ui/probe-chat-workspace.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    post_source = helper.sources(BASE.parent / 'repo')
    assert post_source == binding['source']
    post_bins = helper.binaries(BASE / 'binaries')
    assert post_bins == binding['binaries']
    write(BASE / 'post-cleanup-source-inventory.json', {
        'observed_unix_ms': time.time_ns() // 1_000_000,
        'source': post_source, 'binaries': post_bins,
        'source_equals_capture_before': True, 'binaries_equal_capture_before': True,
        'scope': 'Additional actual post-cleanup read. The original outer receipt independently compared source and binaries at namespace completion.'})
    first = read(BASE / 'capture-01/receipt.json')
    assert first['status'] == 'failed' and first['exit_code'] == 1
    prior = read(BASE / 'capture-01/inside/capture-receipt.json')
    assert not prior['screenshots'] and not prior['snapshot_observations']
    assert [x['label'] for x in prior['cleanup']] == ['Xvfb']
    assert prior['cleanup'][0]['guard_armed_after'] is False

    reviewed = [
        {'file': 'initial.png', 'visible_page': 'Personal / Chat',
         'observed': ['Workspace / Chat is the selected main route.',
                      'Local draft composer, save/export/restore controls and LOCAL DRAFT / NOT SUBMITTED label are visible.',
                      'Tasks, Context and Console are tabs in the right workspace pane; Tasks is selected.',
                      'The actual empty host-task state is visible; no task or AI result is fabricated.',
                      'Selected Message, Notes, Calculator and placeholder Chinese glyphs are visible with the explicitly loaded font.']},
        {'file': 'action-002-screenshot.png', 'visible_page': 'Personal / Chat with Console tab',
         'observed': ['Console is selected inside the same right workspace pane.',
                      'The left chat composer and main Workspace / Chat route remain visible.',
                      'Console / Host observations is read-only and displays the actual Session instance.',
                      'The host process and local notice sections show their empty states.',
                      'No red First use / Second use ScrollArea ID warning is visible in this captured frame.']},
    ]
    for item, png in zip(reviewed, inner['screenshots']):
        assert item['file'] == png['file']
        item.update(sha256=png['sha256'], bytes=png['bytes'])
    write(BASE / 'a10-visual-review.json', {
        'reviewer': 'A10', 'method': 'Each original PNG opened with view_image and inspected visually after actual XGetImage capture.',
        'status': 'passed_within_current_two_page_scope', 'reviewed': reviewed,
        'session': inner['session_a'], 'shell': inner['shell'],
        'outer_receipt': identity((capture / 'receipt.json').read_bytes()),
        'inner_receipt': identity((capture / 'inside/capture-receipt.json').read_bytes()),
        'actual_input': [x['request'] for x in inner['actions']],
        'frame_geometry': 'Unedited 1440x1000 root framebuffer; the 1360x840 Rust window and remaining black area are preserved.',
        'limitations': ['Current R9 two-page rendering only, not restored R7 captures.',
                        'No draft save, host-task lifecycle, Session replacement, independent scrolling or Runtime age pixel test in this slice.',
                        'No original Agentd, issuer, model, device, physical input, IME, GPU or mobile qualification.',
                        'Visible selected Chinese glyphs under this font configuration do not upgrade the two ignored font tests or prior IME failures.']})
    root_review = BASE / 'root-visual-review.json'
    assert identity(root_review.read_bytes())['sha256'] == '624f55d05b483212b842f845a55636e11eb19efdebf7ea5d4f54eeab33a1e997'

    stage = BASE / 'archive-stage'
    stage.mkdir()
    storage = []
    files = []
    for directory in ['capture-01', 'capture-02', 'harness-origin', 'harness', 'harness02', 'receipts']:
        for path in (BASE / directory).rglob('*'):
            rel = path.relative_to(BASE)
            if '__pycache__' in rel.parts or 'cache' in rel.parts or 'runtime' in rel.parts:
                continue
            if path.is_file() and not path.is_symlink():
                files.append(path)
    files.extend(BASE / name for name in ['prepare.py', 'derive_harness.py', 'restore_missing_runtime.py',
                                         'finalize_native.py', 'harness.patch', 'harness-02.patch',
                                         'harness-derivation.json', 'harness-derivation-02.json',
                                         'post-cleanup-source-inventory.json', 'a10-visual-review.json',
                                         'root-visual-review.json'])
    for source in sorted(files):
        relative = source.relative_to(BASE).as_posix()
        raw = source.read_bytes()
        if source.suffix in ['.log', '.patch']:
            kind = 'log' if source.suffix == '.log' else 'patch'
            stored_path = f'content/{identity(raw)["sha256"]}.{kind}.gz'
            encoded = gzip.compress(raw, compresslevel=9, mtime=0)
            assert gzip.decompress(encoded) == raw
        else:
            stored_path, encoded = relative, raw
        destination = stage / stored_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            assert destination.read_bytes() == encoded
        else:
            destination.write_bytes(encoded)
        storage.append({'original_path': relative, 'raw': identity(raw),
                        'stored_path': stored_path, 'stored': identity(encoded),
                        'encoding': 'gzip, mtime=0' if source.suffix in ['.log', '.patch'] else 'identity'})
    build_dir = BASE.parent / 'r9-ui-verification/build-01'
    for name in ['production-binaries.json', 'receipt.json', 'launch.json', 'source-before.json', 'source-after.json']:
        destination = stage / 'original-r9-build' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(build_dir / name, destination)

    (stage / 'README.md').write_text('''# Current R9 native Workspace / Chat and embedded Console

This package contains two new, unedited native PNGs from the current R9 Rust
Shell, one empty owned Session and a private Xvfb display. The first image is
the default Personal / Chat workspace; one actual XTEST primary-pointer click
selects Console within the right workspace pane for the second image. A10 and
the root reviewer each opened and inspected both PNGs.

## Outcome and exact scope

`capture-02/receipt.json` completed with exit 0. Source, harness and all four
ELF hashes remained unchanged. Actual namespace identities were Session PID
7 / instance `4673be60fa79a390b65a827836b94d16`, Shell PID 10 / XID 4194307,
and Xvfb PID 3. The outer namespace leader was PID 511394. All three long-lived
owned groups and the outer leader were reaped; their guards were disarmed.
Short command groups use the same anchored wait/reap path in the retained
harness. The actual Snapshot observations all retain the same Session, empty
host tasks and unconfigured Hepta.

| Original PNG | Bytes | SHA-256 |
| --- | ---: | --- |
| `capture-02/inside/initial.png` | 87,112 | `418ba2bdfd86234e80bb1376c82a6d48553bea538c0e565f4a3572105b1fbbad` |
| `capture-02/inside/action-002-screenshot.png` | 101,494 | `2d64764cc883803bb2c908c4f1c1a3989e7a681e77e8e60e733e7ed5d100687f` |

Both files preserve the complete 1440x1000 root framebuffer, including the
1360x840 Rust window and the remaining black area. There was no cropping,
repainting or reconstruction. The Console frame shows the local draft area
alongside the selected Console tab, its read-only host observation labels,
the real Session instance, and empty process/notice lists. No red ScrollArea
ID conflict text is visible in that frame. Selected Chinese labels and the
placeholder are readable under this explicitly loaded Noto configuration.

This qualifies current two-page rendering in this private X11 setup. It does
not restore R7's lost original pictures or transfer qualification to other
source commits. There was no draft save, task lifecycle, Session replacement,
independent scroll or Runtime-age pixel exercise. It does not upgrade the two
ignored font tests, old IME failures, an unexecuted CI X11 branch, physical
input, GPU, mobile, original Agentd, issuer, model or device behavior.

## Source and unchanged build reuse

The executed current source was clean local commit
`2bc512a445f30a53ac4c579fece1ff91c03c8741`, tree
`ae588699126910065c16b77d83f3ef20b53509f2`. Its compiled UI/observer files exactly
match the earlier R9 build closure
`d720db71872f8c263b73ab3b5ad9702a856898a32b7cfde312cfe805156d0fe0`.
No executable was rebuilt. All four production ELF bodies were copied from
the executable RAM view after matching their original SHA and byte lengths,
then rechecked before and after capture. The normal sandbox's earlier RAM
FileNotFound observation was a mount-view difference, not missing binaries.

`original-r9-build/` preserves the actual original build receipt, launch,
source inventories and four-bin identities. Its recorded HEAD remains 09cf
plus the executed source patch; it is not relabeled as the capture commit.
`capture-02/inside/input-binding.json` records the current full source view,
the original compiled closure, exact ELF identities, source correspondence,
font and environment hashes. `post-cleanup-source-inventory.json` is a later
actual source/ELF read which matches the capture's before inventory; the
outer receipt independently checked equality at namespace completion.

## Preserved environment failure and minimal recovery

Attempt `capture-01` started Xvfb but could not load `xdpyinfo`: the first
private runtime set lacked `libXtst.so.6` and `libXxf86dga.so.1`. It reached
its bounded readiness limit, exited 1, produced no PNG and started no Session
or Shell. Xvfb and the outer namespace were reaped; source/harness/ELF inputs
were unchanged. These raw receipts and all command outputs are retained.

The restoration scripts downloaded fixed Ubuntu package URLs, checked SHA
and lengths, and used `dpkg-deb --extract` only into this task's private
sysroot. No system package installation occurred. Environment 01 contains
11 packages. Environment 02 adds only the two loader gaps actually observed
and constructs a new `view03/usr`; the first receipt/view/harness remain
separate. Link diagnostics then found no unresolved libraries for Xvfb,
xdpyinfo, xdotool and xprop. The actual second launch is the display proof.

The font is `NotoSansCJK-Regular.ttc`, 19,484,784 bytes, SHA-256
`b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`.
The real Shell stderr records the explicit font load and selected face.
Xvfb's retained XKEYBOARD warnings report unsupported key names and state
that they are nonfatal; they are not hidden or upgraded into IME coverage.

## Harness and storage

The tracked `tests/ui/probe-chat-workspace.py` requires the broader R7
31-action/task/export/replacement scenario. The task-private derivative
keeps the actual Session, window/PID checks, XGetImage capture, parent-death
wrapper and anchored process-group cleanup. It restricts input to click,
screenshot and finish; finish requires exactly two images, one unchanged
Session with no tasks and no Hepta configuration, and the same actual window.
The original source, both derivative versions, derivation scripts and exact
diffs are retained. Production source and the tracked harness were not edited.

All raw JSON/PNG and harness text are stored unchanged. Raw logs and patches
are losslessly gzip-compressed with mtime 0 and deduplicated by content hash;
`archive-manifest.json` maps every original filename to its raw SHA/length and
stored SHA/length. This retains each of the 100 identical failed readiness
command outputs without duplicating their bytes. Packaging verified every
decompression against the original file. `SHA256SUMS` covers every stored
file except itself. ELF bodies, Debian packages, sysroot/view symlinks,
sockets and caches are excluded; their needed provenance is retained.
''')
    payloads = {p.relative_to(stage).as_posix(): identity(p.read_bytes())
                for p in sorted(stage.rglob('*')) if p.is_file()}
    manifest = {'schema': 'r9_current_native_workspace_archive_v1', 'storage': storage,
                'payloads': payloads, 'published_file_count_including_manifest_and_sums': len(payloads) + 2,
                'scope': 'Two actual current PNGs plus the preserved setup failure; no ELF/package/cache bodies.'}
    write(stage / 'archive-manifest.json', manifest)
    payloads = {p.relative_to(stage).as_posix(): identity(p.read_bytes())
                for p in sorted(stage.rglob('*')) if p.is_file()}
    (stage / 'SHA256SUMS').write_text(''.join(f"{v['sha256']}  {k}\n" for k, v in payloads.items()))
    for entry in storage:
        raw = (stage / entry['stored_path']).read_bytes()
        if entry['encoding'].startswith('gzip'):
            raw = gzip.decompress(raw)
        assert identity(raw) == entry['raw'] and raw == (BASE / entry['original_path']).read_bytes()
    final = {p.relative_to(stage).as_posix(): identity(p.read_bytes())
             for p in sorted(stage.rglob('*')) if p.is_file()}
    canonical = json.dumps(final, sort_keys=True, separators=(',', ':')).encode()
    seal = {'files': len(final), 'bytes': sum(x['bytes'] for x in final.values()),
            'raw_file_bindings': len(storage), 'all_raw_bytes_verified': True,
            'sha256sums': final['SHA256SUMS'], 'manifest': final['archive-manifest.json'],
            'stored_inventory_sha256': identity(canonical)['sha256'], 'stage': str(stage)}
    write(BASE / 'archive-seal.json', seal)
    print(json.dumps(seal, sort_keys=True))


if __name__ == '__main__':
    main()
