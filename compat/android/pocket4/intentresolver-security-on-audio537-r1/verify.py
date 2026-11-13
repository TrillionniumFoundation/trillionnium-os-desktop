#!/usr/bin/env python3
"""Authenticate and replay the complete Audio537 security producer without Android."""
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
BASE_COMMIT = 'e85ad204e6286be5cba173cc5037884e9fa1ac83'
BASE_TREE = 'e680ae246de9a0edfb1c8aaa9b3e1be392e5d465'
HEAD_COMMIT = '1a5eb38dd809a31b18284839add632a049578f68'
HEAD_TREE = 'c5add898f97018c61515441e689bb854efc793fe'
TESTS = {
    'android::tests::intentresolver_official_git_patch_and_interrupted_recovery_preserve_original',
    'android::tests::intentresolver_changed_provider_source_or_patch_is_rejected_before_projection',
    'android::tests::intentresolver_fixed_request_keeps_audio_source_and_strict_user_command',
    'tests::intentresolver_security_cli_rejects_widening_and_output_aliases',
}


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


def verify_history(manifest):
    docs = {name: decode(check(HERE / safe(row['path']), row)) for name, row in manifest['evidence'].items()}
    ordinary, dma, retired = [docs[n] for n in ('ordinary-325.json', 'ordinary-326.json', 'independent-retirement.json')]
    need(ordinary['base_commit'] == BASE_COMMIT and ordinary['recipe_commit'] == HEAD_COMMIT
         and ordinary['recipe_tree'] == HEAD_TREE and ordinary['actual_distinct_tests_passed'] == 325
         and ordinary['all_1511_producer_files_preserved'] is True and ordinary['errors'] == [], 'actual325 producer evidence differs')
    groups = ordinary['test_runs']
    wanted = {'original_erofs_repack': 1, 'release_queue_2': 2, 'source_42': 42,
              'source_bin_zero': 0, 'source_doc_zero': 0, 'updater_main_280': 280}
    need(set(groups) == set(wanted), 'all actual325 test groups required')
    for name, count in wanted.items():
        row = groups[name]
        need(row['passed'] == len(row['names']) == len(set(row['names'])) == count
             and all(row[k] == 0 for k in ('failed', 'ignored', 'measured')), 'actual325 complete successful group required')
    need(TESTS <= set(groups['updater_main_280']['names']), 'all four security identities required in actual host evidence')
    need(dma['state'] == 'ALL326_REGISTERED_SOURCE_UPDATER_AND_INTEGRATION_TESTS_ACTUALLY_PASSED'
         and dma['actual_distinct_tests_passed'] == 326 and dma['all_registered_ignored_cases_actually_executed'] is True
         and dma['private_original_file_count'] == 103 and dma['private_original_files_unchanged'] is True
         and dma['errors'] == [], 'actual additional original DMA qualification required')
    actual_dma = dma['actual_dma_layout']
    need(actual_dma['names'] == ['dma_heap_video_planes_satisfy_gpu_and_android_layouts']
         and actual_dma['passed'] == 1 and all(actual_dma[k] == 0 for k in ('failed', 'ignored', 'measured', 'filtered')),
         'one real additional DMA test required')
    for claim, name in ((dma['prior325_actual_proof'], 'ordinary-325.json'),
                        (retired['normal325'], 'ordinary-325.json'), (retired['dma326'], 'ordinary-326.json')):
        need(all(claim[k] == manifest['evidence'][name][k] for k in ('bytes', 'sha256')), 'same original evidence chain required')
    need(retired['state'] == 'ACTUAL326_ALL_HARNESSES_RETIRED_AND_ALL1511_SOURCE_FILES_PRESERVED'
         and retired['actual_distinct_tests_passed'] == 326 and retired['all1511_original_recipe_files_unchanged'] is True
         and retired['errors'] == [] and len(retired['original_cgroups_absent']) == 3
         and len(set(retired['original_cgroups_absent'])) == 3
         and len(retired['original_pids_fresh_ESRCH']) == len(set(retired['original_pids_fresh_ESRCH'])) == 38,
         'independent original 38PID and three-cgroup retirement required')
    old_pids = {command['pid'] for proof in (ordinary, dma) for command in proof['commands']}
    need(old_pids <= set(retired['original_pids_fresh_ESRCH']), 'every original normal command must be independently retired')
    for proof in (ordinary, dma, retired):
        need(proof['Android_builds'] == 0 and proof['runtime_qualified'] is False and proof['production_ready'] is False,
             'ordinary host evidence cannot grant runtime credit')
        need(all(c['exit_code'] == 0 and c['original_pidfd_retired'] is True and not c.get('timed_out', False)
                 for c in proof['commands']), 'original qualification command not successful and retired')
    staged = docs['staging.json']
    need(staged['base_commit'] == BASE_COMMIT and staged['base_tree'] == BASE_TREE
         and staged['recipe_commit'] == HEAD_COMMIT and staged['recipe_tree'] == HEAD_TREE
         and staged['all_1508_original_parent_source_files_preserved'] is True
         and staged['all_security_added_removed_lines_match_qualified_original_delta'] is True
         and staged['unchanged_parent_files'] == 1505 and staged['errors'] == [], 'same exact six-file delta staging required')
    return {'actual_host_tests': 326, 'original_PIDs_retired': 38, 'fresh_CI_tests': 0}


