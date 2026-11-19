#!/usr/bin/env python3
"""Replay exact source/evidence bytes; never call the host binder, compiler or VM."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
LIVE = '/home/qq/work/p4-native-exit-vm260-binding-evidence-5cd1-20261119-r1/'
ORIGINAL = '/home/qq/work/p4-native-exit-vm260-binding-evidence-11ea-20261119-r3/'
RETIRED = {'LoadState': 'not-found', 'ActiveState': 'inactive', 'SubState': 'dead',
           'MainPID': '0', 'ControlGroup': '', 'InvocationID': ''}
ACTUAL = {
    'execution/HELD-BINDING.json': (25566, 'b3c406e7cab11fc9eba2a213880e0a615eaaaab36b59f72c8095bb62e7bff9ea'),
    'execution/BINDING-RESULT.json': (6127, 'fa19db074891780c2245de844ed028b5e7c27172533157e7f79806442eb4d41e'),
    'execution/BINDING-TERMINAL.json': (13896, '62cfa4afef97c6c9adca17d0d5169225cf42bd6e7906d4a76bd754688a903fd0'),
    'history/BINDING-RESULT.json': (2893, 'f7f720a84401dea762365b8bdc4ca0bf625db953121fc4fc651528333b053aa5'),
    'history/BINDING-TERMINAL.json': (11105, 'aa2a2edc50ee4ed91276603630881d54be82c7ee33384ee842b46f53cae8adea'),
}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def read(name):
    relative = PurePosixPath(name)
    need(not relative.is_absolute() and '..' not in relative.parts
         and str(relative) == name, 'canonical relative packet path')
    path = ROOT / name
    info = path.lstat()
    need(path.resolve() == path and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
         and info.st_size <= 2 * 1024 ** 2, 'bounded ordinary packet file')
    return path.read_bytes()


def decoded(body):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON value')
    return json.loads(body, object_pairs_hook=pairs, parse_constant=constant)


def pin(name, row):
    body = read(name)
    need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'exact bytes: ' + name)
    return body


def main():
    inventory = {}
    for line in read('FILES.sha256').decode('ascii').splitlines():
        digest, name = line.split('  ', 1)
        need(name not in inventory and len(digest) == 64, 'unique complete file inventory')
        need(sha(read(name)) == digest, 'packet digest: ' + name)
        inventory[name] = digest
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}
    need(actual == set(inventory) | {'FILES.sha256'}, 'exact packet inventory')
    manifest = decoded(read('MANIFEST.json'))
    need(manifest['schema'] == 'pocket4-native-exit-config-binding-publication-v1', 'publication schema')
    need({row['path'] for row in manifest['files']} == actual - {'MANIFEST.json', 'FILES.sha256'}
         and len(manifest['files']) == len(actual) - 2, 'complete manifest members')
    for row in manifest['files']:
        pin(row['path'], row)
    for name, (size, digest) in ACTUAL.items():
        need(len(read(name)) == size and sha(read(name)) == digest, 'unaltered original actual record')
    frozen = decoded(read('FROZEN-INPUT-MANIFEST.json'))
    staging = decoded(read('STAGED-INPUTS.json'))
    need(frozen['host'] == staging['host'] == 'ai395' and frozen['target_uid'] == 1000,
         'same ordinary original target host')
    pin('FROZEN-INPUT-MANIFEST.json', staging['input_manifest'])
    need(staging['state'] == 'STAGED_READBACK_PASS_NOT_EXECUTED'
         and staging['binding_or_VM_started'] is False, 'staging remains an earlier non-execution record')
    expected = {row['path']: row for row in frozen['files']}
    need(len(expected) == 4 and set(expected) == {LIVE + n for n in
         ('inputs/bind_full.py', 'inputs/run_binding.py', 'inputs/KNOWN-INPUTS.json', 'full-durable-terminal.json')},
         'exact four reviewed live inputs')
    for row in frozen['files']:
        pin('candidate/' + row['relative_path'], row)
    need(read('original/KNOWN-INPUTS.json') == read('candidate/inputs/KNOWN-INPUTS.json')
         and read('original/full-durable-terminal.json') == read('candidate/full-durable-terminal.json'),
         'original full anchors and durable response unchanged')
    binding = decoded(read('execution/HELD-BINDING.json'))
    result = decoded(read('execution/BINDING-RESULT.json'))
    terminal = decoded(read('execution/BINDING-TERMINAL.json'))
    outer = decoded(read('execution/OUTER-DURABLE-STATUS.json'))
    launch = decoded(read('execution/LAUNCH.json'))
    need(outer['state'] == 'succeeded' and outer['exit_code'] == 0
         and outer['job_id'] == launch['job']['id'] == '1a1f3241531-ffbe-ca5'
         and outer['output_complete'] is True and outer['output_durable'] is True
         and outer['terminal_publication_confirmed'] is True
         and outer['timed_out'] is False and outer['cancelled'] is False,
         'actual authoritative durable completion')
    runner = expected[LIVE + 'inputs/run_binding.py']
    need(launch['job']['executable'] == frozen['entrypoint']['executable'] == '/usr/bin/python3'
         and launch['job']['args'] == frozen['entrypoint']['args'] ==
         ['-I', '-B', runner['path'], 'manager', runner['sha256']], 'one reviewed original manager invocation')
    need(result['state'] == 'PASS' and terminal['passed'] is True
         and terminal['systemd_run_exit'] == 0 and terminal['systemd_run_actual_reaped'] is True
         and terminal['waitid'] == {'pid': terminal['systemd_run_pid'], 'code': 1, 'status': 0},
         'actual worker/manager success and PIDFD reap')
    pin('execution/HELD-BINDING.json', result['binding'])
    need(result['binding'] == terminal['binding'], 'same complete binding output')
    pin('execution/BINDING-RESULT.json', terminal['worker_result'])
    before = result['inputs_before']
    need(before == result['inputs_after'] == terminal['inputs_before'] == terminal['inputs_after']
         and len(before) == len(staging['files']) == 4
         and {row['path']: row for row in before} == {row['path']: row for row in staging['files']},
         'complete raw input F9/byte bookends')
    for row in before:
        need(row['path'] in expected and all(row[k] == expected[row['path']][k]
             for k in ('bytes', 'sha256')), 'actual executed inputs equal reviewed source')
    need(result['input_bookends_unchanged'] is True and terminal['input_bookends_unchanged'] is True,
         'actual input bookend result')
    need(terminal['original_serials_reacquired'] is True
         and terminal['serials_before'] == terminal['serials_after'] == result['binding_serials']
         == binding['binding_time_original_serials'] and binding['binding_time_serials_released'] is True,
         'original serial identity, reacquisition and release')
    need(terminal['unit_retirement']['fields'] == RETIRED
         and terminal['unit_retirement']['cgroup_absent'] is True, 'actual unit/cgroup retirement')
    need(result['admission']['limits'] == {'cpu.max': '200000 100000', 'memory.high': '2684354560',
         'memory.max': '3221225472', 'memory.swap.max': '0', 'pids.max': '128'}
         and result['admission']['affinity'] == [22, 23]
         and result['resource_admission']['memory_available'] >= 15 * 1024 ** 3
         and result['resource_admission']['disk_free'] >= 32 * 1024 ** 3
         and result['resource_final']['memory_available'] >= 12 * 1024 ** 3
         and result['resource_final']['disk_free'] >= 32 * 1024 ** 3, 'actual original resource contract')
    events = dict(line.split() for line in result['cgroup_final']['memory.events'].splitlines())
    need(events['oom'] == events['oom_kill'] == '0'
         and result['cgroup_final']['memory.swap.current'] == '0', 'actual no-OOM/no-swap outcome')
    retired = decoded(read('execution/INDEPENDENT-RETIREMENT.json'))
    need(retired['state'] == 'PASS_INDEPENDENT_READONLY_RETIREMENT'
         and retired['unit_status'] == RETIRED and retired['cgroup_absent'] is True
         and all(row['proc_lock_rows'] == [] for row in retired['serial_observations']),
         'independent subsequent retirement observation')
    need(binding['state'] == 'HELD_COMPLETE_FULL_BOUND_VM_NOT_AUTHORIZED'
         and binding['release'] == '6.18.64-p4ctx6182' and binding['actual_full_evidence_verified'] is True
         and binding['all_final_named_F9_bookends_equal'] is True,
         'complete full binding retains its launch hold')
    need(binding['source']['members'] == 97316
         and binding['source']['whole_regular_source_bodies_read'] == 91180
         and binding['modules']['built_module_count'] == binding['modules']['staged_module_count'] == 6797,
         'complete source and module scope')
    need(binding['whole_file_reads'] == result['binding_whole_file_reads'] == 104872
         and binding['body_bytes_read'] == result['binding_body_bytes_read'] == 11723017383,
         'actual complete binding I/O counts')
    config = binding['generated_configuration']
    pin('fixtures/full.config', config['actual_full_config'])
    pin('fixtures/autoconf.h', config['pin'])
    for row in config['Kconfig_semantic_sources']:
        relative = row['path'].split('/source/linux-6.18.64/', 1)[1]
        pin('fixtures/' + relative, row)
    need(config['compared_CONFIG_macro_count'] == 10145
         and config['all_generated_CONFIG_macros_match_full_config'] is True
         and config['HEX_spelling_normalizations'] == [{'symbol': 'CONFIG_MTD_NAND_DISKONCHIP_PROBE_ADDRESS',
              'config_value': '0', 'generated_value': '0x0'}], 'one source-proven HEX representation difference')
    previous = decoded(read('history/BINDING-RESULT.json'))
    previous_terminal = decoded(read('history/BINDING-TERMINAL.json'))
    need(previous['state'] == 'FAILED' and previous['error'] ==
         "BindingError('complete generated autoconf does not match actual full config')"
         and previous_terminal['passed'] is False and previous_terminal['systemd_run_exit'] == 1,
         'original failed execution remains failed')
    for value in (binding, result, terminal, previous, previous_terminal):
        need(value['native_exit_abi_qualified'] is False
             and value['production_android_runtime_qualified'] is False, 'no new ABI or production credit')
    for value in (result, terminal, previous, previous_terminal):
        need(value['compiler_invocations'] == value['VM_invocations'] == 0, 'no compiler or VM execution')
    need(binding['VM_executed'] is False and binding['launch_assessment_performed'] is False
         and binding['new_native_exit_C_fixture_created'] is False, 'new fixture remains outstanding')
    catalog = decoded(read('history/VM-CATALOG-r3-DRAFT.json'))
    need(len(catalog['cases']) == 32 and all(row['status'] == 'NOT_IMPLEMENTED_NOT_RUN'
         for row in catalog['cases']), 'original native-exit plan has no execution credit')
    subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'test_config_binding.py')],
                   check=True, cwd=ROOT, timeout=30)
    print(json.dumps({'state': 'PASS_SOURCE_REPLAY_ONLY', 'packet_files': len(inventory),
        'original_failure_reproduced': True, 'source_controls_passed': 12,
        'recorded_actual_full_binding_passed': True, 'compared_CONFIG_macros': 10145,
        'complete_binding_reexecuted_by_this_command': False, 'VM_executed': False,
        'native_exit_abi_qualified': False, 'production_ready': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
