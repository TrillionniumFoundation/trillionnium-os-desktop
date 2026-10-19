#!/usr/bin/env python3
"""Read-only original CPU/SMP evidence review, pinned to git104.

Reuses only function definitions from the prior independent A04 byte parser,
whose hash is pinned by its already completed receipt. It never executes that
script's main, imports project modules, or invokes any producer/test/toolchain.
"""
import ast
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess

BASE = Path('/workspace/scratch/499c7902de8e')
PRODUCT = BASE / 'r12-g1c'
E = BASE / 'r12-evidence'
OUT = E / 'g1c-review'
HEAD = '104204016dcdea57ab73c091b1edd13008ae9a19'
TREE = '179b076747d19c3e07ee19a665e3968c33c598ce'
KERNEL = '1bdc27f45afb2789447473cdf100a8fd67c84111bcec650a1fa96c18edb6163b'
ORIGINAL = '86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3'
BIOS = '1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735'
QEMU = '8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854'
RUNNER = 'tests/organ_backend/run_cpu_config_settlement.py'
ONE = 'tests/organ_backend/run_candidate_matrix.py'
TWO = 'tests/organ_backend/smp2/run_parallel_candidate.py'
FILES, SOURCES = {}, {}
parser_file = OUT / 'capture_a04_review.py'
parser_bytes = parser_file.read_bytes()
parser_sha = hashlib.sha256(parser_bytes).hexdigest()
assert parser_sha == json.loads((OUT / 'a04-combined-review.json').read_text())['reviewer_program_sha256']
names = {'must', 'sha', 'read', 'digest', 'strict', 'js', 'canonical', 'src', 'literal',
         'pinned', 'clean_lines', 'elf', 'newc', 'compare_injection', 'identity'}
