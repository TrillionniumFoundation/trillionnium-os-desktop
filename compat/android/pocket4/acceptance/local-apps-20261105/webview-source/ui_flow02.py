#!/usr/bin/python3 -I
"""Owned WebView fixture acceptance. Default: inert plan; no UI/server.

Scope: controlled page, Unicode input/readback, JS/localStorage, page history,
normal owned task close/reopen and removal of this run's one storage key.
This does not qualify every WebView or Browser2 feature for production.
"""
from pathlib import Path
import argparse, base64, copy, hashlib, json, os, re, secrets, signal, stat, time, types

SESSION_SOURCE = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
SESSION_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
FIXTURE_SOURCE = Path('/home/alex/work/pocket4-webview-flow-20261105-r12-tools-02/fixture_server.py')
FIXTURE_SHA = 'f8370d09cc670d24e2ae12e995e04d5c6a1a3bfefa3157c6e95c12c62bc68bb3'
ROOT = Path('/home/alex/work/pocket4-webview-flow-20261105-r12-02')
PACKAGE = 'org.chromium.webview_shell'
COMPONENT = PACKAGE + '/.WebViewBrowserActivity'
APK_PATH = '/product/app/Browser2/Browser2.apk'
APK_SHA = '0f9dbb8ef3af284a08eb86f9558cd6c21a35dbeca2482b4b6e4b85ea49c183df'
PROVIDER = 'com.android.webview'
PROVIDER_PATH = '/product/app/webview/webview.apk'
PROVIDER_VERSION = '145.0.7632.218'
PROVIDER_CODE = 763221807
PROVIDER_SHA = 'e6b6c8e7e5d1e597c51003ca9e6dbdb4e52650ab04567e9aee535d546a2bee31'
VALUE = 'Pocket4 中文 café 😀 — r12'
MAX_ACTIONS, MAX_SECONDS, CLEANUP_RESERVE = 24, 720, 90
CLEARTEXT_RESOURCE_PROOF_RETAINED = True  # Set only after the exact resource receipt is retained.


def require(value, reason):
    if not value: raise RuntimeError(reason)


def load(path, digest, name):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'FROZEN_SOURCE_CHANGED')
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def package_identity(dump, package, uid, version):
    active = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',dump,re.M|re.S)
    require(len(active)==1 and re.findall(r'^  Package \[([^]]+)\]',active[0],re.M)==[package] and
            re.findall(r'^    appId=(\d+)$',active[0],re.M)==[str(uid)] and
            re.findall(r'^    versionCode=(\d+)\b',active[0],re.M)==[str(version)], 'PACKAGE_UID_OR_VERSION_CHANGED')
    users = re.findall(r'^    User 0: (.*)$',active[0],re.M)
    require(len(users)==1 and all(re.search(r'\b'+key+'='+value+r'\b',users[0]) for key,value in
            (('installed','true'),('hidden','false'),('suspended','false'),('enabled','[01]'))),
            'PACKAGE_USER_STATE_CHANGED')


def provider_ready(raw):
    lines = [' '.join(line.split()) for line in raw.splitlines()]
    def single(prefix):
        matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
        require(len(matches)==1,'PROVIDER_STATE_FIELD_NOT_UNIQUE:'+prefix)
        return matches[0]
    expected = '('+PROVIDER+', '+PROVIDER_VERSION+')'
    require(single('Current WebView package (name, version): ')==expected and
            single('Preferred WebView package (name, version): ')==expected and
            single('WebView package dirty: ')=='false' and single('Any WebView package installed: ')=='true',
            'PROVIDER_SELECTION_OR_READY_STATE_CHANGED')
    started,finished = single('Number of relros started: '),single('Number of relros finished: ')
    require(started.isdecimal() and finished.isdecimal() and int(started)>0 and started==finished,
            'PROVIDER_RELRO_NOT_READY')
    valid = [line for line in lines if line.startswith('Valid package '+PROVIDER+' ')]
    require(valid==['Valid package '+PROVIDER+' (versionName: '+PROVIDER_VERSION+', versionCode: '+
        str(PROVIDER_CODE)+', targetSdkVersion: 36) is installed/enabled for all users'], 'PROVIDER_PACKAGE_NOT_VALID')
    return {'package':PROVIDER,'version_name':PROVIDER_VERSION,'version_code':PROVIDER_CODE,
            'relros_started':int(started),'relros_finished':int(finished),'ready':True}


