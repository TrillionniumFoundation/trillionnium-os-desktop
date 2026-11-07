#!/usr/bin/env python3
"""Local-only derivation; requires the actual fixed parent metadata receipt."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import secrets
import subprocess

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = BASE / 'engine-qualification-template-03'
OLD_BOUND = BASE / 'engine-qualification07-host-bound01'
NEW = BASE / 'engine-qualification-template-04'
BOUND = BASE / 'engine-qualification07-host-bound02'
PARENT = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01'
OLD_NONCE = 'dfcacd6f6da3cf3bdbfcf797f44481c3'
EXPECTED_OLD_PINS = '60976f7c256bd4fb5a5d648b776be756208f4fc8e1999b14d80746bb2bb0b97e'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-result')
    parser.add_argument('--metadata-sha256')
    args = parser.parse_args()
    if not args.metadata_result and not args.metadata_sha256:
        print(json.dumps({'state': 'PLAN_ONLY', 'parent': PARENT,
                          'actual_metadata_required': True, 'remote_dispatch': False}))
        return
    need(args.metadata_result and args.metadata_sha256, 'actual metadata path and hash are required')
    metadata_raw = Path(args.metadata_result).read_bytes()
    need(sha(metadata_raw) == args.metadata_sha256, 'actual metadata bytes differ')
    metadata = json.loads(metadata_raw)
    need(metadata['state'] == 'FIXED_METADATA_OBSERVED' and
         metadata['writes'] == metadata['file_content_reads'] == metadata['recursive_scans'] == 0 and
         metadata['children_created'] == metadata['Main_actions'] == 0 and
         metadata['staging_or_runtime_admitted'] is False, 'unexpected metadata observation contract')
    need(all(metadata['caller'][name] == 1000 for name in ('uid', 'euid', 'gid', 'egid')),
         'the read was not the expected operator observation')
    rows = {row['path']: row for row in metadata['observations']}
    need(len(rows) == len(metadata['observations']) == 4, 'fixed path observations differ')
    old_target = '/home/alex/work/pocket4-combined07-qualification-inputs-' + OLD_NONCE
    alternative = PARENT + '/qualification-inputs-' + OLD_NONCE
    need(set(rows) == {'/home/alex/work', old_target, PARENT, alternative}, 'fixed paths differ')
    for name in (old_target, alternative):
        need(rows[name].get('error', {}).get('errno') == 2 and
             rows[name]['error']['filename'] == name and 'named_before' not in rows[name],
             'previous/planned input path absence was not actually observed')
    parent = rows[PARENT]
    need(not parent.get('error') and parent['identity_stable'] is True and
         parent['canonical_path_equal'] is True and parent['realpath'] == PARENT,
         'alternative parent identity/canonical path was not stable')
    held = parent['held_before']
    need(held['directory'] and not held['symlink'] and held['uid'] == 1000 and
         held['mode'] & 0o022 == 0 and held['device'] > 0 and held['inode'] > 0,
         'alternative parent does not pass the original strict permission gate')
    old_pins_raw = (OLD / 'SOURCE_PINS.json').read_bytes()
    need(sha(old_pins_raw) == EXPECTED_OLD_PINS, 'frozen template03 manifest differs')
    old_pins = json.loads(old_pins_raw)
    sources = {}
    for name, pin in old_pins['files'].items():
        raw = (OLD / name).read_bytes()
        need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'template03 payload changed: ' + name)
        sources[name] = raw
    before = sources['make_qualification.py'].decode()
    old_line = 'return "/home/alex/work/pocket4-combined07-qualification-inputs-" + nonce(config)'
    new_line = 'return "' + PARENT + '/qualification-inputs-" + nonce(config)'
    need(before.count(old_line) == 1, 'input_root derivation target differs')
    after = before.replace(old_line, new_line)
    sources['make_qualification.py'] = after.encode()
    sources['README.md'] += (
        '\n## Template04 private input parent\n\n'
        'Only input_root now uses the actually observed strict native-owned-01 parent. '
        'No suite, runner, artifact qualification or resource guard changes. '
        'The previous stage01 permission failure remains unchanged. Fresh nonce/input '
        'claims are generated; actual host PASS still gates Android preparation.\n').encode()
    need(not NEW.exists() and not BOUND.exists(), 'new template/binding outputs must be absent')
    NEW.mkdir(mode=0o700)
    for name, raw in sources.items():
        target = NEW / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (NEW / 'template03-to04.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile='template03/make_qualification.py',
        tofile='template04/make_qualification.py')))
    (NEW / 'actual-parent-metadata.json').write_bytes(metadata_raw)
    (NEW / 'reference-template03-pins.json').write_bytes(old_pins_raw)
    (NEW / 'DERIVATION.json').write_bytes(encoded({
        'schema': 1, 'actual_metadata_sha256': args.metadata_sha256,
        'parent_manifest_sha256': EXPECTED_OLD_PINS,
        'executable_delta': 'Only input_root prefix; all execution references unchanged',
        'strict_parent_gate_preserved': True, 'old_failure_preserved': True,
        'remote_requests_dispatched': 0, 'production_ready': False}))
    pins = {p.relative_to(NEW).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
            for p in sorted(NEW.rglob('*')) if p.is_file()}
    (NEW / 'SOURCE_PINS.json').write_bytes(encoded({'schema': 1, 'files': pins,
        'tests_executed': False, 'remote_requests_dispatched': 0, 'production_ready': False}))
    config = json.loads((OLD_BOUND / 'binding.json').read_bytes())
    config['nonce'] = secrets.token_hex(16)
    config['android_allocation'] = {'host_uid': 2407, 'subid_start': 14600000}
    BOUND.mkdir(mode=0o700)
    binding_raw = encoded(config)
    (BOUND / 'binding.json').write_bytes(binding_raw)
    command = ['/usr/bin/python3', '-I', '-B', str(NEW / 'make_qualification.py'), 'host',
               '--binding', str(BOUND / 'binding.json'), '--binding-sha256', sha(binding_raw),
               '--out', str(BOUND / 'generated')]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    (BOUND / 'binding.stdout').write_bytes(result.stdout)
    (BOUND / 'binding.stderr').write_bytes(result.stderr)
    (BOUND / 'ACTUAL_PARENT_BINDING.json').write_bytes(encoded({
        'schema': 1, 'actual_metadata': {'path': str(Path(args.metadata_result).resolve()),
                                     'sha256': args.metadata_sha256},
        'parent_identity': held, 'original_stage_failure_retained': True,
        'old_nonce': OLD_NONCE, 'new_nonce': config['nonce'],
        'previous_target_actually_absent': True,
        'template04_pins_sha256': sha((NEW / 'SOURCE_PINS.json').read_bytes()),
        'command': command, 'returncode': result.returncode,
        'remote_requests_dispatched': 0, 'host_suite_executed': False}))
    need(result.returncode == 0 and not result.stderr, 'local receipt binding failed; original output retained')
    print(json.dumps({'state': 'LOCAL_HOST_REQUESTS_BOUND_NOT_DISPATCHED',
                      'template': str(NEW), 'binding': str(BOUND), 'nonce': config['nonce']}))


if __name__ == '__main__':
    main()
