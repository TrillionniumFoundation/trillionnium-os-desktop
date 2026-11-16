import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio_continuation_control as control


def pin(path='synthetic.apex'):
    return {'path': path, 'bytes': 32, 'sha256': 'a' * 64}


def completed_resources():
    p = control.MEMORY8G_RESERVE5G
    return {'resource_profile': p.record(),
            'budget': {'memory.max': str(p.build_memory_max_bytes), 'memory.swap.max': '0',
                       'cpu.max': '200000 100000', 'affinity': [0, 1]},
            'admission': {'hard_cap_bytes': p.build_memory_max_bytes,
                          'minimum_bytes': p.fresh_memavailable_minimum_bytes,
                          'MemAvailable_bytes': p.fresh_memavailable_minimum_bytes},
            'resources_after': {'memory.swap.current': '0', 'memory.peak': str(6 * 1024**3)},
            'resource_events_delta': {'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0},
            'owned_resource_gate_passed': True, 'owned_retirement_complete': True,
            'input_after_qualified': True, 'source_projection_restored': True}


def raw_exit_fixture():
    generation = {'job_id': 'synthetic-process', 'launch_nonce': 'synthetic-generation'}
    request = dict(generation)
    started = {**generation, 'at_unix_ms': 1000, 'invocation_id': 'synthetic-invocation',
               'supervisor_identity': {'kind': 'proc_start_ticks', 'value': 'synthetic-boot:10'},
               'supervisor_pid': 1, 'supervisor_uid': 1000}
    exited = {**generation, 'at_unix_ms': 1100, 'cancelled': False, 'exit_code': 1,
              'log_bytes': {'stdout': {'seen': 0, 'stored': 0}, 'stderr': {'seen': 64, 'stored': 64}},
              'log_errors': {'stdout': None, 'stderr': None},
              'log_synced': {'stdout': True, 'stderr': True},
              'log_truncated': {'stdout': False, 'stderr': False},
              'output_complete': True, 'output_durable': True,
              'terminal_publication_protocol': 1, 'timed_out': False}
    expected = {'expected_exit_code': 1, 'expected_at_unix_ms': 1100,
                'expected_stream_bytes': {'stdout': 0, 'stderr': 64}}
    return exited, request, started, expected


def complete_fixture():
    artifact = pin()
    core = {'bytes': 64, 'sha256': 'b' * 64}
    bridge = {'schema': 'pocket4-audio-compiled-bridge-binding-v1', 'state': 'PASS',
              'whole_apex': dict(artifact), 'core_payload_relative': control.CORE_PAYLOAD,
              'core_payload_file': dict(core),
              'translation_units': [{'source': name} for name in sorted(control.REQUIRED_BRIDGE_UNITS)],
              'actual_successful_ninja_commands_verified': True, 'actual_header_dependencies_verified': True,
              'effective_source_input_window_verified': True}
    q = {'schema': 'pocket4-audio-whole-apex-qualification-v1',
         'normal_complete_audio_apex_build': True, 'signature_and_hashtree_verified': True,
         'payload_file_contents_verified': True, 'payload_membership_verified': True,
         'payload_contents_verified': True, 'complete_apex_qualified': True,
         'runtime_qualified': False, 'production_deployment_performed': False,
         'actual_apex': dict(artifact), 'copy': {'source': dict(artifact)},
         'payload_contents': {'payload_membership_verified': True, 'payload_file_contents_verified': True,
                              'compiled_bridge_binding': bridge}}
    contents = {'schema': 'droidloom-audio-apex-file-contents-v1', 'payload_file_contents_match': True,
                'files': {control.CORE_PAYLOAD: core}}
    return q, artifact, contents


def stage_fixture():
    qualification, artifact, contents = complete_fixture()
    payload = qualification['payload_contents']
    payload['actual_file_contents_result'] = pin('synthetic-contents.json')
    payload['compiled_bridge_binding_result'] = pin('synthetic-compiled-bridge.json')
    class Witness:
        def __init__(self):
            self.rows = {'synthetic-contents.json': contents,
                         'synthetic-compiled-bridge.json': copy.deepcopy(payload['compiled_bridge_binding'])}
            self.reads = []
        def read(self, ref, *, json):
            assert json is True
            self.reads.append(ref['path'])
            return copy.deepcopy(self.rows[ref['path']]), dict(ref)
    return qualification, artifact, Witness()


class ContinuationControls(unittest.TestCase):
    def test_reproduces_original_literal_order_defect(self):
        actual = pin('synthetic-source')
        reviewed = json.loads(json.dumps(actual, sort_keys=True))
        self.assertEqual(actual, reviewed)
        self.assertNotEqual(repr(actual), repr(reviewed))
        self.assertEqual(repr(control.reviewed_reference(actual, reviewed)), repr(reviewed))

    def test_reference_rejects_changed_inputs_before_rebinding(self):
        actual = pin(); reviewed = dict(actual); reviewed['sha256'] = 'c' * 64
        with self.assertRaises(control.ContractError): control.reviewed_reference(actual, reviewed)

    def test_reference_does_not_mutate_observed_or_reviewed_records(self):
        actual = pin(); reviewed = json.loads(json.dumps(actual, sort_keys=True)); old = copy.deepcopy((actual, reviewed))
        rebound = control.reviewed_reference(actual, reviewed); rebound['bytes'] = 100
        self.assertEqual((actual, reviewed), old)

    def test_reproduces_status_wrapper_raw_exit_schema_mismatch(self):
        exited, request, started, expected = raw_exit_fixture()
        with self.assertRaises(KeyError):
            _ = exited['state'] == 'failed' and exited['automatic_retry'] is False
        control.validate_raw_exit(exited, request, started, **expected)

    def test_raw_exit_rejects_wrong_generation_code_and_timestamp(self):
        exited, request, started, expected = raw_exit_fixture()
        for field, value in [('job_id', 'other'), ('launch_nonce', 'other'),
                             ('exit_code', 0), ('at_unix_ms', 1101)]:
            with self.assertRaises(control.ContractError):
                control.validate_raw_exit({**exited, field: value}, request, started, **expected)
        started['launch_nonce'] = 'other'
        with self.assertRaises(control.ContractError):
            control.validate_raw_exit(exited, request, started, **expected)

    def test_raw_exit_rejects_incomplete_or_abnormal_terminal(self):
        exited, request, started, expected = raw_exit_fixture()
        for field, value in [('cancelled', True), ('timed_out', True),
                             ('output_complete', False), ('output_durable', False),
                             ('terminal_publication_protocol', 0)]:
            with self.assertRaises(control.ContractError):
                control.validate_raw_exit({**exited, field: value}, request, started, **expected)

    def test_raw_exit_rejects_incomplete_changed_or_truncated_streams(self):
        exited, request, started, expected = raw_exit_fixture()
        changes = [lambda x: x['log_bytes']['stderr'].update(stored=63),
                   lambda x: x['log_bytes']['stderr'].update(seen=65),
                   lambda x: x['log_synced'].update(stdout=False),
                   lambda x: x['log_truncated'].update(stderr=True),
                   lambda x: x['log_errors'].update(stderr='synthetic failure')]
        for change in changes:
            bad = copy.deepcopy(exited); change(bad)
            with self.assertRaises(control.ContractError):
                control.validate_raw_exit(bad, request, started, **expected)

    def test_raw_exit_rejects_boolean_or_float_integer_fields(self):
        exited, request, started, expected = raw_exit_fixture()
        for field, value in [('exit_code', True), ('exit_code', 1.0),
                             ('terminal_publication_protocol', True), ('terminal_publication_protocol', 1.0),
                             ('at_unix_ms', 1100.0)]:
            with self.assertRaises(control.ContractError):
                control.validate_raw_exit({**exited, field: value}, request, started, **expected)
        for field in ('job_id', 'launch_nonce'):
            with self.assertRaises(control.ContractError):
                control.validate_raw_exit({**exited, field: 1}, {**request, field: 1},
                                          {**started, field: 1}, **expected)

    def test_raw_exit_rejects_numeric_booleans_and_boolean_byte_counts(self):
        exited, request, started, expected = raw_exit_fixture()
        changes = [lambda x: x['log_bytes']['stdout'].update(seen=False, stored=False),
                   lambda x: x['log_bytes']['stderr'].update(seen=64.0, stored=64.0),
                   lambda x: x['log_synced'].update(stdout=1),
                   lambda x: x['log_truncated'].update(stderr=0)]
        for change in changes:
            bad = copy.deepcopy(exited); change(bad)
            with self.assertRaises(control.ContractError):
                control.validate_raw_exit(bad, request, started, **expected)

    def test_profile_constructor_requires_exact_name_and_integer_types(self):
        values = {'name': 'synthetic-profile', 'build_memory_max_bytes': 8 * 1024**3,
                  'host_reserve_bytes': 5 * 1024**3, 'go_memory_limit_bytes': 5 * 1024**3}
        mutations = [('name', True), ('name', 1), ('name', ' '), ('name', ''),
                     ('build_memory_max_bytes', float(8 * 1024**3)), ('host_reserve_bytes', True),
                     ('go_memory_limit_bytes', True), ('go_memory_limit_bytes', float(5 * 1024**3)),
                     ('cpu_quota_percent', 200.0), ('cpu_affinity', (False, True)),
                     ('cpu_affinity', (0.0, 1.0)), ('memory_swap_max_bytes', False)]
        for field, value in mutations:
            with self.assertRaises(control.ContractError): control.ResourceProfile(**{**values, field: value})

    def test_resource_evidence_rejects_boolean_and_float_masquerades(self):
        profile = control.MEMORY8G_RESERVE5G
        for field, value in [('memory_max_bytes', float(8 * 1024**3)), ('cpu_quota_percent', 200.0)]:
            request = {'memory_max_bytes': 8 * 1024**3, 'cpu_quota_percent': 200, field: value}
            with self.assertRaises(control.ContractError): profile.validate_request(request)
        changes = [lambda x: x['resource_profile'].update(memory_swap_max_bytes=False),
                   lambda x: x['resource_profile'].update(cpu_affinity=[False, True]),
                   lambda x: x['resource_profile'].update(go_memory_limit_bytes=float(5 * 1024**3)),
                   lambda x: x['budget'].update(affinity=[False, True]),
                   lambda x: x['admission'].update(hard_cap_bytes=float(8 * 1024**3)),
                   lambda x: x['admission'].update(minimum_bytes=float(13 * 1024**3)),
                   lambda x: x['admission'].update(MemAvailable_bytes=float(13 * 1024**3)),
                   lambda x: x['resource_events_delta'].update(oom=False),
                   lambda x: x['resources_after'].update({'memory.peak': True}),
                   lambda x: x['resources_after'].update({'memory.peak': '1.0'})]
        for change in changes:
            bad = completed_resources(); change(bad)
            with self.assertRaises(control.ContractError): profile.validate_completed_build(bad)

    def test_profile_preserves_five_gib_host_reserve(self):
        p = control.MEMORY8G_RESERVE5G
        self.assertEqual(p.fresh_memavailable_minimum_bytes, 13 * 1024**3)
        self.assertEqual(p.host_reserve_bytes, 5 * 1024**3)
        p.admit(13 * 1024**3)
        with self.assertRaises(control.ContractError): p.admit(13 * 1024**3 - 1)

    def test_old_outer_allocation_is_rejected(self):
        with self.assertRaises(control.ContractError):
            control.MEMORY8G_RESERVE5G.validate_request({'memory_max_bytes': 10 * 1024**3, 'cpu_quota_percent': 200})

    def test_oom_swap_peak_and_incomplete_retirement_are_rejected(self):
        p = control.MEMORY8G_RESERVE5G; good = completed_resources(); p.validate_completed_build(good)
        mutations = [lambda x: x['resource_events_delta'].update(oom_kill=1),
                     lambda x: x['resources_after'].update({'memory.swap.current': '1'}),
                     lambda x: x['resources_after'].update({'memory.peak': str(8 * 1024**3 + 1)}),
                     lambda x: x.update(owned_retirement_complete=False),
                     lambda x: x.update(source_projection_restored=False)]
        for change in mutations:
            bad = copy.deepcopy(good); change(bad)
            with self.assertRaises(control.ContractError): p.validate_completed_build(bad)

    def test_historical_input_is_not_rewritten(self):
        old = completed_resources(); old['budget']['memory.max'] = str(10 * 1024**3); before = copy.deepcopy(old)
        with self.assertRaises(control.ContractError): control.MEMORY8G_RESERVE5G.validate_completed_build(old)
        self.assertEqual(old, before)

    def test_complete_apex_fixture_passes_only_structure_guard(self):
        control.validate_complete_apex(*complete_fixture())

    def test_parser_or_crypto_only_success_is_not_complete(self):
        q, artifact, contents = complete_fixture()
        for field in ('payload_contents_verified', 'complete_apex_qualified', 'signature_and_hashtree_verified'):
            bad = copy.deepcopy(q); bad[field] = False
            with self.assertRaises(control.ContractError): control.validate_complete_apex(bad, artifact, contents)

    def test_missing_compiled_binding_and_wrong_apex_are_rejected(self):
        q, artifact, contents = complete_fixture(); q['payload_contents']['compiled_bridge_binding'] = None
        with self.assertRaises(control.ContractError): control.validate_complete_apex(q, artifact, contents)
        q, artifact, contents = complete_fixture(); artifact['sha256'] = 'd' * 64
        with self.assertRaises(control.ContractError): control.validate_complete_apex(q, artifact, contents)

    def test_wrong_elf_missing_units_and_unproved_commands_are_rejected(self):
        q, artifact, contents = complete_fixture()
        changes = [lambda b: b['core_payload_file'].update(sha256='e' * 64),
                   lambda b: b['translation_units'].pop(),
                   lambda b: b.update(actual_successful_ninja_commands_verified=False),
                   lambda b: b.update(actual_header_dependencies_verified=False),
                   lambda b: b.update(effective_source_input_window_verified=False)]
        for change in changes:
            bad = copy.deepcopy(q); change(bad['payload_contents']['compiled_bridge_binding'])
            with self.assertRaises(control.ContractError): control.validate_complete_apex(bad, artifact, contents)

    def test_payload_byte_counts_cannot_be_boolean_or_float(self):
        for value in (True, 64.0):
            q, artifact, contents = complete_fixture()
            q['payload_contents']['compiled_bridge_binding']['core_payload_file']['bytes'] = value
            contents['files'][control.CORE_PAYLOAD]['bytes'] = value
            with self.assertRaises(control.ContractError): control.validate_complete_apex(q, artifact, contents)

    def test_stage_reads_actual_pinned_contents_and_compiled_receipts(self):
        q, artifact, witness = stage_fixture()
        observed = control.validate_stage_apex(witness, q, artifact)
        self.assertEqual(set(witness.reads), {'synthetic-contents.json', 'synthetic-compiled-bridge.json'})
        self.assertEqual(observed, {'contents': pin('synthetic-contents.json'),
                                    'compiled_bridge': pin('synthetic-compiled-bridge.json')})

    def test_stage_does_not_trust_packet_flags_or_embedded_only_receipts(self):
        q, artifact, witness = stage_fixture()
        q['complete_apex_qualified'] = False
        with self.assertRaises(control.ContractError): control.validate_stage_apex(witness, q, artifact)
        q, artifact, witness = stage_fixture()
        q['payload_contents']['compiled_bridge_binding']['state'] = 'DECLARED_ONLY'
        with self.assertRaises(control.ContractError): control.validate_stage_apex(witness, q, artifact)

    def test_stage_rejects_actual_contents_or_compiled_receipt_mismatch(self):
        q, artifact, witness = stage_fixture()
        witness.rows['synthetic-contents.json']['files'][control.CORE_PAYLOAD]['sha256'] = 'f' * 64
        with self.assertRaises(control.ContractError): control.validate_stage_apex(witness, q, artifact)
        q, artifact, witness = stage_fixture()
        witness.rows['synthetic-compiled-bridge.json']['whole_apex']['sha256'] = 'f' * 64
        with self.assertRaises(control.ContractError): control.validate_stage_apex(witness, q, artifact)

    def test_stage_rejects_a_witness_returning_another_file_pin(self):
        q, artifact, witness = stage_fixture()
        original_read = witness.read
        def different_ref(ref, *, json):
            value, observed = original_read(ref, json=json)
            observed['sha256'] = 'e' * 64
            return value, observed
        witness.read = different_ref
        with self.assertRaises(control.ContractError): control.validate_stage_apex(witness, q, artifact)


if __name__ == '__main__': unittest.main()
