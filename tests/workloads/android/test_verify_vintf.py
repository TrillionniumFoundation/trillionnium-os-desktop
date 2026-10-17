"""Synthetic VINTF partitions + a real executable fake checkvintf; no AOSP boot."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json

FILE = Path(__file__).resolve().parents[3] / 'support/android/verify_vintf.py'
spec = importlib.util.spec_from_file_location('verify_vintf', FILE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class VintfTests(unittest.TestCase):
    def fixture(self, td: str, *, exit_code=0, verdict='COMPATIBLE'):
        root = Path(td)/'aosp'
        (root/'.repo').mkdir(parents=True)
        p = root/'out/target/product/vsoc_x86_64'
        for name, filename, text in (
            ('system','compatibility_matrix.5.xml','<compatibility-matrix/>'),
            ('vendor','manifest.xml','<manifest/>'),
        ):
            f = p/name/'etc/vintf'/filename
            f.parent.mkdir(parents=True)
            f.write_text(text)
        host = root/'out/host/linux-x86/bin/checkvintf'
        host.parent.mkdir(parents=True)
        host.write_text('#!/bin/sh\nprintf "%s\\n" "' + verdict + '"\nexit ' + str(exit_code) + '\n')
        host.chmod(0o755)
        return root, p, host

    def test_build_tool_invocation_and_real_exit(self):
        with tempfile.TemporaryDirectory() as td:
            args = self.fixture(td)
            result = gate.verify(*args)
            self.assertEqual(result['status'], 'pass_vintf_metadata_only',result['errors'])
            self.assertEqual(result['exit_code'], 0)
            self.assertTrue(result['command'][0].endswith('/checkvintf'))
            self.assertIn('--check-compat', result['command'])
            self.assertEqual(len(result['vintf_files']), 2)
            self.assertFalse(result['kernel_vintf_requirements_verified'])
            self.assertFalse(result['android_on_asterinas_verified'])

    def test_incompatible_is_not_green(self):
        with tempfile.TemporaryDirectory() as td:
            args = self.fixture(td, exit_code=1, verdict='INCOMPATIBLE')
            self.assertNotEqual(gate.verify(*args)['status'], 'pass_vintf_metadata_only')

    def test_zero_exit_with_incompatible_string_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            args = self.fixture(td, verdict='INCOMPATIBLE')
            self.assertTrue(any('INCOMPATIBLE' in e for e in gate.verify(*args)['errors']))

    def test_missing_framework_matrix_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host = self.fixture(td)
            (p/'system/etc/vintf/compatibility_matrix.5.xml').unlink()
            result = gate.verify(root,p,host)
            self.assertNotIn('command', result)
            self.assertIn('framework VINTF compatibility matrix is missing', result['errors'])

    def test_active_release_matrix_set_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root, p, host = self.fixture(td)
            result = gate.verify(root, p, host, required_framework_levels=('202404', '202504'))
            self.assertNotEqual(result['status'], 'pass_vintf_metadata_only')
            self.assertTrue(any('202404' in e for e in result['errors']))
            self.assertTrue(any('202504' in e for e in result['errors']))

    def test_wrong_tool_outside_same_build_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,_ = self.fixture(td)
            tool=Path(td)/'host/checkvintf'; tool.parent.mkdir(); tool.write_text('not same build')
            self.assertTrue(any('same-source' in x for x in gate.verify(root,p,tool)['errors']))

    def test_vendor_vintf_symlink_escape_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host = self.fixture(td)
            outside = Path(td)/'outside.xml'; outside.write_text('<manifest/>')
            target=p/'vendor/etc/vintf/manifest.xml'; target.unlink();target.symlink_to(outside)
            result=gate.verify(root,p,host)
            self.assertTrue(any('escapes PRODUCT_OUT' in e for e in result['errors']))

    def test_soong_vintf_symlink_within_same_out_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host=self.fixture(td)
            src=p/'system/etc/vintf/compatibility_matrix.5.xml'
            dst=root/'out/soong/.intermediates/vintf/compatibility_matrix.5.xml'
            dst.parent.mkdir(parents=True)
            dst.write_bytes(src.read_bytes())
            src.unlink(); src.symlink_to(dst)
            self.assertEqual(gate.verify(root,p,host)['status'], 'pass_vintf_metadata_only')

    def test_apex_info_outside_aosp_out_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host = self.fixture(td)
            outside=Path(td)/'apex-info-list.xml';outside.write_text('<apex/>')
            self.assertTrue(any('APEX info file' in e for e in gate.verify(root,p,host,outside)['errors']))

    def test_apex_info_in_build_out_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host=self.fixture(td)
            apex=root/'out/target/product/vsoc_x86_64/apex-info-list.xml'
            apex.write_text('<apex/>')
            r=gate.verify(root,p,host,apex)
            self.assertEqual(r['status'], 'pass_vintf_metadata_only')
            self.assertEqual(r['apex_info_sha256'],gate.checksum(apex))
            self.assertTrue(r['apex_metadata_included'])
            self.assertIn('--dirmap', r['command'])
            self.assertIn('/apex:'+str(apex.parent.resolve()),r['command'])
            self.assertNotIn('--apex-info-file',r['command'])

    def test_zero_exit_without_compatible_marker_fails(self):
        with tempfile.TemporaryDirectory() as td:
            args = self.fixture(td, verdict='SILENT_SUCCESS')
            r = gate.verify(*args)
            self.assertEqual(r['status'], 'blocked_or_failed')
            self.assertTrue(any('without terminal COMPATIBLE' in e for e in r['errors']))

    def test_apex_filename_must_be_real_apex_info_list(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host = self.fixture(td)
            path = p/'unrelated.xml';path.write_text('<apex/>')
            r = gate.verify(root,p,host,path)
            self.assertNotEqual(r['status'], 'pass_vintf_metadata_only')
            self.assertTrue(any('apex-info-list.xml' in e for e in r['errors']))

    def test_apex_legacy_cli_is_never_forwarded(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host = self.fixture(td)
            apex = p/'apex/apex-info-list.xml';apex.parent.mkdir();apex.write_text('<apex/>')
            r = gate.verify(root,p,host,apex)
            self.assertEqual(r['status'], 'pass_vintf_metadata_only')
            self.assertFalse('--apex-info-file' in r['command'])
            self.assertTrue('/apex:'+str(apex.parent.resolve()) in r['command'])

    def test_cli_refuses_incomplete_product_without_success_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root,p,host=self.fixture(td)
            (p/'vendor/etc/vintf/manifest.xml').unlink()
            evidence=Path(td)/'proof.json'
            rc=gate.main(['--aosp-root',str(root),'--product-out',str(p),
                          '--checkvintf',str(host),'--out',str(evidence)])
            self.assertEqual(rc,1)
            self.assertFalse(json.loads(evidence.read_text())['android_on_asterinas_verified'])


if __name__=='__main__':
    unittest.main()
