#!/usr/bin/env python3
"""Verify saved next-round evidence and source proofs; never build, install or run guests."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

MAX_FILE_BYTES = 2 * 1024 * 1024
EVIDENCE_PREFIX = ('support', 'build', 'evidence')
FIXED_PINS = {
    'repository': 'asterinas/asterinas', 'tag': 'v0.19.0',
    'commit': 'c4b7ed575b7b32773475b194d2ad41fb6d03765b',
    'tree': '96605cf64aeae2d34f29b97e85eff9315fe10a8e',
    'toolchain': 'nightly-2026-07-21', 'reuse': 'full_kernel_derived',
    'source_directory': 'kernel/asterinas',
}
FALSE_SCOPES = ('all_project_blockers_closed',
                'cross_host_reproducibility_accepted',
                'immutable_environment_accepted')
IDENTITY_FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(name):
    require(type(name) is str and name and not any(ord(c) < 32 or ord(c) == 127 for c in name),
            'invalid relative path')
    path = PurePosixPath(name)
    require(bool(path.parts) and path.name not in ('.', '..') and
            not path.is_absolute() and str(path) == name and
            not any(part in ('.', '..') for part in path.parts) and '\\' not in name,
            'unsafe relative path: ' + name)
    return path.parts


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(info):
    return tuple(getattr(info, field) for field in IDENTITY_FIELDS)


def open_root(path):
    absolute = Path(path).absolute()
    require(not any(p in ('.', '..') for p in absolute.parts), 'noncanonical repository root')
    fd = os.open('/', DIR_FLAGS)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, absolute
    except BaseException:
        os.close(fd)
        raise


def open_directory(anchor, parts):
    fd = os.dup(anchor)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def stable_file(directory, name):
    before_path = os.stat(name, dir_fd=directory, follow_symlinks=False)
    require(stat.S_ISREG(before_path.st_mode), 'non-regular file: ' + name)
    require(before_path.st_size <= MAX_FILE_BYTES, 'file exceeds 2 MiB: ' + name)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        require(identity(before) == identity(before_path), 'file changed before read: ' + name)
        parts, size = [], 0
        while True:
            block = os.read(fd, 128 * 1024)
            if not block:
                break
            size += len(block)
            require(size <= MAX_FILE_BYTES, 'file grew beyond 2 MiB: ' + name)
            parts.append(block)
        after = os.fstat(fd)
        after_path = os.stat(name, dir_fd=directory, follow_symlinks=False)
        require(identity(before) == identity(after) == identity(after_path), 'file changed during read: ' + name)
        data = b''.join(parts)
        require(len(data) == before.st_size, 'short file read: ' + name)
        return data
    finally:
        os.close(fd)


def read_relative(anchor, name):
    parts = relative(name)
    parent = open_directory(anchor, parts[:-1])
    try:
        return stable_file(parent, parts[-1])
    finally:
        os.close(parent)


def inventory(directory, omit_runtime_caches=False):
    records = {}

    def visit(fd, prefix):
        before = os.fstat(fd)
        for name in sorted(os.listdir(fd)):
            if omit_runtime_caches and name == '__pycache__':
                continue
            relative(name)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            path = '/'.join(prefix + (name,))
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                try:
                    require(identity(os.fstat(child)) == identity(info), 'directory changed before read: ' + path)
                    visit(child, prefix + (name,))
                    require(identity(os.fstat(child)) == identity(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                            'directory path changed: ' + path)
                finally:
                    os.close(child)
            else:
                data = stable_file(fd, name)
                records[path] = {'bytes': len(data), 'sha256': digest(data)}
        require(identity(before) == identity(os.fstat(fd)), 'directory changed during inventory')

    visit(directory, ())
    return records


def checksum_entries(data):
    entries = {}
    for line in data.decode('utf-8').splitlines():
        require(len(line) > 66 and line[64:66] == '  ', 'invalid checksum line')
        sha, name = line[:64], line[66:]
        relative(name)
        require(re.fullmatch('[0-9a-f]{64}', sha) is not None and
                name not in entries and name != 'SHA256SUMS', 'invalid/duplicate/self checksum entry')
        entries[name] = sha
    return entries


def verify_phase(repository, path, expected=None):
    parts = relative(path)
    require(parts[:3] in (EVIDENCE_PREFIX, ('support', 'build', 'handoffs')) and len(parts) >= 4, 'phase outside evidence/handoff directory')
    phase = open_directory(repository, parts)
    try:
        anchor = os.fstat(phase)
        manifest = stable_file(phase, 'SHA256SUMS')
        entries = checksum_entries(manifest)
        files = inventory(phase, omit_runtime_caches=True)
        require(files['SHA256SUMS']['sha256'] == digest(manifest), 'manifest changed during inventory: ' + path)
        require(set(files) == set(entries) | {'SHA256SUMS'}, 'unlisted/missing phase files: ' + path)
        for name, sha in entries.items():
            require(files[name]['sha256'] == sha, 'phase checksum mismatch: ' + path + '/' + name)
        result = {'path': path, 'sha256sums_sha256': digest(manifest),
                  'file_count': len(files), 'total_bytes': sum(r['bytes'] for r in files.values()),
                  'checksum_entries': len(entries),
                  'maximum_file_bytes': max(r['bytes'] for r in files.values())}
        if expected is not None:
            for key in ('file_count', 'total_bytes'):
                require(type(expected[key]) is int and expected[key] >= 0 and result[key] == expected[key],
                        'phase count/size mismatch: ' + path + ':' + key)
            require(re.fullmatch('[0-9a-f]{64}', expected['sha256sums_sha256']) is not None and
                    result['sha256sums_sha256'] == expected['sha256sums_sha256'], 'phase manifest identity mismatch: ' + path)
        reopened = open_directory(repository, parts)
        try:
            require((anchor.st_dev, anchor.st_ino) == (os.fstat(reopened).st_dev, os.fstat(reopened).st_ino),
                    'phase pathname was replaced: ' + path)
        finally:
            os.close(reopened)
        return result
    finally:
        os.close(phase)


DERIVED_TREE = '6b3cab110aa6d30d5b89f99c4389c9c3e01022da'
LOCK_DELTA = ['/kernel/cloud_next_validation_2026_10_17',
              '/native_build_environment', '/reproducible_kernel_build_note']


def json_delta(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            path = prefix + '/' + key
            result += [path] if key not in before or key not in after else json_delta(before[key], after[key], path)
        return result
    return [] if before == after else [prefix]


def verify_source(read, bridge, current_repository=None):
    require(bridge['schema'] == 'a01-next-source-bridge/1', 'wrong source bridge schema')
    objects = {}
    for oid, row in bridge['objects'].items():
        require(re.fullmatch('[0-9a-f]{40}', oid) is not None, 'invalid Git object name')
        typ = row['type']
        require(typ in ('commit', 'tree', 'blob'), 'unsupported Git object type')
        payload = read('source/objects/' + oid)
        require(len(payload) == row['bytes'] and digest(payload) == row['sha256'], 'Git payload hash/size mismatch')
        header = (typ + ' ' + str(len(payload)) + '\0').encode().replace(b'\\0', b'\0')
        # The byte literal below supplies the Git object header NUL explicitly.
        header = (typ + ' ' + str(len(payload))).encode() + bytes([0])
        require(hashlib.sha1(header + payload).hexdigest() == oid, 'Git object identity mismatch: ' + oid)
        objects[oid] = (typ, payload)

    def root(commit):
        typ, payload = objects[commit]
        require(typ == 'commit' and payload.startswith(b'tree '), 'invalid commit proof')
        return payload.splitlines()[0][5:].decode('ascii')

    def entries(oid):
        typ, data = objects[oid]
        require(typ == 'tree', 'non-tree in Git path proof')
        result = {}; offset = 0
        while offset < len(data):
            space = data.index(b' ', offset); nul = data.index(b'\0', space)
            name = data[space + 1:nul].decode('utf-8')
            require(name not in result and '/' not in name and name not in ('.', '..'), 'invalid tree entry')
            require(nul + 21 <= len(data), 'truncated tree object')
            result[name] = (data[offset:space].decode('ascii'), data[nul + 1:nul + 21].hex())
            offset = nul + 21
        return result

    def member(commit, path):
        oid = root(commit); mode = None
        for part in relative(path):
            mode, oid = entries(oid)[part]
        return mode, oid

    def file_row(commit, row):
        mode, oid = member(commit, row['path'])
        require((mode, oid) == (row['mode'], row['blob']), 'source membership mismatch: ' + row['path'])
        typ, data = objects[oid]
        require(typ == 'blob' and len(data) == row['bytes'] and digest(data) == row['sha256'], 'source byte proof mismatch')
        return data

    groups = bridge['groups']
    require({g['name'] for g in groups} == {'normal-runtime', 'debug-runtime-and-tests', 'ktest-runtime-and-locks',
             'main-abi-code-and-runner', 'schema4-reproduction-code'}, 'wrong source bridge groups')
    count = 0
    for group in groups:
        require(group['comparison_commit'] == bridge['comparison_commit'] and group['exact_selected_file_bytes_and_modes_equal'] is True,
                'source bridge comparison boundary mismatch')
        require(group['files'] and len({r['path'] for r in group['files']}) == len(group['files']), 'empty/duplicate source group')
        for row in group['files']:
            data = file_row(group['producer_commit'], row)
            require(file_row(bridge['comparison_commit'], row) == data, 'source groups differ')
            if current_repository is not None:
                require(read_relative(current_repository, row['path']) == data, 'current selected source changed: ' + row['path'])
                actual_mode = '100755' if os.stat(row['path'], dir_fd=current_repository, follow_symlinks=False).st_mode & 0o111 else '100644'
                require(actual_mode == row['mode'], 'current selected source mode changed: ' + row['path'])
            count += 1
    for row in bridge['kernel_trees']:
        require(row['tree'] == DERIVED_TREE and member(row['producer_commit'], row['path']) == (row['mode'], DERIVED_TREE),
                'complete derived kernel tree mismatch')
    locks = {}
    for row in bridge['producer_locks']:
        lock = json.loads(file_row(row['producer_commit'], row)); locks[row['producer_commit']] = lock
        require(all(lock['kernel'][k] == v for k, v in FIXED_PINS.items()), 'producer fixed pins changed')
    final_bytes = read('final-upstream-lock.json'); final = json.loads(final_bytes)
    delta = bridge['lock_delta']
    require(digest(final_bytes) == delta['final_sha256'] and delta['changed_json_paths'] == LOCK_DELTA, 'final lock binding mismatch')
    require(json_delta(locks[delta['baseline_commit']], final) == LOCK_DELTA, 'lock changed outside three metadata paths')
    require(all(final['kernel'][k] == v for k, v in FIXED_PINS.items()), 'final fixed pins changed')
    require(final['reproducible_kernel_build_ready'] is False and final['build_container_digest'] is None,
            'immutable/broad reproduction boundary widened')
    require(file_row(bridge['comparison_commit'], bridge['root_readme']) == b'', 'saved root README is nonempty')
    if current_repository is not None:
        require(read_relative(current_repository, 'support/upstream-lock.json') == final_bytes, 'current lock differs from final saved lock')
        require(read_relative(current_repository, 'README.md') == b'', 'current root README is nonempty')
    return {'groups': len(groups), 'selected_files': count, 'git_objects': len(objects),
            'derived_kernel_tree': DERIVED_TREE, 'final_lock_sha256': digest(final_bytes),
            'lock_changed_json_paths': LOCK_DELTA, 'current_source_checked': current_repository is not None}


def verify(phase_path, evidence_root, current_repo=None):
    repository, repo = open_root(evidence_root)
    phase, phase_absolute = open_root(phase_path)
    current = None
    try:
        own_manifest = read_relative(phase, 'SHA256SUMS'); own_entries = checksum_entries(own_manifest)
        own_files = inventory(phase)
        require(own_files['SHA256SUMS']['sha256'] == digest(own_manifest), 'closure manifest changed during inventory')
        require(set(own_files) == set(own_entries) | {'SHA256SUMS'}, 'unlisted/missing closure files')
        require(all(own_files[n]['sha256'] == h for n, h in own_entries.items()), 'closure checksum mismatch')
        def read(name):
            data = read_relative(phase, name)
            require(name in own_entries and digest(data) == own_entries[name], 'closure file changed after inventory: ' + name)
            return data
        index = json.loads(read('phase-index.json'))
        require(index['schema'] == 'a01-next-cloud-phase-index/1' and len(index['phases']) == 11, 'wrong phase index')
        paths = [r['path'] for r in index['phases']]
        require(len(set(paths)) == 11 and all(p.startswith('support/build/evidence/2026-10-17-') for p in paths), 'phase paths duplicate/outside evidence')
        require(all(p != str(phase_absolute.relative_to(repo)) for p in paths) if phase_absolute.is_relative_to(repo) else True,
                'circular own-phase index')
        phases = [verify_phase(repository, row['path'], row) for row in index['phases']]
        verify_phase(repository, index['a04_exact_input_handoff']['path'], index['a04_exact_input_handoff'])
        observations = json.loads(read('phase-verification.json'))
        commands = observations['commands']; seen = set()
        require(observations['completed'] is True and observations['all_zero'] is True and len(commands) == 22, 'incomplete actual phase verification')
        phase_map = {row['path']: row for row in index['phases']}
        for command in commands:
            key = (command['phase'], command['mode'])
            require(key not in seen and key[0] in phase_map and key[1] in ('I', 'IO'), 'duplicate/unindexed verification receipt')
            seen.add(key); row = phase_map[key[0]]
            require(command['raw_exit_code'] == 0 and type(command['raw_exit_code']) is int, 'original verifier failed')
            require(command['verifier_sha256'] == row['verifier_sha256'] and command['phase_sha256sums_sha256'] == row['sha256sums_sha256'], 'verification input identity mismatch')
            flags = command['argv'][1:-1]
            require(flags == (['-I'] if key[1] == 'I' else ['-I', '-O']) and command['argv'][-1].endswith('/' + key[0] + '/verify.py'), 'wrong actual verifier mode/entry')
            log = read(command['log'])
            require(len(log) == command['log_bytes'] and digest(log) == command['log_sha256'], 'verification log mismatch')
            require(digest(read_relative(repository, key[0] + '/verify.py')) == row['verifier_sha256'], 'original verifier bytes changed')
        if current_repo is not None:
            current, current_path = open_root(current_repo)
        bridge = json.loads(read('source-bridge.json'))
        source = verify_source(read, bridge, current)
        if current is not None:
            import subprocess
            tree = subprocess.check_output(['git', '-C', str(current_path), 'rev-parse', 'HEAD:kernel/asterinas'], stderr=subprocess.PIPE).decode().strip()
            require(tree == DERIVED_TREE, 'current complete derived kernel tree differs')
            clean = subprocess.run(['git', '-C', str(current_path), 'diff', '--quiet', 'HEAD', '--', 'kernel/asterinas'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(clean.returncode == 0, 'current derived kernel has tracked changes')
        ledger = json.loads(read('blockers.json'))
        require(ledger['draft'] is False and ledger['publishable'] is True and ledger['all_project_blockers_closed'] is False
                and ledger['native_resource_control_accepted'] is False and ledger['immutable_environment_claimed'] is False,
                'acceptance scope widened')
        require(ledger['current_round_real_qemu_guests'] == 5 and ledger['current_round_raw_qemu_exits'] == [33] * 5, 'wrong current guest count')
        final_lock = json.loads(read('final-upstream-lock.json'))['kernel']['cloud_next_validation_2026_10_17']
        require(final_lock['current_round_real_qemu_guests'] == 5 and final_lock['all_project_blockers_closed'] is False, 'metadata guest/scope mismatch')
        require(final_lock['kernel_mode_tests']['reported_passed'] == 362 and final_lock['kernel_mode_tests']['soft_skipped'] == 3
                and final_lock['kernel_mode_tests']['exercised_passed_lower_bound'] == 359, 'ktest acceptance counts changed')
        require(final_lock['ordinary_cold_build_and_boot']['first_and_loaded_kernel_complete_bytes_equal'] is True
                and final_lock['ordinary_cold_build_and_boot']['global_prelaunch_payload_retained'] is False,
                'ordinary byte-custody boundary changed')
        pub = json.loads(read('raw/publication/publication-index.json'))
        require(pub['head'] == bridge['comparison_commit'] and len(pub['first_parent_verified_commits']) == 17, 'publication/source checkpoint mismatch')
        previous = pub['base']
        for row in pub['first_parent_verified_commits']:
            require(row['parents'][0] == previous, 'publication first-parent chain broken')
            receipt = read('raw/publication/' + row['verified_receipt'])
            require(digest(receipt) == row['verified_receipt_sha256'], 'publisher verified receipt changed')
            receipt_json = json.loads(receipt)
            require(receipt_json.get('commit', receipt_json.get('remote_sha')) == row['commit'], 'publisher receipt commit mismatch')
            previous = row['commit']
        require(previous == pub['head'], 'publication head differs')
        erratum = json.loads(read('raw/publication/publisher-commit-message-erratum.json'))
        require(erratum['correct_first_and_boot_kernel_complete_bytes_equal'] is True
                and erratum['correct_first_elf']['sha256'] == '5c2cee2a8806baf873149ce07f752cc3b1c633efd4199e0c8c0ba20ef5f325f7', 'missing N2 commit-message correction')
        writer = json.loads(read('raw/writer-observation-v2/result.json'))
        # The precise nested record is preserved and hashed; conclusions stay bounded.
        require(ledger['immutable_environment_claimed'] is False, 'writer observation widened custody')
        require(inventory(phase) == own_files, 'closure changed during verification')
        return {'passed': True, 'scope': 'Offline saved phase hashes,22 actual original-verifier receipts, Git source proofs and final-lock metadata only; no build, installation, archived payload or guest rerun.',
                'indexed_phases': len(phases), 'original_verifier_commands': len(commands), 'source_bridge': source,
                'current_round_real_qemu_guests': 5, 'all_project_blockers_closed': False,
                'publication_checkpoint': pub['head'], 'closure_files': len(own_files),
                'closure_sha256sums_sha256': digest(own_manifest)}
    finally:
        if current is not None: os.close(current)
        os.close(phase); os.close(repository)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, help='Also check present selected source/lock bytes and derived kernel tree; default uses saved historical data.')
    args = parser.parse_args()
    phase = Path(__file__).absolute().parent
    try:
        print(json.dumps(verify(phase, phase.parents[3], args.repo), indent=2))
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print('verification failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
