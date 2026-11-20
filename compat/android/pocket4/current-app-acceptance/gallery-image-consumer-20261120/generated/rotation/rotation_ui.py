#!/usr/bin/python3 -I
"""Bounded owned-task UI adapter for the fixed rotation client and Gallery only.

Snapshot touch uses the unchanged frozen helper's two frame validations. A long
press uses the same two validations before one held-display input command.
No acknowledgement qualifies a document operation without its later readback.
"""
from pathlib import Path
import base64, copy, json, re, time

PACKAGE='org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03'
GALLERY='com.android.gallery3d'
CLIENT=PACKAGE+'.RotationActivity'
PICKER=GALLERY+'.app.GalleryActivity'
FILES=GALLERY+'.app.GalleryActivity'
MAX_ACTIONS=24


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
    if len(popup)==1 and user=='0' and package==GALLERY and activity==FILES:
        return {'package':package,'activity':activity,'window_token':popup[0][0],
            'task':int(task),'popup':True,'title':popup[0][1]}
    return None


class Adapter:
    def __init__(self,session,tx,root):
        self.s,self.tx,self.root=session,tx,Path(root)
        self.sequence=self.actions=self.launches=self.removals=0
        self.owned={};self.baseline=None;self.pending={};self.allowed=set();self.popup_grant=None
        self.allow_new=None;self.last=None;self.closed=[];self.adopted=[]
        self.more_options_attempted=False
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

    def validate_text_window(self,shot,frame,label,step):
        # The exact installed v2 setter resolves a unique semantic node, then
        # rechecks its window/node and verifies ACTION_SET_TEXT by value. A
        # blinking caret is not part of that operation's target identity.
        meta=frame['meta'];before=shot['scope'];after=meta['scope']
        need(all(scope.get('a11y_window_id_is_connection_scoped') is True
            and type(scope.get('window_id')) is int and scope['window_id']>=0
            for scope in (before,after)),'TEXT_CONNECTION_SCOPE_REQUIRED')
        need({k:v for k,v in before.items() if k!='window_id'}
            =={k:v for k,v in after.items() if k!='window_id'},'TEXT_WINDOW_CONTEXT_CHANGED')
        keys=('source','context_token','width','height','scope_bounds','scope_width',
            'scope_height','coordinate_space')
        need(all(meta[k]==shot[k] for k in keys),'TEXT_SCOPE_CONTEXT_CHANGED')
        self.record(label+'-semantic-window-'+step,{'same_window_context_and_geometry':True,
            'scope':after,'context_token':meta['context_token'],
            'pixel_equality_required':False,'input_dispatch_started':False})

    @staticmethod
    def same_semantic_node(nodes,node,package):
        matches=[n for n in nodes if n.get('package')==package
            and n.get('class')==node.get('class') and n.get('resource-id')==node.get('resource-id')
            and n.get('editable')==node.get('editable') and n.get('text')==node.get('text')]
        need(len(matches)==1,'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT')
        current=matches[0]
        need(all(type(n.get('window_id')) is int and n['window_id']>=0 for n in (node,current)),
            'EDITOR_CONNECTION_WINDOW_ID_REQUIRED')
        need({k:v for k,v in current.items() if k!='window_id'}
            =={k:v for k,v in node.items() if k!='window_id'},'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT')
        return current

    def input(self,obs,label,node,kind='tap',value=None,transition=None,popup=False,semantic_context=()):
        self.budget();need(not self.pending,'PENDING_INPUT_NOT_REPLAYABLE')
        self.check_tasks('before-'+label);need(self.focus()==obs['focus'],'INPUT_FOCUS_CHANGED')
        need(node.get('enabled') is True,'INPUT_NODE_DISABLED')
        shot=obs['screenshot'];scope=shot['scope'];point=self.box(obs,node)
        request={'op':'snapshot-tap','package':scope['package'],'display':0,'accessibility_mode':'none',
            'window_token':scope['window_token'],'frame_sha256':shot['frame_sha256'],
            'scope_sha256':shot['scope_sha256'],'context_token':shot['context_token'],'coords':point,'input_source':'touch'}
        if kind=='set-text':
            need(node.get('editable') is True and node.get('password') is not True
                and node.get('focused') is True,'FOCUSED_EDITABLE_NONPASSWORD_REQUIRED')
            selector={'package':scope['package'],'class':node['class'],'editable':True,'enabled':True,'focused':True}
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
            frame=self.s.helper.capture(snapshot_request)
            if kind=='set-text':self.validate_text_window(shot,frame,label,'first')
            else:self.s.helper.validate_snapshot(snapshot_request,frame)
            if kind=='set-text':
                fresh=self.s.helper.ui({'op':'dump','expected_package':scope['package'],
                    'display':0,'accessibility_mode':'none'})
                self.record(label+'-fresh-native',fresh)
                need(fresh.get('ok') is True and fresh.get('outcome_unknown') is not True
                    and fresh.get('accessibility_mode_restoration_verified') is True,'FRESH_NATIVE_NOT_VERIFIED')
                current=self.same_semantic_node(fresh.get('nodes',[]),node,scope['package'])
                for context_node in semantic_context:
                    self.same_semantic_node(fresh.get('nodes',[]),context_node,scope['package'])
                # Each helper.ui dump creates a separate instrumentation connection.
                # Actual flow08 differs only in its connection-scoped window_id.
                # WM token, task, scope, context and geometry remain bound below.
                self.record(label+'-cross-connection-editor-verified',{
                    'original_connection_window_id':node['window_id'],'fresh_connection_window_id':current['window_id'],
                    'all_other_node_fields_equal':True,'wm_window_token':scope['window_token']})
            frame=self.s.helper.capture(snapshot_request)
            if kind=='set-text':self.validate_text_window(shot,frame,label,'last')
            else:self.s.helper.validate_snapshot(snapshot_request,frame)
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

    def open_more_options(self,photo,shown_reply=None):
        """One actual ImageButton ACTION_CLICK; no pointer or whole-frame match.

        The native runner resolves and revalidates its window and complete node
        twice inside the same call. The outer WM token is not a native argument;
        owned task/focus checks surround the fresh observation and dispatch.
        All other input methods, including Rotate right, remain unchanged.
        """
        label='rotation-more-options';self.budget()
        need(not self.more_options_attempted,'MORE_OPTIONS_NOT_REPLAYABLE')
        self.more_options_attempted=True
        focus=photo['focus'];shot=photo['screenshot'];scope=shot['scope']
        need((focus['package'],focus['activity'])==(GALLERY,FILES) and not focus.get('popup')
            and self.allowed_focus(focus),'MORE_OPTIONS_OUTSIDE_OWNED_PHOTO')
        if shown_reply is None:need(not self.pending,'PENDING_INPUT_NOT_REPLAYABLE')
        else:
            need(set(self.pending)=={'show-owned-photo-bars'}
                and self.pending['show-owned-photo-bars'].get('input_acknowledged') is True
                and shown_reply.get('ok') is True and shown_reply.get('input_command_completed') is True
                and shown_reply.get('outcome_unknown') is not True and isinstance(shown_reply.get('after'),dict),
                'SHOW_BARS_ACK_AND_CAPTURE_REQUIRED')
            # This is the actual post-tap capture, not a newly invented frame.
            # Only its scope is used for the subsequent semantic selection.
            self.validate_text_window(shot,{'meta':shown_reply['after']},label,'after-show')
            shot=shown_reply['after'];scope=shot['scope']
        need(scope['package']==GALLERY and scope['activity']==FILES
            and scope['window_token']==focus['window_token'] and scope['display_id']==0
            and shot['scope_bounds']==scope['window_bounds']
            and self.s.helper.context_token(scope,shot['scope_bounds'],[shot['width'],shot['height']])==shot['context_token'],
            'MORE_OPTIONS_REFERENCE_CONTEXT_CHANGED')
        self.check_tasks(label+'-native-before');need(self.focus()==focus,'MORE_OPTIONS_FOCUS_CHANGED')
        self.s.guard()
        native=self.s.helper.ui({'op':'dump','expected_package':GALLERY,'display':0,'accessibility_mode':'none'})
        self.s.guard();self.record(label+'-native-observation',{'native':native,'reference_capture':shot,
            'fresh_pixels_captured_by_this_observation':False,'pixel_equality_required':False})
        context=native.get('window_context',{});window=context.get('selected_window',{});root=context.get('root',{})
        need(native.get('ok') is True and native.get('outcome_unknown') is not True
            and native.get('accessibility_mode_restoration_verified') is True
            and context.get('snapshot_complete') is True and context.get('null_child_count')==0
            and context.get('truncated') is False and context.get('display_id')==0
            and window.get('display_id')==0 and window.get('type')==1
            and window.get('active') is True and window.get('focused') is True
            and root.get('package')==GALLERY and root.get('present') is True and root.get('visible') is True
            and window.get('root')==root and type(window.get('window_id')) is int and window['window_id']>=0
            and root.get('window_id')==window['window_id']
            and window.get('bounds')==root.get('bounds')==scope['window_bounds']
            and all(context.get(key)==value for key,value in scope['accessibility_query'].items()),
            'MORE_OPTIONS_NATIVE_CONTEXT_INCOMPLETE')
        need(self.focus()==focus,'MORE_OPTIONS_NATIVE_FOCUS_CHANGED')
        obs={'focus':focus,'screenshot':shot,'nodes':[n for n in native.get('nodes',[])
            if n.get('package')==GALLERY and n.get('visible') is True]}
        if shown_reply is not None:
            self.record('input-observation-reconciled',{'token':'show-owned-photo-bars',
                'original':self.pending['show-owned-photo-bars'],'action_replayed':False,
                'business_success_verified':False,'fresh_native_owned_context_verified':True})
            del self.pending['show-owned-photo-bars']
        bar=self.one(obs,lambda n:n.get('resource-id')=='android:id/action_bar'
            and n.get('class')=='android.view.ViewGroup' and n.get('enabled') is True,
            'ONE_ACTUAL_PHOTO_ACTION_BAR_REQUIRED')
        node=self.one(obs,lambda n:n.get('class')=='android.widget.ImageButton'
            and n.get('resource-id')=='' and n.get('text')=='' and n.get('content-desc')=='More options'
            and n.get('enabled') is True and n.get('clickable') is True
            and n.get('editable') is False and n.get('password') is False
            and 16 in n.get('supported_actions',[]),'ONE_ACTUAL_MORE_OPTIONS_IMAGEBUTTON')
        self.box(obs,bar);self.box(obs,node);a,b=bar['bounds_array'],node['bounds_array']
        need(bar.get('window_id')==node.get('window_id')==window['window_id']
            and a[0]<=b[0]<b[2]<=a[2] and a[1]<=b[1]<b[3]<=a[3],
            'MORE_OPTIONS_NOT_IN_ACTUAL_ACTION_BAR')
        def stable(n):
            need(isinstance(n,dict) and type(n.get('window_id')) is int and n['window_id']>=0,
                'MORE_OPTIONS_CONNECTION_ID_REQUIRED')
            return {key:value for key,value in n.items() if key!='window_id'}
        previous=[n for n in photo['nodes'] if n.get('content-desc')=='More options']
        need(len(previous)<=1 and (not previous or stable(previous[0])==stable(node)),
            'MORE_OPTIONS_OBSERVED_NODE_CHANGED')
        selector={key:node[field] for key,field in (('package','package'),('class','class'),
            ('id','resource-id'),('text','text'),('desc','content-desc'),('enabled','enabled'),
            ('clickable','clickable'),('editable','editable'),('focused','focused'),
            ('scrollable','scrollable'),('selected','selected'),('checked','checked'))}
        aliases={'id':'resource-id','desc':'content-desc'}
        matches=[n for n in native.get('nodes',[]) if all(n.get(aliases.get(k,k))==v for k,v in selector.items())]
        need(len(matches)==1 and matches[0]==node,'MORE_OPTIONS_SELECTOR_NOT_UNIQUE')
        self.check_tasks(label+'-last');need(self.focus()==focus,'MORE_OPTIONS_LAST_FOCUS_CHANGED')
        request={'op':'click','method':'accessibility','expected_package':GALLERY,'display':0,
            'accessibility_mode':'none','selector':selector}
        self.record(label+'-intent',{'request':request,'node':node,'action_bar':bar,'focus':focus,
            'reference_context_token':shot['context_token'],'reference_capture_unix_ms':shot['captured_unix_ms'],
            'native_action':'ACTION_CLICK','pointer_coordinates_used':False,'automatic_retry':False})
        self.actions+=1;self.pending[label]={'input_acknowledged':False,'kind':'native-more-options'}
        self.s.guard()
        try:reply=self.s.helper.ui(request)
        except BaseException as exc:
            details=getattr(exc,'details',{})
            if isinstance(exc,self.s.helper.ControlError) and details.get('outcome_unknown') is False \
                    and details.get('automatic_retry') is False \
                    and details.get('accessibility_mode_restoration_verified') is True:
                self.record(label+'-explicit-no-effect',{'error':str(exc),'details':details,'action_replayed':False})
                del self.pending[label]
            raise
        self.s.guard();self.record(label+'-response',reply)
        need(reply.get('ok') is True and reply.get('performed')=='click' and reply.get('outcome_unknown') is not True
            and reply.get('accessibility_mode_restoration_verified') is True
            and reply.get('visual_verified') is False and reply.get('business_success_verified') is False
            and reply.get('target')==reply.get('actual_target')
            and stable(reply.get('actual_target'))==stable(node),'MORE_OPTIONS_NATIVE_RECEIPT_UNRESOLVED')
        self.pending[label]['input_acknowledged']=True
        self.popup_grant={'task':focus['task'],'parent':focus['window_token']}
        return reply

    def launch(self):
        self.budget();need(self.launches<2,'ONLY_TWO_NATIVE_HELPER_TASKS');roots,tasks=self.stacks('before-client-launch')
        if self.baseline is None:
            need(not any(c['component'].split('/')[0] in (PACKAGE,GALLERY) for r in roots.values() for c in r['children']),
                'PREEXISTING_CLIENT_OR_DOCUMENTS_TASK_PRESERVED');self.baseline=tasks
        need(tasks==self.baseline and not self.owned,'PREVIOUS_OWNED_TASKS_NOT_CLOSED')
        argv=[*self.tx.ALEX_PREFIX,'launch',PACKAGE,'--component',PACKAGE+'/.RotationActivity','--json']
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

    def bind_gallery_route(self,source,album_uri,caller_uid):
        """Admit only the actual helper's exact album Activity, in either task form."""
        need(source in self.pending and self.pending[source].get('input_acknowledged') is True
            and self.allow_new=={'source':source,'component':(GALLERY,FILES)},
            'ACKNOWLEDGED_EXACT_HELPER_ROUTE_REQUIRED')
        need(re.fullmatch(r'content://media/external/images/media\?bucketId=-?\d+',album_uri)
            and type(caller_uid) is int and 10000<=caller_uid<20000,'OWNED_ALBUM_CALLER_SCOPE')
        roots,tasks=self.stacks('album-route-before-admission')
        need(self.baseline<=tasks and set(self.owned)<=tasks,'ORIGINAL_OR_OWNED_TASK_LOST')
        added=tasks-self.baseline-set(self.owned)
        need(len(self.owned)==1 and len(added)<=1,'ONE_SOURCE_HELPER_TASK_REQUIRED')
        if added:
            task=next(iter(added));need(leaf(roots,task,(GALLERY,FILES)),'NEW_TASK_NOT_EXACT_GALLERY')
            need(all(leaf(roots,old,tuple(info['component'])) for old,info in self.owned.items()),
                'HELPER_TASK_CHANGED_DURING_NEW_GALLERY_ROUTE')
            stack_component=(GALLERY,FILES)
        else:
            task=next(iter(self.owned))
            need(task in self.owned and tuple(self.owned[task]['component'])==(PACKAGE,CLIENT),
                'SAME_TASK_ROUTE_NOT_FROM_THIS_HELPER')
            # A task's stack-list component can be its base Activity. Keep the
            # exact actually observed leaf; bind the foreground route below.
            permitted=[c for c in ((PACKAGE,CLIENT),(GALLERY,FILES)) if leaf(roots,task,c)]
            need(len(permitted)==1,'SAME_TASK_LEAF_OUTSIDE_HELPER_OR_GALLERY')
            stack_component=permitted[0]
        foreground=self.focus()
        need(foreground is not None and not foreground.get('popup')
            and (foreground['package'],foreground['activity'],foreground['task'])==(GALLERY,FILES,task),
            'ACTUAL_GALLERY_TOP_FOCUS_REQUIRED')
        raw=self.s.android(['/system/bin/dumpsys','activity','activities',GALLERY],12).decode()
        blocks=re.split(r'(?=^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{)',raw,flags=re.M)
        expression=r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{[^\n]*\bu0 '+re.escape(GALLERY)+r'/(?:\.app\.GalleryActivity|com\.android\.gallery3d\.app\.GalleryActivity) t'+str(task)+r'\b'
        selected=[block for block in blocks if re.search(expression,block)]
        need(len(selected)==1,'EXACT_TOP_GALLERY_ACTIVITY_RECORD_REQUIRED')
        block=selected[0]
        callers=re.findall(r'\blaunchedFromUid=(\d+)\s+launchedFromPackage=(\S+)',block)
        need(callers==[(str(caller_uid),PACKAGE)],'ALBUM_ROUTE_CALLER_NOT_OWNED_HELPER')
        intent_lines=[line.strip() for line in block.splitlines() if re.match(r'\s*Intent \{',line)]
        need(len(intent_lines)==1 and re.search(r'\bact=android\.intent\.action\.VIEW\b',intent_lines[0])
            and re.search(r'\bdat='+re.escape(album_uri)+r'(?:\s|\})',intent_lines[0])
            and re.search(r'\btyp=vnd\.android\.cursor\.dir/image(?:\s|\})',intent_lines[0]),
            'ACTUAL_ALBUM_INTENT_DIFFERS')
        need(self.focus()==foreground,'ALBUM_TOP_FOCUS_CHANGED_DURING_ROUTE_BINDING')
        self.record('actual-owned-album-route',{'task':task,'caller_uid':caller_uid,
            'caller_package':PACKAGE,'component':[GALLERY,FILES],'album_uri':album_uri,
            'new_task':bool(added),'actual_stack_component':stack_component,
            'foreground':foreground,'actual_activity_block':block})
        previous=self.owned.get(task)
        self.owned[task]={'component':stack_component,'source':source,'previous_owned_route':previous,
            'routed_foreground':(GALLERY,FILES)}
        if added:self.adopted.append(task)
        self.check_tasks('album-route-admitted')
        return task

    def tap_pattern(self,obs,proof,label,purpose='thumbnail'):
        """The fixed photo/thumbnail proof gives a hit region; snapshot remains strict."""
        self.budget();need(not self.pending,'PENDING_INPUT_NOT_REPLAYABLE')
        self.check_tasks('before-'+label);need(self.focus()==obs['focus'],'PATTERN_FOCUS_CHANGED')
        need((obs['focus']['package'],obs['focus']['activity'])==(GALLERY,FILES)
            and not obs['focus'].get('popup'),'ONLY_OWNED_GALLERY_PATTERN_WINDOW')
        if purpose=='thumbnail':
            need(proof.get('thumbnail_verified') is True and proof.get('full_image_verified') is False,
                'ONLY_PROVEN_OWNED_THUMBNAIL_TAP')
        else:
            need(purpose=='show-photo-bars' and proof.get('full_image_verified') is True
                and proof.get('thumbnail_verified') is False and proof.get('clockwise_degrees')==0
                and not any(n.get('content-desc')=='More options' for n in obs['nodes']),
                'ONLY_ORIGINAL_FULL_PHOTO_WITH_HIDDEN_CONTROLS')
        shot=obs['screenshot'];scope=shot['scope'];bounds=proof['scope_pattern_bounds']
        need(proof['scope_size']==[shot['scope_width'],shot['scope_height']]
            and len(bounds)==4 and all(type(v) is int for v in bounds)
            and 0<=bounds[0]<bounds[2]<=shot['scope_width']
            and 0<=bounds[1]<bounds[3]<=shot['scope_height'],'PATTERN_BOUNDS_NOT_IN_EXACT_CAPTURE')
        x=shot['scope_bounds'][0]+(bounds[0]+bounds[2])//2
        y=shot['scope_bounds'][1]+(bounds[1]+bounds[3])//2
        request={'op':'snapshot-tap','package':GALLERY,'display':0,'accessibility_mode':'none',
            'window_token':scope['window_token'],'frame_sha256':shot['frame_sha256'],
            'scope_sha256':shot['scope_sha256'],'context_token':shot['context_token'],
            'coords':[x,y],'input_source':'touch'}
        self.record(label+'-intent',{'request':request,'pattern_proof':proof,'purpose':purpose,'automatic_retry':False})
        self.actions+=1;self.pending[label]={'input_acknowledged':False,'kind':'owned-pattern-'+purpose}
        self.s.guard()
        try:reply=self.s.helper.dispatch(request)
        except BaseException as exc:
            details=getattr(exc,'details',{})
            if details.get('outcome_unknown') is not True and details.get('action_taken') is False:
                self.record(label+'-explicit-no-effect',{'error':str(exc),'details':details,'action_replayed':False})
                del self.pending[label]
            raise
        self.s.guard();self.record(label+'-response',reply)
        need(reply.get('ok') is True and reply.get('input_command_completed') is True
            and (reply.get('outcome_unknown') is not True or reply.get('post_action_observation_available') is False),
            'PATTERN_TOUCH_UNKNOWN_NO_REPLAY')
        self.pending[label].update(input_acknowledged=True,post_capture_outcome_unknown=reply.get('outcome_unknown') is True)
        return reply

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

    def back(self,obs,label):
        """One BACK bound to the exact observed owned picker/window; never repeated unknown."""
        self.budget();need(not self.pending,'PENDING_INPUT_NOT_REPLAYABLE')
        need((obs['focus']['package'],obs['focus']['activity'])==(GALLERY,PICKER)
            and not obs['focus'].get('popup'),'BACK_ONLY_FROM_OWNED_PICKER')
        self.check_tasks('before-'+label);need(self.focus()==obs['focus'],'BACK_FOCUS_CHANGED')
        shot=obs['screenshot'];scope=shot['scope']
        request={'package':scope['package'],'display':0,'accessibility_mode':'none',
            'window_token':scope['window_token'],'frame_sha256':shot['frame_sha256'],
            'scope_sha256':shot['scope_sha256'],'context_token':shot['context_token']}
        for _ in range(2):
            frame=self.s.helper.capture(request);self.s.helper.validate_snapshot(request,frame)
        need(self.focus()==obs['focus'],'FINAL_BACK_FOCUS_CHANGED')
        actual=self.s.helper.window_state(scope['package'],scope['window_token'],0,'none')
        need(self.s.helper.stable_window(actual)==self.s.helper.stable_window(scope),'BACK_WINDOW_CONTEXT_CHANGED')
        self.record(label+'-intent',{'key':'KEYCODE_BACK','snapshot':request,'focus':obs['focus'],
            'automatic_retry':False,'business_success_verified':False})
        self.actions+=1;self.pending[label]={'input_acknowledged':False,'kind':'back'}
        self.s.guard();self.s.android(['/system/bin/input','keyboard','-d','0','keyevent','KEYCODE_BACK'],10)
        self.s.guard();self.pending[label]['input_acknowledged']=True
        self.record(label+'-response',{'input_command_completed':True,'business_success_verified':False})
