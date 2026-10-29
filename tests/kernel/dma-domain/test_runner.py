# SPDX-License-Identifier: MPL-2.0
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('dma_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class EvidenceTests(unittest.TestCase):
    def fixture(self, directory, iommu=True, smp=2, snoop=True):
        marker = ('HEPTA_DMA_DOMAINS_NO_IOMMU_REJECTED' if not iommu else
                  'HEPTA_DMA_DOMAINS_UNSUPPORTED_REJECTED' if not snoop else
                  'HEPTA_DMA_DOMAINS_EDU_PASS cross-read cross-write revoke rebind queue-wrap')
        raw = f'test ostd::{runner.TEST} ...DEBUG: interleaved hardware log\n{marker}\ntest result: ok. 1 passed; 0 failed; 225 filtered out.\n'.encode()
        for name, data in [('kernel.elf', b'actual kernel'), ('bios.bin', b'bios'), ('serial.log', raw)]:
            (directory/name).write_bytes(data)
        (directory/'qemu.bin').write_bytes(b'actual qemu')
        record = dict(schema='hepta.dma-domain-guest.v1', iommu=iommu, smp=smp, snoop_control=snoop,
                      argv=runner.command(str(directory/'qemu.bin'), directory, runner.APPEND, smp, iommu, snoop),
                      qemu_sha256=runner.digest(b'actual qemu'),
                      exit=33, timed_out=False, artifacts_unchanged=True)
        for name, key in [('kernel.elf','kernel_sha256'),('bios.bin','bios_sha256'),('serial.log','serial_sha256')]:
            record[key] = runner.digest((directory/name).read_bytes())
        self.save(directory, record)
        return record

    def save(self, directory, receipt):
        (directory/'qemu.json').write_text(json.dumps(receipt))

    def test_all_three_profiles_require_their_own_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for iommu, snoop in [(True,True),(False,True),(True,False)]:
                self.fixture(directory, iommu, 4, snoop)
                self.assertTrue(runner.verdict(directory,iommu,4,snoop)['passed'])
                self.assertFalse(runner.verdict(directory,not iommu,4,snoop)['passed'])

    def test_exit_and_timeout_cannot_be_hidden_by_success_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for field, value in [('exit',0),('exit',1),('timed_out',True),('artifacts_unchanged',False)]:
                receipt=self.fixture(directory);receipt[field]=value;self.save(directory,receipt)
                self.assertFalse(runner.verdict(directory,True,2)['passed'])

    def test_copied_success_receipt_cannot_hide_modified_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for name in ['kernel.elf','bios.bin','serial.log','qemu.bin']:
                self.fixture(directory);(directory/name).write_bytes(b'changed')
                self.assertFalse(runner.verdict(directory,True,2)['passed'])

    def test_negative_logs_fail_even_with_updated_serial_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for suffix in [b'panic', b'FAILED', b'[skipped: unavailable]', b'HEPTA_DMA_DOMAINS_NO_IOMMU_REJECTED']:
                receipt=self.fixture(directory)
                raw=(directory/'serial.log').read_bytes()+suffix
                (directory/'serial.log').write_bytes(raw)
                receipt['serial_sha256']=runner.digest(raw);self.save(directory,receipt)
                self.assertFalse(runner.verdict(directory,True,2)['passed'])

    def test_changed_device_arguments_and_cpu_count_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            receipt=self.fixture(directory)
            receipt['argv'] += ['-drive','file=host-data']
            self.save(directory,receipt)
            self.assertFalse(runner.verdict(directory,True,2)['passed'])
            self.fixture(directory)
            self.assertFalse(runner.verdict(directory,True,4)['passed'])

    def test_marker_without_the_named_kernel_test_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);receipt=self.fixture(directory)
            raw=(directory/'serial.log').read_bytes().replace(runner.TEST.encode(), b'other_test')
            (directory/'serial.log').write_bytes(raw)
            receipt['serial_sha256']=runner.digest(raw);self.save(directory,receipt)
            self.assertFalse(runner.verdict(directory,True,2)['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
