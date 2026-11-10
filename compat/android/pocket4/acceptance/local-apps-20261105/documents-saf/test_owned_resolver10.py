"""Narrow private-parser contract; no Pocket4 or UI calls."""
import copy,importlib.util,json,re,types,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('resolver_adapter',HERE/'ui_adapter03.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
FOCUS={'package':'android','activity':'com.android.internal.app.ResolverActivity',
    'task':938,'window_token':'59fc3d7','popup':False}
def adapter():
    a=M.Adapter.__new__(M.Adapter);a.resolver_binding=None
    a.owned={938:{'component':(M.DOCS,M.FILES),'source':'open-files'}};a.adopted=[938]
    a.allowed={('android',M.RESOLVER)};a.pending={'files-open-owned-file':{'input_acknowledged':True}}
    a.allow_new={'source':'files-open-owned-file','component':('android',M.RESOLVER)}
    a.current=copy.deepcopy(FOCUS);a.focus=lambda:a.current;a.calls=[];a.records=[]
    a.s=types.SimpleNamespace(guard=lambda:None,android=lambda argv,timeout:(a.calls.append(argv) or b'package:android uid:1000\n'))
    a.check_tasks=lambda label:None;a.record=lambda *args:a.records.append(args)
    def original(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+',value):raise RuntimeError('INVALID_PACKAGE')
        return value
    a.original_package_name=original;return a
class OwnedResolver(unittest.TestCase):
    def test_actual_exact_focus_binds_once_and_preserves_uid_proof(self):
        a=adapter();self.assertEqual(a.helper_package_name('android'),'android')
        self.assertEqual(a.helper_package_name('android'),'android');self.assertEqual(len(a.calls),1)
        self.assertEqual(a.resolver_binding,{k:FOCUS[k] for k in ('package','activity','window_token','task')})
    def test_foreign_activity_or_task_cannot_use_exception(self):
        for key,value in [('activity','com.android.internal.app.ChooserActivity'),('task',999),('popup',True)]:
            a=adapter();a.current={**a.current,key:value}
            with self.assertRaisesRegex(RuntimeError,'OWNED_SYSTEM_RESOLVER_FOCUS_REQUIRED'):a.helper_package_name('android')
            self.assertEqual(a.calls,[])
    def test_unacknowledged_or_wrong_source_open_rejected(self):
        for kind in ['ack','source']:
            a=adapter()
            if kind=='ack':a.pending['files-open-owned-file']['input_acknowledged']=False
            else:a.allow_new['source']='different-input'
            with self.assertRaisesRegex(RuntimeError,'ACKNOWLEDGED_OWNED_FILE_OPEN_REQUIRED'):a.helper_package_name('android')
            self.assertEqual(a.calls,[])
    def test_foreign_leaf_or_unadopted_task_rejected(self):
        for kind in ['component','adopted']:
            a=adapter()
            if kind=='component':a.owned[938]['component']=('com.foreign.app','com.foreign.app.Main')
            else:a.adopted=[]
            with self.assertRaisesRegex(RuntimeError,'SOURCE_BOUND_FILES_TASK_REQUIRED'):a.helper_package_name('android')
            self.assertEqual(a.calls,[])
    def test_wrong_system_uid_does_not_establish_binding(self):
        a=adapter();a.s.android=lambda *args:b'package:android uid:10123\n'
        with self.assertRaisesRegex(RuntimeError,'SYSTEM_RESOLVER_UID_CHANGED'):a.helper_package_name('android')
        self.assertIsNone(a.resolver_binding)
    def test_new_window_cannot_reuse_old_binding(self):
        a=adapter();a.helper_package_name('android');a.current={**a.current,'window_token':'abcd'}
        with self.assertRaisesRegex(RuntimeError,'BOUND_SYSTEM_RESOLVER_WINDOW_CHANGED'):a.helper_package_name('android')
    def test_other_package_validation_unchanged(self):
        a=adapter();self.assertEqual(a.helper_package_name('com.android.documentsui'),'com.android.documentsui')
        for value in ['other','android.extra..bad','',None]:
            with self.assertRaisesRegex(RuntimeError,'INVALID_PACKAGE'):a.helper_package_name(value)
        self.assertEqual(a.calls,[])
if __name__=='__main__':unittest.main(verbosity=2)
