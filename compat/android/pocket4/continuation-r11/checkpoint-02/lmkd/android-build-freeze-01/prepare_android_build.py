#!/usr/bin/env python3
# Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0
"""Freeze and execute one isolated incremental Android build; never deploy/run LMKD.

Reuses the exact executed r5 plan's pinned compiler, headers, DSOs and three
unchanged support objects. All six changed/new translation units get fresh -MD
compiles. Reused object system-header provenance remains a declared limitation.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

UNITS = ['memory_cgroup.cpp', 'lmkd.cpp', 'pressure_relay.cpp', 'enrollment.cpp',
         'relay_session.cpp', 'reaper.cpp']
FILES = sorted(UNITS + ['Android.bp', 'memory_cgroup.h', 'pressure_relay.h',
                       'enrollment.h', 'relay_session.h', 'reaper.h'])


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for value in iter(lambda: stream.read(65536), b''): h.update(value)
    return h.hexdigest()


def record(path):
    p = Path(path)
    return {'sha256': sha(p), 'bytes': p.stat().st_size,
            'symlink': os.readlink(p) if p.is_symlink() else None}


def verify(inputs):
    for name, expected in inputs.items():
        actual = record(name)
        assert actual['sha256'] == expected['sha256'], ('input drift', name)
        assert actual['symlink'] == expected['symlink'], ('symlink drift', name)


def prepare(a):
    assert sha(a.baseline_plan) == a.baseline_plan_sha256, 'baseline plan mismatch'
    assert sha(a.candidate_manifest) == a.candidate_manifest_sha256, 'candidate manifest mismatch'
    old = json.loads(a.baseline_plan.read_text())
    manifest = json.loads(a.candidate_manifest.read_text())
    assert old['schema'] == 'pocket4-lmkd-r5-build-plan-v1'
    assert old['upstream_commit'] == 'c3601e823bd07c9c190f67e2f9bc7486e4978328'
    assert sorted(manifest['files']) == FILES
    verify(old['frozen_files'])
    candidate = a.candidate_dir.resolve()
    for name in FILES:
        assert not (candidate/name).is_symlink()
        assert sha(candidate/name) == manifest['files'][name], ('candidate drift', name)
    out = a.out_dir.resolve()
    assert not out.exists(), 'refuse to overwrite or replay an existing preparation'
    out.mkdir(parents=True)
    stage, build, link = out/'source', out/'build', out/'link'
    old_source = Path(old['source_root'])
    shutil.copytree(old_source, stage, symlinks=True)
    for name in FILES: shutil.copy2(candidate/name, stage/name)

    replacements = [(str(old_source), str(stage)), (old['build_root'], str(build)),
                    (old['link_root'], str(link))]

    def remap(value):
        for source, target in replacements: value = value.replace(source, target)
        return value

    steps = []
    for name in UNITS:
        baseline_label = 'lmkd.cpp-android' if name == 'lmkd.cpp' else 'memory_cgroup.cpp-android'
        base_compile = next(x['argv'] for x in old['steps'] if x['label'] == baseline_label)
        command = [remap(x) for x in base_compile]
        command[command.index('-c')+1] = str(stage/name)
        command[command.index('-o')+1] = str(build/(name+'.o'))
        command[command.index('-MF')+1] = str(build/(name+'.d'))
        assert '-MD' in command and '-MMD' not in command
        steps.append({'label': name, 'argv': command, 'dependency_file': str(build/(name+'.d')),
                      'source': str(stage/name)})
    command = [remap(x) for x in next(x['argv'] for x in old['steps'] if x['label'] == 'link-android')]
    command = ['-Wl,--threads=1' if x.startswith('-Wl,--threads=') else x for x in command]
    if '-Wl,--threads=1' not in command: command.insert(1, '-Wl,--threads=1')
    reaper = [i for i,x in enumerate(command) if x.endswith('/reaper.cpp.o')]
    assert len(reaper) == 1
    command[reaper[0]] = str(build/'reaper.cpp.o')
    position = command.index(str(build/'lmkd.cpp.o')) + 1
    command[position:position] = [str(build/(n+'.o')) for n in ['pressure_relay.cpp','enrollment.cpp','relay_session.cpp']]
    assert command[command.index('-o')+1] == str(link/'lmkd-cgroup')
    steps.append({'label': 'link-android', 'argv': command})

    frozen = dict(old['frozen_files'])
    for name, value in old['frozen_files'].items():
        path = Path(name)
        if path.is_relative_to(old_source):
            mapped = stage/path.relative_to(old_source)
            expected = manifest['files'].get(str(path.relative_to(old_source)), value['sha256'])
            assert sha(mapped) == expected, ('staged inherited source differs', str(mapped))
            frozen[str(mapped)] = record(mapped)
    for name in FILES: frozen[str(stage/name)] = record(stage/name)
    for path in [a.baseline_plan, a.candidate_manifest, Path(__file__).resolve()]:
        frozen[str(path.resolve())] = record(path)
    plan = {'schema': 'pocket4-lmkd-enrollment-r6-android-build-v1',
            'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope': 'isolated incremental compile/link only; no Android execution, pressure, UI or deployment',
            'baseline_plan_sha256': a.baseline_plan_sha256,
            'candidate_manifest_sha256': a.candidate_manifest_sha256,
            'source_sha256': manifest['files'], 'source_root': str(stage),
            'build_root': str(build), 'link_root': str(link), 'steps': steps,
            'frozen_files': frozen, 'required_limits': {'cpu_percent_max': 100,
                'memory_max_bytes_max': 1073741824, 'nice_min': 5, 'compile_jobs': 1, 'lld_threads': 1},
            'reused_support_objects': [x for x in command if x.endswith('.cpp.o') and x not in [str(build/(n+'.o')) for n in UNITS]],
            'baseline_target': str(Path(old['link_root'])/'lmkd-cgroup'),
            'production_ready': False, 'execution_started': False}
    assert len(plan['reused_support_objects']) == 3
    assert sha(plan['baseline_target']) == 'c6d49d95c16d1ce6d94293313ae9f6f683a079ebd4cc821338a701dfe5b2cf6f'
    frozen[plan['baseline_target']] = record(plan['baseline_target'])
    path = out/'plan.json'
    path.write_text(json.dumps(plan, indent=2)+'\n')
    print(json.dumps({'plan': str(path), 'plan_sha256': sha(path), 'units': UNITS,
                      'compiler_started': False, 'deployment': False}, indent=2))


def build(a):
    assert sha(a.plan) == a.plan_sha256, 'plan mismatch'
    plan = json.loads(a.plan.read_text())
    assert plan['schema'] == 'pocket4-lmkd-enrollment-r6-android-build-v1'
    verify(plan['frozen_files'])
    owned = next(x.split(':',2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
    assert owned != '/' and 'droidloomd.service' not in Path(owned).parts
    group = Path('/sys/fs/cgroup')/owned.lstrip('/')
    memory = (group/'memory.max').read_text().strip()
    quota, period = (group/'cpu.max').read_text().split()
    assert memory != 'max' and 0 < int(memory) <= plan['required_limits']['memory_max_bytes_max']
    assert quota != 'max' and 0 < int(quota)*100 <= int(period)*plan['required_limits']['cpu_percent_max']
    assert os.getpriority(os.PRIO_PROCESS, 0) >= plan['required_limits']['nice_min']
    out, link = Path(plan['build_root']), Path(plan['link_root'])
    assert not out.exists() and not link.exists(), 'refuse build replay'
    out.mkdir(); link.mkdir()
    environment = os.environ.copy()
    for key in ['CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH','OBJC_INCLUDE_PATH','LIBRARY_PATH',
                'COMPILER_PATH','GCC_EXEC_PREFIX','LD_PRELOAD','LD_LIBRARY_PATH']:
        environment.pop(key, None)
    environment['LC_ALL'] = 'C'
    report = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'scope': plan['scope'],
              'plan_sha256': a.plan_sha256, 'source_sha256': plan['source_sha256'],
              'owned_limits': {'cgroup': owned, 'memory.max': memory, 'cpu.max': [quota,period],
                               'nice': os.getpriority(os.PRIO_PROCESS,0)},
              'steps': [], 'success': False, 'production_ready': False, 'deployment': False,
              'reused_object_limit': 'three pinned support objects retain prior historical -MMD system-header provenance limitation'}

    def run(label, command):
        start = time.monotonic()
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=180)
        item = {'label': label, 'argv': command, 'rc': result.returncode,
                'seconds': time.monotonic()-start, 'stdout': result.stdout, 'stderr': result.stderr}
        report['steps'].append(item)
        (out/(label+'.json')).write_text(json.dumps(item,indent=2)+'\n')
        assert result.returncode == 0, label+': '+result.stderr[-2000:]
        return result.stdout

    try:
        closure = {}
        for step in plan['steps']:
            if step['label'] == 'link-android': continue
            run(step['label'], step['argv'])
            text = Path(step['dependency_file']).read_text().replace('\\\n',' ')
            inputs = sorted(set(shlex.split(text.split(':',1)[1])))
            assert step['source'] in inputs
            for path in inputs:
                assert path in plan['frozen_files'], ('unfrozen compiler dependency', path)
                assert sha(path) == plan['frozen_files'][path]['sha256'], ('dependency drift', path)
            closure[step['label']] = inputs
        verify(plan['frozen_files'])
        step = next(s for s in plan['steps'] if s['label']=='link-android')
        run(step['label'], step['argv'])
        target = link/'lmkd-cgroup'
        original = run('baseline-dynamic', ['/usr/bin/readelf','-d','-W',plan['baseline_target']])
        current = run('candidate-dynamic', ['/usr/bin/readelf','-d','-W',str(target)])
        needed = lambda text: sorted(line.split('Shared library: ')[1] for line in text.splitlines() if '(NEEDED)' in line)
        assert needed(original)==needed(current), 'DSO contract changed'
        run('candidate-elf', ['/usr/bin/readelf','-h','-l','-n','-W',str(target)])
        run('candidate-symbols', ['/usr/bin/readelf','--dyn-syms','-W',str(target)])
        (out/'actual-md-closure.json').write_text(json.dumps(closure,indent=2)+'\n')
        verify(plan['frozen_files'])
        report.update({'success': True, 'target_sha256': sha(target), 'target_bytes': target.stat().st_size,
                       'actual_md_manifest_sha256': sha(out/'actual-md-closure.json'),
                       'new_objects': {p.name: sha(p) for p in out.glob('*.o')}, 'inputs_unchanged': True})
    except Exception as error:
        report['error'] = repr(error)
    finally:
        (link/'build-result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k!='steps'},indent=2))
    if not report['success']: raise SystemExit(2)


parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest='mode', required=True)
prep = commands.add_parser('prepare')
prep.add_argument('--baseline-plan', type=Path, required=True)
prep.add_argument('--baseline-plan-sha256', required=True)
prep.add_argument('--candidate-dir', type=Path, required=True)
prep.add_argument('--candidate-manifest', type=Path, required=True)
prep.add_argument('--candidate-manifest-sha256', required=True)
prep.add_argument('--out-dir', type=Path, required=True)
execute = commands.add_parser('build')
execute.add_argument('--plan', type=Path, required=True)
execute.add_argument('--plan-sha256', required=True)
args = parser.parse_args()
prepare(args) if args.mode == 'prepare' else build(args)
