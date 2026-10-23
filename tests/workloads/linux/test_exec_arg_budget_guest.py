import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_exec_arg_budget_guest as guest


def green_lines():
    lines = []
    for name, count in guest.GROUPS:
        lines.extend(f'test_{name}: `case_{i}()` passed [got Success]' for i in range(count))
        lines.append(f'test_{name} summary: {count} tests passed, 0 tests failed')
    return lines + [guest.PROCESS_EXIT, guest.BOOT_MARKER]


def verdict(lines, code=33, timed_out=False):
    return guest.evaluate(('\n'.join(lines) + '\n').encode(), code, timed_out)


class ExecArgumentEvidenceTests(unittest.TestCase):
    def test_exact_nineteen_checks_are_required(self):
        result = verdict(green_lines())
        self.assertTrue(result['passed'])
        self.assertEqual(result['checks_passed'], 19)

    def test_missing_or_duplicate_case_is_rejected(self):
        lines = green_lines()
        self.assertFalse(verdict(lines[1:])['passed'])
        self.assertFalse(verdict([lines[0]] + lines)['passed'])

    def test_a_failed_or_skipped_case_cannot_hide_behind_summaries(self):
        for replacement in ('test_combined_argv_envp_exact_limit: `case()` failed [got Success]',
                            'test_combined_argv_envp_exact_limit skipped: unsupported'):
            lines = green_lines()
            lines[0] = replacement
            self.assertFalse(verdict(lines)['passed'])

    def test_linux_reference_without_shebang_does_not_qualify_the_guest(self):
        lines = [line for line in green_lines() if not line.startswith('test_shebang_')]
        self.assertFalse(verdict(lines)['passed'])

    def test_case_order_and_completion_are_checked(self):
        lines = green_lines()
        lines[0], lines[2] = lines[2], lines[0]
        self.assertFalse(verdict(lines)['passed'])
        lines = green_lines()
        lines[-1], lines[-2] = lines[-2], lines[-1]
        self.assertFalse(verdict(lines)['passed'])

    def test_exit_timeout_and_fatal_failures_are_rejected(self):
        for code in (0, 1, 65, None, True):
            self.assertFalse(verdict(green_lines(), code=code)['passed'])
        self.assertFalse(verdict(green_lines(), timed_out=True)['passed'])
        for error in ('Kernel panic', 'fatal error: setup failed', 'unexpected child status=0'):
            self.assertFalse(verdict(green_lines() + [error])['passed'])
        self.assertFalse(verdict(green_lines() + [guest.PROCESS_EXIT])['passed'])


if __name__ == '__main__':
    unittest.main()
