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
    import fcntl
    import posixpath
    import re
    import stat
    import time

    hits, mounts, errors = [], [], []
    hit_keys, mount_keys, error_keys = set(), set(), set()
    namespaces, mount_views, snapshots, identities = set(), {}, {}, {}
    bindings = {}
    opaque_namespaces, covered_namespace_views = set(), set()
    namespace_fd_labels, alias_keys = set(), set()
    namespace_candidates, namespace_handles, namespace_mount_paths, namespace_task_paths = {}, {}, {}, {}
    namespace_pool = None
    namespace_file_device = None
    counts_namespace_witnesses = 0
    namespace_child_lifecycle = {'created': 0, 'retirement_records': 0, 'reaped': 0,
                                 'nonzero_exits': 0, 'close_succeeded': True}
    existing_host_namespace_unchanged = None
    namespace_child_terminals = []
    counts = {'processes': 0, 'tasks': 0, 'entries': 0, 'fds': 0, 'empty_zombies': 0}
    started = time.monotonic()
    proc = Path('/proc')
    MAX_ROOTS, MAX_ENTRIES, MAX_TASKS, MAX_FDS = 128, 100000, 20000, 500000
    MAX_READ, MAX_SECONDS = 16 * 1024 * 1024, 45

    def make_namespace_view_collector(deadline, max_read=4 * 1024 * 1024,
                                      max_children=32):
        import ctypes
        import errno
        import fcntl
        import hashlib
        import json
        import os
        import select
        import signal
        import time
    
        CLONE_NEWNS = 0x20000
        NS_GET_NSTYPE = 0xb703
        REPORT_LIMIT = 16384
        TOTAL_RAW_LIMIT = 16 * 1024 * 1024
        started = time.monotonic()
        if not isinstance(deadline, (int, float)) or not started < deadline <= started + 45:
            raise ValueError("collector_deadline")
        if not isinstance(max_read, int) or not 1024 <= max_read <= 16 * 1024 * 1024:
            raise ValueError("collector_read_bound")
        if not isinstance(max_children, int) or not 1 <= max_children <= 32:
            raise ValueError("collector_child_bound")
        stop = deadline - 2.0
        if stop <= started:
            raise ValueError("collector_retirement_reserve")
        if not hasattr(os, "setns") or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise RuntimeError("collector_linux_api_unavailable")
        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            raise RuntimeError("collector_requires_default_sigchld")
        parent_pid = os.getpid()
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                              ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        procfd = os.open("/proc", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            taskfd = os.open(str(parent_pid) + "/task",
                             os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=procfd)
            try:
                with os.scandir(taskfd) as entries:
                    count = 0
                    for entry in entries:
                        if entry.name.isdigit():
                            count += 1
                            if count > 1:
                                raise RuntimeError("collector_requires_single_thread")
                if count != 1:
                    raise RuntimeError("collector_task_view_invalid")
            finally:
                os.close(taskfd)
        except BaseException:
            os.close(procfd)
            raise
        records = {}
        order = []
        retired = []
        closed = False
        total_raw = 0
    
        class NamespaceViewError(RuntimeError):
            pass
    
        def need(condition, code):
            if not condition:
                raise NamespaceViewError(code)
    
        def bound():
            need(not closed, "collector_closed")
            need(time.monotonic() < stop, "collector_deadline")
    
        def identity(s):
            return s.st_dev, s.st_ino
    
        def ns_identity(fd):
            need(fcntl.ioctl(fd, NS_GET_NSTYPE) == CLONE_NEWNS, "namespace_type_mismatch")
            return identity(os.fstat(fd))
    
        def read_at(path, maximum):
            bound()
            fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC, dir_fd=procfd)
            try:
                data = bytearray()
                while len(data) <= maximum:
                    bound()
                    part = os.read(fd, min(65536, maximum + 1 - len(data)))
                    if not part:
                        bound()
                        return bytes(data)
                    data.extend(part)
                raise NamespaceViewError("collector_read_bound")
            finally:
                os.close(fd)
    
        def decimal(value):
            need(value and all(48 <= c <= 57 for c in value), "collector_nondecimal")
            return int(value)
    
        def mount_id(raw):
            matches = [ln.split(b":", 1)[1].strip() for ln in raw.splitlines()
                       if ln.startswith(b"mnt_id:")]
            need(len(matches) == 1, "root_fd_mount_id")
            return decimal(matches[0])
    
        def unescape(value):
            result = bytearray()
            i = 0
            while i < len(value):
                if value[i] == 92:
                    chunk = value[i:i + 4]
                    need(chunk in (b"\\040", b"\\011", b"\\012", b"\\134"),
                         "mountinfo_path_escape")
                    result.append(int(chunk[1:], 8))
                    i += 4
                else:
                    result.append(value[i])
                    i += 1
            return bytes(result)
    
        def root_row(raw, wanted):
            need(raw and raw.endswith(b"\n"), "mountinfo_incomplete")
            seen = set()
            found = None
            for line in raw.splitlines():
                bound()
                fields = line.split(b" ")
                need(len(fields) >= 10 and all(fields), "mountinfo_fields")
                cuts = [i for i, field in enumerate(fields) if field == b"-"]
                need(len(cuts) == 1 and cuts[0] >= 6 and len(fields) == cuts[0] + 4,
                     "mountinfo_separator")
                mid = decimal(fields[0])
                need(mid not in seen, "mountinfo_duplicate_id")
                seen.add(mid)
                decimal(fields[1])
                parts = fields[2].split(b":")
                need(len(parts) == 2, "mountinfo_device")
                device = tuple(decimal(p) for p in parts)
                root, point = unescape(fields[3]), unescape(fields[4])
                need(point.startswith(b"/"), "mountinfo_point")
                if not root.startswith(b"/"):
                    token = root[5:-1] if root.startswith(b"mnt:[") and root.endswith(b"]") else b""
                    need(fields[cuts[0] + 1] == b"nsfs" and token and decimal(token) > 0,
                         "mountinfo_opaque_root")
                if mid == wanted:
                    found = (device, root, point)
            need(found is not None, "root_mount_missing")
            need(found[2] == b"/", "root_mountpoint_not_root")
            return found
    
        def task_start(pid):
            raw = read_at(str(pid) + "/stat", 65536)
            mark = raw.rfind(b") ")
            need(mark >= 0, "task_stat_format")
            tail = raw[mark + 2:].split()
            need(len(tail) >= 20 and tail[0] not in (b"Z", b"X"), "child_not_live")
            need(decimal(tail[1]) == parent_pid, "child_parent_changed")
            return decimal(tail[19])
    
        def current_namespace(pid):
            fd = os.open(str(pid) + "/ns/mnt", os.O_RDONLY | os.O_CLOEXEC,
                         dir_fd=procfd)
            try:
                return ns_identity(fd)
            finally:
                os.close(fd)
    
        def snapshot(pid, rootfd_number, expected):
            bound()
            first_start = task_start(pid)
            need(current_namespace(pid) == expected, "child_namespace_mismatch")
            prefix = str(pid) + "/"
            before = os.stat(prefix + "root", dir_fd=procfd)
            held_root = os.stat(prefix + "fd/" + str(rootfd_number), dir_fd=procfd)
            need(identity(before) == identity(held_root), "child_root_fd_mismatch")
            displayed = os.readlink(prefix + "root", dir_fd=procfd)
            need(displayed.startswith("/") and not displayed.endswith(" (deleted)"),
                 "child_root_display_invalid")
            mid = mount_id(read_at(prefix + "fdinfo/" + str(rootfd_number), 65536))
            raw = read_at(prefix + "mountinfo", max_read)
            device, root, point = root_row(raw, mid)
            need(device == (os.major(before.st_dev), os.minor(before.st_dev)),
                 "child_root_device_mismatch")
            second = read_at(prefix + "mountinfo", max_read)
            need(second == raw, "child_mount_view_changed")
            need(identity(os.stat(prefix + "root", dir_fd=procfd)) == identity(before),
                 "child_root_changed")
            need(os.readlink(prefix + "root", dir_fd=procfd) == displayed,
                 "child_root_display_changed")
            need(mount_id(read_at(prefix + "fdinfo/" + str(rootfd_number), 65536)) == mid,
                 "child_root_mount_changed")
            need(current_namespace(pid) == expected and task_start(pid) == first_start,
                 "child_identity_changed")
            bound()
            return {"starttime": first_start, "namespace": expected,
                    "root_identity": identity(before), "root_displayed": displayed,
                    "root_mnt_id": mid, "raw": raw,
                    "mountinfo_sha256": hashlib.sha256(raw).hexdigest()}
    
        def close_unneeded(keep):
            directory = os.open(str(os.getpid()) + "/fd",
                                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                                dir_fd=procfd)
            try:
                names = []
                with os.scandir(directory) as entries:
                    for entry in entries:
                        names.append(entry.name)
                        need(len(names) <= 4096, "inherited_fd_bound")
                for name in names:
                    if name.isdigit():
                        fd = int(name)
                        if fd not in keep and fd != directory:
                            try:
                                os.close(fd)
                            except OSError as exc:
                                if exc.errno != errno.EBADF:
                                    raise
            finally:
                os.close(directory)
    
        def child(nsfd, expected, control, report):
            try:
                need(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0, "pdeathsig_setup")
                configured_signal = ctypes.c_int()
                need(libc.prctl(2, ctypes.addressof(configured_signal), 0, 0, 0) == 0
                     and configured_signal.value == signal.SIGKILL, "pdeathsig_readback")
                need(os.getppid() == parent_pid, "parent_exited_before_pdeathsig")
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
                signal.setitimer(signal.ITIMER_REAL, max(0.001, stop - time.monotonic()))
                close_unneeded({0, 1, 2, procfd, nsfd, control, report})
                need(ns_identity(nsfd) == expected, "held_namespace_changed")
                os.setns(nsfd, CLONE_NEWNS)
                need(os.getppid() == parent_pid, "parent_exited_after_setns")
                need(current_namespace(os.getpid()) == expected, "setns_identity_mismatch")
                rootfd_number = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
                # This is evaluated inside the namespace immediately after direct
                # setns, without chroot, fchdir, namespace wrappers, or exec.
                need(os.readlink(str(os.getpid()) + "/root", dir_fd=procfd) == "/",
                     "native_root_link")
                data = snapshot(os.getpid(), rootfd_number, expected)
                message = {"pid": os.getpid(), "rootfd": rootfd_number,
                           "pdeath_signal": configured_signal.value,
                           "starttime": data["starttime"], "namespace": expected,
                           "root_identity": data["root_identity"],
                           "root_mnt_id": data["root_mnt_id"],
                           "mountinfo_sha256": data["mountinfo_sha256"]}
                encoded = json.dumps(message, sort_keys=True).encode()
                need(len(encoded) <= REPORT_LIMIT, "child_report_bound")
                while encoded:
                    count = os.write(report, encoded)
                    encoded = encoded[count:]
                os.close(report)
                # Stable FD set and task root throughout the scanner's observation.
                while True:
                    remaining = stop - time.monotonic()
                    if remaining <= 0:
                        os._exit(124)
                    ready, _, _ = select.select([control], [], [], remaining)
                    if ready:
                        command = os.read(control, 1)
                        os._exit(0 if command in (b"", b"X") else 125)
            except BaseException as exc:
                message = {"error": str(exc) if isinstance(exc, NamespaceViewError)
                           else type(exc).__name__, "errno": getattr(exc, "errno", None)}
                try:
                    encoded = json.dumps(message, sort_keys=True).encode()
                    os.write(report, encoded[:REPORT_LIMIT])
                except BaseException:
                    pass
                os._exit(126)
    
        def record_for(witness):
            record = records.get(id(witness))
            need(record is not None and record["witness"] is witness,
                 "unowned_namespace_witness")
            return record
    
        def reap(record):
            if record.get("wait_status") is not None:
                return True
            result, status = os.waitpid(record["pid"], os.WNOHANG)
            if result:
                record["wait_status"] = status
                return True
            return False
    
        def alive(record):
            need(not reap(record), "namespace_child_exited")
            need(not select.select([record["pidfd"]], [], [], 0)[0],
                 "namespace_pidfd_exited")
    
        class Witness:
            __slots__ = ()
            @property
            def pid(self):
                return record_for(self)["pid"]
            @property
            def starttime(self):
                return record_for(self)["snapshot"]["starttime"]
            @property
            def namespace(self):
                return record_for(self)["snapshot"]["namespace"]
            @property
            def root_identity(self):
                return record_for(self)["snapshot"]["root_identity"]
            @property
            def root_displayed(self):
                return record_for(self)["snapshot"]["root_displayed"]
            @property
            def pdeath_signal(self):
                return record_for(self)["pdeath_signal"]
            @property
            def root_mnt_id(self):
                return record_for(self)["snapshot"]["root_mnt_id"]
            @property
            def raw(self):
                return record_for(self)["snapshot"]["raw"]
    
        class Collector:
            Error = NamespaceViewError
            @property
            def witnesses(self):
                return tuple(r["witness"] for r in order if "snapshot" in r)
            @property
            def retirement(self):
                return tuple(dict(item) for item in retired)
    
            def acquire(self, fd, expected=None):
                nonlocal total_raw
                bound()
                actual = ns_identity(fd)
                if expected is not None:
                    need(type(expected) in (tuple, list) and len(expected) == 2
                         and tuple(expected) == actual, "expected_namespace_mismatch")
                for record in order:
                    if record.get("expected") == actual:
                        self.verify(record["witness"])
                        return record["witness"]
                need(len(order) < max_children, "collector_child_bound")
                nsfd = control_read = control_write = report_read = report_write = None
                pid = None
                try:
                    nsfd = os.dup(fd)
                    os.set_inheritable(nsfd, False)
                    control_read, control_write = os.pipe2(os.O_CLOEXEC)
                    report_read, report_write = os.pipe2(os.O_CLOEXEC)
                    witness = Witness()
                    record = {"witness": witness, "nsfd": nsfd, "expected": actual,
                              "control": control_write, "report": report_read,
                              "wait_status": None}
                    pid = os.fork()
                    if pid == 0:
                        child(nsfd, actual, control_read, report_write)
                        os._exit(127)
                    record["pid"] = pid
                    records[id(witness)] = record
                    order.append(record)
                    os.close(control_read)
                    control_read = None
                    os.close(report_write)
                    report_write = None
                    record["pidfd"] = os.pidfd_open(pid, 0)
                    os.set_blocking(report_read, False)
                    encoded = bytearray()
                    handshake_end = min(stop, time.monotonic() + 5)
                    eof = False
                    while time.monotonic() < handshake_end:
                        alive(record)
                        ready, _, _ = select.select([report_read], [], [],
                                                    max(0.0, min(0.05, handshake_end - time.monotonic())))
                        if ready:
                            part = os.read(report_read, REPORT_LIMIT + 1 - len(encoded))
                            if not part:
                                eof = True
                                break
                            encoded.extend(part)
                            need(len(encoded) <= REPORT_LIMIT, "child_report_bound")
                    need(eof, "namespace_child_handshake_timeout")
                    os.close(report_read)
                    record["report"] = None
                    message = json.loads(encoded)
                    need(type(message) is dict and "error" not in message, "namespace_child_failed")
                    need(message.get("pid") == pid and type(message.get("rootfd")) is int
                         and message["rootfd"] >= 3, "namespace_child_report_identity")
                    snap = snapshot(pid, message["rootfd"], actual)
                    need(message.get("pdeath_signal") == signal.SIGKILL
                         and message.get("starttime") == snap["starttime"]
                         and tuple(message.get("namespace", ())) == actual
                         and tuple(message.get("root_identity", ())) == snap["root_identity"]
                         and message.get("root_mnt_id") == snap["root_mnt_id"]
                         and message.get("mountinfo_sha256") == snap["mountinfo_sha256"],
                         "namespace_child_report_disagrees")
                    need(total_raw + len(snap["raw"]) <= TOTAL_RAW_LIMIT,
                         "collector_total_read_bound")
                    total_raw += len(snap["raw"])
                    record["rootfd"] = message["rootfd"]
                    record["pdeath_signal"] = message["pdeath_signal"]
                    record["snapshot"] = snap
                    alive(record)
                    bound()
                    return witness
                finally:
                    for item in (control_read, report_write):
                        if item is not None:
                            os.close(item)
                    if pid is None:
                        for item in (nsfd, control_write, report_read):
                            if item is not None:
                                os.close(item)
    
            def verify(self, witness):
                bound()
                record = record_for(witness)
                need("snapshot" in record, "namespace_witness_not_ready")
                alive(record)
                need(ns_identity(record["nsfd"]) == record["expected"],
                     "held_namespace_changed")
                current = snapshot(record["pid"], record["rootfd"], record["expected"])
                need(current == record["snapshot"], "namespace_witness_changed")
                alive(record)
                bound()
                return True
    
            def matches(self, witness, pid, starttime, namespace, root_identity,
                        root_displayed, raw):
                self.verify(witness)
                record = record_for(witness)
                snap = record["snapshot"]
                need(pid == record["pid"] and starttime == snap["starttime"]
                     and tuple(namespace) == snap["namespace"]
                     and tuple(root_identity) == snap["root_identity"]
                     and root_displayed == snap["root_displayed"]
                     and raw == snap["raw"], "scanner_witness_mismatch")
                bound()
                return True
    
            def require_coverage(self, expected):
                needed = set(tuple(ns) for ns in expected)
                known = {record["expected"] for record in order if "snapshot" in record}
                need(needed <= known, "namespace_coverage_missing")
                for record in order:
                    if record["expected"] in needed:
                        self.verify(record["witness"])
                return True
    
            def close(self):
                nonlocal closed
                if closed:
                    need(all(item["reaped"] and item["exit_code"] == 0 for item in retired),
                         "collector_retirement_failed")
                    return self.retirement
                # Child work stops two seconds before the supplied absolute budget.
                for record in order:
                    control = record.get("control")
                    if control is not None:
                        try:
                            os.write(control, b"X")
                        except BrokenPipeError:
                            pass
                        finally:
                            os.close(control)
                            record["control"] = None
                gentle_end = min(deadline - 0.5, time.monotonic() + 0.5)
                while time.monotonic() < gentle_end and any(not reap(r) for r in order):
                    time.sleep(0.005)
                for record in order:
                    if not reap(record):
                        try:
                            if "pidfd" in record:
                                signal.pidfd_send_signal(record["pidfd"], signal.SIGKILL)
                            else:
                                os.kill(record["pid"], signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                while time.monotonic() < deadline and any(not reap(r) for r in order):
                    time.sleep(0.005)
                for record in order:
                    status = record.get("wait_status")
                    retired.append({"pid": record["pid"], "namespace": record["expected"],
                                    "reaped": status is not None,
                                    "exit_code": os.waitstatus_to_exitcode(status)
                                    if status is not None else None})
                    for key in ("report", "control", "nsfd", "pidfd"):
                        fd = record.get(key)
                        if fd is not None:
                            os.close(fd)
                            record[key] = None
                os.close(procfd)
                closed = True
                need(all(item["reaped"] and item["exit_code"] == 0 for item in retired),
                     "collector_retirement_failed")
                return self.retirement
    
            def __enter__(self):
                bound()
                return self
    
            def __exit__(self, exc_type, exc, tb):
                self.close()
                return False
    
        return Collector()

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

    def lexical_owner(path, aliases=()):
        path = path.removesuffix(' (deleted)')
        if not path.startswith('/'):
            return set()
        path = posixpath.normpath(path)
        owners = {r for r in roots if beneath(path, r)}
        owners.update(root for root, exposed, _ in aliases if beneath(path, exposed))
        return owners

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
        table, mount_ids = [], set()
        for line in raw.decode('utf-8', 'surrogateescape').splitlines():
            bound()
            fields = line.split()
            if len(fields) < 10 or '-' not in fields or fields.index('-') < 6:
                raise Incomplete('invalid_mountinfo')
            if not re.fullmatch(r'[0-9]+:[0-9]+', fields[2]):
                raise Incomplete('invalid_mount_device')
            mount_id, parent_id = int(fields[0]), int(fields[1])
            if mount_id <= 0 or parent_id <= 0 or mount_id in mount_ids:
                raise Incomplete('invalid_or_duplicate_mount_id')
            mount_ids.add(mount_id)
            dev = tuple(int(x) for x in fields[2].split(':'))
            separator = fields.index('-')
            if len(fields) <= separator + 3:
                raise Incomplete('invalid_mountinfo')
            filesystem_type = fields[separator + 1]
            mount_root, point = unescape(fields[3]), unescape(fields[4])
            if not point.startswith('/'):
                raise Incomplete('invalid_mount_path')
            namespace_label = None
            if not mount_root.startswith('/'):
                if filesystem_type != 'nsfs' or not re.fullmatch(r'mnt:\[[1-9][0-9]*\]', mount_root):
                    raise Incomplete('invalid_mount_path')
                namespace_label = mount_root
                opaque_namespaces.add(namespace_label)
                if len(opaque_namespaces) > MAX_TASKS:
                    raise Incomplete('namespace_reference_bound')
                mount_root = None
            table.append({'id': mount_id, 'parent': parent_id, 'dev': dev,
                          'mount_root': posixpath.normpath(mount_root) if mount_root is not None else None,
                          'point': posixpath.normpath(point), 'namespace': namespace_label})
        if not table:
            raise Incomplete('empty_mountinfo')
        return table

    def deepest_mount(path, table, error_code):
        candidates = [m for m in table if beneath(path, m['point'])]
        if not candidates:
            raise Incomplete(error_code)
        longest = max(len(m['point']) for m in candidates)
        deepest = [m for m in candidates if len(m['point']) == longest]
        if len(deepest) != 1:
            raise Incomplete(error_code)
        return deepest[0]

    def validate_root_mount(table, mount_id, root_identity):
        found = [m for m in table if m['id'] == mount_id]
        if (len(found) != 1 or found[0]['point'] != '/' or
                found[0]['dev'] != (os.major(root_identity[0]), os.minor(root_identity[0]))):
            raise Incomplete('root_mount_view_unresolved')

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
            mount = deepest_mount(root, table, 'ambiguous_target_mount')
            dev, source, point = mount['dev'], mount['mount_root'], mount['point']
            if source is None:
                raise Incomplete('opaque_target_mount')
            if dev != (os.major(initial.st_dev), os.minor(initial.st_dev)):
                raise Incomplete('target_mount_device_mismatch')
            internal = posixpath.normpath(posixpath.join(source, posixpath.relpath(root, point)))
            bindings[root] = (dev, internal)
            mounted = {m['point'] for m in table if beneath(m['point'], root)}

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

    def fd_mount_id(handle):
        info = read(Path('/proc/self/fdinfo') / str(handle), 65536)
        values = [line.split(b':', 1)[1].strip() for line in info.splitlines()
                  if line.startswith(b'mnt_id:')]
        if len(values) != 1 or not values[0].isdigit() or int(values[0]) <= 0:
            raise Incomplete('root_mount_id_unknown')
        return int(values[0])

    def root_mount_id(task, expected):
        handle = os.open(task / 'root', os.O_PATH | os.O_CLOEXEC)
        try:
            actual = os.fstat(handle)
            if (actual.st_dev, actual.st_ino) != expected:
                raise Incomplete('task_root_changed')
            return fd_mount_id(handle)
        finally:
            os.close(handle)

    def inspect_link(path, pid, tid, kind, quiet_missing=False, descriptor=None,
                     aliases=(), namespace_context=None):
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
        owners = lexical_owner(displayed, aliases) | identities.get((before.st_dev, before.st_ino), set())
        if kind == 'fd' and before.st_dev == namespace_file_device and namespace_context is not None:
            key = (before.st_dev, before.st_ino)
            if key not in namespace_candidates:
                if len(namespace_candidates) >= MAX_ROOTS:
                    raise Incomplete('namespace_descriptor_bound')
                namespace_candidates[key] = (path, displayed, namespace_context)
        hit(pid, tid, kind, owners, descriptor)
        return before.st_dev, before.st_ino

    def mount_aliases(table, ns, task, root_identity, root_mount):
        aliases = set()
        anchor = os.open(task / 'root', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            actual = os.fstat(anchor)
            if ((actual.st_dev, actual.st_ino) != root_identity or
                    fd_mount_id(anchor) != root_mount):
                raise Incomplete('alias_view_root_changed')
            indexed = {m['id']: m for m in table}
            for mount in table:
                bound()
                source, point, dev = mount['mount_root'], mount['point'], mount['dev']
                if source is None:
                    continue
                for root, (target_dev, internal) in bindings.items():
                    if dev != target_dev or not beneath(internal, source):
                        continue
                    exposed = posixpath.normpath(posixpath.join(point, posixpath.relpath(internal, source)))
                    selected = deepest_mount(exposed, table, 'ambiguous_alias_mount')
                    resolved = (posixpath.normpath(posixpath.join(selected['mount_root'],
                                posixpath.relpath(exposed, selected['point'])))
                                if selected['mount_root'] is not None else None)
                    if selected['dev'] != target_dev or resolved != internal:
                        raise Incomplete('shadowed_alias_mount')
                    cursor, visited = selected['id'], set()
                    while cursor != root_mount:
                        if cursor in visited or cursor not in indexed or len(visited) >= 128:
                            raise Incomplete('alias_mount_ancestry_unknown')
                        visited.add(cursor)
                        cursor = indexed[cursor]['parent']
                    key = (root, exposed, selected['id'])
                    if key in aliases:
                        continue
                    descriptor = os.dup(anchor)
                    try:
                        parts = exposed.split('/')[1:]
                        for i, part in enumerate(parts):
                            bound()
                            flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
                            if i != len(parts) - 1:
                                flags |= os.O_DIRECTORY
                            child = os.open(part, flags, dir_fd=descriptor)
                            os.close(descriptor)
                            descriptor = child
                        final = os.fstat(descriptor)
                        if metadata(final) != snapshots[root]:
                            raise Incomplete('alias_target_identity_mismatch')
                        if fd_mount_id(descriptor) != selected['id']:
                            raise Incomplete('alias_target_mount_mismatch')
                    finally:
                        os.close(descriptor)
                    aliases.add(key)
                    if exposed != root:
                        alias_keys.add((ns, *key))
                        if len(alias_keys) > 10000:
                            raise Incomplete('mount_alias_bound')
            if fd_mount_id(anchor) != root_mount:
                raise Incomplete('alias_view_root_changed')
        finally:
            # Every temporary root/target descriptor closes before the FD census.
            os.close(anchor)
        return tuple(sorted(aliases))

    def check_mounts(table, aliases, pid, tid, ns):
        for mount in table:
            bound()
            source, point, dev = mount['mount_root'], mount['point'], mount['dev']
            for root, (target_dev, internal) in bindings.items():
                kind = None
                if beneath(point, root) or any(owner == root and beneath(point, exposed)
                                               for owner, exposed, _ in aliases):
                    kind = 'mount_at_or_below_target'
                elif source is not None and dev == target_dev and beneath(source, internal):
                    kind = 'mount_source_inside_target'
                # A strict ancestor bind provides a path alias, not ownership.
                # Actual references through it are checked in this task's view.
                if kind:
                    key = (ns, root, kind, source, point)
                    if key not in mount_keys:
                        if len(mounts) >= 10000:
                            raise Incomplete('mount_hit_bound')
                        mount_keys.add(key)
                        mounts.append({'pid': pid, 'tid': tid, 'namespace': ns,
                                       'root': root, 'kind': kind})

    def capture_namespace(path, expected, expected_label=None):
        # O_PATH pins the object before a readable namespace handle is opened;
        # a swapped /proc FD must never turn into an open of a device or FIFO.
        pinned = os.open(path, os.O_PATH | os.O_CLOEXEC)
        handle = None
        try:
            actual = os.fstat(pinned)
            key = (actual.st_dev, actual.st_ino)
            if key != expected or actual.st_dev != namespace_file_device:
                raise Incomplete('namespace_handle_identity_changed')
            handle = os.open('/proc/self/fd/' + str(pinned), os.O_RDONLY | os.O_CLOEXEC)
            actual = os.fstat(handle)
            if (actual.st_dev, actual.st_ino) != expected:
                raise Incomplete('namespace_handle_identity_changed')
            namespace_type = fcntl.ioctl(handle, 0xb703)
            if namespace_type != 0x00020000:
                if expected_label is not None:
                    raise Incomplete('namespace_handle_wrong_type')
                return None
            label = 'mnt:[' + str(actual.st_ino) + ']'
            if expected_label is not None and label != expected_label:
                raise Incomplete('namespace_handle_wrong_identity')
            if label not in namespace_handles:
                if len(namespace_handles) >= MAX_ROOTS:
                    raise Incomplete('namespace_descriptor_bound')
                namespace_handles[label] = (handle, expected)
                handle = None
            return label
        finally:
            if handle is not None:
                os.close(handle)
            os.close(pinned)

    def close_namespace_pool(pool):
        success = False
        try:
            pool.close()
            success = True
        finally:
            rows = pool.retirement
            namespace_child_terminals[:] = [dict(row) for row in rows]
            namespace_child_lifecycle.update({
                'created': len(rows) if success else None,
                'retirement_records': len(rows),
                'reaped': sum(row['reaped'] for row in rows),
                'nonzero_exits': sum(row['exit_code'] not in (None, 0) for row in rows),
                'close_succeeded': success,
            })

    def verify_namespace_origin(origin, expected):
        path, displayed, (task, start, ns) = origin
        actual = os.stat(path)
        if ((actual.st_dev, actual.st_ino) != expected or os.readlink(path) != displayed or
                task_identity(task)[0] != start or os.readlink(task / 'ns' / 'mnt') != ns):
            raise Incomplete('namespace_descriptor_origin_changed')

    try:
        roots = list(roots)
        if not roots or len(roots) > MAX_ROOTS or len(set(roots)) != len(roots):
            raise Incomplete('invalid_root_count')
        if any(not isinstance(r, str) or r == '/' or not r.startswith('/') or
               posixpath.normpath(r) != r or '//' in r or '\x00' in r for r in roots):
            raise Incomplete('invalid_exact_root')
        host_root_path = proc / 'self' / 'root'
        host_root = os.stat(host_root_path)
        host_root_identity = (host_root.st_dev, host_root.st_ino)
        observer_root = os.stat('/')
        if (os.readlink(host_root_path) != '/' or
                host_root_identity != (observer_root.st_dev, observer_root.st_ino)):
            raise Incomplete('observer_root_view_unknown')
        host_namespace = os.readlink('/proc/self/ns/mnt')
        namespace_stat = os.stat('/proc/self/ns/mnt')
        if (not re.fullmatch(r'mnt:\[[1-9][0-9]*\]', host_namespace) or
                namespace_stat.st_ino != int(host_namespace[5:-1])):
            raise Incomplete('observer_namespace_identity_unknown')
        namespace_file_device = namespace_stat.st_dev
        host_root_mount = root_mount_id(proc / 'self', host_root_identity)
        host_mounts = read(proc / 'self' / 'mountinfo')
        table = mount_table(host_mounts)
        validate_root_mount(table, host_root_mount, host_root_identity)
        for mount in table:
            if mount['namespace'] is not None:
                namespace_mount_paths.setdefault(mount['namespace'], []).append(
                    (mount['point'], os.makedev(*mount['dev'])))
        for root in roots:
            inventory(root, table)
        # Close inventory descriptors before observing our own task.
        pids = names(proc, MAX_TASKS)
        counts['processes'] = len(pids)
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
                        if not re.fullmatch(r'mnt:\[[1-9][0-9]*\]', ns):
                            raise Incomplete('invalid_task_namespace')
                        namespace_task_paths.setdefault(ns, (task, identity[0]))
                        # Z/X has no general missing-link exemption: only the
                        # fully empty, stable branch above can waive visibility.
                        inactive = bool(identity[2] & 0x200000)
                        root_identity = inspect_link(task / 'root', pid, tid, 'root', inactive)
                        root_displayed = os.readlink(task / 'root') if root_identity is not None else None
                        root_mount = root_mount_id(task, root_identity) if root_identity is not None else None
                        raw = read(task / 'mountinfo')
                        namespaces.add(ns)
                        view = (ns, root_identity, root_mount)
                        if view in mount_views:
                            if mount_views[view][1] != raw:
                                raise Incomplete('mount_view_changed')
                            aliases = mount_views[view][4]
                        else:
                            task_table = mount_table(raw)
                            if root_identity is not None:
                                validate_root_mount(task_table, root_mount, root_identity)
                            aliases = mount_aliases(task_table, ns, task, root_identity, root_mount)
                            check_mounts(task_table, aliases, pid, tid, ns)
                        mount_views[view] = (task, raw, identity[0], root_displayed, aliases)
                        inspect_link(task / 'root', pid, tid, 'root', inactive, aliases=aliases)
                        for kind in ('cwd', 'exe'):
                            inspect_link(task / kind, pid, tid, kind, inactive, aliases=aliases)
                        fds = names(task / 'fd', MAX_FDS)
                        counts['fds'] += len(fds)
                        if counts['fds'] > MAX_FDS:
                            raise Incomplete('fd_bound')
                        for descriptor in sorted(fds, key=int):
                            # A closed descriptor may vanish after enumeration.
                            # An occupied slot changing while read is UNKNOWN.
                            inspect_link(task / 'fd' / descriptor, pid, tid, 'fd', True, descriptor,
                                         aliases, (task, identity[0], ns))
                        for line in read(task / 'maps').decode('utf-8', 'surrogateescape').splitlines():
                            bound()
                            fields = line.split(None, 5)
                            if len(fields) < 5 or not re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+', fields[3]):
                                raise Incomplete('invalid_maps')
                            major, minor = (int(x, 16) for x in fields[3].split(':'))
                            inode = int(fields[4])
                            owners = identities.get((os.makedev(major, minor), inode), set()) if inode else set()
                            if len(fields) == 6:
                                owners = owners | lexical_owner(unescape(fields[5]), aliases)
                            hit(pid, tid, 'maps', owners)
                        args = read(task / 'cmdline', 1024 * 1024)
                        owner_tokens = {(root, os.fsencode(root)) for root in roots}
                        owner_tokens.update((root, os.fsencode(exposed)) for root, exposed, _ in aliases)
                        for root, token in owner_tokens:
                            if token in args:
                                hit(pid, tid, 'owner_argument_reference', {root})
                        for argument in args.split(b'\0'):
                            value = argument.split(b'=', 1)[-1]
                            if value.startswith(b'/'):
                                hit(pid, tid, 'owner_argument_reference',
                                    lexical_owner(os.fsdecode(value), aliases))
                        if read(task / 'mountinfo') != raw:
                            raise Incomplete('mount_view_changed')
                        if names(task / 'fd', MAX_FDS) != fds:
                            error('task_fd_set_changed', pid, tid)
                        if root_identity is not None:
                            current_root = os.stat(task / 'root')
                            if ((current_root.st_dev, current_root.st_ino) != root_identity or
                                    os.readlink(task / 'root') != root_displayed or
                                    root_mount_id(task, root_identity) != root_mount):
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
        for (ns, root_identity, root_mount), (task, raw, start, root_displayed, aliases) in mount_views.items():
            bound()
            verified = True
            if (task_identity(task)[0] != start or os.readlink(task / 'ns' / 'mnt') != ns or
                    read(task / 'mountinfo') != raw):
                error('mount_view_changed_after_scan')
                verified = False
            if root_identity is not None:
                current_root = os.stat(task / 'root')
                if ((current_root.st_dev, current_root.st_ino) != root_identity or
                        os.readlink(task / 'root') != root_displayed or
                        root_mount_id(task, root_identity) != root_mount):
                    error('mount_view_root_changed_after_scan')
                    verified = False
            # A foreign task may chroot into an alias of the observer's root.
            # Equal dev/inode alone cannot prove its complete namespace view.
            if (verified and ns == host_namespace and root_identity == host_root_identity and
                    root_mount == host_root_mount and root_displayed == '/'):
                covered_namespace_views.add(ns)
        for expected, origin in namespace_candidates.items():
            bound()
            verify_namespace_origin(origin, expected)
            label = capture_namespace(origin[0], expected)
            verify_namespace_origin(origin, expected)
            if label is not None:
                namespace_fd_labels.add(label)

        required_namespaces = namespaces | opaque_namespaces | namespace_fd_labels
        missing = required_namespaces - covered_namespace_views
        if missing and not errors:
            for ns in sorted(missing):
                if ns not in namespace_handles and ns in namespace_mount_paths:
                    path, dev = namespace_mount_paths[ns][0]
                    inode = int(ns[5:-1])
                    capture_namespace(path, (dev, inode), ns)
                elif ns not in namespace_handles and ns in namespace_task_paths:
                    task, start = namespace_task_paths[ns]
                    if task_identity(task)[0] != start or os.readlink(task / 'ns' / 'mnt') != ns:
                        raise Incomplete('namespace_task_origin_changed')
                    capture_namespace(task / 'ns' / 'mnt',
                                      (namespace_file_device, int(ns[5:-1])), ns)
                    if task_identity(task)[0] != start or os.readlink(task / 'ns' / 'mnt') != ns:
                        raise Incomplete('namespace_task_origin_changed')
            # Factory is embedded in this function; only held kernel handles
            # may create witnesses. No receipt/dict can add coverage.
            namespace_pool = make_namespace_view_collector(started + MAX_SECONDS,
                                                          max_read=MAX_READ, max_children=32)
            try:
                for ns in sorted(missing):
                    bound()
                    if ns not in namespace_handles:
                        continue
                    handle, expected = namespace_handles[ns]
                    witness = namespace_pool.acquire(handle, expected=expected)
                    task = proc / str(witness.pid) / 'task' / str(witness.pid)
                    actual_root = os.stat(task / 'root')
                    root_identity = (actual_root.st_dev, actual_root.st_ino)
                    root_displayed = os.readlink(task / 'root')
                    raw = read(task / 'mountinfo')
                    if root_mount_id(task, root_identity) != witness.root_mnt_id:
                        raise Incomplete('namespace_witness_root_mount_changed')
                    actual_ns = os.stat(task / 'ns' / 'mnt')
                    if os.readlink(task / 'ns' / 'mnt') != ns:
                        raise Incomplete('namespace_witness_namespace_changed')
                    if not namespace_pool.matches(witness, witness.pid,
                            task_identity(task)[0], (actual_ns.st_dev, actual_ns.st_ino),
                            root_identity, root_displayed, raw):
                        raise Incomplete('namespace_witness_mismatch')
                    witness_table = mount_table(raw)
                    aliases = mount_aliases(witness_table, ns, task, root_identity, witness.root_mnt_id)
                    check_mounts(witness_table, aliases, witness.pid, witness.pid, ns)
                    if not namespace_pool.verify(witness):
                        raise Incomplete('namespace_witness_lost')
                    covered_namespace_views.add(ns)
                    counts_namespace_witnesses += 1
            finally:
                closing, namespace_pool = namespace_pool, None
                close_namespace_pool(closing)
            if names(proc, MAX_TASKS) != pids:
                error('process_set_changed_after_namespace_views')
            for (ns, root_identity, root_mount), (task, raw, start, root_displayed, _) in mount_views.items():
                bound()
                actual_root = os.stat(task / 'root') if root_identity is not None else None
                if (task_identity(task)[0] != start or os.readlink(task / 'ns' / 'mnt') != ns or
                        read(task / 'mountinfo') != raw or
                        (actual_root is not None and
                         ((actual_root.st_dev, actual_root.st_ino) != root_identity or
                          os.readlink(task / 'root') != root_displayed or
                          root_mount_id(task, root_identity) != root_mount))):
                    raise Incomplete('mount_view_changed_after_namespace_views')
            for expected, origin in namespace_candidates.items():
                verify_namespace_origin(origin, expected)

        if read(proc / 'self' / 'mountinfo') != host_mounts:
            existing_host_namespace_unchanged = False
            error('host_mount_view_changed')
        current_host_root = os.stat(host_root_path)
        if ((current_host_root.st_dev, current_host_root.st_ino) != host_root_identity or
                os.readlink(host_root_path) != '/' or
                root_mount_id(proc / 'self', host_root_identity) != host_root_mount or
                os.readlink('/proc/self/ns/mnt') != host_namespace):
            existing_host_namespace_unchanged = False
            error('observer_root_changed')
        if existing_host_namespace_unchanged is None:
            existing_host_namespace_unchanged = True
        for path, expected in snapshots.items():
            bound()
            fd = secure_open(path)
            try:
                if metadata(os.fstat(fd)) != expected:
                    error('target_inventory_changed')
            finally:
                os.close(fd)
    except (OSError, ValueError, TypeError, RuntimeError, Incomplete) as exc:
        error(str(exc) if isinstance(exc, Incomplete) else type(exc).__name__)
    finally:
        if namespace_pool is not None:
            try:
                close_namespace_pool(namespace_pool)
            except (OSError, ValueError, RuntimeError):
                error('namespace_collector_close_failed')
        for handle, _ in namespace_handles.values():
            try:
                os.close(handle)
            except OSError:
                error('namespace_handle_close_failed')
    required_namespaces = namespaces | opaque_namespaces | namespace_fd_labels
    uncovered_namespaces = required_namespaces - covered_namespace_views
    if uncovered_namespaces:
        error('persistent_mount_namespace_unobserved')
    return {'observed_utc': now(), 'processes': counts['processes'],
            'tasks': counts['tasks'], 'target_entries': counts['entries'],
            'verified_empty_zombies': counts['empty_zombies'],
            'mount_namespaces': len(namespaces),
            'ancestor_alias_count': len(alias_keys),
            'namespace_fd_count': len(namespace_fd_labels),
            'verified_namespace_witnesses': counts_namespace_witnesses,
            'namespace_child_lifecycle': namespace_child_lifecycle,
            'namespace_child_terminals': namespace_child_terminals,
            'existing_host_mount_namespace_unchanged': existing_host_namespace_unchanged,
            'Android_actions': 0, 'app_actions': 0,
            'required_mount_namespace_count': len(required_namespaces),
            'opaque_mount_namespace_count': len(opaque_namespaces),
            'covered_opaque_mount_namespace_count': len(opaque_namespaces & covered_namespace_views),
            'uncovered_mount_namespace_count': len(uncovered_namespaces),
            'uncovered_mount_namespaces': sorted(uncovered_namespaces)[:128],
            'process_or_owner_hits': hits, 'mount_hits': mounts, 'coverage_errors': errors,
            'visibility': 'UNKNOWN' if errors else 'OBSERVED',
            'command_line_contents_retained': False, 'open_file_contents_read': False,
            'deletion_authorized': False}
