"""One bounded logdr crash-buffer observation for an already held owned init.

The AOSP logdr protocol is a reference, not an assertion about the observed ELF.
There is one connection attempt and one read request. No log mutation, reconnect,
namespace entry, helper process, Main logging or lifecycle authority is provided.
"""
import array
import ctypes
import errno
import hashlib
import os
import select
import socket
import stat
import struct
import time

CAPACITY = 256 * 1024
PACKET_LIMIT = 5 * 1024
RECORD_LIMIT = 2048
PER_POLL_RECORDS = 32
CONNECT_SECONDS = 0.2
COMMAND = b'stream lids=4'
MAGIC = b'P4_GENERATION_CRASH_BUFFER4_V1\n'
OUTPUT = 'generation-crash-buffer4.bin'
HEADER = struct.Struct('<HHiIIIII')
ROOT_TMPFS = 0x01021994
LOGD_UID = 1036
LOGD_ELF_BYTES = 801680
LOGD_ELF_ACCESS = 0o550
LOGD_ELF_SHA256 = '00b71cfeea17a2fa6b2fa4047fb320bdd9d7b64ce16366bbbd2abdbda09d0905'
LOGD_IMAGE_OBSERVATION_SHA256 = '68fece28d8264afba6e123a2e02f4a2a75c05ffa969f975de5ff6dd46df6f5ae'
# The existing native role transport uses the same Linux UAPI value. Unsupported
# kernels fail before the read request; numeric SO_PEERCRED alone is insufficient.
SO_PEERPIDFD = 77


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(fd):
    value = os.fstat(fd)
    return {'device': value.st_dev, 'inode': value.st_ino}


def metadata(fd):
    value = os.fstat(fd)
    return {'device': value.st_dev, 'inode': value.st_ino,
            'mode': stat.S_IMODE(value.st_mode), 'uid': value.st_uid,
            'gid': value.st_gid, 'type': stat.S_IFMT(value.st_mode),
            'nlink': value.st_nlink, 'bytes': value.st_size}



def require_logd_stat(value, record):
    """Record the live fstat before checking the independently observed image tuple."""
    observed = {'device': value.st_dev, 'inode': value.st_ino, 'bytes': value.st_size,
                'full_st_mode': value.st_mode, 'type': stat.S_IFMT(value.st_mode),
                'mode': stat.S_IMODE(value.st_mode), 'access_0777': value.st_mode & 0o777,
                'special_permission_bits': value.st_mode & 0o7000,
                'uid': value.st_uid, 'gid': value.st_gid, 'nlink': value.st_nlink,
                'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns,
                'image_observation_sha256': LOGD_IMAGE_OBSERVATION_SHA256,
                'prior_image_complete_mode_observed': False,
                'live_special_bits_required': 0}
    record['fixed_logd_elf_observed'] = observed
    need(stat.S_ISREG(value.st_mode), 'fixed generation logd ELF is not regular')
    need(value.st_uid == value.st_gid == LOGD_UID,
         'fixed generation logd ELF owner differs from observed image')
    need(not value.st_mode & 0o222 and value.st_mode & 0o111,
         'fixed generation logd ELF writable or non-executable')
    need(value.st_mode & 0o777 == LOGD_ELF_ACCESS,
         'fixed generation logd ELF access differs from observed image')
    # dump.erofs did not expose special bits. This is a fresh live requirement,
    # not a claim that the earlier image observation measured those bits.
    need(not value.st_mode & 0o7000, 'fixed generation logd ELF has special permission bits')
    need(value.st_nlink == 1, 'fixed generation logd ELF link count differs from observed image')
    need(value.st_size == LOGD_ELF_BYTES,
         'fixed generation logd ELF length differs from observed image')
    return observed


def require_logd_digest(digest, record):
    record['fixed_logd_elf_observed']['sha256'] = digest
    need(digest == LOGD_ELF_SHA256,
         'fixed generation logd ELF full SHA differs from observed image')


def filesystem_type(fd):
    library = ctypes.CDLL(None, use_errno=True)
    library.fstatfs.argtypes = (ctypes.c_int, ctypes.c_void_p)
    library.fstatfs.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(256)
    if library.fstatfs(fd, buffer):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), 'held generation filesystem')
    return ctypes.c_long.from_buffer(buffer).value


