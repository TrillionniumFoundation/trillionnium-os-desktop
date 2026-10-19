"""Offline schema4 checks. Never open the original compiler artifact/target paths."""
import hashlib
import json
import re
from collections import Counter


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def jsonl(data):
    return [json.loads(line) for line in data.splitlines()]


def compiler_records(rows, ledger, policy):
    require(policy['schema'] == 'a01-component-path-projection/4', 'wrong projection schema')
    require(digest(policy['rustc_version'].encode()) == policy['rustc_identity'], 'rustc identity mismatch')
    require(policy['real_root'] != policy['virtual_root'], 'real/virtual roots must differ')
    require(type(policy['execution']['cargo_build_jobs']) is int and policy['execution']['cargo_build_jobs'] == 1,
            'schema4 policy did not select one Cargo job')
    require('commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48' in policy['rustc_version'],
            'schema4 compiler is not the fixed nightly')
    flag = '--remap-path-prefix=' + policy['real_root'] + '=' + policy['virtual_root']
    pids = [row['pid'] for row in rows]
    require(len(pids) == len(set(pids)), 'compiler invocation PID reused')
    require(len(ledger) == 2 * len(rows), 'producer ledger invocation count mismatch')
    require(all(entry['state'] in ('started', 'completed') for entry in ledger), 'unknown ledger state')
    require(set(entry['pid'] for entry in ledger) == set(pids), 'producer ledger PID set mismatch')
    canonical_units = {}
    canonical_incoming = {}
    scopes = Counter()
    local_replacements = 0
    remap_insertions = 0
    probe_statuses = Counter()
    completed_unit_statuses = Counter()
    for row in rows:
        starts = [entry for entry in ledger if entry['pid'] == row['pid'] and entry['state'] == 'started']
        finishes = [entry for entry in ledger if entry['pid'] == row['pid'] and entry['state'] == 'completed']
        require(len(starts) == len(finishes) == 1, 'compiler invocation requires one start and completion')
        unit = row['compiler_unit']
        require(starts[0]['unit'] == unit == finishes[0]['unit'], 'compiler/producer unit identity mismatch')
        require(ledger.index(starts[0]) < ledger.index(finishes[0]), 'completion precedes invocation start')
        incoming = row['incoming_argv']
        expected = list(incoming)
        delimiter = expected.index('--') if '--' in expected else len(expected)
        if flag not in expected[:delimiter]:
            expected.insert(delimiter, flag)
            remap_insertions += 1
        if unit is not None:
            scopes[unit['scope']] += 1
            require(finishes[0]['returncode'] == 0, 'Cargo compiler unit failed')
            completed_unit_statuses[finishes[0]['returncode']] += 1
            for path, identity in finishes[0].get('artifacts', {}).items():
                require(path.startswith('/') and set(identity) == {'st_dev', 'st_ino', 'st_size', 'st_mtime_ns'},
                        'invalid stat-bound artifact provenance')
            if unit['scope'] == 'canonical-local':
                descriptor = unit['descriptor']
                canonical = digest(json.dumps(descriptor, sort_keys=True, separators=(',', ':')).encode())
                require(canonical == unit['canonical_id'] == unit['effective_metadata'], 'descriptor identity mismatch')
                require(descriptor['compiler'] == policy['rustc_identity'], 'local descriptor compiler identity mismatch')
                positions = []
                option_end = expected.index('--') if '--' in expected else len(expected)
                for index, argument in enumerate(expected[:option_end]):
                    if argument == '-C' and index + 1 < option_end and expected[index + 1].startswith('metadata='):
                        positions.append((index + 1, 'metadata='))
                    elif argument.startswith('-Cmetadata='):
                        positions.append((index, '-Cmetadata='))
                require(len(positions) == 1, 'ambiguous local metadata argument')
                index, prefix = positions[0]
                require(expected[index] == prefix + unit['incoming_metadata'], 'incoming salt provenance mismatch')
                expected[index] = prefix + canonical
                require(canonical not in canonical_units or canonical_units[canonical] == descriptor,
                        'canonical identity collision')
                require(canonical not in canonical_incoming or canonical_incoming[canonical] == unit["incoming_metadata"],
                        "distinct incoming Cargo units collide in one canonical descriptor")
                canonical_incoming[canonical] = unit["incoming_metadata"]
                canonical_units[canonical] = descriptor
                local_replacements += 1
            else:
                require(unit['scope'] == 'cargo-original' and unit['incoming_metadata'] == unit['effective_metadata'],
                        'nonlocal compiler metadata was changed')
        else:
            probe_statuses[finishes[0]['returncode']] += 1
        require(expected == row['effective_argv'] == row['argv'], 'unrecorded compiler argument mutation')
        require(row['effective']['OSDK_BUILD_USERNAME'] == policy['embedded_builder']['username'] and
                row['effective']['OSDK_BUILD_HOSTNAME'] == policy['embedded_builder']['hostname'],
                'embedded builder override mismatch')
    target_rows = [row for row in rows if 'x86_64-unknown-none' in row['effective_argv']]
    require(target_rows and canonical_units, 'missing freestanding/canonical compiler units')
    require(all(flag in row['effective_argv'] for row in target_rows), 'freestanding call lacks canonical map')
    return {'schema': policy['schema'], 'compiler_calls': len(rows), 'unique_invocation_pids': len(set(pids)),
            'producer_ledger_rows': len(ledger), 'started_rows': len(rows), 'completed_rows': len(rows),
            'local_metadata_replacements': local_replacements, 'canonical_local_units': canonical_units,
            'compiler_unit_scopes': dict(scopes), 'freestanding_calls': len(target_rows),
            'remap_insertions': remap_insertions, 'query_probe_statuses': dict(probe_statuses),
            'all_cargo_unit_completions_zero': True, 'all_invocations_exactly_bound_to_start_and_completion': True,
            'all_arguments_preserved_except_recorded_metadata_and_remap': True,
            'artifact_provenance_scope': 'Completed successful producer plus device/inode/size/mtime; not immutable content.'}


