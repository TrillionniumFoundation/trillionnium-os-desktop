#!/usr/bin/env python3
"""One bounded read-only observation of the known camera's next generation."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import time

BOOT = '981ff371-cd72-4f81-9be3-a862111afdb1'
HOST = 'alex-G1628-04'
KERNEL = '7.0.0-38-generic'
ALIAS = Path('/sys/bus/usb/devices/3-4')
TARGET = '/sys/devices/pci0000:00/0000:00:08.3/0000:c7:00.0/usb3/3-4'
IDENTITY = {'idVendor': '1e08', 'idProduct': '5520', 'serial': 'JX20250923V2',
            'bcdDevice': '0923', 'busnum': '3', 'devpath': '4'}
FIELDS = ('power/control', 'power/autosuspend_delay_ms', 'power/runtime_status',
          'power/runtime_active_time', 'power/runtime_suspended_time',
          'power/runtime_usage', 'power/active_duration', 'power/connected_duration')
OUT = Path('/home/alex/work/pocket4-camera-usb-arrival-readonly01.json')


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def context():
    require(os.uname().nodename == HOST and os.uname().release == KERNEL, 'HOST_CHANGED')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'BOOT_CHANGED')
    require(os.readlink('/proc/self/ns/mnt') == 'mnt:[4026531832]', 'HOST_MOUNT_CHANGED')


def read_at(root, relative, optional=False):
    try:
        fd = os.open(relative, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=root)
        try:
            raw = os.read(fd, 4097)
            require(len(raw) <= 4096, 'UNBOUNDED_ATTRIBUTE')
            return raw.decode('ascii').strip()
        finally:
            os.close(fd)
    except FileNotFoundError:
        if optional:
            return None
        raise


def snapshot(root, birth):
    context()
    require(os.path.realpath(ALIAS) == TARGET, 'CAMERA_ABSENT_OR_TOPOLOGY_CHANGED')
    now = os.stat(TARGET, follow_symlinks=False)
    held = os.fstat(root)
    require((now.st_dev, now.st_ino) == birth == (held.st_dev, held.st_ino)
            and held.st_nlink > 0, 'CAMERA_GENERATION_CHANGED')
    require({k: read_at(root, k) for k in IDENTITY} == IDENTITY, 'CAMERA_IDENTITY_CHANGED')
    return {'at_utc': utc(), 'device_number': read_at(root, 'devnum'),
            'power': {k: read_at(root, k, optional=True) for k in FIELDS}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execute-read-only', action='store_true')
    args = p.parse_args()
    if not args.execute_read_only:
        print(json.dumps({'state': 'PLAN_ONLY', 'host_reads': False, 'sysfs_writes': 0,
                          'wait_limit_seconds': 180, 'sample_limit_seconds': 35}))
        return 0
    context()
    output_fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o640)
    os.fchown(output_fd, 0, 1000)
    result = {'schema': 'pocket4-one-generation-pm-observation-v1', 'started_utc': utc(),
              'read_only': True, 'sysfs_writes': 0, 'ui_actions': 0, 'provider_changes': 0,
              'capture_calls': 0, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'state': 'WAITING', 'samples': [], 'causality_established': False}
    root = None
    try:
        start = time.monotonic()
        while time.monotonic() - start < 180:
            context()
            if ALIAS.exists():
                break
            time.sleep(0.5)
        result['wait_seconds'] = time.monotonic() - start
        if not ALIAS.exists():
            result['state'] = 'NO_TARGET_WITHIN_BOUNDED_WINDOW'
        else:
            require(os.path.realpath(ALIAS) == TARGET, 'TARGET_TOPOLOGY_CHANGED')
            root = os.open(TARGET, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            st = os.fstat(root)
            birth = (st.st_dev, st.st_ino)
            result['device_directory_identity'] = {'dev': st.st_dev, 'ino': st.st_ino}
            sample_start = time.monotonic()
            first_number = None
            while time.monotonic() - sample_start <= 35:
                value = snapshot(root, birth)
                if first_number is None:
                    first_number = value['device_number']
                require(value['device_number'] == first_number, 'DEVICE_ADDRESS_CHANGED')
                result['samples'].append(value)
                time.sleep(0.5)
            result['state'] = 'SAME_GENERATION_OBSERVED_35_SECONDS'
    except Exception as exc:
        result['state'] = 'OBSERVATION_STOPPED'
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if root is not None:
            os.close(root)
        result['finished_utc'] = utc()
        with os.fdopen(output_fd, 'w') as out:
            json.dump(result, out, sort_keys=True, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
