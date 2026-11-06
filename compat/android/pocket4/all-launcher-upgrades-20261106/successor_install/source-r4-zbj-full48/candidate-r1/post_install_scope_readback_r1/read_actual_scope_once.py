"""Read one pinned, already produced host metadata file; no Android command."""
import fcntl
import hashlib
import json
import os
import stat

PIN = {'bytes': 59259, 'path': '/home/alex/work/pocket4-successor-native-install-20261106-zbj-s43-full48-r4-01/app-scope-after.private.json', 'sha256': '9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a'}
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size',
          'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


def need(value, code):
    if not value:
        raise RuntimeError(code)


def census():
    found = {}
    for name in os.listdir('/proc/self/fd'):
        fd = int(name)
        try:
            info = os.fstat(fd)
        except OSError:
            continue
        found[name] = {
            'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'rdev': info.st_rdev,
            'link': os.readlink('/proc/self/fd/' + name),
            'descriptor_flags': fcntl.fcntl(fd, fcntl.F_GETFD),
            'status_flags': fcntl.fcntl(fd, fcntl.F_GETFL),
        }
    return found


def main():
    need(os.getuid() == os.geteuid() == 0, 'EXISTING_HOST_ROOT_REQUIRED')
    before = census()
    owned = []
    body = bytearray()
    metadata = None
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        owned.append(parent)
        parts = PIN['path'][1:].split('/')
        for part in parts[:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            owned.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        owned.append(fd)
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and
             not info.st_mode & 0o022 and info.st_size == PIN['bytes'], 'EXACT_ROOT_REGULAR_METADATA')
        while len(body) <= PIN['bytes']:
            chunk = os.read(fd, min(65536, PIN['bytes'] + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        reopened = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        owned.append(reopened)
        need(len(body) == PIN['bytes'] and hashlib.sha256(body).hexdigest() == PIN['sha256'], 'EXACT_SCOPE_BYTES')
        need(all(getattr(info, key) == getattr(os.fstat(fd), key) == getattr(os.fstat(reopened), key)
                 for key in FIELDS), 'PATH_OR_FILE_CHANGED')
        metadata = {key: getattr(info, key) for key in FIELDS}
    finally:
        errors = []
        for fd in reversed(owned):
            try:
                os.close(fd)
            except OSError as error:
                errors.append((fd, error.errno))
        need(not errors, 'OWNED_FDS_NOT_RETIRED')
    need(census() == before, 'WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    result = {
        'schema': 'pocket4-zbj-post-install48-scope-readback-v1', 'ok': True,
        'file': PIN, 'metadata': metadata, 'raw_utf8': bytes(body).decode('utf-8', 'strict'),
        'whole_process_FD_identities_restored': True,
        'owned_FDs_acquired': len(owned), 'owned_FDs_closed': len(owned),
        'Main_commands': 0, 'namespace_entries': 0, 'UI_actions': 0,
        'permission_changes': 0, 'reconstructed': False,
    }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')), flush=True)


if __name__ == '__main__':
    main()
