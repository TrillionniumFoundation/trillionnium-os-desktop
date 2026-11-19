#!/usr/bin/env python3
"""Verify and reconstruct the complete current source capsule for CI."""
import argparse
import base64
import io
import tarfile
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

HERE = Path(__file__).resolve().parent
PARENT_COMMIT = '8ddad986410bddb5c42bc5549513a3ee5e41327b'
PARENT_TREE = 'ed4664376e9c4b60de0f4359753862425ab41d75'
HEAD_COMMIT = None
HEAD_TREE = '28c270a8e32478e6789c8319b0df164b67268224'
SOURCE_FILES = 2350
SOURCE_BYTES = 44156524


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


def successful_cargo_stream(raw):
    rows=[decode(line) for line in raw.decode().splitlines() if line]
    terminals=[row for row in rows if row.get('reason')=='build-finished']
    need(rows and terminals==[{'reason':'build-finished','success':True}] and rows[-1]==terminals[0],
         'one complete successful Cargo terminal required')
    need(not any(row.get('reason')=='compiler-message' and row.get('message',{}).get('level')=='error' for row in rows),
         'successful Cargo stream contains an error')
    return rows


def test_terminal(text, passed, ignored=(), filtered=None, *, catalog=None):
    passed, ignored = set(passed), set(ignored)
    need(not passed.intersection(ignored), 'passed and ignored identities must be distinct')
    total = len(passed) + len(ignored)
    # The caller supplies the full name set already joined to the actual ELF.
    # Do not infer that catalog from a child transcript or its reported counts.
    if catalog is not None:
        need(isinstance(catalog, (list, tuple)) and all(type(name) is str for name in catalog)
             and len(catalog) == len(set(catalog)), 'distinct complete caller-bound catalog names required')
        catalog = set(catalog)
        need((passed | ignored) <= catalog and type(filtered) is int and filtered >= 0
             and total + filtered == len(catalog), 'parent identities and filters must match the bound catalog')
    # These two frozen updater tests run the same catalogued ELF inside fakeroot.
    # Their child records are evidence of the parent's work, never extra credit.
    image_case = 'image_policy::tests::repack_preserves_android_metadata_and_adbd'
    staging_case = 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
    tool_case = 'native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair'
    nested_cases = {image_case, staging_case}
    # Exact observed banners only: private official Ubuntu erofs-utils 1.9.1
    # prints 1.9; the pinned CI tool prints 1.9.4. Parent/child phases and all
    # exact Rust catalog, status, count and terminal checks remain unchanged.
    tool_line = re.compile(
        r'(?:mkfs\.erofs (?:1\.9|1\.9\.4)|Processing [^\r\n]+ \.\.\.|Build completed\.|------|'
        r'Filesystem UUID: [0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|'
        r'Filesystem total blocks: [0-9]+ \(of [0-9]+-byte blocks\)|'
        r'Filesystem total (?:inodes|metadata blocks): [0-9]+|'
        r'Filesystem total deduplicated bytes \(of source files\): [0-9]+)')

    def summary(line, expected_passed, expected_ignored, expected_filtered):
        match = re.fullmatch(
            r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored; 0 measured; '
            r'(\d+) filtered out; finished in [0-9]+(?:\.[0-9]+)?s', line)
        need(match is not None and int(match[1]) == expected_passed
             and int(match[2]) == expected_ignored, 'successful Rust summary must equal every actual record')
        need(expected_filtered is None or int(match[3]) == expected_filtered, 'unexpected Rust filter count')
        return int(match[3])

    records = {}

    def record(name, status):
        need(name not in records and ((status == 'ok' and name in passed)
             or (status == 'ignored' and name in ignored)), 'unique exact Rust identity/status required')
        records[name] = status

    started = finished = False
    pending = phase = outer_filtered = None
    for line in text.splitlines():
        if not line:
            continue
        need(not finished, 'unexpected output after the complete parent Rust harness')
        if line.startswith('running '):
            if not started:
                need(line == f'running {total} ' + ('test' if total == 1 else 'tests'),
                     'exact parent Rust running count required')
                started = True
            else:
                need(pending in nested_cases and phase == 'child-header' and line == 'running 1 test',
                     'unknown, extra or misplaced nested Rust harness')
                phase = 'child-record'
        elif line.startswith('test result:'):
            need(started, 'Rust summary before parent header')
            if pending is not None:
                need(pending in nested_cases and phase == 'child-summary', 'unclosed or extra nested Rust summary')
                summary(line, 1, 0, len(catalog) - 1)
                phase = 'parent-status'
            else:
                outer_filtered = summary(line, len(passed), len(ignored), filtered)
                need(set(records) == passed | ignored, 'parent summary precedes complete exact Rust records')
                finished = True
        elif line.startswith('test '):
            need(started, 'Rust record before parent header')
            match = re.fullmatch(r'test (\S+) \.\.\. (.*)', line)
            need(match is not None, 'malformed Rust test record')
            name, tail = match.groups()
            if pending is not None:
                need(phase == 'child-record' and pending in nested_cases and name == pending and tail == 'ok',
                     'nested Rust record must be exactly one successful same-name child')
                phase = 'child-summary'
                continue
            status = re.fullmatch(r'(ok|FAILED|ignored)(?:, (.+))?', tail)
            if status is not None:
                need(status[2] is None or status[1] == 'ignored', 'unexpected test reason')
                record(name, status[1])
            else:
                need(name in passed and name not in records, 'unknown or duplicate open parent Rust test')
                if name in nested_cases and tail == '':
                    need(catalog is not None,
                         'nested child must belong to the complete pinned updater catalog')
                    pending, phase = name, 'child-header'
                else:
                    need(name == tool_case and tail in ('mkfs.erofs 1.9', 'mkfs.erofs 1.9.4'), 'unknown split Rust test record')
                    pending, phase = name, 'tool-output'
        elif line == 'ok':
            need(pending is not None and phase in ('parent-status', 'tool-output'),
                 'standalone status without a completed known parent operation')
            record(pending, 'ok')
            pending = phase = None
        else:
            need((phase == 'tool-output' or (pending == image_case and phase == 'child-record'))
                 and tool_line.fullmatch(line) is not None, 'unexpected Rust or tool output')
    need(started and finished and pending is None and set(records) == passed | ignored,
         'exactly one complete parent Rust harness and all known children required')
    return {'passed': sorted(passed), 'ignored': sorted(ignored), 'filtered': outer_filtered}


