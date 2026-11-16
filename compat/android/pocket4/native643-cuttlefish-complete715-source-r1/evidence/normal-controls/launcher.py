import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

B = Path('/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/tools-build-cuttlefish643-20261113-takeover-r1')
Q = B / 'control'
INNER = B / 'qualification/result.json'
UNIT = 'p4-native643-cuttlefish-normal-20261113-takeover-r1.service'
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/home/qq', 'LANG': 'C', 'LC_ALL': 'C',
       'XDG_RUNTIME_DIR': '/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'}
F = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
     'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def ident(st):
    return [getattr(st, key) for key in F]


def pin(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 1000
             and before.st_nlink == 1 and before.st_size < 2 * 1024 ** 2, 'bounded ordinary input')
        data = bytearray()
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            data.extend(block)
            need(len(data) <= before.st_size, 'input grew')
        need(len(data) == before.st_size and ident(before) == ident(os.fstat(fd)) == ident(path.lstat()),
             'same complete held/named ordinary input')
        return bytes(data)
    finally:
        os.close(fd)


def put(name, data):
    path = Q / name
    need(path.parent == Q and path.name == name, 'fixed direct ordinary evidence file')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            need(n > 0, 'evidence write')
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return pin(path, data)


def jb(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


exec('"""Current self-only outer-unit cap; historical missing swap proof stays missing."""\nimport hashlib,os,select,signal,subprocess\nfrom pathlib import Path\n\ndef need(value,message):\n if not value:raise RuntimeError(message)\n\ndef qualify_outer(memory_bytes,cpu_percent):\n need((memory_bytes,cpu_percent)in((536870912,100),(1073741824,100),(4294967296,200)),\'exact approved Source publication/entry outer profile required\')\n need(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,\'ordinary own-unit controller required\');os.sched_setaffinity(0,{8,9});text=Path(\'/proc/self/cgroup\').read_text().strip();need(text.startswith(\'0::/\'),\'own unified cgroup required\');cg=Path(\'/sys/fs/cgroup\')/text.removeprefix(\'0::/\');need((memory_bytes,cpu_percent)==(4294967296,200)and cg.name==\'p4-native643-cuttlefish-normal-20261113-takeover-r1.service\' or (memory_bytes,cpu_percent)in((536870912,100),(1073741824,100))and cg.name.startswith(\'hepta-runtime-job-\')and cg.name.endswith(\'.service\'),\'only own Hepta outer or exact own new normal compiler unit may receive swap cap\')\n names=(\'memory.max\',\'memory.swap.max\',\'memory.swap.current\',\'cpu.max\',\'memory.events\');before={name:(cg/name).read_text().strip()for name in names};argv=[\'/usr/bin/systemctl\',\'--user\',\'set-property\',\'--runtime\',cg.name,\'MemorySwapMax=0\'];env={\'HOME\':\'/home/qq\',\'PATH\':\'/usr/bin:/bin\',\'XDG_RUNTIME_DIR\':\'/run/user/1000\',\'DBUS_SESSION_BUS_ADDRESS\':\'unix:path=/run/user/1000/bus\'};child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,start_new_session=True)\n try:pidfd=os.pidfd_open(child.pid,0)\n except BaseException:\n  if child.poll()is None:child.kill()\n  child.wait(timeout=5);raise\n control=None\n try:\n  try:stdout,stderr=child.communicate(timeout=15)\n  except subprocess.TimeoutExpired:\n   signal.pidfd_send_signal(pidfd,signal.SIGTERM)\n   try:stdout,stderr=child.communicate(timeout=5)\n   except subprocess.TimeoutExpired:signal.pidfd_send_signal(pidfd,signal.SIGKILL);stdout,stderr=child.communicate(timeout=5)\n  poller=select.poll();poller.register(pidfd,select.POLLIN);need(bool(poller.poll(1000))and child.returncode==0,\'own outer swap control must exit0/PIDFD/reap\');control={\'argv\':argv,\'pid\':child.pid,\'returncode\':child.returncode,\'PIDFD_exit_observed\':True,\'actual_child_reaped\':True,\'stdout_bytes\':len(stdout),\'stderr_bytes\':len(stderr),\'stdout_sha256\':hashlib.sha256(stdout).hexdigest(),\'stderr_sha256\':hashlib.sha256(stderr).hexdigest()}\n finally:\n  if child.poll()is None:signal.pidfd_send_signal(pidfd,signal.SIGKILL);child.wait(timeout=5)\n  os.close(pidfd)\n control[\'PIDFD_closed\']=True;after={name:(cg/name).read_text().strip()for name in names};need(after[\'memory.max\']==str(memory_bytes)and after[\'cpu.max\']==str(cpu_percent*1000)+\' 100000\'and after[\'memory.swap.max\']==after[\'memory.swap.current\']==\'0\'and sorted(os.sched_getaffinity(0))==[8,9],\'actual outer budget differs: \'+str({\'before_cap\':before,\'after_cap\':after,\'control\':control}));need(all(int(v)==0 for k,v in map(str.split,after[\'memory.events\'].splitlines())if k in(\'oom\',\'oom_kill\',\'oom_group_kill\')),\'outer unit had OOM\')\n return{\'self_cgroup\':str(cg),\'budget_before_cap\':before,\'budget_after_cap\':after,\'own_cap_control\':control,\'affinity\':[8,9],\'swap_zero_before_business\':True,\'controls_target_self_only\':True,\'historical_outer_budget_upgraded\':False}\n\ndef revalidate_outer(proof):\n cg=Path(proof[\'self_cgroup\']);names=(\'memory.max\',\'memory.swap.max\',\'memory.swap.current\',\'cpu.max\',\'memory.events\');after={name:(cg/name).read_text().strip()for name in names};before=proof[\'budget_after_cap\'];need(all(after[name]==before[name]for name in names if name!=\'memory.events\')and sorted(os.sched_getaffinity(0))==proof[\'affinity\'],\'outer budget changed after business\');need(all(int(v)==0 for k,v in map(str.split,after[\'memory.events\'].splitlines())if k in(\'oom\',\'oom_kill\',\'oom_group_kill\')),\'outer unit had OOM\');return after\n',globals())
need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 1000, 'ordinary principal')
os.umask(0o077)
result = {'schema': 'native643-cuttlefish-ordinary-outer-r1', 'passed': False,
          'Android_starts': 0, 'VM_runs': 0, 'host_policy_loads': 0, 'privileged': False,
          'automatic_retry': False, 'errors': [], 'owned_unit_retired': False,
          'systemd_launcher_pidfd_exit_observed': False}
