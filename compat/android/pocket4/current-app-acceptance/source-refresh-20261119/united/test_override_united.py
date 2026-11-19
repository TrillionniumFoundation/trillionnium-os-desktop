"""Finite source-only United successor controls; no SDK or Android execution."""
import copy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('united_source_override', ROOT / 'override_united.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
DATA = subject.read_inputs(ROOT / 'inputs')
AT = subject.utc(json.loads((ROOT / 'actual/RESULT.json').read_bytes())['created_utc'])


def documents(data=DATA):
    return [subject.parse(b) for b in subject.generate(data, AT).values()]


class UnitedControls(unittest.TestCase):
    def bad_input(self, mutate):
        data = copy.deepcopy(DATA)
        mutate(data)
        with self.assertRaises((ValueError, KeyError)):
            subject.generate(data, AT)

    def bad_output(self, mutate):
        registry, freshness, state = documents()
        mutate(registry, freshness, state)
        with self.assertRaises(ValueError):
            subject.validate_output(DATA, registry, freshness, state, AT)

    def test_actual_complete_new_version_and_three_document_join(self):
        registry, freshness, state = documents()
        selected = next(x for x in registry['applications'] if x['package'] == subject.PACKAGE)
        self.assertEqual((selected['version_name'], selected['version_code']), ('4.2.104', 3622))
        self.assertEqual((len(registry['applications']), len(freshness['rows']), len(state['applications'])), (30,29,39))
        self.assertEqual(selected['expected_input'], DATA['native-input.json']['application']['expected_input'])
        self.assertEqual([a['name'] for a in selected['expected_input']['apks']], list(subject.MEMBERS))

    def test_all_unrelated_records_and_all_installation_gates_preserved(self):
        registry, freshness, state = documents()
        for old, new, field in [(DATA['base-current-source-inputs.json'], registry, 'applications'),
                (DATA['base-current-source-freshness.json'], freshness, 'rows'),
                (DATA['base-CURRENT-SOURCE-STATE.json'], state, 'applications')]:
            self.assertEqual([a for a in old[field] if a['package'] != subject.PACKAGE],
                             [a for a in new[field] if a['package'] != subject.PACKAGE])
        self.assertEqual(state['required_before_installation'],
                         DATA['base-CURRENT-SOURCE-STATE.json']['required_before_installation'])
        self.assertEqual(registry['archives'], DATA['base-current-source-inputs.json']['archives'])
        self.assertEqual(registry['source_overrides'][:-1],
                         DATA['base-current-source-inputs.json']['source_overrides'])

    def test_large_F9_integer_preserved_exactly(self):
        registry, _, _ = documents()
        app = next(a for a in registry['applications'] if a['package'] == subject.PACKAGE)
        self.assertEqual(app['input']['f9'][7], 1795080536543405958)
        self.assertIs(type(app['input']['f9'][7]), int)
        self.assertEqual(app['input'], DATA['SOURCE-HANDOFF.json']['final_input'])

    def test_historical_united_record_and_observations_preserved(self):
        _, freshness, state = documents()
        old = next(a for a in DATA['base-CURRENT-SOURCE-STATE.json']['applications']
                   if a['package'] == subject.PACKAGE)
        new = next(a for a in state['applications'] if a['package'] == subject.PACKAGE)
        self.assertEqual(new['historical_state_record'], old)
        old = next(a for a in DATA['base-current-source-freshness.json']['rows']
                   if a['package'] == subject.PACKAGE)
        new = next(a for a in freshness['rows'] if a['package'] == subject.PACKAGE)
        self.assertEqual(new['complete_inputs'][:-1], old['complete_inputs'])
        self.assertEqual(new['version_observations'][:-1], old['version_observations'])

    def test_old_or_wrong_version_code_rejected(self):
        for name in ('candidate.json','current-metadata.json','SOURCE-HANDOFF.json','current-transport.json'):
            with self.subTest(name=name):
                self.bad_input(lambda d: d[name].update(version_code=3621))

    def test_missing_split_cannot_pass(self):
        self.bad_input(lambda d: d['candidate.json']['apks'].pop())
        self.bad_input(lambda d: d['source-receipt.json']['identities'].pop())

    def test_duplicate_split_and_duplicate_APK_identity_rejected(self):
        self.bad_input(lambda d: d['candidate.json']['apks'].__setitem__(3,
                                                copy.deepcopy(d['candidate.json']['apks'][2])))
        self.bad_input(lambda d: d['candidate.json']['apks'][1].update(
                                                sha256=d['candidate.json']['apks'][0]['sha256']))

    def test_each_actual_SDK37_command_signature_and_version_required(self):
        mutations = [
            lambda r: r.update(signature_verified=False),
            lambda r: r.update(verification_SDK_range=[36,36]),
            lambda r: r.update(version_code=3621),
            lambda r: r['tool_exits'].update(signature=1),
            lambda r: r.update(metadata_outputs_bound_to_apk_sha256='0'*64)]
        for index in range(4):
            for mutate in mutations:
                with self.subTest(index=index):
                    self.bad_input(lambda d: mutate(d['source-receipt.json']['identities'][index]))

    def test_signer_and_GET_ITEMS_certificate_join_required(self):
        self.bad_input(lambda d: d['candidate.json'].update(signer_certificate_sha256=['0'*64]))
        self.bad_input(lambda d: d['current-metadata.json']['certificate_sets'][0].update(
            sha256_base64url='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'))

    def test_complete_zip_and_eleven_native_members_required(self):
        self.bad_input(lambda d: d['source-receipt.json']['complete_zip_integrity'][2].update(
            all_member_crc_verified=False))
        self.bad_input(lambda d: d['source-receipt.json']['selected_abi_native_members'].pop())
        self.bad_input(lambda d: d['source-receipt.json']['binary_metadata'][1]['native_libraries'][0].update(
            elf_machine=62))

    def test_declared_base_and_split_closure_required(self):
        self.bad_input(lambda d: d['source-receipt.json']['split_closure'].update(
            manifest_dependency_closure_verified=False))
        self.bad_input(lambda d: d['source-receipt.json']['split_closure']['dependencies'].pop())

    def test_actual_supervisor_success_reap_and_bookends_required(self):
        self.bad_input(lambda d: d['sdk37-supervisor-RESULT.json']['command'].update(exit_code=1))
        self.bad_input(lambda d: d['sdk37-supervisor-RESULT.json']['command'].update(after_reap_echild=False))
        self.bad_input(lambda d: d['sdk37-worker-RESULT.json'].update(source_bookends_equal=False))
        self.bad_input(lambda d: d['SDK37-CLEANUP.json'].update(cleanup_complete=False))

    def test_actual_container_cannot_be_replaced_with_old_3621(self):
        self.bad_input(lambda d: d['native-input.json']['application']['expected_input'].update(version_code=3621))
        self.bad_output(lambda r,f,s: next(a for a in r['applications'] if a['package']==subject.PACKAGE).update(
            input=copy.deepcopy(next(a for a in DATA['base-current-source-inputs.json']['applications']
                                     if a['package']==subject.PACKAGE)['input'])))

    def test_other_apps_companion_and_scope_cannot_change(self):
        self.bad_output(lambda r,f,s: r['applications'].pop())
        self.bad_output(lambda r,f,s: next(a for a in r['applications'] if a['package']==subject.COMPANION).update(label='changed'))
        self.bad_output(lambda r,f,s: next(a for a in f['rows'] if a['package']!=subject.PACKAGE).update(selected_input_version='wrong'))
        self.bad_output(lambda r,f,s: next(a for a in s['applications'] if a['package']!=subject.PACKAGE).update(kind='changed'))

    def test_gates_exemptions_GSI_and_Beike_custody_cannot_change(self):
        self.bad_output(lambda r,f,s: s['required_before_installation'].pop(next(iter(s['required_before_installation']))))
        self.bad_output(lambda r,f,s: s['exemptions'].pop())
        self.bad_output(lambda r,f,s: s['full_GSI_dependency'].update(sha256='0'*64))
        self.bad_output(lambda r,f,s: s['live_Beike_dependencies'].update(original_destination_custody_must_be_rechecked=False))

    def test_no_runtime_business_or_installation_credit(self):
        for flag in subject.NO_CREDIT:
            with self.subTest(flag=flag):
                self.bad_output(lambda r,f,s: s.update({flag:True}))
        self.bad_output(lambda r,f,s: s.update(all_39_latest_qualified=True))
        self.bad_input(lambda d: d['source-receipt.json'].update(device_profile_match_qualified=True))

    def test_historical_timestamp_is_fixed_and_bounded(self):
        with self.assertRaises(ValueError):
            subject.generate(DATA, AT - timedelta(days=2))
        with self.assertRaises(ValueError):
            subject.generate(DATA, AT + timedelta(days=2))

    def test_duplicate_JSON_keys_and_nonfinite_values_rejected(self):
        for body in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                subject.parse(body)

    def test_exact_input_bytes_and_no_symlink_admission(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'inputs';shutil.copytree(ROOT/'inputs',root,copy_function=shutil.copyfile)
            path=root/'candidate.json';path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaises(ValueError):subject.read_inputs(root)
            path.unlink();path.symlink_to(ROOT/'inputs/candidate.json')
            with self.assertRaises(ValueError):subject.read_inputs(root)

    def test_second_output_directory_reproduces_all_four_metadata_bodies(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'replay'
            result=subprocess.run([sys.executable,'-I','-B',str(ROOT/'override_united.py'),
                '--inputs',str(ROOT/'inputs'),'--out',str(out),'--at',AT.isoformat()],
                capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            for name in ('current-source-inputs.json','current-source-freshness.json',
                         'CURRENT-SOURCE-STATE.json','RESULT.json'):
                self.assertEqual((out/name).read_bytes(),(ROOT/'actual'/name).read_bytes())


if __name__ == '__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UnitedControls))
    print(json.dumps({'state':'PASS_UNITED_SOURCE_CONTROLS' if result.wasSuccessful() else 'FAILED',
        'cases':result.testsRun,'SDK_commands':0,'Android_actions':0,'production_ready':False},sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
