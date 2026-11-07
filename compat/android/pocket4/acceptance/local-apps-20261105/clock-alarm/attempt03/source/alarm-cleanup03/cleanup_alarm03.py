#!/usr/bin/python3 -I
"""Remove only the exact, UI-created Alarm03 fixture; never create another alarm."""
from pathlib import Path
import argparse,copy,hashlib,json,os,re,signal,stat,time

ROOT=Path('/home/alex/work/pocket4-clock-alarm-cleanup-20261105-r12-03')
CORE=Path('/home/alex/work/pocket4-clock-alarm-tools-20261105-r12-03/alarm_accept03.py')
CORE_SHA='84a5b6c3e943d8785d7e62690abac0ec60718f6ec58d5f3135af41b20d9307f0'
PRIOR=Path('/home/alex/work/pocket4-clock-alarm-accept-20261105-r12-03/result.json')
PRIOR_SHA='56a64945ceca3fa907b0c8593660b46255ccac3d2df67ec058469f486d2bf100'
SAVED=Path('/home/alex/work/pocket4-clock-alarm-accept-20261105-r12-03/112-cleanup-current-owned-window.json')
SAVED_SHA='060d562014ef1b835c88328679b7762708182c9b307212f5fc9deac057774c38'
PACKAGE='com.android.deskclock'
ALARM_ID=3
INSTANCE_ID=1
WORK_SECONDS=150

def need(ok,why):
    if not ok:raise RuntimeError(why)

def fixed(path,digest,maximum):
    need(path.resolve(strict=True)==path,'CANONICAL_FIXED_FILE_REQUIRED')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_uid==0 and a.st_nlink==1 and 0<a.st_size<=maximum,'FIXED_ROOT_FILE_REQUIRED')
        chunks=[];left=a.st_size
        while left:
            part=os.read(fd,min(left,65536));need(part,'SHORT_FIXED_READ');chunks.append(part);left-=len(part)
        b=os.fstat(fd);need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==
            (b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns),'FIXED_FILE_CHANGED')
        raw=b''.join(chunks);need(hashlib.sha256(raw).hexdigest()==digest,'FIXED_FILE_HASH_CHANGED');return raw
    finally:os.close(fd)

def load_core():
    raw=fixed(CORE,CORE_SHA,128*1024)
    mod=type(os)('owned_alarm03_source');mod.__file__=str(CORE)
    exec(compile(raw,str(CORE),'exec'),mod.__dict__)
    return mod

def bind_prior(prior,saved):
    need(prior['state']=='FAILED' and prior['error']=='RuntimeError: OWNED_ALARM_ROW_CONTAINER_AMBIGUOUS'
        and prior['UI_actions']==5 and prior['creation_native_ACK'] is True
        and prior['native_launched_tasks']==prior['normally_closed_tasks']==[975]
        and prior['owned_task_remaining'] is None
        and all(prior[k] is None for k in ('pending_effect','close_pending','pending_database_effect')),
        'EXACT_KNOWN_COMPLETED_CREATION_REQUIRED')
    claim=prior['phases']['created-unlabelled'];alarm=claim['alarm'];instances=claim['instances']
    need(alarm=={'_id':3,'daysofweek':0,'delete_after_use':0,'enabled':1,'hour':18,'label':'',
        'minutes':54,'ringtone':'content://settings/system/alarm_alert','vibrate':1}
        and len(instances)==1 and instances[0]['_id']==1 and instances[0]['alarm_id']==3,
        'EXACT_SAVED_IMMUTABLE_FIXTURE_REQUIRED')
    nodes=saved['native']['nodes']
    clocks=[n for n in nodes if n.get('package')==PACKAGE and n.get('visible') is True
        and n.get('resource-id')==PACKAGE+':id/digital_clock' and n.get('text')=='6:54\u200aPM'
        and n.get('content-desc')=='6:54\u200aPM']
    need(len(clocks)==1,'EXACT_SAVED_OWNED_CLOCK_REQUIRED')
    return claim,clocks[0]['text']