def packet_header(packet):
    """Accept only a complete reference v4 crash packet; retain original bytes."""
    need(HEADER.size == 28 and 28 < len(packet) <= PACKET_LIMIT,
         'crash packet size outside reference bound')
    size, header_size, pid, tid, sec, nsec, lid, uid = HEADER.unpack_from(packet)
    need(header_size == 28 and len(packet) == header_size + size,
         'crash packet is incomplete or has a different header schema')
    need(pid > 0 and tid > 0 and sec > 0 and nsec < 1_000_000_000 and lid == 4,
         'crash packet identity/time/buffer differs')
    payload = packet[header_size:]
    need(len(payload) >= 4 and 1 <= payload[0] <= 8 and payload[-1] == 0,
         'crash packet priority or terminator differs')
    boundary = payload.find(b'\0', 1)
    need(1 < boundary <= 129 and boundary < len(payload) - 1,
         'crash packet tag boundary differs')
    tag = payload[1:boundary]
    public = tag.decode('ascii') if tag in (b'DEBUG', b'libc', b'hwservicemanager') else None
    return {'pid': pid, 'tid': tid, 'seconds': sec, 'nanoseconds': nsec,
            'buffer': lid, 'uid': uid, 'priority': payload[0],
            'public_tag': public, 'tag_sha256': hashlib.sha256(tag).hexdigest(),
            'packet_bytes': len(packet)}


class AncillaryCloseError(RuntimeError):
    """An unexpected received descriptor has an uncertain close result."""
    close_failure = True


def receive_packet(sock):
    """Close any unexpected transferred FDs before rejecting ancillary input."""
    packet, ancillary, flags, _ = sock.recvmsg(
        PACKET_LIMIT + 1, socket.CMSG_SPACE(8 * array.array('i').itemsize),
        socket.MSG_DONTWAIT | socket.MSG_CMSG_CLOEXEC)
    close_errors = []
    for level, kind, body in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            values = array.array('i')
            values.frombytes(body[:len(body) - len(body) % values.itemsize])
            for fd in values:
                try:
                    os.close(fd)
                except OSError as error:
                    close_errors.append(repr(error))
    if close_errors:
        raise AncillaryCloseError('unexpected rights close failure: ' + repr(close_errors[:4]))
    need(not ancillary and not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC),
         'unexpected ancillary data or truncated crash packet')
    return packet


