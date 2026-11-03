# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import json
import importlib.util
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("socket_credentials_check", HERE/"check.py")
check=importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

def serial(rows,marker):
    return '\n'.join(json.dumps(row) for row in rows)+'\n'+marker+'=0\nTRILLIONNIUM_A01_BOOT_OK\n'

class OracleTests(unittest.TestCase):
    def test_original_linux_shapes_remain_host_only(self):
        for suite,(name,_,count,marker) in check.REFERENCES.items():
            rows=[json.loads(line) for line in (HERE/name).read_text().splitlines()]
            result=check.check(serial(rows,marker),33,False,suite)
            self.assertTrue(result['passed']);self.assertEqual(result['observations'],count)
            self.assertFalse(result['production_qualification'])

    def test_every_missing_duplicate_or_reordered_record(self):
        for suite,(name,_,_,marker) in check.REFERENCES.items():
            rows=[json.loads(line) for line in (HERE/name).read_text().splitlines()]
            for index in range(len(rows)):
                for bad in [rows[:index]+rows[index+1:],rows[:index]+[rows[index]]+rows[index:]]:
                    self.assertFalse(check.check(serial(bad,marker),33,False,suite)['passed'])
            bad=rows.copy();bad[1],bad[2]=bad[2],bad[1]
            self.assertFalse(check.check(serial(bad,marker),33,False,suite)['passed'])

    def test_authority_identity_aliases_types_and_completion(self):
        for suite,(name,_,_,marker) in check.REFERENCES.items():
            rows=[json.loads(line) for line in (HERE/name).read_text().splitlines()]
            raw=serial(rows,marker)
            for index,row in enumerate(rows):
                for field in ['passed','uid','gid','permitted','effective','nnp','pid_matches','reaped_fixtures','incomplete_fixtures','byte','group0','group1']:
                    if field not in row:continue
                    bad=[r.copy() for r in rows]
                    bad[index][field]=0 if type(row[field]) is bool else row[field]+1
                    self.assertFalse(check.check(serial(bad,marker),33,False,suite)['passed'])
            for candidate in [raw.replace(marker+'=0',marker+'=42'),raw+'TRILLIONNIUM_A01_BOOT_OK\n',raw.replace('TRILLIONNIUM_A01_BOOT_OK\n',''),raw+'kernel panicked at test\n',raw.replace('"passed": true','"passed": true, "passed": true',1),marker+'=0\nTRILLIONNIUM_A01_BOOT_OK\n']:
                self.assertFalse(check.check(candidate,33,False,suite)['passed'])
            for code,timeout in [(0,False),(65,False),(33,True),(None,True)]:self.assertFalse(check.check(raw,code,timeout,suite)['passed'])

    def test_actual_identity_group_and_earlier_blocked_negatives(self):
        for suite,base,marker in [('lifetime','native-4aab-baseline-01','SOCKET_CREDENTIAL_PROBE_EXIT'),('lifetime','native-4aab-baseline-02','SOCKET_CREDENTIAL_PROBE_EXIT'),('groups','native-group-4aab-baseline-01','SOCKET_GROUP_PROBE_EXIT')]:
            raw=(HERE/(base+'-serial.log')).read_text()
            self.assertFalse(check.check(raw,33,False,suite)['passed'])
            rewritten=raw.replace(marker+'=42',marker+'=0').replace(marker+'=142',marker+'=0')
            self.assertFalse(check.check(rewritten,33,False,suite)['passed'])

if __name__=='__main__':unittest.main(verbosity=2)