capture = None
unit_scope = None
expected = None
child = None
try:
    result['outer_budget_before_business']=qualify_outer(1073741824,100)
    expected = json.loads(read(Q / 'preparation.json'))
    need(set(expected) == {'controller', 'request', 'owned_process', 'owned_unit'}, 'fixed preparation roles')
    for key, row in expected.items():
        need(pin(Path(row['path']), read(Path(row['path']))) == row, 'exact admitted input: ' + key)
    helper_scope = {}
    exec(compile(read(Path(expected['owned_process']['path'])), expected['owned_process']['path'], 'exec'), helper_scope)
    capture = helper_scope['capture']
    unit_scope = {}
    exec(compile(read(Path(expected['owned_unit']['path'])), expected['owned_unit']['path'], 'exec'), unit_scope)
    need(not INNER.parent.exists(), 'fresh ordinary build output')
    request = read(Q / 'input.json')
    for row in json.loads(request)['before']:
        need(pin(Path(row['path']), read(Path(row['path']))) == {k: row[k] for k in ('path', 'bytes', 'sha256')},
             'exact original ordinary source/compiler input')
    nonce = os.getrandom(32, os.GRND_NONBLOCK).hex()
    desc = unit_scope['description'](nonce, expected['controller'])
    argv = ['/usr/bin/systemd-run', '--user', '--quiet', '--wait', '--pipe', '--unit', UNIT,
            '--slice=app.slice', '-p', 'Description=' + desc,
            '-p', 'Environment=NATIVE_UNIT_NONCE=' + nonce,
            '-p', 'CPUQuota=200%', '-p', 'CPUAffinity=8-9', '-p', 'MemoryMax=4G', '-p', 'MemorySwapMax=0',
            '-p', 'TasksMax=128', '-p', 'RuntimeMaxSec=3600', '-p', 'TimeoutStopSec=10',
            '-p', 'KillMode=control-group', '--', '/usr/bin/python3', '-I', '-B', str(Q / 'build_normal_tools.py')]
    intent = {'unit': UNIT, 'nonce': nonce, 'description': desc, 'argv': argv,
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'controller': expected['controller'], 'request': expected['request'],
              'privileged': False, 'automatic_retry': False, 'Android_starts': 0, 'VM_runs': 0,
              'host_policy_loads': 0}
    result['intent'] = put('intent.json', jb(intent))
    result['argv'] = argv
    child, stdout, stderr = capture(argv, cwd=B, env=ENV, timeout=3650, input_bytes=request)
    result['systemd_launcher'] = child
    result['returncode'] = child['returncode']
    result['timed_out'] = child['timed_out']
    result['systemd_launcher_pidfd_exit_observed'] = child['retirement_known']
    result['stdout'] = put('normal.stdout', stdout)
    result['stderr'] = put('normal.stderr', stderr)