def verify_capsule(expected_inventory):
    index = regular(HERE / 'FILES.sha256')
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory)
         and hashlib.sha256(index).hexdigest() == expected_inventory, 'externally pinned capsule inventory differs')
    expected = {}
    for line in index.decode().splitlines():
        sha, name = line.split('  ', 1)
        safe(name)
        need(re.fullmatch('[0-9a-f]{64}', sha) and name not in expected and name != 'FILES.sha256', 'unique inventory entry required')
        expected[name] = sha
    actual, _ = member_names(HERE)
    need(actual == set(expected) | {'FILES.sha256'}, 'capsule has missing or extra inputs')
    for name, sha in expected.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'capsule member changed: ' + name)
    manifest = decode(regular(HERE / 'manifest.json'))
    need(manifest['schema'] == 'pocket4-intentresolver-security-on-audio537-source-v2', 'complete current capsule schema required')
    catalogs = {}
    for label, commit, tree, count in (('base', BASE_COMMIT, BASE_TREE, 1508), ('head', HEAD_COMMIT, HEAD_TREE, 1511)):
        item = manifest[label]
        need((item['commit'], item['tree'], item['files']) == (commit, tree, count), 'fixed source generation required')
        raw = check(HERE / safe(item['raw_commit']['path']), item['raw_commit'])
        need(object_id('commit', raw) == commit and raw.splitlines()[0] == ('tree ' + tree).encode()
             and sum(line.startswith(b'tree ') for line in raw.split(b'\n\n', 1)[0].splitlines()) == 1,
             'original raw commit and root identity differ')
        if label == 'head':
            need(('parent ' + BASE_COMMIT).encode() in raw.split(b'\n\n', 1)[0].splitlines(), 'security head must retain exact Audio537 parent')
        rows = decode(check(HERE / safe(item['inventory']['path']), item['inventory']))
        catalogs[label] = validate_rows(rows, count)
        need(tree_id(rows) == tree, 'entire source membership does not authenticate to original root tree')
    changed = {name for name in set(catalogs['base']) | set(catalogs['head'])
               if catalogs['base'].get(name) != catalogs['head'].get(name)}
    rows = manifest['files']
    need(len(rows) == len({row['path'] for row in rows}) == len(changed) == 6
         and {row['path'] for row in rows} == changed and sum(row['pre'] is not None for row in rows) == 3,
         'exact three changed and three added files required')
    for row in rows:
        need(row['mode'] == '100644', 'security delta cannot change executable modes')
        for label, side, directory in (('base', 'pre', 'preimages'), ('head', 'post', 'source')):
            original = catalogs[label].get(row['path'])
            if original is None:
                need(row[side] is None, 'new security source must have no preimage')
            else:
                need(row[side] == {key: original[key] for key in ('bytes', 'sha256', 'git_blob')}, 'delta contradicts whole-source inventory')
                check(HERE / directory / safe(row['path']), row[side])
    for name, row in manifest['unchanged_inputs'].items():
        need(catalogs['base'][name] == catalogs['head'][name] == row, 'Audio537 source boundary or Cargo lock changed')
    need(all(manifest[k] is False for k in ('APK_built', 'APK_installed', 'production_ready', 'runtime_qualified')),
         'source capsule cannot grant Android or runtime credit')
    check(HERE / safe(manifest['patch']['path']), manifest['patch'])
    verify_history(manifest)
    return manifest


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
    need(len(records) == 4 and {name for name, _ in records} == TESTS and all(status == 'ok' for _, status in records),
         'all four exact security test identities must pass once')
    need(running == ['running 4 tests'] and len(summaries) == 1 and re.fullmatch(
        r'test result: ok\. 4 passed; 0 failed; 0 ignored; 0 measured; \d+ filtered out; finished in [0-9]+(?:\.[0-9]+)?s',
        summaries[0]), 'one complete successful summary without contradictory terminal required')
    return sorted(name for name, _ in records)


