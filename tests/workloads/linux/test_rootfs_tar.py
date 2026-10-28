"""A04 rootfs tar regression tests; host-only, never kernel qualification."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('a04_rootfs_capture', ROOT/'support/rootfs/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class RootfsArchive(unittest.TestCase):
    def make_staged(self, base):
        root = base/'staged'
        (root/'etc').mkdir(parents=True)
        (root/'usr/local/bin/a04').mkdir(parents=True)
        for name, data, mode in [('etc/hosts', b'127.0.0.1 localhost\n', 0o444),
                                 ('usr/local/bin/a04/probe', b'ELF-candidate', 0o555)]:
            file = root/name
            file.write_bytes(data)
            file.chmod(mode)
        manifest = base/'manifest.json'
        manifest.write_text(json.dumps({'files': [
            {'path': '/' + p.relative_to(root).as_posix(),
             'sha256': capture.sha(p), 'bytes': p.stat().st_size, 'mode': f'{p.stat().st_mode & 0o777:04o}'}
            for p in sorted(root.rglob('*')) if p.is_file()]}))
        return root, manifest

    def test_real_directory_type_and_roundtrip_extract(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root, manifest = self.make_staged(base)
            self.assertEqual(capture.verify(root, manifest), 2)
            tarpath = base/'rootfs.tar'
            capture.create_tar(root, tarpath)
            original_digest = capture.sha(tarpath)
            with tarfile.open(tarpath) as archive:
                dirs = [member for member in archive if member.isdir()]
                self.assertTrue(dirs)
                self.assertTrue(all(member.type == tarfile.DIRTYPE for member in dirs))
                self.assertTrue(all(member.size == 0 for member in dirs))
            self.assertEqual(capture.extract_verified_tar(tarpath, manifest, base/'extracted'), 2)
            self.assertEqual(capture.verify(base/'extracted', manifest), 2)
            capture.create_tar(root, base/'again.tar')
            self.assertEqual(capture.sha(base/'again.tar'), original_digest)

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            root, manifest=self.make_staged(base)
            (root/'etc/outside').symlink_to('/etc/passwd')
            with self.assertRaisesRegex(ValueError, 'unsafe rootfs'):
                capture.verify(root, manifest)
            with self.assertRaisesRegex(ValueError, 'unsupported staged'):
                capture.create_tar(root, base/'bad.tar')

    def test_duplicate_or_unsafe_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            root, manifest=self.make_staged(base)
            obj=json.loads(manifest.read_text())
            obj['files'].append(dict(obj['files'][0]))
            manifest.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                capture.verify(root, manifest)
            obj['files'].pop()
            obj['files'][0]['path']='/../../etc/passwd'
            manifest.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, 'invalid'):
                capture.verify(root, manifest)

    def test_duplicate_manifest_rejected_before_extraction(self):
        for conflicting in (False, True):
            with self.subTest(conflicting=conflicting), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                root, manifest = self.make_staged(base)
                archive = base/'rootfs.tar'
                capture.create_tar(root, archive)
                obj = json.loads(manifest.read_text())
                duplicate = dict(obj['files'][0])
                if conflicting:
                    duplicate['sha256'] = '0' * 64
                obj['files'].insert(0, duplicate)
                manifest.write_text(json.dumps(obj))
                destination = base/'extracted'
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    capture.extract_verified_tar(archive, manifest, destination)
                self.assertFalse(destination.exists())
                # Reject ambiguous manifests before even opening the archive.
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    capture.extract_verified_tar(base/'absent.tar', manifest, destination)
                self.assertFalse(destination.exists())

    def test_double_slash_manifest_is_rejected_without_hanging(self):
        for name in ('//etc/probe', '//'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                _, manifest = self.make_staged(base)
                obj = json.loads(manifest.read_text())
                obj['files'][0]['path'] = name
                manifest.write_text(json.dumps(obj))
                # Keep a regression to the old infinite parent walk bounded.
                program = (
                    'import runpy, sys\n'
                    'capture = runpy.run_path(sys.argv[1])\n'
                    'try:\n'
                    '    capture["extract_verified_tar"](*sys.argv[2:])\n'
                    'except ValueError as error:\n'
                    '    if "invalid" not in str(error): raise\n'
                    'else:\n'
                    '    raise RuntimeError("ambiguous manifest accepted")\n'
                )
                result = subprocess.run(
                    [sys.executable, '-B', '-c', program, str(ROOT/'support/rootfs/capture.py'),
                     str(base/'absent.tar'), str(manifest), str(base/'extracted')],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((base/'extracted').exists())

    def test_old_directory_as_file_is_reproducibly_broken(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            old=base/'old.tar'
            with tarfile.open(old, 'w', format=tarfile.USTAR_FORMAT) as tar:
                info=tarfile.TarInfo('etc/')  # defaults to REGTYPE, not DIRTYPE
                self.assertEqual(info.type, tarfile.REGTYPE)
                tar.addfile(info)
                info=tarfile.TarInfo('etc/hosts')
                tar.addfile(info)
            with tarfile.open(old) as tar:
                with self.assertRaises((NotADirectoryError, IsADirectoryError)):
                    tar.extractall(base/'old-extract', filter='data')
            _, manifest = self.make_staged(base)
            with self.assertRaisesRegex(ValueError, 'link or special|directory|unsafe or duplicate'):
                capture.extract_verified_tar(old, manifest, base/'old-rejected')


if __name__ == '__main__':
    unittest.main()
