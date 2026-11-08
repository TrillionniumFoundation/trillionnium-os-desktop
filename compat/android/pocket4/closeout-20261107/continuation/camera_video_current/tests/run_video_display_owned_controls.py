#!/usr/bin/python3 -I
"""Isolated actual PID/UID/channel/reaper controls for the video display wrapper.

Display packets, the release observation and business execution are explicit
protocol fixtures. They open no DBus, Pulse, Android, camera or audio device.
The real entry bootstrap, source_packet, outer launch/envelope, SCM credentials,
pidfds, cancellation, lifecycle methods and file/FD retirement remain active.
Every case deliberately fails business qualification; none manufactures a video
success. The finite fixture child only verifies source bytes and the request.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import types

ROOT = Path(__file__).resolve().parents[1]
LIFE = Path('/home/alex/work/pocket4-android-final/framework/runtime_support/capture_lifecycle.py')
LIFE_SHA = '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877'
CASES = ('missing-terminal', 'worker-exit-seven', 'holder-lost', 'wrong-physical-ready')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def ref(path):
    raw = Path(path).read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def fd_table():
    rows = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name)
            value = os.fstat(fd)
            rows[name] = (os.readlink('/proc/self/fd/' + name), os.get_inheritable(fd),
                          value.st_dev, value.st_ino, value.st_mode)
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return rows


def source_snapshot():
    paths = list((ROOT / 'source').glob('*.py')) + list((ROOT / 'display').glob('*.py'))
    paths += [ROOT / 'tools/prepare_camera_video.py', ROOT / 'reviewed-source-inventory.json',
              Path(__file__).resolve(), LIFE]
    result = {}
    keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
            'st_size', 'st_mtime_ns', 'st_ctime_ns')
    for path in paths:
        before = path.lstat()
        row = ref(path)
        after = path.lstat()
        need(all(getattr(before, k) == getattr(after, k) for k in keys), 'control source changed during hash')
        result[str(path)] = {**row, 'identity': {k: getattr(after, k) for k in keys}}
    return result


HOLDER = r'''import json,os,select,socket,sys,time
fd,case,ready_fd=int(sys.argv[1]),sys.argv[2],int(sys.argv[3])
assert os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000
s=socket.socket(fileno=fd)
s.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
device={'by_id':'/explicit-host-fixture/usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0','usb':{'idVendor':'1e08','idProduct':'5520','serial':'JX20250923V2' if case!='wrong-physical-ready' else 'WRONG'},'usb_path':'/explicit-host-fixture/usb3/3-4','HOST_PROTOCOL_FIXTURE_NOT_DEVICE_OBSERVATION':True}
ready={'ready':{'power_save_mode':0,'locked':True},'physical_device':device,'owners':{'fixture':'fixture-owner'},'before':{'power_save_mode':1},'inhibitor':{'path':'/explicit/fixture/inhibitor'}}
sequence=0
def send(kind,value):
 global sequence
 sequence+=1;s.send(json.dumps({'kind':kind,'sequence':sequence,'value':value}).encode())
send('READY',ready);start=time.monotonic()
while time.monotonic()-start<8:
 send('HEARTBEAT',{'power_save_mode':0,'locked':True,'monotonic_ns':time.monotonic_ns()})
 if case=='holder-lost' and select.select([ready_fd],[],[],0)[0]:
  assert os.read(ready_fd,1)==b'R';os.close(ready_fd);s.close();raise SystemExit(17)
 if select.select([s],[],[],.03)[0]:
  data=s.recv(65536)
  if not data:s.close();raise SystemExit(0)
  assert json.loads(data)=={'operation':'release'}
  send('RELEASE',{'success':True,'lease':ready,'HOST_PROTOCOL_FIXTURE_NOT_DISPLAY_RELEASE':True});s.close();raise SystemExit(0)
raise SystemExit(19)
'''

BUSINESS = r'''import argparse,hashlib,json,os,signal,sys,time,types
from pathlib import Path
entry,prep,prep_sha,request,request_sha,fixture_final,case,ready_fd=sys.argv[1:]
ready_fd=int(ready_fd)
scope={'__name__':'actual_source_only_video_entry','__file__':entry}
exec(compile(Path(entry).read_bytes(),entry,'exec'),scope)
c,packet,prep_ref,planner=scope['bootstrap'](argparse.Namespace(preparation=prep,expect_preparation_sha256=prep_sha))
raw=Path(request).read_bytes();assert hashlib.sha256(raw).hexdigest()==request_sha
value=c.parse(raw);assert set(value)=={'base_plan'}
plan=c.parse(c.read_ref(value['base_plan']));c.FINAL=Path(fixture_final)
tasks=planner.source_packet(c,plan,packet);assert set(tasks)=={'camera','player'}
root=Path(plan['case_root']);fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
operator={'pid':os.getpid(),'parent':os.getppid(),'start_ticks':int(fields[19]),'uids':[os.getuid(),os.geteuid(),os.getuid(),os.geteuid()]}
def write(name,body):
 with (root/name).open('x') as h:json.dump(body,h);h.flush();os.fsync(h.fileno())
write('fixture-admission.json',{'operator':operator,'request':value,'source_files':len(packet['files']),'exact_source_packet_verified':True,'runtime_qualified':False,'Main_actions':0,'Android_UI_actions':0})
def cancelled(number,frame):
 write('fixture-cancel.json',{'signal':number,'operator':operator,'Main_actions':0,'Android_UI_actions':0});raise SystemExit(130)
signal.signal(signal.SIGINT,cancelled);signal.signal(signal.SIGTERM,cancelled)
if case=='holder-lost':os.write(ready_fd,b'R');os.close(ready_fd);time.sleep(8);raise SystemExit(23)
raise SystemExit(7 if case=='worker-exit-seven' else 0)
'''

OBSERVER = "import json;print(json.dumps({'inhibitor_removed':True,'entry_mode_matches':True,'owners_unchanged':True,'current':{'locked':True},'HOST_PROTOCOL_FIXTURE_NOT_DISPLAY_OBSERVATION':True}),flush=True)"


def new_plan(module, root, preparation, case_number):
    c, packet, planner = module.VIDEO_CONTEXT
    c.FINAL = root / 'fixture-final'
    module.QUALIFICATION = c.FINAL / 'qualification'
    module.QUALIFICATION.mkdir(parents=True)
    case = module.QUALIFICATION / ('business-camera-video-plan-' + ('%032x' % (case_number + 1)))
    case.mkdir(mode=0o700)
    (case / 'source').mkdir(mode=0o700)
    files = [c.write_new(case / 'source' / Path(r['path']).name, c.read_ref(r), 0o400) for r in packet['files']]
    names = {Path(r['path']).name: r for r in files}
    origins = [preparation] + packet['files'] + packet['origins']
    target, player, helper, limits = planner.named(c, packet, 'camera_profiles.py').profiles('camera_video')
    refs = {}
    for role, profile in (('camera', target), ('player', player)):
        refs[role] = c.write_new(case / ('task-' + role + '.json'), {
            'schema': 'pocket4-final-business-task-source-v1', 'files': files, 'origins': origins,
            'guard_source': names['camera_guard.py'], 'recorder_source': names['camera_flow.py'],
            'target_package': profile['package'], 'target_uid': profile['uid'], 'old_runtime_authority_transferred': False})
    # None actual baseline/identity inputs make this intentionally incapable of
    # real runtime admission. The unchanged source-only gate remains callable.
    plan = {key: None for key in planner.BASE_FIELDS}
    plan.update(schema='pocket4-current-camera-video-plan-v1', kind='camera_video', case_root=str(case),
        source_preparation=preparation, task_source_manifests=refs, target_profile=target,
        player_profile=player, helper_profile=helper, limits=limits, framework_epoch_sha256='e' * 64,
        audio_nonce='13579bdf02468ace', whole_app_business_accepted=False, automatic_retry=False)
    plan_ref = c.write_new(case / 'plan.json', plan)
    request = c.canonical({'schema': 'pocket4-camera-video-display-input-v1', 'plan': plan_ref,
        'source_preparation': preparation, 'automatic_retry': False, 'whole_app_business_accepted': False})
    return c, case, request


def control(root, number, name, preparation):
    module = load(ROOT / 'display/video_display_wrapper.py', 'isolated_video_display_' + str(number))
    module.configure_video_preparation(preparation['path'], preparation['sha256'])
    c, case, raw = new_plan(module, root, preparation, number)
    output = module.QUALIFICATION / ('camera-video-display-' + ('%032x' % (number + 1)))
    output.mkdir(mode=0o700)
    original_write = module.write_json
    def fixture_write(path, value):
        if Path(path) == output / 'result.json':
            need(value['success'] is False and value['case_business_success_verified'] is False
                 and value['runtime_qualified'] is False, 'negative fixture unexpectedly claimed business success')
            value['schema'] = 'pocket4-camera-video-display-negative-host-control-v1'
            value['explicit_fixture_boundaries'] = ['display packets', 'display release observation', 'source-only business child']
            value['actual_video_captured'] = value['actual_display_qualified'] = False
        return original_write(path, value)
    module.write_json = fixture_write
    ready_read, ready_write = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
    class HostSupervisor(module.Supervisor):
        def actor(self, role, argv, pass_fds=(), alex=False):
            self.record.setdefault('fixture_substitutions', []).append({'role': role,
                'original_argv': argv, 'only_private_fixture_backend_changed': True})
            if role == 'holder':
                control_fd = argv[argv.index('--control-fd') + 1]
                argv = ['/usr/bin/python3', '-I', '-B', '-c', HOLDER, control_fd, name, str(ready_read)]
                pass_fds = (*pass_fds, ready_read)
            elif role == 'camera':
                request_path = argv[argv.index('--request') + 1]
                request_sha = argv[argv.index('--expect-request-sha256') + 1]
                argv = ['/usr/bin/python3', '-I', '-B', '-c', BUSINESS,
                    str(ROOT / 'source/camera_entry.py'), preparation['path'], preparation['sha256'],
                    request_path, request_sha, str(c.FINAL), name, str(ready_write)]
                pass_fds = (*pass_fds, ready_write)
            elif role == 'release_observer':
                argv = ['/usr/bin/python3', '-I', '-B', '-c', OBSERVER]
            else:
                raise RuntimeError('unexpected private fixture actor')
            return super().actor(role, argv, pass_fds=pass_fds, alex=alex)
    try:
        owner = HostSupervisor(raw, output)
        code = owner.run()
    finally:
        os.close(ready_read)
        os.close(ready_write)
    value = json.loads((output / 'result.json').read_bytes())
    need(code in (2, 4) and value['success'] is False and value['runtime_qualified'] is False,
         'failure must remain failure')
    record = value['display_lease_wrapper']
    need(record['subreaper']['restored'] is record['subreaper']['final_children_empty'] is True
         and record['adopted_retirement']['owned_tree_cleanup_complete'] is True
         and record['adopted_retirement']['descendants'] == [], 'outer owned tree did not retire')
    for role, item in owner.actors.items():
        need(item['lifecycle']['child_reaped'] is item['lifecycle']['pidfd_closed'] is True,
             'actual private leader/FD remains:' + role)
    if name == 'wrong-physical-ready':
        need('camera' not in owner.actors and not (case / 'fixture-admission.json').exists(),
             'wrong physical READY started the business child')
    else:
        admission = json.loads((case / 'fixture-admission.json').read_bytes())
        need(admission['source_files'] == 29 and admission['exact_source_packet_verified'] is True
             and all(admission['operator'][k] == v for k, v in record['camera_operator'].items()),
             'actual source-only child did not receive the exact current packet/request')
        request = json.loads(Path(record['video_execution_request']['path']).read_bytes())
        need(request == {'base_plan': owner.plan_ref}, 'video execution envelope differs')
        if name == 'holder-lost':
            cancelled = json.loads((case / 'fixture-cancel.json').read_bytes())
            need(cancelled['signal'] == signal.SIGINT and owner.actors['camera']['process'].returncode == 130,
                 'owned acoustic child did not receive graceful cancellation')
        else:
            need(owner.actors['camera']['process'].returncode == (7 if name == 'worker-exit-seven' else 0),
                 'actual private child raw exit changed')
    return {'case': name, 'passed': True, 'actual_owned_actors': len(owner.actors),
            'outer_returncode': code, 'result': ref(output / 'result.json'),
            'actual_Main_actions': 0, 'actual_DBus_actions': 0, 'actual_audio_stream_actions': 0,
            'runtime_qualified': False, 'fixture_success_not_runtime_credit': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    need(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'private root host controls required')
    need(ref(LIFE)['sha256'] == LIFE_SHA, 'original lifecycle bytes required')
    cgrows = Path('/proc/self/cgroup').read_text().splitlines()
    need(len(cgrows) == 1 and cgrows[0].startswith('0::/') and 'hepta-runtime-job-' in cgrows[0],
         'own bounded host job cgroup required')
    cgroup = Path('/sys/fs/cgroup') / cgrows[0][3:].lstrip('/')
    limits = {k: (cgroup / k).read_text().strip() for k in ('cpu.max', 'memory.max', 'memory.swap.max', 'pids.max')}
    need(limits == {'cpu.max': '50000 100000', 'memory.max': '536870912',
                    'memory.swap.max': '0', 'pids.max': '64'}
         and os.sched_getaffinity(0) == {19} and os.getpriority(os.PRIO_PROCESS, 0) == 10,
         'fixed private host controls resource budget required')
    before_sources = source_snapshot()
    root = args.output.resolve()
    root.mkdir(mode=0o700)
    life = load(LIFE, 'actual_owned_display_lifecycle')
    warm = life.OwnChildReaper(protected_pids=(os.getpid(), os.getppid()))
    warm.flag()
    before = fd_table()
    builder = load(ROOT / 'tools/prepare_camera_video.py', 'actual_source_preparation_builder')
    prepared = builder.prepare(ROOT / 'source', ROOT / 'reviewed-source-inventory.json',
                               builder.INVENTORY_SHA256, root / 'prepared')
    rows = []
    for number, name in enumerate(CASES):
        case_root = root / name
        case_root.mkdir(mode=0o700)
        rows.append(control(case_root, number, name, prepared['preparation']))
    after = fd_table()
    after_sources = source_snapshot()
    resources = {k: (cgroup / k).read_text().strip() for k in ('memory.peak', 'memory.events', 'memory.swap.current')}
    events = dict(line.split() for line in resources['memory.events'].splitlines())
    need(before == after and warm.children() == [] and before_sources == after_sources,
         'whole display controls leaked FD/child or changed source')
    need(resources['memory.swap.current'] == '0' and all(events[k] == '0' for k in ('oom', 'oom_kill', 'oom_group_kill')),
         'host controls OOM or swap')
    result = {'schema': 'pocket4-camera-video-display-owned-host-controls-v1',
        'state': 'FOUR_ACTUAL_OWNED_NEGATIVE_BOUNDARIES_PASSED', 'passed': True, 'cases': rows,
        'FD_before': before, 'FD_after': after, 'remaining_children': [],
        'sources_before': before_sources, 'sources_after': after_sources, 'limits': limits, 'resource_after': resources,
        'source_files': 29, 'source_preparation': prepared['preparation'],
        'explicit_fixture_boundaries': ['display protocol backend', 'independent display observation', 'source-only business child'],
        'actual_UID1000_holder_credentials_checked': True,
        'actual_request_source_packet_and_owned_child_checked': True,
        'actual_video_captured': False, 'actual_display_qualified': False,
        'Main_actions': 0, 'DBus_actions': 0, 'Android_UI_actions': 0, 'actual_audio_stream_actions': 0,
        'runtime_qualified': False, 'whole_app_business_accepted': False}
    with (root / 'result.json').open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'passed': True, 'result': ref(root / 'result.json')}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
