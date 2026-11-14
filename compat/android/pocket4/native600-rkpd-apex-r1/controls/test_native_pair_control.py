import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('native_pair_control', Path(__file__).with_name('native_pair_control.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def contract():
    return dict(schema=1, abi=1, protocol='DLOOMGE1-PROCMET2', host_abi='x86_64',
                **{key: 'a' * 64 for key in p.PAIR_KEYS if key.endswith('_sha256')})


def records():
    common = dict(schema=1, targets=p.TARGETS[:], dependency_mode='Strict',
                  private_AppZygote_role_authorized=False, installation_performed=False, runtime_qualified=False)
    attempt = dict(common, state='CLAIMED_BEFORE_SOURCE_PROJECTION',
                   scope='ordinary-app-complete-engine-art-pair', source_lock_sha256=p.LOCK_SHA,
                   engine_compiled_macro=1, ART_compiled_macro=1)
    inputs = dict(common, scope=attempt['scope'], source_lock_sha256=p.LOCK_SHA,
                  selected_targets=p.TARGETS[:], frozen_engine_files_sha256=p.ENGINE_FILES_SHA,
                  required_actual_compile_sources=p.REQUIRED_COMPILE_SOURCES[:],
                  effective_engine_files={'file-%04d' % i: 'b' * 64 for i in range(926)},
                  frozen_ART_inputs=[{'path': name} for name in p.ART_PATHS],
                  full_translation_unit_qualification_verified=False,
                  signature_and_payload_verification_complete=False)
    command = dict(common, state='NORMAL_BUILD_SUCCEEDED_ACTUAL_PAIR_RECORDED',
                   source_projection_restored=True, compiled_engine_ART_pair=contract(),
                   full_translation_unit_qualification_verified=False,
                   signature_and_payload_verification_complete=False)
    return attempt, inputs, command


def elf(marker=True):
    raw = bytearray(64); raw[:6] = b'\x7fELF\x02\x01'; raw[16:20] = b'\x03\x00\x3e\x00'
    if marker:
        raw.extend(b'DROIDLOOM_NATIVE_GENERATION=1;ROLE=ENGINE;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;\0')
    return bytes(raw)


class PairControls(unittest.TestCase):
    def test_exact_normal_completion_keeps_qualification_pending(self):
        self.assertEqual(p.validate_records(*records()), contract())

    def test_actual_prior600_lock_cannot_qualify_new_rkpd_pair(self):
        self.assertEqual(p.LOCK_SHA, '09a020b99c5f9f1876c69450d01ac99907cd6dda97cb4f69601f70151ea43d2b')
        values = records()
        values[0]['source_lock_sha256'] = values[1]['source_lock_sha256'] = '600dc00660af69b4b8eeb497fac8f2a83f0d8b24ad3d02c2774a4df96f5ec8cf'
        with self.assertRaises(RuntimeError):
            p.validate_records(*values)

    def test_schema_and_abi_reject_boolean_or_float(self):
        for key in ('schema', 'abi'):
            for bad in (True, 1.0):
                value = contract(); value[key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(RuntimeError):
                    p.pair_contract_shape(value)

    def test_compiled_macros_reject_boolean_and_disabled_values(self):
        for key in ('engine_compiled_macro', 'ART_compiled_macro'):
            for bad in (True, 0, 1.0, '1'):
                values = records(); values[0][key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(RuntimeError):
                    p.validate_records(*values)

    def test_all_three_normal_schemas_are_exact_integer(self):
        for index in range(3):
            values = records(); values[index]['schema'] = True
            with self.subTest(index=index), self.assertRaises(RuntimeError):
                p.validate_records(*values)

    def test_targets_strict_mode_and_no_runtime_scope_cannot_change(self):
        mutations = {'targets': ['libberberis_arm64'], 'dependency_mode': 'AllowMissing',
                     'private_AppZygote_role_authorized': True, 'installation_performed': True,
                     'runtime_qualified': True}
        for index in range(3):
            for key, bad in mutations.items():
                values = records(); values[index][key] = bad
                with self.subTest(index=index, key=key), self.assertRaises(RuntimeError):
                    p.validate_records(*values)

    def test_old_source_lock_and_incomplete_engine_or_art_fail(self):
        for change in ('lock', 'engine', 'art', 'seven_sources'):
            values = records()
            if change == 'lock': values[1]['source_lock_sha256'] = '0' * 64
            if change == 'engine': values[1]['effective_engine_files'].pop('file-0000')
            if change == 'art': values[1]['frozen_ART_inputs'].pop()
            if change == 'seven_sources': values[1]['required_actual_compile_sources'].pop()
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                p.validate_records(*values)

    def test_normal_compile_cannot_self_grant_signature_or_tu_qualification(self):
        for index in (1, 2):
            for key in ('signature_and_payload_verification_complete', 'full_translation_unit_qualification_verified'):
                values = records(); values[index][key] = True
                with self.subTest(index=index, key=key), self.assertRaises(RuntimeError):
                    p.validate_records(*values)

    def test_unrestored_source_cannot_complete(self):
        values = records(); values[2]['source_projection_restored'] = False
        with self.assertRaises(RuntimeError): p.validate_records(*values)

    def test_pair_hashes_and_host_abi_are_exact(self):
        for key, bad in (('engine_sha256', 'a' * 63), ('art_apex_sha256', 'G' * 64),
                         ('libart_sha256', 1), ('host_abi', 'aarch64'), ('protocol', 'disabled')):
            value = contract(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(RuntimeError): p.pair_contract_shape(value)

    def test_enabled_marker_requires_actual_x86_64_shared_elf(self):
        self.assertEqual(p.pair_engine_marker(elf()), [64])
        for raw in (elf(False), elf().replace(b'\x03\x00\x3e\x00', b'\x02\x00\x3e\x00', 1),
                    elf().replace(b'\x03\x00\x3e\x00', b'\x03\x00\xb7\x00', 1)):
            with self.assertRaises(RuntimeError): p.pair_engine_marker(raw)

    def test_any_disabled_or_foreign_secondary_marker_fails(self):
        for extra in (b'DROIDLOOM_NATIVE_GENERATION=0;\0',
                      b'DROIDLOOM_NATIVE_GENERATION=1;ROLE=ART;ABI=1;PROTOCOL=DLOOMGE1-PROCMET2;\0'):
            with self.assertRaises(RuntimeError): p.pair_engine_marker(elf() + extra)


if __name__ == '__main__':
    unittest.main()
