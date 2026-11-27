"""Bounded read-only UID/track/HAL and host stream observations. Never records audio."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,re,time

UID=10063
ROW=re.compile(r'^\s*(?:[A-Z]\s+)?(?P<id>\d+)\s+(?P<active>yes|no)\s+(?P<pid>\d+)\s*/\s*(?P<uid>\d+)\s+(?P<session>\d+)\s+(?P<rest>.+)$')


def need(ok,why):
    if not ok:raise RuntimeError(why)


def parse_flinger(raw):
    """Read only live track tables; historical AT::add lines are never active tracks."""
    text=raw.decode('utf-8','strict');outputs=[]
    for block in re.split(r'(?=^Output thread )',text,flags=re.M)[1:]:
        name=block.splitlines()[0];body=block.split('  Local log:',1)[0]
        starts=list(re.finditer(r'^  (\d+) Tracks of which (\d+) are active\n',body,re.M))
        need(len(starts)<=1,'LIVE_TRACK_TABLE_AMBIGUOUS')
        if not starts:continue
        section=body[starts[0].end():].split('Effect Chains',1)[0].splitlines()
        need(section and 'Client(pid/uid)' in section[0] and 'Server FrmCnt' in section[0],'LIVE_TRACK_COLUMNS_CHANGED')
        tracks=[]
        for line in section[1:]:
            m=ROW.fullmatch(line)
            if not m:
                need(not line.strip() or re.fullmatch(r'\s*\d+\s*',line),'UNPARSED_LIVE_TRACK_ROW')
                continue
            fields={k:int(m[k]) for k in ('id','pid','uid','session')}
            fields.update(active=m['active']=='yes',raw=line);tracks.append(fields)
        need(len(tracks)==int(starts[0][1]) and sum(t['active'] for t in tracks)==int(starts[0][2]),'LIVE_TRACK_COUNT_MISMATCH')
        frames=re.findall(r'^  Frames written: (\d+)$',body,re.M)
        writes=re.findall(r'^  Total writes: (\d+)$',body,re.M)
        need(len(frames)==len(writes)==1,'OUTPUT_FRAME_COUNTERS_AMBIGUOUS')
        powers=[]
        segment=body.split('Signal power history (resolution: 1000.0 ms):',1)
        if len(segment)==2:
            segment=segment[1].split('Signal power history',1)[0]
            for line in segment.splitlines():
                m=re.fullmatch(r'\s*(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}): \[([^]]+)\] sum\([^)]*\)',line)
                if m:
                    values=m[2].split();need(all(re.fullmatch(r'-?(?:\d+(?:\.\d+)?|inf)',v) for v in values),'HAL_POWER_SCHEMA')
                    powers.append({'timestamp':m[1],'levels_db':values,'raw':line})
        outputs.append({'name':name,'frames_written':int(frames[0]),'total_writes':int(writes[0]),
            'master_muted':'  Master mute: off' not in body,'tracks':tracks,'power_1s':powers})
    need(outputs,'NO_LIVE_AUDIO_OUTPUT_TABLE')
    return outputs


# Working audio mapping is limited to the authenticated Main payload group.
# A parser result is comparison data only; the actual source lease stays in Rust.
from contextlib import contextmanager
import stat

_WORKING_PAYLOAD='/system.slice/droidloom-production.service/cell-u1000/payload'
_WORKING_PID_MAX=32768  # Existing normal Main pids.max contract.
_WORKING_PID_BYTES=12*_WORKING_PID_MAX
_WORKING_F9=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def _working_f9(fd):
    return tuple(getattr(os.fstat(fd),key) for key in _WORKING_F9)

def _working_group_path(raw):
    need(type(raw) is bytes and 0<len(raw)<=4096,'BOUNDED_ACTUAL_MAIN_CGROUP_RECORD')
    lines=raw.decode('ascii','strict').splitlines()
    need(len(lines)==1 and lines[0].startswith('0::'),'EXACT_UNIFIED_MAIN_CGROUP_RECORD')
    path=lines[0][3:]
    need((path==_WORKING_PAYLOAD or path.startswith(_WORKING_PAYLOAD+'/')) and
         all(p and p not in ('.','..') for p in path.split('/')[1:]) and
         len(path.split('/'))<=16,'ACTUAL_MAIN_MUST_REMAIN_IN_FIXED_PAYLOAD_TREE')
    return path

def _working_pid_table(raw):
    need(type(raw) is bytes and len(raw)<=_WORKING_PID_BYTES,'BOUNDED_ACTUAL_MAIN_PID_TABLE')
    lines=raw.decode('ascii','strict').splitlines()
    need(0<len(lines)<=_WORKING_PID_MAX and
         all(v.isdecimal() and 1<=len(v)<=10 and 1<int(v)<2**31 for v in lines),
         'ACTUAL_MAIN_PID_TABLE_GRAMMAR')
    values=tuple(int(v) for v in lines)
    need(len(values)==len(set(values)),'ACTUAL_MAIN_PID_TABLE_HAS_DUPLICATES')
    return values

@contextmanager
def _audio_process_roster(session,namespace,original_end):
    live=session.baseline.live
    if live.working_runtime_root() is None:
        # The historical single-application route retains its original scan.
        yield Path('/proc').iterdir()
        return
    need(live.working_native_source is not None and live.working_preparation_owner is None and
         live.core['application']['package']=='com.android.deskclock',
         'CLOCK_AUDIO_NEEDS_ACTUAL_WORKING_CHILD_SOURCE')
    need(time.monotonic()<original_end<=live.deadline,'ORIGINAL_AUDIO_MAPPING_DEADLINE')
    live.guard()
    main=live.core['main']
    namespaces=[r['inode'] for r in main['framework_namespaces'] if r['name']=='pid']
    need(namespaces==[namespace],'AUDIO_MAPPING_REQUIRES_ACTUAL_MAIN_PID_NAMESPACE')
    pids=[main[role]['host_pid'] for role in ('init','zygote','framework')]
    need(len(set(pids))==3 and all(type(pid) is int and 1<pid<2**31 for pid in pids),
         'ACTUAL_MAIN_ROLE_PID_ROSTER')
    held=[];groups=[]
    def remember(fd,path):
        held.append((fd,path,_working_f9(fd)))
        return fd
    def bounded(fd,maximum):
        raw=bytearray()
        while True:
            need(time.monotonic()<original_end,'AUDIO_PROCESS_MAPPING_BUDGET')
            part=os.read(fd,min(65536,maximum+1-len(raw)))
            if not part:return bytes(raw)
            raw.extend(part);need(len(raw)<=maximum,'AUDIO_PROCESS_MAPPING_READ_BOUND')
    try:
        for pid in pids:
            path=Path('/proc')/str(pid)/'cgroup'
            fd=remember(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC),path)
            groups.append(_working_group_path(bounded(fd,4096)))
        need(groups[0]==groups[1]==groups[2],'ACTUAL_MAIN_ROLES_NEED_ONE_SOURCE_REVIEWED_PAYLOAD_GROUP')
        path=Path('/sys/fs/cgroup')
        parent=remember(os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC),path)
        for name in groups[0].split('/')[1:]:
            path=path/name
            parent=remember(os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,
                                    dir_fd=parent),path)
        # No guessed recursive production-service walk. A new nested layout
        # requires source review before it may participate in this mapping.
        with os.scandir(parent) as entries:
            need(not any(row.is_dir(follow_symlinks=False) for row in entries),
                 'NESTED_PAYLOAD_GROUP_REQUIRES_EXPLICIT_SOURCE_REVIEW')
        table_path=path/'cgroup.procs'
        fd=remember(os.open('cgroup.procs',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,
                            dir_fd=parent),table_path)
        members=_working_pid_table(bounded(fd,_WORKING_PID_BYTES))
        need(set(pids)<=set(members),'CURRENT_MAIN_ROLES_MUST_BE_ACTUAL_PAYLOAD_MEMBERS')
        need(time.monotonic()<original_end,'AUDIO_PROCESS_MAPPING_BUDGET')
        yield tuple(Path('/proc')/str(pid) for pid in members)
        need(time.monotonic()<original_end,'AUDIO_PROCESS_MAPPING_BUDGET')
        live.guard()
        for fd,path,before in held:
            need(_working_f9(fd)==before==tuple(getattr(path.lstat(),k) for k in _WORKING_F9),
                 'HELD_ACTUAL_AUDIO_PAYLOAD_CUSTODY_CHANGED')
        need(time.monotonic()<original_end,'AUDIO_PROCESS_MAPPING_BUDGET')
    finally:
        for fd,path,before in reversed(held):os.close(fd)

class Observe:
    def __init__(self,session,tx,out):
        self.s,self.tx,self.out=session,tx,Path(out);self.out.mkdir(mode=0o700)
        self.baseline=None;self.calls=0

    def sample(self,label):
        self.s.guard();raw=self.s.android(['/system/bin/dumpsys','media.audio_flinger'],15)
        self.tx.write_new(self.out/(label+'-audio-flinger-private.txt'),raw)
        parsed=parse_flinger(raw)
        result={'observed_utc':datetime.now(timezone.utc).isoformat(),'flinger_sha256':hashlib.sha256(raw).hexdigest(),
            'outputs':parsed,'host_streams':[],'recorded_audio_bytes':0,'microphone_access':False}
        pulse=Path('/run/user/1000/pulse/native');pactl=Path('/usr/bin/pactl')
        if pulse.exists() and pactl.exists():
            # Reuse the existing reviewed no-autospawn config; no server may start.
            config=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/inputs/ea857fc2d093b8bd4b2927102c3a6a9b32d699e6fe98bc3e49bf821fee6d8511/pulse-client.conf')
            self.tx.read_regular(config,hashlib.sha256(b'autospawn = no\ndefault-server = unix:/run/user/1000/pulse/native\n').hexdigest())
            prefix=[self.tx.RUNUSER,'-u','alex','--','/usr/bin/env','PULSE_CLIENTCONFIG='+str(config),
                'PULSE_SERVER=unix:/run/user/1000/pulse/native','XDG_RUNTIME_DIR=/run/user/1000',str(pactl.resolve(strict=True))]
            self.calls+=1;reply=self.s.run_host('clock-audio-stream-'+str(self.calls),prefix+['--format=json','list','sink-inputs'],10)
            result['host_stream_query']={k:reply[k] for k in ('rc','joined','timed_out','guard_after')}
            if reply['rc']==0:
                streams=json.loads(reply['stdout']);need(isinstance(streams,list) and len(streams)<=256,'HOST_STREAM_COUNT')
                candidates={int(p['properties']['application.process.id']) for p in streams
                    if isinstance(p.get('properties',{}).get('application.process.id'),str)
                    and p['properties']['application.process.id'].isdecimal()}
                namespace=os.fstat(self.s.target.namespaces['pid']).st_ino;matches={};deadline=time.monotonic()+3
                with _audio_process_roster(self.s,namespace,deadline) as actual_processes:
                    for proc in actual_processes:
                        if not proc.name.isdecimal():continue
                        need(time.monotonic()<deadline,'AUDIO_PROCESS_MAPPING_BUDGET')
                        try:
                            if (proc/'ns/pid').stat().st_ino!=namespace:continue
                            status=(proc/'status').read_text();ns=re.search(r'^NSpid:\s+([0-9 \t]+)$',status,re.M)
                            if ns is None:continue
                            inside=int(ns[1].split()[-1]);host=int(proc.name)
                            keys=[v for v in candidates if v in (inside,host)]
                            if not keys:continue
                            identity=self.s.epoch.process_identity(host)
                            if identity['namespaces']['pid']!='pid:['+str(namespace)+']':continue
                            for key in keys:matches.setdefault(key,[]).append(identity)
                        except (FileNotFoundError,ProcessLookupError):continue
                for item in streams:
                    props=item.get('properties',{});ident=props.get('application.process.id','')
                    owned=matches.get(int(ident),[]) if isinstance(ident,str) and ident.isdecimal() else []
                    if len(owned)!=1:continue
                    fields={k:item.get(k) for k in ('index','client','sink','corked','mute','sample_specification','channel_map','buffer_latency_usec','sink_latency_usec')}
                    fields['process_identity']=owned[0]
                    fields['properties']={k:props.get(k) for k in ('application.process.id','application.process.binary','application.name','object.serial','node.name')}
                    result['host_streams'].append(fields)
                result['other_sink_input_count']=len(streams)-len(result['host_streams'])
        self.s.guard();self.tx.write_new(self.out/(label+'.json'),result);return result

    def start(self):self.baseline=self.sample('before-timer')

    def expired(self,verify_owned,due_ms,uptime):
        need(self.baseline is not None,'AUDIO_BASELINE_REQUIRED');samples=[]
        basis_ms=uptime();basis=datetime.now(timezone.utc)
        due_seconds=basis.timestamp()+(due_ms-basis_ms)/1000
        for index in range(3):
            verify_owned();samples.append(self.sample('expired-'+str(index)));verify_owned()
            if index<2:time.sleep(.45)
        bound=[]
        for sample in samples:
            active=[(out,t) for out in sample['outputs'] for t in out['tracks'] if t['active']]
            sole_clock=bool(active) and all(t['uid']==UID for _,t in active)
            if not sole_clock:continue
            for output,track in active:
                if output['master_muted']:continue
                fresh=[]
                for power in output['power_1s']:
                    stamp=datetime.strptime(str(basis.year)+'-'+power['timestamp'],'%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc).timestamp()
                    if due_seconds-1<=stamp<=basis.timestamp()+20 and any(float(x)>-80 for x in power['levels_db']):fresh.append(power)
                bound.append({'output':output['name'],'track':track,'frames_written':output['frames_written'],
                    'total_writes':output['total_writes'],'fresh_nonzero_power':fresh})
        progress=any(a['output']==b['output'] and a['track']['id']==b['track']['id']
            and a['track']['session']==b['track']['session'] and b['frames_written']>a['frames_written']
            and b['total_writes']>a['total_writes'] for i,a in enumerate(bound) for b in bound[i+1:])
        result={'owned_expiry_due_ms':due_ms,'basis_device_uptime_ms':basis_ms,'basis_UTC':basis.isoformat(),
            'clock_UID_active_track_and_output_progress':progress,
            'nonzero_HAL_power_during_sole_Clock_active_output':progress and any(x['fresh_nonzero_power'] for x in bound),
            'bound_output_samples':bound,'main_namespace_host_stream_samples':[s['host_streams'] for s in samples],
            'recorded_audio_bytes':0,'microphone_access':False,'physical_speaker_audibility_verified':False,
            'audio_settings_changes':0,'engine_qualification':False}
        self.tx.write_new(self.out/'expiry-audio-evidence.json',result);return result