def make_flow(core):
    class Cleanup(core.Flow):
        def row(self,labelled=False):
            value=self.reader.read()
            need(value['alarm']['_id']==ALARM_ID and value['alarm']['label']=='','EXACT_UNLABELLED_FIXTURE_REQUIRED')
            anchor=self.unique(lambda n:n.get('resource-id')==self.ids['clock']
                and n.get('text')==self.clock_text and n.get('content-desc')==self.clock_text,
                'OWNED_TIME_NODE_NOT_UNIQUE')
            candidates=[]
            for node in self.visible():
                if node.get('class') not in ('android.view.ViewGroup','android.widget.LinearLayout',
                    'android.widget.RelativeLayout','android.widget.FrameLayout'):continue
                if node.get('window_id')!=anchor['window_id'] or not core.contains(node['bounds_array'],anchor['bounds_array']):continue
                children=[n for n in self.visible() if n.get('window_id')==anchor['window_id']
                    and core.contains(node['bounds_array'],n['bounds_array'])]
                clocks=[n for n in children if n.get('resource-id')==self.ids['clock']]
                switches=[n for n in children if n.get('resource-id')==self.ids['onoff']]
                if len(clocks)==len(switches)==1:
                    candidates.append((node,children,clocks[0],switches[0]))
            smallest=[v for v in candidates if not any(w is not v and w[0]['bounds_array']!=v[0]['bounds_array']
                and core.contains(v[0]['bounds_array'],w[0]['bounds_array']) for w in candidates)]
            need(len(smallest)==1,'EXACT_ROW_CONTAINER_NOT_UNIQUE')
            row,children,clock,switch=smallest[0]
            need(core.node_identity(clock)==core.node_identity(anchor)
                and switch.get('checked')==bool(value['alarm']['enabled']),'OWNED_ROW_DB_STATE_DIFFERS')
            return {'container':row,'children':children,'clock':clock,'switch':switch,'anchor':anchor}

        def assert_owned_row_if_main(self,label):
            need(label=='expand-owned' and self.t.last_observation['screenshot']['scope']['activity']==core.MAIN,
                'ONLY_EXACT_OWNED_ROW_EXPANSION_ALLOWED')
            row=self.row(False)
            need(core.node_identity(row['container'])==self.expand_identity,'EXPANSION_LEFT_OWNED_ROW')
            return row

        def remove_fixture(self):
            need(self.pending is None and self.close_pending is None and self.effect_pending is None,
                'UNKNOWN_EFFECT_PREVENTS_CLEANUP')
            self.launch('cleanup-exact-unlabelled-alarm')
            self.reader.read();self.observe('owned-row-before-cleanup');self.settle_notice()
            row=self.row(False);deletes=[n for n in row['children'] if n.get('resource-id')==self.ids['delete']]
            if not deletes:
                arrows=[n for n in row['children'] if n.get('resource-id')==self.ids['arrow']
                    and n.get('content-desc')=='Expand alarm' and n.get('clickable') is True]
                need(len(arrows)==1 and row['container'].get('clickable') is True
                    and 16 in row['container'].get('supported_actions',[])
                    and row['container'].get('content-desc')==self.clock_text+' Alarm',
                    'ACTUAL_COLLAPSED_ROW_EXPAND_ROUTE_REQUIRED')
                self.expand_identity=core.node_identity(row['container'])
                self.native('expand-owned',row['container'])
                row=self.row(False);deletes=[n for n in row['children'] if n.get('resource-id')==self.ids['delete']]
            need(len(deletes)==1 and deletes[0].get('clickable') is True
                and (deletes[0].get('text','').casefold()=='delete'
                    or deletes[0].get('content-desc','').casefold() in ('delete','delete alarm')),
                'FRESH_OWNED_DELETE_NOT_OBSERVED')
            self.native('unlabelled-delete',deletes[0],observe_after=False)
            self.delete_ack=True
            until=min(self.end,time.monotonic()+8)
            while time.monotonic()<until:
                summary=self.reader.summary()
                if summary['template_ids']==[1,2] and summary['instance_ids']==[]:
                    proof=self.reader.deleted();self.complete_effect('delete',proof)
                    self.r['deleted_readback']=proof;self.r['exact_owned_alarm_deleted']=True;return
                time.sleep(.25)
            raise RuntimeError('ACKNOWLEDGED_EXACT_DELETE_NOT_READ_BACK')
    return Cleanup

