#!/usr/bin/env python3
"""Synthetic native APK and ADB regression tests; NOT Android execution."""
from __future__ import annotations

import importlib.util
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

import run_native_apk as native
from test_apk import FakeAdb


def fixture(path: Path, isa: int = 62, elf_class: int = 2, native_present=True):
    header = bytearray(64)
    header[:4] = b'\x7fELF'
    header[4] = elf_class
    header[5] = 1
    header[18:20] = isa.to_bytes(2, 'little')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('classes.dex', b'dex\n035\0')
        if native_present:
            z.writestr(native.LIBRARY, bytes(header))


class NativeAdb(FakeAdb):
    def cmd(self, *args, **kwargs):
        if args == ('shell','pm','path',native.PACKAGE):
            self.calls.append(args)
            return 'package:/data/app/a08native/base.apk\n'
        if args == ('shell','pm','clear',native.PACKAGE):
            self.calls.append(args)
            self.saved = 'EMPTY'
            return 'Success\n'
        if args[:4] == ('shell','am','start','-W') and args[-1] == native.ACTIVITY:
            self.calls.append(args)
            self.fg = True
            return 'Status: ok\nActivity: ' + native.ACTIVITY + '\n'
        if args == ('shell','uiautomator','dump','/sdcard/a08-native-window.xml'):
            self.calls.append(args)
            return 'UI hierarchy dumped\n'
        if args == ('exec-out','cat','/sdcard/a08-native-window.xml'):
            self.calls.append(args)
            if not self.fg:
                return '<hierarchy><node resource-id="launcher" /></hierarchy>'
            return (f'<hierarchy><node resource-id="{native.PACKAGE}:id/native_status" '
                    f'text="JNI:x86_64:PID_MATCH" bounds="[0,0][100,30]"/>'
                    f'<node resource-id="{native.PACKAGE}:id/saved_value" '
                    f'text="SAVED:{self.saved}" bounds="[0,30][100,60]"/>'
                    f'<node resource-id="{native.PACKAGE}:id/input_value" '
                    f'text="" bounds="[0,60][100,100]"/>'
                    f'<node resource-id="{native.PACKAGE}:id/save_button" '
                    f'text="SAVE" bounds="[0,110][100,150]"/></hierarchy>')
        if args[:3] == ('shell','input','tap'):
            self.calls.append(args)
            if int(args[4]) == 130:
                self.saved = self.input
            return ''
        if args == ('shell','am','force-stop',native.PACKAGE):
            self.calls.append(args)
            self.fg = False
            return ''
        if args == ('shell','pidof',native.PACKAGE):
            self.calls.append(args)
            return '7' if self.fg else ''
        return super().cmd(*args, **kwargs)


class NativeTests(unittest.TestCase):
    def test_strict_native_cli_requires_preflight(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                native.main(['--apk', '/tmp/missing.apk', '--serial', 'cf-test-only',
                             '--out', '/tmp/a08-native-output'])

    def test_x86_64_elf_not_native_bridge(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path)
            result=native.inspect_native_apk(path)
            self.assertEqual(result['abis'],['x86_64'])
            self.assertEqual(result['native_libraries'],[native.LIBRARY])

    def test_arm64_elf_renamed_as_x86_64_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path,isa=183)
            with self.assertRaises(native.TestFailure):
                native.inspect_native_apk(path)

    def test_32bit_library_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path,elf_class=1)
            with self.assertRaises(native.TestFailure):
                native.inspect_native_apk(path)

    def test_dex_only_cannot_pass_as_jni(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path,native_present=False)
            with self.assertRaises(native.TestFailure):
                native.inspect_native_apk(path)

    def test_native_lifecycle_synthetic_only(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path)
            fake=NativeAdb()
            result=native.run_native(path,fake,Path(td)/'evidence')
            self.assertEqual(result['status'],'pass',result.get('error'))
            self.assertFalse(result['native_asterinas_qualified'])
            self.assertFalse(result['native_bridge_used'])
            self.assertEqual(len(result['steps']),15)
            self.assertEqual(fake.saved,native.VALUE)
            self.assertEqual(sum(c == ('shell','am','force-stop',native.PACKAGE) for c in fake.calls),2)

    def test_native_wrong_device_blocked_before_install(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path)
            fake=NativeAdb(product='actual-phone')
            result=native.run_native(path,fake,Path(td)/'evidence')
            self.assertEqual(result['status'],'fail')
            self.assertEqual(result['classification'],'device_identity')
            self.assertFalse(any(c[0]=='install' for c in fake.calls))

    def test_native_hash_failure_before_adb(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'native.apk'; fixture(path)
            fake=NativeAdb()
            result=native.run_native(path,fake,Path(td)/'evidence',expected_sha256='0'*64)
            self.assertEqual(result['classification'],'host_precondition')
            self.assertFalse(fake.calls)

    def test_native_manifest_product_versions(self):
        project=Path(__file__).with_name('apk-smoke')
        root=ET.parse(project/'native-smoke/app/src/main/AndroidManifest.xml').getroot()
        ns='{http://schemas.android.com/apk/res/android}'
        self.assertEqual(root.get('package'),native.PACKAGE)
        self.assertEqual(root.get(ns+'versionCode'),'1')
        self.assertEqual(root.get(ns+'versionName'),'1.0')
        ids=ET.parse(project/'native-smoke/app/src/main/res/values/ids.xml')
        self.assertEqual({n.get('name') for n in ids.findall('item')},
                         {'native_status','saved_value','input_value','save_button'})
        bp=(project/'Android.bp').read_text()
        self.assertIn('name: "A08NativeSmoke"',bp)
        self.assertIn('jni_libs: ["liba08jni"]',bp)
        self.assertIn('compile_multilib: "64"',bp)


if __name__=='__main__':unittest.main()
