"""Execute real AF_UNIX peer credentials and robust-owner-death C ELF probes.

These are ORIGINAL Linux host tests, not Asterinas syscall qualifications.
The separate static/dynamic binaries must report the same fixed Linux facts.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which('gcc'), 'host C compiler unavailable')
class ExtendedLinuxElf(unittest.TestCase):
    def test_pathname_uds_peercred_and_robust_futex_both_linkage_types(self):
        reference = json.loads((HERE/'baselines/linux-debian13-x86_64.json').read_text())
        with tempfile.TemporaryDirectory(prefix='a04-real-linux-extended-') as td:
            root = Path(td)
            for kind, flags in [('dynamic', []), ('static', ['-static'])]:
                binary = root / ('a04-'+kind)
                compile_ = subprocess.run(
                    ['gcc', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                     '-pthread', *flags, str(HERE/'probe.c'), '-o', str(binary)],
                    timeout=60, capture_output=True, text=True, check=False)
                self.assertEqual(compile_.returncode, 0, compile_.stderr)
                for case in ['uds_peercred', 'robust_owner_death']:
                    scratch = root / (kind+'-'+case)
                    scratch.mkdir()
                    run = subprocess.run([str(binary), case, str(scratch)],
                                         timeout=12, capture_output=True, text=True, check=False)
                    if run.returncode != 0 and ('Operation not permitted' in run.stderr or
                                                'Permission denied' in run.stderr):
                        self.skipTest('host AF_UNIX policy denies pathname socket creation')
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(json.loads(run.stdout),
                                     reference['cases'][kind+'.'+case]['facts'])
                    self.assertFalse(any(scratch.iterdir()), 'workload did not release scratch resources')


if __name__ == '__main__':
    unittest.main()
