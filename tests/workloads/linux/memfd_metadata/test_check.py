# SPDX-License-Identifier: MPL-2.0
import unittest
from check import NAMES, check


def serial():
    return 'MEMFD_METADATA_BEGIN\n' + ''.join(f'MEMFD_METADATA_PASS {n}\n' for n in NAMES) + \
        'MEMFD_METADATA_COMPLETE cases=4\nMEMFD_METADATA_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'


class Evidence(unittest.TestCase):
    def test_complete_original_guest(self):
        self.assertTrue(check(serial(), 33, False)['passed'])

    def test_raw_exit_and_deadline_are_required(self):
        for code, timeout in [(None, True), (33, True), (0, False), (65, False)]:
            self.assertFalse(check(serial(), code, timeout)['passed'])

    def test_every_case_required_once_and_in_original_order(self):
        for name in NAMES:
            line = f'MEMFD_METADATA_PASS {name}\n'
            for changed in [serial().replace(line, ''), serial().replace(line, line * 2),
                            serial().replace(line, 'MEMFD_METADATA_PASS unrelated\n'),
                            serial().replace(line, '') + line]:
                self.assertFalse(check(changed, 33, False)['passed'])

    def test_all_completion_boundaries_required_once(self):
        for marker in ['MEMFD_METADATA_BEGIN\n', 'MEMFD_METADATA_COMPLETE cases=4\n',
                       'MEMFD_METADATA_PROBE_EXIT=0\n', 'TRILLIONNIUM_A01_BOOT_OK\n']:
            self.assertFalse(check(serial().replace(marker, ''), 33, False)['passed'])
            self.assertFalse(check(serial() + marker, 33, False)['passed'])

    def test_failure_and_panic_never_pass(self):
        for failure in ['MEMFD_METADATA_FAIL error\n', 'kernel panicked at source\n',
                        'Kernel panic\n', 'MEMFD_METADATA_PROBE_EXIT=124\n']:
            self.assertFalse(check(serial() + failure, 33, False)['passed'])

    def test_linux_reference_does_not_qualify_a_kernel(self):
        self.assertFalse(check(serial().replace('MEMFD_METADATA_PROBE_EXIT=0\n', '')
                               .replace('TRILLIONNIUM_A01_BOOT_OK\n', ''), 0, False)['passed'])


if __name__ == '__main__':
    unittest.main()
