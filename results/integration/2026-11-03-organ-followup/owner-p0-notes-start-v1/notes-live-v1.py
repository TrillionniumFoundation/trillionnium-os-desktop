import hashlib,json,os,select,stat,subprocess,sys,time,traceback,urllib.request
from pathlib import Path

assert os.getuid()==os.geteuid()==0
os.umask(0o077)
BASE=Path('/data/trill-organ-owner-20261103/root-fd-v5-tests-package-01')
OUT=BASE/'notes-live-fd-a39-v1'
RELEASE=Path('/opt/trill-organ-20261103/releases/fd8d56c52b97-053cc1957b40')
CONFIG=Path('/root/trill-organ-owner-20261103/initialize.json')
PREFIX=Path('/var/lib/trill/o1103n1')
ROOT=RELEASE/'bin/hepta-desktop-root'
GUI_SOURCE=sys.argv[1]
EXPECTED='Hepta 原 owner Notes 验收 20261103 · fd8d56c5/a39a0871'
EXPECTED_SHA=hashlib.sha256(EXPECTED.encode()).hexdigest()
assert not OUT.exists() and not PREFIX.exists()
OUT.mkdir(mode=0o755)
os.chmod(OUT,0o755)
GUI=OUT/'gui';GUI.mkdir(mode=0o700);os.chown(GUI,1000,1000)
config=json.loads(CONFIG.read_bytes())
report={'schema':'trill.audit.original-notes-live.v1','status':'running','started_unix_ms':int(time.time()*1000),
        'desktop_commit':'fd8d56c52b971c2d5d0e6430f296803b43ef60a3','hepta_commit':'a39a0871d9601ffccb5e0d95d8f39d54b3a63360',
        'release':str(RELEASE),'config_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'scope':'Original installed Root, real logind, original user GUI and original finite model/Notes flow in a private mount namespace',
        'lifetime_ms':300000,'long_running_production_qualified':False,'physical_keyboard_qualified':False,
        'requested_notes_text':EXPECTED,'requested_notes_sha256':EXPECTED_SHA,'phases':[],'roots':[],'held_processes':[],
        'write_prompts_sent':0,'model_effect_result_qualified':False,'app_only_readback_qualified':False,'same_boot_recovery_qualified':False}
roots=[];holds=[];streams=[];active_shell=None;active_root=None;seed=None;original_target=None;original_receipt=None;writer_expiry=None
overall_end=time.monotonic()+390

