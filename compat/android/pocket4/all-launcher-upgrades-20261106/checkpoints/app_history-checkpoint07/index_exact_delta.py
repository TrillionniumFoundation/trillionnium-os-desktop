#!/usr/bin/env python3
"""Index only this agent's reviewed public additions; no Git or device writes."""
import hashlib
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BASE_COMMIT = 'f491498a8a7bad7795c293f0e3f63e3ecdcaa383'
SOURCES = ('successor_qa/owned_postcondition_reconciler_r1', 'successor_qa/owned_flow_search_r1')
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def read(path):
    need(not path.is_symlink(), 'NO_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= 2 * 1024 * 1024,
             'BOUNDED_SINGLE_REGULAR_SOURCE')
        parts = []
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            parts.append(part)
            need(sum(map(len, parts)) <= 2 * 1024 * 1024, 'SOURCE_GREW')
        after, again = os.fstat(fd), path.stat(follow_symlinks=False)
        need(all(getattr(before, name) == getattr(after, name) == getattr(again, name) for name in STAT),
             'SOURCE_IDENTITY_CHANGED')
        raw = b''.join(parts)
        need(len(raw) == before.st_size, 'SOURCE_SIZE_CHANGED')
        raw.decode('utf-8', 'strict')
        return raw
    finally:
        os.close(fd)


def pin(path, raw):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save_once(path, value):
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            need(count > 0, 'WRITE_PROGRESS')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(read(path) == raw, 'INDEX_READBACK_CHANGED')
    return raw


def main():
    baseline_file = ROOT / 'checkpoints/checkpoint06-files.json'
    baseline_raw = read(baseline_file)
    baseline = json.loads(baseline_raw)
    known = {row['path']: row for row in baseline['files']}
    directory_file = HERE / 'baseline-owned-postcondition-directory.json'
    directory_raw = read(directory_file)
    directory = json.loads(directory_raw)
    need({row['name'] for row in directory} == {'read_fixed_two_steps.py', 'two-step-reader.process-request.json'},
         'EXACT_CHECKPOINT06_OWN_DIRECTORY_REQUIRED')
    inherited = []
    for row in directory:
        path = ROOT / 'successor_qa/owned_postcondition_reconciler_r1' / row['name']
        raw = read(path)
        need(row['size'] == len(raw) and row['sha'] == hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
             'CHECKPOINT06_INHERITED_BLOB_CHANGED')
        inherited.append(pin(path, raw))
    candidates = []
    for source in SOURCES:
        candidates.extend(path for path in (ROOT / source).rglob('*') if path.is_file() and
                          '__pycache__' not in path.parts and path.suffix != '.pyc')
    candidates.extend((ROOT / 'successor_audit_requests/current_services_r2.app-history-review.md',
                       directory_file, Path(__file__).resolve()))
    rows, originals = [], []
    for path in sorted(set(candidates)):
        raw = read(path)
        row = pin(path, raw)
        previous = known.get(row['path'])
        if previous is not None and (previous['bytes'], previous['sha256']) == (row['bytes'], row['sha256']):
            continue
        need(not any(word in path.name.lower() for word in ('private', 'window', 'bundle')),
             'PRIVATE_FILENAME_REQUIRES_SEPARATE_REVIEW')
        row['change'] = 'changed' if previous else 'added'
        if '/owned_flow_search_r1/' in '/' + row['path']:
            category = 'UNRUN_BLOCKED_PLAN_AND_SOURCE'
        elif '/actual/' in row['path'] or '/actual-binding-diff-r1/' in row['path'] or '/failed-publication-reader-actual-r1/' in row['path']:
            category = 'ORIGINAL_PUBLIC_EXECUTION_METADATA'
        elif path.suffix in ('.md', '.diff', '.patch'):
            category = 'SOURCE_REVIEW_OR_DESIGN_NOT_EXECUTION'
        else:
            category = 'PINNED_SOURCE_REQUEST_OR_PUBLIC_CONTROL_EVIDENCE'
        row['privacy'] = category
        rows.append(row)
        originals.append((path, raw))
    for path, raw in originals:
        need(read(path) == raw, 'DELTA_CHANGED_DURING_INDEX')
    result = {
        'schema': 'pocket4-app-history-checkpoint07-public-delta-v1',
        'repository': 'TrillionniumFoundation/trillionnium-os-desktop',
        'base_commit': BASE_COMMIT,
        'base_tree': 'dc9777906557066f2da349bd61290552257c2532',
        'repository_prefix': 'compat/android/pocket4/all-launcher-upgrades-20261106/',
        'files': rows, 'file_count': len(rows), 'total_bytes': sum(row['bytes'] for row in rows),
        'baseline_manifest': pin(baseline_file, baseline_raw),
        'baseline_directory_actual_Git_GET': pin(directory_file, directory_raw),
        'unchanged_inherited_files': inherited,
        'complete_original_file_bytes_preserved': True,
        'json_execution_records_rewritten': False,
        'Git_written_by_this_program': False,
        'Main_actions_by_this_program': 0,
        'production_ready_apps': 0, 'old_product_deleted_bytes': 0,
        'privacy_review': {
            'included': ['exact source, source diffs and reproducible process requests',
                         'original durable start/read/terminal and stdout/stderr containing execution metadata only',
                         'namespace observation-time diffs, file/command hashes and descriptor closure',
                         'selected public resource IDs, package/activity/window token and task/helper identity summaries'],
            'not_copied': ['remote 177-file original UI evidence bundle',
                           'remote 26-file failed-publication private bundle',
                           'original dumpsys window text, screenshots, UI node trees or private business data',
                           'APK content, signing private keys, pycache or unrelated source trees'],
            'historical_node_metadata': 'Only node/tree/window hashes and a structural node path occur in verifier metadata; no original node record or tree is included.',
            'actual_r1_failure_and_r2_failure_preserved': True,
            'search_plan_status': 'UNRUN_BLOCKED_AFTER_CURRENT_CONTEXT_PUBLICATION_FAILED',
            'historical_reconciliation_design_status': 'DESIGN_ONLY_NO_NEW_PRODUCER_OR_PUBLICATION'
        },
        'actual_outcomes': [
            {'job_id': '1a1b1df441d-fc05-7b41', 'outcome': 'host-only r1 binding equality rejection; preserved'},
            {'job_id': '1a1b1e2aaa2-fc05-7b54', 'outcome': 'readonly exact binding diff succeeded; only five nsfs observation mtimes differ'},
            {'job_id': '1a1b1ed877a-fc05-7b8d', 'outcome': 'host-only r2 full 177-file verification succeeded; no publication'},
            {'job_id': '1a1b1f2e015-fc05-7ba9', 'outcome': 'current-context publisher rejected foreground before publication; preserved'},
            {'job_id': '1a1b1fcedab-fc05-7be7', 'outcome': 'fixed 26-file host reader succeeded; no Main commands'},
            {'job_id': '1a1b206d887-fc05-7c16', 'outcome': 'independent current readonly foreground observation succeeded; IHG foreground, Beike task/helper unchanged'}
        ]
    }
    output = HERE / 'APP_HISTORY_CHECKPOINT07_DELTA.json'
    raw = save_once(output, result)
    print(json.dumps({'manifest': pin(output, raw), 'files': len(rows), 'total_bytes': result['total_bytes'],
                      'Git_writes': 0, 'Main_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
