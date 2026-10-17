"""Real temporary git checkouts; synthetic product files, no AOSP guest."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import subprocess

SRC = Path(__file__).resolve().parents[3]/'support/android/verify_product_source.py'
spec = importlib.util.spec_from_file_location('verify_product_source', SRC)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ProductLockTests(unittest.TestCase):
    def fixture(self, root: Path):
        tree = root/'aosp'
        (tree/'.repo').mkdir(parents=True)
        revisions = {}
        for project in checker.PROJECTS:
            path = tree/project
            path.mkdir(parents=True)
            if project == checker.PROJECTS[0]:
                (path/'vsoc_x86_64/phone').mkdir(parents=True)
                (path/'AndroidProducts.mk').write_text(
                    'PRODUCT_MAKEFILES := \\\n'
                    'aosp_cf_x86_64_phone:$(LOCAL_DIR)/vsoc_x86_64/phone/aosp_cf.mk \\\n'
                    'COMMON_LUNCH_CHOICES := \\\n'
                    'aosp_cf_x86_64_phone-trunk_staging-userdebug\n')
                (path/'vsoc_x86_64/phone/aosp_cf.mk').write_text(
                    'PRODUCT_NAME := aosp_cf_x86_64_phone\nPRODUCT_DEVICE := vsoc_x86_64\n')
            for args in (['init','-q'], ['add','.']):
                subprocess.run(['git','-C',str(path),*args],check=True,capture_output=True)
            subprocess.run(['git','-C',str(path),'-c','user.name=A08 Fixture',
                            '-c','user.email=a08@example.invalid','commit','--allow-empty',
                            '-qm','fixture'], check=True,capture_output=True)
            revisions[project] = checker.git_head(path)
        manifest = root/'manifest-resolved.xml'
        parent = ET.Element('manifest')
        for project, revision in revisions.items():
            ET.SubElement(parent,'project',path=project,revision=revision)
        ET.ElementTree(parent).write(manifest,encoding='unicode')
        return tree,manifest,revisions

    def test_three_real_git_checkouts_match_manifest_only(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,revisions=self.fixture(Path(td))
            got=checker.verify(tree,manifest)
            self.assertEqual(got['status'],'pass_source_checkout_only',got['errors'])
            self.assertTrue(got['product_source_verified'])
            self.assertFalse(got['aosp_build_verified'])
            self.assertFalse(got['android_on_asterinas_verified'])
            self.assertEqual(len(got['projects']),3)
            for project in checker.PROJECTS:
                self.assertEqual(got['projects'][project]['checkout_commit'],revisions[project])

    def test_wrong_resolved_commit_is_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,_=self.fixture(Path(td))
            root=ET.parse(manifest)
            root.getroot().find('project').set('revision','0'*40)
            root.write(manifest,encoding='unicode')
            got=checker.verify(tree,manifest)
            self.assertEqual(got['status'],'blocked')
            self.assertTrue(any('HEAD mismatch' in e for e in got['errors']))

    def test_missing_vmm_revision_is_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,_=self.fixture(Path(td))
            root=ET.parse(manifest)
            entries=root.getroot()
            for p in list(entries):
                if p.get('path')==checker.PROJECTS[2]:entries.remove(p)
            root.write(manifest,encoding='unicode')
            got=checker.verify(tree,manifest)
            self.assertTrue(any('expected unique' in e for e in got['errors']))

    def test_wrong_product_registration_is_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,_=self.fixture(Path(td))
            path=tree/checker.PROJECTS[0]/'AndroidProducts.mk'
            path.write_text('COMMON_LUNCH_CHOICES := other-userdebug\n')
            got=checker.verify(tree,manifest)
            self.assertEqual(got['status'],'blocked')
            self.assertTrue(any('register locked product' in e for e in got['errors']))

    def test_wrong_device_identity_is_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,_=self.fixture(Path(td))
            p=tree/checker.PROJECTS[0]/checker.PRODUCT_PATH
            p.write_text('PRODUCT_NAME := aosp_cf_x86_64_phone\nPRODUCT_DEVICE := arm64\n')
            got=checker.verify(tree,manifest)
            self.assertTrue(any('PRODUCT_DEVICE' in e for e in got['errors']))

    def test_symlink_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            tree,manifest,_=self.fixture(base)
            outside=base/'outside'
            outside.mkdir()
            fake=tree/checker.PROJECTS[2]
            for child in fake.iterdir():
                if child.is_file():child.unlink()
            # temporary git directory with no contents is safe to remove
            import shutil
            shutil.rmtree(fake)
            fake.symlink_to(outside, target_is_directory=True)
            got=checker.verify(tree,manifest)
            self.assertTrue(any('escapes AOSP checkout' in e for e in got['errors']))

    def test_missing_checkout_fails(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,_=self.fixture(Path(td))
            import shutil
            shutil.rmtree(tree/checker.PROJECTS[1])
            got=checker.verify(tree,manifest)
            self.assertTrue(any('directory absent' in e for e in got['errors']))

    def test_cli_fails_closed_and_writes_json(self):
        with tempfile.TemporaryDirectory() as td:
            tree,manifest,_=self.fixture(Path(td))
            out=Path(td)/'out/result.json'
            rc=checker.main(['--aosp-root',str(tree),'--resolved-manifest',str(manifest),'--out',str(out)])
            self.assertEqual(rc,0)
            self.assertTrue(out.is_file())
            self.assertEqual(checker.main(['--aosp-root',str(tree),
                 '--resolved-manifest',str(Path(td)/'missing.xml'),'--out',str(out)]),1)


if __name__=='__main__':unittest.main()
