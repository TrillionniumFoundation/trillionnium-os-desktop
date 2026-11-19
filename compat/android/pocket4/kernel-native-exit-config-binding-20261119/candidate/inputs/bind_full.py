#!/usr/bin/python3
"""Read-only full-r3 evidence binder. CLI stays unconditionally HELD.

This source has no compiler, VM, systemctl, download, install or key-copy path.
After a separately reviewed revision, bind_completed_full may be called with
three externally observed, exact F9/length/SHA pins. It only emits a HELD
binding record. It never removes the holds in the three VM source files.
"""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import stat

HELD = 'HELD_AWAITING_COMPLETE_LIVE_FULL_BINDING_AND_REVIEW_NO_VM_LAUNCH'
BOUND_HELD = 'HELD_COMPLETE_FULL_BOUND_VM_NOT_AUTHORIZED'
ROOT = Path('/home/qq/work/p4-kernel-native-exit-full-11ea-20261119-r3')
CONTROL = ROOT / 'control/full-r3'
SOURCE = ROOT / 'source/linux-6.18.64'
OUT = ROOT / 'out-full-r3'
STAGE = ROOT / 'modules-full-r3'
ORIGINAL = Path('/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1')
NATIVE = Path('/home/qq/work/p4-broker-mac-provider-20261118-162b-r1/kernel-native-exit-candidate-r3')
VM = Path('/home/qq/work/p4-kernel-native-exit-vm260-11ea-20261119-r3')
EVIDENCE = Path('/home/qq/work/p4-native-exit-vm260-binding-evidence-5cd1-20261119-r1')
STATUS_PATH = EVIDENCE / 'full-durable-terminal.json'
RELEASE = '6.18.64-p4ctx6182'
UNIT = 'p4-kernel-native-exit-full-11ea-20261119-r3.service'
ACTUAL_FULL_PIN = {
    'path': str(CONTROL / 'full-observation.json'), 'bytes': 7978909,
    'sha256': '047a3dcb0506a5b7c5936a9edc65a5e87a1b3b53eb199a934c8baa5ccacf23cc',
    'identity': [66306,56687554,33152,1000,1000,1,7978909,1795069986071964871,1795069986073734557]}
ACTUAL_TERMINAL_PIN = {
    'path': str(CONTROL / 'full-terminal.json'), 'bytes': 46638,
    'sha256': '660aab1c9accda978e8c6e16488434fd57f18f91c1b4c651bd9859ceb99a0e42',
    'identity': [66306,56687557,33152,1000,1000,1,46638,1795069986304726117,1795069986304726117]}
# The actual tool response body is already observed. Its future isolated
# ordinary-qq capture has no observed F9 yet; the caller must supply that F9.
ACTUAL_STATUS_BODY = {'bytes': 729,
    'sha256': 'f7daec1be6bdebd7f2c72aaaf385b8a8503474fde07403b5ff5194e5a04ac857'}
GIB = 1024 ** 3
JSON_LIMIT = 64 * 1024 ** 2
ANCHORS_BYTES = 15046
ANCHORS_SHA256 = 'de0d4ab915bf6691283e4f0eb8090387cc446330ae9a385ff55339d5d17129b8'
F9_FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
             'st_size', 'st_mtime_ns', 'st_ctime_ns')
ARTIFACT_NAMES = ('arch/x86/boot/bzImage', 'vmlinux', 'System.map', '.config',
                  'Module.symvers', 'modules.order', 'modules.builtin',
                  'modules.builtin.modinfo', 'certs/signing_key.x509')
SOURCE_VM_INPUTS = ('scripts/selinux/mdp/mdp.c', 'security/selinux/include/classmap.h',
                    'security/selinux/include/initial_sid_to_string.h',
                    'security/selinux/include/policycap_names.h',
                    'scripts/extract-module-sig.pl')
CONFIG_HEX_SYMBOL = 'CONFIG_MTD_NAND_DISKONCHIP_PROBE_ADDRESS'
CONFIG_SEMANTIC_SOURCES = {
    'drivers/mtd/nand/raw/Kconfig':
        (17514, '7a7251734f79da0928019d8a384039139f277507088bed7060408ad8a62ab4f5'),
    'scripts/kconfig/confdata.c':
        (22318, 'aa99f69b2c4ae3ea38b031151e2604e49b8c3b9d4521a5c6f0b217f9dd982bea'),
}
PUBLIC_FIXTURES = {
    'tools/testing/selftests/net/ovpn/data64.key':
        (349, '20cf1390bc45fab71cd13f6e530c3941330d4ac67da19748a3bf34425cbef15f'),
    'tools/testing/selftests/sgx/sign_key.pem':
        (2455, '1f6566d02247dc09d4dcb542ee2399522ceebf9b435ee00fe2053aa5582541e2'),
}
RETIRED_FIELDS = {'LoadState': 'not-found', 'ActiveState': 'inactive',
                  'SubState': 'dead', 'MainPID': '0', 'ControlGroup': ''}
LAUNCH_PREREQUISITES = (
    'New reviewed VM revision must consume this binding; existing three holds remain unconditional.',
    'Preparation must hold the original VM serial during its actual work, not merely probe it.',
    'Both phases must bookend the exact new kernel source inputs and generated header below.',
    'Root must freshly check resource admission, process/unit conflicts and R12 supervisor/build/recovery.',
    'Use independent upload transport then normal-qq O_EXCL/no-follow staging; no transport sidecars in exact inputs.',
    'Keep two sequential normal units: 3GiB max, 2.5GiB high, zero swap, CPU22-23, 200%, Tasks128, 900s.',
    'Keep exact active160/inactive100 Counter catalogs and original PIDFD reap/retirement.',
    'This legacy suite never grants new native-exit ABI/provider or Android production qualification.',
)


class BindingError(RuntimeError):
    pass


def need(condition, reason):
    if not condition:
        raise BindingError(reason)


def f9(value):
    return [getattr(value, key) for key in F9_FIELDS]


