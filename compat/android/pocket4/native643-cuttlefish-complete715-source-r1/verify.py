#!/usr/bin/env python3
"""Authenticate and replay the complete Native647-to715 producer without Android."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

HERE = Path(__file__).resolve().parent
BASE_COMMIT = '2f91fe5f81886ca24c4c562ce9491f16e17261d5'
BASE_TREE = 'd30800eda1b2be36ac636913171195551cfefd38'
HEAD_COMMIT = '3450f2591faec153dbab06477d0a00e95120321f'
HEAD_TREE = 'af2c7788ca297e8cf499a4f18a0aa3d278d3b419'



def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def digest(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def object_id(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def safe(name):
    need(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
         and all(part not in ('', '.', '..', '.git') for part in name.split('/'))
         and all(ord(char) >= 32 and ord(char) != 127 for char in name), 'invalid exact relative path')
    return Path(name)


def regular(path, cap=64 * 1024 * 1024):
    path = Path(path).absolute()
    need(path.resolve() == path, 'input path contains an alias: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= cap,
             'bounded independent regular input required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(cap + 1)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()),
             'input changed during complete held read')
        return raw
    finally:
        os.close(fd)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_pairs)


def check(path, expected):
    raw = regular(path)
    need(digest(raw) == {key: expected[key] for key in ('bytes', 'sha256')}, 'exact input differs: ' + str(path))
    if 'git_blob' in expected:
        need(object_id('blob', raw) == expected['git_blob'], 'Git blob identity differs: ' + str(path))
    return raw


def member_names(root, skip_root_git=False):
    root = Path(root).absolute()
    need(root.resolve() == root and stat.S_ISDIR(root.lstat().st_mode), 'canonical existing directory required')
    names, directories = set(), {'.': f9(root.lstat())}
    for directory, children, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current == root and skip_root_git and '.git' in children:
            git = current / '.git'
            need(stat.S_ISDIR(git.lstat().st_mode) and not git.is_symlink(), 'root Git metadata must be a directory')
            children.remove('.git')
        for name in children:
            path = current / name
            relative = path.relative_to(root).as_posix()
            safe(relative)
            need(stat.S_ISDIR(path.lstat().st_mode) and not path.is_symlink(), 'directory alias or special entry rejected')
            directories[relative] = f9(path.lstat())
        for name in files:
            relative = (current / name).relative_to(root).as_posix()
            safe(relative)
            need(relative not in names, 'duplicate physical member')
            names.add(relative)
    return names, directories


def validate_rows(rows, count):
    need(isinstance(rows, list) and len(rows) == count, 'complete source inventory required')
    result = {}
    for row in rows:
        need(set(row) == {'path', 'bytes', 'sha256', 'git_blob', 'mode'}, 'complete exact source row required')
        safe(row['path'])
        need(row['path'] not in result and row['mode'] in ('100644', '100755')
             and type(row['bytes']) is int and 0 <= row['bytes'] <= 64 * 1024 * 1024
             and re.fullmatch('[0-9a-f]{64}', row['sha256'])
             and re.fullmatch('[0-9a-f]{40}', row['git_blob']), 'unique bounded original file required')
        result[row['path']] = row
    return result


def tree_id(rows):
    root = {}
    for row in rows:
        parts = safe(row['path']).parts
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            need(isinstance(node, dict), 'source file/directory collision')
        need(parts[-1] not in node, 'duplicate source tree member')
        node[parts[-1]] = (row['mode'], row['git_blob'])

    def encode(node):
        entries = []
        for name, value in node.items():
            if isinstance(value, dict):
                mode, oid, sortname = '40000', encode(value), name.encode() + b'/'
            else:
                mode, oid = value
                sortname = name.encode()
            entries.append((sortname, mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(oid)))
        return object_id('tree', b''.join(body for _, body in sorted(entries)))
    return encode(root)


def source_snapshot(root, rows, expected_tree):
    root = Path(root).absolute()
    wanted = validate_rows(rows, len(rows))
    need(tree_id(rows) == expected_tree, 'complete declared root tree differs')
    names, directories = member_names(root, skip_root_git=True)
    expected_dirs = {'.'} | {str(parent) for name in wanted for parent in Path(name).parents if str(parent) != '.'}
    need(names == set(wanted) and set(directories) == expected_dirs, 'complete producer file or directory membership changed')
    files = {}
    for name, row in sorted(wanted.items()):
        path = root / name
        before = f9(path.lstat())
        need(stat.S_ISREG(before[2]) and stat.S_IMODE(before[2]) == (int(row['mode'], 8) & 0o777),
             'producer original regular mode differs: ' + name)
        check(path, row)
        need(f9(path.lstat()) == before, 'producer identity changed during verification')
        files[name] = before
    after_names, after_dirs = member_names(root, skip_root_git=True)
    need(names == after_names and directories == after_dirs, 'producer membership changed during full audit')
    need(all(f9((root / name).lstat()) == identity for name, identity in files.items()), 'producer F9 changed during full audit')
    return {'files': files, 'directories': directories, 'tree': expected_tree}


def fresh_destination(path, protected):
    path = Path(path).absolute()
    need(path.resolve() == path and not os.path.lexists(path), 'fresh destination without any parent alias required')
    for root in protected:
        root = Path(root).absolute()
        need(root.resolve() == root and not path.is_relative_to(root), 'destination must be outside every input and producer')
    return path


def test_terminal(text, expected):
    need(isinstance(expected, (list, tuple)) and len(expected) == len(set(expected)), 'unique exact expected test catalog required')
    wanted = set(expected)
    records, running, summaries = [], [], []
    for line in text.splitlines():
        if line.startswith('test result:'):
            summaries.append(line)
        elif line.startswith('test '):
            match = re.fullmatch(r'test (\S+) \.\.\. (ok|FAILED|ignored(?:,.*)?)', line)
            need(match is not None, 'malformed Rust terminal record')
            records.append(match.groups())
        elif line.startswith('running '):
            match = re.fullmatch(r'running (\d+) tests?', line)
            need(match is not None, 'malformed Rust harness count')
            running.append(int(match.group(1)))
    need(len(records) == len(wanted) and {name for name, _ in records} == wanted
         and all(status == 'ok' for _, status in records), 'exact successful Rust identities required once each')
    need(running == [len(wanted)] and len(summaries) == 1, 'one complete Rust harness terminal required')
    match = re.fullmatch(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [0-9]+(?:\.[0-9]+)?s', summaries[0])
    need(match is not None and tuple(map(int, match.groups()[:4])) == (len(wanted), 0, 0, 0),
         'Rust summary contradicts the complete successful catalog')
    return len(records)


def successful_cargo_stream(raw):
    rows = [decode(line) for line in raw.decode().splitlines() if line]
    need(all(isinstance(row, dict) for row in rows), 'Cargo records must be complete JSON objects')
    terminals = [row for row in rows if row.get('reason') == 'build-finished']
    need(rows and terminals == [{'reason': 'build-finished', 'success': True}] and rows[-1] == terminals[0],
         'one final successful Cargo build-finished record required')
    need(not any(row.get('reason') == 'compiler-message' and row.get('message', {}).get('level') == 'error'
                 for row in rows), 'Cargo reported an error')
    return rows


def catalog(manifest, label):
    item = manifest[label]['inventory']
    return decode(check(HERE / safe(item['path']), item))


def test_catalogs(manifest):
    names = {key: decode(check(HERE / safe(row['path']), row)) for key, row in manifest['normal_test_names'].items()}
    need(set(names) == {'pair', 'source', 'permissions', 'journal', 'focused'}, 'complete current test groups required')
    need([len(names[key]) for key in ('pair', 'source', 'permissions', 'journal', 'focused')] == [53, 26, 7, 6, 6],
         'current Native715 test group counts differ')
    need(all(isinstance(value, list) and len(set(value)) == len(value) and all(isinstance(name, str) for name in value)
             for value in names.values()), 'unique complete test identities required')
    distinct = names['pair'] + names['source'] + names['permissions'] + names['journal']
    need(len(distinct) == len(set(distinct)) == 92 and set(names['focused']) <= set(names['pair']),
         'exact92 different tests and six focused repetitions required')
    return names


def verify_h(raw, paths, job, digest_value, nonce, at, code, stdout, stderr):
    request, started, exited = [decode(raw[name]) for name in paths]
    need(request['job_id'] == started['job_id'] == exited['job_id'] == job
         and request['request_digest'] == digest_value
         and request['launch_nonce'] == started['launch_nonce'] == exited['launch_nonce'] == nonce,
         'historical original process identity differs')
    need(type(exited['exit_code']) is int and exited['exit_code'] == code
         and exited['at_unix_ms'] == at and exited['cancelled'] is exited['timed_out'] is False
         and exited['output_complete'] is exited['output_durable'] is True
         and exited['terminal_publication_protocol'] == 1, 'complete original durable process terminal required')
    for side, size in (('stdout', stdout), ('stderr', stderr)):
        need(exited['log_bytes'][side] == {'seen': size, 'stored': size}
             and exited['log_errors'][side] is None and exited['log_synced'][side] is True
             and exited['log_truncated'][side] is False, 'original complete nontruncated durable logs required')
    return request, started, exited


def verify_history(manifest, capture):
    evidence = manifest['evidence']
    need(len(evidence) == 154 and all(row['path'] == 'evidence/' + name for name, row in evidence.items()),
         'all154 exact qualification records, controls, and logs required')
    raw = {name: check(HERE / safe(row['path']), row) for name, row in evidence.items()}
    originals = capture['source_refs']
    need(len(originals) == 877, 'complete original copied-input provenance required')
    for name, original in originals.items():
        check(HERE / safe(name), original)

    def captured(reference):
        matches = [name for name, row in originals.items() if row['path'] == reference['path']
                   and all(row[key] == reference[key] for key in ('bytes', 'sha256'))]
        need(matches, 'historical reference is missing its complete captured bytes: ' + reference['path'])
        for name in matches:
            if 'identity' in reference:
                need(originals[name]['identity'] == reference['identity'], 'historical original F9 join differs')
        return check(HERE / safe(matches[0]), reference)

    request, _, _ = verify_h(raw,
        ['owner-documents/request.json', 'owner-documents/started.json', 'owner-documents/exit.json'],
        '1a1d7487a36-392-a46', 'f2e29306bb362f6bc7b1293c0ae69410a75850e89eb414f5e7721faf366091e4',
        'b8fda10f3bb213ef21545d0b5237e8ee', 1794613271900, 0, 353, 0)
    verify_h(raw, ['independent-a54/durable-request.json', 'independent-a54/durable-started.json', 'independent-a54/durable-exit.json'],
        '1a1d75745b7-392-a54', 'b7c64cd8ee67ac95886a260bb5a613f277b62e1c99165772028dcf3b74289948',
        '93e98731cee492ec1c2b6d4847debe29', 1794614190586, 0, 1484, 0)
    verify_h(raw, ['source-preparation-a57-request.json', 'source-preparation-a57-started.json', 'source-preparation-a57-exit.json'],
        '1a1d75c5b99-392-a57', '673929fe861ddc44e99b6518efd07822e98cdc7b30956c0c832690cd4c9d866e',
        '74a498bd39a76e3033d37aa452eac3e6', 1794614524843, 0, 1448, 0)
    verify_h(raw, ['failed-export-a5f/request.json', 'failed-export-a5f/started.json', 'failed-export-a5f/exit.json'],
        '1a1d75ff831-392-a5f', '968df229fbc7445d80240da215a425be88bdf8f0b7690ea2947340cecdb781fb',
        '295b638a33eeaf2022d8244acc63cb3b', 1794614757021, 1, 0, 669)
    approved = decode(raw['owner-documents/approved_request.json'])
    for key in ('executable', 'args', 'cwd', 'env', 'memory_max_bytes', 'cpu_quota_percent', 'nice', 'timeout_seconds'):
        need(request[key] == approved.get(key, {} if key == 'env' else None), 'original approved ordinary request differs')
    owner = decode(raw['normal-owner.json'])
    for name, reference in owner['documents'].items():
        need(captured(reference) == raw['owner-documents/' + name + '.json'], 'normal owner/document join differs')
    inner, outer, entry = [decode(raw['owner-documents/' + name + '.json']) for name in ('inner', 'outer', 'entry')]
    need(inner['state'] == 'NORMAL643_CUTTLEFISH_ORIGINAL_PROVIDER_QUALIFIED'
         and inner['errors'] == [] and inner['recipe_commit'] == HEAD_COMMIT and inner['recipe_tree'] == HEAD_TREE
         and inner['full_Normal_qualified'] is inner['all_command_children_retired'] is inner['frozen715_unchanged']
         is inner['frozen647_unchanged'] is inner['original_three_shared_locks_released'] is True,
         'actual current complete715 ordinary qualification required')
    need(inner['complete_input_before'] == inner['complete_input_after']
         and inner['current715_before'] == inner['current715_after'], 'all original ordinary input F9 must agree')
    need(entry['passed'] is outer['passed'] is outer['inner_passed'] is outer['owned_unit_retired'] is True
         and outer['returncode'] == 0 and entry['actual_normal_commands'] == 29
         and entry['ordinary_launch_attempts'] == 1 and entry['direct_child_state'] == 'REAPED',
         'one actual29-command ordinary invocation with complete two-level retirement required')
    for reference, expected in ((entry['inner'], raw['owner-documents/inner.json']),
                                (entry['outer'], raw['owner-documents/outer.json']),
                                (outer['inner'], raw['owner-documents/inner.json'])):
        need(captured(reference) == expected, 'ordinary inner/outer receipt lineage differs')
    commands = inner['commands']
    need(len(commands) == len({row['name'] for row in commands}) == 29, 'all29 unique original normal commands required')
    command_map = {row['name']: row for row in commands}
    for command in commands:
        need(decode(raw['normal-command-records/' + command['name'] + '.json']) == command,
             'original durable command record differs from terminal')
        life = command['lifecycle']
        need(life['returncode'] == 0 and command['errors'] == [] and command['owned_retirement_complete']
             is life['child_reaped'] is life['pidfd_closed'] is life['owned_tree_cleanup_complete'] is True
             and life['remaining_owned_children'] == [] and command['reaper']['final_children_empty']
             is command['reaper']['restored'] is command['adopted_normal_exit']['complete'] is True,
             'every original successful command and adopted child must have retired')
        for side in ('stdout', 'stderr'):
            captured(command[side])
    names = test_catalogs(manifest)
    test_groups = [('new-update-all53-pair-controls', names['pair']),
                   ('new-source-crate-all26-controls', names['source']),
                   ('new-update-seven-filesystem-mode-tests', names['permissions'])]
    test_groups += [('new-update-focused-' + name.rsplit('::', 1)[1], [name]) for name in names['focused']]
    test_groups += [('new-update-' + name.rsplit('::', 1)[1], [name]) for name in names['journal']]
    executions = sum(test_terminal(captured(command_map[name]['stdout']).decode(), expected) for name, expected in test_groups)
    need(executions == 98 and len(test_groups) == 15, 'actual complete92/98 Rust set differs')
    compile_names = ['compile-new-update-test-harness', 'compile-new-source-crate-test-harness', 'compile-both-fresh-normal-CLIs']
    compiled = {name: successful_cargo_stream(captured(command_map[name]['stdout'])) for name in compile_names}
    artifacts = [inner['new_update_test_Cargo_artifact'], inner['new_source_test_Cargo_artifact'], *inner['new_CLI_Cargo_artifacts']]
    need(len(artifacts) == 4, 'two original harnesses and two original normal CLIs required')
    for artifact in artifacts:
        message = artifact['actual_Cargo_message']
        compile_command = artifact['compile_command']
        need(compile_command == command_map[compile_command['name']]
             and type(message['fresh']) is bool and compiled[compile_command['name']].count(message) == 1,
             'each original artifact must come from its exact successful Cargo invocation')
        identity = {key: value for key, value in message.items() if key != 'fresh'}
        origins = [(name, row) for name, rows in compiled.items() for row in rows
                   if row.get('reason') == 'compiler-artifact' and row.get('fresh') is False
                   and {key: value for key, value in row.items() if key != 'fresh'} == identity
                   and command_map[name]['started_ns'] <= compile_command['started_ns']]
        need(len(origins) == 1, 'each artifact needs one real fresh origin in the same original ordinary batch')
        package = 'droidloom-source' if '/tools/droidloom-source/' in message['manifest_path'] else 'droidloom-update'
        kind = 'lib' if message['target']['kind'] == ['lib'] else 'bin'
        need(message['manifest_path'] == inner['recipe_path'] + '/tools/' + package + '/Cargo.toml'
             and message['target']['src_path'] == inner['recipe_path'] + '/tools/' + package + '/src/' + ('lib.rs' if kind == 'lib' else 'main.rs'),
             'original Cargo artifact must bind this complete current producer')
        need(artifact['actual_ELF']['ELF'] is True, 'original actual ELF provenance required')
    retired = decode(raw['independent-a54/NORMALA46-RETIREMENT.json'])
    need(retired['state'] == 'ACTUAL92_TESTS_AND_29_COMMANDS_RETIRED_SOURCE_EPOCH_UNCHANGED'
         and retired['actual_normal_proof'] == capture['actual_normal'] == manifest['historical_actual_normal']
         and retired['old_full_recipe_files'] == 647 and retired['current_full_recipe_files'] == 715
         and retired['source_originals'] == 30952 and retired['source_indexes'] == 643
         and retired['projection_originals'] == 161 and retired['existing_graphics_provider_originals'] == 49,
         'independent full source, original normal and source epoch retirement required')
    proof = retired['actual_normal_proof']
    retirement = proof['actual_retirement']
    need(proof['different_tests'] == 92 and proof['executions'] == 98 and proof['actual29_commands_retired'] is True
         and retirement['actual_log_count'] == 66 and retirement['every_actual_log_SHA_and_F9_verified'] is True
         and len(set(retirement['fresh_original_PIDFD_ESRCH'])) == 43
         and len(set(retirement['actual_original_cgroups_absent'])) == 3, 'actual independent43PID/66log/3cgroup proof required')
    for field in ('source30952_F9_unchanged', 'source161_current_originals_F9_unchanged', 'all643_current_indexes_F9_unchanged',
                  'current715_F9_unchanged', 'original647_F9_unchanged', 'existing49_F9_unchanged'):
        need(retired['complete_source_before_after'][field] is True, 'complete original input bookend required: ' + field)
    for document in (inner, entry, retired, capture):
        need(document['runtime_qualified'] is False, 'ordinary evidence cannot qualify Android runtime')
    need(inner['AOSP_source_writes'] == inner['AOSP_full_builds_started'] == retired['source_writes']
         == retired['full_builds_started'] == capture['source_writes'] == capture['full_builds_started'] == 0,
         'the captured producer qualification must remain ordinary and source-only')
    return {'historical_distinct_tests': 92, 'historical_test_executions': 98, 'historical_commands': 29,
            'historical_complete_logs': 66, 'historical_source_files': 715, 'historical_base_files': 647,
            'failed_export_a5f_preserved': True, 'fresh_CI_tests_counted': 0}


def verify_capsule(expected_inventory):
    index = regular(HERE / 'FILES.sha256')
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory) and hashlib.sha256(index).hexdigest() == expected_inventory,
         'externally fixed capsule inventory differs')
    entries = {}
    for line in index.decode().splitlines():
        sha, name = line.split('  ', 1)
        safe(name)
        need(re.fullmatch('[0-9a-f]{64}', sha) and name not in entries and name != 'FILES.sha256', 'unique exact inventory entry required')
        entries[name] = sha
    actual, directories = member_names(HERE)
    all_names = set(entries) | {'FILES.sha256'}
    expected_dirs = {'.'} | {str(parent) for name in all_names for parent in Path(name).parents if str(parent) != '.'}
    need(actual == all_names and set(directories) == expected_dirs, 'capsule has extra or missing members or directories')
    for name, sha in entries.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'capsule member changed: ' + name)
    manifest = decode(regular(HERE / 'manifest.json'))
    need(manifest['schema'] == 'pocket4-native643-cuttlefish-complete715-source-capsule-v1', 'complete Native715 capsule required')
    catalogs = {}
    for label, commit, tree, count in (('base', BASE_COMMIT, BASE_TREE, 647), ('head', HEAD_COMMIT, HEAD_TREE, 715)):
        item = manifest[label]
        need((item['commit'], item['tree'], item['files']) == (commit, tree, count), 'fixed full source generation required')
        raw = check(HERE / safe(item['raw_commit']['path']), item['raw_commit'])
        header = raw.split(b'\n\n', 1)[0].splitlines()
        need(object_id('commit', raw) == commit and header[0] == ('tree ' + tree).encode()
             and sum(line.startswith(b'tree ') for line in header) == 1, 'original raw commit and root tree must agree')
        if label == 'head':
            need([line for line in header if line.startswith(b'parent ')] == [('parent ' + BASE_COMMIT).encode()],
                 'Native715 must retain its single full647 parent')
        rows = catalog(manifest, label)
        catalogs[label] = validate_rows(rows, count)
        need(tree_id(rows) == tree, 'all source members must reconstruct their original Git root')
    old, new = catalogs['base'], catalogs['head']
    changed = {name for name in old if old[name] != new.get(name)}
    added = set(new) - set(old)
    need(set(old) <= set(new) and changed == {'android/native-generation-pair/source-lock.json',
        'tools/droidloom-source/src/lib.rs', 'tools/droidloom-update/src/native_generation_pair_build.rs'}
        and len(added) == 68 and all(name.startswith('android/native-generation-pair/cuttlefish-graphics-fixtures/') for name in added)
        and manifest['changed_existing_files'] == sorted(changed) and manifest['added_files'] == sorted(added)
        and manifest['unchanged_files'] == 644, 'only three production changes and68 original graphics fixtures required')
    need(manifest['producer'] == 'producer', 'one fixed full715 producer namespace required')
    source_snapshot(HERE / 'producer', catalog(manifest, 'head'), HEAD_TREE)
    need(len(manifest['files']) == 71 and {row['path'] for row in manifest['files']} == changed | added,
         'complete exact source delta required')
    for row in manifest['files']:
        name = row['path']
        need(row['pre'] == old.get(name) and row['post'] == new[name], 'delta contradicts full source inventories')
        check(HERE / 'producer' / safe(name), row['post'])
        if row['pre'] is not None:
            check(HERE / 'preimages' / safe(name), row['pre'])
    need(member_names(HERE / 'preimages')[0] == changed, 'all and only three exact full647 preimages required')
    for name, row in manifest['unchanged_inputs'].items():
        need(old[name] == new[name] == row, 'unrelated producer boundary changed')
    before = decode(regular(HERE / 'preimages/android/native-generation-pair/source-lock.json'))
    after = decode(regular(HERE / 'producer/android/native-generation-pair/source-lock.json'))
    need({key: value for key, value in before.items() if key != 'projects'} ==
         {key: value for key, value in after.items() if key != 'projects'}, 'source release, links, origin or policy changed')
    old_projects, new_projects = [{row['path']: row for row in data['projects']} for data in (before, after)]
    need(len(old_projects) == len(new_projects) == 643 and set(old_projects) == set(new_projects), 'same643 exact projects required')
    for name, original in old_projects.items():
        expected = dict(original)
        if name == 'device/google/cuttlefish':
            expected['sparse_paths'] = original['sparse_paths'] + ['tests/graphics/hotplug']
        need(new_projects[name] == expected, 'only the exact original hotplug cone may be appended')
    need(manifest['source_profiles_independent'] == {'Native_source_projects': 643, 'Native_MAX_PROJECTS': 656,
         'Native_MAX_SPARSE_PATHS': 336, 'Audio_producer_modified': False}, 'independent producer resource scope required')
    source_lib = regular(HERE / 'producer/tools/droidloom-source/src/lib.rs').decode()
    need('const NATIVE_SOURCE_PROJECT_COUNT: usize = 643;' in source_lib
         and 'const MAX_PROJECTS: usize = NATIVE_SOURCE_PROJECT_COUNT.div_ceil(16) * 16;' in source_lib
         and 'const MAX_SPARSE_PATHS: usize = 336;' in source_lib, 'actual source bounds differ from the qualified producer')
    capture = decode(check(HERE / safe(manifest['capture']['path']), manifest['capture']))
    need(capture['base_files'] == 647 and capture['head_files'] == 715
         and (capture['base_commit'], capture['base_tree'], capture['head_commit'], capture['head_tree'])
         == (BASE_COMMIT, BASE_TREE, HEAD_COMMIT, HEAD_TREE)
         and capture['unchanged_files'] == 644 and capture['capsule_modes_are_original_Git_checkout_modes']
         is capture['physical_source_permissions_preserved'] is True, 'original complete tree capture provenance required')
    check(HERE / safe(manifest['patch']['path']), manifest['patch'])
    verify_history(manifest, capture)
    for key in ('native_full_build_complete', 'runtime_qualified', 'production_ready', 'fresh_CI_tests_prequalified'):
        need(manifest[key] is False, 'source qualification cannot grant full, runtime, production or new CI credit')
    need(manifest['AOSP_source_writes'] == manifest['AOSP_full_builds_started'] == manifest['Android_starts'] == 0,
         'ordinary publication scope required')
    return manifest


def replay(manifest, output):
    original = HERE / 'producer'
    output = fresh_destination(output, [HERE])
    base, head = catalog(manifest, 'base'), catalog(manifest, 'head')
    before = source_snapshot(original, head, HEAD_TREE)
    shutil.copytree(original, output, ignore=lambda directory, names: ['.git'] if Path(directory) == original else [])
    need(source_snapshot(original, head, HEAD_TREE) == before, 'complete original input F9 changed during independent copy')
    copied = source_snapshot(output, head, HEAD_TREE)
    need(all(copied['files'][name][:2] != before['files'][name][:2] for name in before['files']), 'independent source inodes required')
    need(not os.path.lexists(output / '.git'), 'input Git metadata must not be copied')
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_OPTIONAL_LOCKS='0')
    commands = []

    def git(args):
        argv = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.filemode=true', '-c', 'core.autocrlf=false', *args]
        run = subprocess.run(argv, cwd=output, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=120, umask=0o022)
        commands.append({'argv': argv, 'exit_code': run.returncode, 'stdout': digest(run.stdout), 'stderr': digest(run.stderr)})
        need(run.returncode == 0, 'actual Git replay failed: ' + run.stderr.decode(errors='replace'))
        return run.stdout

    def prove(rows, tree):
        source_snapshot(output, rows, tree)
        git(['add', '--force', '--all'])
        need(git(['write-tree']).decode().strip() == tree, 'actual complete Git root differs')
        return tree

    git(['init', '--quiet', '--template='])
    trees = [prove(head, HEAD_TREE)]
    patch = str(HERE / safe(manifest['patch']['path']))
    for args, rows, tree in ((['--reverse', '--check'], None, None), (['--reverse'], base, BASE_TREE),
                             (['--check'], None, None), ([], head, HEAD_TREE),
                             (['--reverse', '--check'], None, None), (['--reverse'], base, BASE_TREE),
                             (['--check'], None, None), ([], head, HEAD_TREE)):
        git(['apply', *args, patch])
        if rows is not None:
            trees.append(prove(rows, tree))
    need(source_snapshot(original, head, HEAD_TREE) == before, 'all715 original input F9 must remain unchanged after replay')
    return {'output': str(output), 'base_files': 647, 'head_files': 715, 'actual_Git_root_trees': trees,
            'git_commands': commands, 'input_F9_preserved': True, 'skipped_only_root_git': True,
            'private_Git_reconstructed': True, 'Git_child_umask': '0022', 'full_reverse_forward_reverse_forward_replay': True,
            'Rust_tests_run': False}


def write_report(path, value, protected):
    path = fresh_destination(path, protected)
    path.parent.mkdir(parents=True, exist_ok=True)
    need(path.parent.resolve() == path.parent, 'report parent became aliased')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    need(args.output is None or args.producer is None, 'fresh replay and existing producer audit are separate operations')
    protected = [HERE] + [path.absolute() for path in (args.output, args.producer) if path is not None]
    if args.report is not None:
        fresh_destination(args.report, protected)
    manifest = verify_capsule(args.inventory_sha256)
    result = {'state': 'EXACT_NATIVE643_COMPLETE715_SOURCE_CAPSULE_VERIFIED', 'base_files': 647, 'head_files': 715,
              'changed_existing_files': 3, 'added_original_fixtures': 68, 'historical_distinct_tests': 92,
              'historical_test_executions': 98, 'historical_commands': 29, 'fresh_CI_tests_counted': 0,
              'AOSP_source_writes': 0, 'AOSP_full_builds_started': 0, 'Android_starts': 0,
              'runtime_qualified': False, 'production_ready': False}
    if args.output is not None:
        result['replay'] = replay(manifest, args.output)
    if args.producer is not None:
        snapshot = source_snapshot(args.producer, catalog(manifest, 'head'), HEAD_TREE)
        result['producer'] = {'path': str(args.producer.absolute()), 'files': len(snapshot['files']),
                              'tree': snapshot['tree'], 'all_bytes_Git_blobs_modes_members_verified': True}
    if args.report is not None:
        write_report(args.report, result, protected)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