def own_alert(core,trial,roots,tasks):
    need(851 in tasks and len(tasks-{851})<=1,'ONLY_HOME_AND_POSSIBLE_OWNED_ALERT_ALLOWED')
    if tasks=={851}:return None
    task=next(iter(tasks-{851}));root=roots.get(task)
    need(root and root['display']==root['user']==0 and len(root['children'])==1
        and root['children'][0]['id']==task and root['children'][0]['user']==0,'ONE_ALERT_ROOT_LEAF_REQUIRED')
    component=root['children'][0]['component']
    need(component.split('/')[0]==PACKAGE and core.activity(component.split('/',1)[1])==core.ALERT,
        'EXTRA_TASK_NOT_OWNED_ALARM_ACTIVITY')
    raw=trial.s.android(['/system/bin/dumpsys','activity','activities',PACKAGE],12)
    trial.tx.write_new(ROOT/'possible-alert-activity-private.txt',raw)
    blocks=re.split(r'(?=^\s*\* Hist #\d+: ActivityRecord\{)',raw.decode(),flags=re.M)
    matches=[b for b in blocks if re.search(r'^\s*\* Hist #\d+: ActivityRecord\{[^\n]*\bu0 '
        +re.escape(component)+r' t'+str(task)+r'\b',b)]
    uri='content://com.android.deskclock/instances/1'
    need(len(matches)==1 and re.search(r'Intent \{[^\n]*\bdat='+re.escape(uri)+r'(?:\s|\})',matches[0]),
        'ALERT_NOT_EXACT_SAVED_INSTANCE_URI')
    return {'task':task,'component':component,'uri':uri,'activity_dump_sha256':hashlib.sha256(raw).hexdigest()}

