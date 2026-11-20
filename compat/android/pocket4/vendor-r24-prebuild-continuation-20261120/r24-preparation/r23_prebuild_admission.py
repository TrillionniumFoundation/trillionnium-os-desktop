#!/usr/bin/python3
"""Pure exact R23 prebuild-failure consumption with full original R22 nesting.

Every input is an original full raw body plus its exact original reference.
The previously reviewed R22 helper is loaded only from its full fixed SHA body,
then revalidates all seven R22 originals and thirteen actual archive bodies.
No file I/O, resource admission, source lock, subprocess, build or retry occurs.
The caller must retain original host input bookends and perform fresh live gates.
"""
import hashlib
import json
import types

ROOT = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r23'
ORIGINAL_ROOT = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1'
HISTORY = {'worker': ('source.py',
            335019,
            '19f730767efb1afd3e065093f389e02c8ddfa41e62c19aa89e97574e6ff3dff8',
            [66306,
             74456853,
             33152,
             1000,
             1000,
             1,
             335019,
             1795180706915358448,
             1795180706915358448]),
 'outer': ('outer.py',
           35232,
           '915355af4fce7ca741acb021d10c81ea252e6f76064ef051f0c1d89bbb130e36',
           [66306,
            74456855,
            33152,
            1000,
            1000,
            1,
            35232,
            1795180707080840872,
            1795180707080840872]),
 'contract': ('inputs/CONTRACT.json',
              86703,
              '0957c9d15970b80301eb30d498c2b9baf3a9b84e7dccd0ec42c5f7442a35e875',
              [66306,
               74456852,
               33152,
               1000,
               1000,
               1,
               86703,
               1795180706913390157,
               1795180706913390157]),
 'bundle': ('inputs/BUNDLE.json',
            4887,
            '4cb03fae174dd725689f470b6c9d56badfe492dbc36203d59cb85b3c6c0634ca',
            [66306,
             74456854,
             33152,
             1000,
             1000,
             1,
             4887,
             1795180707075647377,
             1795180707075647377]),
 'terminal': ('actual/outer-terminal.json',
              66143,
              '7b4effc576d23778274d5215f420a86856dee84f5f9acd27f503d5672c9f179f',
              [66306,
               74456861,
               33152,
               1000,
               1000,
               1,
               66143,
               1795180783305971480,
               1795180783305971480]),
 'resource': ('actual/outer-resource-probe.json',
              319,
              '625b79af7389ca75e6c5a427dc5a94fbfd32e179891fd2c1e54d2fbb1530e1c7',
              [66306,
               74456859,
               33152,
               1000,
               1000,
               1,
               319,
               1795180783302971571,
               1795180783302971571]),
 'serialized': ('actual/serialized-heavy-admission.json',
                178565,
                '5b1ae7eedb71b2007730ae19f979a966604ad103c874930e85b238e2231ccfb5',
                [66306,
                 74456858,
                 33152,
                 1000,
                 1000,
                 1,
                 178565,
                 1795180783300971632,
                 1795180783300971632])}
R22_HELPER_REF = {'bytes': 17250,
 'identity': [66306,
              56367534,
              33152,
              1000,
              1000,
              1,
              17250,
              1795180652685336514,
              1795180652685336514],
 'path': '/home/qq/work/p4-r23-controller-preparation-20261120-3b9d-r1/r22_prebuild_admission.py',
 'sha256': '3ebc4eaf743b3a733501c4743178cc604469c49b1e6588a306bef484a76665eb'}
CLIENTS = (('r22-freeze-r2', 'dpty-f70ee7be8e5157c61d3f7d090147804e1da433c8e29decdc44d543452b8ac077', 0),
 ('r22-original-supervisor',
  'dpty-a2dd1fc97b891e1fc369ec9b2c8fec978a93d6a288e4d21cd5c1209cbdfe0b1c',
  1),
 ('r22-prebuild-input-capture',
  'dpty-807b1e5927cac379fbeb56ad26e3c8fb8d54b64633bb0ab39edee88ca111a91a',
  0),
 ('r23-original-root-absence',
  'dpty-fa8c13a30cba5aa11aec300fa205aa9fc06fc5260c3caa66392799b9d975a19e',
  0))
