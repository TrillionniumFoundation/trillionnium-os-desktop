#!/usr/bin/env python3
"""Offline source replay and optional no-load normal compiler checks.

This script never launches a guest, installs a kernel, or loads a policy.
Recorded VM results remain historical evidence, not fresh executions.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def need(value, message):
    if not value:
        raise RuntimeError(message)


def read_json(path):
    return json.loads((ROOT / path).read_bytes())


def pin(path):
    path = Path(path)
    metadata = path.lstat()
    need(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, 'regular single-link file required: ' + str(path))
    data = path.read_bytes()
    need(len(data) < 2 * 1024**2 and b'\0' not in data, 'bounded text source required: ' + str(path))
    data.decode('utf-8')
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def run(argv, timeout=60):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    need(len(result.stdout) + len(result.stderr) < 2 * 1024**2, 'command output bound')
    return result


def terminal(value):
    need(value['state'] == 'succeeded' and value['exit_code'] == 0 and value['output_complete'] and
         value['output_durable'] and not value['timed_out'] and not value['cancelled'], 'terminal H evidence differs')


def check_sources():
    inventory = read_json('inventory.json')
    need(inventory['schema'] == 'p4ctx3-source-only-inventory-v1', 'inventory schema')
    entries = inventory['files']
    expected = {item['path'] for item in entries}
    need(len(entries) == len(expected) and 'inventory.json' not in expected, 'inventory duplicate or self-reference')
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob('*') if path.is_file() or path.is_symlink()}
    need(actual == expected | {'inventory.json'}, 'unlisted or missing capsule file')
    denied = {'.ko', '.o', '.so', '.bin', '.apk', '.jar', '.class', '.log', '.stdout', '.stderr', '.cpio'}
    for item in entries:
        name = Path(item['path'])
        need(not name.is_absolute() and '..' not in name.parts and name.suffix not in denied, 'non-source member')
        need(pin(ROOT / name) == {key: item[key] for key in ('bytes', 'sha256')}, 'inventory pin differs: ' + str(name))
        if name.suffix == '.py':
            ast.parse((ROOT / name).read_text(), filename=name.as_posix())
    scope = read_json('scope.json')
    need(scope['kernel_release'] == '7.0.14-p4ctx3' and scope['combined_context_cases_passed'] == 47 and
         scope['inactive_provider_cases_passed'] == 12 and scope['full_module_count'] == 6901, 'qualification scope differs')
    for key in ('host_deployment_performed', 'Android_started', 'production_acceptance',
                'original_CP3A_client_integration_qualified', 'grant_runtime_rerun_on_p4ctx3',
                'capsule_contains_kernel_or_module_binaries', 'capsule_contains_raw_logs', 'capsule_contains_APKs'):
        need(scope[key] is False, 'scope widened: ' + key)
    for key in ('host_kernel_installations', 'host_module_loads', 'host_policy_loads', 'host_reboots', 'guest_disks', 'guest_external_nics'):
        need(scope[key] == 0, 'host or external guest side effect claim changed')
    provenance = read_json('kernel/provenance.json')
    need(provenance['recorded_upstream_tag'] == 'Ubuntu-7.0.0-43.43' and
         provenance['recorded_upstream_commit'] == 'f53b359683af7918c5436499948763cb726d5082', 'original version changed')
    need(provenance['p4ctx3_configuration_delta'] == {'CONFIG_LOCALVERSION': {'after': '"-p4ctx3"', 'before': '"-p4ctx1"'}},
         'candidate configuration widened')
    need(provenance['p4ctx3_whole_source_before']['semantic_sha256'] == provenance['p4ctx3_whole_source_after']['semantic_sha256'],
         'source changed during build')
    need(provenance['whole_original_source_unchanged'], 'original source changed')
    base = read_json('kernel/p4ctx1-framework-pins.json')
    need(len(base) == 22 and len({row['path'] for row in base}) == 22 and sum(row['before'] is None for row in base) == 4,
         'original framework closure differs')
    need(pin(ROOT / 'kernel/p4ctx1-context-provider.patch') == {
        'bytes': 24176, 'sha256': '1810edbc8ea65e9cccd4ba6dfead6403ec3e4ac327e7bed952bb0fd76cfb140f'}, 'original framework patch changed')
    need(pin(ROOT / 'kernel/p4ctx3-typed-scm.patch') == {
        'bytes': 15935, 'sha256': '58b33c63587b7adf4846a354fdcf6d80a124d3fcac6144a85649ab0ee566c827'}, 'final SCM patch changed')
    delta = read_json('kernel/p4ctx3-delta-pins.json')
    need(len(delta) == 9 and len({row['path'] for row in delta}) == 9, 'final source delta differs')
    need(sorted(row['path'] for row in delta) == sorted(provenance['p4ctx3_changed_paths']), 'build and patch source scope differ')
    need(shutil.which('patch') is not None, 'normal patch command required')
    with tempfile.TemporaryDirectory(prefix='p4ctx3-source-replay-') as directory:
        temporary = Path(directory)
        for row in delta:
            source = ROOT / 'kernel/p4ctx1-preimages' / row['path']
            need(pin(source) == {'bytes': row['before_bytes'], 'sha256': row['before']}, 'original preimage differs')
            target = temporary / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        result = run(['patch', '--batch', '--fuzz=0', '--forward', '--no-backup-if-mismatch', '-p1',
                      '-d', str(temporary), '-i', str(ROOT / 'kernel/p4ctx3-typed-scm.patch')])
        need(result.returncode == 0 and 'offset' not in result.stdout and 'fuzz' not in result.stdout,
             'exact patch replay failed: ' + result.stdout + result.stderr)
        for row in delta:
            need(pin(temporary / row['path']) == {'bytes': row['after_bytes'], 'sha256': row['after']},
                 'replayed postimage differs: ' + row['path'])
        need({p.relative_to(temporary).as_posix() for p in temporary.rglob('*') if p.is_file()} == {r['path'] for r in delta},
             'patch added unexpected files')
    probe_pins = read_json('probe/source-pins.json')
    need(len(probe_pins) == 13 and len({row['path'] for row in probe_pins}) == 13, 'probe source closure differs')
    for row in probe_pins:
        need(pin(ROOT / 'probe' / row['path']) == {key: row[key] for key in ('bytes', 'sha256')}, 'probe source pin differs')
    return len(entries)


def check_recorded_evidence():
    build = read_json('qualification/build-summary.json')
    for name in ('full', 'normal_probe'):
        terminal(build[name]['H'])
        need(build[name]['passed'] and build[name]['inputs_unchanged'], 'recorded normal build failed')
        need(all(row['pidfd_exit'] for row in build[name]['commands']), 'recorded build child remained')
    need([row['exit_code'] for row in build['normal_probe']['commands']] == [0,0,0,64,0,0,64,0,0,64,0,0],
         'ordinary probe build or wrong-PID control differs')
    need(all(row['exit_code'] == 0 and row['child_reaped'] and not row['timed_out'] for row in build['full']['commands']),
         'full Kbuild command failed')
    modules = build['full']['complete_modules']
    need(modules['module_count'] == 6901 and modules['kernel_release'] == '7.0.14-p4ctx3' and
         modules['exact_modules_order_complete'] and modules['all_modules_new_release'], 'complete module qualification differs')
    runtime = read_json('qualification/runtime-summary.json')
    cases = read_json('qualification/case-comparison.json')
    need(len(cases['combined_cases']) == 47 and len({r['name'] for r in cases['combined_cases']}) == 47, 'combined case set')
    need(len(cases['inactive_cases']) == 12 and len({r['name'] for r in cases['inactive_cases']}) == 12, 'inactive case set')
    for name, count, failures in (('baseline',47,6), ('previous',47,2), ('candidate',47,0), ('inactive',12,0)):
        arm = runtime['arms'][name]
        terminal(arm['H'])
        summary = arm['summary']
        need(summary['cases'] == count and summary['passed'] == count - failures and summary['failed'] == failures and
             summary['setup_error'] == 0 and not summary['production_acceptance'] and not summary['Android_started'], 'recorded case totals')
        need(not arm['production_acceptance'] and arm['owned_unit_retired'] and arm['actual_qemu_exited'] and arm['cgroup_retired'] and
             not arm['after_qemu'] and arm['inputs_unchanged'] and arm['host_identity_unchanged'] and arm['host_before'] == arm['host_after'],
             'recorded runtime retirement differs')
        need(arm['memory_events'] and all(all(e[k] == '0' for k in ('oom', 'oom_kill', 'oom_group_kill')) for e in arm['memory_events']),
             'runtime memory event differs')
        selected = cases['inactive_cases'] if name == 'inactive' else [r[name] for r in cases['combined_cases']]
        need(sum(not r['passed'] for r in selected) == failures, 'case matrix differs from recorded summary')
        need(arm['expected_failure_comparison_only'] == (name in ('baseline','previous')), 'comparison mislabeled as qualification')
    boot = runtime['arms']['candidate']['boot']
    need(boot['kernel'] == '7.0.14-p4ctx3' and boot['selinux_enforcing'] == '1' and
         boot['lsm'].index('apparmor') < boot['lsm'].index('selinux'), 'combined boot identity differs')
    inactive = runtime['arms']['inactive']['boot']
    need('selinux' not in inactive['lsm'] and inactive['selinux_policy_bytes'] == 0 and inactive['selinux_enforcing'] == 'inactive',
         'inactive boot used a SELinux provider')
    retirement = read_json('qualification/retirement-summary.json')
    for name in ('full', 'runtime'):
        terminal(retirement[name]['H'])
        need(retirement[name]['verification']['passed'] and not retirement[name]['verification']['remaining_pids'], 'independent retirement failed')
        need(all(not row['same_process_alive'] for row in retirement[name]['verification']['old_processes']), 'old process still alive')
    final = retirement['runtime']['verification']
    need(final['lock_inode'] == 41719533 and final['original_lock_reacquired'] and not final['remaining_qemu_pids'] and
         len(final['cgroups_absent']) == 4, 'original lock or four-generation retirement differs')


def compile_probe():
    need(shutil.which('gcc') and shutil.which('readelf'), 'normal gcc and readelf required')
    commands = []
    with tempfile.TemporaryDirectory(prefix='p4ctx3-probe-build-') as directory:
        for suffix in ('p4ctx1', 'p4ctx2', 'p4ctx3'):
            executable = Path(directory) / suffix
            argv = ['gcc', '-std=c11', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
                    '-Wno-misleading-indentation', '-Wl,-z,noexecstack', '-I', str(ROOT / 'probe/include'),
                    '-DEXPECTED_RELEASE="7.0.14-' + suffix + '"', '-o', str(executable), str(ROOT / 'probe/context_probe.c')]
            built = run(argv, 120)
            need(built.returncode == 0, 'normal probe compilation failed: ' + built.stderr)
            elf = run(['readelf', '-lW', str(executable)])
            stack = [line for line in elf.stdout.splitlines() if 'GNU_STACK' in line]
            need(elf.returncode == 0 and 'INTERP' not in elf.stdout and len(stack) == 1 and ' RW ' in stack[0] and ' RWE ' not in stack[0],
                 'static nonexecutable-stack executable required')
            guarded = run([str(executable)], 5)
            need(guarded.returncode == 64, 'wrong-PID guard must reject execution before any mount')
            commands.append({'release': '7.0.14-' + suffix, 'compiler_exit': built.returncode,
                             'elf_check_exit': elf.returncode, 'outside_guest_exit': guarded.returncode})
    return commands


def compile_policies():
    need(shutil.which('secilc') and shutil.which('apparmor_parser'), 'normal secilc and apparmor_parser required')
    with tempfile.TemporaryDirectory(prefix='p4ctx3-policy-build-') as directory:
        p = Path(directory)
        (p / 'apparmor-parser.conf').write_text('')
        selinux = run(['secilc', '-M', 'true', '-U', 'deny', '-c', '30', '-o', str(p / 'selinux.bin'),
                       '-f', str(p / 'file_contexts'), str(ROOT / 'probe/vocabulary.cil'), str(ROOT / 'probe/context-diagnostic.cil')])
        need(selinux.returncode == 0, 'normal SELinux policy compilation failed: ' + selinux.stderr)
        apparmor = run(['apparmor_parser', '--config-file', str(p / 'apparmor-parser.conf'), '--skip-kernel-load', '--skip-cache',
                        '--features-file', str(ROOT / 'probe/apparmor.features'), '--jobs', '1', '--max-jobs', '1',
                        '--ofile', str(p / 'apparmor.bin'), str(ROOT / 'probe/context-apparmor.profile')])
        need(apparmor.returncode == 0, 'normal AppArmor no-load compilation failed: ' + apparmor.stderr)
    return {'selinux_exit': 0, 'apparmor_no_load_exit': 0, 'neverallow_disabled': False, 'host_policy_loads': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile-probe', action='store_true', help='normal static gcc build and wrong-PID guard for all three release macros')
    parser.add_argument('--compile-policies', action='store_true', help='normal secilc and AppArmor compilation with kernel loading disabled')
    options = parser.parse_args()
    count = check_sources()
    check_recorded_evidence()
    result = {'passed': True, 'source_files_verified': count, 'exact_patch_postimages_verified': 9,
              'historical_combined_cases': {'p4ctx1': [41,6], 'p4ctx2': [45,2], 'p4ctx3': [47,0]},
              'historical_inactive_cases': [12,0], 'fresh_VM_runs': 0, 'host_policy_loads': 0,
              'host_module_loads': 0, 'Android_started': False, 'production_acceptance': False}
    if options.compile_probe:
        result['fresh_normal_probe_compiles'] = compile_probe()
    if options.compile_policies:
        result['fresh_normal_policy_compiles'] = compile_policies()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
