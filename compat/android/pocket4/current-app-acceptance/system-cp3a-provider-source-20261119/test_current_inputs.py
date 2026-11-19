import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
providers=module('assemble_provider_cohort')
preflight=module('refresh_preflight')
REPO=HERE.parents[4]

class CurrentSourceInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider_data,_=providers.load_inputs(REPO,HERE)
        cls.plan_data,_=preflight.read_fixed(REPO)

    def test_current_outputs_preserve_existing_business_and_runtime_gates(self):
        cohort=providers.build(self.provider_data)
        plan=preflight.build_plan(self.plan_data)
        self.assertEqual(cohort['targets'],self.provider_data['base']['targets'])
        self.assertEqual(cohort['provider_source_verified_count'],4)
        self.assertEqual(cohort['provider_runtime_qualified_count'],0)
        old=preflight.index(self.plan_data['plan']['packages']);new=preflight.index(plan['packages'])
        self.assertEqual(sum(new[p]==old[p] for p in old),38)
        self.assertEqual(new[preflight.UNITED]['source_version_code'],3622)
        self.assertEqual(new[preflight.UNITED]['source_body_pin_metadata']['f9'][-1],1795080536543405958)
        self.assertEqual(plan['required_before_installation'],self.plan_data['plan']['required_before_installation'])
        self.assertFalse(plan['production_ready'])

    def test_uniform_signer_guess_is_rejected(self):
        data=copy.deepcopy(self.provider_data)
        data['receipts']['com.android.providers.media.module']['signer_certificate_sha256']=['a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc']
        with self.assertRaisesRegex(ValueError,'exact distinct provider signer'):
            providers.build(data)

    def test_CAPEX_hash_cannot_be_used_as_APK_identity(self):
        data=copy.deepcopy(self.provider_data)
        row=next(x for x in data['result']['providers'] if x['package']=='com.android.providers.media.module')
        row['apk']['sha256']=data['result']['media_source_chain']['capex']['sha256']
        with self.assertRaisesRegex(ValueError,'provider APK identity mismatch'):
            providers.build(data)

    def test_source_provider_cannot_promote_runtime(self):
        data=copy.deepcopy(self.provider_data);data['result']['runtime_qualified']=True
        with self.assertRaisesRegex(ValueError,'source result promotes runtime'):
            providers.build(data)

    def test_omitted_meituan_migration_is_rejected(self):
        data=copy.deepcopy(self.plan_data)
        del data['plan']['required_before_installation']['Meituan_official_signer_and_existing_userdata_migration']
        with self.assertRaisesRegex(ValueError,'installation prerequisites changed'):
            preflight.build_plan(data)

    def test_missing_current_split_or_old_version_is_rejected(self):
        data=copy.deepcopy(self.plan_data);data['receipt']['identities'].pop()
        with self.assertRaisesRegex(ValueError,'complete original four-APK source qualification'):
            preflight.build_plan(data)
        data=copy.deepcopy(self.plan_data)
        preflight.index(data['state']['applications'])[preflight.UNITED]['current_registry_record']['version_code']=3621
        with self.assertRaisesRegex(ValueError,'current state and registry disagree'):
            preflight.build_plan(data)

    def test_other38_row_or_United_runtime_change_is_rejected(self):
        result=preflight.build_plan(self.plan_data)
        preflight.index(result['packages'])['com.android.calendar']['source_version']='invented'
        with self.assertRaisesRegex(ValueError,'another package row changed'):
            preflight.validate_output(result,self.plan_data)
        result=preflight.build_plan(self.plan_data)
        preflight.index(result['packages'])[preflight.UNITED]['actual_runtime_bindings']['UID']=10000
        with self.assertRaisesRegex(ValueError,'United business or runtime gate changed'):
            preflight.validate_output(result,self.plan_data)

if __name__=='__main__':
    unittest.main()
