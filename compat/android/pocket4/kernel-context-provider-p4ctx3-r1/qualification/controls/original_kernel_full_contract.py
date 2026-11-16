"""Bounded independent source custody and complete uninstalled Kbuild validation."""
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat

FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
          'st_size', 'st_mtime_ns', 'st_ctime_ns')
FICLONE = 0x40049409
MAX_NODES = 600000
MAX_FILE = 256 * 1024**2
MAX_SOURCE_BYTES = 24 * 1024**3
FORBIDDEN_SOURCE = {'.config', 'certs/signing_key.pem', 'certs/signing_key.key'}
TARGETS = (
    'security/p4_lsm_context.o',
    'security/security.o',
    'fs/proc/base.o',
    'fs/proc/root.o',
    'fs/proc/inode.o',
    'drivers/android/binder.o',
    'drivers/android/binderfs.o',
    'net/socket.o',
    'net/core/net_namespace.o',
    'net/kcm/kcmsock.o',
    'net/sctp/socket.o',
    'fs/ocfs2/cluster/tcp.o',
    'kernel/p4_guest_mntns.o',
    'fs/namespace.o',
    'kernel/nsproxy.o',
    'security/apparmor/lsm.o',
)


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def identity(s):
    return [getattr(s, x) for x in FIELDS]


def directory_id(s):
    return identity(s)[:5]


def path_parts(value):
    p = Path(value)
    need(not p.is_absolute() and p.parts and '.' not in p.parts
         and '..' not in p.parts and p.as_posix() == value,
         'exact relative source member required')
    return p.parts


def hash_fd(fd, limit=MAX_FILE, checkpoint=lambda: None):
    s = os.fstat(fd)
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and 0 <= s.st_size <= limit,
         'bounded single-link original source required')
    h = hashlib.sha256(); count = 0
    while count < s.st_size:
        b = os.pread(fd, min(1024**2, s.st_size - count), count)
        need(bool(b), 'source file truncated')
        h.update(b); count += len(b)
        if count % (8 * 1024**2) == 0:
            checkpoint()
    need(os.pread(fd, 1, count) == b'' and identity(os.fstat(fd)) == identity(s),
         'source file changed while reading')
    return {'bytes': count, 'sha256': h.hexdigest(), 'identity': identity(s)}