def pairs(items):
    value = {}
    for key, item in items:
        need(key not in value, 'duplicate JSON key: ' + key)
        value[key] = item
    return value


def decode(body):
    def invalid(value):
        raise BindingError('nonfinite JSON: ' + value)
    return json.loads(body, object_pairs_hook=pairs, parse_constant=invalid)


def relative(value):
    need(isinstance(value, str) and value != '' and '\x00' not in value, 'relative path type')
    path = PurePosixPath(value)
    need(not path.is_absolute() and str(path) == value and '..' not in path.parts
         and value != '.', 'canonical relative path required')
    return path


def check_pin_shape(row, path=None):
    need(isinstance(row, dict) and set(row) == {'path', 'bytes', 'sha256', 'identity'}, 'complete pin required')
    need(isinstance(row['path'], str) and Path(row['path']).is_absolute(), 'absolute pinned path')
    if path is not None:
        need(row['path'] == str(path), 'unexpected pinned path: ' + str(path))
    need(type(row['bytes']) is int and 0 <= row['bytes'] <= 4 * GIB, 'bounded exact byte length')
    need(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'complete SHA256 required')
    identity = row['identity']
    need(isinstance(identity, list) and len(identity) == 9
         and all(type(x) is int for x in identity) and identity[6] == row['bytes'], 'complete F9 required')
    need(stat.S_ISREG(identity[2]), 'regular input required')
    need(Path(row['path']).name != 'signing_key.pem', 'user signing-key body forbidden')


class ReadSet:
    """Whole body/F9 reads followed by a final complete named-F9 bookend."""
    def __init__(self, perl):
        self.perl = perl
        self.pins = {}
        self.metadata = {}
        self.body_bytes = 0

    def remember_metadata(self, path, identity, link=None):
        path = Path(path)
        need(f9(path.lstat()) == identity, 'metadata mismatch: ' + str(path))
        if link is not None:
            need(path.is_symlink() and os.readlink(path) == link, 'symlink target mismatch')
        row = {'identity': identity, 'link': link}
        need(str(path) not in self.metadata or self.metadata[str(path)] == row, 'conflicting metadata')
        self.metadata[str(path)] = row

    def remember_pin(self, expected):
        """A named F9 bookend against a previously whole-body-bound pin."""
        check_pin_shape(expected)
        path = Path(expected['path'])
        need(path.resolve() == path and expected['identity'][5] == 1,
             'canonical single-link public product')
        self.remember_metadata(path, expected['identity'])

    def read(self, expected, capture=False):
        check_pin_shape(expected)
        path = Path(expected['path'])
        need(path.resolve() == path, 'input path follows a symlink: ' + str(path))
        before = f9(path.lstat())
        need(before == expected['identity'], 'input F9 changed: ' + str(path))
        if path == Path('/usr/bin/perl'):
            need(expected == self.perl and before[3:6] == [0, 0, 2], 'exact authenticated Perl only')
        else:
            need(before[5] == 1, 'single-link input required: ' + str(path))
        need(not capture or expected['bytes'] <= JSON_LIMIT, 'bounded captured body')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        h = hashlib.sha256(); chunks = []; size = 0
        try:
            need(f9(os.fstat(fd)) == before, 'opened inode differs')
            while True:
                block = os.read(fd, 1024 ** 2)
                if not block:
                    break
                size += len(block)
                need(size <= expected['bytes'], 'input grew while reading')
                h.update(block)
                if capture:
                    chunks.append(block)
            need(size == expected['bytes'] and h.hexdigest() == expected['sha256'], 'whole body mismatch: ' + str(path))
            need(f9(os.fstat(fd)) == before, 'input changed while reading')
        finally:
            os.close(fd)
        need(f9(path.lstat()) == before, 'named inode changed after reading')
        need(str(path) not in self.pins or self.pins[str(path)] == expected, 'conflicting file pins')
        self.pins[str(path)] = dict(expected)
        self.body_bytes += size
        need(self.body_bytes <= 96 * GIB, 'bounded complete binding I/O')
        return b''.join(chunks) if capture else None

    def document(self, expected):
        return decode(self.read(expected, capture=True))

    def current(self, path, limit=JSON_LIMIT):
        """Fresh post-full observation, never mislabeled as a full-worker pin."""
        path = Path(path)
        need(path.resolve() == path and path.name != 'signing_key.pem', 'canonical public observation')
        identity = f9(path.lstat())
        need(stat.S_ISREG(identity[2]) and identity[5] == 1 and identity[6] <= limit, 'bounded single-link observation')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        chunks = []; size = 0
        try:
            need(f9(os.fstat(fd)) == identity, 'observation inode changed')
            while True:
                block = os.read(fd, 1024 ** 2)
                if not block:
                    break
                size += len(block); need(size <= limit, 'observation grew')
                chunks.append(block)
            need(f9(os.fstat(fd)) == identity, 'observation changed while reading')
        finally:
            os.close(fd)
        need(f9(path.lstat()) == identity and size == identity[6], 'observation named bookend')
        body = b''.join(chunks)
        self.body_bytes += size
        need(self.body_bytes <= 96 * GIB, 'bounded complete binding I/O')
        row = {'path': str(path), 'bytes': size, 'sha256': hashlib.sha256(body).hexdigest(), 'identity': identity}
        self.read(row)
        return row, body

    def bookend(self):
        for path, expected in self.pins.items():
            need(Path(path).resolve() == Path(path) and f9(Path(path).lstat()) == expected['identity'], 'final file bookend: ' + path)
        for path, row in self.metadata.items():
            need(f9(Path(path).lstat()) == row['identity'], 'final metadata bookend: ' + path)
            if row['link'] is not None:
                need(os.readlink(path) == row['link'], 'final symlink bookend')


