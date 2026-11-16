"""Original finite WebView reads and single owned mutation admissions."""
import base64
import json
import re

class Policy:
    native_timeout=45
    def __init__(self,runtime):
        self.r=runtime;self.s=runtime.session;self.c=runtime.c;self.remove_sent=False
    def admit(self,argv,timeout,mutation,private):
        c,s=self.c,self.s
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int,float) and 5<timeout<=70 and type(mutation) is bool,
            'EXACT_BOUNDED_ORIGINAL_WEBVIEW_COMMAND')
        if private:
            c.need(s.ui_dispatch_admission==(argv,timeout,mutation),'ONE_CURRENT_TYPED_BACKEND_CALL');return
        if s.ordinary_admission==(argv,timeout,mutation):return
        c.need(not mutation and self.command(argv,timeout) is False,'EXACT_ONCE_ORIGINAL_MUTATION_ADMISSION')
    def command(self,argv,timeout):
        c,s,r=self.c,self.s,self.r;p=s.components['webview_protection.py']
        if argv==c.STACKS:
            c.need(timeout==15,'ORIGINAL_STACK_TIMEOUT');return False
        if argv==c.FOREGROUND:
            c.need(timeout==6,'ORIGINAL_WINDOW_TIMEOUT');return False
        if (argv,timeout) in p.identity_reads() or argv==p.HOME_RESOLVE and timeout==12:
            s.original_caller(['webview_protection.py']);return False
        diagnostics=[(['/system/bin/pm','list','packages','-U','--user','0'],15),
            (['/system/bin/date','+%s'],8),
            (['/system/bin/logcat','-b','events','-d','-v','epoch','-t','2048'],15),
            (['/system/bin/dumpsys','activity','exit-info','org.chromium.webview_shell'],15),
            (['/system/bin/logcat','--uid=10060','-b','crash','-d','-v','epoch','-t','512'],15)]
        if (argv,timeout) in diagnostics:
            c.need(s.kind=='webview_media11','ORIGINAL_MEDIA_DIAGNOSTICS_ONLY')
            s.original_caller(['webview_diagnostics.py']);return False
        if argv[:4]==['/system/bin/cmd','activity','stack','remove']:
            c.need(len(argv)==5 and timeout==15 and re.fullmatch('[1-9][0-9]*',argv[4]),'EXACT_ORIGINAL_TASK_REMOVAL')
            claim=r.selected_task();task=claim['task'];trial=s.trial
            c.need(not self.remove_sent and int(argv[4])==task and claim['cleanup_allowed'] is True
                and claim['prelaunch_absent'] is True and trial is not None and trial.owned is not None
                and trial.owned[0]==task and trial.pending=={'close-'+str(trial.removals)}
                and trial.removals==s.native_launches and s.last_stacks is not None,
                'ONE_ORIGINAL_PENDING_CLOSE_FOR_THIS_NEW_OWNED_TASK')
            roots,tasks=s.last_stacks
            c.need(tasks==set(claim['prelaunch_task_ids'])|{task} and r.tasks.exact_leaf(roots,task,r.scope['package']),
                'CURRENT_EXACT_OWNED_LEAF_WITH_UNCHANGED_OTHER_TASKS')
            intent=s.consume_original_intent('remove',argv)
            c.need(intent['caller']=={'source':s.trial_source,'function':'close_task'}
                and intent['value']['prelaunch_absent'] is True,'ORIGINAL_CLOSE_TASK_INTENT')
            c.write_new(r.root/'cleanup-attempted.json',{'scope':r.scope_ref,'phase':r.phase_lease_ref,
                'selected':claim,'argv':argv,'automatic_retry':False,'Binder_UID_cleanup_verified':False})
            self.remove_sent=True;return True
        raise RuntimeError('COMMAND_NOT_IN_ORIGINAL_WEBVIEW10_OR_MEDIA11')
    def observe(self,argv,raw):return None


def native_request(c,outer,request,action_used):
    c.need(type(request) is dict and request.get('display')==0 and request.get('accessibility_mode')=='none'
        and request.get('expected_package')==outer.get('package'),'ORIGINAL_NATIVE_PACKAGE_DISPLAY_MODE')
    if request.get('op') in ('meta','dump'):
        c.need(set(request)=={'op','expected_package','display','accessibility_mode'},'ONLY_ORIGINAL_NATIVE_READ_FIELDS')
        return False
    c.need(not action_used and outer.get('op') in ('click','set-text'),'NO_OTHER_NATIVE_ACTION_OR_REPLAY')
    expected={k:v for k,v in outer.items() if k in {'op','selector','value','display','accessibility_mode','method'}}
    expected['expected_package']=outer['package']
    c.need(request==expected,'UNCHANGED_FINAL_BACKEND_NATIVE_PROJECTION');return True


def backend_android(c,outer,argv,timeout,action_used):
    if argv==['/system/bin/screencap','-p']:
        c.need(timeout==20,'ORIGINAL_PNG_TIMEOUT');return False,True
    if len(argv)==8 and argv[:6]==['/system/bin/am','instrument','-w','-r','-e','request'] \
            and argv[-1]=='local.pocket4.actions.v2/.ActionRunner':
        c.need(timeout==70,'ORIGINAL_NATIVE_ACTION_TIMEOUT')
        raw=base64.b64decode(argv[6],validate=True);c.need(len(raw)<=65536,'ORIGINAL_NATIVE_REQUEST_BOUND')
        request=c.parse(raw)
        c.need(base64.b64encode(json.dumps(request,ensure_ascii=True,separators=(',',':')).encode()).decode()==argv[6],
            'UNCHANGED_ORIGINAL_NATIVE_ENCODING')
        return native_request(c,outer,request,action_used),False
    if outer.get('op')=='snapshot-tap':
        point=outer.get('coords')
        c.need(type(point) is list and len(point)==2 and all(type(x) is int for x in point)
            and outer.get('input_source')=='touch' and not action_used and timeout==30
            and argv==['/system/bin/input','-d','0','tap',str(point[0]),str(point[1])],
            'ONE_ORIGINAL_SNAPSHOT_BOUND_TOUCH_COMMAND')
        return True,False
    raise RuntimeError('NO_OTHER_WEBVIEW_BACKEND_ANDROID_COMMAND')
