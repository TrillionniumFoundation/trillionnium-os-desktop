"""Import the qualified coherent recipe and two tools into the owned NBD volume.

Called in-process by the reviewed source_import role after namespace_entry has
dropped to UID/GID 1000.  This module cannot start a mount, build, or Android.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import time

BOOT = '8c55b477-233a-4771-995a-6f666f6299b3'
ORIGIN = Path('/data/p4-avb-media-cohort-e6ac-r1')
SOURCE = ORIGIN / 'source'
ORDINARY = ORIGIN / 'qualification'
MOUNT = Path('/data/p4-production651-nbd-e6ac-r1/mount')
BASE = MOUNT / 'source-production651'
DEST = BASE / 'tools-production-latest-r1'
_spec = importlib.util.spec_from_file_location('cohort_checks', Path(__file__).with_name('carrier_checks.py'))
checks = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(checks)
producer = checks.sibling('producer_contract')
HEAD = producer.HEAD
TREE = producer.TREE
PINS = {
    ORDINARY / 'RESULT.json': (246094, 'fef8babe8d768c50066ce84ba0aa84f3e86fc00b725c03ac68e8704dd788afac'),
    ORDINARY / 'SOURCE-AFTER.json': (1037239, '2b9eb10e3ed7f46033533501abed69c960f5b178b2d43121e533c4cd15bbc118'),
    ORDINARY / 'CANDIDATE-GIT-AFTER.json': (15692, '7d148b6dca9e641ecd7af5970b866a76c192f746276766d3f63b0683602cedea'),
    ORDINARY / 'INDEPENDENT-RETIREMENT-r1.json': (135446, '39ac9c029aec0652ccfe1fe59f110f59cc229ba6e5e103448d09d37606933931'),
    ORDINARY / 'NATIVE-CLOSEOUT-r1.json': (2456, '94247e7db27c9d5938808bb34c3ba3149bd8d0e38a4b462c5462c9c70f663425'),
}
TOOLS = dict(producer.TOOL_PINS)
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
       'GIT_CONFIG_COUNT': '0', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_LAZY_FETCH': '1',
       'GIT_PAGER': 'cat', 'GIT_TERMINAL_PROMPT': '0'}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def reference(path, contents=False):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'regular single-link input: ' + str(path))
        need(before.st_size <= 256 * 1024**2, 'bounded input: ' + str(path))
        digest = hashlib.sha256(); pieces = []
        while True:
            part = os.read(fd, 1024**2)
            if not part:
                break
            digest.update(part)
            if contents:
                pieces.append(part)
        need(f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'input changed during read: ' + str(path))
        ref = {'path': str(path), 'identity': f9(before), 'bytes': before.st_size, 'sha256': digest.hexdigest()}
        return (ref, b''.join(pieces)) if contents else ref
    finally:
        os.close(fd)


def create(path, body, mode=0o600):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(body)
        while view:
            count = os.write(fd, view)
            need(count > 0, 'finite output write')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return reference(path)


def save(path, value):
    return create(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


def tree_members(root, skip_git=False):
    root = Path(root); result = set()
    need(stat.S_ISDIR(root.lstat().st_mode), 'real directory: ' + str(root))
    for directory, dirs, files in os.walk(root, followlinks=False):
        if Path(directory) == root and skip_git:
            dirs[:] = [name for name in dirs if name != '.git']
        for name in dirs:
            need(stat.S_ISDIR((Path(directory) / name).lstat().st_mode), 'no directory symlink')
        for name in files:
            path = Path(directory) / name
            need(stat.S_ISREG(path.lstat().st_mode), 'no file symlink or special node')
            result.add(path.relative_to(root).as_posix())
    return result


def validate_qualification(parsed, inputs):
    result = parsed[ORDINARY / 'RESULT.json']; frozen = parsed[ORDINARY / 'SOURCE-AFTER.json']
    need(result['passed'] and result['ordinary_passed'] and result['release_passed'] and result['exact_catalog_union'], 'complete ordinary and release qualification')
    need(result['commit'] == HEAD and result['tree'] == TREE and result['source_files'] == producer.TRACKED_FILES,
         'exact latest qualified producer identity')
    need(len(result['ordinary']) == 20 and sum(x['passed'] for x in result['ordinary']) == 946 and
         sum(x['failed'] for x in result['ordinary']) == 0 and sum(x['ignored'] for x in result['ordinary']) == 27 and
         len(result['release']) == 9 and len(result['actual_exec_stop_tests']) == 3 and
         result['actual_catalog_counts'] == {'catalog': 973, 'harnesses': 20, 'ignored': 27, 'ordinary': 946} and
         result['all_actual_metadata_normal_bins_built'] and result['actual_metadata_targets_all_executed'] and
         result['source_full_F9_SHA_unchanged'] and result['qualified_test_and_release_ELFs_unchanged'],
         'exact complete latest ordinary and release qualification')
    independent = parsed[ORDINARY / 'INDEPENDENT-RETIREMENT-r1.json']
    closeout = parsed[ORDINARY / 'NATIVE-CLOSEOUT-r1.json']
    need(independent['retirement_passed'] and independent['ordinary_and_release_qualification_passed'] and
         independent['original_cgroup_absent'] and independent['actual_ordinary'] ==
         {'catalog': 973, 'failed': 0, 'harnesses': 20, 'ignored': 27, 'passed': 946} and
         closeout['passed'] and closeout['retirement_passed'] and closeout['observer_cgroup_absent'] and
         closeout['observer_original_generation_absent'], 'complete independent producer and observer retirement')
    need(independent['result'] == inputs[str(ORDINARY / 'RESULT.json')], 'retirement result exact F9 binding')
    need(frozen['head'] == HEAD and frozen['tree'] == TREE and len(frozen['files']) == producer.TRACKED_FILES,
         'one exact current coherent source, never a FINAL-SOURCE parent snapshot')
    expected = {name: {key: row[key] for key in ('git_mode', 'git_blob', 'bytes', 'sha256')}
                for name, row in frozen['files'].items()}
    source_proof = next(row for row in independent['source_and_parents'] if row['path'] == str(SOURCE))
    need(source_proof['head'] == HEAD and source_proof['tree'] == TREE and source_proof['files'] == producer.TRACKED_FILES and
         source_proof['original_after'] == inputs[str(ORDINARY / 'SOURCE-AFTER.json')] and
         source_proof['whole_F9_SHA_and_Git_blobs_unchanged'], 'actual current source independently rechecked')
    qualified_git = parsed[ORDINARY / 'CANDIDATE-GIT-AFTER.json']
    git_proof = next(row for row in independent['whole_git_directory_closures'] if row['path'] == str(SOURCE / '.git'))
    need(git_proof['original_after'] == inputs[str(ORDINARY / 'CANDIDATE-GIT-AFTER.json')] and
         git_proof['whole_F9_SHA_unchanged'] and git_proof['complete_files'] == len(qualified_git),
         'qualified Git leaf closure exact binding')
    need(closeout['result'] == inputs[str(ORDINARY / 'RESULT.json')] and closeout['independent'] == inputs[str(ORDINARY / 'INDEPENDENT-RETIREMENT-r1.json')], 'closeout binds exact result and independent originals')
    return result, frozen, expected, qualified_git


def import_coherent_tools():
    producer.require_new_execution_binding()
    entry = sys.modules.get('p4_storage_entry')
    need(entry is not None and callable(getattr(entry, 'check', None)), 'original owned storage entry required')
    entry.check()
    proof = entry.proof; proof_ref = entry.proof_reference
    need(os.getresuid() == os.getresgid() == (1000, 1000, 1000) and os.getgroups() == [], 'ordinary UID/GID 1000 only')
    need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'original desktop boot')
    need(proof['schema'] == 'p4-production651-owned-namespace-entry-v1' and proof['role'] == 'source_import' and
         proof['pid'] == os.getpid() and proof['actual_role_uid'] == proof['actual_role_gid'] == 1000 and
         proof['actual_supplementary_groups'] == [] and proof['actual_capabilities_zero'] is True and
         proof['actual_role_umask'] == 0o077, 'actual fixed source-import role')
    need(reference(proof_ref['path']) == proof_ref, 'original root-created storage entry receipt')
    values = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    need(values['Umask'].strip() == '0077' and all(int(values[x].strip(), 16) == 0 for x in ('CapInh', 'CapPrm', 'CapEff', 'CapAmb')), 'ordinary import credential state')
    need(Path('/proc/self/ns/mnt').stat().st_ino == proof['namespace_entered'] != proof['namespace_before'], 'held private namespace')
    need(f9(MOUNT.lstat())[:2] == proof['volume_root'][:2] and MOUNT.lstat().st_dev == os.makedev(43, 0), 'original selected NBD volume')
    for path, expected_owner in [(MOUNT, 0), (BASE, 1000)]:
        node = path.lstat()
        need(stat.S_ISDIR(node.st_mode) and path.resolve() == path and node.st_uid == node.st_gid == expected_owner and
             node.st_dev == MOUNT.lstat().st_dev and not stat.S_IMODE(node.st_mode) & 0o022, 'owned ordinary destination parent')
    need(not DEST.exists() and not DEST.is_symlink(), 'create-only tools destination')
    inputs = {}; parsed = {}
    for path, (size, digest) in PINS.items():
        ref, raw = reference(path, True)
        need(ref['bytes'] == size and ref['sha256'] == digest, 'qualified source proof pin: ' + str(path))
        inputs[str(path)] = ref; parsed[path] = json.loads(raw)
    result, frozen, expected, qualified_git = validate_qualification(parsed, inputs)
    original_tools = {}
    for name, (size, digest) in TOOLS.items():
        path = ORDINARY / 'release' / name; ref = reference(path)
        need(ref['bytes'] == size and ref['sha256'] == digest and stat.S_IMODE(ref['identity'][2]) == 0o500, 'original qualified normal ELF')
        need(ref in [{key: row[key] for key in ('path', 'identity', 'bytes', 'sha256')} for row in result['release']], 'ELF is in the completed qualification')
        original_tools[name] = ref
    source_directories = checks.directory_refs(SOURCE, True)
    source_git_directories = checks.directory_refs(SOURCE / '.git')
    need(tree_members(SOURCE, True) == set(expected), 'source contains exactly tracked files')
    for name, row in frozen['files'].items():
        ref = reference(SOURCE / name)
        need({key: ref[key] for key in ('identity', 'bytes', 'sha256')} == {key: row[key] for key in ('identity', 'bytes', 'sha256')}, 'full source F9 and SHA')
    source_git = {name: reference(SOURCE / '.git' / name) for name in sorted(tree_members(SOURCE / '.git'))}
    need(set(source_git) == set(qualified_git) and all({k: row[k] for k in ('bytes','sha256','identity')} == qualified_git[name] for name,row in source_git.items()), 'actual complete current qualified Git files/F9 differ')
    need(not any((SOURCE / '.git' / name).exists() for name in ('commondir', 'shallow', 'objects/info/alternates', 'objects/info/http-alternates')), 'self-contained original Git objects')
    entry.check(); DEST.mkdir(mode=0o700); (DEST / 'commands').mkdir(mode=0o700)
    commands = []; deadline = time.monotonic() + 600

    def command(name, args, cwd):
        entry.check(); child = None; pidfd = None; failure = None; row = {'name': name, 'argv': args, 'cwd': str(cwd)}
        outpath = DEST / 'commands' / (name + '.stdout'); errpath = DEST / 'commands' / (name + '.stderr')
        with outpath.open('xb') as out, errpath.open('xb') as err:
            try:
                child = subprocess.Popen(args, cwd=cwd, env=ENV, stdin=subprocess.DEVNULL, stdout=out, stderr=err, close_fds=True)
                pidfd = os.pidfd_open(child.pid)
                row.update(pid=child.pid, proc_stat=Path('/proc', str(child.pid), 'stat').read_text(),
                           cgroup=Path('/proc', str(child.pid), 'cgroup').read_text().strip())
                need(row['cgroup'] == Path('/proc/self/cgroup').read_text().strip(), 'child inherits the actual owned role cgroup')
                save(DEST / 'commands' / (name + '.START.json'), row)
                end = min(deadline, time.monotonic() + 120)
                while child.poll() is None:
                    entry.check(); need(time.monotonic() < end, 'finite Git command deadline')
                    try: child.wait(timeout=min(0.5, end - time.monotonic()))
                    except subprocess.TimeoutExpired: pass
                need(child.returncode == 0, 'Git command failed: ' + name)
            except BaseException as error:
                failure = error; row['error'] = repr(error)
            finally:
                if child is not None and child.returncode is None:
                    if pidfd is not None: signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else: child.kill()  # Only the original still-unreaped Popen child.
                    child.wait(timeout=10)
                if pidfd is not None:
                    poll = select.poll(); poll.register(pidfd, select.POLLIN | select.POLLHUP)
                    row['pidfd_events'] = poll.poll(0); os.close(pidfd)
                if child is not None: row['returncode'] = child.returncode
                out.flush(); err.flush(); os.fsync(out.fileno()); os.fsync(err.fileno())
                row['stdout'] = reference(outpath); row['stderr'] = reference(errpath)
                save(DEST / 'commands' / (name + '.COMMAND.json'), row); commands.append(row)
        if failure is not None: raise failure
        need(row['pidfd_events'] and row['pidfd_events'][0][1] & select.POLLHUP, 'original child reaped')
        need(outpath.stat().st_size <= 8 * 1024**2 and errpath.stat().st_size <= 8 * 1024**2, 'finite command output')
        entry.check(); return outpath.read_bytes()

    def git(name, root, *args):
        return command(name, ['/usr/bin/git', '--no-pager', '-c', 'core.hooksPath=/dev/null', '-c', 'core.autocrlf=false', '-c', 'core.filemode=true', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', *args], root)

    try:
        need(git('source-head', SOURCE, 'rev-parse', 'HEAD', 'HEAD^{tree}').decode().splitlines() == [HEAD, TREE], 'actual source Git head and tree')
        need(not git('source-clean', SOURCE, 'status', '--porcelain=v1', '--untracked-files=all'), 'actual source clean')
        git('clone', BASE, 'clone', '--no-local', '--no-hardlinks', '--no-checkout', '--template=', str(SOURCE), str(DEST / 'recipe'))
        recipe = DEST / 'recipe'
        git('checkout', recipe, 'checkout', '--detach', HEAD)
        git('remove-origin', recipe, 'remote', 'remove', 'origin')
        need(git('destination-head', recipe, 'rev-parse', 'HEAD', 'HEAD^{tree}').decode().splitlines() == [HEAD, TREE], 'copied head/tree match')
        need(not git('destination-clean', recipe, 'status', '--porcelain=v1', '--untracked-files=all'), 'copied recipe clean')
        need(git('not-shallow', recipe, 'rev-parse', '--is-shallow-repository').strip() == b'false', 'full copied object history')
        git('objects-complete', recipe, 'fsck', '--full', '--no-reflogs', '--no-dangling')
        need(not any((recipe / '.git' / name).exists() for name in ('commondir', 'shallow', 'objects/info/alternates', 'objects/info/http-alternates')), 'no borrowed object directory')
        need(tree_members(recipe, True) == set(expected), 'complete destination source membership')
        recipe_files = {}; destination_refs = {}; normalized_modes = []
        for name, row in expected.items():
            entry.check(); ref, raw = reference(recipe / name, True)
            need(row['git_mode'] in ('100644', '100755') and ref['bytes'] == row['bytes'] and ref['sha256'] == row['sha256'] and
                 hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == row['git_blob'], 'authenticated new regular Git blob before mode normalization')
            need(ref['identity'][:2] != frozen['files'][name]['identity'][:2] and ref['identity'][0] == MOUNT.lstat().st_dev and
                 ref['identity'][3:6] == [1000, 1000, 1], 'only the new owned copied inode may be normalized')
            wanted = int(row['git_mode'], 8) & 0o777
            if stat.S_IMODE(ref['identity'][2]) != wanted:
                fd = os.open(recipe / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                before = ref
                try:
                    need(f9(os.fstat(fd)) == before['identity'], 'same no-follow copied file descriptor')
                    os.fchmod(fd, wanted); os.fsync(fd)
                    need(f9(os.fstat(fd))[:2] == before['identity'][:2], 'normalization preserves the copied inode')
                finally: os.close(fd)
                ref = reference(recipe / name)
                need(ref['bytes'] == before['bytes'] and ref['sha256'] == before['sha256'], 'normalization preserves every copied byte')
                normalized_modes.append({'name': name, 'authenticated_git_mode': row['git_mode'], 'before': before, 'after': ref})
            mode = stat.S_IMODE(ref['identity'][2])
            need(mode == (int(row['git_mode'], 8) & 0o777) and ref['bytes'] == row['bytes'] and ref['sha256'] == row['sha256'] and
                 hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == row['git_blob'], 'complete copied source bytes/mode/blob')
            need(ref['identity'][:2] != frozen['files'][name]['identity'][:2] and ref['identity'][0] == MOUNT.lstat().st_dev, 'private copied inode')
            recipe_files[name] = {'kind': 'file', 'mode': mode, 'bytes': ref['bytes'], 'sha256': ref['sha256']}
            destination_refs[name] = ref
        git_files = {name: reference(recipe / '.git' / name) for name in sorted(tree_members(recipe / '.git'))}
        recipe_directories = checks.directory_refs(recipe, True)
        git_directories = checks.directory_refs(recipe / '.git')
        (DEST / 'bin').mkdir(mode=0o700); normal_tools = []
        for name, old in original_tools.items():
            ref, raw = reference(old['path'], True); need(ref == old, 'original ELF unchanged before copy')
            new = create(DEST / 'bin' / name, raw, 0o755)
            need(new['bytes'] == old['bytes'] and new['sha256'] == old['sha256'] and new['identity'][:2] != old['identity'][:2] and
                 new['identity'][0] == MOUNT.lstat().st_dev and stat.S_IMODE(new['identity'][2]) == 0o755, 'new executable copy on owned volume')
            normal_tools.append(new)
        need(tree_members(DEST / 'bin') == set(TOOLS), 'exact two executable members')
        for name, row in frozen['files'].items():
            ref = reference(SOURCE / name)
            need({key: ref[key] for key in ('identity', 'bytes', 'sha256')} == {key: row[key] for key in ('identity', 'bytes', 'sha256')}, 'source full F9 unchanged after import')
        need(source_git == {name: reference(SOURCE / '.git' / name) for name in sorted(tree_members(SOURCE / '.git'))}, 'source Git originals unchanged')
        for ref in list(inputs.values()) + list(original_tools.values()) + normal_tools + list(destination_refs.values()) + list(git_files.values()):
            entry.check(); need(reference(ref['path']) == ref, 'final full input/output F9 revalidation')
        need(tree_members(recipe, True) == set(expected), 'final exact membership')
        need(set(git_files) == tree_members(recipe / '.git'), 'final complete Git leaf membership')
        checks.verify_directories(SOURCE, source_directories, True)
        checks.verify_directories(SOURCE / '.git', source_git_directories)
        checks.verify_directories(recipe, recipe_directories, True)
        checks.verify_directories(recipe / '.git', git_directories)
        entry.check(); need(reference(proof_ref['path']) == proof_ref, 'original entry receipt unchanged')
        receipt = {'schema': 'p4-production651-current-coherent-source-import-v2', 'recipe_commit': HEAD, 'recipe_tree': TREE,
                   'recipe_source_files': recipe_files, 'recipe_source_refs': destination_refs, 'recipe_git_files': git_files,
                   'recipe_directory_refs': recipe_directories, 'recipe_git_directory_refs': git_directories,
                   'normal_tools': normal_tools, 'source_origin': {'host': 'desktop', 'boot': BOOT, 'source': str(SOURCE),
                    'head': HEAD, 'tree': TREE, 'qualified_inputs': inputs, 'normal_tools': original_tools,
                    'source_f9': frozen['files'], 'source_git_f9': source_git,
                    'source_directory_refs': source_directories, 'source_git_directory_refs': source_git_directories},
                   'source_before_after_unchanged': True, 'git_alternates_absent': True,
                   'new_file_modes_normalized_from_authenticated_git': normalized_modes,
                   'destination_full_membership_verified': True,
                   'actual_storage_entry': {'proof': proof, 'reference': proof_ref, 'check_revalidated': True},
                   'commands': commands, 'source_reconciliation_performed': False,
                   'full_builds_started': 0, 'Android_starts': 0, 'runtime_qualified': False, 'production_ready': False}
        result_ref = save(DEST / 'SOURCE-COHORT.json', receipt)
        entry.check(); need(reference(result_ref['path']) == result_ref, 'complete durable source cohort receipt')
        directory_fd = os.open(DEST, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        return result_ref
    except BaseException as error:
        # The native source_import unit retains the whole descendant cgroup.
        # A partial destination is kept for review and is never reused as success.
        save(DEST / 'IMPORT-FAILURE.json', {'schema': 'p4-coherent-source-import-failure-v1',
             'error': repr(error), 'commands': commands, 'source': str(SOURCE), 'destination': str(DEST),
             'success_receipt_issued': (DEST / 'SOURCE-COHORT.json').exists(), 'production_ready': False})
        raise


if __name__ == '__main__':
    raise SystemExit('Use only the reviewed owned source_import role; no standalone entry.')
