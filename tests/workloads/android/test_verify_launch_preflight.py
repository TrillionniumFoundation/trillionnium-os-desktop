"""Real temp-file, hash and git checks; synthetic images, no Android guest."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[3]/'support/android/verify_launch_preflight.py'
spec=importlib.util.spec_from_file_location('verify_launch_preflight',SRC)
pre=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)


def write(path:Path, content:bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(content)
    return {'path':str(path),'sha256':pre.hash_file(path),'bytes':len(content)}


class PreflightTests(unittest.TestCase):
    def fixture(self,td):
        base=Path(td)
        root=base/'aosp'
        evidence=base/'evidence'
        product=root/'out/target/product/vsoc_x86_64'
        launcher=root/'out/host/linux-x86/bin/launch_cvd'
        (root/'.repo').mkdir(parents=True)
        evidence.mkdir()
        write(launcher,b'FAKE_HOST_LAUNCHER_NO_EXECUTION')
        manifest=evidence/'manifest-resolved.xml'
        manifest.write_text('<manifest/>')
        docs={}
        def audit(name,kind,status,source=None,aosp_root=None):
            doc={'kind':kind,'status':status}
            if source is not None:doc['source']=str(source)
            if aosp_root is not None:doc['aosp_root']=str(aosp_root)
            docs[name]=doc
            return doc
        doc=audit('manifest-audit.json','resolved_manifest','pass',manifest)
        doc['source_sha256']=pre.hash_file(manifest)
        source=write(root/'bionic/libc.so.c',b'FAKE_SOURCE')
        doc=audit('source-audit.json','aosp_source','pass',root)
        doc['files']={'bionic':{'path':'bionic/libc.so.c','sha256':source['sha256']}}
        doc['checkout_commits']={}
        doc=audit('product-source-launch-audit.json','a08_cuttlefish_product_source_contract',
                  'pass_source_checkout_only',aosp_root=root)
        fake_prod=write(root/'device/google/cuttlefish/AndroidProducts.mk',b'FAKE_PRODUCT')
        doc['product_files']={'AndroidProducts.mk':{'sha256':fake_prod['sha256']}}
        doc['projects']={}
        doc=audit('image-audit.json','aosp_product_out','pass',product)
        doc['files']={
           'system_img':{'path':'system.img','sha256':write(product/'system.img',b'SYSTEM_IMAGE')['sha256']},
           'vendor_img':{'path':'vendor.img','sha256':write(product/'vendor.img',b'VENDOR_IMAGE')['sha256']},
           'vintf':[{'path':'vendor/etc/vintf/manifest.xml',
                     'sha256':write(product/'vendor/etc/vintf/manifest.xml',b'<manifest/>')['sha256']}],
        }
        checker = write(root/'out/host/linux-x86/bin/checkvintf',b'FAKE_TOOL_DO_NOT_RUN')
        framework_matrix = write(product/'system/etc/vintf/compatibility_matrix.5.xml',b'<compatibility-matrix/>')
        doc=audit('vintf-compatibility.json','a08_aosp_vintf_metadata_compatibility',
                  'pass_vintf_metadata_only')
        doc['product_out']=str(product)
        doc['tool']=str(root/'out/host/linux-x86/bin/checkvintf')
        doc['tool_sha256']=checker['sha256']
        doc['vintf_files']={'system/etc/vintf/compatibility_matrix.5.xml':{
            'path':'system/etc/vintf/compatibility_matrix.5.xml',
            'sha256':framework_matrix['sha256']}}
        for name,report in docs.items():
            (evidence/name).write_text(json.dumps(report))
        return root,evidence,product,launcher

    def test_valid_synthetic_source_and_images_are_only_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            got=pre.verify(*paths)
            self.assertEqual(got['status'],'preflight_only',got['errors'])
            self.assertFalse(got['guest_boot_verified'])
            self.assertFalse(got['android_on_asterinas_verified'])

    def test_stale_image_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[2]/'system.img').write_bytes(b'REPLACED')
            self.assertTrue(any('image:system_img: bytes changed' in x for x in pre.verify(*paths)['errors']))

    def test_stale_vintf_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[2]/'vendor/etc/vintf/manifest.xml').write_bytes(b'<malicious/>')
            self.assertTrue(any('image:vintf[0]' in x for x in pre.verify(*paths)['errors']))

    def test_stale_bionic_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[0]/'bionic/libc.so.c').write_bytes(b'REPLACED')
            self.assertTrue(any('source:bionic' in x for x in pre.verify(*paths)['errors']))

    def test_stale_cuttlefish_product_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[0]/'device/google/cuttlefish/AndroidProducts.mk').write_text('MODIFIED')
            self.assertTrue(any('product:AndroidProducts.mk' in x for x in pre.verify(*paths)['errors']))

    def test_tampered_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[1]/'manifest-resolved.xml').write_text('<changed/>')
            self.assertTrue(any('manifest changed' in x for x in pre.verify(*paths)['errors']))

    def test_wrong_checkout_report_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            audit=paths[1]/'product-source-launch-audit.json'
            data=json.loads(audit.read_text());data['aosp_root']='/another/source'
            audit.write_text(json.dumps(data))
            self.assertEqual(pre.verify(*paths)['status'],'blocked')

    def test_missing_product_launch_audit_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[1]/'product-source-launch-audit.json').unlink()
            self.assertEqual(pre.verify(*paths)['status'],'blocked')

    def test_escaped_image_path_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            audit=paths[1]/'image-audit.json'
            data=json.loads(audit.read_text())
            outside=Path(td)/'outside.img'
            write(outside,b'OUTSIDE')
            data['files']['system_img']={'path':str(outside),'sha256':pre.hash_file(outside)}
            audit.write_text(json.dumps(data))
            self.assertTrue(any('path escaped audited root' in x for x in pre.verify(*paths)['errors']))

    def test_soong_symlink_inside_same_aosp_out_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            original=paths[2]/'system.img'
            actual=paths[0]/'out/soong/.intermediates/aosp_shared_system_image/system.img'
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(original.read_bytes())
            original.unlink()
            original.symlink_to(actual)
            self.assertEqual(pre.verify(*paths)['status'],'preflight_only')

    def test_image_symlink_outside_aosp_out_is_refused_even_if_hash_matches(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            original=paths[2]/'system.img'
            outside=Path(td)/'external-same-bytes.img'
            outside.write_bytes(original.read_bytes())
            original.unlink()
            original.symlink_to(outside)
            self.assertTrue(any('image:system_img: path escaped' in x
                                for x in pre.verify(*paths)['errors']))

    def test_missing_vintf_compatibility_result_blocks_guest(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[1]/'vintf-compatibility.json').unlink()
            self.assertEqual(pre.verify(*paths)['status'],'blocked')

    def test_failed_checkvintf_result_blocks_guest(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            document=paths[1]/'vintf-compatibility.json'
            data=json.loads(document.read_text())
            data['status']='blocked_or_failed'
            document.write_text(json.dumps(data))
            self.assertEqual(pre.verify(*paths)['status'],'blocked')

    def test_checker_binary_changed_after_pass_blocks_guest(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[0]/'out/host/linux-x86/bin/checkvintf').write_bytes(b'SWAPPED')
            self.assertTrue(any('checkvintf host binary changed' in x
                                for x in pre.verify(*paths)['errors']))

    def test_framework_matrix_changed_after_checkvintf_blocks_guest(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            (paths[2]/'system/etc/vintf/compatibility_matrix.5.xml').write_bytes(b'SWAPPED')
            self.assertTrue(any('vintf:system/etc/vintf/compatibility_matrix.5.xml' in x
                                for x in pre.verify(*paths)['errors']))

    def test_apex_info_dirmap_revalidated_before_launch(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.fixture(td)
            apex = paths[2]/'apex/apex-info-list.xml'
            apex.parent.mkdir(parents=True)
            apex.write_text('<apex-info-list/>')
            report = paths[1]/'vintf-compatibility.json'
            data = json.loads(report.read_text())
            data['apex_info_path'] = str(apex)
            data['apex_info_sha256'] = pre.hash_file(apex)
            data['mapped_partitions'] = {'/apex':str(apex.parent.resolve())}
            data['command'] = ['checkvintf','--check-compat','--dirmap','/apex:'+str(apex.parent.resolve())]
            report.write_text(json.dumps(data))
            self.assertEqual(pre.verify(*paths)['status'], 'preflight_only')
            apex.write_text('<changed/>')
            self.assertTrue(any('APEX info bytes changed' in e
                                for e in pre.verify(*paths)['errors']))

    def test_removed_apex_cli_flag_blocks_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            paths = self.fixture(td)
            apex = paths[2]/'apex/apex-info-list.xml'
            apex.parent.mkdir(parents=True)
            apex.write_text('<apex-info-list/>')
            record=paths[1]/'vintf-compatibility.json'
            data=json.loads(record.read_text())
            data['apex_info_path']=str(apex)
            data['apex_info_sha256']=pre.hash_file(apex)
            data['mapped_partitions']={'/apex':str(apex.parent.resolve())}
            data['command']=['checkvintf','--check-compat','--apex-info-file',str(apex)]
            record.write_text(json.dumps(data))
            self.assertTrue(any('APEX mapping not bound' in x
                                for x in pre.verify(*paths)['errors']))

    def test_cli_writes_blocked_and_preflight_json(self):
        with tempfile.TemporaryDirectory() as td:
            paths=self.fixture(td)
            args=['--aosp-root',str(paths[0]),'--evidence',str(paths[1]),
                  '--product-out',str(paths[2]),'--launcher',str(paths[3]),
                  '--out',str(Path(td)/'report.json')]
            self.assertEqual(pre.main(args),0)
            got=json.loads((Path(td)/'report.json').read_text())
            self.assertEqual(got['status'],'preflight_only')
            (paths[2]/'vendor.img').unlink()
            self.assertEqual(pre.main(args),1)


if __name__=='__main__': unittest.main()
