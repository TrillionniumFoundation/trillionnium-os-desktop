"""Actual saved Docs09 dialog and runner boundaries, with no device effects."""
from pathlib import Path
from types import SimpleNamespace
import ast,copy,hashlib,importlib.util,json,unittest

HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'revision09'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module
M=load(HERE/'run_features01.py','delete10');O=load(OLD/'run_features01.py','delete09')
UI=load(HERE/'features_ui.py','delete_ui10')
raw=(OLD/'saved-delete-review/selected-original.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='cfeb5e0a153cba63a8822382db4e2b7a5f383f02f84af4c6191d24e478ed3f03'
E=json.loads(raw)['records']
def obs(name):
    v=E[name]['value'];shot=v['screenshot']
    return {'focus':{'package':M.DOCS,'activity':M.FILES[1],'window_token':shot['scope']['window_token'],
        'task':978,'popup':False},'screenshot':copy.deepcopy(shot),
        'nodes':[copy.deepcopy(n) for n in v['native']['nodes'] if n.get('package')==M.DOCS and n.get('visible') is True]}
SELECTED=obs('839-delete-copies-selected.json');DIALOG=obs('861-delete-copies-dialog-or-result.json')
LEDGER=E['843-delete-copies-before.json']['value']['entries']
class UnknownInput(RuntimeError):pass

class Boundary:
    def __init__(self,dialog=None,unknown_confirm=False,changed_files=False):
        self.dialog=copy.deepcopy(dialog if dialog is not None else DIALOG)
        self.inputs=[];self.layouts=[];self.gates=[];self.records=[];self.tree_reads=[]
        self.unknown_confirm=unknown_confirm;self.changed_files=changed_files
        self.flow=M.Flow.__new__(M.Flow);self.flow.operation_pending=None;self.flow.runtime=None
        self.flow.helper_pending={}
        self.flow.tree=SimpleNamespace(expected=set(LEDGER),expect=self.expect)
        self.flow.ui=SimpleNamespace(one=UI.Adapter.one,pending={},input=self.input,
            observe=lambda *a,**k:copy.deepcopy(self.dialog),record=lambda a,b:self.records.append((a,b)))
        self.flow.select=lambda *a,**k:copy.deepcopy(SELECTED)
        self.flow.location=lambda *a,**k:None
        self.flow.layout_result=self.layout
        self.flow.gate=lambda name,proof:self.gates.append((name,proof))

    def expect(self,*args,**kwargs):
        self.tree_reads.append(args)
        if self.changed_files and args[1].endswith('-before-confirm'):raise RuntimeError('OWNED_FILE_CHANGED')
        return copy.deepcopy(LEDGER)
    def input(self,observation,label,node,**kwargs):
        self.inputs.append((label,copy.deepcopy(node)))
        if label.endswith('-confirm') and self.unknown_confirm:
            self.flow.ui.pending[label]={'outcome_unknown':True}
            raise UnknownInput('CONFIRM_RESULT_UNKNOWN_NO_REPLAY')
    def layout(self,expected,label):
        self.layouts.append((set(expected),label))
        if not any(x[0].endswith('-confirm') for x in self.inputs):
            raise RuntimeError('EXACT_GENERATED_LAYOUT_REQUIRED:'+label+'-readback')
        self.flow.operation_pending=None
        return {n:v for n,v in LEDGER.items() if n in expected}
    def run(self,method=None):
        return (method or M.Flow.delete_entries)(self.flow,copy.deepcopy(SELECTED),M.COPIES,
            {M.ALPHA,M.BETA},'FILES_MULTIPLE_DELETE_COPIES','delete-copies')

class DeleteConfirmationTests(unittest.TestCase):
    def test_original_saved_OK_dialog_never_reaches_confirmation(self):
        b=Boundary()
        with self.assertRaisesRegex(RuntimeError,'EXACT_GENERATED_LAYOUT_REQUIRED'):
            b.run(O.Flow.delete_entries)
        self.assertEqual([x[0] for x in b.inputs],['delete-copies-request'])
        self.assertIsNotNone(b.flow.operation_pending);self.assertEqual(b.gates,[])

    def test_actual_saved_dialog_gets_one_exact_confirm_then_effect_readback(self):
        b=Boundary();b.run()
        self.assertEqual([x[0] for x in b.inputs],['delete-copies-request','delete-copies-confirm'])
        self.assertEqual(b.inputs[-1][1]['resource-id'],'android:id/button1')
        self.assertEqual(b.inputs[-1][1]['text'],'OK')
        self.assertEqual(len(b.layouts),1);self.assertEqual(len(b.gates),1)
        self.assertIsNone(b.flow.operation_pending)

    def test_wrong_count_and_unobserved_message_are_not_confirmed(self):
        for text in ['1 item will be deleted forever. This can’t be undone.',
                     '4 items will be deleted forever. This can’t be undone.','Delete these files?']:
            d=copy.deepcopy(DIALOG);next(n for n in d['nodes'] if n.get('resource-id')=='android:id/message')['text']=text
            b=Boundary(d)
            with self.assertRaisesRegex(RuntimeError,'EXACT_DELETE_DIALOG_CONTROL'):b.run()
            self.assertEqual(len(b.inputs),1);self.assertEqual(b.layouts,[])

    def test_wrong_title_or_package_not_bound_to_generic_OK(self):
        for field,value in [('text','New folder'),('resource-id','android:id/alertTitle'),('package','another.app')]:
            d=copy.deepcopy(DIALOG);next(n for n in d['nodes'] if n.get('resource-id')==M.DOCS+':id/alertTitle')[field]=value
            b=Boundary(d)
            with self.assertRaisesRegex(RuntimeError,'EXACT_DELETE_DIALOG_CONTROL'):b.run()
            self.assertEqual(len(b.inputs),1)

    def test_cross_window_or_outside_panel_confirmation_is_rejected(self):
        for field,value in [('window_id',999),('bounds_array',[1,1,10,10]),('clickable',False),('supported_actions',[])]:
            d=copy.deepcopy(DIALOG);next(n for n in d['nodes'] if n.get('resource-id')=='android:id/button1')[field]=value
            b=Boundary(d)
            with self.assertRaisesRegex(RuntimeError,'DELETE_DIALOG_WINDOW_OR_BUTTON_SCOPE_CHANGED'):b.run()
            self.assertEqual(len(b.inputs),1)

    def test_duplicate_positive_and_changed_button_text_rejected(self):
        for duplicate in [True,False]:
            d=copy.deepcopy(DIALOG);button=next(n for n in d['nodes'] if n.get('resource-id')=='android:id/button1')
            if duplicate:d['nodes'].append(copy.deepcopy(button))
            else:button['text']='ALLOW'
            b=Boundary(d)
            with self.assertRaisesRegex(RuntimeError,'EXACT_DELETE_DIALOG_CONTROL'):b.run()
            self.assertEqual(len(b.inputs),1)

    def test_changed_owned_file_stops_before_confirmation(self):
        b=Boundary(changed_files=True)
        with self.assertRaisesRegex(RuntimeError,'OWNED_FILE_CHANGED'):b.run()
        self.assertEqual(len(b.inputs),1);self.assertEqual(b.layouts,[])

    def test_confirmation_unknown_is_not_replayed_or_upgraded_to_gate(self):
        b=Boundary(unknown_confirm=True)
        with self.assertRaises(UnknownInput):b.run()
        self.assertEqual(len(b.inputs),2);self.assertEqual(b.layouts,[]);self.assertEqual(b.gates,[])
        self.assertEqual(set(b.flow.ui.pending),{'delete-copies-confirm'})
        self.assertIsNotNone(b.flow.operation_pending)

    def test_four_item_final_confirmation_requires_same_exact_plural_contract(self):
        d=copy.deepcopy(DIALOG);n=next(n for n in d['nodes'] if n.get('resource-id')=='android:id/message')
        n['text']='4 items will be deleted forever. This can’t be undone.'
        b=Boundary(d);node=b.flow.delete_confirmation(d,4)
        self.assertEqual(node['text'],'OK')
        with self.assertRaisesRegex(RuntimeError,'OWNED_FILES_DELETE_DIALOG_SCOPE'):b.flow.delete_confirmation(d,1)
        self.assertEqual(b.inputs,[])

    def test_existing_pointer_cleanup_unknown_and_all_other_methods_unchanged(self):
        def defs(path):
            tree=ast.parse(path.read_bytes());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Flow')
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
        before=defs(OLD/'run_features01.py');after=defs(HERE/'run_features01.py')
        self.assertEqual(set(after)-set(before),{'delete_confirmation'})
        self.assertEqual({n for n in before if before[n]!=after[n]},{'delete_entries'})
        for name in ['features_ui.py','package_fixture.py','owned_tree.py','runtime_evidence.py','bounded_diagnostics.py']:
            self.assertEqual((HERE/name).read_bytes(),(OLD/name).read_bytes())

if __name__=='__main__':unittest.main(verbosity=2)