ADDITIONAL_TARGETS = [{'pids': [], 'scope': 'user', 'unit': 'p4-cp3a-vendor-supervisor-20261120-9907-r22.service'},
 {'pids': [], 'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r22.service'},
 {'pids': [], 'scope': 'user', 'unit': 'p4-cp3a-vendor-20261120-9907-r22-recovery.service'}]


def need(value, message):
    if not value:
        raise RuntimeError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def load_original_r22(value):
    """Execute only the exact previously reviewed pure helper body, never a path."""
    need(type(value) is dict and set(value) == {'reference', 'raw'},
         'complete original R22 helper source and reference')
    need(encoded(value['reference']) == encoded(R22_HELPER_REF),
         'exact original R22 helper path, complete pin and nanoseconds')
    raw = value['raw']
    need(type(raw) is bytes and len(raw) == R22_HELPER_REF['bytes']
         and hashlib.sha256(raw).hexdigest() == R22_HELPER_REF['sha256'],
         'exact full unchanged R22 pure helper source')
    helper = types.ModuleType('p4_r24_exact_r22_prebuild')
    helper.__file__ = R22_HELPER_REF['path']
    exec(compile(raw, helper.__file__, 'exec'), helper.__dict__)
    return helper


def validate_clients(helper, contract, outputs):
    clients = contract['preparation_clients']
    need(type(clients) is list and len(clients) == 4,
         'all four actual R23 preparation clients')
    helper.same([(x['name'], x['session_id'], x['expected_exit_code']) for x in clients],
                list(CLIENTS), 'original complete four-client identity/outcome roster')
    need(type(outputs) is dict and set(outputs) == {x[1] for x in CLIENTS},
         'all four complete original output bodies, including the failed R22 supervisor')
    consumed = []
    for client, (name, session, code) in zip(clients, CLIENTS):
        pin = helper.reference(client['stdout'])
        need(pin['path'] == '/home/qq/.local/state/hepta-runtime-mac-worker/terminals/'
             + session + '/output.log', 'same actual durable terminal archive')
        actual, _ = helper.raw_input(outputs[session], pin)
        status = client['actual_status']
        need(type(status) is dict and status['state'] == 'exited'
             and type(status['exit_code']) is int and status['exit_code'] == code
             and status['output_complete'] is True and status['capture_error'] is None,
             'original terminal fully exited with its actual success/failure')
        need(helper.integer(status['bytes_seen']) == helper.integer(status['bytes_stored'])
             == pin['bytes'], 'no missing prefix or suffix of actual terminal output')
        helper.integer(status['pid'], 2); helper.integer(status['owner_pid'], 2)
        helper.integer(status['created_unix_ms'], 1)
        consumed.append({'name': name, 'session_id': session,
                         'original_exit_code': code, 'stdout': actual})
    return consumed


