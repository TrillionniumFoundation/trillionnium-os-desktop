#!/usr/bin/env python3
"""Local compiler/real socket transport only; root fixture is PLAN-only."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'candidate'
OUTPUT = HERE / 'local-verification01'


def pin(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    OUTPUT.mkdir(mode=0o700)
    source_before = {str(path.relative_to(SOURCE)): pin(path)
                     for path in sorted(SOURCE.rglob('*')) if path.is_file()}
    compiler = Path('/usr/bin/g++').resolve(strict=True)
    compiler_before = pin(compiler)
    commands = []
    common = [str(compiler), '-std=c++17', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
              '-fstack-protector-strong', '-I', str(SOURCE / 'include'), '-I', str(SOURCE / 'source')]
    core = [str(SOURCE / 'source' / name) for name in
            ('factory_context.cc', 'role_authorization.cc', 'role_snapshot.cc', 'role_session.cc',
             'proc_maps_factory_wire.cc')]
    argv = [
        ('response-build', common + core + [str(SOURCE / 'controls/response_controls.cc'), '-o', str(OUTPUT / 'response_controls')]),
        ('session-build', common + core + [str(SOURCE / 'controls/session_controls.cc'), '-o', str(OUTPUT / 'session_controls')]),
        ('response-run', [str(OUTPUT / 'response_controls')]),
        ('session-plan', [str(OUTPUT / 'session_controls')]),
    ]
    error = None
    try:
        for name, command in argv:
            start = time.monotonic()
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
            for stream in ('stdout', 'stderr'):
                (OUTPUT / (name + '.' + stream)).write_bytes(getattr(process, stream))
            commands.append({'name': name, 'argv': command, 'returncode': process.returncode,
                             'seconds': time.monotonic() - start,
                             'stdout': pin(OUTPUT / (name + '.stdout')),
                             'stderr': pin(OUTPUT / (name + '.stderr'))})
            if process.returncode:
                raise RuntimeError(name + ' failed')
        output = [json.loads(line) for line in (OUTPUT / 'response-run.stdout').read_text().splitlines()]
        if len(output) != 12 or output[-1]['state'] != 'PASS_RESPONSE_TRANSPORT_ONLY' or output[-1]['cases'] != 17:
            raise RuntimeError('response control result did not match expected execution')
        plan = json.loads((OUTPUT / 'session-plan.stdout').read_text())
        if plan['state'] != 'PLAN_ONLY' or plan['owned_cases'] != 9:
            raise RuntimeError('root fixture was not the expected PLAN-only entry')
    except Exception as problem:
        error = repr(problem)
    source_after = {str(path.relative_to(SOURCE)): pin(path)
                    for path in sorted(SOURCE.rglob('*')) if path.is_file()}
    compiler_after = pin(compiler)
    result = {'state': 'PASS_LOCAL_TRANSPORT_AND_PLAN' if error is None and source_before == source_after
              and compiler_before == compiler_after else 'FAIL',
              'error': error, 'commands': commands, 'compiler': {'path': str(compiler), **compiler_before},
              'compiler_unchanged': compiler_before == compiler_after, 'source_before': source_before,
              'source_unchanged': source_before == source_after, 'root_fixture_executed': False,
              'Android_qualified': False, 'platform_policy_qualified': False, 'remote_actions': 0}
    (OUTPUT / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'state': result['state'], 'commands': len(commands), 'error': error,
                      'result': str(OUTPUT / 'result.json'), **pin(OUTPUT / 'result.json')}))
    return 0 if result['state'] != 'FAIL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
