#!/usr/bin/env python3
"""Stage only explicitly selected UTF-8 source/review/evidence; never write Git."""
from pathlib import Path
import hashlib
import json
import re
import stat

BASE = Path('/workspace/scratch/94990735b266')
OWN = BASE / 'android-cp06'
BILI = OWN / 'bilibili-preparation-01'
HERE = Path(__file__).resolve().parent
TREE = HERE / 'tree'
PARENT = 'bef03784ba3fb4948cef0b128092bda769a6364b'
ROWS = []
EXCLUDED = []


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def add(source, destination, state):
    source = Path(source)
    metadata = source.lstat()
    if not stat.S_ISREG(metadata.st_mode) or source.is_symlink():
        raise RuntimeError('not an ordinary selected source: ' + str(source))
    raw = source.read_bytes()
    text = raw.decode('utf-8', errors='strict')
    if '\x00' in text or raw.startswith((b'\x7fELF', b'PK\x03\x04', b'\x1f\x8b')):
        raise RuntimeError('binary payload: ' + str(source))
    if re.search(r'[A-Za-z0-9+/]{1024,}={0,2}', text):
        raise RuntimeError('encoded bulk payload: ' + str(source))
    if re.search(r'-----BEGIN (?:\w+ )?PRIVATE KEY-----', text):
        raise RuntimeError('private key payload: ' + str(source))
    if str(destination).startswith('/') or '..' in Path(destination).parts:
        raise RuntimeError('unsafe destination')
    target = TREE / destination
    if source.read_bytes() != raw:
        raise RuntimeError('source changed during selection')
    ROWS.append({'source_path': str(source), 'staged_path': str(target),
                 'publication_relative_path': 'android-acceptance/' + str(destination),
                 'bytes': len(raw), 'sha256': digest(raw), 'status': state})


def frozen(name, destination):
    root = BILI / name
    manifest = json.loads((root / 'source-manifest.json').read_text())
    files = manifest['files']
    if isinstance(files, list):
        files = {row['path']: row for row in files}
    selected = set(files) | {'source-manifest.json'}
    for path, row in files.items():
        raw = (root / path).read_bytes()
        if len(raw) != row['bytes'] or digest(raw) != row['sha256']:
            raise RuntimeError('frozen manifest mismatch: ' + str(root / path))
    observed = {str(path.relative_to(root)) for path in root.rglob('*')
                if path.is_file() and '__pycache__' not in path.parts}
    if observed != selected:
        raise RuntimeError('frozen closure differs: ' + str(root))
    for path in sorted(selected):
        add(root / path, Path(destination) / path, 'frozen_historical_bytes')


def named(root, names, destination, state):
    for name in names:
        add(root / name, Path(destination) / name, state)


def exclude(path, reason):
    path = Path(path)
    raw = path.read_bytes()
    EXCLUDED.append({'source_path': str(path), 'bytes': len(raw),
                     'sha256': digest(raw), 'reason': reason})