CAPSULE = {'bytes': 7894116, 'sha256': '3e8b2fa1ea1ef3555ca7c82e27abe79a2be029c701f69ac55ef4c82484f247ad'}
MANIFEST = {'bytes': 696880, 'sha256': '715560653e4c988287555527325f992fb1b5f53bdd48d38b7823c43b4cf5b1f3'}
COMMIT = {'bytes': 775, 'sha256': '02db7881289cc5706d62261f8f7933b4e78f4ddd29bc13ee1ed5846807281959'}


def archive_entries(raw):
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:xz') as archive:
        members = archive.getmembers()
        need(len(members) == 2304 and sum(m.size for m in members) == 43326353,
             'complete bounded current source archive required')
        for member in members:
            safe(member.name)
            need(member.isfile() and not member.linkname and member.name not in entries
                 and 0 <= member.size <= 64 * 1024 * 1024, 'unique ordinary source members only')
            body = archive.extractfile(member).read(member.size + 1)
            need(len(body) == member.size, 'whole archive member required')
            entries[member.name] = (member.mode, body)
    return entries


OVERLAY = {'bytes': 648532, 'sha256': 'b0d7468131ae5a43c29b7188d2e2633810333693c603c0b4c5a422ac5513b7d0'}
OVERLAY_PATH = 'SOURCE-OVERLAY.tar.xz'
OVERLAY_PATHS = 106
OVERLAY_EXPANSION_MAX = 5 * 1024 * 1024


