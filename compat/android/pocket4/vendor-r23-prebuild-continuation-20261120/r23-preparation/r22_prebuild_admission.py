#!/usr/bin/python3
"""Pure consumption of the exact R22 resource-gate failure, never a launcher.

Each input is {"reference": <complete original FileRef>, "raw": bytes}.
The seven historical files and all thirteen preparation output bodies are
required. The caller must read them with its original held-input bookends.
This module performs no I/O, import of the historical worker, lock acquisition,
resource reservation, command execution, source change, or automatic retry.
Its result cannot replace fresh retirement, resources, and three-lock checks.
"""
import hashlib
import json
import re
import stat

ROOT = '/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/vendor-build-20261120-9907-r22'
GIB = 1024 ** 3
HISTORY = {
    'worker': ('source.py', 315362, 'ab581ee8886af0ad6d64a0694bc8595387e43531e4e4bd8b1a49cd313cbc13cc',
        [66306,74456838,33152,1000,1000,1,315362,1795178256076008425,1795178256076008425]),
    'outer': ('outer.py', 35232, '836ff9444ae1968284812da1606820f47d214ad3a95d87c1f27caf5bdd56787e',
        [66306,74456841,33152,1000,1000,1,35232,1795178256223868731,1795178256223868731]),
    'contract': ('inputs/CONTRACT.json', 82455, '746660a89df716c9ffc0dbd2a7e10257fec28f0792e504f5ec0304318595acc5',
        [66306,74456837,33152,1000,1000,1,82455,1795178256074376533,1795178256074376533]),
    'bundle': ('inputs/BUNDLE.json', 4934, 'b97888b0542bace5aa55bcf43dd13b0a699be9a437878372703d8bd6e214b296',
        [66306,74456840,33152,1000,1000,1,4934,1795178256219266727,1795178256219266727]),
    'terminal': ('actual/outer-terminal.json', 65157, 'c726dbd4f7f64bb8081a1d6809ad794cc3b549ae423b6bb6f58710a9b28a114a',
        [66306,74456848,33152,1000,1000,1,65157,1795178474750435910,1795178474750435910]),
    'resource': ('actual/outer-resource-probe.json', 319, 'd239072d79b186ffd9db36ca61a70338637d1bc15140ac840cf45c9f06878fc7',
        [66306,74456846,33152,1000,1000,1,319,1795178474748435970,1795178474748435970]),
    'serialized': ('actual/serialized-heavy-admission.json', 161094, '9b9adbda7086ab38a9a257825f827e5eb54b0ba1a071d0cb7d3ad18bac87ad5a',
        [66306,74456845,33152,1000,1000,1,161094,1795178474746436031,1795178474746436031]),
}
CLIENTS = (
    ('r21-original', 1), ('git-fixture-r1', 1), ('git-fixture-r2', 0),
    ('admission-r2', 0), ('source-r1', 1), ('source-r2', 0),
    ('ci-download', 0), ('ci-extraction', 0), ('binary-imports', 0),
    ('host-abi', 0), ('readonly-plans', 0), ('freeze-r1', 1),
    ('snapshot-container-review', 0),
)
RESOURCE_KEYS = {
    'required_memory': 42 * GIB, 'required_disk': 144 * GIB,
    'output_growth_cap': 120 * GIB, 'disk_floor': 24 * GIB,
    'vendor_growth_cap': 118 * GIB, 'all_light_roots_growth_cap': 2 * GIB,
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def integer(value, minimum=0):
    need(type(value) is int and value >= minimum, 'native integer, never bool')
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def same(left, right, message):
    need(canonical(left) == canonical(right), message)


def decode(raw):
    need(type(raw) is bytes and len(raw) <= 1024 ** 2, 'bounded complete raw JSON')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(value):
        raise RuntimeError('non-finite JSON value: ' + value)
    value = json.loads(raw.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                       parse_constant=nonfinite)
    need(type(value) is dict, 'whole JSON object')
    return value


def reference(value, extras=()):
    need(type(value) is dict, 'complete original reference')
    identity_key = 'identity' if 'identity' in value else 'f9'
    need(set(value) - set(extras) == {'path', 'bytes', 'sha256', identity_key},
         'exact reference keys; one identity representation')
    path = value['path']
    need(type(path) is str and path.startswith('/') and '\x00' not in path
         and all(p and p not in ('.', '..') for p in path.split('/')[1:]),
         'canonical original absolute path')
    size = integer(value['bytes'])
    identity = value[identity_key]
    need(type(identity) is list and len(identity) == 9, 'nine original identity fields')
    for number in identity:
        integer(number)
    need(stat.S_ISREG(identity[2]) and identity[5] == 1 and identity[6] == size,
         'whole single-linked regular input')
    digest = value['sha256']
    need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None,
         'whole SHA256')
    return {'path': path, 'bytes': size, 'sha256': digest, 'identity': identity[:]}


