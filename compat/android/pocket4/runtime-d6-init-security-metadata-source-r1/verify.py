#!/usr/bin/env python3
"""Authenticate and replay the complete430 D6 init-metadata producer without Android."""
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
BASE_COMMIT = 'b08cdd2c70c05463c3b4c892012f7426691c502b'
BASE_TREE = 'af27a280676bc39b5ce98168ebba3ae1891e4e56'
HEAD_COMMIT = '7d86a66b8d95477781519cec99e53fd0e76b6f36'
HEAD_TREE = '224fdc48b1083044cdce30a09ee4ec995a48c12d'
TESTS = {'production_mounts::runtime_assets::tests::runtime_init_metadata_cannot_be_supplied_by_user_attributes', 'production_mounts::runtime_assets::tests::runtime_init_xattr_requires_complete_exact_bytes', 'production_mounts::runtime_assets::tests::runtime_init_capability_absence_rejects_present_empty_and_binary_values', 'production_mounts::runtime_assets::tests::runtime_init_xattr_read_errors_do_not_establish_absence', 'production_mounts::runtime_assets::tests::runtime_schema_rejects_boolean_integer_and_unknown_authority_fields', 'production_mounts::runtime_assets::tests::held_init_rejects_foreign_architecture_and_overflowing_segments', 'production_mounts::runtime_assets::tests::runtime_inputs_reject_other_base_or_original_system', 'production_mounts::runtime_assets::tests::runtime_init_xattr_follows_held_descriptor_after_path_replacement', 'production_mounts::runtime_assets::tests::runtime_manifest_rejects_paths_aliases_and_lineage_substitution'}



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


def focused_test_log(text):
    records, running, summaries = [], [], []
    for line in text.splitlines():
        if line.startswith('test result:'):
            summaries.append(line)
        elif line.startswith('test '):
            match = re.fullmatch(r'test (\S+) \.\.\. (ok|FAILED|ignored)', line)
            need(match is not None, 'malformed Rust test record')
            records.append(match.groups())
        elif line.startswith('running '):
            need(re.fullmatch(r'running \d+ tests?', line), 'malformed Rust test count')
            running.append(line)
    need(len(records) == 9 and {name for name, _ in records} == TESTS and all(status == 'ok' for _, status in records),
         'all nine exact runtime input test identities must pass once')
    need(running == ['running 9 tests'] and len(summaries) == 1 and re.fullmatch(
        r'test result: ok\. 9 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9]+(?:\.[0-9]+)?s',
        summaries[0]), 'one complete successful summary without contradictory terminal required')
    return sorted(name for name, _ in records)


def successful_cargo_stream(raw):
    rows = [decode(line) for line in raw.decode().splitlines() if line]
    terminals = [row for row in rows if row.get('reason') == 'build-finished']
    need(rows and terminals == [{'reason': 'build-finished', 'success': True}]
         and rows[-1] == terminals[0], 'one complete successful Cargo terminal required')
    need(not any(row.get('reason') == 'compiler-message' and row.get('message', {}).get('level') == 'error'
                 for row in rows), 'successful Cargo stream contains an error')
    return rows


def catalog(manifest, label):
    item = manifest[label]['inventory']
    return decode(check(HERE / safe(item['path']), item))


