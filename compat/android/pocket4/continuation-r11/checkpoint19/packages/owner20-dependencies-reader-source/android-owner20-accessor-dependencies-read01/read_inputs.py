#!/usr/bin/env python3
"""Fixed Android executable startup/header inputs. Read-only; no compiler or target runs."""
import errno
import hashlib
import json
import os
import stat
import struct
import sys
import time

SDK = '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1'
BIONIC = SDK + '/aosp-source/bionic/libc'
SOONG = SDK + '/android-composer-leaf-out-r14/soong/.intermediates/bionic/libc'
ACTUAL_REPORT = '/opt/p4-owner16-init-log-android-20261105-build-01/build-result.json'
ACTUAL_PIN = (661519, '2c53bba3ab02b396d2698dfd6e04d870ce69cc55724c6077003dca81ae9a2e0b')
ANCHORS = (
    (BIONIC + '/include/unistd.h', 18701,
     'd4b653b674b921bdfbb996afdcd92a84a128cbe1d9bc872e4e661c4caeab0702'),
    (SOONG + '/crtbegin_so/android_vendor_x86_64/crtbegin_so.o', 7920,
     '9ab2a53e03c04dd87c03a1577e62d8a5b14cf11d50ae70dbb21b9b0f03d90b76'),
    (SOONG + '/crtend_so/android_vendor_x86_64/crtend_so.o', 720,
     'be0274d7f12d0e8921d3517cf5640bbc4655572838b6b541f208ded17224bb9f'),
)
CANDIDATES = (
    ('crtbegin_dynamic', SOONG + '/crtbegin_dynamic/android_vendor_x86_64/crtbegin_dynamic.o', 'ELF64_REL', 65536),
    ('crtend_android', SOONG + '/crtend_android/android_vendor_x86_64/crtend_android.o', 'ELF64_REL', 65536),
    ('system_properties', BIONIC + '/include/sys/system_properties.h', 'UTF8_HEADER', 32768),
    ('groups', BIONIC + '/include/grp.h', 'UTF8_HEADER', 32768),
    ('prctl', BIONIC + '/include/sys/prctl.h', 'UTF8_HEADER', 32768),
    ('prctl_uapi', BIONIC + '/kernel/uapi/linux/prctl.h', 'UTF8_HEADER', 32768),
    ('capability_uapi', BIONIC + '/kernel/uapi/linux/capability.h', 'UTF8_HEADER', 32768),
)
DEADLINE = 10.0
MAX_HELD = 128
MAX_READ_TOTAL = 2 * 1024 * 1024
OUTPUT_LIMIT = 131072
ALLOW = {ACTUAL_REPORT} | {row[0] for row in ANCHORS} | {row[1] for row in CANDIDATES}

def need(value, message):
    if not value:
        raise RuntimeError(message)

def stamp(value, directory=False):
    result = {'device': value.st_dev, 'inode': value.st_ino,
        'type': stat.S_IFMT(value.st_mode), 'mode': stat.S_IMODE(value.st_mode),
        'uid': value.st_uid, 'gid': value.st_gid}
    if not directory:
        result.update(bytes=value.st_size, nlink=value.st_nlink,
            mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)
    return result

def remember(report, stage, error):
    row = {'stage': stage, 'type': type(error).__name__,
           'error': str(error)[:512],
           'errno': error.errno if isinstance(error, OSError) else None}
    if report['first_error'] is None:
        report['first_error'] = row
    if len(report['errors']) < 24:
        report['errors'].append(row)

