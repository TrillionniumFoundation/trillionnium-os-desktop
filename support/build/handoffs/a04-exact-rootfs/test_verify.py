import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('a04_input_verifier', Path(__file__).with_name('verify.py'))
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class OutputCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'output'

    def test_plain_roundtrip_has_original_bytes_and_no_incomplete_marker(self):
        VERIFIER.write_outputs(self.output, {'rootfs.tar': b'original payload'})
        self.assertEqual((self.output / 'rootfs.tar').read_bytes(), b'original payload')
        self.assertFalse((self.output / VERIFIER.MARKER).exists())
        self.assertEqual((self.output / 'rootfs.tar').stat().st_mode & 0o777, 0o400)

    def test_existing_directory_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / 'keep'
        sentinel.write_bytes(b'foreign sentinel')
        before = sentinel.stat()
        with self.assertRaises(FileExistsError):
            VERIFIER.write_outputs(self.output, {'rootfs.tar': b'new bytes'})
        self.assertEqual(sentinel.read_bytes(), b'foreign sentinel')
        self.assertEqual(sentinel.stat(), before)
        self.assertEqual(sorted(path.name for path in self.output.iterdir()), ['keep'])

    def test_existing_file_is_preserved(self):
        self.output.write_bytes(b'foreign file')
        before = self.output.stat()
        with self.assertRaises(FileExistsError):
            VERIFIER.write_outputs(self.output, {'rootfs.tar': b'new bytes'})
        self.assertEqual(self.output.read_bytes(), b'foreign file')
        self.assertEqual(self.output.stat(), before)

    def test_symlink_ancestor_is_refused(self):
        outside = self.root / 'outside'
        outside.mkdir()
        link = self.root / 'link'
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            VERIFIER.write_outputs(link / 'output', {'rootfs.tar': b'new bytes'})
        self.assertEqual(list(outside.iterdir()), [])

    def test_midwrite_error_retains_incomplete_marker(self):
        with self.assertRaises(TypeError):
            VERIFIER.write_outputs(self.output, {'rootfs.tar': None})
        self.assertTrue((self.output / VERIFIER.MARKER).is_file())

    def test_same_length_tamper_before_first_stat_is_refused(self):
        original_fsync, fired = os.fsync, []
        wanted = b'original rootfs payload'
        changed = b'corrupt! rootfs payload'
        self.assertEqual(len(wanted), len(changed))

        def tamper_during_fsync(descriptor):
            original_fsync(descriptor)
            path = Path(os.readlink('/proc/self/fd/' + str(descriptor)))
            if path.name == 'rootfs.tar' and not fired:
                fired.append(True)
                path.chmod(0o600)
                with path.open('r+b') as stream:
                    stream.write(changed)
                path.chmod(0o400)

        with mock.patch.object(VERIFIER.os, 'fsync', tamper_during_fsync):
            with self.assertRaisesRegex(ValueError, 'content changed during FD readback'):
                VERIFIER.write_outputs(self.output, {'rootfs.tar': wanted})
        self.assertTrue(fired)
        self.assertTrue((self.output / VERIFIER.MARKER).is_file())
        self.assertEqual((self.output / 'rootfs.tar').read_bytes(), changed)

    def test_directory_replacement_does_not_redirect_writes(self):
        original_open, fired = os.open, []
        parked = self.root / 'parked'

        def swap_before_payload(path, flags, *args, **kwargs):
            if path == 'rootfs.tar' and flags & os.O_CREAT and not fired:
                fired.append(True)
                self.output.rename(parked)
                self.output.mkdir()
                (self.output / 'keep').write_bytes(b'foreign replacement')
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(VERIFIER.os, 'open', swap_before_payload):
            with self.assertRaisesRegex(ValueError, 'directory changed before completion'):
                VERIFIER.write_outputs(self.output, {'rootfs.tar': b'original'})
        self.assertTrue(fired)
        self.assertEqual(sorted(path.name for path in self.output.iterdir()), ['keep'])
        self.assertEqual((self.output / 'keep').read_bytes(), b'foreign replacement')
        self.assertEqual((parked / 'rootfs.tar').read_bytes(), b'original')
        self.assertTrue((parked / VERIFIER.MARKER).is_file())


if __name__ == '__main__':
    unittest.main()