def raw_input(value, expected):
    need(type(value) is dict and set(value) == {'reference', 'raw'},
         'original reference and full raw body required')
    actual = reference(value['reference'])
    same(actual, expected, 'exact original path, whole body pin and F9')
    raw = value['raw']
    need(type(raw) is bytes and len(raw) == actual['bytes']
         and hashlib.sha256(raw).hexdigest() == actual['sha256'],
         'actual complete historical input body')
    return actual, raw


def validate_clients(contract, outputs):
    clients = contract['preparation_clients']
    need(type(clients) is list and len(clients) == 13,
         'all thirteen actual preparation clients, including failed attempts')
    same([(x['name'], x['expected_exit_code']) for x in clients], list(CLIENTS),
         'unchanged complete original preparation roster and outcomes')
    sessions = [x['session_id'] for x in clients]
    need(len(set(sessions)) == 13 and type(outputs) is dict and set(outputs) == set(sessions),
         'one complete actual output for each original preparation client')
    consumed = []
    for client, (_, expected_code) in zip(clients, CLIENTS):
        session = client['session_id']
        need(type(session) is str and re.fullmatch('dpty-[0-9a-f]{64}', session),
             'actual durable preparation session')
        expected = reference(client['stdout'])
        need(expected['path'] == '/home/qq/.local/state/hepta-runtime-mac-worker/terminals/'
             + session + '/output.log', 'original durable terminal archive')
        pin, _ = raw_input(outputs[session], expected)
        status = client['actual_status']
        need(type(status) is dict and status['state'] == 'exited'
             and type(status['exit_code']) is int and status['exit_code'] == expected_code
             and status['output_complete'] is True and status['capture_error'] is None,
             'actual original terminal completion and preserved success/failure')
        need(integer(status['bytes_seen']) == integer(status['bytes_stored']) == pin['bytes'],
             'complete terminal capture, no missing suffix')
        integer(status['pid'], 2); integer(status['owner_pid'], 2)
        integer(status['created_unix_ms'], 1)
        consumed.append({'name': client['name'], 'session_id': session,
                         'original_exit_code': expected_code, 'stdout': pin})
    return consumed


def validate_baseline(contract, baseline):
    need(type(baseline) is dict and set(baseline) == {'manifest', 'locks'},
         'actual current manifest and three original lock file identities')
    expected = contract['baseline']
    same(reference(baseline['manifest']), reference(expected['manifest']),
         'R21 recovered manifest whole identity remains unchanged')
    locks = baseline['locks']
    need(type(locks) is list and len(locks) == 3, 'exact original three locks')
    for actual, original in zip(locks, expected['locks']):
        pin = reference(actual, ('body_hex', 'actual_lock_records'))
        same(pin, reference(original, ('body_hex', 'actual_lock_records')),
             'original lock path, inode, bytes, full nanosecond identity unchanged')
        need(type(actual.get('body_hex')) is str
             and actual['body_hex'] == original['body_hex'], 'original lock body unchanged')
        body = bytes.fromhex(actual['body_hex'])
        need(len(body) == pin['bytes'] and hashlib.sha256(body).hexdigest() == pin['sha256'],
             'actual complete lock body')
    # This pure check never certifies a current /proc/locks observation or owns
    # an OFD. The caller must retain its original live lock-acquisition protocol.