class Held:
    def __init__(self, end):
        self.end = end
        self.rows = []
        self.cache = {}
        self.read_bytes = 0
        self.complete_reads = []

    def time(self):
        need(time.monotonic() < self.end, 'fixed dependency read deadline exceeded')

    def open(self, path, maximum):
        need(path in ALLOW and path.startswith('/') and
             all(x not in ('', '.', '..') for x in path.split('/')[1:]),
             'outside exact dependency allowlist')
        parts = ['/'] + path.split('/')[1:]
        parent = None
        prefix = ''
        for index, name in enumerate(parts):
            self.time()
            directory = index < len(parts) - 1
            prefix = '/' if index == 0 else prefix.rstrip('/') + '/' + name
            if prefix in self.cache:
                row = self.cache[prefix]
                need(row['directory'] == directory, 'cached path type differs')
                parent = row['fd']
                continue
            need(len(self.rows) < MAX_HELD, 'held input count exceeded')
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            fd = os.open(name, flags, **({} if parent is None else {'dir_fd': parent}))
            row = {'fd': fd, 'parent': parent, 'name': name, 'path': prefix,
                   'directory': directory, 'before': None}
            self.rows.append(row)  # Ownership registered before fstat or any other fallible step.
            value = os.fstat(fd)
            if directory:
                need(stat.S_ISDIR(value.st_mode), 'fixed path component is not a directory')
            else:
                need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and
                     value.st_uid in (0, 1000) and value.st_gid in (0, 1000) and
                     not value.st_mode & 0o7002 and 0 < value.st_size <= maximum,
                     'fixed input type/owner/special/world-write/size differs')
                try:
                    caps = os.getxattr(fd, 'security.capability')
                except OSError as error:
                    need(error.errno in (errno.ENODATA, errno.EOPNOTSUPP),
                         'input capabilities cannot be established')
                    caps = b''
                need(caps == b'', 'input has file capabilities')
            row['before'] = stamp(value, directory)
            named = os.stat(name, follow_symlinks=False,
                            **({} if parent is None else {'dir_fd': parent}))
            need(stamp(named, directory) == row['before'], 'named and held input differ')
            self.cache[prefix] = row
            parent = fd
        return row

    def read(self, row):
        size = row['before']['bytes']
        need(self.read_bytes + size <= MAX_READ_TOTAL, 'total fixed read budget exceeded')
        body = bytearray()
        while len(body) < size:
            self.time()
            chunk = os.pread(row['fd'], min(65536, size - len(body)), len(body))
            need(bool(chunk), 'short fixed dependency read')
            body.extend(chunk)
        need(not os.pread(row['fd'], 1, size), 'fixed dependency grew')
        self.read_bytes += len(body)
        need(stamp(os.fstat(row['fd'])) == row['before'], 'input changed while reading')
        raw = bytes(body)
        self.complete_reads.append((row, hashlib.sha256(raw).hexdigest()))
        return raw

    def recheck(self):
        self.time()
        for row in self.rows:
            need(row['before'] is not None, 'input opening was incomplete')
            observed = stamp(os.fstat(row['fd']), row['directory'])
            named = os.stat(row['name'], follow_symlinks=False,
                **({} if row['parent'] is None else {'dir_fd': row['parent']}))
            need(observed == row['before'] == stamp(named, row['directory']),
                 'fixed named/held input changed')
        completed = list(self.complete_reads)
        for row, digest in completed:
            need(hashlib.sha256(self.read(row)).hexdigest() == digest,
                 'fixed full input content changed')

    def close(self, report):
        closed = True
        for row in reversed(self.rows):
            try:
                os.close(row['fd'])  # Exactly one attempt, including close errors.
            except BaseException as error:
                closed = False
                remember(report, 'close:' + row['path'], error)
        return closed

def elf_object(raw):
    need(len(raw) >= 64, 'CRT object has no complete ELF64 header')
    values = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    ident, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, shstr = values
    need(ident[:7] == b'\x7fELF\x02\x01\x01' and kind == 1 and machine == 62 and
         version == 1 and entry == 0 and ehsize == 64 and phnum == 0 and
         shsize == 64 and 1 <= shnum <= 256 and 0 < shstr < shnum and
         shoff <= len(raw) and shnum * shsize <= len(raw) - shoff,
         'fixed CRT is not a bounded x86_64 ET_REL object')
    return {'class': 64, 'byte_order': 'little', 'type': 'ET_REL',
            'machine': 'x86_64', 'section_count': shnum,
            'binary_body_exported': False, 'executable_startup_qualified': False}