def execute():
    core=load_core();prior=json.loads(fixed(PRIOR,PRIOR_SHA,1024*1024));saved=json.loads(fixed(SAVED,SAVED_SHA,1024*1024))
    claim,clock_text=bind_prior(prior,saved)
    modules={name:core.load(*pair) for name,pair in core.PINS.items()}
    base,model,reader,timer,installer=[modules[k] for k in ('base','model','reader','timer','installer')]
    tx=model.load_session()
    need(model.SOURCE_SHA=='b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
        and tx.ACTIVATION_SHA=='7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
        'EXACT_ORIGINAL_RESOURCE_PROFILE_REQUIRED')
    base.PACKAGE=PACKAGE;base.COMPONENT=PACKAGE+'/.DeskClock';base.ROOT=core.ROOT=ROOT
    base.SOURCE,base.SOURCE_SHA=model.SOURCE,model.SOURCE_SHA
    core.MAX_INPUTS=4;core.WORK_SECONDS=WORK_SECONDS
    result={'state':'FAILED','original_failure_retained':True,'prior_result_sha256':PRIOR_SHA,
        'owned_alarm_id':ALARM_ID,'owned_instance_id':INSTANCE_ID,'source_claim':claim,'target':prior['target'],
        'automatic_retry':False,'maximum_inputs':4,'maximum_new_alarms':0,'SQL_writes':0,'provider_writes':0,
        'global_volume_or_ringtone_changes':0,'started_utc':core.stamp()}
    flow=trial=None;old=signal.signal(signal.SIGALRM,core.deadline)
    try:
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700);signal.setitimer(signal.ITIMER_REAL,WORK_SECONDS)
            with tx.CameraSession(ROOT/'commands') as session:
                result['guard_before']=session.guard();result['identity_before']=model.identity(session)
                need(result['identity_before']==prior['identity_before'],'INSTALLED_CLOCK_IDENTITY_CHANGED')
                apk,_=session.target.read_file(model.APK_PATH,16*1024*1024)
                need(hashlib.sha256(apk).hexdigest()==model.APK_SHA,'CLOCK_APK_CHANGED')
                resources=reader.resource_contract(apk);need(resources==prior['actual_resource_contract'],'CLOCK_RESOURCES_CHANGED')
                native_path=session.android(['/system/bin/pm','path','local.pocket4.actions.v2']).decode().splitlines()
                need(len(native_path)==1 and native_path[0].startswith('package:/data/app/'),'NATIVE_RUNNER_PATH_CHANGED')
                native,_=session.target.read_file(native_path[0][8:],128*1024)
                need(len(native)==20847 and hashlib.sha256(native).hexdigest()==core.NATIVE_SHA,'NATIVE_RUNNER_CHANGED')
                trial=base.Trial(session,tx);roots,tasks=trial.stacks('cleanup-original-taskset')
                prior_tasks=fixed(PRIOR.parent/'commands'/'before-tasks.txt',prior['protected_before']['tasks_sha256'],128*1024)
                prior_roots,prior_ids=base.parse_stacks(prior_tasks.decode())
                need(prior_ids=={851} and all(roots.get(k)==v for k,v in prior_roots.items()),'ORIGINAL_HOME_TASK_CHANGED')
                binding=own_alert(core,trial,roots,tasks)
                need(set(roots)==set(prior_roots)|({binding['task']} if binding else set()),'FOREIGN_ROOT_TASK_PRESENT')
                actual_stacks=trial.stacks
                def initial_stacks(label):
                    if label=='alarm-baseline-tasks':return (copy.deepcopy(prior_roots),set(prior_ids))
                    return actual_stacks(label)
                trial.stacks=initial_stacks
                try:flow=make_flow(core)(trial,base,model,reader,result,resources)
                finally:trial.stacks=actual_stacks
                flow.clock_text=clock_text;flow.create_ack=True;flow.reader.alarm_id=ALARM_ID
                flow.reader.created=copy.deepcopy(claim['alarm']);flow.reader.target=copy.deepcopy(prior['target'])
                flow.reader.instance=copy.deepcopy(claim['instances'][0])
                result['fresh_owned_before']=flow.reader.read();flow.reader.zone_unchanged()
                trial.record('exact-existing-fixture-ownership',{'prior_result_sha256':PRIOR_SHA,
                    'alarm_id':ALARM_ID,'instance_id':INSTANCE_ID,'fresh':result['fresh_owned_before']})
                result['before_runtime']=flow.evidence('before-cleanup')
                try:
                    if binding:
                        flow.alert_task=binding['task'];flow.alert_binding=binding
                        trial.owned=(binding['task'],set(flow.baseline));result['owned_alert_binding']=binding
                        flow.close()
                    flow.remove_fixture();flow.close()
                    result['final_alarm_readback']=flow.reader.deleted()
                    evidence=flow.evidence('after-cleanup')
                    need(evidence['commands']['scheduler']['clock_uid_current_pending_alarm_count']==0
                        and evidence['commands']['notifications']['alarm_record']['present'] is False,
                        'CLOCK_SCHEDULER_OR_NOTIFICATION_REMAINS')
                    result['protected_after']=installer.snapshot(session,tx,model,timer,'after')
                    need(installer.preserved(prior['protected_before'],result['protected_after'],include_preferences=False),
                        'ORIGINAL_PROTECTED_STATE_CHANGED')
                    r,t=flow.topology('cleanup-final-tasks');need(t=={851} and r==flow.baseline_roots,'TASKS_NOT_RESTORED')
                    session.caller_status('cleanup-final-caller');result['guard_after']=session.guard()
                    result.update(state='EXACT_ALARM03_FIXTURE_REMOVED',task_set_restored=True,cleanup_verified=True)
                finally:
                    if flow.pending is None and flow.close_pending is None and flow.effect_pending is None:
                        flow.close()
                    else:result['unknown_retained_read_only']=True
    except BaseException as error:
        result['error']=type(error).__name__+': '+str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        if flow is not None:
            result.update(UI_actions=flow.actions,pending=flow.pending,close_pending=flow.close_pending,
                effect_pending=flow.effect_pending,native_launched_tasks=flow.native_tasks,
                normally_closed_tasks=flow.normal_closed,owned_task_remaining=trial.owned,
                delete_ACK=flow.delete_ack)
        result['finished_utc']=core.stamp()
        if ROOT.is_dir():tx.write_new(ROOT/'result.json',result,alex_readable=True)
        print(json.dumps({k:result.get(k) for k in ('state','error','UI_actions','pending','close_pending','effect_pending',
            'owned_alarm_id','native_launched_tasks','normally_closed_tasks','owned_task_remaining','cleanup_verified')},sort_keys=True))
    return 0 if result.get('cleanup_verified') and not result.get('error') else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if a.execute:raise SystemExit(execute())
    print(json.dumps({'state':'INERT','new_alarms':0,'UI_actions':0,'provider_writes':0}))
