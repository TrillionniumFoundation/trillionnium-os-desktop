"""Actual flow05 nodes/frames, actual old/new adapter methods; Android boundary shims.

No host test result is a claim that a device mutation happened or succeeded.
"""
from pathlib import Path
from types import SimpleNamespace
import ast,copy,hashlib,importlib.util,json,re,unittest

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'revision05'
raw=(OLD/'saved/selected.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='226aa0114cedd64048ef6a97f77fa6a2fde89e9dd0ec537af9bc88ecedd23ccb'
SAVED=json.loads(raw)
RECORDS=SAVED['records']
ACTUAL=RECORDS['281-new-folder-dialog.json']['value']
assert RECORDS['284-before-new-folder-name-1.json']['value']['tasks']==[851,961,962]
assert 'taskId=962: com.android.documentsui/com.android.documentsui.files.FilesActivity ' in RECORDS[
    '284-before-new-folder-name-1.json']['value']['raw']
# focus() is a host test boundary shim. Its package/activity/token come from
# the actual capture; its task comes from the adjacent actual stack receipt.
FOCUS={k:ACTUAL['screenshot']['scope'][k] for k in ('package','activity','window_token')}
FOCUS.update(task=962,popup=False)
BLINK=RECORDS['317-new-folder-name-fresh-3.json']['value']['screenshot']
OBS={'focus':FOCUS,'screenshot':ACTUAL['screenshot'],
    'nodes':[n for n in ACTUAL['native']['nodes'] if n.get('package')=='com.android.documentsui'
        and n.get('visible') is True]}

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

UI=load(HERE/'features_ui.py','semantic_ui')
OLD_UI=load(OLD/'features_ui.py','original_ui')
RUN=load(HERE/'run_features01.py','semantic_runner')
helper_path=HERE.parents[1]/'camera-accept08/reference/android-app.py'
helper_raw=helper_path.read_bytes()
assert hashlib.sha256(helper_raw).hexdigest()=='eb24b1b0eefb275025d10647ccf218f9395b1f74cf6d912aaabf384210d1aa66'
parts=[n for n in ast.parse(helper_raw).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))
    and n.name in ('ControlError','require','digest','validate_snapshot')]
H={'re':re};exec(compile(ast.Module(body=parts,type_ignores=[]),str(helper_path),'exec'),H)
ControlError=H['ControlError']

def controls(obs):
    title=UI.Adapter.one(obs,lambda n:n.get('resource-id')==RUN.DOCS+':id/alertTitle','one title')
    field=UI.Adapter.one(obs,lambda n:n.get('editable') is True and n.get('enabled') is True
        and n.get('password') is False,'one field')
    return title,field

class Boundary:
    def __init__(self,cls=UI.Adapter):
        self.obs=copy.deepcopy(OBS);self.frames=0;self.dumps=0;self.dispatches=0;self.raw_inputs=0
        self.records=[];self.requests=[];self.frame_change=None;self.node_change=None;self.focus_change=None
        self.dispatch_error=None;self.reply_change=None;self.dump_change=None
        self.helper=SimpleNamespace(ControlError=ControlError,capture=self.capture,ui=self.dump,
            validate_snapshot=H['validate_snapshot'],dispatch=self.dispatch)
        self.adapter=cls.__new__(cls);self.adapter.actions=14;self.adapter.pending={}
        self.adapter.s=SimpleNamespace(helper=self.helper,guard=lambda:None,android=self.android)
        self.adapter.record=lambda label,value:self.records.append((label,copy.deepcopy(value)))
        self.adapter.check_tasks=lambda label:None
        self.adapter.focus=self.focus
        self.flow=RUN.Flow.__new__(RUN.Flow);self.flow.s=self.adapter.s;self.flow.ui=self.adapter

    def focus(self):
        value=copy.deepcopy(self.obs['focus'])
        if self.focus_change:self.focus_change(value)
        return value

    def capture(self,request):
        self.frames+=1
        meta=copy.deepcopy(BLINK)
        if self.frame_change:self.frame_change(meta,self.frames)
        return {'meta':meta}

    def dump(self,request):
        self.dumps+=1
        nodes=copy.deepcopy(self.obs['nodes'])
        for n in nodes:n['window_id']+=100
        if self.node_change:self.node_change(nodes)
        result={'ok':True,'outcome_unknown':False,'accessibility_mode_restoration_verified':True,'nodes':nodes}
        if self.dump_change:self.dump_change(result)
        return result

    def dispatch(self,request):
        self.dispatches+=1;self.requests.append(copy.deepcopy(request))
        if self.dispatch_error:raise self.dispatch_error
        assert request['op']=='set-text' and request['value']==RUN.COPIES
        result={'ok':True,'performed':'set-text','outcome_unknown':False,
            'readback_verified':True,'password':False,'accessibility_mode_restoration_verified':True}
        if self.reply_change:self.reply_change(result)
        return result

    def android(self,*args):self.raw_inputs+=1;raise AssertionError('raw input unexpectedly reached')

    def execute(self):
        title,field=controls(self.obs)
        return self.flow.new_folder_name_input(self.obs,title,field)

    def assert_no_input(self,test):
        test.assertEqual((self.dispatches,self.raw_inputs,self.adapter.actions),(0,0,14))
        test.assertEqual(self.adapter.pending,{})
        test.assertFalse(any(label.endswith('-intent') for label,_ in self.records))

