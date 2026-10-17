"""Pinned QEMU rootfs.tar handoff tests. All host-only: no guest execution."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('a04_qemu_tar_under_test', HERE/'replay_qemu.py')
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


class QemuPinnedTarInput(unittest.TestCase):
    def fixture(self, base):
        root = base/'source'
        (root/'usr/local/bin/a04').mkdir(parents=True)
        (root/'etc').mkdir()
        for name, data, mode in (
            ('etc/hosts', b'127.0.0.1 localhost\n', 0o444),
            ('usr/local/bin/a04/test', b'synthetic; not an ELF', 0o555),
        ):
            file = root/name
            file.write_bytes(data)
            file.chmod(mode)
        records = []
        for file in sorted(p for p in root.rglob('*') if p.is_file()):
            records.append({'path': '/' + file.relative_to(root).as_posix(),
                            'sha256': REPLAY.capture.sha(file),
                            'bytes': file.stat().st_size,
                            'mode': f'{file.stat().st_mode & 0o777:04o}'})
        manifest = base/'manifest.json'
        manifest.write_text(json.dumps({'files': records}))
        archive = base/'rootfs.tar'
        REPLAY.capture.create_tar(root, archive)
        args = SimpleNamespace(rootfs=None, rootfs_tar=archive,
                               rootfs_manifest=manifest)
        return args

    def pins(self, args):
        return (patch.object(REPLAY, 'A04_ROOTFS_TAR_SHA256', REPLAY.guest.sha_file(args.rootfs_tar)),
                patch.object(REPLAY, 'A04_ROOTFS_MANIFEST_SHA256', REPLAY.guest.sha_file(args.rootfs_manifest)),
                patch.object(REPLAY, 'A04_ROOTFS_FILE_COUNT', 2))

    def test_archive_verified_and_staged_only_in_new_evidence_directory(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            args = self.fixture(base)
            evidence = base/'evidence'
            evidence.mkdir(mode=0o700)
            with self.pins(args)[0], self.pins(args)[1], self.pins(args)[2]:
                root, facts = REPLAY.stage_rootfs(args, evidence)
            self.assertEqual(root, evidence/'staged-rootfs')
            self.assertEqual(facts['rootfs_extracted_files'], 2)
            self.assertEqual(facts['rootfs_input'], 'pinned_tar_verified_extraction')
            self.assertEqual(REPLAY.capture.verify(root, args.rootfs_manifest), 2)

    def test_self_consistent_repacked_tar_rejected_without_pin_change(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            args = self.fixture(base)
            evidence = base/'evidence'
            evidence.mkdir()
            # The local archive matches itself, but not the REVIEWED sha256.
            with self.assertRaisesRegex(ValueError, 'rootfs tar SHA-256 mismatch'):
                REPLAY.stage_rootfs(args, evidence)
            self.assertFalse((evidence/'staged-rootfs').exists())

    def test_changed_manifest_cannot_rewrite_reviewed_rootfs_contract(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            args = self.fixture(base)
            evidence = base/'evidence'
            evidence.mkdir()
            with patch.object(REPLAY, 'A04_ROOTFS_TAR_SHA256', REPLAY.guest.sha_file(args.rootfs_tar)):
                with self.assertRaisesRegex(ValueError, 'rootfs manifest SHA-256 mismatch'):
                    REPLAY.stage_rootfs(args, evidence)
            self.assertFalse((evidence/'staged-rootfs').exists())

    def test_reject_two_sources_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            args = self.fixture(base)
            args.rootfs = base/'source'
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                REPLAY.stage_rootfs(args, base)
            args.rootfs = None
            (base/'staged-rootfs').mkdir()
            with self.pins(args)[0], self.pins(args)[1], self.pins(args)[2]:
                with self.assertRaisesRegex(ValueError, 'destination already exists'):
                    REPLAY.stage_rootfs(args, base)


if __name__ == '__main__':
    unittest.main()
