#!/usr/bin/env python3
"""One bounded, read-only snapshot of the already claimed framework job."""
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys
import time

JOB = '1a1ad81164b-fc05-5a14'
UNIT = 'hepta-runtime-job-' + JOB + '.service'
CG_PARENT = '/user.slice/user-1000.slice/user@1000.service/app.slice'
MEMBERSHIP = '0::' + CG_PARENT + '/' + UNIT
OWNER = '/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01'
ROOT = OWNER + '/typed-ingress-framework-build-01-20261105'
WORK = OWNER + '/typed-ingress-framework-work-01-20261105'
BUILD = '/home/alex/work/pocket4-native-typed-ingress-builder466-go5-compile-02-20261105'
BUILDER = BUILD + '/attempt01/cargo-target/debug/droidloom-update'
BUILD_ARGV = [BUILDER, '--source', BUILD + '/builder-source', '--jobs', '1',
              'native-role-ingress-build', '--work', WORK, '--out', ROOT + '/android-out']
CLAIM = ROOT + '/attempt-01/claim.json'
CLAIM_SHA = '9b62693a7c1b8b08cde5bad848f154e934c00e48943341f4040a3585836d1482'
CONTROLLER = ROOT + '/control-source/framework_build.py'
CONTROLLER_SHA = '12a86ce8fc03b281193a5942a5b7be0c1d7531f7f4e489f1eeca8db9688d1307'
MAX_PIDS = 128
DEADLINE = None
FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


class Rejected(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def budget():
    if DEADLINE is not None:
        require(time.monotonic() < DEADLINE, 'READ_BUDGET_EXHAUSTED')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink)


