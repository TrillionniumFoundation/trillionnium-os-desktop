#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Run isolated r5 source controls; no Android process/cgroup is touched."""
import argparse, hashlib, json, pathlib, re, subprocess

p = argparse.ArgumentParser()
p.add_argument('--source-dir', type=pathlib.Path, required=True)
p.add_argument('--baseline-dir', type=pathlib.Path, required=True)
p.add_argument('--r4-tests-dir', type=pathlib.Path, required=True)
p.add_argument('--out-dir', type=pathlib.Path, required=True)
a = p.parse_args()
a.out_dir.mkdir(parents=True, exist_ok=False)
here = pathlib.Path(__file__).resolve().parent
reader = (a.r4_tests_dir/'test_reader_events.cpp').read_text().split('int main() {', 1)[0]
reader = reader.replace('extern "C" int __wrap_close(int) {return 0;}',
    'static int close_calls;\nextern "C" int __wrap_close(int fd) {if(fd>=0)++close_calls;return 0;}')
pending = a.out_dir/'actual_reader_pending.cpp'
pending.write_text(reader+(here/'test_pending_evidence.cpp').read_text())
report = {'scope': 'source controls only; no live process, cgroup, pressure, or deployment',
          'production_ready': False, 'tests': {}}
for name, cpp, wraps in [
        ('adapter', a.r4_tests_dir/'test_memory_cgroup.cpp', False),
        ('reader', a.r4_tests_dir/'test_reader_events.cpp', True),
        ('pending', pending, True)]:
    exe = a.out_dir/name
    cmd = ['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(a.source_dir),
           str(a.source_dir/'memory_cgroup.cpp'), str(cpp)]
    if wraps:
        wrapped = 'open,--wrap=openat,--wrap=fstatfs,--wrap=pread,--wrap=close'
        if name == 'pending': wrapped += ',--wrap=clock_gettime'
        cmd += ['-Wl,--wrap='+wrapped]
    cmd += ['-o', str(exe)]
    built = subprocess.run(cmd, capture_output=True, text=True)
    assert built.returncode == 0, name+built.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True)
    report['tests'][name] = {'compile_rc': built.returncode, 'run_rc': run.returncode,
                             'stdout': run.stdout, 'stderr': run.stderr}
    (a.out_dir/(name+'.stdout')).write_text(run.stdout)
    (a.out_dir/(name+'.stderr')).write_text(run.stderr)
    (a.out_dir/'partial-result.json').write_text(json.dumps(report, indent=2)+'\n')
    assert run.returncode == 0, name+run.stdout+run.stderr
    print(name, run.stdout.strip().splitlines()[-1])
for name, cmd in [
        ('actual_sequence', ['python3', str(here/'test_source_sequence.py'),
          '--source-dir', str(a.source_dir), '--baseline-dir', str(a.baseline_dir),
          '--reader-fixture', str(a.r4_tests_dir/'test_reader_events.cpp'),
          '--out-dir', str(a.out_dir/'actual-sequence')]),
        ('stock_selection', ['python3', str(a.r4_tests_dir/'test_aosp_selection.py'),
          '--source', str(a.source_dir/'lmkd.cpp'), '--upstream', str(a.baseline_dir/'lmkd.cpp'),
          '--out-dir', str(a.out_dir/'stock-selection')])]:
    run = subprocess.run(cmd, capture_output=True, text=True)
    report['tests'][name] = {'run_rc': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
    (a.out_dir/'partial-result.json').write_text(json.dumps(report, indent=2)+'\n')
    assert run.returncode == 0, name+run.stdout+run.stderr
    print(name, run.stdout)
source = (a.source_dir/'lmkd.cpp').read_text()
baseline = (a.baseline_dir/'lmkd.cpp').read_text()
# This candidate changes evidence lifetime only. Preserve the diagnostic whose
# possible allocation stall is being investigated independently in fixed r9.
start = '        ALOGI("Cell high throttling with critical PSI:'
end = '              cell_memory_snapshot.high_events);'
def diagnostic(text):
    i = text.index(start); return text[i:text.index(end, i)+len(end)]
assert diagnostic(source) == diagnostic(baseline)
assert source.count('ConsumeHighEvidence(psi_window_size_ms)') == 1
for constant in ['stall_limit_critical', 'pressure_after_kill_min_score', 'psi_window_size_ms',
                 'psi_partial_stall_ms', 'psi_complete_stall_ms', 'kill_timeout_ms']:
    expression = re.compile(r'^\s*'+constant+r'\s*= GET_LMK_PROPERTY[^;]+;', re.M)
    assert expression.findall(source) == expression.findall(baseline), constant
sha = lambda data: hashlib.sha256(data).hexdigest()
report['source_sha256'] = {n: sha((a.source_dir/n).read_bytes())
                           for n in ['lmkd.cpp','memory_cgroup.cpp','memory_cgroup.h','Android.bp']}
report['test_sha256'] = {p.name: sha(p.read_bytes()) for p in here.glob('*.py')}
report['test_sha256']['test_pending_evidence.cpp'] = sha((here/'test_pending_evidence.cpp').read_bytes())
report['pre_kill_diagnostic_unchanged'] = True
report['threshold_property_expressions_unchanged'] = True
report['selection_comparison'] = 'byte identity versus r4, whose six functions are pinned byte-identical to upstream c3601e823bd07c9c190f67e2f9bc7486e4978328'
report['pass'] = True
(a.out_dir/'result.json').write_text(json.dumps(report, indent=2)+'\n')
