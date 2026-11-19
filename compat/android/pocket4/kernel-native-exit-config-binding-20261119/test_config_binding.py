"""Exact full-r3 snapshots and negative controls; no binding job, lock or VM."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


subject = module('fixed_config_binding', ROOT / 'candidate/inputs/bind_full.py')
previous = module('original_failed_config_binding', ROOT / 'original/bind_full.py')
SYMBOL = subject.CONFIG_HEX_SYMBOL
CONFIG = (ROOT / 'fixtures/full.config').read_text()
HEADER = (ROOT / 'fixtures/autoconf.h').read_text()


class SnapshotReads:
    """Test-only pinned bytes adapter; never claims actual host F9 custody."""
    def __init__(self):
        self.pins = {}
        self.bodies = {}
        self.source_rows = {}
        for relative, (size, digest) in subject.CONFIG_SEMANTIC_SOURCES.items():
            body = (ROOT / 'fixtures' / relative).read_bytes()
            assert len(body) == size and hashlib.sha256(body).hexdigest() == digest
            path = str(subject.SOURCE / relative)
            self.source_rows[relative] = {'kind': 'file', 'bytes': size,
                                          'sha256': digest, 'identity': []}
            self.bodies[path] = body
        self.config_pin = self.add(subject.OUT / '.config', CONFIG.encode())
        self.header_pin = self.add(subject.OUT / 'include/generated/autoconf.h', HEADER.encode())
        self.full = {'config': self.config_pin, 'whole_source_before': {'test_only': True}}

    def add(self, path, body):
        self.bodies[str(path)] = body
        return {'path': str(path), 'bytes': len(body),
                'sha256': hashlib.sha256(body).hexdigest(), 'identity': []}

    def document(self, row):
        assert row == {'test_only': True}
        return copy.deepcopy(self.source_rows)

    def read(self, pin, capture=False):
        body = self.bodies[pin['path']]
        subject.need(len(body) == pin['bytes'] and hashlib.sha256(body).hexdigest() == pin['sha256'],
                     'test snapshot complete bytes differ')
        self.pins[pin['path']] = pin
        return body if capture else None

    def current(self, path):
        assert str(path) == self.header_pin['path']
        return self.header_pin, self.read(self.header_pin, capture=True)


class ConfigControls(unittest.TestCase):
    def compare(self, config, header):
        return subject.compare_generated_configuration(config, header, {SYMBOL})

    def test_actual_complete_snapshots_have_exact_pins(self):
        for row in json.loads((ROOT / 'ORIGINAL-INPUTS.json').read_text()):
            body = (ROOT / row['dest']).read_bytes()
            self.assertEqual((len(body), hashlib.sha256(body).hexdigest()),
                             (row['bytes'], row['sha256']))

    def test_original_failure_and_complete_10145_macro_successor(self):
        reads = SnapshotReads()
        with self.assertRaisesRegex(previous.BindingError, 'complete generated autoconf'):
            previous.generated_configuration(reads, reads.full)
        result = subject.generated_configuration(reads, reads.full)
        self.assertEqual(result['compared_CONFIG_macro_count'], 10145)
        self.assertEqual(result['HEX_spelling_normalizations'],
                         [{'symbol': SYMBOL, 'config_value': '0', 'generated_value': '0x0'}])
        self.assertEqual(result['pin'], reads.header_pin)
        self.assertEqual(result['actual_full_config'], reads.config_pin)
        self.assertEqual({p['path'] for p in result['Kconfig_semantic_sources']},
                         {str(subject.SOURCE / name) for name in subject.CONFIG_SEMANTIC_SOURCES})

    def test_hex_zero_and_existing_prefix_spelling(self):
        for raw, emitted in [('0', '0x0'), ('0x0', '0x0'), ('0X0', '0X0'), ('0A', '0x0A')]:
            with self.subTest(raw=raw):
                self.compare(f'{SYMBOL}={raw}\n', f'#define {SYMBOL} {emitted}\n')

    def test_hex_value_changes_and_decimal_interpretation_rejected(self):
        for raw, emitted in [('0', '0x1'), ('0x1', '0x0'), ('10', '16'), ('10', '10')]:
            with self.subTest(raw=raw, emitted=emitted), self.assertRaises(subject.BindingError):
                self.compare(f'{SYMBOL}={raw}\n', f'#define {SYMBOL} {emitted}\n')
        self.compare(f'{SYMBOL}=10\n', f'#define {SYMBOL} 0x10\n')

    def test_quoted_or_invalid_hex_value_rejected(self):
        for value in ['"0"', '"0x0"', '-0', '0x', '0xg', 'y', 'm']:
            with self.subTest(value=value), self.assertRaises(subject.BindingError):
                self.compare(f'{SYMBOL}={value}\n', f'#define {SYMBOL} 0x0\n')

    def test_string_zero_keeps_exact_string_semantics(self):
        self.compare('CONFIG_LABEL="0"\n', '#define CONFIG_LABEL "0"\n')
        for emitted in ['0', '0x0', '"0x0"']:
            with self.subTest(emitted=emitted), self.assertRaises(subject.BindingError):
                self.compare('CONFIG_LABEL="0"\n', f'#define CONFIG_LABEL {emitted}\n')

    def test_other_numeric_symbols_are_not_normalized(self):
        with self.assertRaises(subject.BindingError):
            self.compare('CONFIG_UNPROVEN=0\n', '#define CONFIG_UNPROVEN 0x0\n')
        with self.assertRaisesRegex(subject.BindingError, 'only the source-proven'):
            subject.compare_generated_configuration('CONFIG_UNPROVEN=0\n',
                '#define CONFIG_UNPROVEN 0x0\n', {SYMBOL, 'CONFIG_UNPROVEN'})

    def test_missing_or_extra_actual_macro_rejected(self):
        removed = HEADER.replace(f'#define {SYMBOL} 0x0\n', '')
        self.assertNotEqual(removed, HEADER)
        for header in [removed, HEADER + '#define CONFIG_INVENTED 1\n']:
            with self.assertRaisesRegex(subject.BindingError, 'symbol set'):
                self.compare(CONFIG, header)

    def test_duplicate_symbols_rejected(self):
        for config, header in [(CONFIG + f'{SYMBOL}=0\n', HEADER),
                               (CONFIG, HEADER + f'#define {SYMBOL} 0x0\n')]:
            with self.assertRaisesRegex(subject.BindingError, 'duplicate'):
                self.compare(config, header)

    def test_boolean_and_module_rules_preserved(self):
        self.compare('CONFIG_ENABLED=y\nCONFIG_DRIVER=m\nCONFIG_OFF=n\n',
                     '#define CONFIG_ENABLED 1\n#define CONFIG_DRIVER_MODULE 1\n')
        with self.assertRaises(subject.BindingError):
            self.compare('CONFIG_DRIVER=m\n', '#define CONFIG_DRIVER 1\n')

    def test_source_type_and_writer_require_the_original_full_source_pins(self):
        for name in subject.CONFIG_SEMANTIC_SOURCES:
            reads = SnapshotReads()
            reads.source_rows[name]['sha256'] = '0' * 64
            with self.subTest(name=name), self.assertRaisesRegex(subject.BindingError, 'semantic source'):
                subject.verified_hex_symbols(reads, reads.full)
        reads = SnapshotReads()
        path = str(subject.SOURCE / 'drivers/mtd/nand/raw/Kconfig')
        reads.bodies[path] = reads.bodies[path].replace(b'hex "Physical address of DiskOnChip"',
                                                      b'int "Physical address of DiskOnChip"')
        with self.assertRaisesRegex(subject.BindingError, 'complete bytes differ'):
            subject.verified_hex_symbols(reads, reads.full)

    def test_binder_cli_remains_unconditionally_held(self):
        with self.assertRaisesRegex(subject.BindingError, subject.HELD):
            subject.main()


if __name__ == '__main__':
    unittest.main(verbosity=2)