def open_dir(path):
    """Walk only this literal absolute path; never enumerate directories."""
    require(path.startswith('/') and '..' not in PurePosixPath(path).parts, 'FIXED_DIRECTORY_REQUIRED')
    fd = os.open('/', FLAGS | os.O_DIRECTORY)
    try:
        for part in PurePosixPath(path).parts[1:]:
            budget()
            next_fd = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def bounded(parent, name, maximum):
    budget()
    require('/' not in name and name not in ('.', '..'), 'FIXED_LEAF_REQUIRED')
    fd = os.open(name, FLAGS, dir_fd=parent)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode), 'REGULAR_FILE_REQUIRED')
        raw = b''
        while len(raw) <= maximum:
            budget()
            chunk = os.read(fd, min(4096, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        require(len(raw) <= maximum, 'READ_BOUND_EXCEEDED')
        last = os.fstat(fd)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(identity(first) == identity(last) == identity(named), 'READ_FILE_IDENTITY_CHANGED')
        return raw
    finally:
        os.close(fd)


def fixed_file(path, size, expected):
    parent = open_dir(str(PurePosixPath(path).parent))
    try:
        before = os.stat(PurePosixPath(path).name, dir_fd=parent, follow_symlinks=False)
        raw = bounded(parent, PurePosixPath(path).name, size)
        after = os.stat(PurePosixPath(path).name, dir_fd=parent, follow_symlinks=False)
        require(identity(before) == identity(after) and before.st_nlink == 1 and
                before.st_size == after.st_size == len(raw) == size and
                before.st_mtime_ns == after.st_mtime_ns and before.st_ctime_ns == after.st_ctime_ns and
                sha(raw) == expected, 'FIXED_INPUT_CHANGED')
        return raw
    finally:
        os.close(parent)


def pid_list(raw):
    values = raw.split()
    require(len(values) <= MAX_PIDS and all(re.fullmatch(b'[1-9][0-9]{0,9}', v) for v in values),
            'OWN_JOB_PID_BOUND_OR_FORMAT')
    return sorted(set(int(v) for v in values))


def proc_stat(raw, pid):
    left, right = raw.find(b'('), raw.rfind(b')')
    require(left > 0 and right > left and raw[:left].strip() == str(pid).encode(), 'PROC_STAT_PID_FORMAT')
    fields = raw[right + 1:].split()
    require(len(fields) >= 20 and fields[0] in (b'R', b'S', b'D', b'Z', b'T', b't', b'X',
            b'x', b'K', b'W', b'P', b'I', b'N') and
            all(re.fullmatch(b'[0-9]+', fields[n]) for n in (1, 11, 12, 19)), 'PROC_STAT_FIELDS')
    return {'comm': raw[left + 1:right], 'state': fields[0].decode(), 'ppid': int(fields[1]),
            'user': int(fields[11]), 'system': int(fields[12]), 'start': int(fields[19])}


def local_path(raw):
    """Publish only canonical paths inside these exact owned build roots."""
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', 'strict')
    if len(raw) > 4096 or not raw.startswith('/') or '..' in PurePosixPath(raw).parts:
        return None
    if str(PurePosixPath(raw)) != raw:
        return None
    for prefix, label in ((WORK, 'work'), (ROOT, 'build'), (BUILD, 'builder')):
        if raw == prefix:
            return {'root': label, 'relative': '.'}
        if raw.startswith(prefix + '/'):
            relative = raw[len(prefix) + 1:]
            if len(relative) <= 512 and re.fullmatch(r'[A-Za-z0-9_./+@=-]+', relative):
                return {'root': label, 'relative': relative}
    return None


def argv_view(raw):
    """Classify known tools; never return raw argv, arbitrary flags or URLs."""
    if not raw:
        return {'class': 'empty'}
    require(raw.endswith(b'\0'), 'COMMAND_LINE_NOT_COMPLETE')
    args = raw[:-1].split(b'\0')
    if args == [a.encode() for a in BUILD_ARGV]:
        return {'class': 'exact_typed_framework_builder'}
    name = args[0].rsplit(b'/', 1)[-1]
    result = {'class': 'unclassified'}
    if name == b'git':
        i = 1
        while i < len(args):
            if args[i] in (b'-C', b'-c', b'--git-dir', b'--work-tree', b'--shallow-file') and i + 1 < len(args):
                if args[i] == b'-C':
                    chosen = local_path(args[i + 1])
                    if chosen is not None:
                        result['local_project_cwd'] = chosen
                i += 2
            elif args[i].startswith((b'--git-dir=', b'--work-tree=', b'--shallow-file=')):
                i += 1
            else:
                break
        operations = {b'init', b'remote', b'sparse-checkout', b'fetch', b'checkout', b'rev-parse',
                      b'status', b'apply', b'index-pack', b'unpack-objects', b'pack-objects'}
        result['class'] = 'git_' + args[i].decode() if i < len(args) and args[i] in operations else 'git_other'
    elif name in (b'git-remote-https', b'git-remote-http', b'git-index-pack', b'git-unpack-objects'):
        result['class'] = name.decode().replace('-', '_')
    elif args[0] == (ROOT + '/android-out/soong_ui').encode():
        result['class'] = 'owned_soong_ui'
    elif args[0] == (ROOT + '/android-out/microfactory_Linux').encode():
        result['class'] = 'owned_microfactory'
    elif args[0] == (WORK + '/aosp-source/prebuilts/go/linux-x86/bin/go').encode():
        result['class'] = 'owned_go'
    elif name in (b'ninja', b'clang', b'clang++', b'javac', b'java', b'ckati', b'soong_build',
                  b'compile', b'link', b'asm', b'rustc'):
        result['class'] = 'build_tool_name_only_' + name.decode()
    if result['class'] != 'unclassified':
        urls = [sha(a) for a in args if a.startswith((b'https://', b'http://', b'ssh://', b'git://'))]
        if urls:
            result['remote_URL_sha256'] = sorted(set(urls))[:8]
    return result


def command_bytes(fd):
    try:
        return bounded(fd, 'cmdline', 16384)
    except Rejected as error:
        if str(error) == 'READ_BOUND_EXCEEDED':
            return None
        raise


def observe_pid(proc, pid):
    budget()
    fd = os.open(str(pid), FLAGS | os.O_DIRECTORY, dir_fd=proc)
    try:
        first = os.fstat(fd)
        require(first.st_uid == 1000, 'OWN_OPERATOR_PID_REQUIRED')
        a = proc_stat(bounded(fd, 'stat', 4096), pid)
        require(bounded(fd, 'cgroup', 4096).decode().strip() == MEMBERSHIP, 'PID_NOT_IN_EXACT_JOB')
        comm = bounded(fd, 'comm', 128).rstrip(b'\n')
        require(re.fullmatch(b'[A-Za-z0-9_.+-]{1,32}', comm) is not None, 'COMM_NOT_PUBLIC_TOOL_NAME')
        command = command_bytes(fd)
        budget()
        cwd = os.readlink('cwd', dir_fd=fd)
        require(len(cwd) <= 4096, 'CWD_BOUND')
        wchan = bounded(fd, 'wchan', 128).strip()
        require(re.fullmatch(b'[A-Za-z0-9_.]{1,96}', wchan) is not None, 'WCHAN_FORMAT')
        require(command_bytes(fd) == command and os.readlink('cwd', dir_fd=fd) == cwd and
                bounded(fd, 'comm', 128).rstrip(b'\n') == comm, 'PID_COMMAND_OR_CWD_CHANGED')
        require(bounded(fd, 'cgroup', 4096).decode().strip() == MEMBERSHIP, 'PID_LEFT_EXACT_JOB')
        b = proc_stat(bounded(fd, 'stat', 4096), pid)
        require(a['start'] == b['start'] and a['comm'] == b['comm'] == comm and
                identity(first) == identity(os.fstat(fd)) ==
                identity(os.stat(str(pid), dir_fd=proc, follow_symlinks=False)), 'PID_IDENTITY_CHANGED')
        require(b['user'] >= a['user'] and b['system'] >= a['system'], 'CPU_COUNTER_REGRESSED')
        return {'pid': pid, 'start_ticks': a['start'], 'comm': comm.decode(),
                'state_before': a['state'], 'state_after': b['state'], 'ppid': b['ppid'],
                'cpu_ticks_before': [a['user'], a['system']], 'cpu_ticks_after': [b['user'], b['system']],
                'wchan': wchan.decode(), 'cwd': local_path(cwd) or {'scope': 'outside_owned_roots_not_disclosed'},
                'command': argv_view(command) if command is not None else {'class': 'over_bound_not_read'},
                'identity_and_membership_stable': True}
    finally:
        os.close(fd)


def main():
    global DEADLINE
    require(sys.argv[1:] == ['--execute-once'], 'EXPLICIT_ONCE_REQUIRED')
    start = time.monotonic()
    DEADLINE = start + 2.4
    result = {'schema': 1, 'job': JOB, 'unit': UNIT, 'read_only': True, 'pid_limit': MAX_PIDS,
              'observations': [], 'unobserved': [], 'complete': False, 'error': None}
    cg = proc = None
    try:
        require(os.getuid() == os.geteuid() == 1000, 'ORIGINAL_OPERATOR_REQUIRED')
        claim = json.loads(fixed_file(CLAIM, 3352, CLAIM_SHA))
        require(claim['unit'] == UNIT and claim['plan']['root'] == ROOT and
                claim['plan']['work'] == WORK and claim['plan']['argv'] == BUILD_ARGV and
                claim['plan']['builder_sha256'] == '309e96393ab482c958a519b78a455a6c75d156a6edb805c840aa6d21f76fa96a',
                'ACTUAL_CLAIM_SCOPE_CHANGED')
        fixed_file(CONTROLLER, 38463, CONTROLLER_SHA)
        path = '/sys/fs/cgroup' + CG_PARENT + '/' + claim['unit']
        cg = open_dir(path)
        cg_identity = identity(os.fstat(cg))
        require(re.search(rb'(?m)^nr_descendants 0$', bounded(cg, 'cgroup.stat', 2048)) is not None,
                'UNEXPECTED_CHILD_CGROUP_NOT_ENUMERATED')
        pids = pid_list(bounded(cg, 'cgroup.procs', 2048))
        result.update(claim_sha256=CLAIM_SHA, controller_sha256=CONTROLLER_SHA,
                      cgroup_path=path, clock_ticks_per_second=os.sysconf('SC_CLK_TCK'),
                      initial_pid_count=len(pids), unexpected_child_cgroups=False)
        proc = open_dir('/proc')
        output_bytes = 0
        for pid in pids:
            budget()
            try:
                row = observe_pid(proc, pid)
                output_bytes += len(json.dumps(row, ensure_ascii=True).encode())
                require(output_bytes <= 100000, 'OBSERVATION_OUTPUT_BOUND')
                result['observations'].append(row)
            except (Rejected, OSError, UnicodeError, ValueError) as error:
                code = str(error) if isinstance(error, Rejected) else type(error).__name__
                result['unobserved'].append({'pid': pid, 'reason': code})
                if code in ('READ_BUDGET_EXHAUSTED', 'OBSERVATION_OUTPUT_BOUND'):
                    raise
        after = pid_list(bounded(cg, 'cgroup.procs', 2048))
        require(re.search(rb'(?m)^nr_descendants 0$', bounded(cg, 'cgroup.stat', 2048)) is not None,
                'CHILD_CGROUP_APPEARED_NOT_ENUMERATED')
        require(cg_identity == identity(os.fstat(cg)) == identity(os.stat(path, follow_symlinks=False)),
                'CGROUP_IDENTITY_CHANGED')
        result.update(final_pid_count=len(after), pid_set_changed=pids != after,
                      complete=not result['unobserved'] and pids == after)
    except (Rejected, OSError, UnicodeError, ValueError, KeyError) as error:
        result['error'] = str(error) if isinstance(error, Rejected) else type(error).__name__
    finally:
        for fd in (proc, cg):
            if fd is not None:
                os.close(fd)
        result['elapsed_seconds'] = round(time.monotonic() - start, 6)
        result['build_source_or_binary_executed'] = False
        result['progress_snapshot_not_build_success'] = True
        raw = json.dumps(result, ensure_ascii=True, separators=(',', ':'))
        require(len(raw.encode()) <= 131072, 'OUTPUT_BOUND')
        print(raw, flush=True)
    return 0 if result['error'] is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