def main():
    named(HERE, ['README.md', 'assemble_allowlist.py', 'packaging01-failure.json', 'packaging02-failure.json'], '.', 'publication_recipe_and_scope_only')
    for name, destination in (
        ('transport-r2-freeze', 'bilibili/transport-r2'),
        ('transport-r3', 'bilibili/transport-r3'),
        ('recorder-held-r1-freeze-01', 'bilibili/recorder-held-r1'),
        ('recorder-held-r2-freeze-01', 'bilibili/recorder-held-r2'),
    ):
        frozen(name, destination)
    named(BILI, ['recorder-held-r1-freeze-01-receipt.json',
                 'recorder-held-r2-freeze-01.finalization.json'],
          'bilibili/freeze-receipts', 'frozen_historical_receipt')
    named(BILI / 'readonly-request-r2-01', [
        'coordinator.py', 'local-static-and-staging.json',
        'process-start-request.json', 'request-summary.json'],
        'bilibili/readonly-r2-request', 'submitted_original_once_request')
    device = BILI / 'readonly-device-r2-01'
    named(device, [
        'archive-readback-verified.json', 'collector.py', 'collector-start-request.json',
        'collector-start-tool-result.json',
        'collector-terminal-00.json', 'collector-report.json',
        'readback-validation.json', 'concise-original-failure.json',
        'runtime-terminal-00.json',
        'start-tool-result.json', 'upload-tool-result.json'],
        'bilibili/readonly-r2-failure', 'actual_original_FAIL_or_bounded_collection')
    for path in sorted((device / 'retained-files').rglob('*')):
        if path.is_file():
            add(path, Path('bilibili/readonly-r2-failure/retained-files') /
                path.relative_to(device / 'retained-files'), 'actual_original_FAIL_retained_text')
    named(BILI / 'bound-input-diagnostic-01', [
        'diagnose.py', 'process-start-request.json', 'analysis-and-request.json'],
        'bilibili/diagnostic-request', 'reviewed_request_NOT_SUBMITTED_at_snapshot')
    named(BILI / 'input-error-context-r3-work-01', [
        'source_contract.py', 'preimage_source_contract.py', 'control.py',
        'control.stdout.json', 'control.stderr', 'error-context.patch'],
        'bilibili/candidates/input-error-context-r3-01',
        'candidate_snapshot_NOT_a_complete_frozen_or_admitted_revision')

    factory = OWN / 'factory-v2-independent-review-01'
    for path in sorted(factory.iterdir()):
        if not path.is_file():
            continue
        if path.suffix in ('.py', '.json', '.cc', '.patch', '.stderr', '.stdout', '.jsonl'):
            add(path, Path('reviews/factory-v2') / path.name, 'actual_scoped_independent_review_or_control')
        else:
            exclude(path, 'compiled ELF control excluded; source and exact output are retained')
    build = BASE / 'native-new-env-01/host-fixture-build02/actual-handoff-01'
    named(build, ['stage_and_build02.py', 'build_fixture.py', 'build01-to-build02.patch'],
          'reviews/factory-v2/host-build02-reviewed-sources', 'reviewed_snapshot_build_NOT_EXECUTED_by_reviewer')
    peer = Path('/workspace/scratch/pocket4-lmkd-supervisor-r11-20261104-owned-01/reviews/bili-recorder-frontend-freeze01-review-01/report.json')
    add(peer, 'reviews/bili-frontend/inventory-scoped-review.json', 'independent_scoped_source_review_no_device_execution')
    root = BASE / 'root-cp07'
    named(root, [
        'bilibili-recorder-r2-root-source-review.json',
        'bilibili-three-input-diagnostic-root-review.json',
        'factory-v2-r2-root-source-review.json',
        'factory-receive-pidfd-local-01.json',
        'factory-child-output-bound-fixed-01.json',
        'factory-pidfd-original-pocket4-control-result.json'],
        'reviews/root-verbatim', 'parent_authored_source_review_or_actual_scoped_control_verbatim')
    for name in ('recorder-held-r1-freeze-01.tar.gz', 'recorder-held-r2-freeze-01.tar.gz'):
        exclude(BILI / name, 'binary transport archive excluded; exact UTF-8 payloads retained')
    exclude(BILI / 'readonly-request-r2-01/upload-request.json', 'contains base64 archive payload; source manifest and upload result retained')
    for name in ('archive-chunk-0.json', 'archive-chunk-1.json', 'collector-bundle-readback.json',
                 'retained-evidence.json.gz', 'retained-evidence.json', 'collector-report-readback.json',
                 'collector-read-00.json', 'runtime-read-00.json'):
        exclude(device / name, 'binary or encoded duplicate envelope excluded; bounded decoded text and validation retained')
    exclude(root / 'factory-pidfd-original-pocket4-control-01.py', 'encoded source deployment envelope excluded; original unencoded actual C++ control and parent device result retained')
    rows = sorted(ROWS, key=lambda row: row['publication_relative_path'])
    if len({row['publication_relative_path'] for row in rows}) != len(rows):
        raise RuntimeError('duplicate destination')
    manifest = {
        'schema': 1, 'kind': 'UTF8_PUBLICATION_ALLOWLIST_ONLY',
        'git_parent_commit': PARENT, 'existing_payload_count_to_preserve': 1858,
        'git_operations_performed': False, 'source_freezes_modified': False,
        'publication_prefix': 'android-acceptance',
        'whole_app_production_ready_count': 0, 'whole_app_target_count': 45,
        'new_Bilibili_UI_audio_reopen_actions': 0,
        'diagnostic_executed_at_snapshot': False,
        'original_Bilibili_admission_status': 'FAIL_BEFORE_ANDROID_UID_COMMAND',
        'candidate_snapshot_is_not_final_source_freeze': True,
        'utf8_files': len(rows), 'total_payload_bytes': sum(row['bytes'] for row in rows),
        'rows': rows, 'excluded': EXCLUDED,
        'always_excluded': ['__pycache__ and .pyc', 'ELF/APK/SO/signing keys',
                            'binary tar/gzip/zip', 'complete activation or UID inventory',
                            'commercial App raw logs, screenshots or audio'],
    }
    TREE.mkdir()
    for row in rows:
        raw = Path(row['source_path']).read_bytes()
        if len(raw) != row['bytes'] or digest(raw) != row['sha256']:
            raise RuntimeError('selected source changed before copy')
        target = Path(row['staged_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
        if target.read_bytes() != raw:
            raise RuntimeError('staged bytes differ')
    with (HERE / 'allowlist.json').open('x') as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({'files': len(rows), 'bytes': manifest['total_payload_bytes'],
                      'manifest': str(HERE / 'allowlist.json'),
                      'sha256': digest((HERE / 'allowlist.json').read_bytes())}))


if __name__ == '__main__':
    main()
