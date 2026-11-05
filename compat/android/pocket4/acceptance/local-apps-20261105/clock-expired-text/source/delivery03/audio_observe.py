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
            config=Path('/home/alex/work/pocket4-clock-delivery-contract-20261105-r12-03/pulse-client.conf')
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
                for proc in Path('/proc').iterdir():
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