nodes = [node for node in ast.parse(parser_bytes).body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(nodes) == len(names)
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<pinned independent read-only byte parsers>', 'exec'), globals())


def at_source_or_artifact(path):
    path = Path(path)
    if path.is_relative_to(PRODUCT):
        return src(str(path.relative_to(PRODUCT)))
    return read(path)


def stage(name):
    path = E / 'local-cpu-config-checks' / (name + '.attempt.json')
    result = js(path)
    identity(result)
    must(result['name'] == name and result['exit_code'] == 0, 'stage failure: ' + name)
    for channel in ('stdout', 'stderr'):
        pinned(result[channel], result[channel + '_sha256'])
    return result


def qemu_args(kernel, image, vcpus, nic=False):
    argv = ['/usr/bin/qemu-system-x86_64', '-kernel', str(kernel), '-initrd', str(image),
            '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
            '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', '/usr/share/seabios/bios-256k.bin',
            '-m', '512M', '-smp', str(vcpus), '-nodefaults', '-no-user-config', '-no-reboot', '-nographic',
            '-display', 'none', '-monitor', 'none', '-serial', 'stdio']
    if nic:
        argv += ['-nic', 'none']
    return argv + ['-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']


def review_config(period, mode):
    name = f'cpu-config-{period}-{mode}'
    p = E / ('local-' + name)
    receipt = js(p / 'result.json')
    inputs = js(p / 'inputs.json')
    attempt = stage(name)
    bound = 1.2 if period == 100000 else 52.0
    must(receipt['inputs'] == inputs and receipt['passed'] is True and receipt['qemu_exit'] == 33
         and receipt['timed_out'] is False and receipt['inputs_unchanged'] is True
         and receipt['changed_inputs'] == {}, 'config original verdict failed')
    must(inputs['kernel_sha256'] == KERNEL and inputs['quota_us'] == 1000 and inputs['period_us'] == period
         and inputs['mode'] == mode and inputs['duration_seconds'] == 4 and inputs['max_cpu_percent'] == bound
         and inputs['minimum_unlimited_percent'] == 70.0 and inputs['max_serial_bytes'] == 8*1024*1024,
         'config acceptance threshold drift')
    must(inputs['single_vcpu'] is True and inputs['network'] is False and inputs['data_disks'] is False
         and inputs['hos2_qualification'] is False, 'config qualification drift')
    for key, record in {**inputs['input_files'], 'input_receipt': receipt['input_receipt']}.items():
        data = at_source_or_artifact(record['path'])
        must(len(data) == record['size'] and sha(data) == record['sha256'], 'input byte mismatch: ' + key)
    original_source = src('tests/organ_backend/cpu_config_settlement_probe.c')
    must(original_source.count(b'__KERNEL_SHA__') == 1
         and read(p/'probe.c') == original_source.replace(b'__KERNEL_SHA__', KERNEL.encode()),
         'compiled config source not exact original variant')
    binary = pinned(p/'probe', inputs['probe_sha256'])
    header = elf(binary)
    must(header['machine'] == 62 and header['interpreter'] is None, 'config probe not static x86_64')
    must(read(p/'compile.log') == b'', 'unexpected config compile diagnostics')
    image = pinned(p/'initramfs.cpio.gz', inputs['initramfs_sha256'])
    injected = (f'if /bin/cpu-config-settlement --asterinas-disposable-guest {period} {mode} 4; then\n'
                '  echo "CPU_CONFIG_PROCESS_EXIT status=0"\nelse\n  probe_status=$?\n'
                '  echo "CPU_CONFIG_PROCESS_EXIT status=$probe_status"\n  exit "$probe_status"\nfi\n').encode()
    archive_check = compare_injection(ORIGINAL_ENTRIES, newc(image), injected,
        {'bin/cpu-config-settlement': (0o755, binary), '.hepta-disposable-guest': (0o400, (KERNEL+'\n').encode())})
    must(inputs['argv'] == qemu_args(E/'local-ordinary-candidate-final/product-kernel.elf', p/'initramfs.cpio.gz', 1, True),
         'actual frozen config QEMU argv differs')
    must(inputs['qemu_sha256'] == QEMU and inputs['bios_sha256'] == BIOS
         and inputs['original_initramfs_sha256'] == ORIGINAL, 'config pinned boot input differs')
    command = attempt['command']
    for flag, value in {'--expected-sha256': KERNEL, '--period-us': str(period), '--mode': mode}.items():
        must(command[command.index(flag)+1] == value, 'config actual CLI differs')
    raw = pinned(p/'serial.log', receipt['serial_sha256'])
    must(len(raw) == receipt['serial_bytes'] <= 8*1024*1024, 'config serial size differs')
    lines = clean_lines(raw)
    pattern = re.compile(r'CPU_CONFIG_SAMPLE label=(unlimited|read-only|same-value) wall_ns=([0-9]{1,20}) cpu_ns=([0-9]{1,20}) operations=([0-9]{1,20}) checksum=([0-9]{1,20})')
    markers = [line for line in lines if 'CPU_CONFIG_' in line or 'TRILLIONNIUM_A01_BOOT_OK' in line]
    expected_non_sample = [f'CPU_CONFIG_PARAMETERS quota_us=1000 period_us={period} mode={mode} seconds=4',
                          'CPU_CONFIG_STAT', 'CPU_CONFIG_COMPLETE', 'CPU_CONFIG_PROCESS_EXIT status=0', 'TRILLIONNIUM_A01_BOOT_OK']
    must(len(markers) == 7 and [markers[i] for i in (1,3,4,5,6)] == expected_non_sample, 'config exact marker event sequence differs')
    samples = []
    for index, label in ((0, 'unlimited'), (2, mode)):
        match = pattern.fullmatch(markers[index])
        must(match is not None and match[1] == label, 'config sample format differs')
        wall, cpu, operations, checksum = map(int, match.groups()[1:])
        must(all(0 < x < 2**64 for x in (wall,cpu,operations)) and checksum < 2**64, 'invalid sample values')
        samples.append({'label': label, 'wall_ns': wall, 'cpu_ns': cpu, 'operations': operations,
                        'checksum': checksum, 'cpu_percent': 100*cpu/wall})
    must(samples == receipt['samples'] and samples[0]['wall_ns'] >= 250000000
         and samples[1]['wall_ns'] >= 4000000000 and samples[0]['cpu_percent'] >= 70
         and samples[1]['cpu_percent'] <= bound, 'config original numeric thresholds fail')
    must(not re.search('CPU_CONFIG_BLOCKED|panicked at|Kernel panic|Uncaught panic|\\[PANIC\\]', '\n'.join(lines)), 'config failure in serial')
    return {'name': name, 'passed': True, 'unlimited': samples[0], 'capped': samples[1],
            'quota_us': 1000, 'period_us': period, 'declared_limit_percent': bound,
            'declared_unlimited_min_percent': 70, 'qemu_exit': 33, 'probe_process_exit': 0,
            'all_frozen_input_records_match_explicit_git104_or_retained_bytes': True,
            'inputs_sha256': digest(p/'inputs.json'), 'probe_sha256': sha(binary),
            'serial_sha256': sha(raw), 'initramfs': archive_check,
            'hos2_qualification': False, 'attempt_started_at': attempt['started_at'],
            'attempt_finished_at': attempt['finished_at']}


def review_parallel(vcpus):
    p = E / f'local-probe-{vcpus}vcpu'
    result = js(p/'result.json')
    attempt = stage(f'probe-{vcpus}vcpu')
    source_path = 'tests/organ_backend/' + ('cpu_cap_probe.c' if vcpus == 1 else 'smp2/parallel_cpu_probe.c')
    original = src(source_path)
    prior_marker = b'e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63'
    must(original.count(prior_marker) == 1 and read(p/'probe.c') == original.replace(prior_marker, KERNEL.encode()),
         '1-second leaf1000 variant differs from source104')
    must(read(p/'candidate_kernel.sha256') == (KERNEL+'\n').encode() and result['candidate_sha256'] == KERNEL,
         'candidate digest differs')
    binary = read(p/'probe')
    h = elf(binary)
    must(h['machine'] == 62 and h['interpreter'] is None, 'parallel probe not static x86_64')
    must(read(p/'compile.log') == b'', 'unexpected parallel compile diagnostics')
    image = pinned(p/'initramfs.cpio.gz', result['initramfs_sha256'])
    base = ORIGINAL_ENTRIES
    if vcpus == 2:
        base = []
        for name, fields, data in ORIGINAL_ENTRIES:
            if name == 'init':
                must(data.count(b'test "$cpu_count" -eq 1') == 1, 'original CPU count fixture changed')
                data = data.replace(b'test "$cpu_count" -eq 1', b'test "$cpu_count" -eq 2')
                fields = fields.copy()
                fields[6] = len(data)
            base.append((name, fields, data))
    image_check = compare_injection(base, newc(image), b'/bin/cpu-cap-probe --asterinas-disposable-guest\n',
        {'bin/cpu-cap-probe': (0o755, binary), '.hepta-disposable-guest': (0o400, (KERNEL+'\n').encode())})
    must(result['mode'] == 'leaf' and result['quota_us'] == 1000 and result['period_us'] == 100000
         and result['duration_seconds'] == 1 and result['max_cpu_percent'] == 3.0 and len(result['runs']) == 2,
         'parallel original input criteria differ')
    for flag, value in {'--expected-sha256': KERNEL, '--quota-us': '1000', '--mode': 'leaf', '--repeat': '2',
                        '--duration-seconds': '1', '--max-cpu-percent': '3'}.items():
        must(attempt['command'][attempt['command'].index(flag)+1] == value, 'parallel actual CLI differs')
    must(datetime.fromisoformat(FROZEN['frozen_at']) < datetime.fromisoformat(attempt['started_at']), 'probe not after frozen digest')
    must(result['host_cgroup_modified'] is False and result['guest_only'] is True
         and result['smp_qualified'] is False and result['hepta_hos2_qualified'] is False
         and result['source_pin'] == ORIGINAL, 'parallel scope drift')
    if vcpus == 2:
        must(result['configured_vcpus'] == result['parallel_pthreads'] == 2, 'parallel denominator differs')
    runs = []
    for index, reported in enumerate(result['runs'], 1):
        raw = read(p/f'serial-{index}.log')
        lines = clean_lines(raw)
        sample_lines = [line for line in lines if line.startswith('ORGAN_CPU_SAMPLE ')]
        must(len(sample_lines) == 2, 'parallel raw sample denominator differs')
        parsed = []
        for label, line in zip(('unlimited', 'one-percent-configured'), sample_lines):
            m = re.match(r'ORGAN_CPU_SAMPLE label=(\S+) wall_ns=(\d+) cpu_ns=(\d+) iterations=(\d+) checksum=', line)
            must(m is not None and m[1] == label, 'parallel raw sample malformed/out-of-order')
            wall, cpu, iterations = map(int, m.groups()[1:])
            must(0 < wall < 2**64 and 0 < cpu < 2**64 and 0 <= iterations < 2**64, 'parallel invalid numeric sample')
            parsed.append({'label':label, 'wall_ns':wall,'cpu_ns':cpu,'iterations':iterations})
        must(parsed == reported['samples'] and reported['index'] == index and reported['qemu_exit'] == 33
             and reported['guest_complete'] is True and reported['panic'] is False and reported['policy_rt'] is False,
             'parallel result does not match raw/actual QEMU')
        percents = [sample['cpu_ns']*100/sample['wall_ns'] for sample in parsed]
        must(round(percents[1],3) == reported['cpu_percent'] <= 3.0, 'parallel original cap threshold differs')
        if vcpus == 2:
            must(parsed[0]['cpu_ns']*100 > 145*parsed[0]['wall_ns'], 'two-vCPU baseline fails original strict >145 gate')
            must(all(x['iterations'] == 0 for x in parsed), 'original parallel counter field differs')
        else:
            must(all(x['iterations'] > 0 for x in parsed), 'one-vCPU workload inactive')
        completion = 'ORGAN_PROBE_COMPLETE'
        boot = 'TRILLIONNIUM_A01_BOOT_OK'
        configuration = 'ORGAN_CPU_CONFIG quota_us=1000 period_us=100000'
        verdict = 'ORGAN_CPU_VERDICT=INCONCLUSIVE_REQUIRES_TIMING_VALIDATION'
        for marker in (completion, boot, configuration, verdict):
            must(lines.count(marker) == 1, 'parallel marker not exact once')
        must(lines.index(sample_lines[0]) < lines.index(configuration) < lines.index(sample_lines[1])
             < lines.index(verdict) < lines.index(completion) < lines.index(boot), 'parallel marker order differs')
        must(not re.search('ORGAN_PROBE_BLOCKED|panicked at|Uncaught panic|Kernel panic|ORGAN_POLICY=RT_FIFO', '\n'.join(lines)),
             'parallel serial failure or unexpected policy')
        runs.append({'index': index, 'unlimited_cpu_percent': percents[0], 'capped_cpu_percent_exact': percents[1],
                     'reported_cpu_percent_rounded3': reported['cpu_percent'], 'raw_samples': parsed,
                     'qemu_exit': 33, 'guest_markers_exact_and_ordered': True,
                     'serial_bytes': len(raw), 'serial_sha256': sha(raw),
                     'two_vcpu_original_unlimited_gt145': (percents[0] > 145) if vcpus == 2 else None})
    return {'configured_vcpus': vcpus, 'parallel_pthreads': vcpus, 'mode': 'leaf', 'passed': True,
            'kernel_sha256': KERNEL, 'probe_sha256': sha(binary), 'initramfs': image_check,
            'two_vcpu_fixture_cpu_count_exactly_changed_from_1_to_2': vcpus == 2,
            'predeclared_max_cpu_percent': 3.0, 'runs': runs,
            'smp_qualified': False, 'hepta_hos2_qualified': False,
            'raw_probe_verdict': 'INCONCLUSIVE_REQUIRES_TIMING_VALIDATION',
            'original_one_vcpu_runner_baseline_gate': 'No explicit unlimited threshold in one-vCPU original runner; current raw baselines are independently reported.',
            'metadata_scope': 'Legacy candidate runner retains actual CLI in stage attempt, source-pinned generated C/image, kernel digest and raw serial; it does not retain the separate QEMU-input SHA/argv receipt used by CPU4. Review hashes original serial now and derives -smp from fixed source plus fixture. No stronger post-execution input fence is inferred.'}


SEQUENCE = js(E/'local-cpu-config-checks/sequence.json')
identity(SEQUENCE)
must(SEQUENCE['source_head_after'] == HEAD and SEQUENCE['source_tree_after'] == TREE
     and SEQUENCE['source_status_after'] == '' and SEQUENCE['all_original_stage_exit_codes_zero'] is True,
     'recorded source boundary differs')
for name, expected in SEQUENCE['source_files'].items():
    must(sha(src(name)) == expected, 'sequence source byte mismatch')
must(sha(src('.github/workflows/a06-kernel.yml')) == SEQUENCE['workflow_sha256'], 'workflow hash differs')
must('samples[0]["cpu_percent"] >= 70.0' in src(RUNNER).decode()
     and 'bound = 1.2 if period_us == 100000 else 52.0' in src(RUNNER).decode()
     and 'x["samples"][0]["cpu_ns"] * 100 > 145 * x["samples"][0]["wall_ns"]' in src(TWO).decode(),
     'original runner criteria no longer explicit')
PRODUCT_RECEIPT = js(E/'local-ordinary-candidate-final/result.json')
identity(PRODUCT_RECEIPT)
must(PRODUCT_RECEIPT['passed'] is True and PRODUCT_RECEIPT['kernel_elf_sha256'] == KERNEL
     and digest(E/'local-ordinary-candidate-final/result.json') == SEQUENCE['ordinary_product_receipt_sha256'],
     'ordinary producer binding differs')
PRODUCT_ELF = pinned(E/'local-ordinary-candidate-final/product-kernel.elf', KERNEL)
ORIGINAL_ENTRIES = newc(pinned(E/'local-full-bundle/original-initramfs.cpio.gz', ORIGINAL))
pinned('/usr/bin/qemu-system-x86_64', QEMU)
pinned('/usr/share/seabios/bios-256k.bin', BIOS)

TESTS = {}
for name in ('runner-tests', 'runner-tests-optimized'):
    r = stage(name)
    log = read(r['stderr']).decode()
    matches = re.findall(r'^(test_[a-z0-9_]+) \([^\n]+\) \.\.\. ok$', log, re.M)
    expected_names = sorted(n.name for n in ast.walk(ast.parse(src('tests/organ_backend/test_cpu_config_settlement.py')))
                            if isinstance(n, ast.FunctionDef) and n.name.startswith('test_'))
    must(sorted(matches) == expected_names and len(matches) == len(set(matches)) == 10
         and re.search(r'Ran 10 tests in [\d.]+s\n\nOK\n$', log), 'CPU10 test original log differs')
    TESTS[name] = {'count':10, 'names': matches, 'exit_code': 0, 'stderr_sha256': sha(log.encode())}
CONFIGS = [review_config(period, mode) for period in (100000,2000) for mode in ('read-only','same-value')]
must(len({row['probe_sha256'] for row in CONFIGS}) == 1, 'CPU4 not same frozen probe ELF')

BUILD = stage('smp2-build')
BUILD_FREEZE = stage('smp2-elf-and-freeze')
FROZEN = js(E/'local-cpu-config-checks/frozen-smp2-input.json')
must(FROZEN['kernel_sha256'] == KERNEL and SEQUENCE['smp2_kernel_sha256_frozen_before_probes'] == KERNEL,
     'SMP frozen ELF identity differs')
must(read(FROZEN['digest_source']) == (KERNEL+'  '+FROZEN['kernel']+'\n').encode(), 'original pre-probe SHA text differs')
must(pinned(FROZEN['saved_elf'], KERNEL) == PRODUCT_ELF, 'saved SMP2 ELF differs from ordinary product')
must(elf(PRODUCT_ELF)['machine'] == 3, 'QEMU multiboot ELF marker differs')
must(datetime.fromisoformat(BUILD['finished_at']) < datetime.fromisoformat(BUILD_FREEZE['started_at'])
     < datetime.fromisoformat(BUILD_FREEZE['finished_at']) < datetime.fromisoformat(FROZEN['frozen_at']),
     'SMP freeze chronology differs')
must(BUILD['command'] == ['bash','support/build/kernel.sh','kernel'] and BUILD['environment_overrides']['A01_SMP'] == '2',
     'not original SMP2 build command')
build_dir = E/'local-smp2-build'
for f in ('make-exit-code.txt','log-exit-code.txt','run-exit-code.txt'):
    must(read(build_dir/f) == b'0\n', 'SMP2 build original exit failed')
command = read(build_dir/'command.sh').decode()
must(' SMP=2 MEM=512M ENABLE_KVM=0 BOOT_PROTOCOL=multiboot INITRAMFS=on AUTO_TEST=none ' in command
     and 'CARGO_OSDK=/workspace/scratch/499c7902de8e/r12-cargo/bin/cargo-osdk' in command,
     'SMP original make/OSDK/TCG command differs')
environment = read(build_dir/'environment.log').decode()
must(HEAD in environment.splitlines() and 'commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48' in environment
     and 'commit-hash: 3efb1f477e99b42974b982d939fd100303cdf7db' in environment
     and 'e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506' in environment,
     'SMP original source/toolchain/lock environment differs')
build_source = js(build_dir/'source-inputs.json')
must(build_source['passed'] is True and build_source['errors'] == [] and build_source['checked_files'] == 118,
     'SMP bounded upstream source verification failed')
for path, expected in build_source['input_sha256'].items():
    must(sha(src('kernel/asterinas/'+path)) == expected, 'SMP source input differs from104')
for path, row in build_source['downstream_manifests'].items():
    must(sha(src('kernel/asterinas/'+path)) == row['derived_sha256'], 'SMP downstream manifest differs')
pinned(build_dir/'initramfs.cpio.gz', ORIGINAL)
read(build_dir/'initramfs-manifest.json')
build_log = read(build_dir/'kernel.log').decode()
must('Finished `release` profile [optimized] target(s)' in build_log and 'error: could not compile' not in build_log,
     'original SMP build log incomplete')
RUNS = [review_parallel(1), review_parallel(2)]

RESULT = {'schema':'g1c.independent.local-cpu-smp-review.v1','passed':True,
          'source_head':HEAD,'source_tree':TREE,'reviewed_at':datetime.now(timezone.utc).isoformat(),
          'review_method':'Read-only explicit git104 source and original artifacts. No producer/test/compiler/kernel invocation, source checkout/status dependency, product or remote writes.',
          'reviewer_program_sha256':sha(Path(__file__).read_bytes()),'reused_own_byte_parser_sha256':parser_sha,
          'ordinary_and_saved_smp2_kernel_sha256':KERNEL,'same_retained_kernel_bytes':True,
          'cpu_percent_units':'100 * process user+system CPU nanoseconds / wall nanoseconds; one-CPU denominator, not divided by configured vCPU count.',
          'cpu4':CONFIGS,'legacy_one_two_vcpu_runs':RUNS,'original_runner_tests':TESTS,
          'preprobe_smp2_freeze':FROZEN,
          'smp_build':{'original_command':BUILD['command'],'A01_SMP':'2','source_build_receipt':build_source,
                       'source_scope':'118 upstream build/manifest checks are bounded. Full product source binding is the parent recorded104/tree179b boundary and exact equality with the previously independently reviewed ordinary ELF; no full7346 SMP-specific snapshot is invented.',
                       'saved_elf_sha256':KERNEL,'ordinary_bytes_equal':True,'make_exit':0,'wrapper_exit':0,
                       'build_started_at':BUILD['started_at'],'build_finished_at':BUILD['finished_at'],
                       'environment_log_sha256':sha(environment.encode()),'kernel_log_sha256':sha(build_log.encode())},
          'source_inputs':{p:{'bytes':len(data),'sha256':sha(data)} for p,data in sorted(SOURCES.items())},
          'artifacts':{str(Path(p).relative_to(E)):v for p,v in sorted(FILES.items()) if str(p).startswith(str(E)+'/')},
          'limits':['Actual local original-runner CPU settlement/bounded quota evidence only.',
                    'SMP and Hepta HOS2 qualification flags remain false.',
                    'Two-vCPU probe explicitly starts/joins an additional pthread; iterations=0 is its original placeholder field, not measured workload inactivity.',
                    'Original C probe emits INCONCLUSIVE_REQUIRES_TIMING_VALIDATION; actual original Python caller separately applies supplied3% bound and two-vCPU >145% unlimited gate.',
                    'Some cpu.stat text is interleaved with kernel syscall logging; no additional exact cpu.stat counter qualification is claimed.',
                    'No hosted CI conclusion transferred from these local ELF bytes.']}
path = OUT/'local-cpu-smp-review.json'
data = (json.dumps(RESULT,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
path.write_bytes(data)
print(json.dumps({'path':str(path),'bytes':len(data),'sha256':sha(data),'passed':True,
                  'cpu4':[row['capped']['cpu_percent'] for row in CONFIGS],
                  'one_vcpu':[r['reported_cpu_percent_rounded3'] for r in RUNS[0]['runs']],
                  'two_vcpu':[r['reported_cpu_percent_rounded3'] for r in RUNS[1]['runs']],
                  'two_vcpu_unlimited':[r['unlimited_cpu_percent'] for r in RUNS[1]['runs']]}))
