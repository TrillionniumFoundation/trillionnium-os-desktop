"""Observe fixed production commands and the actual Soong variable input.

This module grants no artifact, policy, APEX, or runtime qualification. The
caller retains its normal builder's PIDFD and source locks through observation.
The tool and variables are observed from the owned, running build generation;
none of the local controls stand in for a real build observation.
"""
import json
import os
from pathlib import Path


def need(value, message):
    if not value:
        raise RuntimeError(message)


def expected_ui_argv(out):
    return [str(Path(out) / 'soong_ui'), '--make-mode', '-j6',
            'libberberis_arm64', 'com.android.art']


def expected_build_argv(source, out):
    source = str(source); out = Path(out); soong = out / 'soong'
    return [str(out / 'host/linux-x86/bin/soong_build'), '--top', source,
            '--soong_out', str(soong), '--out', str(out),
            '--soong_variables', str(soong / 'soong.droidloom_x86_64.variables'),
            '-o', str(soong / 'build.droidloom_x86_64.ninja'),
            '--kati_suffix', '-droidloom_x86_64', '--kati_enabled',
            '-l', str(out / '.module_paths/Android.bp.list'),
            '--available_env', str(soong / 'soong.environment.available'),
            '--used_env', str(soong / 'soong.environment.used.droidloom_x86_64.build'),
            'Android.bp']


def validate_ui_environment(environment):
    expected = {'TARGET_BUILD_VARIANT': 'user', 'TARGET_RELEASE': 'cp2a',
                'TARGET_PRODUCT': 'droidloom_x86_64', 'ALLOW_MISSING_DEPENDENCIES': 'false'}
    need(type(environment) is dict and all(type(environment.get(k)) is str
         and environment[k] == v for k, v in expected.items()),
         'actual soong_ui must use the fixed production user/cp2a/product and strict dependencies')
    return expected


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate key in actual Soong variables')
        result[key] = value
    return result


def validate_variables(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 2 * 1024**2,
         'bounded complete Soong variable bytes required')
    values = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    need(type(values) is dict and values.get('Debuggable') is False
         and values.get('Eng') is False and values.get('Allow_missing_dependencies') is False,
         'actual Soong variables must explicitly disable debuggable/eng/missing dependencies')
    need(values.get('DeviceProduct') == 'droidloom_x86_64'
         and values.get('DeviceArch') == 'x86_64', 'actual Soong product/architecture differs')
    return {name: values[name] for name in
            ('Debuggable', 'Eng', 'Allow_missing_dependencies', 'DeviceProduct', 'DeviceArch')}


def observe(process, *, source, out, expected_cgroup, result_directory, support, witness):
    """Take two execution boundaries around one full environment/input capture."""
    s = support
    need(type(process) is dict and type(process.get('pid')) is int and process['pid'] > 0,
         'actual positive owned process PID required')
    before = s.process_identity(process['pid'])
    need(witness.generation(before) == witness.generation(process)
         and before['cgroup'] == expected_cgroup, 'production observer left the owned generation')
    name = Path(before['exe']).name
    need(name in ('soong_ui', 'soong_build'), 'not a selected normal Soong process')
    expected = expected_ui_argv(out) if name == 'soong_ui' else expected_build_argv(source, out)
    need(before['argv'] == expected and before['exe'] == expected[0],
         'actual production Soong command differs from the fixed normal invocation')
    executable = s.file_ref(expected[0], 256 * 1024**2)
    records = {'schema': 'native-actual-production-user-input-observation-v1',
               'process_role': name, 'before': before, 'expected_argv': expected,
               'host_authority_inherited': False, 'artifact_qualified': False,
               'runtime_qualified': False}
    with witness.PinnedExecutable(executable, maximum=256 * 1024**2) as held:
        held.verify_running(before['pid'])
        witness.validate_executed_command(process, s.process_identity(before['pid']),
                                         expected, executable['path'])
        if name == 'soong_ui':
            raw = (Path('/proc') / str(before['pid']) / 'environ').read_bytes()
            need(len(raw) <= 2 * 1024**2, 'process environment exceeds observation bound')
            env = {}
            for item in raw.split(b'\0'):
                if not item:
                    continue
                key, sep, value = item.partition(b'=')
                need(sep == b'=' and key not in env, 'invalid or duplicate process environment key')
                env[key] = value
            selected = {k: env.get(k.encode(), b'').decode('utf-8') for k in
                        ('TARGET_BUILD_VARIANT', 'TARGET_RELEASE', 'TARGET_PRODUCT', 'ALLOW_MISSING_DEPENDENCIES')}
            records['actual_environment'] = validate_ui_environment(selected)
        else:
            variable_path = Path(out) / 'soong/soong.droidloom_x86_64.variables'
            variable_ref = s.file_ref(variable_path, 2 * 1024**2)
            ref, raw = s.pinned(variable_ref, 2 * 1024**2, contents=True)
            records['actual_variables'] = validate_variables(raw)
            records['original_variables'] = ref
            records['snapshot_variables'] = s.create(Path(result_directory) /
                ('production-variables-%d-%d.json' % (before['pid'], before['start_ticks'])), raw)
            need(all(records['snapshot_variables'][k] == ref[k] for k in ('bytes', 'sha256')),
                 'complete actual Soong variable snapshot differs')
            s.pinned(ref)
        after = s.process_identity(before['pid'])
        witness.validate_executed_command(process, after, expected, executable['path'])
        held.verify_running(before['pid'])
        records['after'] = after
        records['executable_observation'] = held.record()
    return s.create(Path(result_directory) / ('production-%s-%d-%d.json' %
                    (name, before['pid'], before['start_ticks'])), records)
