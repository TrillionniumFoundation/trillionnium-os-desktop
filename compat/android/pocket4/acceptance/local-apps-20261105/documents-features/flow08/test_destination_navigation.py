"""Actual saved06 failures plus explicit boundary-only drawer/Android shims."""
from pathlib import Path
from types import SimpleNamespace
import ast,copy,hashlib,importlib.util,json,unittest

HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'revision06'
raw=(OLD/'saved/selected.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='22a3dfdb996798a4d2f303314f6744168f76197716ccd346fc1c11b3226b969c'
SAVED=json.loads(raw)['records']
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m
M=load(HERE/'run_features01.py','navigation07')
O=load(OLD/'run_features01.py','navigation06')
UI=load(HERE/'features_ui.py','navigation_adapter07')

def actual(name,route):
    v=copy.deepcopy(SAVED[name]['value']);scope=v['screenshot']['scope']
    return {'focus':dict(package=route[0],activity=route[1],task=965,
                         window_token=scope['window_token'],popup=False),
            'nodes':[n for n in v['native']['nodes'] if n.get('package')==M.DOCS and n.get('visible') is True],
            'screenshot':v['screenshot']}
DEFAULT=actual('423-copy-destination-picker.json',M.PICKER)
SOURCE=actual('347-open-owned-source-result.json',M.FILES)
OWNED=actual('324-new-folder-result.json',M.PICKER)
ROOT_TEXT='Row: 0 root_id=primary, flags=1114139, title=Cuttlefish, document_id=primary:, available_bytes=-1\n'

def node(rid,cls,rect,text='',window=12091,**kw):
    return dict({'package':M.DOCS,'resource-id':rid,'class':cls,'bounds_array':rect,
                 'text':text,'enabled':True,'visible':True,'editable':False,'clickable':False,
                 'window_id':window,'supported_actions':[]},**kw)

class Boundary:
    def __init__(self):
        self.flow=M.Flow.__new__(M.Flow);self.inputs=[];self.queries=[];self.records=[];self.guards=0
        self.expected={M.SOURCE,M.COPIES,M.SOURCE+'/'+M.ALPHA,M.SOURCE+'/'+M.BETA}
        self.flow.tree=SimpleNamespace(expected=self.expected,guard=self.guard,
            expect=lambda *args:self.guard())
        self.flow.before_packages={'com.android.externalstorage':{'uid':10024,
            'apk_sha256':'50d1e6f2be950e049cdc898dd812c8e609f421cc167013d4ee2c795dcdc0e5ea'}}
        self.root_text=ROOT_TEXT;self.fail_input=None
        self.flow.s=SimpleNamespace(guard=self.guard,android=self.query)
        self.flow.ui=SimpleNamespace(one=UI.Adapter.one,input=self.input,observe=self.observe,
            record=lambda label,value:self.records.append((label,copy.deepcopy(value))),pending={})
        # These next-state views are boundary shims, NOT captured drawer evidence.
        # Only DEFAULT/SOURCE/OWNED came from actual06; every synthetic node must
        # satisfy the same production selector before its mocked input is called.
        self.drawer={'focus':copy.deepcopy(DEFAULT['focus']),'nodes':[
            node(M.DOCS+':id/container_roots','android.widget.FrameLayout',[0,50,360,1450]),
            node(M.DOCS+':id/roots_list','android.widget.ListView',[0,80,360,1400]),
            node('android:id/title','android.widget.TextView',[50,300,220,350],M.PRIMARY_TITLE)]}
        self.primary={'focus':copy.deepcopy(DEFAULT['focus']),'nodes':[
            node(M.DOCS+':id/breadcrumb_text','android.widget.TextView',[0,131,145,195],M.PRIMARY_TITLE),
            node('android:id/title','android.widget.TextView',[30,300,460,340],M.FOLDER),
            node(M.DOCS+':id/item_root','android.widget.LinearLayout',[20,280,500,400],
                 clickable=True,supported_actions=[16])]}
        self.owned=copy.deepcopy(OWNED)

    def guard(self):self.guards+=1;return {}
    def query(self,argv,timeout):
        self.queries.append(argv)
        assert argv==['/system/bin/content','query','--uri',
            'content://com.android.externalstorage.documents/root','--projection',
            'root_id:flags:title:document_id:available_bytes']
        return self.root_text.encode()
    def input(self,obs,label,n,*args,**kwargs):
        assert n in obs['nodes'] and n['enabled'] and n['visible']
        self.inputs.append((label,copy.deepcopy(n)))
        if self.fail_input and label.endswith(self.fail_input):
            self.flow.ui.pending[label]={'input_acknowledged':False,'outcome_unknown':True}
            raise RuntimeError('NATIVE_OUTCOME_UNKNOWN_NO_REPLAY')
    def observe(self,label,routes):
        assert routes in ([M.PICKER],(M.PICKER,),(M.FILES,))
        if label.endswith('-roots'):return copy.deepcopy(self.drawer)
        if label.endswith('-primary-root'):return copy.deepcopy(self.primary)
        if label.endswith('-owned-root') or label.endswith('-result'):return copy.deepcopy(self.owned)
        raise AssertionError(label)
    def run(self,obs=None):return self.flow.destination_root(copy.deepcopy(obs or DEFAULT),'copy-destination-root')

class DestinationBoundary(unittest.TestCase):
    def test_old_actual_default_is_rejected_before_input(self):
        b=Boundary()
        with self.assertRaisesRegex(RuntimeError,'CURRENT_LOCATION_NOT_OWNED_TREE'):
            O.Flow.root_directory(b.flow,copy.deepcopy(DEFAULT),'copy-root',(M.PICKER,))
        self.assertEqual(b.inputs,[])

    def test_actual_default_uses_three_exact_navigation_inputs_only(self):
        b=Boundary();out=b.run()
        self.assertEqual([x[0] for x in b.inputs],['copy-destination-root-show-roots',
            'copy-destination-root-select-primary','copy-destination-root-open-owned-folder'])
        self.assertEqual(len(b.queries),1);self.assertEqual(out,b.owned)
        proof=b.records[-1][1];self.assertFalse(proof['file_operation_committed'])
        self.assertFalse(proof['broader_location_accepted_for_writes']);self.assertEqual(proof['new_URI_grants'],0)

    def test_wrong_root_metadata_and_extra_row_have_no_input(self):
        for text in (ROOT_TEXT.replace('root_id=primary','root_id=other'),
                     ROOT_TEXT.replace('title=Cuttlefish','title=Other'),ROOT_TEXT+'Row: 1 unknown\n'):
            b=Boundary();b.root_text=text
            with self.assertRaisesRegex(RuntimeError,'EXACT_PRIMARY_PROVIDER_ROOT_METADATA_REQUIRED'):b.run()
            self.assertEqual(b.inputs,[])

    def test_wrong_task_route_is_not_treated_as_destination(self):
        b=Boundary();obs=copy.deepcopy(DEFAULT);obs['focus']['activity']=M.FILES[1]
        with self.assertRaisesRegex(RuntimeError,'OWNED_DESTINATION_PICKER_REQUIRED'):b.run(obs)
        self.assertEqual(b.inputs,[]);self.assertEqual(b.queries,[])

    def test_foreign_default_directory_is_not_accepted(self):
        b=Boundary();obs=copy.deepcopy(DEFAULT)
        for n in obs['nodes']:
            if n['resource-id']==M.DOCS+':id/breadcrumb_text':n['text']='Another folder'
        with self.assertRaisesRegex(RuntimeError,'UNRECOGNIZED_DEFAULT_DESTINATION_PRESERVED'):b.run(obs)
        self.assertEqual(b.inputs,[])

    def test_matching_title_behind_drawer_is_not_clicked(self):
        b=Boundary();b.drawer['nodes'][-1]['bounds_array']=[600,300,800,350]
        with self.assertRaisesRegex(RuntimeError,'ONE_ACTUAL_VERIFIED_PRIMARY_ROOT_TITLE'):b.run()
        self.assertEqual(len(b.inputs),1)

    def test_duplicate_title_inside_roots_is_not_clicked(self):
        b=Boundary();duplicate=copy.deepcopy(b.drawer['nodes'][-1]);duplicate['bounds_array']=[50,400,220,450]
        b.drawer['nodes'].append(duplicate)
        with self.assertRaisesRegex(RuntimeError,'ONE_ACTUAL_VERIFIED_PRIMARY_ROOT_TITLE'):b.run()
        self.assertEqual(len(b.inputs),1)

    def test_wrong_primary_readback_does_not_open_any_row(self):
        b=Boundary();b.primary['nodes'][0]['text']='Downloads'
        with self.assertRaisesRegex(RuntimeError,'PRIMARY_ROOT_NAVIGATION_NOT_VERIFIED'):b.run()
        self.assertEqual(len(b.inputs),2)

    def test_similar_foreign_name_is_not_opened(self):
        b=Boundary();b.primary['nodes'][1]['text']=M.FOLDER+'-foreign'
        with self.assertRaisesRegex(RuntimeError,'ONE_EXACT_OWNED_FOLDER_IN_PRIMARY_ROOT'):b.run()
        self.assertEqual(len(b.inputs),2)

    def test_folder_open_requires_actual_owned_location_readback(self):
        b=Boundary()
        for n in b.owned['nodes']:
            if n['resource-id']==M.DOCS+':id/breadcrumb_text' and n['text']==M.FOLDER:n['text']='foreign'
        with self.assertRaisesRegex(RuntimeError,'OWNED_BREADCRUMB_REQUIRED'):b.run()
        self.assertEqual(len(b.inputs),3)
        self.assertFalse(any(k.endswith('-navigation-verified') for k,_ in b.records))

    def test_actual_ancestor_old_selector_fails_new_item_is_exact(self):
        old=Boundary()
        with self.assertRaisesRegex(RuntimeError,'ONE_ACTUAL_OWNED_ROOT_BREADCRUMB'):
            O.Flow.root_directory(old.flow,copy.deepcopy(SOURCE),'return-root',(M.FILES,))
        self.assertEqual(old.inputs,[])
        new=Boundary();new.flow.root_directory(copy.deepcopy(SOURCE),'return-root',(M.FILES,))
        self.assertEqual(len(new.inputs),1)
        n=new.inputs[0][1];self.assertEqual(n['class'],'android.widget.LinearLayout')
        self.assertEqual(n['bounds_array'],[154,131,552,195])
        self.assertTrue(n['enabled']);self.assertFalse(n['clickable'])

    def test_duplicate_ancestor_item_rejected(self):
        b=Boundary();obs=copy.deepcopy(SOURCE)
        item=next(n for n in obs['nodes'] if n['bounds_array']==[154,131,552,195])
        obs['nodes'].append(copy.deepcopy(item))
        with self.assertRaisesRegex(RuntimeError,'ONE_ACTUAL_OWNED_BREADCRUMB_ITEM'):
            b.flow.root_directory(obs,'return-root',(M.FILES,))
        self.assertEqual(b.inputs,[])

    def test_unknown_show_roots_is_never_replayed(self):
        b=Boundary();b.fail_input='show-roots'
        with self.assertRaisesRegex(RuntimeError,'OUTCOME_UNKNOWN'):b.run()
        self.assertEqual(len(b.inputs),1);self.assertTrue(b.flow.ui.pending)
        self.assertFalse(any(k.endswith('-navigation-verified') for k,_ in b.records))

    def test_business_ownership_and_cleanup_methods_unchanged(self):
        def methods(path):
            tree=ast.parse(path.read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Flow')
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
        before=methods(OLD/'run_features01.py');after=methods(HERE/'run_features01.py')
        self.assertEqual(set(after)-set(before),{'primary_root_metadata','destination_root'})
        self.assertEqual({k for k in before if before[k]!=after[k]},{'root_directory','copy_or_move'})
        self.assertEqual((OLD/'features_ui.py').read_bytes(),(HERE/'features_ui.py').read_bytes())

if __name__=='__main__':unittest.main(verbosity=2)
