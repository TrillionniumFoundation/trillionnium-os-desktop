#!/usr/bin/env python3
"""Synthetic contract controls. No fixture provides host or runtime credit."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_release_candidate', HERE / 'source/native_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SyntheticIO:
    """Model the existing held-reader interface, not its real filesystem trust.

    Fixed binding/runner pins are explicitly synthetic observations. All tests
    exercise policy and schema boundaries; none qualifies real source bytes.
    """
    class Refusal(RuntimeError):
        pass

    def __init__(self):
        self.files = {}
        self.present_journals = set()

    def need(self, value, reason):
        if not value:
            raise self.Refusal(reason)

    @staticmethod
    def encode(value):
        return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()

    parse = staticmethod(json.loads)

    @staticmethod
    def short(row):
        return {k: row[k] for k in ('path', 'bytes', 'sha256')}

    def add(self, path, value, *, fixed=None):
        raw = value if type(value) is bytes else self.encode(value)
        short = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if fixed:
            short.update(fixed)
        pin = dict(short, identity=[1, 400 + len(self.files), 0o100600, 1000, 1000, 1,
                                  short['bytes'], 100, 100], xattrs={})
        self.files[str(path)] = {'pin': pin, 'value': value}
        return copy.deepcopy(pin)

    def matches(self, actual, expected, *, full=False):
        fields = ('path', 'bytes', 'sha256', 'identity', 'xattrs') if full else ('path', 'bytes', 'sha256')
        return all(k not in expected or actual.get(k) == expected[k] for k in fields)

    def pinned(self, ref, *, contents=False, single=False):
        self.need(ref['path'] in self.files, 'MISSING_SYNTHETIC_FILE')
        row = self.files[ref['path']]
        self.need(self.matches(row['pin'], ref, full='identity' in ref), 'CHANGED_SYNTHETIC_PIN')
        value = row['value']
        raw = value if type(value) is bytes else self.encode(value)
        return copy.deepcopy(row['pin']), raw if contents else None

    def same(self, ref):
        self.pinned(ref)

    def held_read(self, path, *, absent=False):
        self.need(absent and str(path) not in self.present_journals, 'SOURCE_PROJECTION_STILL_PRESENT')
        return {'path': str(path), 'absent': True}, None


class Witness:
    def __init__(self, io):
        self.io = io
        self.observed = {}

    def read(self, ref, json=False):
        row, raw = self.io.pinned(ref, contents=json)
        prior = self.observed.get(row['path'])
        self.io.need(prior is None or self.io.matches(row, prior, full=True), 'EVIDENCE_DRIFT')
        self.observed[row['path']] = row
        return (self.io.parse(raw) if json else row), row

    def gate(self, gate):
        self.io.need(1 <= len(gate['proofs']) <= 32 and 1 <= len(gate['conditions']) <= 1024, 'GATE_BOUND')
        docs = [self.read(ref, json=True)[0] for ref in gate['proofs']]
        for condition in gate['conditions']:
            value = docs[condition['proof']]
            for key in condition['path']:
                value = value[key]
            self.io.need(type(value) is type(condition['equals']) and value == condition['equals'], 'GATE_CONDITION')


def fixture():
    io = SyntheticIO()
    root = module.FINAL / 'native'
    name = 'native597-8gib-hostreserve5-20261108-r1'
    run = root / ('attempts/full-build-' + name)
    attempt = root / ('attempt-' + name)
    fences = root / ('build-fences-' + name)
    out = root / ('android-out-' + name)
    product = out / 'target/product/droidloom_x86_64'
    job = 'deadbeef-1-1'
    jobs = Path('/home/alex/.local/state/hepta-runtime-mac-worker/jobs') / job
    targets = ['libberberis_arm64', 'com.android.art']
    packet = {'controller_source': '# synthetic controller\n', 'outer_source': '# synthetic outer\n'}
    packet_pin = io.add(run / 'build-packet.json', packet)
    sources = {}
    for key, filename in [('controller', 'framework_build.py'), ('outer', 'fenced_build.py'), ('launcher', 'launch_build.py')]:
        raw = packet[key + '_source'].encode() if key != 'launcher' else b'# synthetic launcher\n'
        sources[key] = io.short(io.add(run / filename, raw))
    plan = {'targets': targets, 'dependency_mode': 'Strict', 'builder_source_files': 515,
        'out': str(out), 'builder_sha256': 'b' * 64, 'published_source_manifest_sha256': 'f' * 64,
        'resource_profile_id': name, 'memory_max_bytes': 8 * 1024**3,
        'fresh_MemAvailable_min_bytes': 13 * 1024**3, 'admission_difference_bytes': 5 * 1024**3}
    binding = {'schema': 'pocket4-native597-normal-execution-binding-v1',
        'prior_child_attribution_applies_to_new_attempt': False, 'plan': plan,
        'packet': io.short(packet_pin), 'sources': sources}
    io.add(root / 'manifests/native597-8gib-hostreserve5-normal-execution-binding-20261108-r1.json', binding,
        fixed={'bytes': 75828, 'sha256': 'bc1aa383f812245b45c7e1f76310cadbe95ac89528ac27a5bc8c0c0ff1eaea94'})
    request = {'job_id': job, 'job_dir': str(jobs), 'unit': 'hepta-runtime-job-' + job,
        'execution_mode': 'operator', 'executable': '/usr/bin/python3',
        'args': ['-I', str(run / 'launch_build.py'), packet_pin['sha256']], 'cwd': str(run),
        'timeout_seconds': 23000, 'memory_max_bytes': 8 * 1024**3, 'cpu_quota_percent': 200,
        'nice': 10, 'env': {}, 'terminal_publication_protocol': 1, 'launch_nonce': 'a' * 32}
    request_pin = io.add(jobs / 'request.json', request)
    exited = {'at_unix_ms': 10, 'cancelled': False, 'exit_code': 0, 'job_id': job,
        'launch_nonce': 'a' * 32, 'log_bytes': {'stdout': {'seen': 1, 'stored': 1}, 'stderr': {'seen': 0, 'stored': 0}},
        'log_errors': {'stdout': None, 'stderr': None}, 'log_synced': {'stdout': True, 'stderr': True},
        'log_truncated': {'stdout': False, 'stderr': False}, 'output_complete': True, 'output_durable': True,
        'terminal_publication_protocol': 1, 'timed_out': False}
    exit_pin = io.add(jobs / 'exit.json', exited)
    runner = io.add(jobs / 'runner.py', b'# synthetic runtime runner', fixed={'bytes': 40463,
        'sha256': '65564ce756f3a341def2cf34b2c0d54ef3e75960923c6002c4c56db13564ebf1'})
    admission = {'schema': 'pocket4-native597-outer-runtime-admission-v1',
        'state': 'ACTUAL_OUTER_RUNTIME_VERIFIED_BUILD_PENDING', 'job_id': job,
        'actual_request': io.short(request_pin), 'packet': io.short(packet_pin),
        'outer_timeout_seconds': 23000, 'normal_build_timeout_seconds': 21600,
        'actual_runtime_runner': io.short(runner),
        'outer_cgroup': '0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-' + job + '.service'}
    admission_pin = io.add(run / 'outer-runtime-admission.json', admission)
    pair = {'schema': 1, 'abi': 1, 'protocol': 'DLOOMGE1-PROCMET2', 'host_abi': 'x86_64',
            **{role + '_sha256': ('%x' % (i + 1)) * 64 for i, role in
               enumerate(('engine', 'art_apex', 'libart', 'libnativebridge', 'apex_pubkey'))}}
    pair_pin = io.add(product / 'droidloom-native-generation-pair.json', pair)
    manifest_pin = io.add(root / 'work/aosp-source/.droidloom-source-manifest.json', {'synthetic_generation': 597},
                          fixed={'sha256': 'f' * 64})
    records = {role: io.add(out / ('droidloom-native-generation-build-' + role + '.json'), {'role': role})
               for role in ('attempt', 'inputs', 'command')}
    product_files = {'engine': io.add(product / 'system/lib64/libberberis_arm64.so', b'synthetic engine'),
                     'art_apex': io.add(product / 'system/apex/com.android.art.apex', b'synthetic full APEX')}
    offline_pin = io.add(root / 'synthetic-offline/result.json', {'pair_file': pair_pin})

    def legacy(pin):
        return dict(io.short(pin), identity=[pin['identity'][i] for i in (0, 1, 2, 6, 7, 8)])

    complete = {'state': 'ORDINARY_PAIR_COMMAND_COMPLETED_ARTIFACT_QUALIFICATION_PENDING', 'pair': pair,
        'published_projects': 597, 'published_root_links': 8, 'targets': targets, 'dependency_mode': 'Strict',
        'source_projection_restored': True, 'runtime_authorization_enabled': False, 'installation_performed': False,
        'records': {Path(pin['path']).name: legacy(pin) for pin in records.values()},
        'engine': legacy(product_files['engine']), 'whole_ART_APEX': legacy(product_files['art_apex']),
        'actual_product_pair': legacy(pair_pin), 'actual_published_manifest': legacy(manifest_pin)}
    events = {'low': 0, 'high': 0, 'max': 0, 'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0}
    raw_memory = 'MemTotal: 16777216 kB\nMemAvailable: 13631488 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\nSwapCached: 0 kB\n'
    resource = {'schema': 1, 'state': 'OBSERVED_BEFORE_RESOURCE_ADMISSION',
        'decision_performed': False, 'historical_sample_used_for_admission': False,
        'Main_actions': 0, 'Android_actions': 0, 'production_ready': False,
        'profile': {'resource_profile_id': name, 'memory_max_bytes': 8 * 1024**3,
            'memory_swap_max_bytes': 0, 'minimum_fresh_MemAvailable_bytes': 13 * 1024**3,
            'admission_difference_bytes': 5 * 1024**3, 'global_swap_is_owned_budget': False},
        'owned_observed': {'memory.max': str(8 * 1024**3), 'cpu.max': '200000 100000',
            'memory.swap.max': '0', 'memory.swap.current': '0'},
        'owned_cgroup': '/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-' + job + '.service',
        'meminfo': {'path': '/proc/meminfo', 'bytes': len(raw_memory),
            'sha256': hashlib.sha256(raw_memory.encode()).hexdigest(), 'raw_ascii': raw_memory},
        'observed_unix_ns_decimal': '3000000'}
    resource_pin = io.add(root / ('resource-admission-' + name + '.json'), resource)
    inner = {'schema': 1, 'state': 'ORDINARY_PAIR_COMMAND_COMPLETED_QUALIFICATION_PENDING',
        'builder_returncode': 0, 'error': None, 'input_after_qualified': True, 'input_after_error': None,
        'source_projection_journal_present': False, 'strict_targets': targets, 'builder_sha256': plan['builder_sha256'],
        'runtime_authorization_enabled': False, 'Main_actions': 0, 'Android_actions': 0, 'all_apps_ready': False,
        'cleanup': {'complete': True, 'children': [{'pid': 42, 'wait_status': 0, 'reaped': True}], 'errors': []},
        'memory_events': ''.join('%s %d\n' % item for item in events.items()),
        'owned_resource_gate': {'pass': True, 'events': events}, 'memory_swap_max': '0',
        'memory_swap_current': '0', 'memory_swap_peak': '0',
        'owned_budget_before_builder': {'memory.max': str(8 * 1024**3), 'cpu.max': '200000 100000',
            'memory.swap.max': '0', 'memory.swap.current': '0'}, 'normal_command_completion_gate': complete,
        'resource_admission_receipt': legacy(resource_pin)}
    inner_pin = io.add(attempt / 'terminal.json', inner)
    outer = {'schema': 1, 'state': 'OFFLINE_BUILD_AND_STOPPED_COHORT_FENCES_PASSED', 'error': None,
        'inner_build_called': True, 'inner_returncode': 0, 'before_observed': True, 'after_observed': True,
        'Main_actions': 0, 'Android_actions': 0, 'installed': False, 'production_ready': False,
        'runtime_authorization_enabled': False, 'restart_requires_new_generation_qualification': True,
        'stopped_cohort_fence_assessment': {'stopped_cohort_fence_pass': True, 'changed_invariants': [],
            'live_Main_fence_pass': False, 'stopped_generation_absence_checked_before_and_after': True,
            'continuous_absence_or_unobserved_interference_excluded': False,
            'runtime_authorization_enabled': False, 'new_generation_qualification_required_after_restart': True},
        'capture_lifecycle_controls': {'state': 'PASS', 'passed': 4,
            'rows': [{'passed': True, 'owned_children_empty': True} for _ in range(4)]},
        'capture_lifecycle_receipts': [{'phase': phase, 'qualified_success': True, 'first_error': None,
            'secondary_errors': [], 'command': {'child_reaped': True, 'owned_tree_cleanup_complete': True,
            'all_acquired_fds_closed': True, 'retirement_within_deadline': True, 'qualified_success': True,
            'returncode': 0, 'remaining_owned_children': [], 'descendants': []}} for phase in ('before', 'after')]}
    outer_pin = io.add(fences / 'terminal.json', outer)
    works = (root / 'work', module.FINAL / 'framework/work',
             Path('/home/alex/work/pocket4-audio-source-build-20261108-r1/work'))
    fresh = [{'path': str(work / lock), 'identity': [1, 700 + i * 2 + j, 0o100600, 1000, 1000, 1, 7, 100, 100],
              'observed_free': True} for i, work in enumerate(works) for j, lock in
              enumerate(('package-build.lock', 'aosp-source-update.lock'))]
    leased = [{'path': row['path'], 'identity': row['identity'], 'content_sha256': '9' * 64,
               'acquired_ns': 1000000} for row in fresh[2:]]
    parent = {'schema': 'native597-full-parent-work-lease-v1', 'errors': [], 'outer_invoked': True,
        'outer_returned': True, 'outer_returncode': 0, 'owned_retirement_complete': True,
        'owned_children_after_outer': [], 'source_restore_check_completed': True,
        'source_projection_restored': True, 'native_two_locks_free_after_outer': True,
        'full_build_success': True, 'global_admission_granted': False, 'normal_updater_owns_native_two': True,
        'inner_terminal': io.short(inner_pin), 'outer_terminal': io.short(outer_pin),
        'original_inner_cleanup_summary': {'complete': True, 'child_record_count': 1, 'error_count': 0,
            'remaining_count': 0, 'complete_original_in_inner_terminal_reference': True},
        'original_input_after_qualified': True, 'fresh_six_locks': fresh, 'parent_leases': leased,
        'lease_release': {'qualified': True, 'all_parent_descriptors_closed': True, 'remaining_parent_kernel_locks': [],
            'errors': [], 'rows': [dict(row, descriptor_closed=True, released_ns=8000000) for row in leased]},
        'started_ns': 2000000, 'source_restore_check_completed_ns': 7000000, 'finished_ns': 9000000,
        'projection_observations': [{'path': str(work / 'source-projection.json'), 'absent': True} for work in works]}
    parent_pin = io.add(run / 'parent-work-lease-terminal.json', parent)
    requested = {'runtime_request': io.short(request_pin), 'runtime_exit': io.short(exit_pin),
        'outer_runtime_admission': io.short(admission_pin), 'parent_work_lease_terminal': io.short(parent_pin)}
    info = {'pair': pair, 'ordinary_records': records, 'sources': product_files, 'offline': offline_pin}
    return io, requested, info, {'binding': binding, 'request': request, 'exit': exited, 'admission': admission,
        'inner': inner, 'outer': outer, 'parent': parent, 'complete': complete, 'root': root, 'run': run,
        'resource': resource}


class Release(unittest.TestCase):
    def setUp(self):
        self.io, self.requested, self.info, self.docs = fixture()

    def call(self):
        return module.native_release(self.io, Witness(self.io), self.requested, self.info)

    def reject(self, message=None):
        with self.assertRaisesRegex(self.io.Refusal, message or '.'):
            self.call()

    def test_complete_synthetic_contract_only(self):
        gate = self.call()
        self.assertEqual(len(gate['proofs']), 7)
        self.assertLess(len(gate['conditions']), 1024)
        self.assertIs(self.docs['outer']['production_ready'], False)

    def test_failed_inner_is_not_source_success(self):
        self.docs['inner']['state'] = 'FAILED'
        self.reject('INNER_state')

    def test_normalized_H_status_cannot_replace_raw_exit(self):
        self.docs['exit']['state'] = 'succeeded'
        self.reject('RAW_H_EXIT_SCHEMA')

    def test_unknown_nonzero_or_boolean_exit_rejected(self):
        for value in (None, 1, False):
            with self.subTest(value=value):
                self.docs['exit']['exit_code'] = value
                self.reject('RAW_H_EXIT_exit_code')

    def test_original_child255_exception_not_reused(self):
        self.docs['inner']['cleanup']['children'][0]['wait_status'] = 65280
        self.reject('OWNED_CHILD_RAW_ZERO_STATUS')

    def test_unknown_or_signal_adopted_status_rejected(self):
        for value in (None, 9, False):
            with self.subTest(value=value):
                self.docs['inner']['cleanup']['children'][0]['wait_status'] = value
                self.reject('OWNED_CHILD_RAW_ZERO_STATUS')

    def test_original_six_field_identity_drift_rejected(self):
        next(iter(self.docs['complete']['records'].values()))['identity'][-1] += 1
        self.reject('ORIGINAL_IDENTITY_CHANGED')

    def test_current597_cannot_be_old268(self):
        self.docs['complete']['published_projects'] = 268
        self.reject('ACTUAL_PAIR_published_projects')

    def test_mixed_pair_rejected(self):
        self.docs['complete']['pair'] = dict(self.info['pair'], engine_sha256='0' * 64)
        self.reject('ACTUAL_PAIR_pair')

    def test_wrong_output_generation_rejected(self):
        row = next(iter(self.docs['complete']['records'].values()))
        row['path'] = row['path'].replace('8gib-hostreserve5-', '')
        self.reject('EXACT_ACTUAL_FILE_REF')

    def test_durable_raw_terminal_required(self):
        self.docs['exit']['output_durable'] = False
        self.reject('RAW_H_EXIT_output_durable')

    def test_same_request_nonce_required(self):
        self.docs['exit']['launch_nonce'] = 'b' * 32
        self.reject('RAW_H_EXIT_launch_nonce')

    def test_original_10gib_request_is_not_new_profile(self):
        self.docs['request']['memory_max_bytes'] = 10 * 1024**3
        self.reject('REQUEST_memory_max_bytes')

    def test_reserve_cannot_be_reduced(self):
        self.docs['binding']['plan']['fresh_MemAvailable_min_bytes'] = 12 * 1024**3
        self.reject('FRESH_HOST_FLOOR')

    def test_actual_resource_profile_cannot_be_historical(self):
        self.docs['resource']['profile']['memory_max_bytes'] = 10 * 1024**3
        self.reject('ACTUAL_ADMISSION_profile')

    def test_fresh_memory_hash_drift_rejected(self):
        self.docs['resource']['meminfo']['raw_ascii'] += 'Changed: 1 kB\n'
        self.reject('FRESH_MEMINFO_BYTES')

    def test_actual_memory_below_floor_despite_global_swap_rejected(self):
        raw = 'MemTotal: 16777216 kB\nMemAvailable: 13631487 kB\nSwapTotal: 67108864 kB\nSwapFree: 67108864 kB\nSwapCached: 0 kB\n'
        self.docs['resource']['meminfo'].update(raw_ascii=raw, bytes=len(raw),
            sha256=hashlib.sha256(raw.encode()).hexdigest())
        self.reject('ACTUAL_FRESH_13GIB_ADMISSION')

    def test_old_sample_not_accepted_for_current_attempt(self):
        self.docs['resource']['observed_unix_ns_decimal'] = '1999999'
        self.reject('CURRENT_ATTEMPT_RESOURCE_SAMPLE')

    def test_owned_OOM_even_without_kill_rejected(self):
        self.docs['inner']['memory_events'] = self.docs['inner']['memory_events'].replace('oom 0', 'oom 1')
        self.docs['inner']['owned_resource_gate']['events']['oom'] = 1
        self.reject('NO_OWNED_OOM')

    def test_memory_reclaim_event_is_not_falsely_oom(self):
        self.docs['inner']['memory_events'] = self.docs['inner']['memory_events'].replace('max 0', 'max 7')
        self.docs['inner']['owned_resource_gate']['events']['max'] = 7
        self.call()

    def test_source_restore_false_rejected(self):
        self.docs['parent']['source_projection_restored'] = False
        self.reject('PARENT_source_projection_restored')

    def test_journal_reappeared_rejected(self):
        self.io.present_journals.add(str(self.docs['root'] / 'work/source-projection.json'))
        self.reject('SOURCE_PROJECTION_STILL_PRESENT')

    def test_parent_descriptor_not_closed_rejected(self):
        self.docs['parent']['lease_release']['rows'][0]['descriptor_closed'] = False
        self.reject('PARENT_DESCRIPTOR_CLOSED')

    def test_release_before_restoration_rejected(self):
        self.docs['parent']['lease_release']['rows'][0]['released_ns'] = 6000000
        self.reject('RELEASE_AFTER_RESTORATION')

    def test_unknown_children_block_release(self):
        self.docs['parent']['owned_children_after_outer'] = [123]
        self.reject('PARENT_owned_children_after_outer')

    def test_aliased_six_lock_inodes_rejected(self):
        self.docs['parent']['fresh_six_locks'][1]['identity'] = self.docs['parent']['fresh_six_locks'][0]['identity']
        self.reject('SIX_DISTINCT_ORIGINAL_LOCKS')

    def test_missing_raw_exit_rejected(self):
        del self.io.files[self.requested['runtime_exit']['path']]
        self.reject('MISSING_SYNTHETIC_FILE')

    def test_exit_before_parent_completion_rejected(self):
        self.docs['exit']['at_unix_ms'] = 8
        self.reject('RAW_EXIT_FOLLOWS_PARENT_RETIREMENT')

    def test_caller_cannot_supply_arbitrary_true_predicates(self):
        self.requested = {'proofs': [], 'conditions': [{'equals': True}]}
        self.reject('EXACT_COMPLETED_OUTPUT_REFS_REQUIRED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
