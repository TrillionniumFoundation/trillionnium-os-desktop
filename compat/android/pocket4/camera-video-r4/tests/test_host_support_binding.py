"""Local source controls for the current Camera r4 host-support migration.

The identity controls run the real entry dispatch with bootstrap and the final
collector substituted. Plan controls use a synthetic baseline implementing the
unchanged public API; they never construct a real BusinessBaseline. Composition
controls run the actual inspect-source CLI on a synthetic local preparation.
No Main, Android, camera, audio stream, support bundle, or real lease is opened.
"""
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source'
MANIFEST = json.loads((ROOT / 'source-manifest.json').read_bytes())
FIXTURES = ROOT / 'tests' / 'fixtures'
HOST_REF = {
    'path': '/home/alex/work/pocket4-android-final/qualification/business-support-host-20261108-r1/source-manifest.json',
    'bytes': 1002,
    'sha256': '8cfa9cb05bb7e7768350dbe04acd4cd6421b9f4e8493746aad49b64c37969e70',
}
COMMON_SHA = '6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0'


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')
    return reference(path)


def load_module(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(Path(path).resolve())
    exec(compile(Path(path).read_bytes(), module.__file__, 'exec'), module.__dict__)
    return module


class CameraHostBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = MANIFEST['production_files']
        assert len(rows) == 29
        assert {ROOT / row['path'] for row in rows} == set(SOURCE.iterdir())
        expected_changes = {
            'source/app_common.py': (38256, '6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0'),
            'source/camera_audio_binding.py': (18775, 'c8c0c123153a83a2397595d2efcf6ba3b40f60916362403348d1f6f6a57a4754'),
            'source/camera_audio_runtime.py': (26272, 'b480c7e99cd44bd9ff79e7d95fb87e80f7634c843e8e9c77f3f38ea8ab9f8cee'),
            'source/camera_entry.py': (9811, '55607f576146c9adc8792fdeb510c1992512ac4d782ccd0efcb75415c81ac4f9'),
            'source/camera_case.py': (7576, '19f015a8dcf836e6aa8160af9566abc04923b1fe9d5fad34bd98e89ec9d883d7'),
            'source/camera_decode.py': (14597, '7a42785a9d5d16fbc4644d0db961acd965b42f79dc9a75b2f101d88ab51574a4'),
            'source/camera_video_media.py': (9197, '58c5b6508fe23532fe4282c38446e75dfc25800ed6b063691da80bd431f74190'),
        }
        assert {row['path'] for row in rows if row['changed']} == set(expected_changes)
        assert sum(not row['changed'] for row in rows) == 22
        for row in rows:
            actual = reference(ROOT / row['path'])
            assert (actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256'])
            if row['changed']:
                assert (row['bytes'], row['sha256']) == expected_changes[row['path']]
            else:
                assert (row['bytes'], row['sha256']) == (row['original']['bytes'], row['original']['sha256'])
            compile((ROOT / row['path']).read_bytes(), row['path'], 'exec')
        assert reference(SOURCE / 'app_common.py')['sha256'] == COMMON_SHA
        for row in json.loads((FIXTURES / 'source-manifest.json').read_bytes())['files']:
            actual = reference(ROOT / row['path'])
            assert (actual['bytes'], actual['sha256']) == (row['bytes'], row['sha256'])

    def setUp(self):
        self.common = load_module(SOURCE / 'app_common.py', 'candidate_common')
        self.entry = load_module(SOURCE / 'camera_entry.py', 'candidate_entry')
        self.planner = load_module(SOURCE / 'camera_plan.py', 'candidate_plan')
        self.profiles = load_module(SOURCE / 'camera_profiles.py', 'candidate_profiles')
        self.legacy = load_module(FIXTURES / 'original-app_common.py', 'original_common')
        self.assertEqual(self.common.SUPPORT_REF, HOST_REF)

    def identity_dispatch(self, common, entry, entry_path, manifest, role, expected_error=None):
        with tempfile.TemporaryDirectory(prefix='p4-camera-source-identity-') as temporary:
            root = Path(temporary).resolve()
            qualification = write_json(root / 'qualification.json', {'source_manifest': manifest})
            request_value = {'baseline': {'synthetic_source_control': True}, 'qualification': qualification}
            request = write_json(root / 'request.json', request_value)
            output = root / 'collector-output.json'
            entry_ref = reference(entry_path)
            packet = {'files': [entry_ref]}
            planner = types.SimpleNamespace(named=mock.Mock(return_value=self.profiles))
            collector = mock.Mock(return_value={'synthetic_collector_reached': True})
            argv = [str(entry_path), '--preparation', str(root / 'synthetic-unopened.json'),
                    '--expect-preparation-sha256', '1' * 64, 'identity',
                    '--request', request['path'], '--expect-request-sha256', request['sha256'],
                    '--role', role, '--output', str(output)]
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(entry, 'bootstrap', return_value=(common, packet, {}, planner)))
                stack.enter_context(mock.patch.object(entry.os, 'getuid', return_value=0))
                stack.enter_context(mock.patch.object(entry.os, 'geteuid', return_value=0))
                stack.enter_context(mock.patch.object(common, 'collect_identity', collector))
                stack.enter_context(mock.patch.object(common, 'support', side_effect=AssertionError('No support load in identity control')))
                stack.enter_context(mock.patch.object(sys, 'argv', argv))
                stdout = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if expected_error:
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        entry.main()
                    collector.assert_not_called()
                else:
                    self.assertEqual(entry.main(), 0)
                    profile = {'camera': self.profiles.CAMERA, 'player': self.profiles.PLAYER,
                               'native-helper': self.profiles.HELPER}[role]
                    collector.assert_called_once_with(request_value, str(output), profile, entry_ref)
                    self.assertFalse(json.loads(stdout.getvalue())['whole_app_business_accepted'])
            self.assertFalse(output.exists(), 'Synthetic collector must not create a runtime receipt')

    def test_original_binding_rejects_current_host_before_collector(self):
        entry_path = FIXTURES / 'original-camera_entry.py'
        entry = load_module(entry_path, 'original_entry')
        self.identity_dispatch(self.legacy, entry, entry_path, HOST_REF, 'camera', 'EXACT_CURRENT_R9_MAIN_BASELINE')

    def test_candidate_admits_current_host_for_all_three_identity_roles(self):
        for role in ('camera', 'player', 'native-helper'):
            with self.subTest(role=role):
                self.identity_dispatch(self.common, self.entry, SOURCE / 'camera_entry.py', HOST_REF, role)

    def test_candidate_rejects_legacy_clock_and_tampered_qualification(self):
        for cohort in (self.legacy.SUPPORT_REF, self.common.CLOCK_SUPPORT_REF, {**HOST_REF, 'sha256': '0' * 64}):
            with self.subTest(cohort=cohort):
                self.identity_dispatch(self.common, self.entry, SOURCE / 'camera_entry.py', cohort,
                                       'camera', 'EXACT_CURRENT_HOST_MAIN_BASELINE')

    def plan_inputs(self, cohort, rejected=False):
        request = {name: {'synthetic_ref': name} for name in (
            'baseline', 'qualification', 'target_identity', 'player_identity', 'helper_identity')}
        target, player, helper, limits = self.profiles.profiles('camera_video')
        baseline = types.SimpleNamespace(qualification={'source_manifest': cohort},
            value={'data_continuity': {'package_uids': {
                target['package']: target['uid'], player['package']: player['uid']}}}, guard=mock.Mock())
        factory = mock.Mock(return_value=baseline)
        support = mock.Mock(return_value=(None, {'business_baseline.py': types.SimpleNamespace(BusinessBaseline=factory)}))
        packet = {'synthetic_packet': True}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.common, 'support', support))
            read = stack.enter_context(mock.patch.object(self.common, 'read_ref', side_effect=lambda ref: json.dumps(ref).encode()))
            identity = stack.enter_context(mock.patch.object(self.common, 'validate_identity'))
            named = stack.enter_context(mock.patch.object(self.planner, 'named', return_value=self.profiles))
            if rejected:
                with self.assertRaisesRegex(RuntimeError, 'ACTUAL_CURRENT_MAIN_SUPPORT'):
                    self.planner.inputs(self.common, 'camera_video', request, packet)
                read.assert_not_called(); identity.assert_not_called(); named.assert_not_called()
                baseline.guard.assert_not_called()
            else:
                value = self.planner.inputs(self.common, 'camera_video', request, packet)
                self.assertIs(value[0], baseline)
                self.assertEqual(value[1:5], (target, player, helper, limits))
                self.assertEqual(identity.call_count, 3)
                baseline.guard.assert_called_once_with()
            support.assert_called_once_with(HOST_REF)
            factory.assert_called_once_with(request['baseline'], request['qualification'])

    def test_plan_inputs_preserves_public_baseline_interface_and_host_gate(self):
        self.plan_inputs(HOST_REF)

    def test_plan_inputs_rejects_old_cohort_before_identity_or_guard(self):
        self.plan_inputs(self.legacy.SUPPORT_REF, rejected=True)

    def test_active_plan_keeps_exact_cohort_qualification_and_role_scope(self):
        target, player, helper, limits = self.profiles.profiles('camera_video')
        ref = lambda name: {'synthetic_ref': name}
        flows = [{'role': role, 'nonce': str(index) * 32,
                  'flow_root': str(self.common.FINAL / 'qualification' / ('business-flow-camera-video-' + str(index) * 32))}
                 for index, role in enumerate(('camera', 'player', 'camera'), 1)]
        value = {'schema': 'pocket4-current-camera-video-active-plan-v1', 'kind': 'camera_video',
            **{name: ref(name) for name in ('baseline', 'qualification', 'target_identity', 'player_identity',
                'helper_identity', 'source_preparation', 'base_plan', 'lease', 'action_lock')},
            'framework_epoch_sha256': 'f' * 64, 'support_manifest': HOST_REF,
            'target_profile': target, 'player_profile': player, 'helper_profile': helper, 'limits': limits,
            'task_source_manifests': {'camera': ref('camera-task'), 'player': ref('player-task')},
            'original_gates': self.common.GATES, 'flows': flows,
            'case_root': str(self.common.FINAL / 'qualification' / ('business-camera-video-plan-' + '1' * 32)),
            'audio_nonce': '1' * 16, 'whole_app_business_accepted': False, 'automatic_retry': False}
        baseline = types.SimpleNamespace(baseline_ref=value['baseline'], qualification_ref=value['qualification'],
            value={'framework_epoch': {'sha256': value['framework_epoch_sha256']}})
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(self.planner, 'preparation', return_value={'synthetic_packet': True}))
            stack.enter_context(mock.patch.object(self.planner, 'named', return_value=self.profiles))
            stack.enter_context(mock.patch.object(self.planner, 'source_packet', return_value={}))
            for flow in flows:
                key = 'target_identity' if flow['role'] == 'camera' else 'player_identity'
                profile = target if flow['role'] == 'camera' else player
                scope = {**flow, 'task_source_manifest': value['task_source_manifests'][flow['role']],
                    'actual_resolution_receipt': value[key],
                    'installed_helper_receipts': [value[name] for name in self.planner.IDENTITIES if name != key],
                    'support_manifest': HOST_REF, **{name: profile[name] for name in ('package', 'uid', 'component')}}
                self.planner.validate(self.common, value, baseline, scope, semantic=False)
                with self.assertRaisesRegex(RuntimeError, 'EXACT_ROLE_BOUND_RECORDER_SCOPE'):
                    self.planner.validate(self.common, value, baseline,
                        {**scope, 'support_manifest': self.legacy.SUPPORT_REF}, semantic=False)
            for changed in ({**value, 'support_manifest': self.legacy.SUPPORT_REF},
                            {**value, 'qualification': ref('other-qualification')}):
                with self.assertRaisesRegex(RuntimeError, 'UNCHANGED_VIDEO_CURRENT_INPUTS_AND_NONCE'):
                    self.planner.validate(self.common, changed, baseline, semantic=False)

    def source_inspection(self, *, original_entry=False, tamper=False):
        with tempfile.TemporaryDirectory(prefix='p4-camera-source-composition-') as temporary:
            root = Path(temporary).resolve(); source = root / 'source'
            shutil.copytree(SOURCE, source)
            if original_entry:
                shutil.copyfile(FIXTURES / 'original-camera_entry.py', source / 'camera_entry.py')
            packet = {'schema': 'pocket4-current-camera-video-preparation-v1', 'code_entrypoints_complete': True,
                'Android_execution_authorized_by_publication': False, 'whole_app_business_accepted': False,
                'files': [reference(path) for path in sorted(source.iterdir())],
                'origins': [reference(FIXTURES / 'original-app_common.py'), reference(FIXTURES / 'original-camera_entry.py')]}
            prep = write_json(root / 'synthetic-source-preparation.json', packet)
            if tamper:
                with (source / 'camera_session.py').open('ab') as stream:
                    stream.write(b'\n# Local negative control after the source pin was made.\n')
            return subprocess.run([sys.executable, '-I', '-B', str(source / 'camera_entry.py'),
                '--preparation', prep['path'], '--expect-preparation-sha256', prep['sha256'], 'inspect-source'],
                text=True, capture_output=True, timeout=15, check=False)

    def test_actual_local_inspect_source_composition_stays_inert(self):
        result = self.source_inspection()
        self.assertEqual(result.returncode, 0, result.stderr)
        observation = json.loads(result.stdout)
        self.assertEqual(observation['source_files'], 29)
        self.assertEqual(observation['Main_actions'], 0)
        self.assertEqual(observation['Android_UI_actions'], 0)
        self.assertFalse(observation['runtime_qualified'])
        self.assertFalse(observation['whole_app_business_accepted'])
        self.assertFalse(observation['source_publication_authorizes_Android'])
        self.assertTrue(observation['camera_recovery_preparation_pending'])
        self.assertEqual(result.stderr, '')

    def test_common_only_swap_is_rejected_by_original_entry_pin(self):
        result = self.source_inspection(original_entry=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('EXACT_CURRENT_R9_COMMON_LIBRARY', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_inspection_rejects_changed_session_before_any_module_execution(self):
        result = self.source_inspection(tamper=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FROZEN_VIDEO_COMPONENT_CHANGED:camera_session.py', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_migration_preserves_non_binding_ast_and_business_contract(self):
        def normalized(path, common=False):
            tree = ast.parse(Path(path).read_bytes())
            names = {'SUPPORT', 'SUPPORT_REF', 'CLOCK_SUPPORT_REF'} if common else {'COMMON_PIN'}
            tree.body = [node for node in tree.body if not (isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id in names for target in node.targets))]
            if not common:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        node.value = node.value.replace('EXACT_CURRENT_HOST_COMMON_LIBRARY', 'EXACT_CURRENT_R9_COMMON_LIBRARY')
                        node.value = node.value.replace('EXACT_CURRENT_HOST_MAIN_BASELINE', 'EXACT_CURRENT_R9_MAIN_BASELINE')
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(normalized(SOURCE / 'app_common.py', True), normalized(FIXTURES / 'original-app_common.py', True))
        self.assertEqual(normalized(SOURCE / 'camera_entry.py'), normalized(FIXTURES / 'original-camera_entry.py'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
