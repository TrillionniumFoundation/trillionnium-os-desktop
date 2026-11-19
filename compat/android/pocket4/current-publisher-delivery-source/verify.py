#!/usr/bin/env python3
"""Replay frozen publisher source evidence without claiming an APK/device rerun."""
from pathlib import Path, PurePosixPath
import hashlib
import importlib.util
import io
import json
import stat
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[4]
PACKET = Path(__file__).resolve().parent
ARCHIVE_BYTES = 218378
ARCHIVE_SHA256 = 'd3291642001aa72c4bf8342c32567958ec9f4e7ace46150414673d45f184bd6a'
EXCLUSIONS = ['com.enflick.android.TextNow', 'com.pinger.textfree', 'com.ubercab']


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def read(relative, limit=2 * 1024 * 1024):
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and '..' not in parts.parts, 'relative source path')
    path = ROOT / relative
    require(path.resolve() == path and stat.S_ISREG(path.lstat().st_mode), 'ordinary canonical source')
    with path.open('rb') as stream:
        body = stream.read(limit + 1)
    require(len(body) <= limit, 'bounded source bytes')
    return body


def read_pin(row):
    body = read(row['path'])
    require(len(body) == row['bytes'] and sha(body) == row['sha256'], 'source pin: ' + row['path'])
    return body


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def main():
    prefix = PACKET.relative_to(ROOT).as_posix()
    files = {}
    for line in read(prefix + '/FILES.sha256').decode().splitlines():
        expected, name = line.split('  ', 1)
        require(name not in files and len(expected) == 64, 'unique complete file inventory')
        files[name] = expected
        require(sha(read(prefix + '/' + name)) == expected, 'packet file: ' + name)
    actual = {p.relative_to(PACKET).as_posix() for p in PACKET.rglob('*') if p.is_file()}
    require(set(files) == actual - {'FILES.sha256'}, 'exact packet inventory')
    manifest_body = read(prefix + '/MANIFEST.json')
    manifest = json.loads(manifest_body)
    require(manifest['schema'] == 'pocket4-current-publisher-delivery-publication-v1', 'publication schema')
    require(len({r['path'] for r in manifest['files']}) == len(manifest['files']), 'unique pinned sources')
    spec = importlib.util.spec_from_file_location('publisher_source_successor', PACKET / 'successor.py')
    successor_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(successor_module)
    successor = successor_module.Successor(read, manifest_body)
    for row in manifest['files']:
        if row['path'] in successor.history:
            # The original publication remains a historical 23-input record.
            # Its exact registry bytes are retained; current bytes have their
            # own fixed successor pins and separate complete semantic checks.
            body = successor.historical_registry(row['path'])
            require(len(body) == row['bytes'] and sha(body) == row['sha256'],
                    'original registry snapshot: ' + row['path'])
        else:
            read_pin(row)
    archive_body = read_pin(manifest['source_archive'])
    require(len(archive_body) == ARCHIVE_BYTES and sha(archive_body) == ARCHIVE_SHA256, 'original frozen archive')
    with tarfile.open(fileobj=io.BytesIO(archive_body), mode='r:gz') as archive:
        members = archive.getmembers()
        require(len(members) == 122 and len({m.name for m in members}) == 122, '122 unique frozen members')
        require(sum(m.size for m in members) == 1265992, 'complete expanded body budget')
        for member in members:
            path = PurePosixPath(member.name)
            require(member.isfile() and member.mode == 0o444 and not path.is_absolute()
                    and '..' not in path.parts, 'regular read-only frozen member')
        payloads = {m.name: archive.extractfile(m).read() for m in members}
    freeze_body = read_pin(manifest['source_freeze'])
    require(payloads['SOURCE_FREEZE.json'] == freeze_body, 'freeze exact archive member')
    freeze = json.loads(freeze_body)
    require(len(freeze['entries']) == freeze['payload_member_count'] == 121, '121 frozen payload entries')
    require(sum(r['bytes'] for r in freeze['entries']) == freeze['payload_bytes'] == 1184974, 'frozen payload bytes')
    require({r['member'] for r in freeze['entries']} == set(payloads) - {'SOURCE_FREEZE.json'}, 'frozen member inventory')
    for row in freeze['entries']:
        body = payloads[row['member']]
        require(len(body) == row['bytes'] and sha(body) == row['sha256'], 'frozen payload: ' + row['member'])
    for row in manifest['source_bindings']:
        require(read(row['published']) == payloads[row['frozen_member']], 'published source is exact frozen member')
    old_gate_manifest = json.loads(payloads['gate/SOURCE_MANIFEST.json'])
    old_gate_names = {r['name'] for r in old_gate_manifest['files']} | {'SOURCE_MANIFEST.json'}
    require(len(old_gate_names) == 20, 'exact original 20 product gate files')
    gate_names = old_gate_names | {'verify_publisher_delivery.py', 'test_publisher_delivery.py'}
    for name in gate_names:
        if name in successor_module.DOCUMENTATION:
            # All historical documentation remains fully pinned in SOURCE.tar.gz.
            # These three current documentation records explicitly describe the
            # additional gate; old executable gate/test sources stay byte-exact.
            successor.check_documentation(name)
        else:
            require(read('compat/android/pocket4/apk-content-identity/' + name) == payloads['gate/' + name],
                    'all original executable gate and test sources retain frozen bytes')
    # Two frozen transport lock records are archival evidence, not product sources.
    # Their bytes remain covered by the complete 121-entry archive verification.
    require({n[5:] for n in payloads if n.startswith('gate/')} - gate_names
            == {'.hepta-lock-0a6b910cf03f8c160e8f6963', '.hepta-lock-d65e66a2f8fca7f8dd91a0e7'},
            'exact two original transport lock records remain archived')
    summary = json.loads(payloads['SOURCE-INPUT-SUMMARY.json'])
    data = json.loads(payloads['DATA-INPUTS.json'])
    expected = json.loads(payloads['EXPECTED-INPUTS.json'])
    require(len(summary['packages']) == len(data) == len(expected) == 7, 'seven package evidence sets')
    require({r['package'] for r in summary['packages']} == {r['package'] for r in data}
            == {r['package'] for r in expected}, 'complete package mapping')
    require(sum(r['apks'] for r in summary['packages']) == 23, '23 original delivered APKs')
    require(sum(r['original_delivery_bytes'] for r in summary['packages']) == 942526044, 'original APK byte total')
    require(freeze['old_gate_source_files_unchanged'] == 20 and freeze['old_controls_passed'] == 146
            and freeze['new_controls_passed'] == 39, 'actual frozen control observations')
    inputs = json.loads(successor.historical_registry(successor_module.INPUTS))
    freshness = json.loads(successor.historical_registry(successor_module.FRESHNESS))
    scope = inputs['scope']
    require(inputs['schema'] == 'pocket4-current-source-inputs-v3', 'explicit custody union schema')
    require(sha(canonical(inputs['applications'][:17])) == manifest['preserved_previous_application_entries_sha256'],
            '17 earlier application/dependency custody entries unchanged')
    require(sha(canonical(inputs['archives'])) == manifest['preserved_previous_archive_entries_sha256'],
            'eight earlier archive custody entries unchanged')
    require(len(inputs['applications']) == 24 and scope['selected_application_count'] == 42
            and scope['required_application_count'] == 39 and scope['required_third_party_count'] == 29
            and scope['required_system_count'] == 10, 'unchanged requested scope')
    require(scope['excluded_packages'] == freshness['excluded_packages'] == EXCLUSIONS, 'only original three exclusions')
    require(scope['current_verified_third_party_source_input_count'] == 23
            and scope['remaining_current_compatible_third_party_input_count'] == 6
            and freshness['selected_current_source_input_count'] == 23
            and freshness['remaining_current_source_input_count'] == 6
            and len(freshness['rows']) == 29
            and sum(r['source_input_selected'] is True for r in freshness['rows']) == 23, '23 obtained, six still required')
    for row in [manifest, scope, summary, freeze, *inputs['applications'], *freshness['rows']]:
        require(not any(row.get(k, False) for k in ['installed', 'runtime_qualified', 'native_compatibility_qualified',
                                                   'business_qualified', 'production_ready']), 'no runtime acceptance from source evidence')
    current = successor.verify()
    # This entry point is a CI evidence replay, so its new finite rejection
    # controls run here without changing the frozen workflow or APK tests.
    subprocess.run([sys.executable, '-I', '-B', str(PACKET / 'test_successor.py')],
                   cwd=ROOT, check=True, timeout=30)
    print(json.dumps({'status': 'PASS_SOURCE_EVIDENCE_REPLAY_ONLY', 'packet_files': len(files),
                      'frozen_members': 122, 'source_bindings': len(manifest['source_bindings']),
                      'actual_sdk_evidence_packages': 7, 'actual_sdk_evidence_original_apks': 23,
                      'old_controls_recorded': 146, 'new_controls_recorded': 39,
                      'historical_required_third_party_inputs': 23, 'historical_remaining_source_inputs': 6,
                      'sdk_reexecuted_by_this_command': False, 'installed': False,
                      'runtime_qualified': False, 'production_ready': False, **current}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
