"""Actual old/new menu methods: this run's marker and durable IDs, no device calls."""
from pathlib import Path
import copy, importlib.util, types, unittest

HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/name);m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m
adapter=load('ui_preflight05.py');menu=load('owned_menu03.py');verifier=load('verify_contact.py')

class MenuBinding(unittest.TestCase):
    def make(self,new=True):
        original={'raw_contact_id':'5','contact_id':'5','name_data_id':'5',
                  'name':verifier.NAME,'local_null_account':True}
        cls=menu.trial_class(adapter,verifier,{'owned_contact_identity':original}) if new else adapter.Trial
        trial=cls.__new__(cls);trial.owned=(990,{851});trial.menu_contact=None;trial.records=[]
        trial.last_observation={'screenshot':{'scope':{'package':adapter.PACKAGE,'activity':adapter.QUICK_ACTIVITY}}}
        trial.record=lambda label,value:trial.records.append((label,copy.deepcopy(value)))
        return trial,dict(original,name=verifier.EDITED)

    def test_old_actual_method_rejects_new_marker_new_private_method_binds_real_proof(self):
        old,proof=self.make(False)
        with self.assertRaisesRegex(RuntimeError,'MORE_MENU_REQUIRES_EXACT_OWNED_LOCAL_CONTACT'):
            old.bind_owned_contact_menu(proof)
        new,proof=self.make();new.bind_owned_contact_menu(proof)
        self.assertEqual(new.menu_contact,proof);self.assertEqual(new.records[0][1],proof)

    def test_wrong_or_stale_marker_and_wrong_durable_ids_rejected(self):
        for change in ({'name':'Pocket4 Local QA r12 9c38f5a1 Edited'}, {'name':verifier.NAME},
                       {'raw_contact_id':'6'},{'contact_id':'6'},{'name_data_id':'6'},
                       {'local_null_account':False}):
            with self.subTest(change=change):
                trial,proof=self.make();proof.update(change)
                with self.assertRaises(RuntimeError):trial.bind_owned_contact_menu(proof)
                self.assertIsNone(trial.menu_contact);self.assertFalse(trial.records)

    def test_no_owned_task_or_foreign_activity_never_binds(self):
        for change in ('owned','activity','package'):
            with self.subTest(change=change):
                trial,proof=self.make()
                if change=='owned':trial.owned=None
                else:trial.last_observation['screenshot']['scope'][change]='foreign'
                with self.assertRaises(RuntimeError):trial.bind_owned_contact_menu(proof)
                self.assertIsNone(trial.menu_contact)

    def test_menu_proof_is_once_only(self):
        trial,proof=self.make();trial.bind_owned_contact_menu(proof)
        with self.assertRaises(RuntimeError):trial.bind_owned_contact_menu(proof)

if __name__=='__main__':unittest.main(verbosity=2)
