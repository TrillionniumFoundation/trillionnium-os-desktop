"""Pure kernel-record fixtures only; never opens /dev/kmsg or runs main()."""
import base64
import errno
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('collect-template.py'))
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
C.CFG = {'window_start_us': 100, 'window_end_us': 200, 'owned_pids': [1204580]}


def record(seq, ts, message=b'init: fixture\n', caller=None):
    header = f'6,{seq},{ts},-'.encode('ascii')
    if caller is not None:
        header += f',caller=T{caller}'.encode('ascii')
    return header + b';' + message


def run_scan(parts, report=None):
    report = C.empty_scan() if report is None else report
    with mock.patch.object(C.os, 'read', side_effect=parts), mock.patch.object(C.time, 'monotonic', return_value=1.0):
        C.scan(99999, report)
    return report


class Controls(unittest.TestCase):
    def test_exact_window_does_not_export_outside_messages(self):
        end = BlockingIOError(errno.EAGAIN, 'fixture drained')
        result = run_scan([record(1, 99), record(2, 100), record(3, 200), record(4, 201), end])
        self.assertEqual([x['timestamp_us'] for x in result['selected_records']], [100, 200])
        self.assertTrue(result['window_evidence_complete'])

    def test_only_owned_caller_or_named_init_candidate(self):
        self.assertTrue(C.selected(C.parse_record(record(1, 150, b'other diagnostic', 1204580))))
        self.assertFalse(C.selected(C.parse_record(record(2, 150, b'other diagnostic', 7))))
        self.assertFalse(C.selected(C.parse_record(record(3, 201, b'init: outside', 1204580))))
        self.assertTrue(C.selected(C.parse_record(record(4, 150, b'reboot: candidate', 7))))

    def test_malformed_header_and_duplicate_caller_rejected(self):
        for raw in (b'6,1,150,-,caller=T1,caller=T2;x', b'6,1,no,-;x', b'6,1,150,-x', b'192,1,150,-;x'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                C.parse_record(raw)

    def test_partial_selected_evidence_survives_later_read_error(self):
        report = C.empty_scan()
        with self.assertRaises(OSError):
            run_scan([record(1, 100), OSError(errno.EIO, 'fixture read fault')], report)
        self.assertEqual(len(report['selected_records']), 1)
        self.assertFalse(report['window_evidence_complete'])
        self.assertFalse(report['ring_end_observed'])

    def test_overrun_and_sequence_loss_cannot_be_complete(self):
        for parts in ([record(1, 99), OSError(errno.EPIPE, 'fixture overrun'), record(2, 201)],
                      [record(1, 99), record(3, 201)]):
            result = run_scan(parts + [BlockingIOError(errno.EAGAIN, 'fixture drained')])
            self.assertTrue(result['window_timestamp_bounds_covered'])
            self.assertFalse(result['window_evidence_complete'])

    def test_missing_old_window_cannot_be_complete(self):
        result = run_scan([record(1, 150), record(2, 201), BlockingIOError(errno.EAGAIN, 'fixture drained')])
        self.assertTrue(result['ring_end_observed'])
        self.assertFalse(result['window_timestamp_bounds_covered'])
        self.assertFalse(result['window_evidence_complete'])

    def test_raw_non_utf8_selected_record_is_preserved_exactly(self):
        raw = record(2, 150, b'init: raw\xff\n')
        result = run_scan([record(1, 99), raw, record(3, 201), BlockingIOError(errno.EAGAIN, 'fixture drained')])
        actual = result['selected_records'][0]
        self.assertFalse(actual['message_utf8_exact'])
        self.assertEqual(base64.b64decode(actual['raw_base64'], validate=True), raw)
        self.assertEqual(actual['raw_sha256'], C.sha(raw))

    def test_selected_limit_keeps_prior_record_and_never_completes(self):
        report = C.empty_scan()
        with mock.patch.object(C, 'MAX_SELECTED_RECORDS', 1), self.assertRaises(RuntimeError):
            run_scan([record(1, 100), record(2, 150)], report)
        self.assertEqual(len(report['selected_records']), 1)
        self.assertFalse(report['window_evidence_complete'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
