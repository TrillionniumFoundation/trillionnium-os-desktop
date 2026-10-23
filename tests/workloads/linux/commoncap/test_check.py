# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import json
import unittest
import check

HERE = Path(__file__).resolve().parent


def serial(rows):
    return '\n'.join(json.dumps(row) for row in rows)+'\nCOMMONCAP_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.rows = [json.loads(line) for line in (HERE/'linux-reference.jsonl').read_text().splitlines()]
        self.raw = serial(self.rows)

    def test_actual_linux_shape_is_host_only(self):
        result = check.check(self.raw,33,False)
        self.assertTrue(result['passed'])
        self.assertEqual(result['cases'],16)
        self.assertFalse(result['production_qualification'])

    def test_every_missing_duplicate_or_reordered_record_is_rejected(self):
        for index in range(len(self.rows)):
            for rows in (self.rows[:index]+self.rows[index+1:], self.rows[:index]+[self.rows[index]]+self.rows[index:]):
                self.assertFalse(check.check(serial(rows),33,False)['passed'])
        rows = self.rows.copy(); rows[6],rows[7]=rows[7],rows[6]
        self.assertFalse(check.check(serial(rows),33,False)['passed'])

    def test_authority_errno_values_completion_and_closed_fields(self):
        mutations = []
        for index, field, value in [(1,'observer_uid',0),(1,'effective',1),(1,'permitted',1),
             (1,'nnp',0),(4,'permitted',0),(4,'effective',1),(4,'dumpable',0),(4,'uid',0),
             (6,'errno',38),(6,'rc',0),(6,'passed',1),(6,'denied_expected',False),
             (16,'rc',0),(17,'rc',1),(18,'passed',False),(27,'all_children_reaped',False)]:
            rows = [r.copy() for r in self.rows]; rows[index][field] = value; mutations.append(serial(rows))
        mutations.extend([self.raw.replace('COMMONCAP_PROBE_EXIT=0','COMMONCAP_PROBE_EXIT=42'),
            self.raw+'TRILLIONNIUM_A01_BOOT_OK\n', self.raw.replace('TRILLIONNIUM_A01_BOOT_OK\n',''),
            self.raw+'kernel panicked at test\n', self.raw.replace('"passed": true','"passed": true, "passed": true',1),
            'COMMONCAP_PROBE_EXIT=0\nTRILLIONNIUM_A01_BOOT_OK\n'])
        for index, candidate in enumerate(mutations):
            with self.subTest(index=index): self.assertFalse(check.check(candidate,33,False)['passed'])
        for code, timeout in [(0,False),(65,False),(33,True),(None,True)]:
            self.assertFalse(check.check(self.raw,code,timeout)['passed'])

    def test_actual_old_native_failure_and_marker_only_rewrite_stay_rejected(self):
        raw = (HERE/'native-baseline-serial.log').read_bytes()
        self.assertFalse(check.check(raw,33,False)['passed'])
        self.assertFalse(check.check(raw.replace(b'COMMONCAP_PROBE_EXIT=42',b'COMMONCAP_PROBE_EXIT=0'),33,False)['passed'])


if __name__ == '__main__': unittest.main(verbosity=2)
