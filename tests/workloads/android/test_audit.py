#!/usr/bin/env python3
"""Offline tests; none of these synthesize a real AOSP build or boot."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

AUDIT = Path(__file__).resolve().parents[3] / 'support/android/audit.py'
spec = importlib.util.spec_from_file_location('a08audit', AUDIT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def manifest_xml(revisions=None, extra=''):
    revisions = revisions or audit.EXPECTED
    elements = [f'<project path="{path}" revision="{sha}"/>' for path, sha in revisions.items()]
    elements.append(f'<project path="device/google/cuttlefish" revision="{"e"*40}"/>')
    elements.extend(f'<project path="other/{i}" revision="{i:040x}"/>' for i in range(100))
    return '<manifest>' + ''.join(elements) + extra + '</manifest>'


class ManifestTests(unittest.TestCase):
    def test_resolved_manifest_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'resolved.xml'
            path.write_text(manifest_xml())
            report = audit.audit_manifest(path)
            self.assertEqual(report['status'], 'pass')
            self.assertEqual(report['project_count'], len(audit.EXPECTED) + 101)
            self.assertEqual(report['cuttlefish_project_commit'], 'e'*40)

    def test_non_hash_revision_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'resolved.xml'
            path.write_text(manifest_xml({'build/make':'main', **{
                k:v for k,v in audit.EXPECTED.items() if k!='build/make'}}))
            report = audit.audit_manifest(path)
            self.assertEqual(report['status'], 'fail')
            self.assertTrue(any('not a 40-hex' in e for e in report['errors']))

    def test_missing_cuttlefish_project_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'resolved.xml'
            path.write_text(manifest_xml().replace(
                '<project path="device/google/cuttlefish" revision="'+'e'*40+'"/>',''))
            self.assertEqual(audit.audit_manifest(path)['status'], 'fail')

    def test_duplicate_project_path_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'resolved.xml'
            path.write_text(manifest_xml(extra='<project path="build/make" revision="'+'f'*40+'"/>'))
            self.assertTrue(any('duplicate' in e for e in audit.audit_manifest(path)['errors']))

    def test_source_product_requires_expected_identity(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / '.repo').mkdir()
            for proj in audit.EXPECTED:
                (base / proj).mkdir(parents=True, exist_ok=True)
            for rel in audit.REQUIRED_SOURCE.values():
                p = base / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('PRODUCT_NAME := aosp_cf_x86_64_phone\n' if p.name == 'aosp_cf.mk' else 'source fixture')
            with patch.object(audit, 'git_rev', side_effect=lambda path: audit.EXPECTED[path.relative_to(base).as_posix()]):
                self.assertEqual(audit.audit_source(base)['status'], 'pass')
            (base / audit.REQUIRED_SOURCE['cuttlefish_product']).write_text('PRODUCT_NAME := wrong\n')
            with patch.object(audit, 'git_rev', side_effect=lambda path: audit.EXPECTED[path.relative_to(base).as_posix()]):
                self.assertEqual(audit.audit_source(base)['status'], 'fail')

    def test_aidl_and_hidl_versions_remain_distinct(self):
        xml = '''<manifest version="1.0" type="device">
        <hal format="aidl"><name>android.hardware.graphics.composer3</name><version>3</version>
        <fqname>IComposer/default</fqname></hal>
        <hal format="hidl"><name>android.hardware.graphics.mapper</name><version>4.0</version>
        <interface><name>IMapper</name><instance>default</instance></interface></hal></manifest>'''
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'manifest.xml'
            path.write_text(xml)
            got = audit.hal_entries(path)
            self.assertEqual(got[0]['format'], 'aidl')
            self.assertEqual(got[0]['fqname'], 'IComposer/default')
            self.assertEqual(got[1]['format'], 'hidl')
            self.assertEqual(got[1]['version'], ['4.0'])

    def test_empty_product_out_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            result = audit.audit_image(Path(td))
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(any('VINTF' in x for x in result['errors']))
            self.assertTrue(any('ART APEX' in x for x in result['errors']))

    def test_synthetic_partition_inventory_and_vintf(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            for rel in list(audit.REQUIRED_IMAGE.values()) + ['system/apex/com.android.art.apex']:
                p = base / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'fixture: not a real image')
            vendor = base / 'vendor/etc/vintf/manifest.xml'
            vendor.parent.mkdir(parents=True, exist_ok=True)
            vendor.write_text('<manifest type="device"><hal format="aidl"><name>android.hardware.graphics.composer3</name><version>3</version><fqname>IComposer/default</fqname></hal></manifest>')
            matrix = base / 'system/etc/vintf/compatibility_matrix.2025.xml'
            matrix.parent.mkdir(parents=True, exist_ok=True)
            matrix.write_text('<compatibility-matrix type="framework"></compatibility-matrix>')
            report = audit.audit_image(base)
            self.assertEqual(report['status'], 'pass', report['errors'])
            self.assertEqual(report['aidl_hal_instances'][0]['fqname'], 'IComposer/default')
            self.assertEqual(len(report['files']['vintf']), 2)
            matrix.write_text('<unexpected/>')
            self.assertEqual(audit.audit_image(base)['status'], 'fail')

    def test_empty_artifact_not_reported_as_pass(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / 'system.img').touch()
            report = audit.audit_image(base)
            self.assertTrue(any('missing or empty' in e for e in report['errors']))

    def test_cli_missing_source_returns_failure_json(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'report.json'
            rc = audit.main(['audit.py','manifest',str(Path(td)/'nope.xml'),str(out)])
            self.assertEqual(rc, 1)
            self.assertTrue(out.exists())

if __name__ == '__main__':
    unittest.main()
