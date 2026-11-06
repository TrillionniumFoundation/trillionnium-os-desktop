"""Owned local kernel mechanism controls; not a Rust or Android execution.

This reproduces mkdir(0755) under0077 and the held-FD fchmod operation.
Root/private-mount admission remains a production source gate and is not
replaced by this tempfile fixture. No setuid, mount, UI, or remote calls.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

OUT = Path(__file__).parent
rows = []
owned = []


def opened(path, flags):
    fd = os.open(path, flags | os.O_CLOEXEC | os.O_NOFOLLOW)
    owned.append(fd)
    return fd


def ident(fd):
    s = os.fstat(fd)
    return [s.st_dev, s.st_ino, s.st_uid, s.st_gid]


def mode(fd):
    return stat.S_IMODE(os.fstat(fd).st_mode)


def check(label, condition, details):
    if not condition:
        raise AssertionError(label)
    rows.append({'name': label, 'pass': True, 'details': details})


def main():
    original_mask = os.umask(0o077)
    first = None
    close_errors = []
    try:
        with tempfile.TemporaryDirectory(prefix='p4-owned-bootstrap-modes-', dir='/dev/shm') as folder:
            private = Path(folder)
            private_fd = opened(private, os.O_RDONLY | os.O_DIRECTORY)
            os.mkdir(private / 'droidloom', 0o755)
            os.mkdir(private / 'droidloom/lmkd-bootstrap', 0o755)
            parent = opened(private / 'droidloom', os.O_RDONLY | os.O_DIRECTORY)
            leaf = opened(private / 'droidloom/lmkd-bootstrap', os.O_RDONLY | os.O_DIRECTORY)
            identities = [ident(parent), ident(leaf)]
            check('old0755_mkdir_under0077_yields_two0700_directories',
                  mode(parent) == mode(leaf) == 0o700,
                  {'parent_mode': oct(mode(parent)), 'bootstrap_mode': oct(mode(leaf)),
                   'world_search_bits': [mode(parent) & 1, mode(leaf) & 1]})
            payload = private / 'droidloom/lmkd-bootstrap/public.bin'
            public_bytes = b'owned-public-payload-no-secrets\n'
            payload.write_bytes(public_bytes)
            payload.chmod(0o555)
            payload_before = payload.stat()
            os.fchmod(parent, 0o755)
            os.fchmod(leaf, 0o755)
            named_parent = opened(private / 'droidloom', os.O_RDONLY | os.O_DIRECTORY)
            named_leaf = opened(private / 'droidloom/lmkd-bootstrap', os.O_RDONLY | os.O_DIRECTORY)
            check('explicit_held_fchmod_restores_only_two_guest_search_modes',
                  mode(parent) == mode(leaf) == mode(named_parent) == mode(named_leaf) == 0o755
                  and identities == [ident(parent), ident(leaf)] == [ident(named_parent), ident(named_leaf)]
                  and mode(private_fd) == 0o700 and payload.read_bytes() == public_bytes
                  and all(getattr(payload.stat(), key) == getattr(payload_before, key)
                          for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')),
                  {'parent_mode': oct(mode(parent)), 'bootstrap_mode': oct(mode(leaf)),
                   'private_host_parent_mode': oct(mode(private_fd)), 'same_held_named_identities': True,
                   'payload_size': len(public_bytes), 'payload_sha256': hashlib.sha256(public_bytes).hexdigest(),
                   'payload_metadata_and_bytes_unchanged': True})
            current_mask = os.umask(0o077)
            check('held_chmod_does_not_change_process_umask', current_mask == 0o077,
                  {'actual_mask': oct(current_mask)})
            # The actual development path uses create_dir_all before entry.
            os.makedirs(private / 'preexisting-droidloom/ime', mode=0o755)
            existing = opened(private / 'preexisting-droidloom', os.O_RDONLY | os.O_DIRECTORY)
            before = ident(existing)
            check('create_dir_all_parent_has_same0077_counterexample', mode(existing) == 0o700,
                  {'actual_parent_mode': oct(mode(existing))})
            os.fchmod(existing, 0o755)
            check('held_parent_mode_fix_keeps_inode_and_host_parent_private',
                  ident(existing) == before and mode(existing) == 0o755 and mode(private_fd) == 0o700,
                  {'same_identity': True, 'actual_parent_mode': oct(mode(existing))})
            path_only = opened(private / 'droidloom/lmkd-bootstrap', os.O_PATH | os.O_DIRECTORY)
            failed_errno = None
            try:
                os.fchmod(path_only, 0o700)
            except OSError as exc:
                failed_errno = exc.errno
            check('fchmod_on_path_only_descriptor_preserves_EBADF', failed_errno == errno.EBADF
                  and mode(leaf) == 0o755, {'errno': failed_errno, 'mode_unchanged': True})
            os.symlink('droidloom', private / 'link')
            symlink_errno = None
            try:
                unexpected = opened(private / 'link', os.O_RDONLY | os.O_DIRECTORY)
            except OSError as exc:
                symlink_errno = exc.errno
            check('directory_open_NOFOLLOW_rejects_symlink', symlink_errno in (errno.ELOOP, errno.ENOTDIR),
                  {'errno': symlink_errno})
            # A create-only successor must not silently adopt an existing leaf.
            existing_errno = None
            try:
                os.mkdir(private / 'droidloom/lmkd-bootstrap', 0o755)
            except OSError as exc:
                existing_errno = exc.errno
            check('bootstrap_create_only_returns_EEXIST', existing_errno == errno.EEXIST,
                  {'errno': existing_errno})
    except Exception as exc:
        first = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        os.umask(original_mask)
        for fd in reversed(owned):
            try:
                os.close(fd)
            except OSError as exc:
                close_errors.append({'errno': exc.errno, 'message': str(exc)})
    result = {'schema': 1, 'scope': 'LOCAL_OWNED_KERNEL_MKDIR_UMASK_FCHMOD_MECHANISM',
              'ok': first is None and not close_errors, 'first_error': first,
              'close_errors': close_errors, 'held_fds_closed': not close_errors,
              'checks': rows, 'checks_passed': len(rows),
              'actual_Rust_function_executed': False, 'private_guest_mount_admission_executed': False,
              'LMKD_UID_or_DAC_OVERRIDE_tested': False, 'Android_or_device_run': False,
              'three_new_Rust_tests': 'PENDING_MATCHED_HOST_BUILD_AND_ORDINARY_RUN'}
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    (OUT / 'kernel-result.json').open('xb').write(raw)
    print(json.dumps({'ok': result['ok'], 'checks': len(rows), 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest()}))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
