# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import unittest
import check

HERE = Path(__file__).resolve().parent


class OracleTests(unittest.TestCase):
    def test_linux_shape_only(self):
        raw = (HERE/'linux-reference.log').read_text() + 'SUPPLEMENTARY_DAC_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'
        result = check.check(raw, 33, False)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['cases']), 6)
        self.assertFalse(result['production_qualification'])

    def test_strict_rejections(self):
        raw = (HERE/'linux-reference.log').read_text() + 'SUPPLEMENTARY_DAC_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'
        alternatives = [
            raw.replace('actual=1 expected=1 errno=0', 'actual=0 expected=1 errno=13', 1),
            raw.replace('uid=60001', 'uid=0', 1),
            raw.replace('group_count=1 group=60002', 'group_count=1 group=60003', 1),
            raw.replace('caps=0', 'caps=1', 1),
            raw.replace('nnp=1', 'nnp=0', 1),
            raw.replace('errno=13', 'errno=38', 1),
            raw.replace('SUPPLEMENTARY_DAC_REAP member=1 exited=1 code=0\n', ''),
            raw.replace('reaped=2', 'reaped=1', 1),
            raw.replace('SUPPLEMENTARY_DAC_CHECK name=supplementary_file_read actual=1 expected=1 errno=0\n', ''),
            raw.replace('SUPPLEMENTARY_DAC_CHILD', check.EXPECTED[1]+'\nSUPPLEMENTARY_DAC_CHILD', 1),
            raw.replace('PROBE_EXIT=0', 'PROBE_EXIT=42'),
            raw + 'TRILLIONNIUM_A01_BOOT_OK\n',
            raw.replace('TRILLIONNIUM_A01_BOOT_OK\n', ''),
            'SUPPLEMENTARY_DAC_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n',
            raw + 'kernel panicked at sentinel\n',
        ]
        for i, candidate in enumerate(alternatives):
            with self.subTest(mutation=i): self.assertFalse(check.check(candidate, 33, False)['passed'])
        for code, timeout in [(0, False), (65, False), (33, True), (None, True)]:
            with self.subTest(code=code, timeout=timeout): self.assertFalse(check.check(raw, code, timeout)['passed'])

    def test_actual_old_kernel_negative_stays_rejected(self):
        raw = (HERE/'native-baseline.log').read_bytes()
        self.assertFalse(check.check(raw, 33, False)['passed'])
        self.assertFalse(check.check(raw.replace(b'PROBE_EXIT=42', b'PROBE_EXIT=0'), 33, False)['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