def validate_status_history(terminal, serialized, contract):
    targets = contract['live_retirement_targets']
    units = serialized['actual_units']
    commands = terminal['original_worker_status_children']
    need(type(targets) is list and type(units) is list and type(commands) is list
         and len(targets) == len(units) == len(commands) == 132,
         'complete original 132 target, observation and PIDFD child rosters')
    need(len({(x['scope'], x['unit']) for x in targets}) == 132,
         'no missing or duplicate historical retirement target')
    previous_finished = terminal['started_ns']
    for target, unit, child in zip(targets, units, commands):
        need(target['scope'] in ('user', 'system'), 'original service manager scope')
        same((unit['scope'], unit['unit']), (target['scope'], target['unit']),
             'same exact historical service in the same manager')
        need(set(unit) == {'scope', 'unit', 'fields', 'both_cgroup_paths_absent', 'original_pids_absent'}
             and unit['both_cgroup_paths_absent'] is True, 'both original cgroup paths retired')
        same(unit['original_pids_absent'], target.get('pids', []),
             'all original actor PID absences retained')
        fields = {'LoadState': 'not-found', 'ActiveState': 'inactive',
                  'SubState': 'dead', 'ControlGroup': ''}
        if target['unit'].endswith('.service'):
            fields['MainPID'] = '0'
        else:
            need(target['unit'].endswith('.scope'), 'original scope or service')
        same(unit['fields'], fields, 'exact original retired service/scope wire')
        argv = ['/usr/bin/systemctl'] + (['--user'] if target['scope'] == 'user' else [])
        argv += ['show', target['unit'], '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup']
        need(set(child) == {'actual_child_reaped', 'argv', 'error', 'exit_code', 'finished_ns',
             'original_pidfd_held_until_reaped', 'pid', 'started_ns'}, 'whole original status child')
        same(child['argv'], argv, 'fixed read-only command for this exact observed unit')
        need(child['actual_child_reaped'] is True and child['original_pidfd_held_until_reaped'] is True
             and type(child['exit_code']) is int and child['exit_code'] == 0 and child['error'] is None,
             'every original status child succeeded and was reaped under its held PIDFD')
        integer(child['pid'], 2)
        start, end = integer(child['started_ns'], 1), integer(child['finished_ns'], 1)
        need(previous_finished <= start < end <= serialized['observed_ns'] < terminal['finished_ns'],
             'actual serial historical status commands within the original outer')
        previous_finished = end


