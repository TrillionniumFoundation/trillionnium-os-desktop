"""Original Features10 command set, source-bound intents and owned tasks.

No arbitrary command/dispatch route is provided. Host retirement is independent
of original Android task, URI-grant and temporary-package cleanup evidence.
"""
import base64
import json
import re

DOCS='com.android.documentsui'
PROVIDER='com.android.externalstorage'
NATIVE='local.pocket4.actions.v2'


class Policy:
    def __init__(self, session):
        self.s=session; self.c=session.c
        self.install_sent=self.uninstall_sent=False
        self.remove_sent=set(); self.direct_inputs=set()

    def command(self, argv, timeout):
        s,c,f=self.s,self.c,self.s.case; package=s.names.PACKAGE
        c.need(type(argv) is list and argv and all(type(v) is str and v and '\0' not in v for v in argv)
            and type(timeout) in (int,float) and 5<timeout<=70,'EXACT_BOUNDED_DOCUMENTS_COMMAND')
        caller=s.original_caller(['documents_features_core.py','documents_features_ui.py',
            'documents_package_fixture.py','documents_diagnostics.py'])
        if argv==['/system/bin/cmd','activity','stack','list']:
            c.need(timeout in (6,15) and caller['source']=='documents_features_ui.py','ORIGINAL_TASK_READ');return False
        if argv==['/system/bin/dumpsys','window','displays']:
            c.need(timeout==6 and caller['source']=='documents_features_ui.py','ORIGINAL_FOCUS_READ');return False
        if len(argv)==3 and argv[:2]==['/system/bin/dumpsys','package']:
            c.need(argv[2] in (DOCS,PROVIDER,package) and timeout in (15,20)
                and caller['source'] in ('documents_package_fixture.py','documents_diagnostics.py'),
                'ORIGINAL_PACKAGE_METADATA_ONLY');return False
        if len(argv)==5 and argv[:4]==['/system/bin/pm','path','--user','0']:
            c.need(argv[4] in (DOCS,PROVIDER,package) and timeout==20
                and caller['source']=='documents_package_fixture.py','ORIGINAL_PACKAGE_APK_PATH');return False
        reads=[(['/system/bin/pm','list','packages','-u','-U',package],20),
            (['/system/bin/dumpsys','activity','package',package,'permissions'],20)]
        if (argv,timeout) in reads:
            c.need(caller['source']=='documents_package_fixture.py','ORIGINAL_HELPER_PACKAGE_AND_GRANTS');return False
        diagnostic=[(['/system/bin/pm','list','packages','-U','--user','0'],15),
            (['/system/bin/date','+%s'],8),
            (['/system/bin/logcat','-b','events','-d','-v','epoch','-t','2048'],15)]
        for pkg,uid in ((DOCS,10022),(PROVIDER,10024)):
            diagnostic.extend([(['/system/bin/dumpsys','activity','exit-info',pkg],15),
                (['/system/bin/logcat','--uid='+str(uid),'-b','crash','-d','-v','epoch','-t','512'],15)])
        if (argv,timeout) in diagnostic:
            c.need(caller['source']=='documents_diagnostics.py','ORIGINAL_BOUNDED_TARGET_DIAGNOSTICS');return False
        if argv==['/system/bin/content','query','--uri','content://com.android.externalstorage.documents/root',
                  '--projection','root_id:flags:title:document_id:available_bytes']:
            c.need(timeout==15 and caller=={'source':'documents_features_core.py','function':'primary_root_metadata'},
                'ONLY_ORIGINAL_PRIMARY_ROOT_METADATA_PROJECTION');return False
        c.need(f is not None and s.active_api is None,'ORIGINAL_CASE_ORDINARY_MUTATION_CONTEXT')
        if argv[:4]==['/system/bin/cmd','activity','stack','remove']:
            c.need(caller=={'source':'documents_features_ui.py','function':'close_all'} and len(argv)==5
                and timeout==15 and re.fullmatch('[1-9][0-9]*',argv[4]),'ORIGINAL_NORMAL_OWNED_REMOVE')
            task=int(argv[4]);token='close-'+argv[4];claim=s.claimed_tasks.get(task)
            c.need(claim is not None and claim['source_ref']['sha256'] not in self.remove_sent
                and task not in f.ui.owned and set(f.ui.pending)=={token}
                and f.ui.pending[token]['input_acknowledged'] is False and s.last_stacks is not None
                and not f.helper_pending and f.operation_pending is None and not f.pkg.install_pending and not f.pkg.uninstall_pending,
                'UNKNOWN_INPUT_OR_UNOWNED_TASK_CANNOT_BE_REMOVED')
            roots,tasks=s.last_stacks
            c.need(task not in f.ui.baseline and tasks==f.ui.baseline|set(f.ui.owned)|{task}
                and s.components['documents_features_ui.py'].leaf(roots,task,tuple(claim['component'])),
                'ACTUAL_CURRENT_SOURCE_BOUND_FREEFORM_LEAF')
            s.consume_intent('task-remove',argv);self.remove_sent.add(claim['source_ref']['sha256']);return True
        if argv[:2]==['/system/bin/input','keyboard']:
            c.need(caller=={'source':'documents_features_ui.py','function':'back'} and timeout==10
                and argv==['/system/bin/input','keyboard','-d','0','keyevent','KEYCODE_BACK'],
                'ONLY_ORIGINAL_OWNED_PICKER_BACK')
            item=s.consume_intent('back',argv);s.admit_direct_input(item,'back');return True
        if argv[:4]==['/system/bin/input','-d','0','swipe']:
            c.need(caller=={'source':'documents_features_ui.py','function':'input'} and timeout==10
                and len(argv)==9 and argv[-1]=='650' and argv[4:6]==argv[6:8],
                'ONLY_ORIGINAL_OBSERVED_650MS_LONG_PRESS')
            item=s.consume_intent('long-press',argv);s.admit_direct_input(item,'long-press');return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_DOCUMENTS_FEATURES_SCOPE')

    def observe(self,argv,raw):
        s,c=self.s,self.c
        if len(argv)==5 and argv[:4]==['/system/bin/pm','path','--user','0']:
            paths=c.apk_paths(raw)
            c.need(len(paths)==1,'ORIGINAL_SINGLE_APK_PATH');s.apk_paths[argv[-1]]=paths[0]
        if argv==['/system/bin/cmd','activity','stack','list']:
            s.last_stacks=s.components['documents_features_ui.py'].parse_stacks(raw.decode('utf-8','strict'))
            s.observe_owned_tasks()