def post_capture_only(response, acknowledgements, op):
    if op!='click' or len(acknowledgements)!=1: return False
    ack=acknowledgements[0]
    return (ack.get('ok') is True and ack.get('performed')=='click' and ack.get('outcome_unknown') is not True and
            ack.get('accessibility_mode_restoration_verified') is True and isinstance(ack.get('target'),dict) and
            isinstance(ack.get('actual_target'),dict) and response.get('ok') is True and response.get('performed')=='click' and
            response.get('outcome_unknown') is True and response.get('post_action_observation_available') is False)


def expired(number, frame):
    raise TimeoutError('UI_SESSION_DEADLINE_NO_ACTION_REPLAY')


def parse_stacks(raw):
    roots, tasks = {}, set()
    for block in re.split(r'(?=^RootTask id=)', raw, flags=re.M):
        if not block.startswith('RootTask id='): continue
        head = block.splitlines()[0]
        rid = int(re.search(r'^RootTask id=(\d+)\b', head)[1])
        display = int(re.search(r'\bdisplayId=(\d+)\b', head)[1])
        user = int(re.search(r'\buserId=(\d+)\b', head)[1])
        children = []
        for line in block.splitlines():
            match = re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b', line)
            require(not re.match(r'\s*taskId=', line) or match is not None, 'UNPARSED_TASK_LINE')
            if match:
                tid = int(match[1]); require(tid not in tasks, 'DUPLICATE_TASK')
                tasks.add(tid); children.append({'id':tid,'component':match[2],'user':int(match[3])})
        require(rid not in roots, 'DUPLICATE_ROOT')
        roots[rid] = {'display':display,'user':user,'freeform':'mWindowingMode=freeform' in block,'children':children}
    require(bool(roots) and bool(tasks), 'UNRECOGNIZED_STACK_LIST')
    return roots, tasks


def exact_leaf(roots, task):
    root = roots.get(task)
    return bool(root and root['display']==root['user']==0 and root['freeform'] and
        len(root['children'])==1 and root['children'][0]['id']==task and
        root['children'][0]['user']==0 and root['children'][0]['component'].split('/')[0]==PACKAGE)