def validate_r22_prebuild(inputs, baseline):
    need(type(inputs) is dict and set(inputs) == set(HISTORY) | {'preparation_outputs'},
         'complete immutable R22 failure inputs and thirteen original output bodies')
    refs, values = {}, {}
    for name, (relative, size, digest, identity) in HISTORY.items():
        expected = {'path': ROOT + '/' + relative, 'bytes': size,
                    'sha256': digest, 'identity': identity}
        refs[name], raw = raw_input(inputs[name], expected)
        if name not in ('worker', 'outer'):
            values[name] = decode(raw)
    contract, bundle, terminal, resources, serialized = [values[k] for k in
        ('contract', 'bundle', 'terminal', 'resource', 'serialized')]
    need(contract['schema'] == 'p4-vendor-r22-operational-input-contract-v1'
         and contract['operational_inputs_frozen'] is True
         and bundle['schema'] == 'pocket4-vendor-r22-launch-bundle-v1'
         and bundle['dispatch_inputs_frozen'] is True
         and bundle['original_budgets_unchanged'] is True,
         'original actually frozen R22 contract and bundle')
    for value in (contract, bundle, terminal, serialized):
        need(value['production_ready'] is False and value['runtime_qualified'] is False,
             'historical source evidence carries no runtime credit')
    same(reference(bundle['operational_contract']), refs['contract'], 'actual adopted R22 contract')
    same(reference(bundle['worker']), refs['worker'], 'actual adopted R22 worker')
    same(reference(terminal['worker']), refs['worker'], 'actual outer worker body and OFD identity')
    same(reference(terminal['bundle']), refs['bundle'], 'actual outer bundle body and OFD identity')
    need(terminal['schema'] == 'pocket4-vendor-r22-supervisor-terminal-v1'
         and terminal['passed'] is False and terminal['installed'] is False
         and terminal['build_attempted'] is False and terminal['normal_recovery_attempted'] is False
         and terminal['normal_recovery_verified'] is False
         and terminal['serial_held_through_all_source_operations'] is False
         and terminal['serial_lock_acquired'] is True and terminal['fixed_deadline_exceeded'] is False
         and terminal['all_owned_units_retired'] is True
         and terminal['all_created_children_reaped'] is True
         and terminal['phases'] == [] and terminal['children'] == []
         and terminal['final_retirement_errors'] == [],
         'actual prebuild refusal, no fabricated build or recovery phase')
    errors = terminal['errors']
    need(type(errors) is list and len(errors) == 1 and errors[0]['stage'] == 'outer'
         and errors[0]['error'] == "RuntimeError('original fresh 42 GiB / 144 GiB admission')",
         'the sole actual original resource-gate rejection')
    start, finish = integer(terminal['started_ns'], 1), integer(terminal['finished_ns'], 1)
    need(start < finish and set(resources) == set(RESOURCE_KEYS) | {'memory_available', 'disk_free', 'observed_ns'},
         'whole original resource observation')
    for key, value in RESOURCE_KEYS.items():
        need(integer(resources[key]) == value, 'unchanged original resource bound: ' + key)
    memory, disk = integer(resources['memory_available']), integer(resources['disk_free'])
    need(memory < RESOURCE_KEYS['required_memory'] and disk >= RESOURCE_KEYS['required_disk'],
         'preserve the actual below-memory-threshold failure; disk was sufficient')
    need(serialized['schema'] == 'p4-serialized-heavy-build-resource-plan-v1'
         and serialized['resource_admission_reused'] is False
         and serialized['new_provider_materialization_credit'] is False
         and serialized['historical_83_inputs_preserved'] is True,
         'original complete serialized evidence without resource or materialization credit')
    same({k: serialized[k] for k in ('original_minimum_memory_gib', 'vendor_memory_max_gib',
         'simultaneous_other_heavy_compilers', 'bounded_light_scopes_max_gib',
         'host_reserve_gib', 'unallocated_margin_within_minimum_gib')},
         {'original_minimum_memory_gib': 42, 'vendor_memory_max_gib': 24,
          'simultaneous_other_heavy_compilers': 0, 'bounded_light_scopes_max_gib': 3.25,
          'host_reserve_gib': 12, 'unallocated_margin_within_minimum_gib': 2.75},
         'unchanged original serialized resource accounting')
    need(start < integer(serialized['observed_ns'], 1) < integer(resources['observed_ns'], 1) < finish,
         'original retirement evidence preceded the actual fresh resource refusal')
    immutable = serialized['historical_79_immutable_inputs_rechecked']
    need(type(immutable) is list and len(immutable) == len({x['path'] for x in immutable}) == 79,
         'all original immutable historical inputs retained')
    validate_status_history(terminal, serialized, contract)
    clients = validate_clients(contract, inputs['preparation_outputs'])
    validate_baseline(contract, baseline)
    return {'schema': 'p4-r23-actual-r22-prebuild-failure-consumed-v1',
        'actual_R22_prebuild_failure_consumed': True, 'historical_inputs': refs,
        'original_status_children_reaped': 132, 'original_outer_children_created': 0,
        'original_preparation_clients': clients, 'original_manifest_and_three_lock_files_unchanged': True,
        'original_resource_failure': {'memory_available': memory, 'disk_free': disk, **RESOURCE_KEYS},
        'original_vendor_memory_max': 24 * GIB, 'original_recovery_budget_seconds': 1200,
        'live_retirement_recheck_required': True, 'fresh_resource_admission_required': True,
        'original_three_lock_acquisition_required': True, 'resource_admission_reused': False,
        'build_attempted': False, 'normal_recovery_attempted': False,
        'R22_uncreated_producer_lock_adopted': False,
        'source_mutations': 0, 'children_started': 0, 'Android_builds': 0, 'Android_starts': 0,
        'runtime_qualified': False, 'production_ready': False}