def known_inputs():
    path = Path(__file__).resolve().parent / 'KNOWN-INPUTS.json'
    before = f9(path.lstat())
    need(stat.S_ISREG(before[2]) and before[5] == 1 and before[6] == ANCHORS_BYTES, 'known-input type/size')
    need(path.resolve() == path, 'known-input path follows symlink')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(f9(os.fstat(fd)) == before, 'known-input descriptor identity')
        body = os.read(fd, ANCHORS_BYTES + 1)
        need(len(body) == ANCHORS_BYTES and f9(os.fstat(fd)) == before,
             'known-input descriptor bookend')
    finally:
        os.close(fd)
    need(hashlib.sha256(body).hexdigest() == ANCHORS_SHA256 and f9(path.lstat()) == before, 'fixed known-input pin')
    return decode(body), {'path': str(path), 'identity': before, 'bytes': len(body), 'sha256': ANCHORS_SHA256}


@contextmanager
def original_serials(known):
    """Binding-time custody only; this is not a future VM launch lease."""
    held = []
    try:
        for path, inode in [(ORIGINAL / 'control/build.serial.lock', 72394674),
                            (ORIGINAL / 'control/vm.serial.lock', 72404993)]:
            need(path.resolve() == path, 'serial path follows symlink')
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append((path, fd))
            identity = f9(os.fstat(fd))
            need(stat.S_ISREG(identity[2]) and identity[:2] == [66306, inode]
                 and identity[3:7] == [1000, 1000, 1, 0], 'original serial identity')
            if inode == 72394674:
                need(identity == known['TU_SERIAL'], 'original complete build-serial F9')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            need(f9(path.lstat()) == identity, 'serial named identity')
        identities = {str(path): f9(os.fstat(fd)) for path, fd in held}
        yield identities
        for path, fd in held:
            need(f9(os.fstat(fd)) == identities[str(path)] == f9(path.lstat()), 'serial final bookend')
    finally:
        for _, fd in reversed(held):
            os.close(fd)


def full_contract(full, terminal, full_pin, status, anchors):
    k = anchors['known_actual_TU_and_source']
    need(full_pin == ACTUAL_FULL_PIN, 'exact observed completed full receipt')
    need(full['schema'] == 'p4-native-exit-full-11ea-r3-v1'
         and terminal['schema'] == 'p4-native-exit-full-11ea-r3-terminal-v1', 'exact full-r3 schemas')
    for value in (full, terminal):
        need(value['source_revision'] == 3 and value['full_build_required_task_layout_changed'] is True, 'r3 task layout contract')
        need(all(value[x] is False for x in ('installed', 'booted', 'runtime_qualified', 'production_ready')), 'full build is not runtime credit')
        need('error' not in value and 'failed_ns' not in value, 'failed receipt cannot bind')
    need(full['stage'] == 'full-build-complete' and full['source_copy_is_complete_kernel_tree'] is True, 'complete full build required')
    for key in ('full_kernel_build_passed', 'whole_source_unchanged', 'tool_inputs_unchanged',
                'original_full_source_unchanged', 'original_full_release_artifacts_unchanged',
                'native_candidate_inputs_unchanged', 'actual_r3_tu_unchanged'):
        need(full[key] is True, 'missing complete full bookend: ' + key)
    for key in ('passed', 'worker_started', 'systemd_run_actual_reaped', 'cgroup_absent',
                'original_serial_reacquired', 'actual_r3_tu_unchanged', 'full_kernel_build_passed',
                'whole_source_unchanged', 'original_full_source_unchanged', 'original_full_release_artifacts_unchanged'):
        need(terminal[key] is True, 'incomplete original manager: ' + key)
    need('active_command' not in full and full['kernel_release'] == terminal['kernel_release'] == RELEASE, 'exact complete release')
    need(terminal['full_observation'] == full_pin, 'manager binds exact full observation')
    need(terminal['systemd_run_exit'] == 0 and terminal['systemd_run_waitid'] == {
        'pid': terminal['systemd_run_pid'], 'code': os.CLD_EXITED, 'status': 0}, 'original PIDFD wait and reap')
    need(len(terminal['systemd_run_pidfd_identity']) == 9, 'original held manager PIDFD record')
    need(not any(x in terminal for x in ('stop_own_unit', 'stop_own_unit_error', 'stop_residual_unit', 'exit_after_error')), 'normal manager completion required')
    need(terminal['unit_retirement'] == {'unit': UNIT, 'fields': RETIRED_FIELDS, 'cgroup_absent': True}, 'exact full unit retirement')
    need(full['lock'] == terminal['original_serial_before'] == terminal['original_serial_after'] == k['TU_SERIAL'], 'same original build serial')
    for name in ('full_worker', 'full_launcher'):
        row = full['worker'] if name == 'full_worker' else terminal['launcher']
        need(all(row[key] == value for key, value in anchors[name].items()), 'exact reviewed ' + name)
    need(terminal['worker'] == full['worker'], 'worker pin equality')
    need(terminal['argv'] == [
        '/usr/bin/systemd-run', '--user', '--unit=' + UNIT, '--wait', '--collect', '--pipe',
        '--service-type=exec', '--property=MemoryMax=21474836480',
        '--property=MemoryHigh=19327352832', '--property=MemorySwapMax=0',
        '--property=CPUAffinity=0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15',
        '--property=CPUQuota=800%', '--property=TasksMax=512',
        '--property=RuntimeMaxSec=10800', '--property=TimeoutStopSec=10',
        '--property=KillMode=control-group', '--property=Nice=10', '--property=UMask=0077',
        '--property=WorkingDirectory=' + str(ROOT), '/usr/bin/python3', '-I', '-B',
        anchors['full_worker']['path'], anchors['full_worker']['sha256']],
        'exact original normal-manager invocation')
    need(full['native_source_handoff'] == k['TU_HANDOFF_PIN'], 'exact frozen eight-file r3 source')
    tu = full['actual_r3_tu']
    need(terminal['actual_r3_tu'] == tu and tu['result'] == k['TU_RESULT_PIN']
         and tu['manager_retirement'] == k['TU_TERMINAL_PIN'] and tu['source_handoff'] == k['TU_HANDOFF_PIN'], 'actual r3 TU antecedents')
    need(tu['four_fresh_ET_REL_objects'] == k['TU_PRODUCTS'][:4]
         and tu['two_fresh_layout_headers'] == k['TU_PRODUCTS'][4:]
         and tu['actual_children_reaped'] == 11 and tu['source_tool_previous_output_bookends'] is True
         and tu['original_serial'] == k['TU_SERIAL'] and tu['full_build_required_task_layout_changed'] is True
         and tu['full_kernel_build_credit'] is False and tu['vm_credit'] is False, 'TU scope and complete actual products')
    need(len(tu['pins']) == len({r['path'] for r in tu['pins']}) == 73, 'complete actual TU evidence references')
    need(status['job_id'] == anchors['original_durable_job']['job_id']
         and status['launch_nonce'] == '2310b87cac41645e0809895200f860ac'
         and status['state'] == 'succeeded' and status['exit_code'] == 0
         and status['timed_out'] is False and status['cancelled'] is False
         and status['automatic_retry'] is False and status['audit_recorded'] is True
         and status['output_complete'] is True and status['output_durable'] is True
         and status['terminal_publication_confirmed'] is True
         and status['terminal_publication_protocol'] == 1, 'original authoritative outer terminal required')
    need(status['log_errors'] == {'stdout': None, 'stderr': None}
         and status['log_synced'] == {'stdout': True, 'stderr': True}
         and status['log_truncated'] == {'stdout': False, 'stderr': False}, 'complete original durable logs')
    need(full['started_ns'] <= full['finished_ns'] <= terminal['finished_ns']
         and (status['at_unix_ms'] + 1) * 1000000 > terminal['finished_ns'], 'full/outer terminal ordering')
    admission = full['admission']
    need(admission['pid'] == anchors['original_durable_job']['observed_MainPID'], 'same actually observed full worker')
    need(admission['limits'] == {'memory.max': str(20 * GIB), 'memory.high': str(18 * GIB),
         'memory.swap.max': '0', 'pids.max': '512', 'cpu.max': '800000 100000'}
         and admission['affinity'] == list(range(16)), 'original full resource limits')
    need(admission['memory_available'] >= 32 * GIB and admission['disk_free'] >= 96 * GIB
         and admission['own_output_budget'] == 64 * GIB and admission['host_disk_floor'] == 32 * GIB
         and admission['emergency_host_memory_floor'] == 8 * GIB, 'original full resource admission')
    events = dict(line.split() for line in full['cgroup_final']['memory.events'].splitlines())
    need(int(events['oom']) == int(events['oom_kill']) == 0
         and full['cgroup_final']['memory.swap.current'] == '0', 'actual full cgroup outcome')
    last = full['latest_resource_observation']
    need(last['own_allocated_bytes'] <= 64 * GIB and last['host_free_bytes'] >= 32 * GIB
         and last['memory_available'] >= 8 * GIB, 'actual full terminal resource floor')
    need(full['config_delta_from_original_release'] == {
        'CONFIG_LOCALVERSION': {'before': '"-p4ctx6181"', 'after': '"-p4ctx6182"'}}, 'only approved release config delta')
    need(full['published_test_fixture_bodies'] == 2 and full['user_private_signing_key_reads'] == 0, 'published fixture/private key distinction')
    need(len(full['artifacts']) == 9 and len(full['modules']) == len(full['staged_modules']) == 6797
         and terminal['modules'] == terminal['staged_modules'] == 6797, 'complete artifact/module counts')