class Capture:
    def __init__(self, init, audit, plan, evidence, owned, outer_deadline):
        self.init = init                 # Borrowed; the original actor owns it.
        self.owned = owned
        self.plan = plan
        self.evidence = evidence         # Borrowed; never closed by this object.
        self.deadline = outer_deadline
        self.fds = {}
        self.sock = None
        self.peer_value = None
        self.close_failed = False
        self.file_hash = hashlib.sha256()
        self.file_bytes = 0
        self.finished = False
        self.record = {
            'schema': 1, 'scope': 'one generation-private logdr crash buffer 4',
            'generation_nonce': audit.get('nonce'), 'state': 'INITIALIZING',
            'first_error': None, 'secondary_errors': [], 'connection_attempts': 0,
            'read_request_attempts': 0, 'read_request_completed': False,
            'source_qualified_before_request': False, 'protocol_observed': False,
            'records': 0, 'received_packets': 0, 'packet_bytes': 0, 'capacity_bytes': CAPACITY,
            'capacity_reached': False, 'record_bound_reached': False,
            'public_tag_counts': {'DEBUG': 0, 'libc': 0, 'hwservicemanager': 0, 'other': 0},
            'first_header': None, 'last_header': None, 'eof_observed': False,
            'empty_proves_hws_health': False, 'hws_attribution_qualified': False,
            'complete_log_stream_claimed': False, 'Main_logs_read': False,
            'log_mutation_requested': False, 'new_child_started': False,
            'namespace_or_UID_change_requested': False, 'held_fds_closed': False,
            'started_monotonic_ns': time.monotonic_ns(), 'original_stop_delayed_for_logs': False,
        }
        try:
            self._bind_init(audit)
            self._create_output()
            self.record['state'] = 'WAITING_FIXED_ENDPOINT'
        except BaseException as error:
            self._failure('initial_binding', error)

    def _take(self, name, fd):
        if name in self.fds:
            error = RuntimeError('duplicate owned diagnostic FD name')
            try:
                os.close(fd)
            except BaseException as close_error:
                self.close_failed = True
                error.add_note('new duplicate FD close failed: ' + repr(close_error)[:256])
            raise error
        self.fds[name] = fd
        return fd

    def _close(self, name):
        fd = self.fds.pop(name, None)
        if fd is not None:
            try:
                os.close(fd)            # Never retry close on an uncertain FD.
            except BaseException:
                self.close_failed = True
                raise

    def _failure(self, stage, error):
        row = {'stage': stage, 'error': repr(error)[:512],
               'errno': error.errno if isinstance(error, OSError) else None,
               'notes': [str(x)[:256] for x in getattr(error, '__notes__', ())][:4]}
        if getattr(error, 'close_failure', False):
            self.close_failed = True
        if self.record['first_error'] is None:
            self.record['first_error'] = row
        elif len(self.record['secondary_errors']) < 8:
            self.record['secondary_errors'].append(row)
        self.record['state'] = 'FAILED'

    def _bind_init(self, audit):
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
             'private crash capture requires the unchanged root actor')
        nonce = audit.get('nonce')
        need(isinstance(nonce, str) and len(nonce) == 64 and nonce != '0' * 64 and
             set(nonce) <= set('0123456789abcdef'), 'generation nonce malformed')
        hello = [r['detail']['init'] for r in audit['records'] if r['detail']['event'] == 'init_hello']
        domains = [r['detail']['domain'] for r in audit['records'] if r['detail']['event'] == 'prepared']
        need(len(hello) == len(domains) == 1, 'single actual HELLO and prepared domain required')
        snapshot = self.init.snapshot()
        for field in ('process', 'namespaces', 'executable', 'executable_sha256'):
            need(snapshot[field] == hello[0][field], 'held init does not match current HELLO ' + field)
        need(snapshot['identity']['uids'] == snapshot['identity']['gids'] == [0] * 4,
             'actual init is not unchanged initial-userns root')
        current_user = self._take('actor_userns', os.open('/proc/self/ns/user', os.O_RDONLY | os.O_CLOEXEC))
        current_pid = self._take('actor_pidns', os.open('/proc/self/ns/pid', os.O_RDONLY | os.O_CLOEXEC))
        need(identity(current_user) == snapshot['namespaces'][4] and
             identity(current_pid) != snapshot['namespaces'][0],
             'initial user namespace or private init PID namespace differs')
        root = self._take('root', os.open('root', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                                         dir_fd=self.init.proc))
        root_meta = metadata(root)
        need(identity(root) == hello[0]['root'], 'held init root differs from exact HELLO root')
        need(root_meta['type'] == stat.S_IFDIR and root_meta['inode'] == 1 and
             root_meta['uid'] == root_meta['gid'] == 0 and root_meta['mode'] == 0o755 and
             filesystem_type(root) == ROOT_TMPFS, 'actual held init root is not private synthetic tmpfs')
        domain_path = self.plan['spec']['pressure_relay']['cgroup_parent'] + '/g-' + nonce + '/android'
        need(domain_path.startswith('/sys/fs/cgroup/'), 'generation cgroup root is noncanonical')
        domain = self._take('domain', self.owned.directory(domain_path))
        self.owned.require_cgroup2(domain)
        need(identity(domain) == domains[0], 'held generation domain differs from actual audit')
        self.domain_relative = domain_path[len('/sys/fs/cgroup'):]
        self.init.live()
        self.record.update(init_snapshot=snapshot, init_root=root_meta,
                           actor_user_namespace=identity(current_user),
                           actor_pid_namespace=identity(current_pid),
                           generation_domain={'path': domain_path, **identity(domain)},
                           initial_user_namespace_root_verified=True)

    def _create_output(self):
        fd = self._take('output', os.open(OUTPUT, os.O_RDWR | os.O_CREAT | os.O_EXCL |
            os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=self.evidence))
        meta = metadata(fd)
        need(meta['type'] == stat.S_IFREG and meta['uid'] == meta['gid'] == 0 and
             meta['mode'] == 0o600 and meta['nlink'] == 1 and meta['bytes'] == 0,
             'new private packet file metadata differs')
        self.output_id = identity(fd)
        self._write(MAGIC + self.record['generation_nonce'].encode('ascii') + b'\n')

    def _write(self, raw):
        need(self.file_bytes + len(raw) <= CAPACITY, 'private packet capacity would be exceeded')
        view = memoryview(raw)
        while view:
            count = os.write(self.fds['output'], view)
            need(count > 0, 'zero private packet file write')
            self.file_hash.update(view[:count])
            self.file_bytes += count
            view = view[count:]

    def _descendant(self, parent, parts, name, executable=False):
        current = self._take(name + '_walk', os.dup(parent))
        primary = None
        try:
            for index, part in enumerate(parts):
                last_file = executable and index == len(parts) - 1
                child = os.open(part, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW |
                                (0 if last_file else os.O_DIRECTORY), dir_fd=current)
                self._take(name + '_child', child)
                self._close(name + '_walk')
                self.fds[name + '_walk'] = self.fds.pop(name + '_child')
                current = child
            result = self.fds.pop(name + '_walk')
            return self._take(name, result)
        except BaseException as error:
            primary = error
            raise
        finally:
            close_error = None
            for suffix in ('_child', '_walk'):
                try:
                    self._close(name + suffix)
                except BaseException as error:
                    if primary is not None:
                        primary.add_note('owned walk cleanup failed: ' + repr(error)[:256])
                    elif close_error is None:
                        close_error = error
                    else:
                        close_error.add_note('secondary owned walk close: ' + repr(error)[:256])
            if primary is None and close_error is not None:
                raise close_error

    def _named_path(self, parent, parts, expected, executable=False):
        # This temporary held walk is closed on every path; it creates no node.
        fd = self._descendant(parent, parts, 'named_recheck', executable)
        primary = None
        try:
            need(identity(fd) == expected, 'generation named path changed')
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                self._close('named_recheck')
            except BaseException as error:
                if primary is None:
                    raise
                primary.add_note('named recheck close failed: ' + repr(error)[:256])

    def _endpoint_unchanged(self):
        self.init.live()
        fields = dict(line.split(':', 1) for line in self.owned.bounded(self.init.proc, 'status').decode().splitlines() if ':' in line)
        need([int(x) for x in fields['Uid'].split()] == [int(x) for x in fields['Gid'].split()] == [0] * 4,
             'actual init credentials changed before diagnostic request')
        for name, index in (('pid', 0), ('user', 4)):
            current_ns = os.stat('ns/' + name, dir_fd=self.init.proc)
            need({'device': current_ns.st_dev, 'inode': current_ns.st_ino} ==
                 self.record['init_snapshot']['namespaces'][index],
                 'actual init namespace changed before diagnostic request')
        need(identity(self.fds['root']) ==
             {key: self.record['init_root'][key] for key in ('device', 'inode')},
             'held init root changed')
        current = os.stat('root', dir_fd=self.init.proc)
        need({'device': current.st_dev, 'inode': current.st_ino} == identity(self.fds['root']),
             'current init root differs from held generation')
        self._named_path(self.fds['root'], ('dev', 'socket'), identity(self.fds['socket_dir']))
        self._named_path(self.fds['root'], ('system', 'bin', 'logd'), identity(self.fds['logd_elf']), True)
        need(self._named_socket() == self.record['socket_identity'] == identity(self.fds['socket_inode']),
             'logdr named socket differs from held generation socket')
        need(self.owned.stamp(os.fstat(self.fds['logd_elf'])) == self.logd_elf_stamp,
             'fixed logd ELF metadata changed')
        self.init.live()

    def _peer_live(self):
        pidfd, proc = self.fds['peer_pidfd'], self.fds['peer_proc']
        need(not self.owned.dead(pidfd) and self.owned.pidfd_pid(pidfd) == self.peer_value['pid'],
             'socket peer pidfd is no longer the same live host process')
        birth = int(self.owned.bounded(proc, 'stat').decode().rsplit(')', 1)[1].split()[19])
        need(birth == self.peer_value['birth'], 'socket peer birth differs')

    def _bind_peer_identity(self, pid):
        # The socket-associated pidfd, not a numeric PID lookup, supplies the
        # authority. Read only the fixed identity files; no cmdline or environ.
        proc = self._take('peer_proc', os.open('/proc/' + str(pid),
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW))
        first = self.owned.bounded(proc, 'stat').decode().rsplit(')', 1)[1].split()[19]
        fields = dict(line.split(':', 1) for line in self.owned.bounded(proc, 'status').decode().splitlines() if ':' in line)
        value = {'pid': int(fields['Pid']), 'birth': int(first), 'parent': int(fields['PPid']),
                 'uids': [int(x) for x in fields['Uid'].split()],
                 'gids': [int(x) for x in fields['Gid'].split()],
                 'nspid': [int(x) for x in fields['NSpid'].split()]}
        second = self.owned.bounded(proc, 'stat').decode().rsplit(')', 1)[1].split()[19]
        need(value['pid'] == pid and first == second and
             not self.owned.dead(self.fds['peer_pidfd']) and
             self.owned.pidfd_pid(self.fds['peer_pidfd']) == pid,
             'socket-associated peer identity changed')
        self.peer_value = value
        return proc

    def _peer_snapshot(self):
        self._peer_live()
        proc = self.fds['peer_proc']
        fields = dict(line.split(':', 1) for line in self.owned.bounded(proc, 'status').decode().splitlines() if ':' in line)
        current = {'pid': int(fields['Pid']), 'parent': int(fields['PPid']),
            'uids': [int(x) for x in fields['Uid'].split()],
            'gids': [int(x) for x in fields['Gid'].split()],
            'nspid': [int(x) for x in fields['NSpid'].split()], 'birth': self.peer_value['birth']}
        need(current == {key: self.peer_value[key] for key in current},
             'socket peer credentials or parent changed')
        namespaces = {}
        for name in ('pid', 'user'):
            held = identity(self.fds['peer_ns_' + name])
            now = os.stat('ns/' + name, dir_fd=proc)
            need(held == {'device': now.st_dev, 'inode': now.st_ino}, 'socket peer namespace changed')
            namespaces[name] = held
        exe = os.stat('exe', dir_fd=proc)
        need(identity(self.fds['peer_exe']) == {'device': exe.st_dev, 'inode': exe.st_ino} and
             self.owned.stamp(os.fstat(self.fds['peer_exe'])) == self.peer_exe_stamp,
             'socket peer executable changed')
        root = os.stat('root', dir_fd=proc)
        need(identity(self.fds['peer_root']) == {'device': root.st_dev, 'inode': root.st_ino},
             'socket peer root changed')
        cgroup = self.owned.bounded(proc, 'cgroup', 4096).decode('ascii').splitlines()
        self._peer_live()
        return {'process': {'pid': current['pid'], 'birth': current['birth'],
                           'pidfd': identity(self.fds['peer_pidfd']), 'proc_dir': identity(proc)},
                'identity': current, 'namespaces': namespaces, 'executable': identity(self.fds['peer_exe']),
                'executable_sha256': self.peer_exe_sha, 'root': identity(self.fds['peer_root']),
                'cgroup': cgroup}

    def _named_socket(self):
        st = os.stat('logdr', dir_fd=self.fds['socket_dir'], follow_symlinks=False)
        need(stat.S_ISSOCK(st.st_mode) and st.st_uid == st.st_gid == LOGD_UID and
             st.st_nlink == 1 and stat.S_IMODE(st.st_mode) == 0o666,
             'fixed logdr socket type/owner/mode differs')
        return {'device': st.st_dev, 'inode': st.st_ino}

    def _prepare_endpoint(self):
        self.init.live()
        if 'socket_dir' not in self.fds:
            try:
                parent = self._descendant(self.fds['root'], ('dev', 'socket'), 'socket_dir')
            except FileNotFoundError:
                return False
            meta = metadata(parent)
            need(meta['type'] == stat.S_IFDIR and meta['uid'] == meta['gid'] == 0 and
                 not meta['mode'] & 0o022, 'generation socket directory unsafe')
            self.record['socket_directory'] = meta
        try:
            socket_id = self._named_socket()
        except FileNotFoundError:
            return False
        path_fd = self._take('socket_inode', os.open('logdr', os.O_PATH | os.O_CLOEXEC |
                            os.O_NOFOLLOW, dir_fd=self.fds['socket_dir']))
        need(identity(path_fd) == socket_id and metadata(path_fd)['type'] == stat.S_IFSOCK,
             'held logdr socket differs from its name')
        executable = self._descendant(self.fds['root'], ('system', 'bin', 'logd'), 'logd_elf', True)
        value = os.fstat(executable)
        observed = require_logd_stat(value, self.record)
        observed['first_four_bytes_hex'] = os.pread(executable, 4, 0).hex()
        need(observed['first_four_bytes_hex'] == '7f454c46',
             'fixed generation logd ELF magic differs')
        observed['read_only_view'] = bool(os.fstatvfs(executable).f_flag & os.ST_RDONLY)
        need(observed['read_only_view'], 'generation logd ELF is not on readonly view')
        digest, before = self.owned.digest_fd(executable, LOGD_ELF_BYTES)
        require_logd_digest(digest, self.record)
        self.logd_elf_stamp = self.owned.stamp(before)
        need(self.logd_elf_stamp == self.owned.stamp(value) ==
             self.owned.stamp(os.fstat(executable)),
             'fixed generation logd ELF changed during qualification')
        self.record.update(socket_identity=socket_id,
            fixed_logd_elf={'guest_path': '/system/bin/logd', **metadata(executable),
                           'sha256': digest, 'external_individual_ELF_pin_previously_observed': True,
                           'image_observation_sha256': LOGD_IMAGE_OBSERVATION_SHA256,
                           'prior_image_complete_mode_observed': False,
                           'live_special_permission_bits': observed['special_permission_bits']})
        need(self._named_socket() == socket_id, 'logdr changed before connection')
        self.init.live()
        return True

    def _connect_and_qualify(self):
        need(self.record['connection_attempts'] == 0, 'a second logdr connection is forbidden')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC |
                                  socket.SOCK_NONBLOCK)
        path = '/proc/self/fd/' + str(self.fds['socket_dir']) + '/logdr'
        self.record['connection_attempts'] = 1
        try:
            self.sock.connect(path)
        except BlockingIOError as error:
            need(error.errno == errno.EINPROGRESS, 'logdr connect not immediately admissible')
            poller = select.poll(); poller.register(self.sock, select.POLLOUT)
            wait = min(CONNECT_SECONDS, self.deadline - time.monotonic())
            need(wait > 0 and poller.poll(int(wait * 1000)), 'single logdr connect deadline')
            code = self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if code:
                raise OSError(code, os.strerror(code), 'single logdr connect')
        self.init.live()
        self._endpoint_unchanged()
        credentials = struct.unpack('3i', self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        pid, uid, gid = credentials
        need(pid > 0 and pid not in (os.getpid(), self.init.value['pid']) and uid == gid == LOGD_UID,
             'actual logdr peer credentials differ')
        peer_pidfd = self._take('peer_pidfd', self.sock.getsockopt(socket.SOL_SOCKET, SO_PEERPIDFD))
        need(peer_pidfd >= 0 and not os.get_inheritable(peer_pidfd) and
             self.owned.pidfd_pid(peer_pidfd) == pid and not self.owned.dead(peer_pidfd),
             'socket-associated peer pidfd is not the exact live CLOEXEC peer')
        proc = self._bind_peer_identity(pid)
        exe = self._take('peer_exe', os.open('exe', os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
        need(identity(exe) == identity(self.fds['logd_elf']), 'socket peer ELF inode differs before hash')
        self.peer_exe_sha, exe_stat = self.owned.digest_fd(exe, self.record['fixed_logd_elf']['bytes'])
        self.peer_exe_stamp = self.owned.stamp(exe_stat)
        for name in ('pid', 'user'):
            self._take('peer_ns_' + name, os.open('ns/' + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
        root = self._take('peer_root', os.open('root', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=proc))
        peer = self._peer_snapshot()
        init = self.init.snapshot()
        need(peer['identity']['parent'] == init['process']['pid'] and
             peer['identity']['uids'] == peer['identity']['gids'] == [LOGD_UID] * 4,
             'logdr peer is not an actual init-owned logd credential')
        for name, index in (('pid', 0), ('user', 4)):
            need(peer['namespaces'][name] == init['namespaces'][index],
                 'logdr peer PID/user namespace differs from held init')
        need(peer['executable'] == identity(self.fds['logd_elf']) and
             peer['executable_sha256'] == self.record['fixed_logd_elf']['sha256'],
             'actual logdr peer executable differs from fixed generation logd')
        need(identity(root) == identity(self.fds['root']), 'logdr peer root is outside owned generation')
        membership = peer['cgroup']
        need(len(membership) == 1 and membership[0].startswith('0::'), 'logdr peer cgroup schema differs')
        relative = membership[0][3:]
        need(relative == self.domain_relative or relative.startswith(self.domain_relative + '/'),
             'logdr peer escaped exact generation cgroup')
        suffix = relative[len(self.domain_relative):].lstrip('/')
        parts = suffix.split('/') if suffix else ()
        need(all(part and part not in ('.', '..') for part in parts), 'logdr peer cgroup suffix noncanonical')
        actual_domain = self._descendant(self.fds['domain'], parts, 'peer_cgroup')
        self.owned.require_cgroup2(actual_domain)
        need(membership == self.owned.bounded(proc, 'cgroup', 4096).decode('ascii').splitlines(),
             'logdr peer cgroup changed during qualification')
        need(self.owned.stamp(os.fstat(self.fds['logd_elf'])) == self.logd_elf_stamp and
             identity(self.fds['domain']) == {k: self.record['generation_domain'][k] for k in ('device', 'inode')},
             'logd source or generation domain changed')
        need(self._peer_snapshot() == peer, 'socket-associated peer changed before request')
        self._endpoint_unchanged()
        self.record.update(peer_credentials={'pid': pid, 'uid': uid, 'gid': gid},
                           peer_snapshot=peer, peer_root=identity(root),
                           peer_cgroup={'membership': relative, **identity(actual_domain)},
                           source_qualified_before_request=True)
        need(time.monotonic() < self.deadline, 'original observation window ended before read request')
        self.record['read_request_attempts'] = 1
        sent = self.sock.send(COMMAND, socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL)
        need(sent == len(COMMAND), 'single crash-buffer request was not sent completely')
        self.record['read_request_completed'] = True
        self.record['request_sha256'] = hashlib.sha256(COMMAND).hexdigest()
        self.record['state'] = 'READING_CRASH_BUFFER4'

    def poll(self):
        if self.finished or self.record['first_error'] is not None or self.record['eof_observed']:
            return
        try:
            need(time.monotonic() < self.deadline, 'original startup observation deadline exhausted')
            if self.sock is None:
                if not self._prepare_endpoint():
                    return
                self._connect_and_qualify()
            self._drain()
        except BaseException as error:
            self._failure('bounded_observation', error)

    def _drain(self):
        for _ in range(PER_POLL_RECORDS):
            try:
                packet = receive_packet(self.sock)
            except BlockingIOError:
                return
            if not packet:
                self.record['eof_observed'] = True
                self.record['state'] = 'PEER_STREAM_ENDED'
                return
            framed = struct.pack('<I', len(packet)) + packet
            if self.record['received_packets'] >= RECORD_LIMIT:
                self.record['record_bound_reached'] = True
                raise RuntimeError('bounded crash record prefix reached its record limit')
            if self.file_bytes + len(framed) > CAPACITY:
                self.record['capacity_reached'] = True
                raise RuntimeError('bounded crash record prefix reached its byte capacity')
            self._write(framed)
            self.record['received_packets'] += 1
            self.record['packet_bytes'] += len(packet)
            try:
                header = packet_header(packet)
            except BaseException:
                # Retain one complete bounded kernel packet as private evidence
                # even when this reference parser cannot qualify it. No retry.
                self.record['protocol_rejected_packet'] = {
                    'bytes': len(packet), 'sha256': hashlib.sha256(packet).hexdigest(),
                    'raw_packet_retained_in_private_file': True}
                raise
            self.record['records'] += 1
            self.record['public_tag_counts'][header['public_tag'] or 'other'] += 1
            if self.record['first_header'] is None:
                self.record['first_header'] = header
            self.record['last_header'] = header
            self.record['protocol_observed'] = True

    def finish(self, reason):
        if self.finished:
            return self.record
        self.finished = True
        self.record['finish_reason'] = reason
        # No wait for new data, reconnect or delayed Stop is permitted here.
        if self.sock is not None and self.record['first_error'] is None and not self.record['eof_observed']:
            try:
                self._drain()
            except BaseException as error:
                self._failure('final_nonblocking_drain', error)
        if 'peer_pidfd' in self.fds and self.record['source_qualified_before_request']:
            try:
                self.record['peer_dead_at_finish'] = self.owned.dead(self.fds['peer_pidfd'])
                if not self.record['peer_dead_at_finish']:
                    final = self._peer_snapshot()
                    need(final == self.record['peer_snapshot'], 'held logd changed before close')
                    self.record['live_peer_identity_rechecked'] = True
                else:
                    self.record['live_peer_identity_rechecked'] = False
            except BaseException as error:
                self._failure('peer_final_observation', error)
        if self.record['source_qualified_before_request']:
            try:
                self.record['init_dead_at_finish'] = self.owned.dead(self.init.pidfd)
                if not self.record['init_dead_at_finish']:
                    self._endpoint_unchanged()
                    self.record['live_init_endpoint_rechecked'] = True
                else:
                    self.record['live_init_endpoint_rechecked'] = False
            except BaseException as error:
                self._failure('init_final_observation', error)
        if self.sock is not None:
            sock, self.sock = self.sock, None
            try:
                sock.close()
            except BaseException as error:
                self.close_failed = True
                self._failure('socket_close', error)
        if 'output' in self.fds:
            try:
                fd = self.fds['output']; value = os.fstat(fd)
                need(identity(fd) == self.output_id and value.st_size == self.file_bytes and value.st_nlink == 1,
                     'private output changed before sealing')
                os.fchmod(fd, 0o400); os.fsync(fd)
                digest = hashlib.sha256(); offset = 0
                while offset < self.file_bytes:
                    data = os.pread(fd, min(65536, self.file_bytes - offset), offset)
                    need(data, 'private output truncated during final full hash')
                    digest.update(data); offset += len(data)
                need(os.pread(fd, 1, offset) == b'' and digest.hexdigest() == self.file_hash.hexdigest(),
                     'private output full byte hash differs')
                named = os.stat(OUTPUT, dir_fd=self.evidence, follow_symlinks=False)
                need((named.st_dev, named.st_ino, named.st_size, stat.S_IMODE(named.st_mode)) ==
                     (self.output_id['device'], self.output_id['inode'], self.file_bytes, 0o400),
                     'private output final named identity differs')
                os.fsync(self.evidence)
                self.record['packet_file'] = {'relative': 'evidence/' + OUTPUT,
                    'bytes': self.file_bytes, 'sha256': digest.hexdigest(), **metadata(fd),
                    'complete_packets_only': self.record['first_error'] is None}
            except BaseException as error:
                self._failure('packet_file_final', error)
        closes = []
        for name in list(self.fds):
            try:
                self._close(name)
            except BaseException as error:
                closes.append(name)
                self._failure('close_' + name, error)
        self.record['held_fds_closed'] = not self.close_failed and not closes and not self.fds and self.sock is None
        if self.record['first_error'] is None:
            self.record['state'] = ('BOUNDED_PREFIX_CLOSED' if self.record['read_request_completed']
                                    else 'NOT_READY_BEFORE_ORIGINAL_STOP')
        self.record['finished_monotonic_ns'] = time.monotonic_ns()
        return self.record
