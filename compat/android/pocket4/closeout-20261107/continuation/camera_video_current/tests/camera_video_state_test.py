"""Nine portable controls for the exact f9 public Camera recording state machine.

The owner fixture is retained byte-for-byte. All observations are synthetic
public-API values; no Main, Android, process, media or physical audio is used.
The old source is reconstructed and pinned only to demonstrate the regression.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TESTS = 9
STATE_PIN = (21072, '68c6369a068d822b0ea4e849cf2172d0180bbe69b3c576e7aa74ba2f6e7d66fc')
OWNER_FIXTURE_PIN = (8070, '6231c471ec505ed11afb7c40fa2d7f0e4c05299a2d297a31981a4fa223097e51')
OLD_STATE_PIN = (20889, '536291d92f09941771673232f12208154827ca3e7b1ea49d12b769cae9507aa2')
OWNER_SEALED_CLIP_LEGACY_AST = '7ccc54fb39d968f6307e39bdcf241d1e7641bf5ea04d0de08c5dda143898e9fe'
OWNER_SEALED_CLIP_NORMALIZED_AST = '55df6764b50d50932fdc134fd63e9b0d44becafd6d47cd4b2cf879b103ad20eb'
OWNER_DECODER_SOURCE_PIN = (15348, '2536849daa9913832bc8c33bf4de17292f0e8a471c571c11ca0b0ddfb3b11c8a')
CASES = ('playback_then_restore_photo', 'restore_photo_then_playback', 'original_video_mode',
    'no_audio_playback_rejected', 'wrong_final_mode_rejected', 'unretired_host_rejected',
    'unclosed_task_rejected', 'unpreserved_state_rejected', 'unacknowledged_restore_rejected')


def pinned(path, expected):
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != expected:
        raise RuntimeError('EXACT_OWNER_STATE_OR_FIXTURE_PIN:' + str(path))
    return raw.decode('utf-8')


def canonical_ast(value):
    """Keep semantic fields, independent of ast.dump's versioned formatting.

    CPython 3.12 adds empty type_params to functions/classes; 3.13 adds
    default_value=None to type parameters. Their absence has the same meaning
    on earlier interpreters. No other empty or optional fields are discarded.
    """
    if isinstance(value, ast.AST):
        kind = type(value).__name__
        fields = {}
        for key, item in ast.iter_fields(value):
            if (kind in ('FunctionDef', 'AsyncFunctionDef', 'ClassDef')
                    and key == 'type_params' and type(item) is list and not item):
                continue
            if (kind in ('TypeVar', 'ParamSpec', 'TypeVarTuple')
                    and key == 'default_value' and item is None):
                continue
            fields[key] = canonical_ast(item)
        return {'node': kind, 'fields': fields}
    if type(value) is list:
        return [canonical_ast(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        # Tag scalar types so bool/int and other equal JSON values cannot alias.
        return {'scalar': type(value).__name__, 'value': value}
    if type(value) is bytes:
        return {'scalar': 'bytes', 'hex': value.hex()}
    if type(value) is complex:
        return {'scalar': 'complex', 'real': value.real, 'imag': value.imag}
    if value is Ellipsis:
        return {'scalar': 'ellipsis'}
    raise TypeError('unsupported AST field type: ' + type(value).__name__)


class OwnerRestorationControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pinned(ROOT / 'source/camera_video_state.py', STATE_PIN)
        fixture_path = ROOT / 'tests/fixtures/owner_camera_video_state_fixture.py'
        fixture_text = pinned(fixture_path, OWNER_FIXTURE_PIN)
        cls.fixture = types.ModuleType('camera_owner_f9_public_api_fixture')
        cls.fixture.__file__ = str(fixture_path)
        exec(compile(fixture_text, str(fixture_path), 'exec'), cls.fixture.__dict__)
        # Preserve the fixture bytes while giving its new location the actual
        # production-source filename used for compile diagnostics.
        cls.fixture.source = ROOT / 'source/camera_video_state.py'
        cls.cases = cls.fixture.run_cases(cls.text)
        if set(cls.cases) != set(CASES):
            raise RuntimeError('EXACT_NINE_OWNER_STATE_SCENARIOS')
        tree = ast.parse((ROOT / 'source/camera_decode.py').read_text(encoding='utf-8'))
        helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'sealed_clip']
        if len(helpers) != 1 or hashlib.sha256(json.dumps(canonical_ast(helpers[0]), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() != OWNER_SEALED_CLIP_NORMALIZED_AST:
            raise RuntimeError('EXACT_OWNER_SEALED_CLIP_HELPER_AST')

    def case(self, name):
        self.assertIs(self.cases[name]['passed'], True, self.cases[name])

    def test_playback_then_restore_photo(self):
        self.case('playback_then_restore_photo')
        new = ("        # Restoring Photo after verified playback moves the state to MODE_RESTORED.\n"
               "        # The audio/playback receipts below still gate success in either order.\n"
               "        restored = (self.state in ('PLAYBACK_VERIFIED', 'MODE_RESTORED') and\n")
        old = "        restored = (self.state == 'PLAYBACK_VERIFIED' and\n"
        self.assertEqual(self.text.count(new), 1)
        prior = self.text.replace(new, old)
        self.assertEqual((len(prior.encode()), hashlib.sha256(prior.encode()).hexdigest()), OLD_STATE_PIN)
        old_cases = self.fixture.run_cases(prior)
        self.assertEqual({name for name, value in old_cases.items() if value['passed'] is not True},
                         {'playback_then_restore_photo'})
        self.assertEqual(self.cases['playback_then_restore_photo']['observed_state'], 'MODE_RESTORED')

    def test_restore_photo_then_playback(self):
        self.case('restore_photo_then_playback')

    def test_original_video_mode(self):
        self.case('original_video_mode')

    def test_no_audio_playback_rejected(self):
        self.case('no_audio_playback_rejected')
        shared = {'nonce': '0' * 16, 'epoch_sha256': '0' * 64,
            'uri': 'content://media/external_primary/video/media/1000', 'file_sha256': '0' * 64,
            'scope': {}, 'phase': {}, 'outcome_unknown': True}
        cases = [(side, field, value, 'AUDIO_PLAYBACK_MUST_BE_THIS_FRESH_RECORDING')
            for side in ('audio', 'playback') for field, value in shared.items()]
        cases += [('audio', field, value, 'NONZERO_PCM_OR_OLD_HOST_CHALLENGE_IS_NOT_CAMERA_AUDIO')
            for field, value in {'decoded_own_audio_nonce_match': False, 'CAMCORDER_uid': 1000,
                'actual_HAL_input_session_bound': False, 'actual_physical_source_bound': False,
                'baseline_negative_passed': False, 'decoy_negative_passed': False}.items()]
        cases += [('playback', field, value, 'SAME_OWNED_URI_VIDEO_AND_PHYSICAL_PLAYBACK_REQUIRED')
            for field, value in {'actual_owned_uri_intent': False, 'actual_video_decoder_outputs_advanced': False,
                'two_current_foreground_pixel_observations': False, 'physical_presented_frame_claim': True,
                'actual_Android_output_session_bound': False, 'physical_playback_nonce_match': False,
                'owned_player_closed': False, 'foreign_tasks_unchanged': False}.items()]
        for side, field, wrong, why in cases:
            with self.subTest(side=side, field=field):
                namespace = self.fixture.namespace(self.text)
                original = namespace['Recording'].audio_and_playback

                def corrupt(recording, **kwargs):
                    changed = copy.deepcopy(kwargs)
                    changed[side][field] = wrong
                    return original(recording, **changed)

                namespace['Recording'].audio_and_playback = corrupt
                with mock.patch.object(self.fixture, 'namespace', return_value=namespace):
                    with self.assertRaisesRegex(namespace['Refusal'], '^' + why + '$'):
                        self.fixture.run_cases(self.text)

    def test_wrong_final_mode_rejected(self):
        self.case('wrong_final_mode_rejected')

    def test_unretired_host_rejected(self):
        self.case('unretired_host_rejected')

    def test_unclosed_task_rejected(self):
        self.case('unclosed_task_rejected')

    def test_unpreserved_state_rejected(self):
        self.case('unpreserved_state_rejected')

    def test_unacknowledged_restore_rejected(self):
        self.case('unacknowledged_restore_rejected')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OwnerRestorationControls)
    if suite.countTestCases() != EXPECTED_TESTS:
        raise RuntimeError('EXACT_NINE_STATE_CONTROLS')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and result.testsRun == EXPECTED_TESTS and not result.skipped
    report = {'schema': 'pocket4-camera-f9-state-source-controls-v1', 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
        'passed': passed,
        'elapsed_seconds': time.monotonic() - start, 'executable': sys.executable, 'python': sys.version,
        'owner_fixture_byte_identical': passed, 'owner_state_byte_identical': passed,
        'owner_sealed_clip_ast_identical': passed, 'old_state_regression_reproduced': passed,
        'declared_binding_negative_subcases': 28, 'Main_actions': 0, 'Android_actions': 0,
        'subprocess_actions': 0, 'physical_audio_actions': 0, 'runtime_qualified': False,
        'actual_uid1000_sealed_input_qualified': False,
        'scope': 'synthetic observations through the exact owner public state API and retained owner fixture'}
    with args.report.open('x', encoding='utf-8') as out:
        out.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report['passed'] else 1)
