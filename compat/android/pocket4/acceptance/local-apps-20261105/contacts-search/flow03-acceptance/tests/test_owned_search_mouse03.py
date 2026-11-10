"""Exercise the private branch with actual retained Contacts02 nodes; no device calls."""
from pathlib import Path
import copy, importlib.util, json, time, types, unittest

HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/name);m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m
mouse=load('owned_search_mouse03.py');loop=load('session_loop08.py')
FIXTURE=json.loads((HERE/'actual-search-observations02.json').read_text())
BEFORE=FIXTURE['before'];FRESH=FIXTURE['fresh'];NAME=FIXTURE['edited_name']

class RecordedFlow:
    def __init__(self):
        self.records=[];self.dispatched=[];self.observations=[]
        self.created={'actual_fixture':True};self.ownership_journal=True
        self.number=8;self.deadline=time.monotonic()+30;self.loop=loop
        proof=copy.deepcopy(FIXTURE['same_contact'])
        self.v=types.SimpleNamespace(EDITED=NAME,validate_owned=lambda *args:copy.deepcopy(proof))
        self.r={'search_result':{'same_contact':copy.deepcopy(proof),'observation':'actual02-query'}}
        self.c=types.SimpleNamespace(nodes=copy.deepcopy(BEFORE['native']['nodes']),
            latest='actual02-query',pending=None,seen=set(),actions=8)
        self.t=types.SimpleNamespace(owned=(990,{851}),last_observation=copy.deepcopy(BEFORE),
            record=lambda name,value:self.records.append((name,copy.deepcopy(value))))
        scope=BEFORE['screenshot']['scope']
        self.focus={'verified':True,'package':mouse.PACKAGE,'activity':mouse.ACTIVITY,
            'window_token':scope['window_token'],'task':990,'user':0}
        self.t.ready_focus=lambda **kw:copy.deepcopy(self.focus)
        self.frames=[{'meta':copy.deepcopy(BEFORE['screenshot'])},
                     {'meta':copy.deepcopy(FRESH['screenshot'])}]
        self.native=copy.deepcopy(FRESH['native'])
        self.ack_change=lambda value:None
        self.post_capture_unknown=False;self.observe_error=False
        self.helper=types.SimpleNamespace(capture=lambda request:self.frames.pop(0),ui=self.ui,dispatch=self.dispatch)
        self.t.s=types.SimpleNamespace(helper=self.helper,guard=lambda:None)
        self.c.observe=self.observe
        self.owned=lambda *args:{'same_actual_fixture':True}
        self.search_field=lambda expected:None
        self.may_mutate=lambda:mouse.need(self.c.pending is None,'PENDING')

    def leaf(self):
        return next(n for n in self.c.nodes if n.get('resource-id')==mouse.PACKAGE+':id/cliv_name_textview'
                    and n.get('text')==NAME)

    def ui(self,request):
        if request['op']=='dump':return copy.deepcopy(self.native)
        if request['op']!='click':raise AssertionError('unexpected action')
        target=copy.deepcopy(self.leaf());target['window_id']+=100
        box=target['bounds_array']
        ack={'ok':True,'performed':'click','method':'mouse','source':'native_bounds_mouse',
            'coordinates':[(box[0]+box[2])//2,(box[1]+box[3])//2],
            'target':target,'actual_target':copy.deepcopy(target),'outcome_unknown':False,
            'accessibility_mode_restoration_verified':True,'visual_verified':False,'business_success_verified':False}
        self.ack_change(ack)
        return ack

    def dispatch(self,request):
        self.dispatched.append(copy.deepcopy(request))
        reply=copy.deepcopy(self.helper.ui(request))
        if self.post_capture_unknown:reply.update(outcome_unknown=True,post_action_observation_available=False)
        return reply

    def observe(self,label):
        self.observations.append(label)
        if self.observe_error:raise RuntimeError('READ_ONLY_POST_OBSERVATION_FAILED')
        self.c.latest=label

    def run(self):mouse.open_search_result(self,'open-search-result',self.leaf())

class SearchMouseBoundary(unittest.TestCase):
    def test_actual_saved_pair_keeps_full_nodes_and_window_despite_changed_pixels(self):
        a=mouse.binding(loop,BEFORE['native']['nodes'],NAME,BEFORE['screenshot'])
        b=mouse.binding(loop,FRESH['native']['nodes'],NAME,FRESH['screenshot'])
        self.assertEqual({k:mouse.normalized(v) for k,v in a.items()},
                         {k:mouse.normalized(v) for k,v in b.items()})
        self.assertNotEqual(BEFORE['screenshot']['scope_sha256'],FRESH['screenshot']['scope_sha256'])
        mouse.same_window(BEFORE['screenshot'],{'meta':FRESH['screenshot']})
        f=RecordedFlow();f.run();self.assertEqual(len(f.dispatched),1)
        command=f.dispatched[0];self.assertEqual((command['op'],command['method']),('click','mouse'))
        self.assertNotIn('coords',command);self.assertIs(command['selector']['clickable'],False)
        self.assertEqual(f.c.actions,9);self.assertIsNone(f.c.pending)

    def test_changed_or_duplicate_fresh_node_stops_before_dispatch(self):
        for role,change in [('leaf',{'text':'other'}),('query',{'text':'other'}),
                            ('row',{'checked':True}),('list',{'enabled':False}),('leaf',None)]:
            with self.subTest(role=role,change=change):
                f=RecordedFlow();binding=mouse.binding(loop,f.native['nodes'],NAME,BEFORE['screenshot'])
                if change is None:f.native['nodes'].append(copy.deepcopy(binding[role]))
                else:binding[role].update(change)
                with self.assertRaises(RuntimeError):f.run()
                self.assertFalse(f.dispatched);self.assertEqual(f.c.actions,8);self.assertIsNone(f.c.pending)

    def test_context_or_final_owned_focus_change_stops_before_dispatch(self):
        for what in ('context','geometry','focus'):
            with self.subTest(what=what):
                f=RecordedFlow()
                if what=='context':f.frames[-1]['meta']['context_token']='changed'
                elif what=='geometry':f.frames[-1]['meta']['scope_bounds'][0]+=1
                else:
                    calls=[]
                    def focus(**kwargs):
                        calls.append(1);v=copy.deepcopy(f.focus)
                        if len(calls)==2:v['task']=991
                        return v
                    f.t.ready_focus=focus
                with self.assertRaises(RuntimeError):f.run()
                self.assertFalse(f.dispatched);self.assertIsNone(f.c.pending)

    def test_native_unknown_wrong_target_or_coordinate_retains_pending(self):
        for what in ('unknown','target','coordinate','restoration'):
            with self.subTest(what=what):
                f=RecordedFlow()
                def change(v):
                    if what=='unknown':v['outcome_unknown']=True
                    elif what=='target':v['actual_target']['text']='other'
                    elif what=='coordinate':v['coordinates'][0]+=1
                    else:v['accessibility_mode_restoration_verified']=False
                f.ack_change=change
                with self.assertRaises(RuntimeError):f.run()
                self.assertEqual(len(f.dispatched),1);self.assertIsNotNone(f.c.pending)
                with self.assertRaises(RuntimeError):f.run()
                self.assertEqual(len(f.dispatched),1)

    def test_acknowledged_post_capture_unknown_needs_new_observation(self):
        f=RecordedFlow();f.post_capture_unknown=True;f.run()
        self.assertEqual(len(f.dispatched),1);self.assertIsNone(f.c.pending)
        self.assertEqual(len(f.observations),1)
        record=[v for k,v in f.records if k.startswith('mouse-input-observed-')][0]
        self.assertTrue(record['original_post_capture_unknown_retained'])
        self.assertFalse(record['business_success_verified'])

    def test_failed_post_observation_retains_fence(self):
        f=RecordedFlow();f.observe_error=True
        with self.assertRaisesRegex(RuntimeError,'READ_ONLY_POST_OBSERVATION_FAILED'):f.run()
        self.assertEqual(len(f.dispatched),1);self.assertIsNotNone(f.c.pending)

if __name__=='__main__':unittest.main(verbosity=2)