def snapshot(root, checkpoint=lambda: None):
    """Never follow source symlinks or leave the selected source root."""
    root = Path(root)
    rfd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    root_id = identity(os.fstat(rfd)); entries = []; total = 0
    need(root.resolve(strict=True) == root and stat.S_ISDIR(root.lstat().st_mode),
         'source root must not be an alias')
    def walk(fd, prefix):
        nonlocal total
        before = identity(os.fstat(fd))
        names = sorted(os.listdir(fd))
        for name in names:
            need(name not in ('.', '..') and '/' not in name and '\0' not in name,
                 'invalid source directory entry')
            relative = '/'.join((*prefix, name))
            need(relative not in FORBIDDEN_SOURCE and name != '.git',
                 'generated configuration, signing key or repository metadata in source')
            s = os.stat(name, dir_fd=fd, follow_symlinks=False)
            row = {'path': relative, 'identity': identity(s), 'mode': stat.S_IMODE(s.st_mode)}
            need(s.st_uid == os.geteuid() and (stat.S_ISLNK(s.st_mode) or not s.st_mode & 0o7022),
                 'source member ownership or mode differs')
            if stat.S_ISDIR(s.st_mode):
                row['kind'] = 'directory'; entries.append(row)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                try:
                    need(identity(os.fstat(child)) == identity(s), 'source directory replaced')
                    walk(child, (*prefix, name))
                finally:
                    os.close(child)
            elif stat.S_ISREG(s.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
                try:
                    row.update(hash_fd(child, checkpoint=checkpoint)); row['kind'] = 'file'
                    need(row['identity'] == identity(s) == identity(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                         'named source input replaced')
                finally:
                    os.close(child)
                total += row['bytes']; entries.append(row)
                need(total <= MAX_SOURCE_BYTES, 'source-only copy size bound exceeded')
            elif stat.S_ISLNK(s.st_mode):
                target = os.readlink(name, dir_fd=fd)
                need(not Path(target).is_absolute() and (root / relative).resolve(strict=True).is_relative_to(root),
                     'source symlink escapes the exact source root')
                need(identity(s) == identity(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                     'source symlink changed')
                row.update(kind='symlink', target=target); entries.append(row)
            else:
                raise RuntimeError('non-source special file rejected: ' + relative)
            need(len(entries) <= MAX_NODES, 'source node bound exceeded')
            if len(entries) % 128 == 0:
                checkpoint()
        need(names == sorted(os.listdir(fd)) and identity(os.fstat(fd)) == before,
             'source directory changed during snapshot')
    try:
        walk(rfd, ())
        need(root_id == identity(os.fstat(rfd)) == identity(root.lstat()), 'source root replaced')
    finally:
        os.close(rfd)
    return {'root': str(root), 'root_identity': root_id, 'entries': entries,
            'files_apparent_bytes': total,
            'independent_copy_4k_upper_bytes': sum(((x.get('bytes', 0) + 4095)//4096)*4096 + 4096 for x in entries)}


def copy_source(root, destination, inventory, checkpoint=lambda: None):
    """Fresh independent inodes; reflink when supported, buffered copy otherwise."""
    root, destination = Path(root), Path(destination)
    need(inventory['root'] == str(root) and identity(root.lstat()) == inventory['root_identity'],
         'source snapshot root changed')
    destination.mkdir(mode=0o700)
    methods = {'reflink': 0, 'buffered': 0, 'symlink': 0}
    for index, row in enumerate(inventory['entries']):
        path_parts(row['path']); old = root / row['path']; new = destination / row['path']
        need(old.parent.resolve(strict=True) == old.parent and new.parent.resolve(strict=True) == new.parent,
             'copy source or destination ancestor became a symlink')
        need(identity(old.lstat()) == row['identity'], 'source changed before independent copy')
        if row['kind'] == 'directory':
            new.mkdir(mode=row['mode']); os.chmod(new, row['mode'])
        elif row['kind'] == 'symlink':
            need(os.readlink(old) == row['target'], 'source link target changed')
            os.symlink(row['target'], new); methods['symlink'] += 1
        else:
            src = os.open(old, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            dst = os.open(new, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, row['mode'])
            try:
                need(identity(os.fstat(src)) == row['identity'], 'held source copy input changed')
                try:
                    fcntl.ioctl(dst, FICLONE, src); methods['reflink'] += 1
                except OSError as error:
                    if error.errno not in (errno.EOPNOTSUPP, errno.EXDEV, errno.ENOTTY, errno.EINVAL):
                        raise
                    offset = 0
                    while offset < row['bytes']:
                        block = os.pread(src, min(1024**2, row['bytes'] - offset), offset)
                        need(bool(block), 'source copy truncated')
                        view = memoryview(block)
                        while view:
                            n = os.write(dst, view); need(n > 0, 'short independent copy'); view = view[n:]
                        offset += len(block)
                        if offset % (8 * 1024**2) == 0:
                            checkpoint()
                    methods['buffered'] += 1
                os.fchmod(dst, row['mode'])
                actual = hash_fd(dst, checkpoint=checkpoint)
                need(all(actual[k] == row[k] for k in ('bytes', 'sha256'))
                     and identity(os.fstat(src)) == row['identity'] == identity(old.lstat())
                     and (os.fstat(src).st_dev, os.fstat(src).st_ino) != (os.fstat(dst).st_dev, os.fstat(dst).st_ino),
                     'independent copy bytes, source identity or inode separation differs')
                os.fsync(dst)
            finally:
                os.close(dst); os.close(src)
        if index % 128 == 0:
            checkpoint()
    return methods


def semantic_members(inventory):
    return {x['path']: {k: x[k] for k in ('kind', 'mode', 'bytes', 'sha256', 'target') if k in x}
            for x in inventory['entries']}


def parse_config(raw):
    result = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
        elif re.fullmatch(r'# CONFIG_[A-Za-z0-9_]+ is not set', line):
            key, value = line.split()[1], 'n'
        else:
            continue
        need(key not in result, 'duplicate Kconfig symbol')
        result[key] = value
    need(bool(result), 'empty Kconfig symbol map')
    return result


RELEASE = '7.0.14-p4ctx1'
LOCALVERSION = '-p4ctx1'
FULL_TARGETS = ('bzImage', 'modules')
MAX_ARTIFACT = 4 * 1024**3


def verify_config(before, after):
    old, new = parse_config(before), parse_config(after)
    need(old.get('CONFIG_LOCALVERSION') == '"-p4guest1"'
         and new.get('CONFIG_LOCALVERSION') == '"-p4ctx1"'
         and 'CONFIG_P4_LSM_CONTEXT' not in old
         and new.get('CONFIG_P4_LSM_CONTEXT') == 'y'
         and old.get('CONFIG_P4_GUEST_MNTNS') == new.get('CONFIG_P4_GUEST_MNTNS') == 'y'
         and new.get('CONFIG_XEN_PVCALLS_BACKEND') == 'n',
         'exact context release, retained grant and disabled Xen configuration required')
    expected = dict(old)
    expected.update(CONFIG_LOCALVERSION='"-p4ctx1"', CONFIG_P4_LSM_CONTEXT='y')
    need(new == expected, 'configuration changed beyond the exact two context symbols')
    need(new.get('CONFIG_MODULE_SIG_KEY') == '"certs/signing_key.pem"'
         and new.get('CONFIG_MODULE_SIG') == new.get('CONFIG_MODULE_SIG_ALL') == 'y'
         and new.get('CONFIG_SYSTEM_TRUSTED_KEYS') == '"debian/canonical-certs.pem"'
         and new.get('CONFIG_SYSTEM_REVOCATION_KEYS') == '"debian/canonical-revoked-certs.pem"'
         and new.get('CONFIG_LSM') == '"landlock,lockdown,yama,integrity,apparmor,bpf"',
         'original signing/public certificate/LSM configuration was not preserved')
    return {'CONFIG_P4_LSM_CONTEXT': {'before': None, 'after': 'y'},
            'CONFIG_LOCALVERSION': {'before': '"-p4guest1"', 'after': '"-p4ctx1"'}}


def normal_commands(source, output, private_arguments):
    allowed = ('RUSTC=', 'HOSTRUSTC=', 'BINDGEN=', 'CLANG=', 'PAHOLE=', 'HOSTCFLAGS=', 'HOSTLDFLAGS=')
    need(len(private_arguments) == len(allowed) and all(value.startswith(prefix)
         for value, prefix in zip(private_arguments, allowed)), 'exact normal toolchain argument roles required')
    base = ['/usr/bin/make', '--no-print-directory', '-C', str(source),
            'O=' + str(output), '-j8', *private_arguments]
    return [base + ['olddefconfig'], base + ['prepare', 'scripts'],
            base + ['-s', 'kernelrelease'], base + list(FULL_TARGETS)]


def stable_artifact(path, *, maximum=MAX_ARTIFACT, checkpoint=lambda: None,
                    elf_type=None, release=None, bzimage=False, unsigned_module=False):
    import struct
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        need(st.st_uid == os.geteuid() and not st.st_mode & 0o7022,
             'artifact ownership or writable permission differs')
        ref = hash_fd(fd, maximum, checkpoint)
        if elf_type is not None:
            h = os.pread(fd, 64, 0)
            need(len(h) == 64 and h[:7] == b'\x7fELF\x02\x01\x01'
                 and struct.unpack_from('<HH', h, 16) == (elf_type, 62),
                 'complete little-endian x86_64 ELF artifact required')
            if release is not None:
                section_offset = struct.unpack_from('<Q', h, 40)[0]
                entry_size, count, strings = struct.unpack_from('<HHH', h, 58)
                need(entry_size == 64 and 0 < count < 65535 and 0 < strings < count
                     and section_offset >= 64 and section_offset + count * 64 <= st.st_size,
                     'bounded ordinary ELF section table required')
                table = os.pread(fd, count * 64, section_offset)
                need(len(table) == count * 64, 'truncated ELF section table')
                def section(index):
                    name, kind = struct.unpack_from('<II', table, index * 64)
                    offset, size = struct.unpack_from('<QQ', table, index * 64 + 24)
                    need(offset <= st.st_size and ((kind == 8 and size <= MAX_ARTIFACT)
                         or (kind != 8 and size <= st.st_size - offset)),
                         'ELF section outside its held file')
                    return name, kind, offset, size
                _, kind, off, size = section(strings)
                need(kind == 3 and size <= 4 * 1024**2, 'bounded ELF string table required')
                names = os.pread(fd, size, off); found = []
                for i in range(count):
                    name, kind, off, size = section(i)
                    need(name < len(names), 'ELF section name outside string table')
                    end = names.find(b'\0', name)
                    need(end >= name, 'unterminated ELF section name')
                    if names[name:end] == b'.modinfo':
                        need(kind == 1 and size <= 4 * 1024**2, 'bounded module information required')
                        found.append(os.pread(fd, size, off))
                need(len(found) == 1, 'exactly one module information section required')
                values = [x.removeprefix(b'vermagic=') for x in found[0].split(b'\0')
                          if x.startswith(b'vermagic=')]
                need(len(values) == 1 and values[0].startswith(release.encode() + b' '),
                     'module vermagic does not use the new exact kernel release')
                ref['vermagic'] = values[0].decode('ascii')
        if bzimage:
            h = os.pread(fd, 0x270, 0)
            need(len(h) == 0x270 and h[0x1fe:0x200] == b'\x55\xaa'
                 and h[0x202:0x206] == b'HdrS', 'normal x86 bzImage boot header required')
            offset = 0x200 + struct.unpack_from('<H', h, 0x20e)[0]
            need(0x200 < offset < st.st_size, 'bzImage kernel version pointer outside image')
            version = os.pread(fd, min(512, st.st_size - offset), offset).split(b'\0', 1)[0]
            need(version.startswith(RELEASE.encode() + b' '), 'bzImage release differs')
            ref['boot_protocol_version_string'] = version.decode('ascii')
        if unsigned_module:
            marker = b'~Module signature appended~\n'
            need(os.pread(fd, len(marker), max(0, st.st_size - len(marker))) != marker,
                 'unexpected module signing during compile-only build')
        need(ref['identity'] == identity(os.fstat(fd)) == identity(path.lstat()),
             'artifact changed during complete verification')
        return {'path': str(path), **ref}
    finally:
        os.close(fd)


def complete_modules(output, source, checkpoint=lambda: None):
    output = Path(output)
    fd = os.open(output / 'modules.order', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        order_ref = hash_fd(fd, 8 * 1024**2, checkpoint)
        raw = os.pread(fd, order_ref['bytes'], 0)
        need(identity(os.fstat(fd)) == order_ref['identity'] == identity((output / 'modules.order').lstat()),
             'module order changed')
    finally:
        os.close(fd)
    need(raw.endswith(b'\n'), 'complete newline-terminated module order required')
    objects = raw.decode('utf-8').splitlines()
    need(0 < len(objects) <= 32768 and len(objects) == len(set(objects)), 'module order count or duplicates invalid')
    for value in objects:
        path_parts(value)
        need(value.endswith('.o'), 'normal in-tree module object path required')
    expected = {value[:-2] + '.ko' for value in objects}
    actual = set()
    # Only enumerate the new output. The generated private key is never opened.
    for directory, directories, files in os.walk(output, followlinks=False):
        for name in directories:
            p = Path(directory) / name
            need(not p.is_symlink() or (p == output / 'source' and p.resolve(strict=True) == Path(source)),
                 'unexpected directory alias in new build output')
        for name in files:
            if name.endswith('.ko'):
                actual.add((Path(directory) / name).relative_to(output).as_posix())
        checkpoint()
    need(actual == expected, 'complete built .ko path set differs from modules.order')
    modules = []
    for relative in sorted(expected):
        # Only the same-config large AMD driver gets a separate new-output bound.
        # Source bounds remain 256 MiB; no old artifact inode or body is reused.
        maximum = 1024**3 if relative == 'drivers/gpu/drm/amd/amdgpu/amdgpu.ko' else 256 * 1024**2
        modules.append(stable_artifact(output / relative, maximum=maximum,
            checkpoint=checkpoint, elf_type=1, release=RELEASE, unsigned_module=True))
        checkpoint()
    return {'kernel_release': RELEASE, 'modules_order': {'path': str(output / 'modules.order'), **order_ref},
            'module_count': len(modules), 'modules': modules, 'all_modules_unsigned': True,
            'all_modules_new_release': True, 'exact_modules_order_complete': True}