def commands_and_logs(reads, full, terminal, tools):
    inputs = ORIGINAL / 'inputs/full-r2'
    make = ['make', '-C', str(SOURCE), 'O=' + str(OUT), '-j8',
            'CC=/usr/bin/x86_64-linux-gnu-gcc-15'] + tools['private_make_arguments']
    targets = [r['path'][:-2] + '.o' for r in full['source_delta'] if r['path'].endswith('.c')]
    targets.append('drivers/android/binder_linux.o')
    expected = []
    for label, patch in [('original-complete-delta', inputs / 'candidate.patch'), ('native-exit-delta', NATIVE / 'changes.patch')]:
        expected += [(label + '-dry-run', ['patch', '--dry-run', '--forward', '--batch', '--fuzz=0', '-p1', '-i', str(patch)]),
                     (label + '-apply', ['patch', '--forward', '--batch', '--fuzz=0', '-p1', '-i', str(patch)])]
    expected += [('config-adjust', [str(SOURCE / 'scripts/config'), '--file', str(OUT / '.config'),
        '--set-str', 'LOCALVERSION', '-p4ctx6182', '--disable', 'LOCALVERSION_AUTO',
        '--enable', 'IKCONFIG', '--enable', 'IKCONFIG_PROC', '--enable', 'DM_VERITY_FEC',
        '--enable', 'LOCK_DOWN_IN_SECURE_BOOT', '--enable', 'SECURITY_PERF_EVENTS_RESTRICT',
        '--set-str', 'LSM', 'landlock,lockdown,yama,integrity,apparmor,selinux,bpf']),
        ('olddefconfig', make + ['olddefconfig']), ('changed-translation-units', make + targets),
        ('full-kernel-and-modules', make + ['bzImage', 'modules']),
        ('kernel-release', make + ['--no-print-directory', '-s', 'kernelrelease']),
        ('modules-install-to-private-stage', make + ['INSTALL_MOD_PATH=' + str(STAGE), 'INSTALL_MOD_STRIP=1', 'modules_install'])]
    need([(r['name'], r['argv']) for r in full['commands']] == expected, 'exact ten actual full commands')
    previous = full['started_ns']
    for command in full['commands']:
        need(command['exit'] == 0 and previous <= command['started_ns'] <= command['finished_ns'] <= full['finished_ns'], 'actual command exit/order')
        previous = command['finished_ns']
        for channel in ('stdout', 'stderr'):
            row = command[channel]
            check_pin_shape(row, CONTROL / (command['name'] + '.' + channel))
            reads.read(row)
    release = next(r for r in full['commands'] if r['name'] == 'kernel-release')['stdout']
    need(reads.read(release, capture=True).decode().strip() == RELEASE, 'actual kernelrelease stdout')
    for channel in ('stdout', 'stderr'):
        check_pin_shape(terminal[channel], CONTROL / ('full-launch.' + channel))
        reads.read(terminal[channel])
    need([r['path'] for r in full['translation_units']] == [str(OUT / r) for r in targets], 'actual full-config TU products')