def verify_history(manifest):
    evidence = manifest['evidence']
    need(len(evidence) == 109, 'all109 original qualification records and logs are required')
    raw = {name: check(HERE / safe(row['path']), row) for name, row in evidence.items()}
    need(all(row['path'] == 'evidence/' + name for name, row in evidence.items()), 'one exact original evidence namespace required')
    normal, completion, retired = [decode(raw[name]) for name in ('normal/RESULT.json', 'completion/RESULT.json', 'independent/RESULT.json')]
    preflight = decode(raw['preflight-failure/RESULT.json'])
    need(preflight['state'] == 'FAILED' and preflight['errors'], 'original9f7 preflight failure must remain failed')
    need(normal['state'] == 'FAILED' and len(normal['errors']) == 1
         and normal['errors'][0]['type'] == 'AssertionError' and 'st_nlink == 1' in normal['errors'][0]['traceback']
         and normal['release_binaries'] == {}, 'originala00 copy refusal remains a real failed record')
    need(completion['state'] == 'COMPOSITE_NINE_ACTUAL_TESTS_AND_TWO_FRESH_RELEASE_BINARIES_QUALIFIED'
         and completion['errors'] == [] and completion['Cargo_or_tests_repeated'] is False
         and completion['original_failed_report_unchanged'] is completion['original21_commands_and_tree_retired'] is True,
         'actuala0b completion must retain the original failed report without repeating tests or compilation')
    need(retired['state'] == 'NINE_ACTUAL_TESTS_TWO_FRESH_RELEASES_AND_430_SOURCE_FILES_INDEPENDENTLY_RETIRED'
         and retired['errors'] == [] and retired['actual_commands'] == 26 and retired['actual_distinct_tests_passed'] == 9
         and retired['all430_F9_Gitblobs_modes_unchanged'] is retired['all52_command_log_F9_and_whole_SHA256_verified'] is True
         and len(retired['original_PIDs_fresh_ESRCH']) == len(set(retired['original_PIDs_fresh_ESRCH'])) == 32
         and len(retired['cgroups_absent']) == len(set(retired['cgroups_absent'])) == 6,
         'actuala1d independent32PID/6cgroup/source430 retirement required')
    for proof in (normal, completion, retired, preflight):
        need((proof['base'], proof['head'], proof['tree']) == (BASE_COMMIT, HEAD_COMMIT, HEAD_TREE), 'historical source generation differs')
        need(all(proof[k] is False for k in ('ExecutionAdmission_constructible', 'actual_SELinux_transition_qualified', 'runtime_qualified', 'production_ready'))
             and proof['Android_starts'] == proof['host_policy_writes'] == proof['original_data_body_reads'] == 0,
             'host qualification must not grant Android, policy or live execution credit')
    need(normal['all430_source_F9_Gitblobs_modes_preserved'] is completion['all430_source_F9_Gitblobs_modes_preserved'] is completion['source_before_and_after_unchanged'] is True,
         'complete430 original source F9 and Git identities required')
    for claim, name in ((completion['original_failed_result'], 'normal/RESULT.json'),
                        (retired['original_failed_normal_result_preserved'], 'normal/RESULT.json'),
                        (retired['completion_result'], 'completion/RESULT.json')):
        need(all(claim[key] == evidence[name][key] for key in ('bytes', 'sha256')), 'completion/retirement must bind exact original report bytes')
    for proof, key in ((normal, 'actual_tests_passed'), (completion, 'actual_original_tests_passed'), (retired, 'actual_test_names')):
        need(len(proof[key]) == 9 and set(proof[key]) == TESTS, 'same nine actual test identities required')
    need(focused_test_log(raw['normal/nine-runtime-input-controls.stdout'].decode()) == sorted(TESTS), 'original nine-test complete terminal differs')
    commands = []
    for group, proof, count in (('normal', normal, 21), ('completion', completion, 5)):
        need(len(proof['commands']) == count and len({c['name'] for c in proof['commands']}) == count, 'exact original command membership required')
        for command in proof['commands']:
            need(command['exit_code'] == 0 and command['original_pidfd_retired'] is True and command['timed_out'] is False,
                 'every actual compile/test/completion command must retire successfully')
            for side in ('stdout', 'stderr'):
                name = group + '/' + command['name'] + '.' + side
                need(name in raw and digest(raw[name]) == {key: command[side][key] for key in ('bytes', 'sha256')}, 'whole original command log differs')
            commands.append(command)
    need({c['pid'] for c in commands} <= set(retired['original_PIDs_fresh_ESRCH']), 'all26 original command actors must be independently retired')
    by_name = {command['name']: command for command in commands}
    source = Path('/data/pocket4-runtime-d6-init-metadata-20261113-e2a3-r2/source')
    target = source.parent / 'target'
    harness_rows = successful_cargo_stream(raw['normal/compile-library-harness.stdout'])
    harness = [row for row in harness_rows if row.get('reason') == 'compiler-artifact' and row.get('executable')
               and row['target']['name'] == 'droidloom_supervisor' and row['target']['kind'] == ['lib'] and row['profile']['test'] is True]
    need(len(harness) == 1 and harness[0]['fresh'] is False
         and harness[0]['target']['src_path'] == str(source / 'runtime/droidloom-supervisor/src/lib.rs')
         and harness[0]['executable'] == normal['actual_test_harness']['path']
         and by_name['nine-runtime-input-controls']['argv'][0] == harness[0]['executable'], 'actual fresh original library harness generation required')
    releases = successful_cargo_stream(raw['normal/two-fresh-release-binaries.stdout'])
    selected = [row for row in releases if row.get('reason') == 'compiler-artifact' and row.get('executable')
                and row['target']['name'] in ('droidloom-supervisor', 'droidloomd')]
    need(len(selected) == 2 and {row['target']['name'] for row in selected} == {'droidloom-supervisor', 'droidloomd'}, 'both fresh original release products required')
    need(set(completion['release_binaries']) == {'droidloom-supervisor', 'droidloomd'}
         and retired['fresh_single_link_0555_release_binaries'] == completion['release_binaries'], 'actual independent release-copy retirement required')
    for row in selected:
        name = row['target']['name']
        relative = 'main.rs' if name == 'droidloom-supervisor' else 'bin/droidloomd.rs'
        need(row['target']['kind'] == ['bin'] and row['profile']['test'] is False and row['fresh'] is False
             and row['target']['src_path'] == str(source / 'runtime/droidloom-supervisor/src' / relative)
             and row['executable'] == str(target / 'release' / name), 'exact original fresh Cargo release generation required')
        copied, aliases = completion['release_binaries'][name], completion['original_Cargo_aliases'][name]
        need(copied['identity'][5] == 1 and stat.S_IMODE(copied['identity'][2]) == 0o555
             and copied['sha256'] == aliases['sha256'] and copied['bytes'] == aliases['identity'][6]
             and aliases['all_links_inside_private_target'] is True
             and len(aliases['paths']) == aliases['identity'][5] == 2
             and all(Path(path).is_relative_to(target / 'release') for path in aliases['paths']), 'only the original bounded private Cargo hardlinks may become independent copies')
    need(b'Usage:' in raw['completion/normal-supervisor-help.stdout'], 'actual original supervisor release CLI help required')
    for proof, name in ((normal, 'normal/SOURCE-BEFORE.json'), (completion, 'completion/SOURCE-BEFORE.json'), (retired, 'independent/SOURCE-AFTER.json')):
        claim = proof['source_after' if proof is retired else 'source_before']
        need(all(claim[k] == evidence[name][k] for k in ('bytes', 'sha256')), 'complete430 original source observation must remain bound')
    identities = {
        'normal': ('1a1d722f93f-392-a00', '0b851510596cc2303a02a41e18ffbc82', 1, 1794610868759),
        'completion': ('1a1d72a3008-392-a0b', '5d3edd5edd4fb2944af583de1d1e0cf9', 0, 1794611232307),
        'independent': ('1a1d734bd81-392-a1d', '49c6978bcd15b809d2f4c27d44f26f5b', 0, 1794611922444),
    }
    for group, (job, nonce, exit_code, at) in identities.items():
        request, started, exited = [decode(raw['durable/' + group + '-' + side + '.json']) for side in ('request', 'started', 'exit')]
        need(request['job_id'] == started['job_id'] == exited['job_id'] == job
             and request['launch_nonce'] == started['launch_nonce'] == exited['launch_nonce'] == nonce
             and exited['exit_code'] == exit_code and exited['at_unix_ms'] == at
             and exited['output_complete'] is exited['output_durable'] is True
             and exited['timed_out'] is exited['cancelled'] is False,
             'original durable failed/completed/retired job identities must remain exact')
        for side in ('stdout', 'stderr'):
            need(exited['log_bytes'][side]['seen'] == exited['log_bytes'][side]['stored']
                 and exited['log_synced'][side] is True and exited['log_truncated'][side] is False
                 and exited['log_errors'][side] is None, 'durable original H terminal logs incomplete')
    reader_retired = decode(raw['independent/READER-RETIREMENT.json'])
    need(reader_retired['original_PIDs_fresh_ESRCH'] == [3637250, 3637258]
         and reader_retired['runtime_qualified'] is reader_retired['production_ready'] is False,
         'original independent retirement reader must also retire')
    for side, claim in reader_retired['actual_H_terminal_verified'].items():
        need(all(claim[k] == evidence['durable/independent-' + side + '.json'][k] for k in ('bytes', 'sha256')), 'retirement reader H identity differs')
    metadata = {name: decode(check(HERE / safe(row['path']), row)) for name, row in manifest['original_init_metadata'].items()}
    original = metadata['RESULT-r1.json']
    init = [entry for entry in original['entries'] if entry['member'] == '/system/bin/init']
    need(len(init) == 1 and init[0]['xattrs']['security.selinux']['hex'] == b'u:object_r:init_exec:s0\0'.hex()
         and init[0]['xattrs']['security.selinux']['length'] == 24 and init[0]['xattrs']['security.capability']['present'] is False,
         'original Android init label/capability observation differs')
    for proof in metadata.values():
        need(proof['Android_starts'] == proof['ELF_executions'] == proof['source_image_writes'] == 0
             and proof['ExecutionAdmission_qualified'] is proof['runtime_qualified'] is False, 'original image metadata is not a MAC/Android execution witness')
    return {'historical_actual_tests': 9, 'historical_fresh_release_products': 2, 'historical_commands': 26,
            'original_failed_a00_preserved': True, 'completion_without_recompile_or_retest': True,
            'independently_retired_PIDs': 32, 'independently_retired_cgroups': 6, 'fresh_CI_tests': 0}