def main():
    started = time.monotonic()
    held = Held(started + DEADLINE)
    report = {'schema': 1, 'kind': 'owner20-fixed-Android-accessor-inputs-read01',
        'collection_complete': False, 'first_error': None, 'errors': [],
        'anchors': [], 'candidates': [], 'held_named_unchanged': False,
        'held_fds_closed': False, 'commands': [], 'child_processes': 0,
        'files_created': False, 'Main_or_services_touched': False,
        'live_Main_checked': False, 'namespace_or_UID_changes': False,
        'compiler_executed': False, 'Android_executed': False,
        'runtime_qualified': False, 'source_paths_previously_unobserved': True,
        'candidate_missing_is_failure_without_scan_or_fallback': True,
        'operator_owned_source_inputs_may_be_group_writable': True}
    header_total = 0
    try:
        need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
             'fixed protected build receipt requires root')
        row = held.open(ACTUAL_REPORT, ACTUAL_PIN[0])
        raw = held.read(row)
        need((len(raw), hashlib.sha256(raw).hexdigest()) == ACTUAL_PIN,
             'C16 actual receipt whole pin differs')
        actual = json.loads(raw.decode('utf-8'))
        need(actual['success'] is True and actual['errors'] == [] and
             actual['all_inputs_unchanged'] is True and
             actual['root'] == '/opt/p4-owner16-init-log-android-20261105-build-01',
             'C16 actual build receipt is not the exact qualified source')
        report['actual_receipt'] = {'path': ACTUAL_REPORT, 'bytes': len(raw),
            'sha256': ACTUAL_PIN[1], 'metadata': row['before']}
        for path, size, digest in ANCHORS:
            expected = actual['original_inputs_before'][path]
            need(expected['bytes'] == size and expected['sha256'] == digest,
                 'C16 authority anchor differs')
            row = held.open(path, size)
            raw = held.read(row)
            need((len(raw), hashlib.sha256(raw).hexdigest()) == (size, digest),
                 'C16 exact source/Soong anchor content differs')
            need(row['before']['uid'] == expected['uid'] and
                 row['before']['gid'] == expected['gid'],
                 'C16 anchor owner differs')
            report['anchors'].append({'path': path, 'bytes': size,
                'sha256': digest, 'metadata': row['before']})
        for label, path, kind, maximum in CANDIDATES:
            member = {'label': label, 'path': path, 'expected_kind': kind,
                      'observed': False, 'first_error': None}
            report['candidates'].append(member)
            try:
                row = held.open(path, maximum)
                raw = held.read(row)
                need(row['before']['uid'] == row['before']['gid'] == 1000,
                     'candidate owner differs from held C16 source authority')
                member.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                              metadata=row['before'])
                if kind == 'UTF8_HEADER':
                    header_total += len(raw)
                    need(header_total <= 65536, 'fixed header body output budget exceeded')
                    text = raw.decode('utf-8')
                    need('\0' not in text, 'fixed header contains NUL')
                    member['utf8'] = text
                else:
                    member['ELF'] = elf_object(raw)
                member['observed'] = True
            except BaseException as error:
                member['first_error'] = {'type': type(error).__name__,
                    'error': str(error)[:512],
                    'errno': error.errno if isinstance(error, OSError) else None}
                remember(report, 'candidate:' + label, error)
    except BaseException as error:
        remember(report, 'fixed_input_collection', error)
    finally:
        try:
            held.recheck()
            report['held_named_unchanged'] = True
        except BaseException as error:
            remember(report, 'final_full_content_and_named_recheck', error)
        report['held_descriptor_count'] = len(held.rows)
        report['held_fds_closed'] = held.close(report)
    report['elapsed_seconds'] = time.monotonic() - started
    report['full_read_bytes'] = held.read_bytes
    if report['elapsed_seconds'] >= DEADLINE:
        remember(report, 'deadline', RuntimeError('fixed dependency deadline exceeded'))
    report['collection_complete'] = (not report['errors'] and report['held_named_unchanged'] and
        report['held_fds_closed'] and len(report['anchors']) == 3 and
        len(report['candidates']) == 7 and all(r['observed'] for r in report['candidates']))
    raw = (json.dumps(report, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    need(len(raw) <= OUTPUT_LIMIT, 'fixed dependency wire exceeds bound')
    sys.stdout.buffer.write(raw)
    return 0 if report['collection_complete'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
