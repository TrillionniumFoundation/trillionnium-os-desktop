# SPDX-License-Identifier: MPL-2.0
import unittest
from check import NAMES, check


def serial():
    return ''.join(f'UNIX_OWNER_CASE {name} PASS\n' for name in NAMES) + \
        'UNIX_OWNER_COMPLETE cases=10 failures=0\nUNIX_OWNER_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'


class Evidence(unittest.TestCase):
    def test_exact_full_guest(self):
        self.assertTrue(check(serial(), 33, False)['passed'])

    def test_timeout_and_marker_only_cannot_pass(self):
        for code, timed_out in [(None, True), (33, True), (0, False), (65, False)]:
            self.assertFalse(check(serial(), code, timed_out)['passed'])

    def test_missing_substitution_duplicate_or_reordered_case(self):
        for name in NAMES:
            line = f'UNIX_OWNER_CASE {name} PASS\n'
            for changed in [serial().replace(line, ''), serial().replace(line, line * 2),
                            serial().replace(name, 'unrelated', 1)]:
                self.assertFalse(check(changed, 33, False)['passed'])

    def test_incomplete_or_duplicate_completion(self):
        for marker in ['UNIX_OWNER_COMPLETE cases=10 failures=0\n',
                       'UNIX_OWNER_PROBE_EXIT=0\n', 'TRILLIONNIUM_A01_BOOT_OK\n']:
            self.assertFalse(check(serial().replace(marker, ''), 33, False)['passed'])
            self.assertFalse(check(serial() + marker, 33, False)['passed'])

    def test_linux_reference_is_not_kernel_qualification(self):
        raw = ''.join(f'UNIX_OWNER_CASE {name} PASS\n' for name in NAMES[:2])
        raw += 'UNIX_OWNER_COMPLETE cases=2 failures=0\nUNIX_OWNER_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'
        self.assertFalse(check(raw, 33, False)['passed'])

    def test_explicit_failed_substep_rejects_even_with_all_markers(self):
        self.assertFalse(check(serial() + 'UNIX_OWNER_FAIL line=1 errno=5\n', 33, False)['passed'])


if __name__ == '__main__':
    unittest.main()