def complete_source(reads, full, handoff, hash_bodies=True):
    reference = full['whole_source_before']
    check_pin_shape(reference, CONTROL / 'whole-source-before.json')
    rows = reads.document(reference)
    need(len(rows) == full['whole_source_member_count'] == 97316, 'complete r3 source member set')
    need(handoff['files'] and len(handoff['files']) == handoff['cumulative_paths'] == 8
         and handoff['abi_bytes'] == 24 and handoff['ioctl_x86_64'] == '0x40182150'
         and handoff['source_revision'] == 3 and handoff['full_build_required_task_layout_changed'] is True, 'r3 source ABI')
    seen = set(); regular = 0; fixture_metadata = 0
    for parent, directories, files in os.walk(SOURCE, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name; rel = str(path.relative_to(SOURCE)); relative(rel)
            need(rel in rows and rel not in seen, 'unrecorded/duplicate source member: ' + rel)
            seen.add(rel); row = rows[rel]; identity = f9(path.lstat())
            need(identity == row['identity'], 'complete source F9: ' + rel)
            if row['kind'] == 'file':
                regular += 1
                need(stat.S_ISREG(identity[2]) and identity[5] == 1 and rel != 'certs/signing_key.pem', 'public single-link source')
                if rel in PUBLIC_FIXTURES:
                    need((row['bytes'], row['sha256']) == PUBLIC_FIXTURES[rel], 'published fixture pin')
                    reads.remember_metadata(path, identity); fixture_metadata += 1
                else:
                    pin = {'path': str(path), 'bytes': row['bytes'], 'sha256': row['sha256'], 'identity': identity}
                    if hash_bodies:
                        reads.read(pin)
                    else:
                        reads.remember_pin(pin)
            elif row['kind'] == 'symlink':
                reads.remember_metadata(path, identity, row['target'])
            else:
                need(row['kind'] == 'directory' and stat.S_ISDIR(identity[2]), 'source member type')
                reads.remember_metadata(path, identity)
    need(seen == set(rows) and regular == 91182 and fixture_metadata == 2, 'complete public source body/metadata scope')
    for row in handoff['files']:
        actual = rows[row['path']]
        need(actual['kind'] == 'file' and actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'], 'r3 exact postimage in full source')
    for row in full['source_delta']:
        actual = rows[row['path']]
        need(actual['bytes'] == row['after_bytes'] and actual['sha256'] == row['after_sha256'], 'complete full source delta')
    selected = []
    for name in SOURCE_VM_INPUTS:
        row = rows[name]
        selected.append({'path': str(SOURCE / name), 'bytes': row['bytes'], 'sha256': row['sha256'], 'identity': row['identity']})
    for row in selected:
        reads.read(row)
    return {'manifest': reference, 'members': len(rows),
            'whole_regular_source_bodies_read': regular - fixture_metadata if hash_bodies else len(selected),
            'published_fixture_metadata_only': fixture_metadata, 'new_native_source_files': handoff['files'],
            'VM_source_inputs': selected}


def declared_module_contract(full, names):
    """Pure exact-set checks; no filesystem, subprocess or success synthesis."""
    artifact = {r['path']: r for r in full['artifacts']}
    need(len(artifact) == len(full['artifacts']) == 9
         and set(artifact) == {str(OUT / p) for p in ARTIFACT_NAMES}, 'exact nine public release artifacts')
    need(full['config'] == artifact[str(OUT / '.config')], 'same actual config pin')
    need(len(names) == len(set(names)) == 6797, 'exact unique 6797 module order')
    need(all(str(relative(p)) == p and Path(p).suffix == '.ko' for p in names), 'canonical module names')
    built = {r['path']: r for r in full['modules']}; staged = {r['path']: r for r in full['staged_modules']}
    need(len(built) == len(full['modules']) == len(staged) == len(full['staged_modules']) == 6797
         and set(built) == {str(OUT / p) for p in names}
         and set(staged) == {str(STAGE / 'lib/modules' / RELEASE / 'kernel' / p) for p in names}, 'complete built/staged module bijection')
    for row in list(artifact.values()) + list(built.values()) + list(staged.values()):
        check_pin_shape(row)
        need(row['identity'][5] == 1, 'single-link release product')
    envelope = full['all_staged_module_signature_envelopes']
    need(envelope['module_count'] == 6797 and envelope['complete_pkcs7_envelopes'] is True
         and envelope['ordinary_kbuild_signing'] is True, 'ordinary Kbuild envelope contract')
    erows = {r['path']: r for r in envelope['modules']}
    need(len(erows) == len(envelope['modules']) == 6797 and set(erows) == set(staged), 'exact full signature-envelope members')
    for path, row in erows.items():
        need(set(row) == {'path','signature_bytes','pkcs7_signature_envelope'}
             and row['pkcs7_signature_envelope'] is True and type(row['signature_bytes']) is int
             and 0 < row['signature_bytes'] < staged[path]['bytes'] - 40, 'complete bounded signature envelope')
    need(full['private_module_stage'] == str(STAGE), 'isolated current module stage')
    return artifact, built, staged, erows


def module_set(reads, full, hash_bodies=True):
    order_rows = [r for r in full['artifacts'] if r['path'] == str(OUT / 'modules.order')]
    need(len(order_rows) == 1, 'exact module-order artifact')
    order = reads.read(order_rows[0], capture=True).decode().splitlines()
    names = []
    for line in order:
        if not line.strip():
            continue
        rel = relative(line.strip())
        if rel.suffix == '.o':
            rel = rel.with_suffix('.ko')
        need(rel.suffix == '.ko', 'module-order suffix'); names.append(str(rel))
    artifact, built, staged, erows = declared_module_contract(full, names)
    for row in artifact.values():
        reads.read(row) if hash_bodies else reads.remember_pin(row)
    need({str(p) for p in OUT.rglob('*.ko')} == set(built), 'actual built module membership')
    need({str(p) for p in STAGE.rglob('*') if p.name.endswith('.ko') or '.ko.' in p.name}
         == set(staged), 'actual staged module membership')
    magic = b'~Module signature appended~\n'
    for row in built.values():
        reads.read(row) if hash_bodies else reads.remember_pin(row)
    for path, row in staged.items():
        if not hash_bodies:
            reads.remember_pin(row)
            need(erows[path]['pkcs7_signature_envelope'] is True
                 and type(erows[path]['signature_bytes']) is int
                 and 0 < erows[path]['signature_bytes'] < row['bytes'] - len(magic) - 12,
                 'previous complete module envelope record')
            continue
        reads.read(row)
        need(row['bytes'] > len(magic) + 12, 'bounded module footer')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(f9(os.fstat(fd)) == row['identity'], 'signed module inode')
            footer = os.pread(fd, len(magic) + 12, row['bytes'] - len(magic) - 12)
            need(f9(os.fstat(fd)) == row['identity'], 'signed module footer bookend')
        finally:
            os.close(fd)
        need(footer[-len(magic):] == magic and footer[2] == 2 and footer[3:8] == b'\0' * 5, 'actual PKCS7 envelope')
        size = int.from_bytes(footer[8:12], 'big')
        need(0 < size < row['bytes'] - len(magic) - 12
             and erows[path] == {'path': path, 'signature_bytes': size, 'pkcs7_signature_envelope': True}, 'exact recorded signature length')
    need(full['private_module_stage'] == str(STAGE), 'isolated current module stage')
    return {'public_release_artifacts': list(artifact.values()), 'built_module_count': 6797,
            'staged_module_count': 6797, 'signature_envelope_count': 6797,
            'module_order': artifact[str(OUT / 'modules.order')],
            'all_module_cryptographic_signatures_verified_here': False,
            'future_VM_requirement': 'Retain the original actual OpenSSL CMS verification of each loaded module and the genuine unsigned/tampered negative modules.'}


def verified_hex_symbols(reads, full):
    """Use the exact full-build Kconfig type and C writer, never infer from text."""
    source_rows = reads.document(full['whole_source_before'])
    pins, bodies = [], {}
    for name, expected in CONFIG_SEMANTIC_SOURCES.items():
        row = source_rows[name]
        need(row['kind'] == 'file' and (row['bytes'], row['sha256']) == expected,
             'exact full-build Kconfig semantic source: ' + name)
        pin = {'path': str(SOURCE / name), 'bytes': row['bytes'],
               'sha256': row['sha256'], 'identity': row['identity']}
        bodies[name] = reads.read(pin, capture=True).decode()
        pins.append(pin)
    # confdata.c:print_symbol_for_c preserves S_HEX text and adds 0x only
    # when neither 0x nor 0X is present. Its complete body is pinned above.
    blocks = re.findall(r'(?m)^config ' + re.escape(CONFIG_HEX_SYMBOL[7:])
                        + r'\n((?:[ \t].*\n|\n)*)', bodies['drivers/mtd/nand/raw/Kconfig'])
    need(len(blocks) == 1 and re.findall(r'(?m)^[ \t]+(bool|tristate|string|int|hex)(?:[ \t]|$)',
                                       blocks[0]) == ['hex'],
         'exact selected configuration symbol is Kconfig HEX')
    return {CONFIG_HEX_SYMBOL}, pins


def compare_generated_configuration(config, header, hex_symbols):
    """Compare every symbol; only proven HEX symbols use the C writer's spelling."""
    need(hex_symbols == {CONFIG_HEX_SYMBOL}, 'only the source-proven HEX symbol')
    wanted = {}
    normalizations = []
    for line in config.splitlines():
        if not line.startswith('CONFIG_'):
            continue
        name, value = line.split('=', 1)
        if value == 'n':
            continue
        key = name + '_MODULE' if value == 'm' else name
        need(key not in wanted, 'duplicate config symbol')
        if name in hex_symbols:
            need(re.fullmatch(r'(?:0[xX])?[0-9a-fA-F]+', value) is not None,
                 'source-proven HEX symbol must have an unquoted hexadecimal value')
            if not value.startswith(('0x', '0X')):
                normalizations.append({'symbol': name, 'config_value': value,
                                       'generated_value': '0x' + value})
                value = '0x' + value
        wanted[key] = '1' if value in ('y', 'm') else value
    actual = {}
    for line in header.splitlines():
        if line.startswith('#define CONFIG_'):
            name, value = line[len('#define '):].split(' ', 1)
            need(name not in actual, 'duplicate generated config macro')
            actual[name] = value.strip()
    need(set(actual) == set(wanted), 'complete generated CONFIG symbol set differs')
    need(actual == wanted, 'complete generated autoconf does not match actual full config')
    return {'compared_CONFIG_macro_count': len(actual), 'HEX_spelling_normalizations': normalizations}


def generated_configuration(reads, full, expected_pin=None):
    """Bind a previously unrecorded generated input without inventing its origin."""
    config = reads.read(full['config'], capture=True).decode()
    hex_symbols, semantics = verified_hex_symbols(reads, full)
    if expected_pin is None:
        header, body = reads.current(OUT / 'include/generated/autoconf.h')
    else:
        check_pin_shape(expected_pin, OUT / 'include/generated/autoconf.h')
        header, body = expected_pin, reads.read(expected_pin, capture=True)
    comparison = compare_generated_configuration(config, body.decode(), hex_symbols)
    return {'pin': header, 'scope': 'fresh post-full readonly input; not a previously recorded full-worker artifact',
            'actual_full_config': full['config'], 'all_generated_CONFIG_macros_match_full_config': True,
            'Kconfig_semantic_sources': semantics, **comparison}


def module_indexes(reads, expected=None):
    """Fresh public depmod inputs, not mislabeled as original full artifacts."""
    root = STAGE / 'lib/modules' / RELEASE
    names = sorted(str(p) for p in root.iterdir() if stat.S_ISREG(p.lstat().st_mode))
    need(names and str(root / 'modules.dep') in names
         and all(Path(p).name.startswith('modules.') for p in names),
         'ordinary installed public module indexes')
    if expected is None:
        rows = [reads.current(Path(p), limit=16 * 1024**2)[0] for p in names]
    else:
        rows = expected
        need([r['path'] for r in rows] == names, 'complete module-index membership')
        for row in rows:
            reads.read(row)
    return {'inputs': rows, 'scope': 'fresh post-full public depmod-index observations; not full-worker artifact pins'}


def bind_completed_full(full_pin, terminal_pin, durable_status_pin, output):
    """Future reviewed call only; emits HELD evidence, never a VM dispatch."""
    need(os.getuid() == os.geteuid() == 1000, 'ordinary qq only')
    check_pin_shape(full_pin, CONTROL / 'full-observation.json')
    check_pin_shape(terminal_pin, CONTROL / 'full-terminal.json')
    check_pin_shape(durable_status_pin, STATUS_PATH)
    need(full_pin == ACTUAL_FULL_PIN and terminal_pin == ACTUAL_TERMINAL_PIN,
         'exact observed full and original manager F9/length/SHA')
    need(all(durable_status_pin[k] == v for k,v in ACTUAL_STATUS_BODY.items()),
         'exact original authoritative status bytes; no status reserialization')
    output = Path(output)
    need(output.is_absolute() and output.parent == EVIDENCE and output.name == 'HELD-BINDING.json'
         and not os.path.lexists(output), 'exclusive fixed binding output')
    parent = output.parent.lstat()
    need(output.parent.resolve() == output.parent and stat.S_ISDIR(parent.st_mode)
         and parent.st_uid == 1000 and stat.S_IMODE(parent.st_mode) == 0o700,
         'private ordinary-qq binding destination')
    anchors, anchors_pin = known_inputs(); k = anchors['known_actual_TU_and_source']
    reads = ReadSet(k['SYSTEM_PERL_PIN']); reads.read(anchors_pin)
    with original_serials(k) as serials:
        full = reads.document(full_pin); terminal = reads.document(terminal_pin)
        status = reads.document(durable_status_pin)
        full_contract(full, terminal, full_pin, status, anchors)
        cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / UNIT
        need(not os.path.lexists(cgroup), 'full worker cgroup still present')
        reads.read(full['worker']); reads.read(terminal['launcher'])
        handoff = reads.document(full['native_source_handoff'])
        need(handoff['files'] == k['TU_SOURCE_FILES'], 'all eight frozen r3 paths')
        for row in (k['TU_RESULT_PIN'], k['TU_TERMINAL_PIN']):
            reads.read(row)  # Keep original raw receipts, not every retired TU intermediate.
        tool_path = Path('/home/qq/work/p4-kernel-p4ctx1-scm-8764-r3/control/tool-inputs.json')
        tool_rows = [r for r in full['actual_r3_tu']['pins'] if r['path'] == str(tool_path)]
        need(len(tool_rows) == 1 and tool_rows[0]['sha256'] == '3657f30e2db081a6e74509560f6527add2a9a0965624d0eb111f5a633c5311ae', 'fixed original tool manifest')
        tools = reads.document(tool_rows[0])
        commands_and_logs(reads, full, terminal, tools)
        source = complete_source(reads, full, handoff)
        modules = module_set(reads, full)
        config = generated_configuration(reads, full)
        indexes = module_indexes(reads)
        for row in full['public_tool_inputs']:
            reads.read(row)
        for row in full['host_tools']:
            reads.read(row['resolved_input'])
            need(Path(row['invocation_path']).resolve() == Path(row['resolved_input']['path'])
                 and f9(Path(row['invocation_path']).lstat()) == row['alias_identity'], 'actual tool alias changed')
            reads.remember_metadata(Path(row['invocation_path']), row['alias_identity'],
                                    os.readlink(row['invocation_path']) if Path(row['invocation_path']).is_symlink() else None)
        for row in anchors['original_VM_input_bindings']:
            reads.read(row)
        # Whole-byte rereads of both original final receipts and the original
        # authoritative terminal close the small root evidence after all reads.
        for row in (full_pin, terminal_pin, durable_status_pin, anchors_pin):
            reads.read(row)
        reads.bookend()
        record = {'schema': 'p4-vm260-r3-complete-full-binding-held-v1', 'state': BOUND_HELD,
            'source_revision': 3, 'actual_full_evidence_verified': True,
            'full_observation': full_pin, 'original_full_terminal': terminal_pin,
            'original_durable_status_capture': durable_status_pin, 'known_inputs': anchors_pin,
            'release': RELEASE, 'source': source, 'modules': modules,
            'generated_configuration': config, 'module_indexes': indexes,
            'binding_time_original_serials': serials,
            'locks_are_not_a_future_launch_lease': True,
            'whole_file_reads': len(reads.pins), 'body_bytes_read': reads.body_bytes,
            'metadata_bookends': len(reads.metadata), 'all_final_named_F9_bookends_equal': True,
            'historical_TU_scope': 'Exact raw receipts retained and bound by actual full worker/manager; TU intermediates are historical, not claimed live by this binder.',
            'original_full_source_bookend_scope': 'Actual fixed full worker proves original full-r2 source/release preservation; this binder does not reread the old whole source.',
            'held_VM_source': anchors['held_VM_source'], 'launch_prerequisites': list(LAUNCH_PREREQUISITES),
            'launch_assessment_performed': False, 'VM_executed': False, 'native_exit_abi_qualified': False,
            'production_android_runtime_qualified': False, 'private_signing_key_bodies_read': 0,
            'published_fixture_bodies_read': 0, 'new_native_exit_C_fixture_created': False}
        body = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode()
        need(len(body) <= JSON_LIMIT, 'bounded binding record')
        reads.bookend()
    # The serial context completed its descriptor/named F9 checks and closed
    # its original handles. This is a historical read-only binding, not a VM
    # launch lease; each consumer must repeat all live named-F9 bookends.
    record['binding_time_serials_released'] = True
    body = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode()
    need(len(body) <= JSON_LIMIT, 'bounded complete binding record')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        pending = memoryview(body)
        while pending:
            count = os.write(fd, pending); need(count > 0, 'binding write failed'); pending = pending[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return record


class BoundPhase:
    """Consume a completed binding while an ordinary manager holds custody.

    The separate binder checked all regular source/module bodies. A VM phase
    checks their exact membership and every named F9, hashes the five actual
    kernel-source inputs and generated header again, and repeats these checks
    at its end. The phase still hashes each loaded product through its original
    digest path. This class never acquires a serial behind its caller's back.
    """
    def __init__(self, binding_pin):
        need(os.getuid() == os.geteuid() == 1000, 'ordinary qq VM phase')
        check_pin_shape(binding_pin, EVIDENCE / 'HELD-BINDING.json')
        self.anchors, self.anchors_pin = known_inputs()
        self.reads = ReadSet(self.anchors['known_actual_TU_and_source']['SYSTEM_PERL_PIN'])
        self.reads.read(self.anchors_pin)
        self.binding_pin = binding_pin
        self.binding = self.reads.document(binding_pin)
        b = self.binding
        need(b['schema'] == 'p4-vm260-r3-complete-full-binding-held-v1'
             and b['state'] == BOUND_HELD and b['actual_full_evidence_verified'] is True
             and b['source_revision'] == 3 and b['release'] == RELEASE
             and b['binding_time_serials_released'] is True,
             'complete held full binding required')
        need(all(b[x] is False for x in ('launch_assessment_performed', 'VM_executed',
             'native_exit_abi_qualified', 'production_android_runtime_qualified',
             'new_native_exit_C_fixture_created')), 'binding grants no runtime/launch credit')
        need(b['private_signing_key_bodies_read'] == b['published_fixture_bodies_read'] == 0,
             'no private key or public dummy-key body reads by binder')
        need(b['full_observation'] == ACTUAL_FULL_PIN
             and b['original_full_terminal'] == ACTUAL_TERMINAL_PIN,
             'fixed actual full/manager evidence in binding')
        check_pin_shape(b['original_durable_status_capture'], STATUS_PATH)
        need(all(b['original_durable_status_capture'][k] == v for k,v in ACTUAL_STATUS_BODY.items()),
             'same original authoritative status response')
        self.full = self.reads.document(b['full_observation'])
        self.terminal = self.reads.document(b['original_full_terminal'])
        self.status = self.reads.document(b['original_durable_status_capture'])
        full_contract(self.full, self.terminal, b['full_observation'], self.status, self.anchors)
        self.handoff = self.reads.document(self.full['native_source_handoff'])
        need(self.handoff['files'] == self.anchors['known_actual_TU_and_source']['TU_SOURCE_FILES'],
             'eight frozen source paths in VM binding')
        self.reads.read(self.full['worker']); self.reads.read(self.terminal['launcher'])
        need(b['known_inputs']['bytes'] == self.anchors_pin['bytes']
             and b['known_inputs']['sha256'] == self.anchors_pin['sha256'],
             'same exact known-input content across isolated staging')
        self._scope()
        self.reads.bookend()

    def _scope(self):
        b = self.binding
        source = complete_source(self.reads, self.full, self.handoff, hash_bodies=False)
        for key in ('manifest', 'members', 'published_fixture_metadata_only',
                    'new_native_source_files', 'VM_source_inputs'):
            need(source[key] == b['source'][key], 'same complete source binding: ' + key)
        need(b['source']['whole_regular_source_bodies_read'] == 91180,
             'complete earlier source body verification')
        need(module_set(self.reads, self.full, hash_bodies=False) == b['modules'],
             'same nine artifacts and complete 6797 module sets')
        need(generated_configuration(self.reads, self.full,
             b['generated_configuration']['pin']) == b['generated_configuration'],
             'same generated full-config input')
        need(module_indexes(self.reads, b['module_indexes']['inputs']) == b['module_indexes'],
             'same real depmod-index inputs')
        self.reads.read(self.full['config'])

    def source_inputs(self):
        return (list(self.binding['source']['VM_source_inputs'])
                + [self.binding['generated_configuration']['pin']]
                 + list(self.binding['generated_configuration']['Kconfig_semantic_sources'])
                + list(self.binding['module_indexes']['inputs']))

    def receipt_inputs(self):
        b = self.binding
        return [self.binding_pin, b['full_observation'], b['original_full_terminal'],
                b['original_durable_status_capture'], self.full['native_source_handoff'],
                self.full['whole_source_before']]

    def bookend(self):
        self._scope()
        for row in self.receipt_inputs() + [self.anchors_pin]:
            self.reads.read(row)
        self.reads.bookend()
        return {'binding': self.binding_pin,
                'all_97316_source_members_named_F9_equal': True,
                'all_nine_release_artifacts_named_F9_equal': True,
                'all_6797_built_and_staged_modules_named_F9_equal': True,
                'actual_VM_kernel_source_and_generated_header_SHA_equal': True,
                'complete_original_outer_terminal_bound': True,
                'module_index_inputs_SHA_equal': True,
                'phase_all_regular_source_bodies_rehashed': False,
                'phase_all_module_bodies_rehashed': False,
                'prior_complete_body_verification': self.binding_pin,
                'whole_file_reads': len(self.reads.pins),
                'body_bytes_read': self.reads.body_bytes,
                'metadata_bookends': len(self.reads.metadata),
                'native_exit_abi_qualified': False,
                'production_android_runtime_qualified': False}


def main():
    # No arguments, environment variables or incomplete/fabricated result can
    # turn this preparation revision into a running binder or VM launcher.
    raise BindingError(HELD)


if __name__ == '__main__':
    main()