def focus_metadata(raw):
    focus_lines = [x.strip() for x in raw.splitlines() if 'mCurrentFocus=' in x]
    app_lines = [x.strip() for x in raw.splitlines() if 'mFocusedApp=' in x]
    focus = re.findall(r'mCurrentFocus=Window\{([0-9a-fA-F]+)\s+u(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', raw)
    app = re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*?\bu(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t(\d+)\b', raw)
    if any(len(set(x)) != 1 for x in (focus_lines, app_lines, focus, app)):
        return {'verified':False,'reason':'FOCUS_OR_ACTIVITY_NOT_UNIQUE'}
    token,user,package,activity = focus[0]; app_user,app_package,app_activity,task = app[0]
    return {'verified':user==app_user=='0' and package==app_package,
            'package':package,'activity':activity,'window_token':token.lower(),
            'focused_activity':app_activity,'task':int(task),'user':int(user)}


class Trial:
    def __init__(self, session, tx, fixture):
        self.s,self.tx,self.fixture = session,tx,fixture
        self.start = time.monotonic(); self.sequence = self.actions = self.launches = self.removals = 0
        self.owned = None; self.pending = set()
        self.provider_fingerprint = None
        self.result = {'state':'NOT_STARTED','business_flow_completed':False,'whole_app_production_ready':False,
                       'navigation_scope':'same-origin page history','run':fixture.run,'automatic_retry':False,
                       'origin':'http://127.0.0.1:%d'%fixture.ready['port'],'fixture_port':fixture.ready['port'],
                       'owned_storage_key':'pocket4.webview.r12.'+fixture.run,
                       'owned_storage_state':'NOT_EXAMINED','owned_storage_key_removal_verified':False}

    def record(self, label, value):
        self.sequence += 1
        self.tx.write_new(ROOT / ('%03d-' % self.sequence + label + '.json'), value)

    def budget(self, cleanup=False):
        require(self.actions < MAX_ACTIONS, 'ACTION_BUDGET_EXHAUSTED')
        if not cleanup:
            require(self.actions < MAX_ACTIONS - 2 and time.monotonic()-self.start < MAX_SECONDS-CLEANUP_RESERVE,
                    'SESSION_BUDGET_RESERVED_FOR_CLEANUP')
            self.fixture.ensure_alive()

    def identity(self):
        paths = self.s.android(['/system/bin/pm','path','--user','0',PACKAGE]).decode().splitlines()
        require(paths==['package:'+APK_PATH], 'SHELL_ACTIVE_APK_PATH_CHANGED')
        data,_ = self.s.target.read_file(APK_PATH,1024*1024)
        require(len(data)==70877 and hashlib.sha256(data).hexdigest()==APK_SHA,'SHELL_APK_CHANGED')
        dump = self.s.android(['/system/bin/dumpsys','package',PACKAGE]).decode()
        package_identity(dump,PACKAGE,10060,1)
        require(self.s.android(['/system/bin/pm','path','--user','0',PROVIDER]).decode().splitlines()==
                ['package:'+PROVIDER_PATH], 'ACTIVE_PROVIDER_APK_PATH_CHANGED')
        package_identity(self.s.android(['/system/bin/dumpsys','package',PROVIDER]).decode(),PROVIDER,10071,PROVIDER_CODE)
        fd=self.s.target.open_root(PROVIDER_PATH,os.O_RDONLY|os.O_NOFOLLOW)
        fields=('st_dev','st_ino','st_size','st_uid','st_gid','st_mode','st_mtime_ns','st_ctime_ns')
        streamed=False
        try:
            before=os.fstat(fd); fingerprint=tuple(getattr(before,key) for key in fields)
            require(stat.S_ISREG(before.st_mode) and (before.st_dev,before.st_ino,before.st_size,before.st_uid,
                    stat.S_IMODE(before.st_mode))==(1809,7915904,333998538,0,0o644),'PROVIDER_APK_METADATA_CHANGED')
            if self.provider_fingerprint is None:
                digest,count,end=hashlib.sha256(),0,time.monotonic()+25
                while True:
                    require(time.monotonic()<end,'PROVIDER_STREAM_HASH_DEADLINE')
                    chunk=os.read(fd,1024*1024)
                    if not chunk:break
                    count+=len(chunk);digest.update(chunk)
                    require(count<=before.st_size,'PROVIDER_APK_GREW')
                require(count==before.st_size and digest.hexdigest()==PROVIDER_SHA,'PROVIDER_APK_HASH_CHANGED')
                streamed=True
            else:
                require(fingerprint==self.provider_fingerprint,'PROVIDER_HASHED_FILE_IDENTITY_CHANGED')
            after=os.fstat(fd)
            require(fingerprint==tuple(getattr(after,key) for key in fields),'PROVIDER_CHANGED_DURING_IDENTITY_CHECK')
            self.provider_fingerprint=fingerprint
        finally:os.close(fd)
        raw=self.s.android(['/system/bin/dumpsys','webviewupdate']).decode()
        state=provider_ready(raw)
        self.record('provider-identity',{'service':state,'raw':raw,'guest_path':PROVIDER_PATH,
            'sha256':PROVIDER_SHA,'stream_hash_this_check':streamed,'fingerprint':dict(zip(fields,fingerprint))})
        self.s.guard()

    def stacks(self, label):
        raw = self.s.android(['/system/bin/cmd','activity','stack','list'],15).decode()
        roots,tasks = parse_stacks(raw); self.record(label,{'raw':raw,'tasks':sorted(tasks)})
        return roots,tasks

    def owned_check(self, label):
        require(self.owned is not None, 'NO_OWNED_TASK')
        task,preserved = self.owned; roots,tasks = self.stacks(label)
        require(exact_leaf(roots,task) and tasks==preserved|{task}, 'OWNED_TASK_SCOPE_CHANGED')

    def focus(self):
        return focus_metadata(self.s.android(['/system/bin/dumpsys','window','displays'],6).decode())

    def ready_focus(self):
        end = time.monotonic()+10; previous = None
        while end-time.monotonic()>6:
            current = self.focus()
            valid = current.get('verified') and current.get('package')==PACKAGE and current.get('task')==self.owned[0]
            if valid and current==previous:
                self.owned_check('ready-owned'); return current
            previous = current if valid else None; time.sleep(.2)
        raise RuntimeError('OWNED_SHELL_FOCUS_NOT_READY')

    def observe(self, label):
        self.budget(); focus = self.ready_focus(); self.s.guard()
        value = self.s.helper.dispatch({'op':'observe','package':PACKAGE,'window_token':focus['window_token'],
                                       'display':0,'accessibility_mode':'none','with_png':True})
        self.s.guard(); png = value.pop('screenshot_png_base64',None)
        if png is not None:
            self.tx.write_new(ROOT / ('%03d-' % (self.sequence+1) + label + '.png'),base64.b64decode(png,validate=True))
        self.record(label,value)
        native = value.get('native',{})
        require(value.get('ok') is True and value.get('outcome_unknown') is not True and native.get('ok') is True and
                native.get('accessibility_mode_restoration_verified') is True,'OBSERVATION_UNVERIFIED')
        require(value['screenshot']['scope']['package']==PACKAGE and
                value['screenshot']['scope']['window_token']==focus['window_token'],'OBSERVATION_SCOPE_CHANGED')
        self.owned_check('observed-owned')
        return {'focus':focus,'nodes':[n for n in native.get('nodes',[]) if n.get('package')==PACKAGE and n.get('visible') is True]}

    def one(self, obs, predicate, reason):
        nodes = [n for n in obs['nodes'] if predicate(n)]
        require(len(nodes)==1,reason); return nodes[0]

    def mutate(self, obs, label, operation, node, value=None):
        self.budget(); self.owned_check('before-'+label)
        require(self.focus()==obs['focus'],'ACTION_FOCUS_CHANGED')
        selector = {'package':PACKAGE,'class':node['class'],'enabled':True}
        if node.get('resource-id'): selector['id']=node['resource-id']
        if isinstance(node.get('text'),str): selector['text']=node['text']
        if node.get('content-desc'): selector['desc']=node['content-desc']
        selector['editable' if operation=='set-text' else 'clickable']=True
        request = {'op':operation,'package':PACKAGE,'display':0,'window_token':obs['focus']['window_token'],
                   'accessibility_mode':'none','selector':selector}
        if operation=='set-text': request['value']=value
        else: request['method']='accessibility'
        self.record(label+'-intent',{'request':request,'automatic_retry':False})
        self.actions += 1; self.pending.add(label); self.s.guard()
        original_ui=self.s.helper.ui; acknowledgements=[]
        def record_native(native_request):
            reply=original_ui(native_request)
            if native_request.get('op')==operation:
                ack=copy.deepcopy(reply);acknowledgements.append(ack);self.record(label+'-native-ack',ack)
            return reply
        self.s.helper.ui=record_native
        try:reply=self.s.helper.dispatch(request)
        finally:self.s.helper.ui=original_ui
        self.s.guard(); self.record(label+'-response',reply)
        if post_capture_only(reply,acknowledgements,operation):
            self.observe(label+'-reconciled')
            self.record(label+'-reconciliation',{'original_outcome_unknown_retained':True,'native_input_acknowledged':True,
                'fresh_owned_observation_verified':True,'action_replayed':False,'business_success_verified':False})
            self.result.setdefault('post_capture_reconciliations',[]).append(label)
            self.pending.remove(label);return
        require(reply.get('ok') is True and reply.get('performed')==operation and reply.get('outcome_unknown') is not True,
                'ACTION_OUTCOME_UNVERIFIED_NO_REPLAY')
        if operation=='set-text':
            require(reply.get('readback_verified') is True and reply.get('password') is False,'TEXT_NATIVE_READBACK_UNVERIFIED')
        self.pending.remove(label)

    def button(self, obs, label, text):
        node = self.one(obs,lambda n:n.get('enabled') is True and n.get('clickable') is True and
                        (n.get('text')==text or n.get('content-desc')==text),'ONE_SEMANTIC_BUTTON_REQUIRED:'+text)
        self.mutate(obs,label,'click',node)

    def expect(self, label, text):
        for attempt in range(3):
            obs = self.observe(label+'-%d'%attempt)
            visible = [str(n.get('text','')) for n in obs['nodes']]
            if any(t.startswith('FAIL:') for t in visible): raise RuntimeError('FIXTURE_REPORTED_FAILURE')
            if text in visible and self.fixture.run in visible and 'JavaScript ready: 437' in visible:
                return obs
            if attempt<2: time.sleep(.4)
        raise RuntimeError('EXPECTED_VISIBLE_PAGE_RESULT_MISSING:'+text)

    def url(self, name, expected):
        target = self.fixture.url(name); obs = self.observe('before-url')
        field = self.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/url_field' and
                         n.get('editable') is True and n.get('enabled') is True,'ONE_URL_FIELD_REQUIRED')
        self.mutate(obs,'url-'+name,'set-text',field,target)
        obs = self.observe('url-readback')
        self.one(obs,lambda n:n.get('resource-id')==PACKAGE+':id/url_field' and n.get('text')==target,
                 'URL_READBACK_DIFFERENT')
        go = self.one(obs,lambda n:n.get('class')=='android.widget.ImageButton' and
                      n.get('content-desc')=='Load URL' and n.get('enabled') is True and
                      n.get('clickable') is True,'ONE_OBSERVED_LOAD_URL_REQUIRED')
        self.mutate(obs,'go-'+name,'click',go)
        return self.expect('page-'+name,expected)

    def launch(self):
        self.budget(); roots,tasks = self.stacks('before-launch')
        require(not any(c['component'].split('/')[0]==PACKAGE for r in roots.values() for c in r['children']),
                'PREEXISTING_SHELL_TASK_PRESERVED')
        command = [*self.tx.ALEX_PREFIX,'launch',PACKAGE,'--component',COMPONENT,'--json']
        self.record('launch-intent',{'argv':command,'automatic_retry':False})
        self.actions += 1; self.launches += 1; token='launch-%d'%self.launches; self.pending.add(token)
        response = self.s.run_host('webview-launch-%d'%self.launches,command,45)
        require(response['rc']==0 and not response['timed_out'] and response['joined'],'LAUNCH_OUTCOME_UNKNOWN')
        value = json.loads(response['stdout'])
        require(value.get('ok') is True and value.get('state')=='running' and value.get('host_pid')==self.tx.MAIN_HOST and
                value.get('outcome_unknown') is not True,'LAUNCH_RECEIPT_UNVERIFIED')
        match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',value.get('launch',''))
        require(match and int(match[3])==0,'LAUNCH_TASK_UNKNOWN'); task=int(match[4])
        require(task not in roots and task not in tasks,'LAUNCH_TASK_NOT_NEW')
        self.owned=(task,tasks); self.owned_check('after-launch'); self.pending.remove(token)

    def close_task(self):
        if self.owned is None: return
        self.budget(cleanup=True); task,preserved=self.owned; self.owned_check('before-close')
        command=['/system/bin/cmd','activity','stack','remove',str(task)]
        self.record('close-intent',{'argv':command,'automatic_retry':False,'prelaunch_absent':True})
        self.owned=None; self.actions+=1; self.removals+=1; token='close-%d'%self.removals; self.pending.add(token)
        self.s.android(command,15)
        end=time.monotonic()+8
        while time.monotonic()<end:
            roots,tasks=self.stacks('close-readback')
            require(tasks-{task}==preserved,'OTHER_TASK_SET_CHANGED_DURING_CLOSE')
            if task not in roots and task not in tasks: self.pending.remove(token); return
            time.sleep(.25)
        raise RuntimeError('OWNED_CLOSE_OUTCOME_UNKNOWN_NO_REPLAY')

    def run(self):
        old_handler=signal.signal(signal.SIGALRM,expired)
        signal.setitimer(signal.ITIMER_REAL,MAX_SECONDS-CLEANUP_RESERVE)
        try:
            self.identity(); self.launch()
            obs=self.url('a.html','BASELINE_EMPTY; input is empty')
            self.result['owned_storage_state']='ABSENT_VERIFIED_BEFORE_ACTIONS'
            field=self.one(obs,lambda n:n.get('editable') is True and n.get('enabled') is True and
                n.get('resource-id')!=PACKAGE+':id/url_field' and
                (n.get('resource-id')=='entry' or n.get('content-desc')=='Unicode test input'),
                'ONE_OBSERVED_PAGE_INPUT_REQUIRED')
            require(field.get('text','')=='','PAGE_INPUT_NOT_EMPTY')
            self.mutate(obs,'unicode','set-text',field,VALUE)
            obs=self.observe('unicode-readback')
            self.one(obs,lambda n:n.get('editable') is True and n.get('text')==VALUE,'UNICODE_READBACK_DIFFERENT')
            self.result['owned_storage_state']='WRITE_OUTCOME_NOT_YET_VERIFIED'
            self.button(obs,'save-owned-key','Verify input and store')
            obs=self.expect('stored','INPUT_AND_STORAGE_OK counter=1 value='+VALUE)
            self.result['owned_storage_state']='PRESENT_VERIFIED_COUNTER_1'
            self.button(obs,'next-page','Open second page')
            obs=self.expect('second','SECOND_PAGE_READBACK_OK counter=1 value='+VALUE)
            self.result['owned_storage_state']='COUNTER_UPDATE_OUTCOME_NOT_YET_VERIFIED'
            self.button(obs,'increment','Increment stored counter')
            obs=self.expect('incremented','COUNTER_INCREMENT_OK counter=2 value='+VALUE)
            self.result['owned_storage_state']='PRESENT_VERIFIED_COUNTER_2'
            self.button(obs,'history-back','Return to input page')
            self.expect('back','BACK_READBACK_OK counter=2 value='+VALUE)
            self.close_task(); self.launch()
            obs=self.url('reopen.html','REOPEN_READBACK_OK counter=2 value='+VALUE)
            self.result['owned_storage_state']='REMOVAL_OUTCOME_NOT_YET_VERIFIED'
            self.button(obs,'remove-owned-key','Remove this run storage key')
            self.expect('key-removed','OWNED_KEY_REMOVED')
            self.result['owned_storage_key_removal_verified']=True
            self.result['owned_storage_state']='ABSENT_VERIFIED_AFTER_OWNED_REMOVAL'
            self.close_task(); self.identity()
            require(self.launches==self.removals==2 and not self.pending,'LIFECYCLE_OR_EFFECTS_INCOMPLETE')
            self.result.update(state='SCOPED_BUSINESS_FLOW_COMPLETED',business_flow_completed=True)
        except BaseException as exc:
            self.result.update(state='WEBVIEW_FLOW_STOPPED',business_flow_completed=False,
                               error=type(exc).__name__+': '+str(exc))
        finally:
            signal.setitimer(signal.ITIMER_REAL,max(.001,min(CLEANUP_RESERVE,MAX_SECONDS-(time.monotonic()-self.start))))
            try: self.close_task()
            except BaseException as exc:
                self.result.update(state='OWNED_CLEANUP_UNVERIFIED',business_flow_completed=False,
                                   cleanup_error=type(exc).__name__+': '+str(exc))
            finally:
                signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
            self.result.update(action_calls=self.actions,launch_calls=self.launches,owned_remove_calls=self.removals,
                pending_effects=sorted(self.pending),outcome_unknown=bool(self.pending),
                elapsed_seconds=time.monotonic()-self.start,framework_epoch_sha256=self.s.epoch_sha256)
        return self.result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'PLAN_ONLY','ui_actions':0,'server_starts':0,'max_actions':MAX_ACTIONS,
            'max_seconds':MAX_SECONDS,'fixture_lease_seconds':600,'resource_proof_retained':CLEARTEXT_RESOURCE_PROOF_RETAINED,
            'whole_app_production_ready':False},indent=2));return 0
    require(CLEARTEXT_RESOURCE_PROOF_RETAINED,'CLEARTEXT_RESOURCE_PROOF_NOT_YET_FROZEN')
    tx=load(SESSION_SOURCE,SESSION_SHA,'webview_session'); fixture_module=load(FIXTURE_SOURCE,FIXTURE_SHA,'webview_fixture')
    result={'state':'NOT_STARTED','business_flow_completed':False,'whole_app_production_ready':False}
    with tx.ui_lock():
        ROOT.mkdir(mode=0o700)
        try:
            with tx.CameraSession(ROOT/'commands') as session:
                with fixture_module.FixtureOwner(session,FIXTURE_SOURCE,FIXTURE_SHA,secrets.token_hex(16),ROOT/'fixture',600) as fixture:
                    result=Trial(session,tx,fixture).run()
                require(fixture.result['own_child_reaped'] and fixture.result['exit_code']==0,'OWN_SERVER_CLEANUP_UNVERIFIED')
                terminal=[json.loads(line) for line in fixture.result['child_stdout'].splitlines()]
                require(len(terminal)==1 and terminal[0].get('state')=='FIXTURE_CLOSED' and
                        terminal[0].get('socket_closed') is True,'OWN_SERVER_CLOSE_RECEIPT_UNVERIFIED')
                fixture.result['terminal']=terminal[0]
                result['fixture_cleanup']=fixture.result
                result['final_guard']=session.guard();session.caller_status('webview-final-caller')
        except BaseException as exc:
            result.update(state='WEBVIEW_OUTER_FAILURE',business_flow_completed=False,error=type(exc).__name__+': '+str(exc))
        tx.write_new(ROOT/'result.json',result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['business_flow_completed'] else 1


if __name__=='__main__':raise SystemExit(main())