def validate_status_history(helper, terminal, serialized, contract, r22_contract):
    original = r22_contract['live_retirement_targets']
    extra = contract['additional_live_retirement_targets']
    need(type(original) is list and len(original) == 132,
         'complete original 132 retirement targets retained')
    helper.same(extra, ADDITIONAL_TARGETS, 'the three exact R22 units checked by R23')
    targets = original + extra
    continuation = serialized['actual_R22_continuation']
    original_units = serialized['actual_units']
    extra_units = continuation['additional_R22_live_retirement_observations']
    need(type(original_units) is list and len(original_units) == 132
         and type(extra_units) is list and len(extra_units) == 3,
         'both full original and added retirement observation arrays')
    units = original_units + extra_units
    children = terminal['original_worker_status_children']
    need(type(children) is list and len(children) == 135
         and len({(x['scope'], x['unit']) for x in targets}) == 135,
         'all 135 actual original status children and distinct target identities')
    previous = helper.integer(terminal['started_ns'], 1)
    observed = helper.integer(serialized['observed_ns'], 1)
    finished = helper.integer(terminal['finished_ns'], 1)
    for target, unit, child in zip(targets, units, children):
        need(target['scope'] in ('user', 'system'), 'actual original service manager scope')
        helper.same((unit['scope'], unit['unit']), (target['scope'], target['unit']),
                    'same exact original target in the same manager')
        need(set(unit) == {'scope', 'unit', 'fields', 'both_cgroup_paths_absent', 'original_pids_absent'}
             and unit['both_cgroup_paths_absent'] is True, 'both original cgroup paths absent')
        helper.same(unit['original_pids_absent'], target.get('pids', []),
                    'all original PID absences retained')
        fields = {'LoadState': 'not-found', 'ActiveState': 'inactive',
                  'SubState': 'dead', 'ControlGroup': ''}
        if target['unit'].endswith('.service'):
            fields['MainPID'] = '0'
        else:
            need(target['unit'].endswith('.scope'), 'original service or scope wire')
        helper.same(unit['fields'], fields, 'exact actually observed retired service fields')
        argv = ['/usr/bin/systemctl'] + (['--user'] if target['scope'] == 'user' else [])
        argv += ['show', target['unit'], '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
        need(set(child) == {'actual_child_reaped', 'argv', 'error', 'exit_code', 'finished_ns',
             'original_pidfd_held_until_reaped', 'pid', 'started_ns'}, 'complete original status child')
        helper.same(child['argv'], argv, 'fixed original readonly status command')
        need(child['actual_child_reaped'] is True and child['original_pidfd_held_until_reaped'] is True
             and type(child['exit_code']) is int and child['exit_code'] == 0
             and child['error'] is None, 'each original child succeeded under its retained PIDFD and reaped')
        helper.integer(child['pid'], 2)
        start, end = helper.integer(child['started_ns'], 1), helper.integer(child['finished_ns'], 1)
        need(previous <= start < end <= observed < finished,
             'complete serial status history within the same original outer window')
        previous = end


def validate_continuation(helper, continuation, contract, nested_failure):
    need(type(continuation) is dict and set(continuation) == {
        'actual_R22_prebuild_failure_and_original_status_retirement',
        'actual_unmaterialized_R22_plan', 'current_prebuild_controls',
        'additional_R22_live_retirement_observations', 'all_actual_R22_input_pins_preserved',
        'resource_admission_reused', 'same_total_admission_budget_seconds', 'observed_ns'},
        'complete actual R23 continuation record')
    helper.same(continuation['actual_R22_prebuild_failure_and_original_status_retirement'],
                nested_failure, 'actual nested R22 failure must be re-derived from every original body')
    need(continuation['all_actual_R22_input_pins_preserved'] is True
         and continuation['resource_admission_reused'] is False
         and helper.integer(continuation['same_total_admission_budget_seconds']) == 150,
         'no lost actual input, resource reuse or renewed retirement deadline')
    absence = continuation['actual_unmaterialized_R22_plan']
    need(type(absence) is dict and set(absence) == {'parent', 'parent_identity',
         'absent_direct_children', 'unmaterialized_planned_lock', 'actual_historical_input_removed'},
         'complete actual predecessor absence observation')
    identity = absence['parent_identity']
    need(type(identity) is list and len(identity) == 9,
         'whole original absence parent identity')
    for number in identity:
        helper.integer(number)
    helper.same(identity[:5], contract['root_authority'], 'same actual original parent authority')
    need(absence['parent'] == ORIGINAL_ROOT and absence['actual_historical_input_removed'] is False,
         'absence never deletes an actual historical input')
    helper.same(absence['absent_direct_children'], contract['unmaterialized_R22_plan']['absent_roots'],
                'all three original uncreated predecessor roots retained')
    need(absence['unmaterialized_planned_lock'] == contract['unmaterialized_R22_plan']['lock_path'],
         'exact unmaterialized R22 planned lock')
    controls = continuation['current_prebuild_controls']
    helper.same(controls, {'control_receipt': contract['prebuild_controls'],
        'actual_positive_cases': 1, 'negative_cases': 27,
        'runtime_qualified': False, 'production_ready': False},
        'the actual reviewed source-only R22 controls without invented live credit')


def validate_r23_prebuild(inputs, baseline):
    need(type(inputs) is dict and set(inputs) == set(HISTORY) | {
        'r22_helper', 'r22', 'preparation_outputs'},
        'seven complete actual R23 inputs, original helper, full nested R22 inputs and four archives')
    helper = load_original_r22(inputs['r22_helper'])
    nested_failure = helper.validate_r22_prebuild(inputs['r22'], baseline)
    refs, values = {}, {}
    for name, (relative, size, digest, identity) in HISTORY.items():
        expected = {'path': ROOT + '/' + relative, 'bytes': size,
                    'sha256': digest, 'identity': identity}
        refs[name], raw = helper.raw_input(inputs[name], expected)
        if name not in ('worker', 'outer'):
            values[name] = helper.decode(raw)
    contract, bundle, terminal, resources, serialized = [values[k] for k in
        ('contract', 'bundle', 'terminal', 'resource', 'serialized')]
    r22_contract = helper.decode(inputs['r22']['contract']['raw'])
    need(contract['schema'] == 'p4-vendor-r23-prebuild-continuation-contract-v1'
         and contract['operational_inputs_frozen'] is True
         and contract['all_original_constraints_unchanged'] is True
         and bundle['schema'] == 'pocket4-vendor-r23-launch-bundle-v1'
         and bundle['dispatch_inputs_frozen'] is True
         and bundle['original_budgets_unchanged'] is True
         and bundle['new_vendor_build_not_yet_dispatched'] is True
         and bundle['previous_failed_build_replaced'] is False,
         'the exact actually frozen R23 successor retained the failed R22 evidence')
    for document in (contract, bundle, terminal, serialized):
        need(document['production_ready'] is False and document['runtime_qualified'] is False,
             'historical source-only evidence grants no runtime credit')
    helper.same(helper.reference(contract['prebuild_helper']), R22_HELPER_REF,
                'same actual original R22 helper source and identity')
    helper.same(contract['r22_inputs'], nested_failure['historical_inputs'],
                'all original R22 input refs remain exact and nested')
    for key in ('baseline', 'current_source', 'current_binaries'):
        helper.same(contract[key], r22_contract[key], 'unchanged original R22 ' + key)
    helper.same(helper.reference(bundle['operational_contract']), refs['contract'], 'exact R23 contract')
    helper.same(helper.reference(bundle['worker']), refs['worker'], 'exact R23 worker')
    helper.same(helper.reference(terminal['worker']), refs['worker'], 'actual R23 outer worker OFD')
    helper.same(helper.reference(terminal['bundle']), refs['bundle'], 'actual R23 outer bundle OFD')
    helper.same(bundle['actual_R22_prebuild_failure'], nested_failure['historical_inputs'],
                'the actual launch bundle retains the complete original R22 failure refs')
    need(terminal['schema'] == 'pocket4-vendor-r23-supervisor-terminal-v1',
         'actual R23 terminal schema remains original')
    for key in ('passed', 'installed', 'build_attempted', 'normal_recovery_attempted',
                'normal_recovery_verified', 'serial_held_through_all_source_operations',
                'fixed_deadline_exceeded'):
        need(terminal[key] is False, 'actual R23 prebuild refusal flag: ' + key)
    for key in ('serial_lock_acquired', 'all_owned_units_retired', 'all_created_children_reaped'):
        need(terminal[key] is True, 'actual original terminal completion flag: ' + key)
    for key in ('phases', 'children', 'final_retirement_errors'):
        helper.same(terminal[key], [], 'no build, recovery, phase or unreaped child: ' + key)
    errors = terminal['errors']
    need(type(errors) is list and len(errors) == 1 and errors[0]['stage'] == 'outer'
         and errors[0]['error'] == "RuntimeError('original fresh 42 GiB / 144 GiB admission')",
         'the sole original fresh resource rejection, never a fabricated build failure')
    need(set(resources) == set(helper.RESOURCE_KEYS) | {'memory_available', 'disk_free', 'observed_ns'},
         'complete original fresh resource observation')
    for key, value in helper.RESOURCE_KEYS.items():
        need(helper.integer(resources[key]) == value, 'unchanged original resource bound: ' + key)
    memory, disk = helper.integer(resources['memory_available']), helper.integer(resources['disk_free'])
    need(memory < helper.RESOURCE_KEYS['required_memory'] and disk >= helper.RESOURCE_KEYS['required_disk'],
         'the actual R23 failure was below memory threshold with sufficient disk')
    need(serialized['schema'] == 'p4-serialized-heavy-build-resource-plan-v1'
         and serialized['resource_admission_reused'] is False
         and serialized['new_provider_materialization_credit'] is False
         and serialized['historical_83_inputs_preserved'] is True,
         'unchanged original serialized admission schema and limits')
    helper.same({k: serialized[k] for k in ('original_minimum_memory_gib', 'vendor_memory_max_gib',
        'simultaneous_other_heavy_compilers', 'bounded_light_scopes_max_gib',
        'host_reserve_gib', 'unallocated_margin_within_minimum_gib')},
        {'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
         'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
         'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75},
        'all original serialized resource accounting unchanged')
    immutable = serialized['historical_79_immutable_inputs_rechecked']
    need(type(immutable) is list and len(immutable) == len({x['path'] for x in immutable}) == 79,
         'all original immutable historical input observations retained')
    continuation = serialized['actual_R22_continuation']
    validate_continuation(helper, continuation, contract, nested_failure)
    validate_status_history(helper, terminal, serialized, contract, r22_contract)
    clients = validate_clients(helper, contract, inputs['preparation_outputs'])
    start, finish = helper.integer(terminal['started_ns'], 1), helper.integer(terminal['finished_ns'], 1)
    need(start < helper.integer(continuation['observed_ns'], 1)
         <= helper.integer(serialized['observed_ns'], 1)
         < helper.integer(resources['observed_ns'], 1) < finish,
         'all original admission evidence preceded this actual fresh resource refusal')
    return {'schema': 'p4-r24-actual-r23-prebuild-failure-consumed-v1',
        'actual_R23_prebuild_failure_consumed': True, 'historical_inputs': refs,
        'original_R22_helper_source': R22_HELPER_REF,
        'actual_nested_R22_failure': nested_failure,
        'original_status_children_reaped': 135, 'original_outer_children_created': 0,
        'original_preparation_clients': clients,
        'original_manifest_and_three_lock_files_unchanged': True,
        'original_resource_failure': {'memory_available': memory, 'disk_free': disk, **helper.RESOURCE_KEYS},
        'original_vendor_memory_max': 24 * 1024**3, 'original_recovery_budget_seconds': 1200,
        'same_total_admission_budget_seconds': 150,
        'live_retirement_recheck_required': True, 'fresh_resource_admission_required': True,
        'original_three_lock_acquisition_required': True, 'resource_admission_reused': False,
        'R23_uncreated_producer_lock_adopted': False,
        'build_attempted': False, 'normal_recovery_attempted': False,
        'source_mutations': 0, 'children_started': 0, 'Android_builds': 0, 'Android_starts': 0,
        'runtime_qualified': False, 'production_ready': False}
