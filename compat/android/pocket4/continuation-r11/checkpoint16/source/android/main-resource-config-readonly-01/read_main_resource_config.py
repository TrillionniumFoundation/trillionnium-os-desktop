#!/usr/bin/env python3
"""Read exactly two observed Main drop-ins; never change or qualify Main."""
import argparse
import base64
import hashlib
import json
import os
import stat
import time

PATHS = (
    '/etc/systemd/system.control/droidloomd.service.d/50-TasksMax.conf',
    '/etc/systemd/system/droidloomd.service.d/90-digitalis-validation-resources.conf',
)
REFERENCE = dict(
    observation='completed Main service resource diagnostic03',
    stdout_bytes=96513,
    stdout_sha256='8545c6b1e77cd2716c3a386bd0008f1fdbb350c6261b93f4d7152b5c5fb36e23',
    systemctl_stdout_bytes=586,
    systemctl_stdout_sha256='0af1787d9a5c3458d8b072d5974337e53618e37861ab87920bcc4efc5fca168e',
    observed_TasksMax='6144',
    activation_sha256='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
    activation_expected_pids_max='12288',
    relationship='both exact paths were present in the actual DropInPaths property',
)
FILE_MAX = 16384
OUTPUT_MAX = 131072
DEADLINE_SECONDS = 5.0


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_time(deadline):
    require(time.monotonic() < deadline, 'COLLECTION_DEADLINE')


def metadata(fd):
    s = os.fstat(fd)
    return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode,
                uid=s.st_uid, gid=s.st_gid, nlink=s.st_nlink, size=s.st_size,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def open_fixed(path, directory, deadline):
    """Walk every component with O_NOFOLLOW; return only the held final FD."""
    require(path.startswith('/') and '//' not in path, 'ABSOLUTE_FIXED_PATH')
    parts = path[1:].split('/')
    require(parts and all(part not in ('', '.', '..') for part in parts), 'PATH_COMPONENT')
    parent = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            check_time(deadline)
            child = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                            dir_fd=parent)
            os.close(parent)
            parent = child
        check_time(deadline)
        flags = (os.O_PATH | os.O_DIRECTORY) if directory else (os.O_RDONLY | os.O_NONBLOCK)
        return os.open(parts[-1], flags | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)


def read_bounded(fd, maximum, deadline):
    """Read to EOF, including pseudo files whose stat size is zero."""
    data = bytearray()
    while len(data) <= maximum:
        check_time(deadline)
        block = os.read(fd, min(65536, maximum + 1 - len(data)))
        if not block:
            return bytes(data)
        data.extend(block)
    raise RuntimeError('FILE_READ_BOUND')


def collect():
    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    result = dict(schema=1, collection_complete=False, error=None, secondary_errors=[],
                  reference=REFERENCE, paths=list(PATHS), files=[],
                  maximum_bytes_each=FILE_MAX, maximum_input_bytes=FILE_MAX * len(PATHS),
                  deadline_seconds=DEADLINE_SECONDS, device_file_writes=0,
                  child_processes_started=0, Android_UI_actions=0,
                  activation_read=False, service_command_called=False,
                  main_guard_called=False, runtime_authorized=False,
                  current_service_identity_reverified=False,
                  values_interpreted_as_effective_policy=False,
                  observation_scope='two fixed configuration bodies, with held and named rereads; not an atomic snapshot')
    held = []
    close_failed = False

    def remember(phase, path, error):
        failure = dict(phase=phase, path=path, type=type(error).__name__,
                       message=str(error), errno=getattr(error, 'errno', None))
        if result['error'] is None:
            result['error'] = failure
        else:
            result['secondary_errors'].append(failure)

    try:
        require(os.getuid() == os.geteuid() == 0, 'ROOT_READ_ONLY_COLLECTOR_REQUIRED')
        for path in PATHS:
            record = dict(path=path, complete=False)
            result['files'].append(record)
            try:
                fd = open_fixed(path, False, deadline)
                held.append((path, fd, record))
                before = metadata(fd)
                record['before'] = before
                require(stat.S_ISREG(before['mode']) and before['nlink'] == 1 and
                        0 <= before['size'] <= FILE_MAX, 'REGULAR_SINGLE_LINK_CONFIG_BOUND')
                raw = read_bounded(fd, FILE_MAX, deadline)
                after = metadata(fd)
                require(len(raw) == before['size'] and after == before, 'CONFIG_HELD_INPUT_CHANGED')
                raw.decode('utf-8', errors='strict')
                record.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                              encoding='base64-original-utf8-bytes',
                              original_base64=base64.b64encode(raw).decode('ascii'),
                              after_first_read=after)
            except Exception as error:
                remember('read_fixed_config', path, error)
        for path, fd, record in held:
            if 'sha256' not in record:
                continue
            named = None
            try:
                check_time(deadline)
                named = open_fixed(path, False, deadline)
                named_before = metadata(named)
                held_after = metadata(fd)
                require(named_before == held_after == record['before'], 'CONFIG_FINAL_NAMED_IDENTITY_CHANGED')
                raw = read_bounded(named, FILE_MAX, deadline)
                named_after = metadata(named)
                final_held = metadata(fd)
                actual_sha = hashlib.sha256(raw).hexdigest()
                require(len(raw) == record['bytes'] and actual_sha == record['sha256'] and
                        named_after == final_held == record['before'], 'CONFIG_FINAL_CONTENT_OR_IDENTITY_CHANGED')
                record.update(named_before=named_before, named_after=named_after,
                              held_after=final_held, named_bytes=len(raw), named_sha256=actual_sha,
                              complete=True)
            except Exception as error:
                remember('verify_fixed_config_again', path, error)
            finally:
                if named is not None:
                    try:
                        os.close(named)
                    except OSError as error:
                        close_failed = True
                        remember('close_named_config_fd', path, error)
        check_time(deadline)
    except Exception as error:
        remember('collect_fixed_configs', None, error)
    finally:
        for path, fd, record in reversed(held):
            try:
                os.close(fd)
            except OSError as error:
                close_failed = True
                remember('close_held_config_fd', path, error)
        result['owned_fds_closed'] = not close_failed
        result['collection_complete'] = (result['error'] is None and not result['secondary_errors'] and
                                         result['owned_fds_closed'] and len(result['files']) == len(PATHS) and
                                         all(record['complete'] for record in result['files']))
        result['elapsed_ms'] = int((time.monotonic() - started) * 1000)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-once', action='store_true')
    args = parser.parse_args(argv)
    if args.collect_once:
        result = collect()
    else:
        result = dict(state='PLAN_ONLY', reference=REFERENCE, paths=list(PATHS),
                      maximum_bytes_each=FILE_MAX, maximum_input_bytes=FILE_MAX * len(PATHS),
                      output_maximum_bytes=OUTPUT_MAX, deadline_seconds=DEADLINE_SECONDS,
                      no_path_arguments=True, maximum_files=2, device_file_writes=0,
                      child_processes_started=0, Android_UI_actions=0, runtime_authorized=False)
    output = (json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    require(len(output) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(output.decode('ascii'), end='', flush=True)
    return 0 if not args.collect_once or result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