def overlay_packet(raw):
    need(isinstance(raw, bytes) and 0 < len(raw) <= OVERLAY['bytes'],
         'bounded complete overlay frame required')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=64 * 1024 * 1024)
    body = decoder.decompress(raw, max_length=OVERLAY_EXPANSION_MAX + 1)
    need(decoder.eof and not decoder.unused_data and len(body) <= OVERLAY_EXPANSION_MAX,
         'one complete bounded XZ overlay without trailing frames required')
    # Whole binary postimages avoid base64's wire expansion. The original
    # single-frame 5 MiB expansion and 64 MiB decoder bounds stay unchanged.
    # Accept only contiguous canonical USTAR regular files, no extension
    # headers, links, implicit directories, alternate archives or trailing data.
    need(len(body) % 512 == 0, 'overlay USTAR blocks must be complete')
    extracted = {}
    next_offset = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode='r:') as archive:
            members = archive.getmembers()
            need(len(members) == OVERLAY_PATHS + 1, 'exact overlay USTAR member count')
            for member in members:
                safe(member.name)
                need(member.name not in extracted and member.isreg()
                     and not member.linkname and not member.pax_headers
                     and member.uid == member.gid == member.mtime == 0
                     and member.uname == member.gname == ''
                     and member.devmajor == member.devminor == 0
                     and member.mode in (0o644, 0o755)
                     and 0 <= member.size <= OVERLAY_EXPANSION_MAX,
                     'canonical distinct regular overlay members required')
                need(member.offset == next_offset
                     and member.offset_data == member.offset + 512,
                     'overlay extension headers or member gaps are forbidden')
                header = body[member.offset:member.offset + 512]
                need(header[156:157] in (b'0', b'\0')
                     and header[257:263] == b'ustar\0' and header[263:265] == b'00',
                     'one canonical USTAR header per overlay file required')
                data = archive.extractfile(member).read(member.size + 1)
                need(len(data) == member.size, 'whole overlay member required')
                next_offset = member.offset_data + ((member.size + 511) // 512) * 512
                need(not any(body[member.offset_data + member.size:next_offset]),
                     'overlay member padding must be zero')
                extracted[member.name] = (member.mode, data)
    except (tarfile.TarError, EOFError) as error:
        raise RuntimeError('invalid complete overlay USTAR archive') from error
    need(len(body) - next_offset >= 1024 and not any(body[next_offset:]),
         'overlay must end with only complete zero trailer blocks')
    need('OVERLAY-MANIFEST.json' in extracted
         and extracted['OVERLAY-MANIFEST.json'][0] == 0o644,
         'exact overlay manifest member required')
    manifest = decode(extracted.pop('OVERLAY-MANIFEST.json')[1])
    need(isinstance(manifest, dict) and isinstance(manifest.get('paths'), dict),
         'overlay manifest must declare its exact path set')
    encoded = {}
    for name, (mode, data) in extracted.items():
        need(name.startswith('postimages/'), 'undeclared overlay member prefix')
        relative = name[len('postimages/'):]
        safe(relative)
        change = manifest['paths'].get(relative)
        need(isinstance(change, dict) and isinstance(change.get('after'), dict)
             and change['after'].get('git_mode') == format(0o100000 | mode, 'o'),
             'overlay member mode must match its exact declared postimage')
        encoded[relative] = base64.b64encode(data).decode('ascii')
    need(set(encoded) == set(manifest['paths']), 'all and only declared overlay members required')
    return {'manifest': manifest, 'files_base64': encoded}


def apply_overlay(parent, parent_rows, parent_entries, packet):
    need(set(packet) == {'manifest', 'files_base64'}, 'exact overlay envelope required')
    manifest = packet['manifest']
    need(isinstance(manifest, dict) and set(manifest) == {
        'candidate_bytes', 'candidate_file_count', 'candidate_tree_from_manifest',
        'compiled', 'format_qualified', 'parent_file_count', 'parent_head',
        'parent_tree', 'paths', 'production_ready', 'runtime_qualified', 'schema'},
        'exact noncommitted overlay manifest required')
    need(parent['head'] == manifest['parent_head'] == PARENT_COMMIT
         and parent['tree'] == manifest['parent_tree'] == PARENT_TREE
         and parent['file_count'] == manifest['parent_file_count'] == 2302
         and manifest['candidate_file_count'] == SOURCE_FILES
         and manifest['candidate_bytes'] == SOURCE_BYTES
         and manifest['candidate_tree_from_manifest'] == HEAD_TREE
         and manifest['schema'] == 'p4-launch-combined-formatted-overlay-v2'
         and manifest['format_qualified'] is True and manifest['compiled'] is False
         and manifest['runtime_qualified'] is False and manifest['production_ready'] is False,
         'fixed qualified parent and exact formatted successor tree required')
    old_rows = validate_rows(parent_rows, 2302)
    need(tree_id(parent_rows) == PARENT_TREE and set(old_rows) == set(parent['files']),
         'complete exact parent inventory required before overlay')
    changes, encoded_files = manifest['paths'], packet['files_base64']
    need(isinstance(changes, dict) and isinstance(encoded_files, dict)
         and len(changes) == OVERLAY_PATHS and set(changes) == set(encoded_files),
         'all and only declared overlay bodies required')
    current = dict(parent['files'])
    entries = dict(parent_entries)
    for name, change in sorted(changes.items()):
        safe(name)
        need(isinstance(change, dict) and set(change) == {'before', 'after'}
             and change['before'] == parent['files'].get(name),
             'overlay before-row must match the original parent: ' + name)
        after = change['after']
        need(isinstance(after, dict) and set(after) == {'bytes', 'sha256', 'git_blob', 'git_mode'},
             'complete successor file row required')
        row = {'path': name, 'bytes': after['bytes'], 'sha256': after['sha256'],
               'git_blob': after['git_blob'], 'mode': after['git_mode']}
        validate_rows([row], 1)
        need(isinstance(encoded_files[name], str), 'exact base64 overlay text required')
        body = base64.b64decode(encoded_files[name], validate=True)
        need(digest(body) == {key: after[key] for key in ('bytes', 'sha256')}
             and object_id('blob', body) == after['git_blob'],
             'whole overlay body and Git blob must match: ' + name)
        current[name] = dict(after)
        entries['source/' + name] = (int(after['git_mode'], 8) & 0o777, body)
    rows = [{'path': name, 'bytes': row['bytes'], 'sha256': row['sha256'],
             'git_blob': row['git_blob'], 'mode': row['git_mode']}
            for name, row in sorted(current.items())]
    validate_rows(rows, SOURCE_FILES)
    need(sum(row['bytes'] for row in rows) == SOURCE_BYTES and tree_id(rows) == HEAD_TREE
         and set(entries) == {'source/' + name for name in current}
             | {'SOURCE-MANIFEST.json', 'SOURCE-COMMIT.txt'},
         'every successor byte and exact member must contribute to the fixed complete Git tree')
    return rows, entries, manifest


def verify_parent_entries(entries):
    need('SOURCE-MANIFEST.json' in entries and 'SOURCE-COMMIT.txt' in entries,
         'source manifest and exact commit object required')
    manifest_body = entries['SOURCE-MANIFEST.json'][1]; commit_body = entries['SOURCE-COMMIT.txt'][1]
    need(digest(manifest_body) == MANIFEST and digest(commit_body) == COMMIT
         and object_id('commit', commit_body) == PARENT_COMMIT, 'original manifest and commit object must match')
    manifest = decode(manifest_body)
    need(manifest['schema'] == 'p4-portable-qualified-source-manifest-v2'
         and manifest['head'] == PARENT_COMMIT and manifest['tree'] == PARENT_TREE
         and manifest['file_count'] == 2302 and manifest['file_bytes'] == 42628698
         and manifest['commit'] == COMMIT and len(manifest['files']) == 2302,
         'exact complete current source generation required')
    need(commit_body.startswith(('tree ' + PARENT_TREE + '\n').encode())
         and not any(line.startswith(b'parent ') for line in commit_body.split(b'\n\n', 1)[0].splitlines()),
         'explicit root snapshot commit and original tree required')
    provenance = manifest.get('provenance')
    need(isinstance(provenance, dict)
         and provenance.get('snapshot_kind') == 'explicit_root_snapshot_from_verified_complete_tree'
         and provenance.get('upstream_ancestry_claimed') is False
         and provenance.get('parent_commits') == []
         and provenance.get('previous_packet_inventory_sha256') == '5f131f2dbcccafb735b84594e5b1a5c29a77b2e4c9c7882d76b2e66c7a5ee473'
         and provenance.get('previous_source_parent_commit') == '61a38baa745483fbfb757466a1cf352febc20552'
         and provenance.get('previous_source_parent_tree') == 'db6249e80209abeda8000eeced6d045a1d57e0a2'
         and provenance.get('previous_reconstructed_tree') == PARENT_TREE
         and provenance.get('historical_qualification_transferred') is False,
         'complete previous lineage and explicit new root snapshot required')
    rows = [{'path': name, 'bytes': row['bytes'], 'sha256': row['sha256'],
             'git_blob': row['git_blob'], 'mode': row['git_mode']}
            for name, row in sorted(manifest['files'].items())]
    wanted = validate_rows(rows, 2302)
    need(set(entries) == {'source/' + name for name in wanted}
         | {'SOURCE-MANIFEST.json', 'SOURCE-COMMIT.txt'}, 'missing or undeclared source member')
    for name, row in wanted.items():
        mode, body = entries['source/' + name]
        need(mode == (int(row['mode'], 8) & 0o777)
             and digest(body) == {key: row[key] for key in ('bytes', 'sha256')}
             and object_id('blob', body) == row['git_blob'], 'source body, mode or Git blob differs: ' + name)
    need(tree_id(rows) == PARENT_TREE and sum(row['bytes'] for row in rows) == 42628698,
         'every source byte must contribute to the complete Git tree')
    return manifest, rows


def verify_capsule(expected_inventory_sha):
    need(re.fullmatch('[0-9a-f]{64}', expected_inventory_sha), 'external inventory SHA required')
    index = regular(HERE / 'FILES.sha256', 65536)
    need(hashlib.sha256(index).hexdigest() == expected_inventory_sha, 'external inventory pin differs')
    inventory = {}
    for line in index.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^\r\n]+)', line)
        need(match is not None, 'complete inventory record required')
        name = match[2]; safe(name)
        need(name not in inventory and name != 'FILES.sha256', 'distinct nonrecursive inventory members')
        inventory[name] = match[1]
    names, _ = member_names(HERE)
    need(names == set(inventory) | {'FILES.sha256'}, 'exact current capsule file membership')
    for name, sha in inventory.items():
        need(hashlib.sha256(regular(HERE / name)).hexdigest() == sha, 'capsule input differs: ' + name)
    entries = archive_entries(check(HERE / 'SOURCE-CAPSULE.tar.xz', CAPSULE))
    manifest, rows = verify_parent_entries(entries)
    packet = overlay_packet(check(HERE / OVERLAY_PATH, OVERLAY))
    rows, entries, overlay = apply_overlay(manifest, rows, entries, packet)
    return {'parent_manifest': manifest, 'overlay_manifest': overlay, 'rows': rows,
            'entries': entries, 'inventory_sha256': expected_inventory_sha}


