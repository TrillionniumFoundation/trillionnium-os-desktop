#!/usr/bin/python3 -I
"""Bounded owned-task UI adapter for the fixed SAF client and DocumentsUI only.

Snapshot touch uses the unchanged frozen helper's two frame validations. A long
press uses the same two validations before one held-display input command.
No acknowledgement qualifies a document operation without its later readback.
"""
from pathlib import Path
import base64, copy, json, re, time

PACKAGE='org.droidloom.qa.saf.r12.n69814e80ea71f485'
DOCS='com.android.documentsui'
CLIENT=PACKAGE+'.SafActivity'
PICKER=DOCS+'.picker.PickActivity'
FILES=DOCS+'.files.FilesActivity'
RESOLVER='com.android.internal.app.ResolverActivity'
MAX_ACTIONS=36


def need(value,reason):
    if not value:raise RuntimeError(reason)


def expand(package,activity):return package+activity if activity.startswith('.') else activity


def parse_stacks(raw):
    roots,tasks={},set()
    for block in re.split(r'(?=^RootTask id=)',raw,flags=re.M):
        if not block.startswith('RootTask id='):continue
        head=block.splitlines()[0]
        rid=int(re.search(r'^RootTask id=(\d+)\b',head)[1])
        display=int(re.search(r'\bdisplayId=(\d+)\b',head)[1]);user=int(re.search(r'\buserId=(\d+)\b',head)[1])
        children=[]
        for line in block.splitlines():
            match=re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b',line)
            need(not re.match(r'\s*taskId=',line) or match is not None,'UNPARSED_TASK_LINE')
            if match:
                tid=int(match[1]);need(tid not in tasks,'DUPLICATE_TASK');tasks.add(tid)
                children.append({'id':tid,'component':match[2],'user':int(match[3])})
        need(rid not in roots,'DUPLICATE_ROOT')
        roots[rid]={'display':display,'user':user,'freeform':'mWindowingMode=freeform' in block,'children':children}
    need(roots and tasks,'UNRECOGNIZED_STACK_LIST')
    return roots,tasks


def leaf(roots,task,component=None):
    root=roots.get(task)
    if not(root and root['display']==root['user']==0 and root['freeform'] and len(root['children'])==1
            and root['children'][0]['id']==task and root['children'][0]['user']==0):return False
    observed=root['children'][0]['component'];package,activity=observed.split('/',1)
    return component is None or (package,expand(package,activity))==component


