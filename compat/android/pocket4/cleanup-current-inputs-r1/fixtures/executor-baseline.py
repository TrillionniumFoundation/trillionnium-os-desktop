"""Retire the exact reviewed Pocket4 host artifacts; never touch Android data.

The default is a read-only preflight. --apply records immutable before/after
proof and deletes only admitted directory identities using directory FDs.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import sys

CUSTODY = Path('/home/alex/work/pocket4-android-final/qualification/apps-content-bound-20261108-8b88-r1')
PLAN = CUSTODY / 'cleanup_work/exact78-old-root-retirement-map.json'
PLAN_SHA = 'b8d6769cafd9fb9bba2d99b17d71452c8b8f1782a0957318dee274f829e8d3ee'
WORK = Path('/home/alex/work')
OUTPUT = Path('/home/alex/work/pocket4-android-final/cleanup/apps-old-root-retirement-20261108-8b88-r1')
IMAGE = Path('/var/lib/droidloom/users/1000/data/data.img')
CURRENT = Path('/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json')
RETIRED_SIGNING_ROOTS = {
    'pocket4-documents-features-build-20261105-r12-03': {
        'package': 'org.droidloom.qa.documents.r12.neeff7aa90e47139a',
        'certificate': 'c85a78ef6b0b71242d321e3091e9ef52e4aafc5ea637a73514da0055dfa0a89e',
        'apk': 'owned-features.apk', 'apk_sha256': '46172494453c8ced3d7ecff67884df59fc2fbc9026057c6d11da70466aac2d48',
        'key_bytes': 3574, 'password_bytes': 65,
    },
    'pocket4-documents-saf-build-20261105-r12-02': {
        'package': 'org.droidloom.qa.saf.r12.n69814e80ea71f485',
        'certificate': 'f772d334443bb5cd71abcc179d04e21ee3e70d424290df69828b94e42bc448f2',
        'apk': 'owned-saf.apk', 'apk_sha256': '3b2b8d01b551f68256a25c351b34f2a6c74f74cbfc9b44b226ea708dba9fffe6',
        'key_bytes': 3526, 'password_bytes': 65,
    },
}
META = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_blocks')


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def identity(path):
    s = path.lstat()
    return {k: getattr(s, k) for k in META}


def plain_path(path):
    for p in [path, *path.parents]:
        if p.is_symlink():
            raise RuntimeError('Symlink path component: ' + str(p))


def read_pin(ref):
    p = Path(ref['path'])
    plain_path(p)
    if not stat.S_ISREG(p.stat().st_mode):
        raise RuntimeError('Not a regular input: ' + str(p))
    raw = p.read_bytes()
    if len(raw) != ref['bytes'] or digest(raw) != ref['sha256']:
        raise RuntimeError('Current input changed: ' + str(p))
    return raw


def write_once(path, value):
    raw = value if isinstance(value, bytes) else encode(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    if path.read_bytes() != raw:
        raise RuntimeError('Proof readback failed')
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def tree_metadata(root):
    """No file contents, no symlink traversal, no other filesystems."""
    first = identity(root)
    if not stat.S_ISDIR(first['st_mode']):
        raise RuntimeError('Target is not a directory')
    entries, private, source, stack = [], [], [], [root]
    files, directories, symlinks, allocated = 0, 0, 0, 0
    while stack:
        directory = stack.pop()
        directories += 1
        if directories > 5000 or files > 50000:
            raise RuntimeError('Inventory bound reached')
        for entry in directory.iterdir():
            m = identity(entry)
            if m['st_dev'] != first['st_dev']:
                raise RuntimeError('Cross-device descendant')
            rel = str(entry.relative_to(root))
            entries.append({'relative': rel, **m, 'nlink': entry.lstat().st_nlink})
            allocated += m['st_blocks'] * 512
            if stat.S_ISLNK(m['st_mode']):
                symlinks += 1
            elif stat.S_ISDIR(m['st_mode']):
                stack.append(entry)
            elif stat.S_ISREG(m['st_mode']):
                files += 1
                if re.search(r'(^|/)(private-signing|password[^/]*|credentials?[^/]*|keystores?)(/|$)', rel.lower()) or entry.name.lower().endswith(('.pk8', '.p12', '.pfx', '.jks', '.keystore', '.key')):
                    private.append({'relative': rel, **m, 'nlink': entry.lstat().st_nlink})
                if entry.suffix in ('.java', '.kt', '.patch', '.diff'):
                    source.append({'relative': rel, 'bytes': m['st_size']})
            else:
                raise RuntimeError('Special file descendant')
    if identity(root) != first:
        raise RuntimeError('Root changed during metadata scan')
    entries.sort(key=lambda x: x['relative'])
    return {'root': str(root), 'identity': first, 'files': files, 'directories': directories,
            'symlinks': symlinks, 'allocated_bytes': allocated,
            'all_entry_metadata_sha256': digest(encode(entries)),
            'possible_private_material_metadata': private, 'source_or_patch_metadata': source,
            'contents_read': False, 'inventory_complete': True}


def private_inputs_released(root, inventory, registry):
    found = inventory['possible_private_material_metadata']
    if not found:
        return {'private_material': 'none'}
    policy = RETIRED_SIGNING_ROOTS.get(root.name)
    if policy is None:
        raise RuntimeError('Unreleased unique signing or credential material')
    expected = {'private-signing/owned.p12': policy['key_bytes'],
                'private-signing/password.txt': policy['password_bytes']}
    if {r['relative']: r['st_size'] for r in found} != expected:
        raise RuntimeError('Private material set changed')
    if any(stat.S_IMODE(r['st_mode']) != 0o600 or r['nlink'] != 1 for r in found):
        raise RuntimeError('Unexpected private material custody')
    if any(r['name'] == policy['package'] or policy['certificate'] in r['certificate_sha256'] for r in registry['packages']):
        raise RuntimeError('An installed identity still needs this QA signing lineage')
    if digest((root / policy['apk']).read_bytes()) != policy['apk_sha256']:
        raise RuntimeError('Public QA APK identity changed')
    return {**policy, 'installed_package_or_certificate_uses': [],
            'private_key_or_password_contents_read_or_hashed': False,
            'public_APK_signature_proof': 'documents-retired-QA-APKs-content-bound.ndjson'}


def live_references(roots):
    root_bytes = [(r, r.encode()) for r in roots]
    def owner(target):
        target = target.removesuffix(' (deleted)')
        return next((r for r in roots if target == r or target.startswith(r + '/')), None)
    hits, mounts, errors, namespaces = [], [], [], set()
    count = 0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        count += 1
        try:
            for name in ('cwd', 'exe', 'root'):
                try:
                    target = os.readlink(p / name)
                    old = owner(target)
                    if old:
                        hits.append({'pid': int(p.name), 'kind': name, 'root': old})
                except (FileNotFoundError, ProcessLookupError):
                    pass
            for fd in (p / 'fd').iterdir():
                try:
                    old = owner(os.readlink(fd))
                    if old:
                        hits.append({'pid': int(p.name), 'kind': 'fd', 'fd': fd.name, 'root': old})
                except (FileNotFoundError, ProcessLookupError):
                    pass
            with (p / 'maps').open() as f:
                for line in f:
                    fields = line.rstrip().split(None, 5)
                    old = owner(fields[5]) if len(fields) == 6 else None
                    if old:
                        hits.append({'pid': int(p.name), 'kind': 'maps', 'root': old})
            # Only matching old-root names are retained; no argument content is emitted.
            args = (p / 'cmdline').read_bytes()
            for root, token in root_bytes:
                if token in args:
                    hits.append({'pid': int(p.name), 'kind': 'owner_argument_reference', 'root': root})
            ns = os.readlink(p / 'ns/mnt')
            if ns not in namespaces:
                namespaces.add(ns)
                with (p / 'mountinfo').open() as f:
                    for line in f:
                        for root in roots:
                            if root in line:
                                mounts.append({'pid': int(p.name), 'namespace': ns, 'root': root})
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            errors.append({'pid': int(p.name), 'error': 'permission'})
    return {'observed_utc': now(), 'processes': count, 'mount_namespaces': len(namespaces),
            'process_or_owner_hits': hits, 'mount_hits': mounts, 'coverage_errors': errors,
            'command_line_contents_retained': False, 'open_file_contents_read': False}


def current_inputs(plan, roots, packages):
    pins, seen, hits = [], {}, []
    def check(ref, scan):
        if ref['path'] in seen:
            return seen[ref['path']]
        raw = read_pin(ref)
        seen[ref['path']] = raw
        pins.append({k: ref[k] for k in ('path', 'bytes', 'sha256')})
        if scan:
            for root in roots:
                if root.encode() in raw or Path(root).name.encode() in raw:
                    hits.append({'path': ref['path'], 'old_root': root})
        return raw
    for ref in plan['fresh_selected_preparation_hashes']:
        raw = check(ref, True)
        preparation = json.loads(raw)
        if 'files' in preparation:
            sources = preparation['files']
            if isinstance(sources, dict):
                sources = list(sources.values())
        elif preparation.get('schema') == 'pocket4-camera-photo-display-preparation-v1':
            sources = [preparation['source'], preparation['base_wrapper'], *preparation['source_dependencies']]
        else:
            raise RuntimeError('Unrecognized preparation source schema')
        for source in sources:
            check(source, True)
    for row in packages['consumer_migration']:
        check(row['installed'], True)
        check(row['staged'], True)
    for ref in json.loads((CUSTODY / 'cleanup_work/canonical-production-package-references.json').read_text())['matching_files']:
        check(ref, True)
    current = CURRENT.read_bytes()
    for root in roots:
        if root.encode() in current or Path(root).name.encode() in current:
            hits.append({'path': str(CURRENT), 'old_root': root})
    if hits:
        raise RuntimeError('A reviewed current source or selector references a candidate: ' + json.dumps(hits))
    return {'pins': pins, 'files': len(pins), 'all_exact': True, 'candidate_references': hits,
            'CURRENT': {'path': str(CURRENT), 'bytes': len(current), 'sha256': digest(current)}}


def unlink_tree_fd(parent, name, expected):
    """Unlink confined to one admitted inode, without following directory links."""
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        s = os.fstat(fd)
        if any(getattr(s, k) != expected[k] for k in ('st_dev', 'st_ino', 'st_ctime_ns')):
            raise RuntimeError('Directory identity changed at destructive boundary')
        def empty(directory_fd):
            for item in os.listdir(directory_fd):
                st = os.stat(item, dir_fd=directory_fd, follow_symlinks=False)
                if st.st_dev != expected['st_dev']:
                    raise RuntimeError('Mounted or cross-device descendant at destructive boundary')
                if stat.S_ISDIR(st.st_mode):
                    child = os.open(item, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    try:
                        actual = os.fstat(child)
                        if (actual.st_dev, actual.st_ino) != (st.st_dev, st.st_ino):
                            raise RuntimeError('Descendant changed while opening')
                        empty(child)
                        check = os.stat(item, dir_fd=directory_fd, follow_symlinks=False)
                        if (check.st_dev, check.st_ino) != (actual.st_dev, actual.st_ino):
                            raise RuntimeError('Descendant replaced while removing')
                        os.rmdir(item, dir_fd=directory_fd)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                    os.unlink(item, dir_fd=directory_fd)
                else:
                    raise RuntimeError('Special descendant at destructive boundary')
        empty(fd)
        check = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (check.st_dev, check.st_ino) != (s.st_dev, s.st_ino):
            raise RuntimeError('Root replaced while removing')
        os.rmdir(name, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Root-owned metadata coverage is required')
    os.nice(19)
    plain_path(CUSTODY)
    raw = PLAN.read_bytes()
    if digest(raw) != PLAN_SHA:
        raise RuntimeError('Wrong reviewed root manifest')
    plan = json.loads(raw)
    targets = [r for r in plan['roots'] if r['state'] == 'immediate_host_artifact_retirement_candidate']
    if len(targets) != 34:
        raise RuntimeError('Wrong frozen candidate count')
    roots = [r['path'] for r in targets]
    if len(set(roots)) != 34 or any(Path(r).parent != WORK or not Path(r).name.startswith('pocket4-') for r in roots):
        raise RuntimeError('Non-exact root allowlist')
    if any('owned-amazon-qa-r3-build-02' in r for r in roots):
        raise RuntimeError('Active QA signing material cannot retire yet')
    registry = json.loads((CUSTODY / 'cleanup_work/all208-installed-cleanup-metadata.json').read_text())
    packages = json.loads((CUSTODY / 'cleanup_work/package-retirement-manifest.json').read_text())
    protected_before = identity(IMAGE)
    for k, v in packages['offline_image_identity']['before'].items():
        if protected_before[k] != v:
            raise RuntimeError('Original account image changed since registry audit')
    plain_path(WORK)
    plain_path(OUTPUT.parent)
    inputs = current_inputs(plan, roots, packages)
    before = []
    skipped = []
    for target in targets:
        root = Path(target['path'])
        try:
            plain_path(root)
            inventory = tree_metadata(root)
            if inventory['identity'] != target['fresh_root_identity']:
                raise RuntimeError('Root inode/ctime/metadata drift from reviewed identity')
            for field in ('files', 'directories', 'symlinks', 'allocated_bytes'):
                if inventory[field] != target[field]:
                    raise RuntimeError('Recursive inventory changed: ' + field)
            release = private_inputs_released(root, inventory, registry)
            before.append({'path': str(root), 'inventory': inventory, 'signing_release': release})
        except Exception as e:
            skipped.append({'path': str(root), 'reason': str(e)})
    live = live_references([r['path'] for r in before])
    if live['coverage_errors']:
        raise RuntimeError('Incomplete process/mount ownership coverage')
    busy = {r['root'] for r in live['process_or_owner_hits'] + live['mount_hits']}
    admitted = []
    for row in before:
        if row['path'] in busy:
            skipped.append({'path': row['path'], 'reason': 'Fresh process/owner/mount reference'})
        else:
            admitted.append(row)
    proof = {'schema': 'exact-host-artifact-retirement-preflight-v1', 'observed_utc': now(),
             'plan_sha256': PLAN_SHA, 'current_inputs': inputs, 'live_owner_proof': live,
             'admitted': admitted, 'skipped': skipped, 'protected_data_image_before': protected_before,
             'Android_actions': 0, 'CURRENT_writes': 0, 'private_keys_or_passwords_read': False}
    if not args.apply:
        print(json.dumps({'admitted': len(admitted), 'skipped': skipped, 'live_owner_proof': live,
                          'source_files_verified': inputs['files'], 'read_only': True}))
        return
    OUTPUT.mkdir(mode=0o700)
    write_once(OUTPUT / 'executor.py', Path(__file__).read_bytes())
    preflight_pin = write_once(OUTPUT / 'preflight.json', proof)
    journal_fd = os.open(OUTPUT / 'journal.ndjson', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    parent = os.open(WORK, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    removed, errors = [], []
    try:
        for row in admitted:
            root = Path(row['path'])
            try:
                if identity(IMAGE) != protected_before:
                    raise RuntimeError('Protected data image drift')
                # Recheck the entire metadata census immediately at the boundary.
                actual = tree_metadata(root)
                if actual != row['inventory']:
                    raise RuntimeError('Candidate changed after preflight')
                os.write(journal_fd, (json.dumps({'utc': now(), 'phase': 'remove_begin', 'path': str(root),
                                               'identity': actual['identity'], 'metadata_sha256': actual['all_entry_metadata_sha256']}) + '\n').encode())
                os.fsync(journal_fd)
                unlink_tree_fd(parent, root.name, actual['identity'])
                if root.exists() or root.is_symlink():
                    raise RuntimeError('Root remains after removal')
                record = {'path': str(root), 'absent': True, 'files': actual['files'],
                          'allocated_bytes': actual['allocated_bytes'], 'finished_utc': now()}
                removed.append(record)
                os.write(journal_fd, (json.dumps({'phase': 'remove_complete', **record}) + '\n').encode())
                os.fsync(journal_fd)
            except Exception as e:
                errors.append({'path': str(root), 'reason': str(e)})
                os.write(journal_fd, (json.dumps({'phase': 'remove_failed', **errors[-1]}) + '\n').encode())
                os.fsync(journal_fd)
                break
    finally:
        os.close(journal_fd)
        os.close(parent)
    protected_after = identity(IMAGE)
    post_inputs = current_inputs(plan, roots, packages)
    result = {'schema': 'exact-host-artifact-retirement-result-v1', 'completed_utc': now(),
              'preflight': preflight_pin, 'plan_sha256': PLAN_SHA, 'removed': removed,
              'removed_roots': len(removed), 'removed_files': sum(x['files'] for x in removed),
              'removed_allocated_bytes': sum(x['allocated_bytes'] for x in removed),
              'skipped': skipped, 'errors': errors, 'protected_data_image_before': protected_before,
              'protected_data_image_after': protected_after, 'protected_data_image_unchanged': protected_before == protected_after,
              'current_consumer_inputs_unchanged': inputs['pins'] == post_inputs['pins'],
              'CURRENT_before': inputs['CURRENT'], 'CURRENT_after': post_inputs['CURRENT'],
              'CURRENT_writes': 0, 'Android_actions': 0, 'installed_APK_or_account_data_changes': 0,
              'all_admitted_removed': len(removed) == len(admitted),
              'Amazon_QA_unique_signing_material_retained': True}
    final = write_once(OUTPUT / 'result.json', result)
    print(json.dumps({'result': final, 'removed_roots': result['removed_roots'],
                      'removed_files': result['removed_files'], 'removed_allocated_bytes': result['removed_allocated_bytes'],
                      'skipped': skipped, 'errors': errors, 'protected_data_image_unchanged': result['protected_data_image_unchanged'],
                      'current_consumer_inputs_unchanged': result['current_consumer_inputs_unchanged']}))
    if errors or protected_before != protected_after:
        raise RuntimeError('Retirement requires reconciliation')


if __name__ == '__main__':
    main()