def verify_capsule(expected_inventory):
    index = regular(HERE / 'FILES.sha256')
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory) and hashlib.sha256(index).hexdigest() == expected_inventory,
         'externally pinned capsule inventory differs')
    expected = {}
    for line in index.decode().splitlines():
        sha, name = line.split('  ', 1)
        safe(name)
        need(re.fullmatch('[0-9a-f]{64}', sha) and name not in expected and name != 'FILES.sha256', 'unique inventory entry required')
        expected[name] = sha
    actual, directories = member_names(HERE)
    all_names = set(expected) | {'FILES.sha256'}
    expected_directories = {'.'} | {str(parent) for name in all_names for parent in Path(name).parents if str(parent) != '.'}
    need(actual == all_names and set(directories) == expected_directories, 'capsule has missing or extra inputs or directories')
    for name, sha in expected.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'capsule member changed: ' + name)
    manifest = decode(regular(HERE / 'manifest.json'))
    need(manifest['schema'] == 'pocket4-runtime-d6-init-security-metadata-complete430-source-v1', 'complete430 D6 capsule required')
    catalogs = {}
    for label, commit, tree in (('base', BASE_COMMIT, BASE_TREE), ('head', HEAD_COMMIT, HEAD_TREE)):
        item = manifest[label]
        need((item['commit'], item['tree'], item['files']) == (commit, tree, 430), 'fixed source generation required')
        raw = check(HERE / safe(item['raw_commit']['path']), item['raw_commit'])
        header = raw.split(b'\n\n', 1)[0].splitlines()
        need(object_id('commit', raw) == commit and header[0] == ('tree ' + tree).encode()
             and sum(line.startswith(b'tree ') for line in header) == 1, 'original raw commit/root identity differs')
        if label == 'head':
            need([line for line in header if line.startswith(b'parent ')] == [('parent ' + BASE_COMMIT).encode()], 'D6 head must retain exactly the original D5 parent')
        rows = catalog(manifest, label)
        catalogs[label] = validate_rows(rows, 430)
        need(tree_id(rows) == tree, 'entire source membership differs from original Git root')
    changed = {name for name in set(catalogs['base']) | set(catalogs['head']) if catalogs['base'].get(name) != catalogs['head'].get(name)}
    need(changed == {'docs/contracts/runtime-layout-v1.md', 'runtime/droidloom-supervisor/src/production_runtime_assets.rs'}
         and set(catalogs['base']) == set(catalogs['head']) and manifest['unchanged_files'] == 428
         and len(manifest['files']) == 2 and {row['path'] for row in manifest['files']} == changed, 'exact2 changed and428 retained files required')
    need(manifest['producer'] == 'producer', 'one fixed full producer namespace required')
    source_snapshot(HERE / 'producer', catalog(manifest, 'head'), HEAD_TREE)
    for row in manifest['files']:
        need(row['mode'] == '100644', 'D6 metadata delta cannot change executable file modes')
        for label, side, directory in (('base', 'pre', 'preimages'), ('head', 'post', 'producer')):
            original = catalogs[label][row['path']]
            need(row[side] == {key: original[key] for key in ('bytes', 'sha256', 'git_blob')}, 'delta contradicts whole-source inventory')
            check(HERE / directory / safe(row['path']), row[side])
    for name, row in manifest['unchanged_inputs'].items():
        need(catalogs['base'][name] == catalogs['head'][name] == row, 'unchanged admission or dependency boundary differs')
    for key in ('actual_SELinux_transition_qualified', 'ExecutionAdmission_constructible', 'runtime_qualified', 'production_ready', 'fresh_CI_tests_prequalified'):
        need(manifest[key] is False, 'source capsule cannot grant live execution or fresh CI credit')
    need(manifest['Android_builds'] == manifest['Android_starts'] == manifest['host_policy_writes'] == 0, 'ordinary source-only scope required')
    check(HERE / safe(manifest['patch']['path']), manifest['patch'])
    verify_history(manifest)
    return manifest