def now():return int(time.time()*1000)
def write(name,data):
    raw=data if isinstance(data,bytes) else (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()
    path=OUT/name;tmp=path.with_name(path.name+'.partial')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.chmod(tmp,0o644);os.replace(tmp,path)
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def save():write('result.json',report)
def phase(name,**values):report['phases'].append({'name':name,'unix_ms':now(),**values});save()
def bounded(path,limit=65536):
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=limit
        data=f.read(limit+1);assert len(data)<=limit
        after=os.fstat(f.fileno());assert (s.st_ino,s.st_size,s.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
    return data
def exited(hold):
    p=select.poll();p.register(hold['fd'],select.POLLIN);return bool(p.poll(0))
def proc_meta(pid):
    fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    status=Path('/proc/'+str(pid)+'/status').read_text().splitlines()
    uid=next(x for x in status if x.startswith('Uid:')).split()[1:]
    gid=next(x for x in status if x.startswith('Gid:')).split()[1:]
    return {'pid':pid,'parent_pid':int(fields[1]),'start_ticks':int(fields[19]),'uids':[int(x) for x in uid],
            'gids':[int(x) for x in gid],'executable':str(Path('/proc/'+str(pid)+'/exe').resolve(strict=True))}
def hold_actual_child(parent,executable,label):
    # Discover the live direct child through the kernel, never a disk PID.
    candidates=[]
    children=Path('/proc/'+str(parent)+'/task/'+str(parent)+'/children').read_text().split()
    for raw in children:
        try:
            observed=proc_meta(int(raw))
            if observed['executable']==str(executable) and observed['parent_pid']==parent:candidates.append(observed)
        except (FileNotFoundError,ProcessLookupError):pass
    if not candidates:return None
    assert len(candidates)==1
    before=candidates[0];fd=os.pidfd_open(before['pid']);after=proc_meta(before['pid'])
    assert before==after and before['uids']==[1000]*4 and before['gids']==[1000]*4
    hold={**before,'fd':fd,'label':label};assert not exited(hold)
    holds.append(hold);report['held_processes'].append(before|{'label':label,'anchor':'live kernel parent-child relation, retained pidfd, pre/post birth and installed exe'})
    save();return hold
def wait(probe,label,seconds,root=None):
    end=min(overall_end,time.monotonic()+seconds);last=None
    while time.monotonic()<end:
        if root is not None and root.poll() is not None:raise RuntimeError(label+': original Root exited '+str(root.returncode))
        try:
            value=probe()
            if value:return value
        except (FileNotFoundError,PermissionError,AssertionError,json.JSONDecodeError) as e:last=repr(e)
        time.sleep(.1)
    raise RuntimeError(label+' timed out; last='+str(last))
def spawn_root(mode,operation=None):
    args=[str(ROOT),mode,'--config',str(CONFIG)]
    if operation is not None:args+=['--operation-id',operation]
    index=len(roots);stdout=(OUT/f'root-{index}-{mode}.stdout.log').open('xb');stderr=(OUT/f'root-{index}-{mode}.stderr.log').open('xb')
    streams.extend([stdout,stderr]);p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
    roots.append(p);report['roots'].append({'mode':mode,'argv':args,'pid':p.pid,'started_unix_ms':now()});save();return p
def gui(hold,label,mode='send',prompt=None):
    assert not exited(hold)
    request={k:hold[k] for k in ('pid','parent_pid','start_ticks','executable')}
    request.update(pidfd=hold['fd'],mode=mode,output=str(GUI/(label+'.json')))
    if prompt is not None:request['prompt']=prompt
    # Persist this one operator intent before crossing the GUI action boundary.
    phase(label+'_intent',mode=mode,pid=hold['pid'],prompt=prompt)
    env={'PATH':'/usr/bin:/bin','HOME':str(PREFIX/'u/home'),**config['environment']}
    r=subprocess.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/python3.12','-B','-c',GUI_SOURCE,json.dumps(request,ensure_ascii=False)],
                     env=env,pass_fds=(hold['fd'],),capture_output=True,timeout=45)
    write(label+'.stdout.log',r.stdout);write(label+'.stderr.log',r.stderr)
    value=json.loads(bounded(GUI/(label+'.json'),32768));phase(label,exit_code=r.returncode,gui_receipt=value)
    assert r.returncode==0 and value['passed']
    return value
def setup(root,admin,label):
    composition=wait(lambda:json.loads(bounded(admin/'actual-composition.json')),'original composition',45,root)
    assert composition['bootstrap_model_turn_sent'] is False
    session=wait(lambda:hold_actual_child(root.pid,RELEASE/'desktop/bin/trill-session',label+'-session'),'actual Session child',3,root)
    agent=wait(lambda:hold_actual_child(root.pid,RELEASE/'bin/codex-hepta-agentd',label+'-agentd'),'actual Agentd child',3,root)
    shell=wait(lambda:hold_actual_child(root.pid,RELEASE/'desktop/bin/trill-shell',label+'-shell'),'actual original Shell child',20,root)
    app=wait(lambda:hold_actual_child(session['pid'],RELEASE/'desktop/bin/trill-app-window',label+'-notes-app'),'actual reserved Notes child',10,root)
    human=json.loads(bounded(admin/'actual-human-provider-receipt.json'))
    assert human['human_source']=='actual_local_systemd_logind_session' and human['source_uid']==1000
    registrations=list(admin.glob('native-ui-'+str(root.pid)+'-*.json'));assert len(registrations)==1
    native=json.loads(bounded(registrations[0]));assert native['peer_pid']==shell['pid'] and native['process_start_ticks']==shell['start_ticks']
    write(label+'-composition.json',composition);write(label+'-human-provider.json',human)
    phase(label+'_actual_composition',session_pid=session['pid'],agent_pid=agent['pid'],shell_pid=shell['pid'],app_pid=app['pid'],target=composition['notes_target'],human_source=human['human_source'])
    return composition,session,agent,shell,app
def admin_observe(admin,label):
    args=[str(ROOT),'admin','--instance-file',str(admin/'root-admin-instance.json'),'observe']
    r=subprocess.run(args,capture_output=True,timeout=5)
    write(label+'.stdout.json',r.stdout);write(label+'.stderr.log',r.stderr)
    assert r.returncode==0
    value=json.loads(r.stdout);assert value['status']=='observed'
    physical=value['observation']['physical_current'];assert isinstance(physical,dict) and physical['material_bytes']>0 and physical['current']
    phase(label,observation=value)
    return value

def rollout():
    path=Path(seed['rollout_path']);assert path.is_relative_to(Path(seed['codex_home'])) and path.is_relative_to(PREFIX)
    raw=bounded(path,2*1024*1024);lines=raw.splitlines();records=[]
    for index,line in enumerate(lines):
        try:records.append((index,json.loads(line)))
        except json.JSONDecodeError:assert index==len(lines)-1
    return raw,records
def original_outputs(records):
    calls={};outputs=[];completed=[]
    for line,record in records:
        payload=record.get('payload',{})
        if not isinstance(payload,dict):continue
        if record.get('type')=='event_msg' and payload.get('type') in ('task_complete','turn_complete'):completed.append(line)
        if record.get('type')!='response_item':continue
        kind=payload.get('type')
        if kind in ('function_call','custom_tool_call'):
            name=payload.get('name','').split('.')[-1]
            if name in ('hepta_notes_state','hepta_notes_replace','hepta_notes_status'):
                calls[payload['call_id']]={'line':line,'tool':name,'item':payload}
        if kind=='message' and payload.get('role')=='assistant' and payload.get('phase')=='final':completed.append(line)
        if kind not in ('function_call_output','custom_tool_call_output'):continue
        call=calls.get(payload.get('call_id'))
        if call is None:continue
        output=payload.get('output')
        texts=[output] if isinstance(output,str) else [p.get('text') for p in output or [] if isinstance(p,dict) and p.get('type')=='input_text']
        for text in texts:
            if not isinstance(text,str) or len(text)>65536:continue
            try:value=json.loads(text)
            except json.JSONDecodeError:continue
            if isinstance(value,dict):outputs.append({'line':line,'call_id':payload['call_id'],'tool':call['tool'],'value':value,'original_response_item':payload})
    return calls,outputs,completed
def document():
    t=original_target;path=PREFIX/'u/notes'/(t['session_instance']+'-'+str(t['task_id'])+'-'+t['incarnation'])/'document.json'
    raw=bounded(path,16384);value=json.loads(raw)
    assert value['target']==t
    return raw,value
def qualified(after,label,recovered=False):
    raw,records=rollout();calls,outputs,completed=original_outputs(records)
    recent=[x for x in outputs if x['line']>=after]
    statuses=[];states=[]
    for output in recent:
        value=output['value'];human=value.get('human_input')
        if not isinstance(human,dict) or not human.get('authbus_client_id') or not human.get('principal_id'):continue
        if output['tool']=='hepta_notes_status' and value.get('state')=='Committed' and value.get('original_target')==original_target:
            if not isinstance(value.get('receipt_utf8'),str):continue
            receipt=json.loads(value['receipt_utf8']);applied=receipt.get('result',{})
            if receipt.get('target')!=original_target or applied.get('status')!='applied' or applied.get('previous_revision')!=0 or applied.get('revision')!=1 or applied.get('text_sha256')!=EXPECTED_SHA:continue
            if original_receipt is not None and value['receipt_utf8']!=original_receipt:continue
            provenance=value.get('provenance',{})
            if provenance.get('thread_id')!=seed['thread_id'] or provenance.get('app_server_session_id')!=seed['app_server_session_id']:continue
            statuses.append(output)
        if output['tool']=='hepta_notes_state' and isinstance(value.get('document'),dict):
            current=value['document']
            if recovered or (current.get('target')==original_target and current.get('revision')==1 and current.get('text_sha256')==EXPECTED_SHA):states.append(output)
    if not statuses or not states:return None
    latest=max(statuses[-1]['line'],states[-1]['line'])
    if not any(x>latest for x in completed):return None
    raw_document,saved=document()
    assert saved['text']==EXPECTED and saved['revision']==1
    new_writes=[c for c in calls.values() if c['tool']=='hepta_notes_replace' and c['line']>=after]
    if label!='initial':assert not new_writes,'read-only reconciliation turn attempted another replace'
    result={'status_tool':statuses[-1],'state_tool':states[-1],'document':saved,
            'document_artifact':write(label+'-document.json',raw_document),
            'rollout_artifact':write(label+'-rollout.jsonl',raw),'replace_calls_in_stage':new_writes,
            'completion_after_tool_results':True,'scope':'Original Core function-call-output items matched to exact tool call IDs; assistant prose is excluded from effect evidence'}
    write(label+'-qualified-evidence.json',result)
    return result
def line_count():return len(rollout()[1])
def wait_expiry_exit(root,label,expiry):
    timeout=max(1,min(225,expiry/1000-time.time()+20))
    code=root.wait(timeout=timeout)
    phase(label,root_pid=root.pid,exit_code=code,writer_expiry_unix_ms=expiry,returned_before_writer_expiry=now()<expiry,termination='Root returned after normal owned Shell close; no operator signal to Root or Agentd')
    report['roots'][roots.index(root)].update(exit_code=code,finished_unix_ms=now());save()

try:
    prepared=json.loads(bounded(BASE/'notes-prepare-v1.json'))
    assert prepared['status']=='prepared' and config['lifetime_ms']==300000
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:18083/v1/models',timeout=5) as response:
        models=response.read(65537);assert len(models)<=65536
        assert any(item.get('id')=='qwen38-flash-next-uc' for item in json.loads(models).get('data',[]))
    assert hashlib.sha256(bounded(ROOT,128*1024*1024)).hexdigest()=='d22d265d8f6414342831eea7fef843212af95e08a90ca6467aca538aa15a3f0f'
    phase('initializing_original_root',private_mount_namespace=os.readlink('/proc/self/ns/mnt'))
    active_root=spawn_root('initialize')
    comp,session,agent,active_shell,app=setup(active_root,PREFIX/'admin','initial')
    seed=comp['original_thread_seed'];original_target=comp['notes_target']
    report['thread_seed']=seed;report['original_target']=original_target;save()
    initial_raw,initial_doc=document();assert initial_doc['text']=='' and initial_doc['revision']==0
    write('empty-original-document.json',initial_raw)
    before=line_count()
    prompt='请把这次新打开的 Notes 文档完整替换为这个 JSON 字符串的解码内容，不附加字符或换行：'+json.dumps(EXPECTED,ensure_ascii=False)+'\n先用 hepta_notes_state 读取版本，只调用一次 hepta_notes_replace；然后调用 hepta_notes_status（selector.kind=latest_original_replace）及 hepta_notes_state 独立核对。未知或失败只读查询，禁止再提交写入。请报告原 operation_id、target、revision 和内容 SHA256。'
    report['write_prompts_sent']=1;save()
    gui(active_shell,'initial-write-prompt',prompt=prompt)
    effect=wait(lambda:qualified(before,'initial'),'actual original writer terminal and independent Notes readback',90,active_root)
    original_receipt=effect['status_tool']['value']['receipt_utf8'];operation=effect['status_tool']['value']['operation_id']
    report['model_effect_result_qualified']=True;report['operation_id']=operation
    report['original_receipt_sha256']=hashlib.sha256(original_receipt.encode()).hexdigest()
    phase('original_effect_and_independent_readback_verified',operation_id=operation)
    observation=admin_observe(PREFIX/'admin','initial-physical-current')
    writer_expiry=observation['observation']['writer']['lease']['expires_at_unix_ms'];report['writer_expiry_unix_ms']=writer_expiry;save()
    gui(app,'original-notes-app-close',mode='close')
    assert exited(app) and not exited(session) and not exited(agent)
    before=line_count()
    gui(active_shell,'app-only-readback-prompt',prompt='Notes 窗口已正常关闭。只用 hepta_notes_status（selector.kind=latest_original_replace）查询刚才原操作，再用 hepta_notes_state 查询原文档。不要调用 replace，不要新建或恢复可编辑文档；核对原 operation、target、revision、receipt 和内容摘要。')
    app_readback=wait(lambda:qualified(before,'app-only'),'original helper independent readback after actual App exit',45,active_root)
    assert not exited(session) and not exited(agent)
    report['app_only_readback_qualified']=True;phase('original_app_only_recovery_verified',same_session_pid=session['pid'],same_agent_pid=agent['pid'])
    admin_observe(PREFIX/'admin','before-natural-retirement-physical-current')
    gui(active_shell,'initial-shell-normal-close',mode='close');active_shell=None
    wait_expiry_exit(active_root,'initial-natural-owner-retirement',writer_expiry)
    assert exited(agent) and exited(session) and exited(app)
    phase('original_agent_and_session_lifetimes_retired',agent_pid=agent['pid'],session_pid=session['pid'])
    active_root=spawn_root('recover',operation)
    comp2,session2,agent2,active_shell,app2=setup(active_root,PREFIX/'admin/recovery','recovered')
    assert comp2['original_thread_seed']==seed and comp2['notes_target']!=original_target
    before=line_count()
    gui(active_shell,'same-boot-readback-prompt',prompt='这是同一原任务的恢复检查。只调用 hepta_notes_status，selector.kind=latest_original_replace，核对原 operation_id='+operation+' 的原 writer 终态与因果 receipt；再调用 hepta_notes_state。不要调用 replace，不要把新窗口的当前文档当作旧目标，分别报告原结果和当前 target。')
    recovered=wait(lambda:qualified(before,'same-boot',True),'same original recovered owner result without another effect',35,active_root)
    assert recovered['status_tool']['value']['operation_id']==operation
    after_raw,after_doc=document();assert after_doc['text']==EXPECTED and after_doc['revision']==1
    observation2=admin_observe(PREFIX/'admin/recovery','recovered-physical-current')
    report['same_boot_recovery_qualified']=True;phase('same_boot_original_result_recovered',operation_id=operation,new_target_for_future_operations=comp2['notes_target'])
    writer_expiry2=observation2['observation']['writer']['lease']['expires_at_unix_ms']
    gui(active_shell,'recovered-shell-normal-close',mode='close');active_shell=None
    wait_expiry_exit(active_root,'successor-natural-owner-retirement',writer_expiry2)
    assert exited(agent2) and exited(session2) and exited(app2)
    report['status']='passed'
except Exception as error:
    report['status']='blocked_or_unknown';report['error']=repr(error);report['traceback']=traceback.format_exc();save()
finally:
    for held_shell in [h for h in holds if h['label'].endswith('-shell') and not exited(h)]:
        try:gui(held_shell,'cleanup-owned-shell-'+str(held_shell['pid']),mode='close')
        except Exception as error:report.setdefault('shell_cleanup_errors',[]).append(repr(error))
    for index,root in enumerate(roots):
        if root.poll() is None:
            try:root.wait(timeout=max(1,min(320,(overall_end-time.monotonic()))))
            except subprocess.TimeoutExpired:report.setdefault('cleanup_pending_root_pids',[]).append(root.pid)
        report['roots'][index].update(exit_code=root.poll(),finished_observation_unix_ms=now())
    for hold in holds:
        report.setdefault('final_lifetime_observations',[]).append({'label':hold['label'],'pid':hold['pid'],'exited':exited(hold)})
        os.close(hold['fd'])
    if seed is not None:
        try:
            raw,_=rollout();write('final-original-rollout.jsonl',raw)
            raw_doc,_=document();write('final-original-document.json',raw_doc)
        except Exception as error:report['final_readback_error']=repr(error)
    for stream in streams:stream.flush();stream.close();os.chmod(stream.name,0o644)
    report['finished_unix_ms']=now();save()
    print(json.dumps({'path':str(OUT/'result.json'),'status':report['status'],'sha256':hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),
                      'original_effect':report['model_effect_result_qualified'],'app_only':report['app_only_readback_qualified'],'same_boot':report['same_boot_recovery_qualified'],'error':report.get('error')},ensure_ascii=False),flush=True)
if report['status']!='passed':sys.exit(1)
