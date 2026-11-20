"""Exact SAF11 command admission; original pending tasks never gain replay rights."""
import base64
import json
import re

DOCS='com.android.documentsui'
PROVIDER='com.android.externalstorage'
NATIVE='local.pocket4.actions.v2'

class Policy:
    def __init__(self,session):
        self.s=session;self.c=session.c;self.install_sent=self.uninstall_sent=False;self.remove_sent=set()

    def command(self,argv,timeout):
        s,c,f=self.s,self.c,self.s.case;package=s.names.PACKAGE
        c.need(type(argv) is list and argv and all(type(v) is str and v and '\0' not in v for v in argv)
            and type(timeout) in (int,float) and 5<timeout<=70,'EXACT_BOUNDED_SAF11_COMMAND')
        caller=s.original_caller(['documents_saf_core.py','documents_saf_ui.py'])
        if argv==['/system/bin/cmd','activity','stack','list']:
            c.need(timeout in (6,15) and caller=={'source':'documents_saf_ui.py','function':'stacks'},'ORIGINAL_SAF_TASK_READ');return False
        if argv==['/system/bin/dumpsys','window','displays']:
            c.need(timeout==6 and caller=={'source':'documents_saf_ui.py','function':'focus'},'ORIGINAL_SAF_FOCUS_READ');return False
        if len(argv)==3 and argv[:2]==['/system/bin/dumpsys','package']:
            c.need(argv[2] in (DOCS,PROVIDER,package) and timeout==20 and caller['source']=='documents_saf_core.py'
                and caller['function'] in ('absent','identity'),'ORIGINAL_SAF_PACKAGE_METADATA');return False
        if len(argv)==5 and argv[:4]==['/system/bin/pm','path','--user','0']:
            c.need(argv[4] in (DOCS,PROVIDER,package) and timeout==20
                and caller=={'source':'documents_saf_core.py','function':'identity'},'ORIGINAL_SAF_SINGLE_APK_PATH');return False
        if argv==['/system/bin/pm','list','packages','-u','-U',package]:
            c.need(timeout==20 and caller=={'source':'documents_saf_core.py','function':'absent'},'ORIGINAL_SAF_ABSENT_ALL_USERS');return False
        if argv==['/system/bin/dumpsys','activity','package',package,'permissions']:
            c.need(timeout==20 and caller=={'source':'documents_saf_core.py','function':'grants'},'ORIGINAL_EXACT_HELPER_URI_GRANTS');return False
        if argv==['/system/bin/pm','list','packages','-U','--user','0','android']:
            c.need(timeout==15 and caller=={'source':'documents_saf_ui.py','function':'helper_package_name'}
                and f is not None and s.ui_owner is f.ui and f.ui.resolver_binding is None
                and s.last_focus is not None and s.last_focus['package']=='android'
                and s.last_focus['activity']=='com.android.internal.app.ResolverActivity'
                and not s.last_focus['popup'],'ORIGINAL_SOURCE_ACK_BOUND_SYSTEM_RESOLVER_UID_READ');return False
        c.need(f is not None and s.active_api is None,'ORIGINAL_SAF_ORDINARY_MUTATION_CONTEXT')
        stage='/data/local/tmp/pocket4-owned-saf-'+s.names.RUN+'/owned-saf.apk'
        if argv==['/system/bin/pm','install','-R','-t','--user','0',stage]:
            c.need(timeout==60 and caller=={'source':'documents_saf_core.py','function':'install'}
                and s.phase=='business' and not self.install_sent and f.install_pending and f.installed is None
                and f.staged is not None and f.staged['guest']==stage and not f.ui.owned and not f.ui.pending,
                'ONCE_ORIGINAL_CREATE_ONLY_SAF_HELPER_INSTALL')
            s.consume_intent('helper-install',argv);self.install_sent=True;return True
        if argv==['/system/bin/pm','uninstall',package]:
            c.need(timeout==60 and caller=={'source':'documents_saf_core.py','function':'cleanup'}
                and s.phase=='final_cleanup' and self.install_sent and not self.uninstall_sent
                and f.uninstall_pending and not f.install_pending and f.installed is not None
                and not f.ui.owned and not f.ui.pending,'ONCE_KNOWN_SAF_HELPER_UNINSTALL')
            s.consume_intent('helper-uninstall',argv);self.uninstall_sent=True;return True
        if argv[:4]==['/system/bin/cmd','activity','stack','remove']:
            c.need(caller=={'source':'documents_saf_ui.py','function':'close_all'} and len(argv)==5 and timeout==15
                and re.fullmatch('[1-9][0-9]*',argv[4]),'ORIGINAL_NORMAL_SAF_OWNED_REMOVE')
            task=int(argv[4]);token='close-'+argv[4];claim=s.claimed_tasks.get(task)
            # The original SAF cleanup may independently close a known exact
            # owned task after an unknown UI result. It must not clear that UI
            # pending state or authorize package/file cleanup or a second remove.
            c.need(claim is not None and claim['source_ref']['sha256'] not in self.remove_sent
                and task not in f.ui.owned and token in f.ui.pending
                and f.ui.pending[token]['input_acknowledged'] is False and s.last_stacks is not None,
                'ONLY_BURNED_ONCE_ORIGINAL_SAF_TASK_AUTHORITY')
            roots,tasks=s.last_stacks
            c.need(task not in f.ui.baseline and tasks==f.ui.baseline|set(f.ui.owned)|{task}
                and s.components['documents_saf_ui.py'].leaf(roots,task,tuple(claim['component'])),
                'ACTUAL_SAF_SOURCE_BOUND_FREEFORM_LEAF')
            s.consume_intent('task-remove',argv);self.remove_sent.add(claim['source_ref']['sha256']);return True
        if argv[:4]==['/system/bin/input','-d','0','swipe']:
            c.need(caller=={'source':'documents_saf_ui.py','function':'input'} and timeout==10
                and len(argv)==9 and argv[-1]=='650' and argv[4:6]==argv[6:8],
                'ONLY_ORIGINAL_OBSERVED_650MS_LONG_PRESS')
            item=s.consume_intent('long-press',argv);s.admit_direct_input(item,'long-press');return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_SAF11_SCOPE')

    def observe(self,argv,raw):
        s,c=self.s,self.c
        if len(argv)==5 and argv[:4]==['/system/bin/pm','path','--user','0']:
            paths=c.apk_paths(raw);c.need(len(paths)==1,'ORIGINAL_SAF_SINGLE_APK');s.apk_paths[argv[-1]]=paths[0]
        if argv==['/system/bin/cmd','activity','stack','list']:
            s.last_stacks=s.components['documents_saf_ui.py'].parse_stacks(raw.decode('utf-8','strict'));s.observe_owned_tasks()

