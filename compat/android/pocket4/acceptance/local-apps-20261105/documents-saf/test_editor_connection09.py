"""Exercise the actual input method using retained 08 nodes; no device access."""
from pathlib import Path
import copy,hashlib,importlib.util,json,types,unittest
HERE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
OLD=module('ui_adapter01');NEW=module('ui_adapter02')
FIXTURE=json.loads((HERE/'fixtures/owned-rename-editor08.json').read_text())
RAW=FIXTURE['original'];FRESH=FIXTURE['fresh']
NODE=next(n for n in RAW['native']['nodes'] if n.get('editable') is True)
CURRENT=next(n for n in FRESH['nodes'] if n.get('editable') is True)

def exercise(module,fresh_node,*,bad_focus=False,bad_snapshot=False):
    calls=[];captures=[];records=[];adapter=module.Adapter.__new__(module.Adapter)
    scope=RAW['screenshot']['scope'];focus={k:scope[k] for k in ('package','activity','window_token')}
    obs={'focus':focus,'screenshot':RAW['screenshot'],'nodes':RAW['native']['nodes']}
    adapter.actions=0;adapter.pending={};adapter.record=lambda *a:records.append(a)
    adapter.check_tasks=lambda label:None
    focus_calls=[]
    def current_focus():
        focus_calls.append(1)
        return {**focus,'window_token':'changed'} if bad_focus and len(focus_calls)>1 else focus
    def capture(request):
        captures.append(copy.deepcopy(request));return {'capture':len(captures)}
    def validate(request,frame):
        assert all(request[k]==RAW['screenshot'][k] for k in ('frame_sha256','scope_sha256','context_token'))
        assert request['window_token']==scope['window_token']
        if bad_snapshot and frame['capture']==2:raise RuntimeError('STALE_FRAME')
    def dispatch(request):
        calls.append(request)
        return {'ok':True,'performed':'set-text','outcome_unknown':False,'readback_verified':True,'password':False}
    adapter.focus=current_focus
    fresh=copy.deepcopy(FRESH);fresh['nodes']=[fresh_node]
    helper=types.SimpleNamespace(capture=capture,validate_snapshot=validate,ui=lambda request:fresh,dispatch=dispatch)
    adapter.s=types.SimpleNamespace(helper=helper,guard=lambda:None)
    error=None
    try:adapter.input(obs,'rename',NODE,'set-text','files-ui-69814e80ea71f485.txt')
    except RuntimeError as exc:error=str(exc)
    return {'error':error,'calls':calls,'captures':captures,'pending':adapter.pending,'actions':adapter.actions,'records':records}

class RetainedEditorBoundaries(unittest.TestCase):
    def test_original_rejects_only_connection_number_change(self):
        self.assertEqual([k for k in set(NODE)|set(CURRENT) if NODE.get(k)!=CURRENT.get(k)],['window_id'])
        result=exercise(OLD,CURRENT)
        self.assertEqual(result['error'],'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT');self.assertEqual(result['calls'],[])

    def test_new_actual_nodes_keep_two_snapshot_checks_and_one_input(self):
        result=exercise(NEW,CURRENT)
        self.assertIsNone(result['error']);self.assertEqual(len(result['calls']),1)
        self.assertEqual(len(result['captures']),2);self.assertEqual(result['actions'],1)
        self.assertTrue(result['pending']['rename']['input_acknowledged'])

    def test_any_other_editor_change_stops_before_input(self):
        for key,value in [('bounds_array',[233,733,968,808]),('text','foreign.txt'),('value','foreign.txt'),
                ('focused',False),('password',True),('enabled',False),('selected',True),('new_unknown_field','changed')]:
            with self.subTest(field=key):
                result=exercise(NEW,{**CURRENT,key:value})
                self.assertEqual(result['error'],'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT')
                self.assertEqual(result['calls'],[]);self.assertEqual(result['pending'],{})

    def test_invalid_connection_id_rejected(self):
        for value in [None,-1,'6576',True]:
            with self.subTest(value=value):
                result=exercise(NEW,{**CURRENT,'window_id':value})
                self.assertEqual(result['error'],'EDITOR_CONNECTION_WINDOW_ID_REQUIRED');self.assertEqual(result['calls'],[])

    def test_final_wm_token_change_stops_before_input(self):
        result=exercise(NEW,CURRENT,bad_focus=True)
        self.assertEqual(result['error'],'LAST_INPUT_FOCUS_CHANGED');self.assertEqual(result['calls'],[])

    def test_second_snapshot_failure_stops_before_input(self):
        result=exercise(NEW,CURRENT,bad_snapshot=True)
        self.assertEqual(result['error'],'STALE_FRAME');self.assertEqual(result['calls'],[])

if __name__=='__main__':unittest.main(verbosity=2)
