"""Read-only replacement for the pinned cleanup helper's reference observer.

Only live_references is inserted into the existing helper. This module has no
command line, deletion, package-management or receipt-writing operation.
"""
from pathlib import Path
import datetime
import os


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def live_references(roots):
    """Bounded observation; any incomplete view is UNKNOWN, never admission.

    Preserve the caller's three veto lists. Match every task's references by
    displayed path and filesystem identity, and resolve mount roots to catch
    parent bind aliases. No open-file contents are read. This is a snapshot,
    not a lock against references acquired after the observation.
    """
    import posixpath
    import re
    import stat
    import time

    hits, mounts, errors = [], [], []
    hit_keys, mount_keys, error_keys = set(), set(), set()
    namespaces, mount_views, snapshots, identities = set(), {}, {}, {}
    bindings = {}
    counts = {'processes': 0, 'tasks': 0, 'entries': 0, 'fds': 0, 'empty_zombies': 0}
    started = time.monotonic()
    proc = Path('/proc')
    MAX_ROOTS, MAX_ENTRIES, MAX_TASKS, MAX_FDS = 128, 100000, 20000, 500000
    MAX_READ, MAX_SECONDS = 16 * 1024 * 1024, 45

    class Incomplete(Exception):
        pass

    def error(code, pid=None, tid=None):
        key = (code, pid, tid)
        if key not in error_keys and len(errors) < 512:
            error_keys.add(key)
            errors.append({k: v for k, v in
                           (('error', code), ('pid', pid), ('tid', tid))
                           if v is not None})

    def bound():
        if time.monotonic() - started > MAX_SECONDS:
            raise Incomplete('time_bound')

    def read(path, limit=MAX_READ):
        bound()
        with path.open('rb') as f:
            raw = f.read(limit + 1)
        if len(raw) > limit:
            raise Incomplete('read_bound')
        return raw

    def names(path, maximum):
        answer = set()
        with os.scandir(path) as entries:
            for entry in entries:
                bound()
                if entry.name.isdigit():
                    answer.add(entry.name)
                    if len(answer) > maximum:
                        raise Incomplete('enumeration_bound')
        return answer

    def beneath(path, parent):
        return path == parent or path.startswith(parent.rstrip('/') + '/')

    def lexical_owner(path):
        path = path.removesuffix(' (deleted)')
        return {r for r in roots if beneath(path, r)}

    def metadata(s):
        return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
                s.st_mtime_ns, s.st_ctime_ns)

    def secure_open(path):
        # Linux O_PATH obtains metadata without reading a file body. Each
        # ancestor is opened relative to an already held directory descriptor.
        fd = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            parts = path.split('/')[1:]
            for i, part in enumerate(parts):
                flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
                if i != len(parts) - 1:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            s = os.fstat(fd)
            if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
                raise Incomplete('target_symlink_or_special_node')
            return fd
        except BaseException:
            os.close(fd)
            raise

    def unescape(value):
        # mountinfo uses octal escapes; paths in maps may use the same escapes.
        return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), value)

    def mount_table(raw):
        table = []
        for line in raw.decode('utf-8', 'surrogateescape').splitlines():
            bound()
            fields = line.split()
            if len(fields) < 10 or '-' not in fields or fields.index('-') < 6:
                raise Incomplete('invalid_mountinfo')
            if not re.fullmatch(r'[0-9]+:[0-9]+', fields[2]):
                raise Incomplete('invalid_mount_device')
            dev = tuple(int(x) for x in fields[2].split(':'))
            source, point = unescape(fields[3]), unescape(fields[4])
            if not source.startswith('/') or not point.startswith('/'):
                raise Incomplete('invalid_mount_path')
            table.append((dev, posixpath.normpath(source), posixpath.normpath(point)))
        if not table:
            raise Incomplete('empty_mountinfo')
        return table

    def remember(path, s, root):
        bound()
        counts['entries'] += 1
        if counts['entries'] > MAX_ENTRIES:
            raise Incomplete('target_inventory_bound')
        snapshots[path] = metadata(s)
        identities.setdefault((s.st_dev, s.st_ino), set()).add(root)

    def inventory(root, table):
        fd = secure_open(root)
        try:
            initial = os.fstat(fd)
            candidates = [m for m in table if beneath(root, m[2])]
            if not candidates:
                raise Incomplete('target_mount_unresolved')
            longest = max(len(m[2]) for m in candidates)
            deepest = [m for m in candidates if len(m[2]) == longest]
            if len(deepest) != 1:
                raise Incomplete('ambiguous_target_mount')
            dev, source, point = deepest[0]
            if dev != (os.major(initial.st_dev), os.minor(initial.st_dev)):
                raise Incomplete('target_mount_device_mismatch')
            internal = posixpath.normpath(posixpath.join(source, posixpath.relpath(root, point)))
            bindings[root] = (dev, internal)
            mounted = {m[2] for m in table if beneath(m[2], root)}

            def walk(directory, path, depth):
                if depth > 128:
                    raise Incomplete('inventory_depth_bound')
                with os.scandir(directory) as children:
                    for entry in children:
                        bound()
                        name = entry.name
                        child_path = path + '/' + name
                        s = os.stat(name, dir_fd=directory, follow_symlinks=False)
                        if child_path in mounted or s.st_dev != initial.st_dev:
                            raise Incomplete('mounted_target_descendant')
                        if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
                            raise Incomplete('target_symlink_or_special_node')
                        remember(child_path, s, root)
                        if stat.S_ISDIR(s.st_mode):
                            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY |
                                            os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
                            try:
                                if metadata(os.fstat(child)) != metadata(s):
                                    raise Incomplete('target_changed_during_inventory')
                                walk(child, child_path, depth + 1)
                            finally:
                                os.close(child)
            remember(root, initial, root)
            if root in mounted:
                raise Incomplete('mounted_target_root')
            if stat.S_ISDIR(initial.st_mode):
                directory = os.open('.', os.O_RDONLY | os.O_DIRECTORY |
                                    os.O_CLOEXEC, dir_fd=fd)
                try:
                    walk(directory, root, 0)
                finally:
                    os.close(directory)
        finally:
            os.close(fd)

    def hit(pid, tid, kind, owners, descriptor=None):
        for root in owners:
            key = (pid, tid, kind, root, descriptor)
            if key not in hit_keys:
                if len(hits) >= 10000:
                    raise Incomplete('reference_hit_bound')
                hit_keys.add(key)
                row = {'pid': pid, 'tid': tid, 'kind': kind, 'root': root}
                if descriptor is not None:
                    row['fd'] = descriptor
                hits.append(row)

    def task_identity(task):
        raw = read(task / 'stat', 65536).decode('ascii', 'surrogateescape')
        tail = raw[raw.rfind(')') + 2:].split()
        if len(tail) < 20:
            raise Incomplete('invalid_task_stat')
        return int(tail[19]), tail[0], int(tail[6])

    def inspect_link(path, pid, tid, kind, quiet_missing=False, descriptor=None):
        try:
            displayed = os.readlink(path)
        except (FileNotFoundError, ProcessLookupError):
            if not quiet_missing:
                error('missing_task_' + kind, pid, tid)
            return None
        try:
            before = os.stat(path)
            after = os.readlink(path)
            final = os.stat(path)
        except (FileNotFoundError, ProcessLookupError):
            error('reference_vanished_during_read', pid, tid)
            return None
        if displayed != after or (before.st_dev, before.st_ino) != (final.st_dev, final.st_ino):
            raise Incomplete('reference_changed_during_read')
        owners = lexical_owner(displayed) | identities.get((before.st_dev, before.st_ino), set())
        hit(pid, tid, kind, owners, descriptor)
        return before.st_dev, before.st_ino

    def check_mounts(table, pid, tid, ns):
        for dev, source, point in table:
            bound()
            for root, (target_dev, internal) in bindings.items():
                kind = None
                if beneath(point, root):
                    kind = 'mount_at_or_below_target'
                elif dev == target_dev and beneath(source, internal):
                    kind = 'mount_source_inside_target'
                elif dev == target_dev and beneath(internal, source):
                    exposed = posixpath.normpath(posixpath.join(point, posixpath.relpath(internal, source)))
                    if exposed != root:
                        kind = 'ancestor_mount_alias'
                if kind:
                    key = (ns, root, kind, source, point)
                    if key not in mount_keys:
                        if len(mounts) >= 10000:
                            raise Incomplete('mount_hit_bound')
                        mount_keys.add(key)
                        mounts.append({'pid': pid, 'tid': tid, 'namespace': ns,
                                       'root': root, 'kind': kind})

    try:
        roots = list(roots)
        if not roots or len(roots) > MAX_ROOTS or len(set(roots)) != len(roots):
            raise Incomplete('invalid_root_count')
        if any(not isinstance(r, str) or r == '/' or not r.startswith('/') or
               posixpath.normpath(r) != r or '//' in r or '\x00' in r for r in roots):
            raise Incomplete('invalid_exact_root')
        host_mounts = read(proc / 'self' / 'mountinfo')
        table = mount_table(host_mounts)
        for root in roots:
            inventory(root, table)
        # Close inventory descriptors before observing our own task.
        pids = names(proc, MAX_TASKS)
        counts['processes'] = len(pids)
        root_tokens = [(r, os.fsencode(r)) for r in roots]
        for name in sorted(pids, key=int):
            pid = int(name)
            process = proc / name
            try:
                leader = task_identity(process)
                tids = names(process / 'task', MAX_TASKS)
                if not tids:
                    raise Incomplete('empty_task_directory')
                for tname in sorted(tids, key=int):
                    bound()
                    counts['tasks'] += 1
                    if counts['tasks'] > MAX_TASKS:
                        raise Incomplete('task_bound')
                    tid, task = int(tname), process / 'task' / tname
                    try:
                        identity = task_identity(task)
                        # A verified single-thread Z/X task cannot acquire new
                        # references. Missing namespace alone never proves this.
                        if (identity[1] in ('Z', 'X') and leader[1] in ('Z', 'X') and
                                identity[0] == leader[0] and len(tids) == 1 and tid == pid):
                            absent = 0
                            for reference in ('ns/mnt', 'cwd', 'exe', 'root'):
                                try:
                                    os.readlink(task / reference)
                                except (FileNotFoundError, ProcessLookupError):
                                    absent += 1
                            if absent == 4:
                                if (names(task / 'fd', MAX_FDS) or read(task / 'maps') or
                                        read(task / 'cmdline', 1024 * 1024)):
                                    raise Incomplete('zombie_reference_view_not_empty')
                                if task_identity(task) != identity:
                                    raise Incomplete('zombie_identity_changed')
                                counts['empty_zombies'] += 1
                                continue
                        ns = os.readlink(task / 'ns' / 'mnt')
                        # Z/X has no general missing-link exemption: only the
                        # fully empty, stable branch above can waive visibility.
                        inactive = bool(identity[2] & 0x200000)
                        for kind in ('cwd', 'exe'):
                            inspect_link(task / kind, pid, tid, kind, inactive)
                        root_identity = inspect_link(task / 'root', pid, tid, 'root', inactive)
                        fds = names(task / 'fd', MAX_FDS)
                        counts['fds'] += len(fds)
                        if counts['fds'] > MAX_FDS:
                            raise Incomplete('fd_bound')
                        for descriptor in sorted(fds, key=int):
                            # A closed descriptor may vanish after enumeration.
                            # An occupied slot changing while read is UNKNOWN.
                            inspect_link(task / 'fd' / descriptor, pid, tid, 'fd', True, descriptor)
                        for line in read(task / 'maps').decode('utf-8', 'surrogateescape').splitlines():
                            bound()
                            fields = line.split(None, 5)
                            if len(fields) < 5 or not re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+', fields[3]):
                                raise Incomplete('invalid_maps')
                            major, minor = (int(x, 16) for x in fields[3].split(':'))
                            inode = int(fields[4])
                            owners = identities.get((os.makedev(major, minor), inode), set()) if inode else set()
                            if len(fields) == 6:
                                owners = owners | lexical_owner(unescape(fields[5]))
                            hit(pid, tid, 'maps', owners)
                        args = read(task / 'cmdline', 1024 * 1024)
                        for root, token in root_tokens:
                            if token in args:
                                hit(pid, tid, 'owner_argument_reference', {root})
                        raw = read(task / 'mountinfo')
                        namespaces.add(ns)
                        check_mounts(mount_table(raw), pid, tid, ns)
                        view = (ns, root_identity)
                        if view in mount_views and mount_views[view][1] != raw:
                            raise Incomplete('mount_view_changed')
                        mount_views[view] = (task, raw, identity[0])
                        if names(task / 'fd', MAX_FDS) != fds:
                            error('task_fd_set_changed', pid, tid)
                        if root_identity is not None:
                            current_root = os.stat(task / 'root')
                            if (current_root.st_dev, current_root.st_ino) != root_identity:
                                error('task_root_changed', pid, tid)
                        if os.readlink(task / 'ns' / 'mnt') != ns or task_identity(task)[0] != identity[0]:
                            raise Incomplete('task_identity_or_namespace_changed')
                    except (OSError, ValueError, Incomplete) as exc:
                        error(str(exc) if isinstance(exc, Incomplete) else type(exc).__name__, pid, tid)
                if names(process / 'task', MAX_TASKS) != tids or task_identity(process)[0] != leader[0]:
                    error('task_set_or_leader_changed', pid)
            except (OSError, ValueError, Incomplete) as exc:
                error(str(exc) if isinstance(exc, Incomplete) else type(exc).__name__, pid)
        if names(proc, MAX_TASKS) != pids:
            error('process_set_changed')
        for (ns, root_identity), (task, raw, start) in mount_views.items():
            bound()
            if (task_identity(task)[0] != start or os.readlink(task / 'ns' / 'mnt') != ns or
                    read(task / 'mountinfo') != raw):
                error('mount_view_changed_after_scan')
            if root_identity is not None:
                current_root = os.stat(task / 'root')
                if (current_root.st_dev, current_root.st_ino) != root_identity:
                    error('mount_view_root_changed_after_scan')
        if read(proc / 'self' / 'mountinfo') != host_mounts:
            error('host_mount_view_changed')
        for path, expected in snapshots.items():
            bound()
            fd = secure_open(path)
            try:
                if metadata(os.fstat(fd)) != expected:
                    error('target_inventory_changed')
            finally:
                os.close(fd)
    except (OSError, ValueError, TypeError, Incomplete) as exc:
        error(str(exc) if isinstance(exc, Incomplete) else type(exc).__name__)
    return {'observed_utc': now(), 'processes': counts['processes'],
            'tasks': counts['tasks'], 'target_entries': counts['entries'],
            'verified_empty_zombies': counts['empty_zombies'],
            'mount_namespaces': len(namespaces),
            'process_or_owner_hits': hits, 'mount_hits': mounts, 'coverage_errors': errors,
            'visibility': 'UNKNOWN' if errors else 'OBSERVED',
            'command_line_contents_retained': False, 'open_file_contents_read': False,
            'deletion_authorized': False}
