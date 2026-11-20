#!/usr/bin/env python3
"""Replay all four reviewed source deltas against their one complete2352 parent."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).resolve().parent
PARENT_TREE = '7bfb70d7107cb5c95e9aec307124e1369aa735d1'
PARENT_PACKET = {'inventory_sha256': '9c1c330bd29ea6d2bdbcde0ead6e27bafaaab07177fb22a6f90ef81c967466a2', 'verify_sha256': 'd81a4160496ef388559a598ba24e9faa0807b0deafb1536f586ca5b98427ba20', 'source_tree': '7bfb70d7107cb5c95e9aec307124e1369aa735d1', 'source_files': 2352, 'source_bytes': 44260146}
PARENT_ROWS = {'path': 'PARENT-SOURCE-ROWS.json', 'bytes': 700253, 'sha256': '3a7eeac592a39840d330e54db18002f4216cf900ce96d52359210fcbf402401c'}
COMPONENTS = [{'name': 'lint', 'review': {'path': 'component-reviews/lint.json', 'bytes': 10746, 'sha256': 'ee8d9eed8510d94188895851f797cd0828e6ca58c9138fa50e0ffa22062cbedd'}, 'rows': {'bytes': 700769, 'sha256': '459b7dc122c4afbbd128e1812a48ba374eb8855c355bd2645fe408fc2b5c0fe6'}, 'patch': {'bytes': 440252, 'sha256': '3050a4fb3bfcb70492fff1cb9c7fa33ca8de8b6ce812dc95b61511e90f738878'}, 'addition_patch_header': 'prefix_a', 'source': {'tree': 'deec841ee7cabd33e9c7d061c5498331c0729d90', 'files': 2354, 'bytes': 44676502}, 'changed_paths': ['tools/droidloom-source/src/lib.rs', 'tools/droidloom-source/src/main.rs', 'tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/coherent_images.rs', 'tools/droidloom-update/src/coherent_images_tests.rs', 'tools/droidloom-update/src/framework_asb_security.rs', 'tools/droidloom-update/src/production_source.rs', 'tools/droidloom-update/src/settings_asb_security_tests.rs', 'tools/droidloom-update/src/wm_security.rs'], 'added_paths': ['android/manifest/production-full-lint-source-lock.json', 'tools/droidloom-source/src/production_lint.rs']}, {'name': 'image_custody', 'review': {'path': 'component-reviews/image_custody.json', 'bytes': 12782, 'sha256': 'ee6addc679cb53697a237eb85807f5e0fad1a05b2efda07ffc49350cbdc69dac'}, 'rows': {'bytes': 701604, 'sha256': '5e406c5ce240c6c5cea80de36fe37a95cd5c5f8599fac3c14b96166eb528c6c0'}, 'patch': {'bytes': 70657, 'sha256': 'd15ca18dff9d103b033fb572149e6bcd67f3f41ed5ddbd423cfc94dc2ef1c273'}, 'addition_patch_header': 'dev_null', 'source': {'tree': 'c9966bf21016d49f4975c4d12af1cf419893e61c', 'files': 2357, 'bytes': 44321077}, 'changed_paths': ['runtime/droidloom-applications/src/main.rs', 'runtime/droidloom-applications/src/runtime_plan.rs', 'runtime/droidloom-supervisor/src/control.rs', 'runtime/droidloom-supervisor/src/control_progress.rs', 'runtime/droidloom-supervisor/src/production_application.rs', 'runtime/droidloom-supervisor/src/production_cell.rs', 'runtime/droidloom-supervisor/src/production_control.rs', 'runtime/droidloom-supervisor/src/production_mounts.rs', 'runtime/droidloom-supervisor/src/production_namespace_application_parent.rs'], 'added_paths': ['runtime/droidloom-supervisor/src/application_custody.rs', 'runtime/droidloom-supervisor/src/application_custody_tests.rs', 'runtime/droidloom-supervisor/src/production_application_custody.rs', 'runtime/droidloom-supervisor/src/production_mounts_custody.rs', 'runtime/droidloom-supervisor/src/production_namespace_image_custody.rs']}, {'name': 'proc_masks', 'review': {'path': 'component-reviews/proc_masks.json', 'bytes': 8499, 'sha256': 'ba5691438f6da9b099140f7187e6179b4a94679473b727adec57ec72a7889af0'}, 'rows': {'bytes': 700253, 'sha256': '772aa885c8d2647d474575ac25d7480980c59f4481765a4bc29b0d225c69aa1b'}, 'patch': {'bytes': 14458, 'sha256': 'a162038fda902edd3c5eb7d0146a4691692ce0b58f85011d7b2c0096bd749ee7'}, 'addition_patch_header': 'dev_null', 'source': {'tree': '62380cd8a0ee9a6770b72cfda597ee84c140828a', 'files': 2352, 'bytes': 44266083}, 'changed_paths': ['runtime/droidloom-supervisor/src/production_namespace_writable_proc_child.rs', 'runtime/droidloom-supervisor/src/production_namespace_writable_proc_parent.rs'], 'added_paths': []}, {'name': 'backing_custody', 'review': {'path': 'component-reviews/backing_custody.json', 'bytes': 9803, 'sha256': '42f79ea20b100fe8d48741fda8ab776ef50cdc13597be168a2185eba5276bdbb'}, 'rows': {'bytes': 700524, 'sha256': 'd00005cde6963a7f1c54c9405534f6a894da4b13503eed04dce1635e032ef7af'}, 'patch': {'bytes': 20417, 'sha256': '8a1517c22de8eb52c0808ab394c437f3794c19a9b7fe6fa0682b44d61708e7ce'}, 'addition_patch_header': 'dev_null', 'source': {'tree': 'f81f82393cf2f95fab7f9d00145add9cadd2821c', 'files': 2353, 'bytes': 44273691}, 'changed_paths': ['runtime/droidloom-supervisor/src/production_identity.rs'], 'added_paths': ['runtime/droidloom-supervisor/src/production_identity_backings.rs']}]
CHANGED_PATH = 'runtime/droidloom-applications/src/leaf_routes.rs'
CHANGED_PATHS = ['runtime/droidloom-applications/src/main.rs', 'runtime/droidloom-applications/src/runtime_plan.rs', 'runtime/droidloom-supervisor/src/control.rs', 'runtime/droidloom-supervisor/src/control_progress.rs', 'runtime/droidloom-supervisor/src/production_application.rs', 'runtime/droidloom-supervisor/src/production_cell.rs', 'runtime/droidloom-supervisor/src/production_control.rs', 'runtime/droidloom-supervisor/src/production_identity.rs', 'runtime/droidloom-supervisor/src/production_mounts.rs', 'runtime/droidloom-supervisor/src/production_namespace_application_parent.rs', 'runtime/droidloom-supervisor/src/production_namespace_writable_proc_child.rs', 'runtime/droidloom-supervisor/src/production_namespace_writable_proc_parent.rs', 'tools/droidloom-source/src/lib.rs', 'tools/droidloom-source/src/main.rs', 'tools/droidloom-update/src/android.rs', 'tools/droidloom-update/src/coherent_images.rs', 'tools/droidloom-update/src/coherent_images_tests.rs', 'tools/droidloom-update/src/framework_asb_security.rs', 'tools/droidloom-update/src/production_source.rs', 'tools/droidloom-update/src/settings_asb_security_tests.rs', 'tools/droidloom-update/src/wm_security.rs']
ADDED_PATHS = ['android/manifest/production-full-lint-source-lock.json', 'runtime/droidloom-supervisor/src/application_custody.rs', 'runtime/droidloom-supervisor/src/application_custody_tests.rs', 'runtime/droidloom-supervisor/src/production_application_custody.rs', 'runtime/droidloom-supervisor/src/production_identity_backings.rs', 'runtime/droidloom-supervisor/src/production_mounts_custody.rs', 'runtime/droidloom-supervisor/src/production_namespace_image_custody.rs', 'tools/droidloom-source/src/production_lint.rs']
SOURCE_TREE = '56548053c91840f2dd3de50db45b705069d35fa9'
SOURCE_FILES = 2360
SOURCE_BYTES = 44756915
SOURCE_SCOPE = {'source_only': True, 'Rust_compilation_claimed': False, 'Rust_test_execution_claimed': False, 'historical_tests_counted_as_fresh': False, 'Android_builds': 0, 'Android_starts': 0, 'APK_installs': 0, 'live_image_custody_observed': False, 'business_qualified': False, 'runtime_qualified': False, 'production_ready': False, 'activated': False}


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


def write_report(path, value, protected):
    path = fresh_destination(path, protected); path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
    finally: os.close(fd)


def strict_patch(before, patch, relative=CHANGED_PATH):
    """Apply only exact line-numbered hunks; no fuzz, offsets or extra files."""
    lines = patch.splitlines(keepends=True)
    need(lines[:2] == [('--- a/' + relative + '\n').encode(),
                       ('+++ b/' + relative + '\n').encode()],
         'patch must name only the exact source file')
    original = before.splitlines(keepends=True)
    result = []
    cursor = 0
    index = 2
    hunks = 0
    while index < len(lines):
        match = re.fullmatch(rb'@@ -(\d+),(\d+) \+(\d+),(\d+) @@[^\n]*\n', lines[index])
        need(match is not None, 'exact bounded unified hunk required')
        old_start, old_count, new_start, new_count = map(int, match.groups())
        need(old_start >= cursor + 1 and old_count > 0 and new_count > 0,
             'ordered nonempty exact hunks required')
        result.extend(original[cursor:old_start - 1])
        cursor = old_start - 1
        need(new_start == len(result) + 1, 'patch output line position differs')
        used = added = 0
        index += 1
        while index < len(lines) and not lines[index].startswith(b'@@ '):
            line = lines[index]
            need(line[:1] in (b' ', b'+', b'-') and line.endswith(b'\n'),
                 'ordinary complete patch lines required')
            if line[:1] in (b' ', b'-'):
                need(cursor < len(original) and original[cursor] == line[1:],
                     'patch context or removed line differs')
                cursor += 1
                used += 1
            if line[:1] in (b' ', b'+'):
                result.append(line[1:])
                added += 1
            index += 1
        need((used, added) == (old_count, new_count), 'hunk line counts differ')
        hunks += 1
    need(hunks > 0, 'nonempty exact patch required')
    result.extend(original[cursor:])
    return b''.join(result)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def verify_packet(expected_inventory_sha):
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory_sha), 'external source inventory SHA required')
    names, directories = member_names(HERE)
    identities = {name: f9((HERE / name).lstat()) for name in names}
    index = regular(HERE / 'FILES.sha256', 65536)
    need(hashlib.sha256(index).hexdigest() == expected_inventory_sha, 'external combined source pin differs')
    inventory = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^\r\n]+)', line)
        need(match is not None, 'exact source inventory row required')
        name = match[2]
        safe(name)
        need(name not in inventory and name != 'FILES.sha256', 'unique nonrecursive source member required')
        inventory[name] = match[1]
    need(names == set(inventory) | {'FILES.sha256'}, 'complete combined source packet membership differs')
    for name, expected in inventory.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == expected, 'source packet member differs: ' + name)
    manifest = decode(regular(HERE / 'MANIFEST.json'))
    need(set(manifest) == {'schema', 'parent_packet', 'parent_rows', 'components', 'changes',
                          'additions', 'successor', 'scope'}, 'exact combined source manifest fields required')
    need(manifest['schema'] == 'p4-combined-runtime-source-successor-v1'
         and manifest['parent_packet'] == PARENT_PACKET and manifest['parent_rows'] == PARENT_ROWS
         and manifest['components'] == COMPONENTS
         and manifest['successor'] == {'source_tree': SOURCE_TREE, 'source_files': SOURCE_FILES,
                                      'source_bytes': SOURCE_BYTES}
         and manifest['scope'] == SOURCE_SCOPE, 'frozen parent, components, source or holds differ')
    before = decode(check(HERE / PARENT_ROWS['path'], PARENT_ROWS))
    old = validate_rows(before, 2352)
    need(tree_id(before) == PARENT_TREE and sum(row['bytes'] for row in before) == 44260146,
         'complete common2352 parent required')
    changes = manifest['changes']; additions = manifest['additions']
    need(isinstance(changes, list) and [r['path'] for r in changes] == CHANGED_PATHS
         and isinstance(additions, list) and [r['path'] for r in additions] == ADDED_PATHS,
         'only all frozen disjoint source postimages may change')
    mapped_changes = {}; mapped_additions = {}; patches = {}; payloads = {}
    for row in changes:
        need(set(row) == {'component', 'path', 'before', 'after', 'patch'}, 'exact changed source fields required')
        path = row['path']; safe(path)
        need(row['before'] == old[path] and row['after']['path'] == path
             and row['after']['mode'] == row['before']['mode'], 'exact preimage and unchanged source mode required')
        validate_rows([row['after']], 1)
        need(path not in mapped_changes and row['patch']['path'] == 'patches/' + path + '.patch',
             'unique canonical per-file patch required')
        mapped_changes[path] = row
        patches[path] = check(HERE / row['patch']['path'], row['patch'])
    for row in additions:
        need(set(row) == {'component', 'path', 'after', 'payload'}, 'exact added source fields required')
        path = row['path']; safe(path)
        need(path not in old and path not in mapped_additions and row['after']['path'] == path
             and row['after']['mode'] == '100644' and row['payload']['path'] == 'additions/' + path,
             'unique reviewed ordinary addition required')
        validate_rows([row['after']], 1)
        raw = check(HERE / row['payload']['path'], row['payload'])
        need(digest(raw) == {k: row['after'][k] for k in ('bytes', 'sha256')}
             and object_id('blob', raw) == row['after']['git_blob'], 'complete added postimage differs')
        mapped_additions[path] = row; payloads[path] = raw
    seen = set()
    for component in COMPONENTS:
        review = decode(check(HERE / component['review']['path'], component['review']))
        need(review['parent_tree'] == PARENT_TREE and review['parent_files'] == 2352
             and review['parent_bytes'] == 44260146 and review['closed_full_source_snapshot'] is True
             and review['parent_full_f9_bookend_unchanged'] is True
             and review['rust_compilation_passed'] is False and review['rust_tests_executed'] is False
             and review['runtime_qualified'] is False and review['production_ready'] is False,
             'component must remain its exact source-only parent observation')
        need(review['changed_paths'] == component['changed_paths']
             and review['added_paths'] == component['added_paths'], 'component path scope differs')
        paths = sorted(component['changed_paths'] + component['added_paths'])
        need(not seen.intersection(paths), 'independent source components overlap')
        seen.update(paths)
        postimages = review['postimages']
        need([r['after']['path'] for r in postimages] == paths, 'complete component postimage roster required')
        altered = {}; added = []; exact_patch = []
        for item in postimages:
            path = item['after']['path']
            if path in old:
                row = mapped_changes[path]
                need(row['component'] == component['name'] and item == {'before': row['before'], 'after': row['after']},
                     'reviewed source patch preimage or postimage differs')
                altered[path] = row['after']; exact_patch.append(patches[path])
            else:
                row = mapped_additions[path]
                need(row['component'] == component['name'] and item == {'before': None, 'after': row['after']},
                     'reviewed added source postimage differs')
                added.append(row['after'])
                exact_patch.append(''.join(difflib.unified_diff([], payloads[path].decode('utf-8', 'strict').splitlines(True),
                    fromfile='/dev/null' if component['addition_patch_header'] == 'dev_null' else 'a/' + path,
                    tofile='b/' + path)).encode())
        component_rows = sorted([altered.get(r['path'], r) for r in before] + added, key=lambda r: r['path'])
        validate_rows(component_rows, component['source']['files'])
        need(tree_id(component_rows) == component['source']['tree'] == review['candidate_tree']
             and len(component_rows) == review['candidate_files']
             and sum(r['bytes'] for r in component_rows) == component['source']['bytes'] == review['candidate_bytes']
             and digest(json_bytes(component_rows)) == component['rows']
             and digest(b''.join(exact_patch)) == component['patch'],
             'complete original reviewed component tree, row bytes or canonical patch differs')
    need(seen == set(CHANGED_PATHS) | set(ADDED_PATHS), 'component union does not close the combined delta')
    after = sorted([mapped_changes[r['path']]['after'] if r['path'] in mapped_changes else r for r in before]
                   + [r['after'] for r in additions], key=lambda r: r['path'])
    validate_rows(after, SOURCE_FILES)
    need(tree_id(after) == SOURCE_TREE and sum(r['bytes'] for r in after) == SOURCE_BYTES,
         'unique complete combined source tree differs')
    need(next(r for r in after if r['path'] == 'Cargo.lock') == old['Cargo.lock'], 'original Cargo lockfile must stay unchanged')
    after_names, after_directories = member_names(HERE)
    need(names == after_names and directories == after_directories
         and all(f9((HERE / name).lstat()) == identity for name, identity in identities.items()),
         'source packet changed during complete verification')
    return {'manifest': manifest, 'before': before, 'after': after, 'patches': patches, 'added': payloads,
            'inventory_sha256': expected_inventory_sha,
            'packet_snapshot': {'files': identities, 'directories': directories}}


def verify_parent_packet(path, packet):
    """Authenticate the entire64f -> materialization -> leaf2352 source chain."""
    path = Path(path).absolute()
    raw = regular(path / 'verify.py')
    need(hashlib.sha256(raw).hexdigest() == PARENT_PACKET['verify_sha256'], 'exact complete-cohort parent verifier required')
    need(hashlib.sha256(regular(path / 'FILES.sha256')).hexdigest() == PARENT_PACKET['inventory_sha256'],
         'exact complete-cohort parent inventory required')
    spec = importlib.util.spec_from_file_location('combined_source_complete_current_parent', path / 'verify.py')
    parent = importlib.util.module_from_spec(spec); spec.loader.exec_module(parent)
    need(regular(path / 'verify.py') == raw, 'parent verifier changed during import')
    verified = parent.verify_capsule(PARENT_PACKET['inventory_sha256'])
    need(verified['rows'] == packet['before'] and parent.HEAD_TREE == PARENT_TREE,
         'complete parent source chain does not end at the common2352 tree')
    return parent, verified


def replay(packet, parent_source, output):
    parent_source = Path(parent_source).absolute()
    before_snapshot = source_snapshot(parent_source, packet['before'], PARENT_TREE)
    output = fresh_destination(output, [HERE, parent_source])
    changed = {}
    for change in packet['manifest']['changes']:
        name = change['path']; before = check(parent_source / name, change['before'])
        raw = strict_patch(before, packet['patches'][name], name)
        need(digest(raw) == {k: change['after'][k] for k in ('bytes', 'sha256')}
             and object_id('blob', raw) == change['after']['git_blob'], 'strict combined patch postimage differs')
        changed[name] = raw
    output.mkdir(mode=0o700)
    for row in packet['after']:
        name = row['path']
        raw = packet['added'][name] if name in packet['added'] else changed[name] if name in changed else check(parent_source / name, row)
        dest = output / safe(name); dest.parent.mkdir(parents=True, exist_ok=True)
        need(dest.parent.resolve() == dest.parent, 'new complete output parent alias rejected')
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(os.dup(fd), 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.fchmod(fd, int(row['mode'], 8) & 0o777)
        finally:
            os.close(fd)
    need(source_snapshot(parent_source, packet['before'], PARENT_TREE) == before_snapshot,
         'common parent source changed during complete composition')
    current = source_snapshot(output, packet['after'], SOURCE_TREE)
    return {'parent_snapshot': before_snapshot, 'source_snapshot': current}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory-sha256', required=True)
    parser.add_argument('--parent-packet', type=Path, required=True)
    parser.add_argument('--parent-source', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--producer', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    packet = verify_packet(args.inventory_sha256)
    parent, parent_packet = verify_parent_packet(args.parent_packet, packet)
    protected = [HERE, args.parent_packet, parent.ORIGINAL, parent.MATERIALIZATION, parent.LEAF]
    result = {'schema': 'p4-combined-runtime-source-replay-v1', 'state': 'COMPLETE',
              'packet_inventory_sha256': args.inventory_sha256, 'parent_packet_verified': True,
              'parent_tree': PARENT_TREE, **packet['manifest']['successor'],
              'changed_paths': CHANGED_PATHS, 'added_paths': ADDED_PATHS, **SOURCE_SCOPE}
    if args.output:
        need(args.parent_source is not None, 'complete common parent source required for composition')
        fresh_destination(args.output, protected)
        result.update(replay(packet, args.parent_source, args.output))
        protected += [args.parent_source, args.output]
    else:
        need(args.parent_source is None, 'no parent source with verify-only mode')
        result['source_snapshot'] = source_snapshot(args.producer, packet['after'], SOURCE_TREE)
        protected.append(args.producer)
    after = verify_packet(args.inventory_sha256)
    need(after['packet_snapshot'] == packet['packet_snapshot'], 'source packet F9 bookend differs')
    _, parent_after = verify_parent_packet(args.parent_packet, packet)
    need(parent_after['rows'] == parent_packet['rows'] and parent_after['source_chain'] == parent_packet['source_chain'],
         'complete parent source chain changed during composition')
    write_report(args.report, result, protected)
    print(json.dumps({k: v for k, v in result.items() if k not in ('parent_snapshot', 'source_snapshot')}, sort_keys=True))


if __name__ == '__main__':
    main()
