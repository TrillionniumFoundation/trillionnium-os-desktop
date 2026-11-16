import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import owned_allocation as a


class SingleRootAllocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'owned'
        self.root.mkdir()
        (self.root / 'file').write_bytes(b'x' * 8193)
        os.link(self.root / 'file', self.root / 'hardlink')
        outside = self.base / 'unowned'; outside.mkdir()
        (outside / 'not-counted').write_bytes(b'y' * 65537)
        (self.root / 'external').symlink_to(outside)

    def test_actual_single_owned_root_keeps_hardlink_and_symlink_accounting(self):
        expected = subprocess.run(['/usr/bin/du', '-sx', '--block-size=1', str(self.root)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        observer = a.AllocationObserver((self.root,), self.base / 'one-root', lambda: None, required_roots=1)
        self.addCleanup(observer.close)
        size, ref = observer.observe()
        row = json.loads(Path(ref['path']).read_bytes())
        self.assertEqual(size, int(expected.stdout.split()[0]))
        self.assertEqual(row['required_root_count'], 1)
        self.assertEqual(row['allocation_by_root_bytes'], {str(self.root): size})
        self.assertTrue(row['complete'])
        self.assertFalse(row['partial_output_accepted'])
        self.assertEqual(row['attempts'][0]['returncode'], 0)
        self.assertTrue(row['attempts'][0]['child_reaped'] and row['attempts'][0]['pidfd_closed'])

    def test_default_two_roots_not_widened_and_requested_count_strict(self):
        with self.assertRaises(RuntimeError):
            a.AllocationObserver((self.root,), self.base / 'default', lambda: None)
        for count in (True, 1.0, 0, 3):
            with self.subTest(count=count), self.assertRaises(RuntimeError):
                a.AllocationObserver((self.root,), self.base / str(count), lambda: None, required_roots=count)
        with self.assertRaises(RuntimeError):
            a.AllocationObserver((self.root, self.base / 'unowned'), self.base / 'wrong-count',
                                 lambda: None, required_roots=1)

    def test_single_root_requires_one_complete_exact_nul_record(self):
        operands = ['/proc/self/fd/7']
        valid = b'12\t/proc/self/fd/7\0'
        self.assertEqual(a.decode_complete(valid, operands, required_roots=1), [12])
        with self.assertRaises(RuntimeError):
            a.decode_complete(valid, operands)
        for bad in (valid[:-1], b'', valid + valid, valid.replace(b'/fd/7', b'/fd/8'),
                    valid.replace(b'12\t', b'-1\t')):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                a.decode_complete(bad, operands, required_roots=1)


if __name__ == '__main__':
    unittest.main()