def catalog(manifest, label):
    item = manifest[label]['inventory']
    return decode(check(HERE / safe(item['path']), item))


def replay(manifest, output, audio_source):
    audio_source = Path(audio_source).absolute()
    output = fresh_destination(output, [HERE, audio_source])
    base, head = catalog(manifest, 'base'), catalog(manifest, 'head')
    before = source_snapshot(audio_source, base, BASE_TREE)
    shutil.copytree(audio_source, output,
                    ignore=lambda directory, names: ['.git'] if Path(directory) == audio_source else [])
    need(source_snapshot(audio_source, base, BASE_TREE) == before, 'Audio input F9 changed during complete copy')
    copied = source_snapshot(output, base, BASE_TREE)
    need(all(copied['files'][name][:2] != before['files'][name][:2] for name in before['files']), 'copied producer must have independent inodes')
    need(not os.path.lexists(output / '.git'), 'Audio root Git metadata must not be copied')
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null', GIT_OPTIONAL_LOCKS='0')
    commands = []

    def git(args):
        argv = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.filemode=true', '-c', 'core.autocrlf=false', *args]
        run = subprocess.run(argv, cwd=output, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=120, umask=0o022)
        commands.append({'argv': argv, 'exit_code': run.returncode, 'stdout': digest(run.stdout), 'stderr': digest(run.stderr)})
        need(run.returncode == 0, 'normal Git replay failed: ' + run.stderr.decode(errors='replace'))
        return run.stdout

    def prove(rows, expected_tree):
        source_snapshot(output, rows, expected_tree)
        git(['add', '--force', '--all'])
        observed = git(['write-tree']).decode().strip()
        need(observed == expected_tree, 'actual complete Git root tree differs')
        return observed

    git(['init', '--quiet', '--template='])
    trees = [prove(base, BASE_TREE)]
    patch = str(HERE / safe(manifest['patch']['path']))
    for args, rows, expected_tree in ((['--check'], None, None), ([], head, HEAD_TREE),
                                     (['--reverse', '--check'], None, None), (['--reverse'], base, BASE_TREE),
                                     (['--check'], None, None), ([], head, HEAD_TREE)):
        git(['apply', *args, patch])
        if rows is not None:
            trees.append(prove(rows, expected_tree))
    need(source_snapshot(audio_source, base, BASE_TREE) == before, 'all original Audio input F9 must remain unchanged after round trip')
    return {'output': str(output), 'base_files': 1508, 'head_files': 1511,
            'actual_Git_root_trees': trees, 'git_commands': commands, 'input_F9_preserved': True,
            'skipped_only_root_git': True, 'private_Git_reconstructed': True, 'Git_child_umask': '0022',
            'full_forward_reverse_forward_replay': True, 'Rust_tests_run': False}


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
    parser.add_argument('--audio-source', type=Path)
    parser.add_argument('--producer', type=Path)
    parser.add_argument('--tests-log', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    need((args.output is None) == (args.audio_source is None), 'full Audio input and fresh replay output must be supplied together')
    need(args.producer is None or args.output is None, 'producer post-check and fresh replay are separate operations')
    protected = [HERE] + [path.absolute() for path in (args.audio_source, args.output, args.producer, args.tests_log) if path is not None]
    if args.report is not None:
        fresh_destination(args.report, protected)
    manifest = verify_capsule(args.inventory_sha256)
    result = {'state': 'EXACT_SECURITY537_COMPLETE_SOURCE_CAPSULE_VERIFIED', 'changed_source_files': 6,
              'historical_actual_host_tests': 326, 'fresh_CI_tests': 0,
              'production_ready': False, 'runtime_qualified': False, 'Android_builds_started': 0}
    if args.output is not None:
        result['replay'] = replay(manifest, args.output, args.audio_source)
    if args.producer is not None:
        snapshot = source_snapshot(args.producer, catalog(manifest, 'head'), HEAD_TREE)
        result['producer'] = {'path': str(args.producer.absolute()), 'file_count': len(snapshot['files']),
                              'root_tree': snapshot['tree'], 'all_bytes_Git_blobs_modes_members_verified': True}
    if args.tests_log is not None:
        raw = regular(args.tests_log)
        result['actual_focused_tests_passed'] = focused_test_log(raw.decode())
        result['observed_focused_test_records'] = 4
        result['test_log'] = digest(raw)
    if args.report is not None:
        write_report(args.report, result, protected)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
