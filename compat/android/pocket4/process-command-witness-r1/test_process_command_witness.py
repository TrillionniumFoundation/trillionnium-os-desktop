import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from process_command_witness import PinnedExecutable, validate_executed_command


ARGV = ['/build/tools/normal-builder', '--source', '/build/recipe', '-j6',
        'audio-apex-build', '--work', '/build/work']
INITIAL = {'pid': 4321, 'start_ticks': 123456, 'exe': ARGV[0],
           'cgroup': '0::/system.slice/owned-build.service\n', 'argv': []}


def numeric_proc_executable_available():
    try:
        fd = os.open('/proc/%d/exe' % os.getpid(), os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        return False
    os.close(fd)
    return True


class CommandWitnessTests(unittest.TestCase):
    def current(self):
        return dict(INITIAL, argv=list(ARGV))

    def check(self, current):
        return validate_executed_command(INITIAL, current, ARGV, ARGV[0])

    def test_original_full_dictionary_comparison_reproduces_exec_window_failure(self):
        current = self.current()
        self.assertNotEqual(INITIAL, current)
        with self.assertRaisesRegex(RuntimeError, 'original generation check'):
            if INITIAL != current:
                raise RuntimeError('original generation check')
        self.assertEqual(self.check(current)['pid'], INITIAL['pid'])

    def test_pid_and_start_ticks_cannot_change(self):
        for field in ('pid', 'start_ticks'):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                row = self.current(); row[field] += 1; self.check(row)

    def test_identity_integers_reject_bool_float_and_string(self):
        for field in ('pid', 'start_ticks'):
            for bad in (True, False, 4321.0, '4321', 0, -1):
                with self.subTest(field=field, value=bad), self.assertRaises(RuntimeError):
                    row = self.current(); row[field] = bad; self.check(row)

    def test_executable_and_cgroup_cannot_change(self):
        for field, bad in (('exe', '/build/tools/other'), ('cgroup', '0::/other\n'),
                           ('exe', ''), ('cgroup', False)):
            with self.subTest(field=field, value=bad), self.assertRaises(RuntimeError):
                row = self.current(); row[field] = bad; self.check(row)

    def test_actual_argv_is_exact_even_when_generation_matches(self):
        for argv in ([], ARGV[:-1], ARGV + ['--relaxed'], list(reversed(ARGV)),
                     [*ARGV[:3], '-j1', *ARGV[4:]], [False, *ARGV[1:]], tuple(ARGV)):
            with self.subTest(argv=argv), self.assertRaises(RuntimeError):
                self.check(dict(INITIAL, argv=argv))

    def test_frozen_command_requires_pinned_absolute_executable(self):
        for expected in ('normal-builder', '/build/tools/other', False):
            with self.subTest(expected=expected), self.assertRaises(RuntimeError):
                validate_executed_command(INITIAL, self.current(), ARGV, expected)

    def test_initial_observation_is_not_rewritten(self):
        before = copy.deepcopy(INITIAL); current = self.current(); after = copy.deepcopy(current)
        self.check(current)
        self.assertEqual(INITIAL, before); self.assertEqual(current, after)

    def test_named_executable_pin_rejects_changed_bytes_symlink_and_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'tool'; path.write_bytes(b'owned executable')
            ref = {'path': str(path), 'bytes': path.stat().st_size,
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            with PinnedExecutable(ref) as held:
                self.assertIsNotNone(held.named_fd)
            self.assertIsNone(held.named_fd)
            for key, bad in (('bytes', True), ('bytes', float(ref['bytes'])),
                             ('sha256', '0' * 64), ('sha256', True)):
                with self.subTest(field=key), self.assertRaises(RuntimeError):
                    with PinnedExecutable(dict(ref, **{key: bad})):
                        pass
            link = Path(temporary) / 'link'; link.symlink_to(path)
            with self.assertRaises(OSError):
                with PinnedExecutable(dict(ref, path=str(link))):
                    pass

    def test_held_executable_rejects_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'tool'; path.write_bytes(b'owned executable')
            ref = {'path': str(path), 'bytes': path.stat().st_size,
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            with self.assertRaises(RuntimeError):
                with PinnedExecutable(ref) as held:
                    replacement = Path(temporary) / 'replacement'; replacement.write_bytes(path.read_bytes())
                    replacement.replace(path); held.verify_named()
            self.assertIsNone(held.named_fd)

    @unittest.skipUnless(numeric_proc_executable_available(), 'readable Linux numeric procfs executable required')
    def test_actual_running_executable_requires_two_boundaries_and_matches_pin(self):
        path = Path('/proc/self/exe').resolve()
        ref = {'path': str(path), 'bytes': path.stat().st_size,
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        with PinnedExecutable(ref) as held:
            held.verify_running(os.getpid())
            with self.assertRaises(RuntimeError):
                held.record()
            held.verify_running(os.getpid())
            self.assertEqual(held.record()['boundary_observations'], 2)
        self.assertIsNone(held.executed_fd); self.assertIsNone(held.named_fd)


if __name__ == '__main__':
    unittest.main()