def boot(record, serial, originals):
    require(record['raw_exit_code'] == record['recorder_exit_code'] == 33 and record['timed_out'] is False and
            record['stage'] == 'complete', 'actual QEMU did not pass')
    require(len(serial) == record['serial_size'] and digest(serial) == record['serial_sha256'], 'serial bytes changed')
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', serial.decode(errors='replace'))
    markers = ['OSTD initialized. Preparing components.', 'TRILLIONNIUM_A01_INIT_BEGIN',
               'TRILLIONNIUM_A01_CPU_COUNT=1', 'Successfully booted.', 'TRILLIONNIUM_A01_BOOT_OK']
    require(all(marker in clean for marker in markers), 'actual guest marker missing')
    fatal = ['panicked at', 'An uncaught panic occurred:', 'Uncaught panic:',
             'unknown panic payload! (fatal panic handling error', 'Non-resettable panic!',
             'The panic handler panicked', 'Panicked in `PanicGuard`, aborting the system']
    require(not any(marker in clean for marker in fatal), 'actual guest panic')
    for option, info in record['artifacts'].items():
        path = 'normalized-cloud/' + info['path'].split('/normalized-cloud/', 1)[1]
        require(path in originals and len(originals[path]) == info['size'] and digest(originals[path]) == info['sha256'],
                'retained actual snapshot changed: ' + option)
    return {'passed': True, 'raw_qemu_exit': 33, 'serial_sha256': digest(serial), 'serial_bytes': len(serial),
            'markers': markers, 'scope': 'Actual recorded guest acceptance, rechecked from retained bytes offline.'}


def execution_records(policy, environment_log):
    require(policy['schema'] == 'a01-component-path-projection/4', 'wrong projection schema')
    require(type(policy['execution']['cargo_build_jobs']) is int and policy['execution']['cargo_build_jobs'] == 1,
            'policy did not select one Cargo job')
    lines = [line for line in environment_log.decode().splitlines() if line.startswith('CARGO_BUILD_JOBS=')]
    require(lines == ['CARGO_BUILD_JOBS=1'], 'actual child environment did not retain exactly one Cargo job')
    require('commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48' in policy['rustc_version'] and
            digest(policy['rustc_version'].encode()) == policy['rustc_identity'], 'fixed nightly identity mismatch')
    return {'policy_jobs': 1, 'actual_child_jobs': 1,
            'recorded_caller_jobs': policy['execution'].get('caller_cargo_build_jobs'),
            'fixed_nightly_identity_verified': True}


def compare_cases(left, right, left_inputs, right_inputs):
    require(left['source_commit'] == right['source_commit'], 'producer differs')
    require(left['actual_host'] == right['actual_host'], 'same-host identity differs')
    require(left['real_root'] != right['real_root'], 'actual source roots must differ')
    for field in ('virtual_root', 'profile_code_sha256', 'components_sha256', 'canonical_local_units'):
        require(left[field] == right[field], 'case proof differs: ' + field)
    options = ('-kernel', '-initrd', '-bios')
    require(set(left_inputs) == set(right_inputs) == set(options), 'missing binary input type')
    require(all(type(left_inputs[o]) is bytes and type(right_inputs[o]) is bytes for o in options), 'comparison needs complete input bytes')
    equality = {option: left_inputs[option] == right_inputs[option] for option in options}
    return {'passed': all(equality.values()), 'complete_input_bytes_equal': equality,
            'scope': 'Same-host complete input bytes only; no cross-host or immutable environment acceptance.'}