def replay(manifest, output):
    original = HERE / 'producer'
    output = fresh_destination(output, [HERE])
    base, head = catalog(manifest, 'base'), catalog(manifest, 'head')
    before = source_snapshot(original, head, HEAD_TREE)
    shutil.copytree(original, output, ignore=lambda directory, names: ['.git'] if Path(directory) == original else [])
    need(source_snapshot(original, head, HEAD_TREE) == before, 'complete original input F9 changed while copying')
    copied = source_snapshot(output, head, HEAD_TREE)
    need(all(copied['files'][name][:2] != before['files'][name][:2] for name in before['files']), 'private producer must use independent inodes')
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

    def prove(rows, expected_tree):
        source_snapshot(output, rows, expected_tree)
        git(['add', '--force', '--all'])
        observed = git(['write-tree']).decode().strip()
        need(observed == expected_tree, 'actual complete430 Git root differs')
        return observed

    git(['init', '--quiet', '--template='])
    trees = [prove(head, HEAD_TREE)]
    patch = str(HERE / safe(manifest['patch']['path']))
    for args, rows, expected_tree in ((['--reverse', '--check'], None, None), (['--reverse'], base, BASE_TREE),
                                     (['--check'], None, None), ([], head, HEAD_TREE),
                                     (['--reverse', '--check'], None, None), (['--reverse'], base, BASE_TREE),
                                     (['--check'], None, None), ([], head, HEAD_TREE)):
        git(['apply', *args, patch])
        if rows is not None:
            trees.append(prove(rows, expected_tree))
    need(source_snapshot(original, head, HEAD_TREE) == before, 'all original430 input F9 must remain unchanged after round trip')
    return {'output': str(output), 'base_files': 430, 'head_files': 430, 'actual_Git_root_trees': trees,
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
    parser.add_argument('--tests-log', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    need(args.producer is None or args.output is None, 'producer post-check and fresh replay are separate operations')
    protected = [HERE] + [path.absolute() for path in (args.output, args.producer, args.tests_log) if path is not None]
    if args.report is not None:
        fresh_destination(args.report, protected)
    manifest = verify_capsule(args.inventory_sha256)
    result = {'state': 'EXACT_D6_COMPLETE430_SOURCE_CAPSULE_VERIFIED', 'changed_source_files': 2,
              'historical_actual_host_tests': 9, 'historical_release_products': 2, 'fresh_CI_tests': 0,
              'production_ready': False, 'runtime_qualified': False, 'ExecutionAdmission_constructible': False,
              'actual_SELinux_transition_qualified': False, 'Android_builds_started': 0, 'Android_starts': 0}
    if args.output is not None:
        result['replay'] = replay(manifest, args.output)
    if args.producer is not None:
        snapshot = source_snapshot(args.producer, catalog(manifest, 'head'), HEAD_TREE)
        result['producer'] = {'path': str(args.producer.absolute()), 'file_count': len(snapshot['files']),
                              'root_tree': snapshot['tree'], 'all_bytes_Git_blobs_modes_members_verified': True}
    if args.tests_log is not None:
        raw = regular(args.tests_log)
        result['actual_focused_tests_passed'] = focused_test_log(raw.decode())
        result['observed_focused_test_records'] = 9
        result['test_log'] = digest(raw)
    if args.report is not None:
        write_report(args.report, result, protected)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
