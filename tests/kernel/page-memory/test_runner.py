# SPDX-License-Identifier: MPL-2.0
import gzip
import json
import tempfile
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("page_memory_runner", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class EvidenceTests(unittest.TestCase):
    def test_only_successful_nonce_bound_guest_can_pass(self):
        raw = b'{"case":"real_page","passed":true}\nHEPTA_PAGE_MEMORY nonce=owned exit=0\n'
        self.assertTrue(runner.guest_passed(raw, "owned", 33, False, False))
        for text, nonce, code, timeout, excessive in [
            (raw, "other", 33, False, False), (raw, "owned", 0, False, False),
            (raw, "owned", 33, True, False), (raw, "owned", 33, False, True),
            (raw + raw, "owned", 33, False, False),
            (raw + b'{"passed":false}', "owned", 33, False, False),
            (b'', "owned", 33, False, False),
        ]:
            with self.subTest(text=text, nonce=nonce, code=code):
                self.assertFalse(runner.guest_passed(text, nonce, code, timeout, excessive))

    def test_guest_assembly_preserves_exact_probe_and_smp(self):
        original = b'#!/bin/sh\ntest "$cpu_count" -eq 1\n' + runner.BOOT_MARKER
        fields = [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        archive = gzip.compress(runner.pack([("init", fields, original)]))
        for smp in [2, 4]:
            encoded = runner.inject(archive, b'actual-probe', 'nonce', smp)
            entries = {name: data for name, _, data in runner.unpack(gzip.decompress(encoded))}
            self.assertEqual(entries['bin/page-memory-probe'], b'actual-probe')
            self.assertIn(f'test "$cpu_count" -eq {smp}'.encode(), entries['init'])
            self.assertEqual(entries['init'].count(b'HEPTA_PAGE_MEMORY nonce=nonce exit=$result'), 1)

    def test_missing_cpu_or_duplicate_boot_marker_is_rejected(self):
        fields = [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        for script in [runner.BOOT_MARKER, b'test "$cpu_count" -eq 1\n' + runner.BOOT_MARKER * 2]:
            archive = gzip.compress(runner.pack([("init", fields, script)]))
            with self.assertRaises(Exception):
                runner.inject(archive, b'probe', 'nonce', 2)


    def fixture(self, directory):
        source = {"kind": "development-working-bytes", "head": "reviewed", "files": {"kernel.rs": {"sha256": "source"}}}
        raw = b'{"passed":true}\nHEPTA_PAGE_MEMORY nonce=owned exit=0\n'
        files = {"kernel.elf": b"kernel", "bios.bin": b"bios", "ordinary-initramfs.cpio.gz": b"ordinary",
                 "initramfs.cpio.gz": b"guest", "probe": b"probe", "serial.log": raw}
        for name, content in files.items():
            (directory / name).write_bytes(content)
        for name in ["source-before.json", "source-after.json"]:
            (directory / name).write_text(json.dumps(source))
        receipt = {"schema": "hepta.page-memory-guest.v1", "passed": True, "source_unchanged": True,
                   "nonce": "owned", "qemu_exit": 33, "timed_out": False, "excessive_output": False,
                   "serial_sha256": runner.digest(raw), "initramfs_sha256": runner.digest(b"guest"),
                   "probe_sha256": runner.digest(b"probe"), "qemu_sha256": "qemu",
                   "ordinary_sha256": {name: runner.digest(files[name]) for name in
                       ["kernel.elf", "bios.bin", "ordinary-initramfs.cpio.gz"]}}
        (directory / "result.json").write_text(json.dumps(receipt))
        return source, receipt

    def test_reuse_accepts_only_source_and_artifact_bound_guest(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, receipt = self.fixture(directory)
            artifacts, provenance = runner.ordinary(directory, source, directory)
            self.assertEqual(artifacts['-kernel'], b'kernel')
            self.assertEqual(provenance['qemu_sha256'], 'qemu')
            (directory / 'kernel.elf').write_bytes(b'changed')
            with self.assertRaises(Exception):
                runner.ordinary(directory, source, directory)

    def test_reuse_rejects_failed_guest_even_when_serial_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, receipt = self.fixture(directory)
            raw = (directory / 'serial.log').read_bytes() + b'{"passed":false}'
            (directory / 'serial.log').write_bytes(raw)
            receipt['serial_sha256'] = runner.digest(raw)
            (directory / 'result.json').write_text(json.dumps(receipt))
            with self.assertRaises(Exception):
                runner.ordinary(directory, source, directory)

    def test_reuse_rejects_changed_source_and_failed_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, receipt = self.fixture(directory)
            with self.assertRaises(Exception):
                runner.ordinary(directory, {**source, 'head': 'different'}, directory)
            receipt['passed'] = False
            (directory / 'result.json').write_text(json.dumps(receipt))
            with self.assertRaises(Exception):
                runner.ordinary(directory, source, directory)



if __name__ == '__main__':
    unittest.main(verbosity=2)