def native_request(c,outer,request,action_used):
    c.need(type(request) is dict and request.get('display')==0 and request.get('accessibility_mode')=='none'
        and request.get('expected_package')==outer.get('package',outer.get('expected_package')),
        'EXACT_ORIGINAL_SAF_NATIVE_PACKAGE')
    if request.get('op') in ('meta','dump'):
        c.need(set(request)=={'op','expected_package','display','accessibility_mode'},'ONLY_ORIGINAL_SAF_NATIVE_READ_FIELDS');return False
    c.need(not action_used and outer.get('op')=='set-text','ONLY_ORIGINAL_SAF_SET_TEXT_NATIVE_EFFECT')
    expected={k:v for k,v in outer.items() if k in {'op','selector','value','display','accessibility_mode'}}
    expected['expected_package']=outer['package']
    c.need(request==expected,'UNCHANGED_FINAL_BACKEND_SAF_SET_TEXT_PROJECTION');return True

def backend_android(c,outer,argv,timeout,action_used):
    if argv==['/system/bin/screencap','-p']:
        c.need(timeout==20,'ORIGINAL_SAF_SCREENSHOT_TIMEOUT');return False,True
    if len(argv)==8 and argv[:6]==['/system/bin/am','instrument','-w','-r','-e','request']:
        c.need(argv[-1]==NATIVE+'/.ActionRunner' and timeout==70,'EXACT_ORIGINAL_SAF_NATIVE_RUNNER')
        raw=base64.b64decode(argv[6],validate=True);c.need(len(raw)<=65536,'BOUNDED_SAF_NATIVE_REQUEST')
        request=c.parse(raw)
        c.need(base64.b64encode(json.dumps(request,ensure_ascii=True,separators=(',',':')).encode()).decode()==argv[6],
            'ORIGINAL_SAF_NATIVE_WIRE_ENCODING')
        return native_request(c,outer,request,action_used),False
    if outer.get('op')=='snapshot-tap':
        point=outer.get('coords')
        c.need(type(point) is list and len(point)==2 and all(type(x) is int for x in point)
            and outer.get('input_source')=='touch' and not action_used and timeout==30
            and argv==['/system/bin/input','-d','0','tap',str(point[0]),str(point[1])],
            'ONLY_ORIGINAL_SAF_CURRENT_FRAME_BOUND_TOUCH');return True,False
    raise RuntimeError('NO_OTHER_SAF_BACKEND_ANDROID_COMMAND')
