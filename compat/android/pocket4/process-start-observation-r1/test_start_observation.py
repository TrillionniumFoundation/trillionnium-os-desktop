import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

support_path = Path(os.environ.get('BUILD_SUPPORT_SOURCE', str(Path(__file__).with_name('linux_build_support.py'))))
spec = importlib.util.spec_from_file_location('support', support_path)
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)


class InitialObservationTests(unittest.TestCase):
    def test_exit_gap_waits_for_same_unreaped_pidfd(self):
        reaper = Mock(); reaper.peek.side_effect = [None, 'kernel_exit']
        reaper.observed.return_value = {'pid': 17, 'code': 1, 'status': 0}
        with patch.object(s, 'process_identity', side_effect=FileNotFoundError), \
             patch.object(s.select, 'poll') as poll:
            result = s.initial_process_observation(17, 9, reaper)
        self.assertEqual(result['unreaped_kernel_exit'], {'pid': 17, 'code': 1, 'status': 0})
        self.assertTrue(result['exited_before_process_snapshot'])
        self.assertEqual(reaper.peek.call_args_list[0].args, (17, 9))
        self.assertEqual(reaper.peek.call_args_list[1].args, (17, 9))
        poll.return_value.register.assert_called_once_with(9, s.select.POLLIN)
        poll.return_value.poll.assert_called_once_with(10)
        reaper.retire.assert_not_called()

    def test_transient_gap_can_return_actual_identity(self):
        current = {'pid': 17, 'start_ticks': 100, 'argv': ['actual']}
        reaper = Mock(); reaper.peek.return_value = None
        with patch.object(s, 'process_identity', side_effect=[ProcessLookupError(), current]), \
             patch.object(s.select, 'poll'):
            self.assertIs(s.initial_process_observation(17, 9, reaper), current)
        reaper.observed.assert_not_called()

    def test_missing_identity_and_exit_have_finite_deadline(self):
        reaper = Mock(); reaper.peek.return_value = None
        with patch.object(s, 'process_identity', side_effect=FileNotFoundError), \
             patch.object(s.time, 'monotonic', side_effect=[1.0, 1.6]), \
             patch.object(s.select, 'poll'):
            with self.assertRaisesRegex(RuntimeError, 'remained unavailable'):
                s.initial_process_observation(17, 9, reaper)

    def test_permission_errors_are_not_disguised_as_exit(self):
        reaper = Mock()
        with patch.object(s, 'process_identity', side_effect=PermissionError), \
             patch.object(s.select, 'poll'):
            with self.assertRaises(PermissionError):
                s.initial_process_observation(17, 9, reaper)
        reaper.peek.assert_not_called()


if __name__ == '__main__':
    unittest.main()