def native_request(c,outer,request,action_used):
    c.need(type(request) is dict and request.get('display')==0 and request.get('accessibility_mode')=='none'
        and request.get('expected_package')==outer.get('package',outer.get('expected_package')),
        'EXACT_ORIGINAL_DOCUMENTS_NATIVE_PACKAGE')
    if request.get('op') in ('meta','dump'):
        c.need(set(request)=={'op','expected_package','display','accessibility_mode'},'ONLY_ORIGINAL_NATIVE_READ_FIELDS');return False
    c.need(not action_used and outer.get('op')=='set-text','ONLY_ORIGINAL_DOCUMENTS_SET_TEXT_NATIVE_EFFECT')
    expected={k:v for k,v in outer.items() if k in {'op','selector','value','display','accessibility_mode'}}
    expected['expected_package']=outer['package']
    c.need(request==expected,'UNCHANGED_FINAL_BACKEND_SET_TEXT_PROJECTION');return True


def backend_android(c,outer,argv,timeout,action_used):
    if argv==['/system/bin/screencap','-p']:
        c.need(timeout==20,'ORIGINAL_SCREENSHOT_TIMEOUT');return False,True
    if len(argv)==8 and argv[:6]==['/system/bin/am','instrument','-w','-r','-e','request']:
        c.need(argv[-1]==NATIVE+'/.ActionRunner' and timeout==70,'EXACT_ORIGINAL_NATIVE_RUNNER')
        raw=base64.b64decode(argv[6],validate=True);c.need(len(raw)<=65536,'BOUNDED_NATIVE_REQUEST')
        request=c.parse(raw)
        c.need(base64.b64encode(json.dumps(request,ensure_ascii=True,separators=(',',':')).encode()).decode()==argv[6],
            'ORIGINAL_NATIVE_WIRE_ENCODING')
        return native_request(c,outer,request,action_used),False
    if outer.get('op')=='snapshot-tap':
        point=outer.get('coords')
        c.need(type(point) is list and len(point)==2 and all(type(x) is int for x in point)
            and outer.get('input_source')=='touch' and not action_used and timeout==30
            and argv==['/system/bin/input','-d','0','tap',str(point[0]),str(point[1])],
            'ONLY_ORIGINAL_CURRENT_FRAME_BOUND_TOUCH');return True,False
    raise RuntimeError('NO_OTHER_DOCUMENTS_BACKEND_ANDROID_COMMAND')