def replay(capsule, destination):
    destination = fresh_destination(destination, [HERE]); destination.mkdir(mode=0o700)
    for row in capsule['rows']:
        name = row['path']; path = destination / safe(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        need(path.parent.resolve() == path.parent, 'new source parent alias rejected')
        body = capsule['entries']['source/' + name][1]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            view = memoryview(body)
            while view:
                count = os.write(fd, view); need(count > 0, 'complete source write'); view = view[count:]
            os.fchmod(fd, int(row['mode'], 8) & 0o777); os.fsync(fd)
        finally: os.close(fd)
    return source_snapshot(destination, capsule['rows'], HEAD_TREE)


def write_report(path, value, protected):
    path = fresh_destination(path, protected); path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(os.dup(fd), 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
    finally: os.close(fd)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--inventory-sha256', required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--output', type=Path); group.add_argument('--producer', type=Path)
    parser.add_argument('--report', type=Path); args = parser.parse_args()
    capsule = verify_capsule(args.inventory_sha256)
    result = {'schema': 'p4-current-complete-source-verification-v1', 'source_commit': HEAD_COMMIT,
              'source_parent_commit': PARENT_COMMIT, 'source_parent_tree': PARENT_TREE,
              'source_parent_kind': 'explicit_root_snapshot_from_verified_complete_tree',
              'upstream_ancestry_claimed': False,
              'source_tree': HEAD_TREE, 'source_files': SOURCE_FILES, 'source_bytes': SOURCE_BYTES,
              'source_overlay_sha256': OVERLAY['sha256'], 'full_source_overlay_verified': True,
              'full_source_archive_verified': True, 'historical_tests_counted_as_fresh': 0,
              'Android_builds': 0, 'Android_starts': 0, 'runtime_qualified': False, 'production_ready': False}
    protected = [HERE]
    if args.output:
        destination = args.output.absolute(); result['source_snapshot'] = replay(capsule, destination)
        result['full_source_verified'] = True; protected.append(destination)
    elif args.producer:
        producer = args.producer.absolute()
        result['source_snapshot'] = source_snapshot(producer, capsule['rows'], HEAD_TREE)
        result['full_source_verified'] = True; protected.append(producer)
    if args.report: write_report(args.report, result, protected)
    print(json.dumps({key: value for key, value in result.items() if key != 'source_snapshot'}, sort_keys=True))


if __name__ == '__main__': main()