except BaseException as exc:
    result['errors'].append({'stage': 'launch-or-evidence', 'type': type(exc).__name__, 'message': str(exc)})
finally:
    # This runs after capture has actually reaped its direct child or explicitly
    # recorded UNKNOWN.  Missing INNER or failed log writes cannot bypass it.
    if capture is not None and unit_scope is not None and expected is not None:
        result['unit_reconciliation'] = unit_scope['reconcile'](
            capture, ENV, put, expected['controller'], 'launcher')
        result['owned_unit_retired'] = result['unit_reconciliation']['retired']
        result['observed_owned_cgroup'] = str(unit_scope['CGROUP'])
    else:
        result['unit_reconciliation'] = {'retired': False, 'state': 'UNKNOWN_BEFORE_HELPER_LOAD'}

try:
    raw = read(INNER)
    inner = json.loads(raw)
    result['inner'] = pin(INNER, raw)
    result['inner_passed'] = (inner.get('state') == 'NORMAL643_CUTTLEFISH_ORIGINAL_PROVIDER_QUALIFIED'
        and inner.get('normal_tools_compiled') is True and inner.get('frozen630_unchanged') is True and inner.get('frozen638_unchanged') is True and inner.get('frozen647_unchanged') is True and inner.get('frozen715_unchanged') is True
        and inner.get('all_command_children_retired') is True and inner.get('errors') == []
        and len(inner.get('commands', [])) == inner.get('expected_normal_commands') == 29)
    result['inner_resources'] = inner.get('budget_after')
    need(inner['budget_before']['path'] == result['observed_owned_cgroup'], 'same actual unit cgroup')
    need(inner['owned_unit_started']['invocation_id'] == result['unit_reconciliation']['actual_invocation_id'],
         'inner actual invocation equals independently retired generation')
    result['passed'] = bool(child and child['returncode'] == 0 and child['retirement_known']
        and not child['timed_out'] and not child['forced_termination'] and not child['errors']
        and not result['errors'] and result['inner_passed'] and result['owned_unit_retired']
        and not result['unit_reconciliation']['errors'])
except BaseException as exc:
    result['errors'].append({'stage': 'inner-after-unit-reconciliation', 'type': type(exc).__name__, 'message': str(exc)})
    result['passed'] = False

try:
    if 'outer_budget_before_business'in result:result['outer_budget_after_business']=revalidate_outer(result['outer_budget_before_business'])
    out = put('result.json', jb(result))
    fd = os.open(Q, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({'result': out, 'passed': result['passed'], 'inner': result.get('inner'),
                      'errors': result['errors'], 'Android_starts': 0, 'VM_runs': 0, 'host_policy_loads': 0}), flush=True)
except BaseException as exc:
    result['passed'] = False
    result['errors'].append({'stage': 'final-result-publication', 'type': type(exc).__name__, 'message': str(exc)})
    print(json.dumps({'unpersisted_outer': result, 'passed': False}), flush=True)
sys.exit(0 if result['passed'] else 1)
