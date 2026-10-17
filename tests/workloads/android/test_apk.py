#!/usr/bin/env python3
"""Offline fake-transport tests. Not an Android device or emulator run."""
import importlib.util
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

RUNNER = Path(__file__).with_name('run_apk.py')
spec = importlib.util.spec_from_file_location('a08runner', RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def make_apk(path, native=False):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('classes.dex', b'dex\n035\0')
        if native:
            z.writestr('lib/arm64-v8a/libx.so', b'fixture')


class FakeAdb:
    serial = 'cf-test-only'
    def __init__(self, product='aosp_cf_x86_64_phone', install_ok=True, build_id='BP1A.250505.005.D1', reported_serial='cf-test-only', state='device'):
        self.product = product
        self.build_id = build_id
        self.reported_serial = reported_serial
        self.state = state
        self.install_ok = install_ok
        self.calls = []
        self.saved = 'EMPTY'
        self.input = ''
        self.fg = False
        self.last_tap = None

    def cmd(self, *args, timeout=60, allow_failure=False):
        self.calls.append(args)
        if args == ('get-state',): return self.state + '\n'
        if args == ('get-serialno',): return self.reported_serial + '\n'
        if args[:2] == ('shell','getprop'):
            return {
                'ro.product.name':self.product,
                'ro.build.id':self.build_id,
                'ro.build.version.release':'15',
                'ro.product.device':'vsoc_x86_64',
                'ro.product.cpu.abi':'x86_64',
                'ro.hardware':'cutf_cvm',
                'ro.build.version.sdk':'35',
                'ro.build.fingerprint':'fixture/a08/35:fake',
            }[args[2]] + '\n'
        if args == ('shell','getconf','PAGESIZE'): return '4096\n'
        if args == ('shell','uname','-a'): return 'Linux cuttlefish-fixture 6.1 #1 SMP\n'
        if args[0] == 'install':
            return 'Success\n' if self.install_ok else 'Failure [INSTALL_FAILED_INVALID_APK]\n'
        if args == ('shell','pm','path',runner.PACKAGE): return 'package:/data/app/a08/base.apk\n'
        if args == ('shell','pm','clear',runner.PACKAGE):
            self.saved='EMPTY'; return 'Success\n'
        if args[:4] == ('shell','am','start','-W'):
            self.fg=True
            return 'Status: ok\nActivity: ' + runner.ACTIVITY + '\n'
        if args == ('shell','uiautomator','dump','/sdcard/a08-window.xml'):
            return 'UI hierarchy dumped\n'
        if args == ('exec-out','cat','/sdcard/a08-window.xml'):
            if not self.fg: return '<?xml version="1.0"?><hierarchy><node resource-id="launcher"/></hierarchy>'
            return (f'<hierarchy><node resource-id="{runner.PACKAGE}:id/saved_value" '
                    f'text="SAVED:{self.saved}" bounds="[0,0][100,30]"/>'
                    f'<node resource-id="{runner.PACKAGE}:id/input_value" text="" bounds="[0,40][100,80]"/>'
                    f'<node resource-id="{runner.PACKAGE}:id/save_button" text="SAVE" bounds="[0,90][100,130]"/></hierarchy>')
        if args[:3] == ('shell','input','tap'):
            x,y = int(args[3]),int(args[4])
            if y == 110:
                self.saved = self.input
            self.last_tap = (x,y)
            return ''
        if args[:3] == ('shell','input','text'):
            self.input = args[3]; return ''
        if args == ('shell','input','keyevent','KEYCODE_HOME'):
            self.fg=False; return ''
        if args == ('shell','am','force-stop',runner.PACKAGE):
            self.fg=False; return ''
        if args == ('shell','pidof',runner.PACKAGE):
            return '' if not self.fg else '666'
        if args[0]=='logcat': return 'fake logcat: no real Android runtime\n'
        raise AssertionError(f'unexpected command: {args!r}')


class ApkTests(unittest.TestCase):
    def make_preflight(self, directory: Path) -> Path:
        audits = {}
        for name in runner.PREFLIGHT_AUDITS:
            value = (directory / name)
            value.write_text('audit:' + name + '\n')
            audits[name] = hashlib.sha256(value.read_bytes()).hexdigest()
        path = directory / 'cuttlefish-launch-preflight.json'
        path.write_text(json.dumps({
            'kind': runner.PREFLIGHT_KIND,
            'kernel': runner.PREFLIGHT_KERNEL,
            'status': 'preflight_only',
            'guest_boot_verified': False,
            'android_on_asterinas_verified': False,
            'errors': [],
            'audit_reports': audits,
            'launcher_sha256': 'a' * 64,
        }))
        return path

    def test_preflight_bundle_is_hash_bound_and_reference_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = self.make_preflight(root)
            record = runner.load_preflight_evidence(path)
            self.assertEqual(record['status'], 'preflight_only')
            self.assertFalse(record['guest_boot_verified'])
            self.assertFalse(record['android_on_asterinas_verified'])
            (root / 'image-audit.json').write_text('tampered\n')
            with self.assertRaisesRegex(runner.TestFailure, 'changed'):
                runner.load_preflight_evidence(path)

    def test_preflight_bundle_rejects_missing_or_claimed_boot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = self.make_preflight(root)
            path.unlink()
            with self.assertRaisesRegex(runner.TestFailure, 'missing'):
                runner.load_preflight_evidence(path)
            path = self.make_preflight(root)
            data = json.loads(path.read_text())
            data['guest_boot_verified'] = True
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(runner.TestFailure, 'reference-only'):
                runner.load_preflight_evidence(path)

    def test_strict_cli_requires_preflight_before_constructing_adb(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main(['--apk', '/tmp/missing.apk', '--serial', 'cf-test-only',
                             '--out', '/tmp/a08-runner-output'])

    def test_soong_manifest_declares_expected_version_package(self):
        root = ET.parse(Path(__file__).with_name('apk-smoke') / 'app/src/main/AndroidManifest.xml').getroot()
        attr = '{http://schemas.android.com/apk/res/android}'
        self.assertEqual(root.attrib['package'], runner.PACKAGE)
        self.assertEqual(root.attrib[attr + 'versionCode'], '1')
        self.assertEqual(root.attrib[attr + 'versionName'], '1.0')
        uses = root.find('uses-sdk')
        self.assertIsNotNone(uses)
        self.assertEqual(uses.get(attr + 'minSdkVersion'), '28')
        self.assertEqual(uses.get(attr + 'targetSdkVersion'), '35')

    def test_dex_only_metadata_and_sha(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'app.apk'; make_apk(p)
            m = runner.apk_metadata(p)
            self.assertEqual(m['abis'],[])
            self.assertEqual(m['native_libraries'],[])
            self.assertEqual(len(m['sha256']),64)

    def test_native_libraries_are_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'app.apk'; make_apk(p, native=True)
            self.assertEqual(runner.apk_metadata(p)['abis'], ['arm64-v8a'])

    def test_tap_bounds_validation(self):
        self.assertEqual(runner.bounds_center('[1,2][11,12]'),(6,7))
        with self.assertRaises(runner.TestFailure):
            runner.bounds_center('[1,2][1,12]')

    def test_disposable_reference_lifecycle_with_fake_adb(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'A08Smoke.apk'; make_apk(p)
            fake=FakeAdb(); out=Path(td)/'evidence'
            report=runner.run_workload(p, fake, out)
            self.assertEqual(report['status'], 'pass', report.get('error'))
            self.assertFalse(report['native_asterinas_qualified'])
            self.assertEqual(len(report['steps']), 14)
            self.assertEqual(fake.saved,runner.VALUE)
            self.assertEqual(json.loads((out/'result.json').read_text())['status'],'pass')
            self.assertIn(('shell','pm','clear',runner.PACKAGE),fake.calls)

    def test_tcp_transport_selector_can_differ_from_guest_serial(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'A08Smoke.apk'; make_apk(p)
            fake=FakeAdb(reported_serial='cvd-guest-42')
            report=runner.run_workload(p, fake, Path(td)/'report')
            self.assertEqual(report['status'],'pass',report.get('error'))
            self.assertEqual(report['guest']['adb_transport_selector'],fake.serial)
            self.assertEqual(report['guest']['guest_reported_serial'],'cvd-guest-42')

    def test_adb_transport_offline_blocks_install(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'A08Smoke.apk'; make_apk(p)
            fake=FakeAdb(state='offline')
            report=runner.run_workload(p, fake, Path(td)/'report')
            self.assertEqual(report['classification'],'device_identity')
            self.assertFalse(any(c[0]=='install' for c in fake.calls))

    def test_unknown_guest_serial_blocks_install(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'A08Smoke.apk'; make_apk(p)
            fake=FakeAdb(reported_serial='unknown')
            report=runner.run_workload(p, fake, Path(td)/'report')
            self.assertEqual(report['classification'],'device_identity')
            self.assertFalse(any(c[0]=='install' for c in fake.calls))

    def test_wrong_device_is_rejected_before_writes_and_logcat(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'A08Smoke.apk'; make_apk(p)
            fake=FakeAdb(product='real_vendor_phone')
            report=runner.run_workload(p, fake, Path(td)/'report')
            self.assertEqual(report['status'],'fail')
            self.assertEqual(report['classification'],'device_identity')
            self.assertFalse(any(c[0]=='install' for c in fake.calls))
            self.assertFalse(any(c[0]=='logcat' for c in fake.calls))

    def test_wrong_android_build_id_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path+m¹çÛh‘éì¶»§q«^wubprocess
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