def focus_metadata(raw):
    lines=[x.strip() for x in raw.splitlines() if 'mCurrentFocus=' in x]
    app_lines=[x.strip() for x in raw.splitlines() if 'mFocusedApp=' in x]
    windows=re.findall(r'mCurrentFocus=Window\{([0-9a-fA-F]+)\s+u(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)',raw)
    apps=re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*?\bu(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t(\d+)\b',raw)
    if any(len(set(x))!=1 for x in (lines,app_lines,apps)):return None
    user,package,activity,task=apps[0];activity=expand(package,activity)
    if len(set(windows))==1:
        token,wuser,wpackage,wactivity=windows[0]
        if user==wuser=='0' and package==wpackage and activity==expand(wpackage,wactivity):
            return {'package':package,'activity':activity,'window_token':token.lower(),'task':int(task),'popup':False}
    popup=re.findall(r'mCurrentFocus=Window\{([0-9a-f]+) u0 (PopupWindow:[0-9a-f]+)\}',raw)
    if len(popup)==1 and user=='0' and package==DOCS and activity==FILES:
        return {'package':package,'activity':activity,'window_token':popup[0][0],
            'task':int(task),'popup':True,'title':popup[0][1]}
    return None


class Adapter:
    def __init__(self,session,tx,root):
        self.s,self.tx,self.root=session,tx,Path(root)
        self.sequence=self.actions=self.launches=self.removals=0
        self.owned={};self.baseline=None;self.pending={};self.allowed=set();self.popup_grant=None
        self.allow_new=None;self.last=None;self.closed=[];self.adopted=[]
        self.s.helper.foreground=self.helper_foreground

    def record(self,label,value):
        self.sequence+=1
        self.tx.write_new(self.root/('%03d-'%self.sequence+label+'.json'),value)

    def budget(self,cleanup=False):
        need(self.actions<MAX_ACTIONS-(0 if cleanup else 4),'UI_ACTION_BUDGET')

    def stacks(self,label,timeout=15):
        raw=self.s.android(['/system/bin/cmd','activity','stack','list'],timeout).decode()
        roots,tasks=parse_stacks(raw);self.record(label,{'raw':raw,'tasks':sorted(tasks)})
        return roots,tasks

    def check_tasks(self,label,admit=False):
        roots,tasks=self.stacks(label)
        need(self.baseline is not None and self.baseline<=tasks,'PREEXISTING_TASK_LOST')
        added=tasks-self.baseline-set(self.owned)
        if added:
            grant=self.allow_new
            need(admit and grant is not None and len(added)==1 and grant['source'] in self.pending
                and self.pending[grant['source']]['input_acknowledged'],'UNOWNED_TASK_DELTA')
            task=next(iter(added));component=grant['component']
            need(leaf(roots,task,component),'NEW_TASK_IS_NOT_SOURCE_BOUND_EXACT_COMPONENT')
            self.owned[task]={'component':component,'source':grant['source']};self.adopted.append(task)
            self.record('adopt-source-bound-task',{'task':task,'grant':grant,'prelaunch_absent':True})
        need(tasks==self.baseline|set(self.owned),'OWNED_TASK_SET_CHANGED')
        need(all(leaf(roots,task,tuple(info['component'])) for task,info in self.owned.items()),'OWNED_LEAF_CHANGED')
        return roots,tasks

    def focus(self):
        raw=self.s.android(['/system/bin/dumpsys','window','displays'],6).decode()
        value=focus_metadata(raw);self.record('focus',{'focus':value,'raw':raw})
        if value and value.get('popup'):
            grant=self.popup_grant
            if not(grant and value['task']==grant['task'] and value['window_token']!=grant['parent']
                and grant.get('popup') in (None,value['window_token'])):return None
            grant['popup']=value['window_token']
        return value

    def allowed_focus(self,value):
        return bool(value and value['task'] in self.owned and (value['package'],value['activity']) in self.allowed)

    def helper_foreground(self):
        value=self.focus();need(self.allowed_focus(value),'HELPER_FOCUS_OUTSIDE_OWNED_ROUTE')
        return {k:value[k] for k in ('package','activity','window_token')}

    def observe(self,label,routes,admit=False):
        self.budget();self.allowed=set(routes);self.check_tasks(label+'-tasks',admit)
        previous=None;end=time.monotonic()+12;focus=None
        while end-time.monotonic()>6:
            current=self.focus()
            if self.allowed_focus(current) and current==previous:focus=current;break
            previous=current if self.allowed_focus(current) else None;time.sleep(.15)
        need(focus is not None,'OWNED_FOCUS_NOT_STABLE')
        self.s.guard()
        value=self.s.helper.dispatch({'op':'observe','package':focus['package'],'window_token':focus['window_token'],
            'display':0,'accessibility_mode':'none','with_png':True})
        self.s.guard();png=value.pop('screenshot_png_base64',None)
        if png:self.tx.write_new(self.root/('%03d-'%(self.sequence+1)+label+'.png'),base64.b64decode(png,validate=True))
        self.record(label,value);native=value.get('native',{})
        need(value.get('ok') is True and value.get('outcome_unknown') is not True and native.get('ok') is True
            and native.get('accessibility_mode_restoration_verified') is True,'OBSERVATION_NOT_VERIFIED')
        shot=value['screenshot'];need(shot['scope']['package']==focus['package']
            and shot['scope']['window_token']==focus['window_token'],'OBSERVATION_SCOPE_CHANGED')
        self.check_tasks(label+'-after')
        self.last={'focus':focus,'screenshot':shot,'nodes':[n for n in native.get('nodes',[])
            if n.get('package')==focus['package'] and n.get('visible') is True]}
        # Resolve only post-observation uncertainty after a recorded successful
        # input acknowledgement. Business gates are deliberately separate.
        for token in list(self.pending):
            if self.pending[token].get('input_acknowledged'):
                self.record('input-observation-reconciled',{'token':token,'original':self.pending[token],
                    'action_replayed':False,'business_success_verified':False})
                del self.pending[token]
        self.allow_new=None
        return self.last

    @staticmethod
    def one(obs,predicate,reason):
        nodes=[n for n in obs['nodes'] if predicate(n)];need(len(nodes)==1,reason);return nodes[0]

    def box(self,obs,node):
        bounds=node.get('bounds_array');scope=obs['screenshot']['scope_bounds']
        need(isinstance(bounds,list) and len(bounds)==4 and all(type(v) is int for v in bounds)
            and scope[0]<=bounds[0]<bounds[2]<=scope[2] and scope[1]<=bounds[1]<bounds[3]<=scope[3],
            'CONTROL_NOT_FULLY_VISIBLE_IN_OWNED_SCOPE')
        return [(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2]

    def input(self,obs,label,node,kind='tap',value=None,transition=None,popup=False):
        self.budget();need(not self.pending,'PENDING_INPUT_NOT_REPLAYABLE')
        self.check_tasks('before-'+label);need(self.focus()==obs['focus'],'INPUT_FOCUS_CHANGED')
        need(node.get('enabled') is True,'INPUT_NODE_DISABLED')
        shot=obs['screenshot'];scope=shot['scope'];point=self.box(obs,node)
        request={'op':'snapshot-tap','package':scope['package'],'display':0,'accessibility_mode':'none',
            'window_token':scope['window_token'],'frame_sha256':shot['frame_sha256'],
            'scope_sha256':shot['scope_sha256'],'context_token':shot['context_token'],'coords':point,'input_source':'touch'}
        if kind=='set-text':
            need(node.get('editable') is True and node.get('password') is not True,'EDITABLE_NONPASSWORD_REQUIRED')
            selector={'package':scope['package'],'class':node['class'],'editable':True,'enabled':True}
            if node.get('resource-id'):selector['id']=node['resource-id']
            if isinstance(node.get('text'),str):selector['text']=node['text']
            request={'op':'set-text','package':scope['package'],'display':0,'accessibility_mode':'none',
                'window_token':scope['window_token'],'selector':selector,'value':value}
        elif kind=='long-press':need(node.get('long-clickable') is True or node.get('long_clickable') is True
            or 32 in node.get('supported_actions',[]),'OBSERVED_LONG_CLICK_CAPABILITY_REQUIRED')
        else:need(kind=='tap','UNSUPPORTED_INPUT_KIND')
        snapshot_request={'package':scope['package'],'display':0,'accessibility_mode':'none',
            'window_token':scope['window_token'],'frame_sha256':shot['frame_sha256'],
            'scope_sha256':shot['scope_sha256'],'context_token':shot['context_token']}
        if kind in ('set-text','long-press'):
            frame=self.s.helper.capture(snapshot_request);self.s.helper.validate_snapshot(snapshot_request,frame)
            if kind=='set-text':
                fresh=self.s.helper.ui({'op':'dump','expected_package':scope['package'],
                    'display':0,'accessibility_mode':'none'})
                self.record(label+'-fresh-native',fresh)
                need(fresh.get('ok') is True and fresh.get('outcome_unknown') is not True
                    and fresh.get('accessibility_mode_restoration_verified') is True,'FRESH_NATIVE_NOT_VERIFIED')
                matches=[n for n in fresh.get('nodes',[]) if n.get('package')==scope['package']
                    and n.get('class')==node.get('class') and n.get('resource-id')==node.get('resource-id')
                    and n.get('editable') is True and n.get('text')==node.get('text')]
                need(len(matches)==1,'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT')
                current=matches[0]
                # Each helper.ui dump creates a separate instrumentation connection.
                # Actual flow08 differs only in its connection-scoped window_id.
                # WM token, task, scope and pixels remain independently bound below.
                need(all(type(n.get('window_id')) is int and n['window_id']>=0 for n in (node,current)),
                    'EDITOR_CONNECTION_WINDOW_ID_REQUIRED')
                need({k:v for k,v in current.items() if k!='window_id'}
                    =={k:v for k,v in node.items() if k!='window_id'},'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT')
                self.record(label+'-cross-connection-editor-verified',{
                    'original_connection_window_id':node['window_id'],'fresh_connection_window_id':current['window_id'],
                    'all_other_node_fields_equal':True,'wm_window_token':scope['window_token']})
            frame=self.s.helper.capture(snapshot_request);self.s.helper.validate_snapshot(snapshot_request,frame)
            need(self.focus()==obs['focus'],'LAST_INPUT_FOCUS_CHANGED')
        self.record(label+'-intent',{'request':request,'kind':kind,'node':node,'automatic_retry':False})
        self.actions+=1;self.pending[label]={'input_acknowledged':False,'kind':kind}
        self.s.guard()
        try:
            if kind=='long-press':
                self.s.android(['/system/bin/input','-d','0','swipe',str(point[0]),str(point[1]),
                    str(point[0]),str(point[1]),'650'],10)
                reply={'ok':True,'performed':'long-press','input_command_completed':True,'business_success_verified':False}
            else:reply=self.s.helper.dispatch(request)
        except BaseException as exc:
            details=getattr(exc,'details',{})
            if details.get('outcome_unknown') is not True and (details.get('action_taken') is False
                    or details.get('outcome_unknown') is False):
                self.record(label+'-no-effect',{'error':str(exc),'details':details,'action_replayed':False})
                del self.pending[label]
            raise
        self.s.guard();self.record(label+'-response',reply)
        if kind=='set-text':
            need(reply.get('ok') is True and reply.get('performed')=='set-text' and reply.get('outcome_unknown') is not True
                and reply.get('readback_verified') is True and reply.get('password') is False,'INPUT_UNKNOWN_NO_REPLAY')
        else:
            need(reply.get('ok') is True and reply.get('input_command_completed') is True
                and (reply.get('outcome_unknown') is not True or reply.get('post_action_observation_available') is False),
                'INPUT_UNKNOWN_NO_REPLAY')
        self.pending[label].update(input_acknowledged=True,post_capture_outcome_unknown=reply.get('outcome_unknown') is True)
        if transition:self.allow_new={'source':label,'component':transition}
        if popup:self.popup_grant={'task':obs['focus']['task'],'parent':obs['focus']['window_token']}
        return reply

    def launch(self):
        self.budget();roots,tasks=self.stacks('before-client-launch')
        if self.baseline is None:
            need(not any(c['component'].split('/')[0] in (PACKAGE,DOCS) for r in roots.values() for c in r['children']),
                'PREEXISTING_CLIENT_OR_DOCUMENTS_TASK_PRESERVED');self.baseline=tasks
        need(tasks==self.baseline and not self.owned,'PREVIOUS_OWNED_TASKS_NOT_CLOSED')
        argv=[*self.tx.ALEX_PREFIX,'launch',PACKAGE,'--component',PACKAGE+'/.SafActivity','--json']
        token='launch-'+str(self.launches+1);self.record(token+'-intent',{'argv':argv,'automatic_retry':False})
        self.actions+=1;self.launches+=1;self.pending[token]={'input_acknowledged':False}
        result=self.s.run_host(token,argv,45)
        need(result['rc']==0 and not result['timed_out'] and result['joined'],'LAUNCH_UNKNOWN')
        value=json.loads(result['stdout']);self.record(token+'-receipt',value)
        need(value.get('ok') is True and value.get('state')=='running' and value.get('host_pid')==self.tx.MAIN_HOST
            and value.get('outcome_unknown') is not True,'NATIVE_LAUNCH_NOT_VERIFIED')
        match=re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)',value.get('launch',''))
        need(match and int(match[3])==0,'LAUNCH_TASK_UNKNOWN');task=int(match[4])
        need(task not in roots and task not in tasks,'LAUNCH_TASK_PREEXISTED')
        self.owned[task]={'component':(PACKAGE,CLIENT),'source':token}
        self.check_tasks('after-client-launch');del self.pending[token]

    def close_all(self):
        for task in list(self.owned)[::-1]:
            self.budget(True);self.check_tasks('before-close')
            component=tuple(self.owned[task]['component'])
            token='close-'+str(task);self.record(token+'-intent',{'task':task,'source':self.owned[task],
                'method':'normal exact owned leaf remove','automatic_retry':False})
            self.actions+=1;self.removals+=1;del self.owned[task]
            self.pending[token]={'input_acknowledged':False}
            self.s.android(['/system/bin/cmd','activity','stack','remove',str(task)],15)
            end=time.monotonic()+8;verified=False
            while end-time.monotonic()>6:
                roots,tasks=self.stacks(token+'-readback',6)
                need(tasks-{task}==self.baseline|set(self.owned),'OTHER_TASKS_CHANGED_DURING_CLOSE')
                if task not in roots and task not in tasks:verified=True;break
                root=roots.get(task)
                shrinking=bool(root and task not in tasks and root['display']==root['user']==0
                    and root['freeform'] and root['children']==[])
                need(leaf(roots,task,component) or shrinking,'CLOSING_TASK_SCOPE_CHANGED')
                time.sleep(.2)
            need(verified,'OWNED_CLOSE_COMPLETION_UNKNOWN_NO_REPLAY')
            self.closed.append(task);del self.pending[token]