class SemanticTextBoundary(unittest.TestCase):
    def test_old_actual_method_rejects_saved_caret_frame_before_input(self):
        b=Boundary(OLD_UI.Adapter);_,field=controls(b.obs)
        with self.assertRaisesRegex(ControlError,'STALE_FRAME'):
            b.adapter.input(b.obs,'new-folder-name',field,'set-text',RUN.COPIES)
        b.assert_no_input(self)
        proof=next(v for k,v in b.records if k.endswith('-pre-input-no-effect'))
        self.assertIs(proof['action_taken'],False);self.assertIs(proof['outcome_unknown'],False)

    def test_saved_caret_only_change_allows_one_exact_semantic_decision(self):
        b=Boundary();b.execute()
        self.assertEqual((b.frames,b.dumps,b.dispatches,b.adapter.actions),(2,1,1,15))
        request=b.requests[0]
        self.assertEqual(request['selector'],{'package':RUN.DOCS,'class':'android.widget.EditText',
            'editable':True,'enabled':True,'focused':True,'id':'android:id/text1','text':'Name'})
        self.assertNotIn('index',request);self.assertNotIn('coords',request)
        self.assertTrue(b.adapter.pending['new-folder-name']['input_acknowledged'])
        self.assertEqual(len([k for k,v in b.records if k.endswith('-intent')]),1)

    def test_wrong_window_in_either_capture_has_no_input(self):
        for stage in (1,2):
            b=Boundary()
            def change(meta,count):
                if count==stage:meta['scope']['window_token']='deadbeef'
            b.frame_change=change
            with self.assertRaisesRegex(RuntimeError,'TEXT_WINDOW_CONTEXT_CHANGED'):b.execute()
            b.assert_no_input(self)

    def test_changed_geometry_context_screen_or_init_has_no_input(self):
        changes=[lambda m:m.__setitem__('context_token','a'*64),
            lambda m:m.__setitem__('scope_bounds',[168,617,1032,926]),
            lambda m:m.__setitem__('width',2561),
            lambda m:m['scope'].__setitem__('android_init_host_pid',42),
            lambda m:m['scope'].__setitem__('window_bounds',[168,617,1032,926])]
        for change in changes:
            b=Boundary();b.frame_change=lambda m,count:change(m)
            with self.assertRaisesRegex(RuntimeError,'TEXT_.*CONTEXT_CHANGED'):b.execute()
            b.assert_no_input(self)

    def test_wrong_owned_task_or_focus_before_action_has_no_input(self):
        for key,value in [('task',999),('activity','com.android.documentsui.Foreign'),('window_token','deadbeef')]:
            b=Boundary();b.focus_change=lambda focus:focus.__setitem__(key,value)
            with self.assertRaisesRegex(RuntimeError,'INPUT_FOCUS_CHANGED'):b.execute()
            b.assert_no_input(self)

    def test_duplicate_fresh_editor_has_no_input(self):
        b=Boundary();b.node_change=lambda nodes:nodes.append(copy.deepcopy(next(n for n in nodes if n.get('editable'))))
        with self.assertRaisesRegex(RuntimeError,'FULL_EDITOR_NODE_CHANGED'):b.execute()
        b.assert_no_input(self)

    def test_changed_value_hint_geometry_focus_or_password_has_no_input(self):
        for key,value in [('value','foreign'),('hint','Other'),('bounds_array',[232,733,967,809]),
                          ('focused',False),('password',True),('showing-hint',False),('enabled',False)]:
            b=Boundary()
            b.node_change=lambda nodes:next(n for n in nodes if n.get('editable')).__setitem__(key,value)
            with self.assertRaisesRegex(RuntimeError,'FULL_EDITOR_NODE_CHANGED'):b.execute()
            b.assert_no_input(self)

    def test_changed_or_duplicate_dialog_title_has_no_input(self):
        for duplicate in (False,True):
            b=Boundary()
            def change(nodes):
                title=next(n for n in nodes if n.get('resource-id')==RUN.DOCS+':id/alertTitle')
                if duplicate:nodes.append(copy.deepcopy(title))
                else:title['text']='Rename'
            b.node_change=change
            with self.assertRaisesRegex(RuntimeError,'FULL_EDITOR_NODE_CHANGED'):b.execute()
            b.assert_no_input(self)

    def test_unknown_native_outcome_keeps_pending_and_is_never_replayed(self):
        b=Boundary();b.dispatch_error=ControlError('UI_RUNNER_TRANSPORT_ERROR',outcome_unknown=True,automatic_retry=False)
        with self.assertRaises(ControlError):b.execute()
        self.assertEqual((b.dispatches,b.adapter.actions),(1,15))
        self.assertEqual(b.adapter.pending,{'new-folder-name':{'input_acknowledged':False,'kind':'set-text'}})

    def test_native_explicit_no_effect_is_not_replayed(self):
        b=Boundary();b.dispatch_error=ControlError('TARGET_CHANGED_NO_ACTION_TAKEN',outcome_unknown=False,automatic_retry=False)
        with self.assertRaises(ControlError):b.execute()
        self.assertEqual((b.dispatches,b.adapter.actions),(1,15));self.assertEqual(b.adapter.pending,{})

    def test_missing_or_false_readback_retains_unknown_input(self):
        for value in (None,False):
            b=Boundary();b.reply_change=lambda reply:reply.__setitem__('readback_verified',value)
            with self.assertRaisesRegex(RuntimeError,'INPUT_UNKNOWN_NO_REPLAY'):b.execute()
            self.assertEqual(b.dispatches,1);self.assertFalse(b.adapter.pending['new-folder-name']['input_acknowledged'])

    def test_unverified_fresh_native_response_has_no_input(self):
        b=Boundary();b.dump_change=lambda result:result.__setitem__('accessibility_mode_restoration_verified',False)
        with self.assertRaisesRegex(RuntimeError,'FRESH_NATIVE_NOT_VERIFIED'):b.execute()
        b.assert_no_input(self)

    def test_long_press_still_enforces_the_actual_frozen_pixel_validator(self):
        b=Boundary();_,field=controls(b.obs)
        self.assertIn(32,field['supported_actions'])
        with self.assertRaisesRegex(ControlError,'STALE_FRAME'):
            b.adapter.input(b.obs,'long-press-control',field,'long-press')
        b.assert_no_input(self)

    def test_absent_connection_scoped_window_identity_has_no_input(self):
        b=Boundary();b.frame_change=lambda meta,count:meta['scope'].__setitem__('window_id',None)
        with self.assertRaisesRegex(RuntimeError,'TEXT_CONNECTION_SCOPE_REQUIRED'):b.execute()
        b.assert_no_input(self)

if __name__=='__main__':unittest.main(verbosity=2)
