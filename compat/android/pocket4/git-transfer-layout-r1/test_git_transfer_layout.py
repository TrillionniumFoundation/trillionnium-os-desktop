import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from git_transfer_layout import ensure_refs_container


class GitContainerControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'checkout'; self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic Test')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        (self.root / 'source.c').write_text('int actual_fixture;\n')
        self.git('add', 'source.c'); self.git('commit', '-qm', 'fixture')
        self.head = self.git('rev-parse', 'HEAD').stdout.strip()
        branch = self.git('symbolic-ref', 'HEAD').stdout.strip().decode()
        self.git('checkout', '-q', '--detach'); self.git('update-ref', '-d', branch)
        self.uid = (self.root / '.git').stat().st_uid

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, check=True):
        value = subprocess.run(['/usr/bin/git', '-C', str(self.root), *args], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=10, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'GIT_OPTIONAL_LOCKS': '0', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'})
        if check and value.returncode:
            raise RuntimeError(value.stderr.decode())
        return value

    def files(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_actual_git_failure_reproduced_then_empty_container_recovers(self):
        before = self.files(); shutil.rmtree(self.root / '.git/refs')
        bad = self.git('rev-parse', 'HEAD', check=False)
        self.assertEqual(bad.returncode, 128)
        self.assertIn(b'not a git repository', bad.stderr)
        result = ensure_refs_container(self.root, self.uid)
        self.assertTrue(result['created_empty_refs_directory'])
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), self.head)
        self.assertEqual(self.git('status', '--porcelain').stdout, b'')
        self.assertEqual(self.files(), before)
        self.assertEqual(result['regular_files_written'], 0)

    def test_existing_container_is_left_unchanged(self):
        old = (self.root / '.git/refs').stat().st_ino
        result = ensure_refs_container(self.root, self.uid)
        self.assertFalse(result['created_empty_refs_directory'])
        self.assertEqual(result['refs_inode'], old)

    def test_wrong_owner_is_rejected_without_creating_refs(self):
        shutil.rmtree(self.root / '.git/refs')
        with self.assertRaises(ValueError):
            ensure_refs_container(self.root, self.uid + 1)
        self.assertFalse((self.root / '.git/refs').exists())

    def test_boolean_and_float_owner_is_rejected(self):
        for bad in (True, float(self.uid)):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                ensure_refs_container(self.root, bad)

    def test_refs_file_is_not_replaced(self):
        shutil.rmtree(self.root / '.git/refs'); p = self.root / '.git/refs'; p.write_text('preserve')
        with self.assertRaises(OSError):
            ensure_refs_container(self.root, self.uid)
        self.assertEqual(p.read_text(), 'preserve')

    def test_refs_symlink_is_not_followed(self):
        shutil.rmtree(self.root / '.git/refs'); outside = Path(self.tmp.name) / 'outside'; outside.mkdir()
        (self.root / '.git/refs').symlink_to(outside)
        with self.assertRaises(OSError):
            ensure_refs_container(self.root, self.uid)
        self.assertEqual(list(outside.iterdir()), [])

    def test_git_directory_symlink_is_not_followed(self):
        old = self.root / '.git'; destination = Path(self.tmp.name) / 'git-outside'; old.rename(destination)
        old.symlink_to(destination)
        with self.assertRaises(OSError):
            ensure_refs_container(self.root, self.uid)

    def test_missing_objects_is_not_invented(self):
        shutil.rmtree(self.root / '.git/objects')
        with self.assertRaises(FileNotFoundError):
            ensure_refs_container(self.root, self.uid)
        self.assertFalse((self.root / '.git/objects').exists())


if __name__ == '__main__':
    unittest.main()
