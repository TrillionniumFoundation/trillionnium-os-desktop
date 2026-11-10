#!/usr/bin/python3
"""Original acceptance controls plus actual disabled-shutter observation cases."""
from pathlib import Path
import copy
import importlib.util
import tempfile
import types
import unittest
from unittest.mock import patch

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

candidate = load('ready_candidate', 'accept_camera_ready02.py')
original = load('original_tests', 'test_acceptance.py')
original.accept = candidate

class ReadinessTests(unittest.TestCase):
    def run_preview(self, flags):
        clock, calls = [0.0], []
        roots, tasks = candidate.parse_stacks(original.OTHER + original.CAMERA)
        with tempfile.TemporaryDirectory() as directory:
            trial = candidate.Trial(None, None, Path(directory))
            trial.owned = (900, {851}, 'open')
            trial.stacks = lambda label: (copy.deepcopy(roots), tasks)
            def observe(label, request):
                self.assertEqual(request['op'], 'observe')
                self.assertEqual(request['package'], candidate.PACKAGE)
                calls.append(label)
                clock[0] += .5
                flag = flags[min(len(calls)-1, len(flags)-1)]
                nodes = [] if flag is None else [{'package':candidate.PACKAGE,
                    'resource-id':candidate.PACKAGE + ':id/shutter_button',
                    'visible':True, 'enabled':flag, 'clickable':True}]
                return {'ok':True,'native':{'ok':True,
                    'accessibility_mode_restoration_verified':True,'nodes':nodes},
                    'screenshot':{'scope':{'package':candidate.PACKAGE},'scope_sha256':'a'*64}}
            trial.ui = observe
            with patch.object(candidate.time,'monotonic',side_effect=lambda:clock[0]), \
                 patch.object(candidate.time,'sleep',side_effect=lambda t:clock.__setitem__(0,clock[0]+t)):
                try:
                    result = trial.preview('open')
                    return result, calls, trial.shutter_calls
                except candidate.Stop as error:
                    return error, calls, trial.shutter_calls

    def test_disabled_then_ready_is_read_only_and_uses_new_observation(self):
        result, calls, shutters = self.run_preview([False, True])
        self.assertTrue(result['shutter_ready'])
        self.assertEqual(result['readiness_observations'], 2)
        self.assertEqual(len(set(calls)), 2)
        self.assertEqual(shutters, 0)

    def test_permanently_disabled_is_bounded_and_never_clicked(self):
        result, calls, shutters = self.run_preview([False])
        self.assertIsInstance(result, candidate.Stop)
        self.assertIn('SHUTTER_REMAINED_DISABLED', str(result))
        self.assertEqual(len(calls), 10)
        self.assertEqual(shutters, 0)

    def test_missing_shutter_or_error_page_is_not_waited_away(self):
        result, calls, shutters = self.run_preview([None])
        self.assertIsInstance(result, candidate.Stop)
        self.assertIn('ONE_VISIBLE_SHUTTER_REQUIRED_NO_WAIT', str(result))
        self.assertEqual(len(calls), 1)
        self.assertEqual(shutters, 0)

if __name__ == '__main__':
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(original),
                               unittest.defaultTestLoader.loadTestsFromTestCase(ReadinessTests)])
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
