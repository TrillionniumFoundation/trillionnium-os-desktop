"""Freeze the matched C build with two actually observed added inputs."""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIR = ROOT / 'android-owner16-init-log-source-freeze01'
OLD = ROOT / 'lmkd-recovery-20261105-01/init-cgroup-handoff-build-freeze-01'
OUT = ROOT / 'android-owner16-init-log-android-build-freeze01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/init-cgroup-handoff-build01/build-result.json'
DEPS = ROOT / 'root-recovery-20261104-02/evidence/owner16-log-dependencies-read01/stdout.log'
KIND = 'p4-owner16-init-log-android-build01'
REMOTE = '/opt/p4-owner16-init-log-android-20261105-build-01'
PAIR_SHA = 'c5afbb0a61653f5fa554ef42cd68f77e71a38893b229151d2b685b5e2d032050'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def pretty(value): return json.dumps(value, sort_keys=True, indent=2) + '\n'
def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

def main():
    assert not OUT.exists()
    files = {}
    def put(name, data):
        data = data.encode() if isinstance(data, str) else data
        data.decode('utf-8'); assert name not in files
        files[name] = data
    manifest = (PAIR / 'SOURCE_PINS.json').read_bytes()
    assert sha(manifest) == PAIR_SHA
    for path, pin in json.loads(manifest)['files'].items():
        raw = (PAIR / path).read_bytes()
        assert len(raw) == pin['bytes'] and sha(raw) == pin['sha256']
    actual_raw = ACTUAL.read_bytes()
    assert len(actual_raw) == 540269 and sha(actual_raw) == '718b131c94126d6d7f9df30a2f164e8f85335fc027a2db3101b0e5904c291b64'
    actual = json.loads(actual_raw)
    assert actual['success'] and actual['all_inputs_unchanged'] and len(actual['commands']) == 16
    assert all(row['returncode'] == 0 and row['child_reaped'] and not row['timed_out'] for row in actual['commands'])
    old_cfg = json.loads((OLD / 'config.json').read_bytes())
    assert len(old_cfg['original_inputs']) == len(actual['original_inputs_before']) == 147
    for path, pin in old_cfg['original_inputs'].items():
        observed = actual['original_inputs_before'][path]
        assert pin == {'bytes': observed['bytes'], 'sha256': observed['sha256']}
    for name, pin in old_cfg['payload'].items():
        raw = base64.b64decode(pin['base64'], validate=True)
        assert len(raw) == pin['bytes'] and sha(raw) == pin['sha256']
        assert {'bytes': len(raw), 'sha256': sha(raw)} == {k: actual['source_before'][name][k] for k in ('bytes', 'sha256')}
    deps_raw = DEPS.read_bytes()
    assert len(deps_raw) == 13543 and sha(deps_raw) == 'd8eb8d858e9a1f8eb4446db9a9c8d95d3b223fa8abc96a3ffcc5157213d907e3'
    deps = json.loads(deps_raw)
    assert deps['collection_complete'] and deps['all_named_and_held_unchanged'] and deps['held_fds_closed']
    assert deps['error'] is None and deps['close_errors'] == [] and len(deps['inputs']) == 2
    header, library = deps['inputs']
    assert header['path'] == '/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/bionic/libc/include/dlfcn.h'
    assert (header['bytes'], header['sha256']) == (8723, '4fe89ca9769480e3560111f05d68739c899278d36b3d2ef1e7d1f97e77f62d74')
    header_raw = base64.b64decode(header['utf8_original_base64'], validate=True)
    assert len(header_raw) == header['bytes'] and sha(header_raw) == header['sha256']
    assert library['path'] == '/home/alex/work/pocket4-lmkd-production-candidate-20261104/android-link-01/deps/libdl.so'
    assert (library['bytes'], library['sha256']) == (50760, 'cac32e3c3cf985186becde5aeae987794892c88b192762073eb38f202ec111a9')
    cfg = copy.deepcopy(old_cfg)
    cfg.update(kind=KIND, root=REMOTE, source_manifest_sha256=PAIR_SHA)
    for row in deps['inputs']:
        assert row['path'] not in cfg['original_inputs']
        cfg['original_inputs'][row['path']] = {'bytes': row['bytes'], 'sha256': row['sha256']}
    cfg['non_MD_inputs'].append(library['path'])
    assert len(set(cfg['original_inputs']) - set(cfg['non_MD_inputs'])) == 141
    cfg['prior_147_input_closure_sha256'] = old_cfg['original_input_closure_sha256']
    cfg['new_dependency_receipt_sha256'] = sha(deps_raw)
    cfg['original_input_closure_sha256'] = sha(pretty(cfg['original_inputs']).encode())
    link = cfg['original_android_argv'][2]
    assert link.count('-lc') == 1 and '-Wl,--no-undefined' in link
    link.insert(link.index('-lc') + 1, library['path'])
    for name in ('Android.bp', 'init_relay_barrier.c', 'init_relay_protocol.h'):
        previous = (PAIR / 'preimage/android' / name).read_bytes()
        assert {'bytes': len(previous), 'sha256': sha(previous)} == {k: actual['source_before'][name][k] for k in ('bytes', 'sha256')}
        raw = (PAIR / 'candidate/android' / name).read_bytes()
        cfg['payload'][name] = {'bytes': len(raw), 'sha256': sha(raw), 'base64': base64.b64encode(raw).decode()}
    source = (PAIR / 'controls/init_log_controls.c').read_text()
    source = once(source, '#include "../candidate/android/init_relay_barrier.c"', '#include "init_relay_barrier.c"')
    raw = source.encode()
    cfg['payload']['init_log_controls.c'] = {'bytes': len(raw), 'sha256': sha(raw), 'base64': base64.b64encode(raw).decode()}
    assert len(cfg['payload']) == 9 and len(cfg['original_inputs']) == 149
    old = (OLD / 'build-template.py').read_text()
    template = old.replace('p4-init-cgroup-handoff-build01', KIND).replace('p4-init-cgroup-handoff-20261105-build-01', Path(REMOTE).name)
    template = once(template, "'original_input_closure_sha256': CFG['original_input_closure_sha256'],", "'original_input_closure_sha256': CFG['original_input_closure_sha256'],\n              'prior_147_input_closure_sha256': CFG['prior_147_input_closure_sha256'],\n              'new_dependency_receipt_sha256': CFG['new_dependency_receipt_sha256'],")
    template = once(template, "needed == ['libc.so']", "needed == ['libc.so', 'libdl.so']")
    template = once(template, "('cgroup-view', 'cgroup_view_controls.c', False, 8, 'cases')]:", "('cgroup-view', 'cgroup_view_controls.c', False, 8, 'cases'),\n            ('init-log', 'init_log_controls.c', False, 9, 'controls')]:")
    template = once(template, "source_path, '-o', str(root / name)])", "source_path, '-ldl', '-o', str(root / name)])")
    template = once(template,
        "            require(len(records) == expected_count + 1 and all(item.get('ok') is True for item in records) and\n                    records[-1].get(marker) == expected_count, 'owned controls result set differs')",
        """            if name == 'init-log':
                require(records == [{'controls': 9, 'assertions': 187, 'real_memfd': True,
                    'real_child_exec': True, 'kernel_logger_call': 'explicit fixture seam',
                    'android_or_namespace_executed': False, 'all_owned_fds_closed': True,
                    'success': True}] and result['stderr'] == '', 'owned init log controls differ')
            else:
                require(len(records) == expected_count + 1 and all(item.get('ok') is True for item in records) and
                        records[-1].get(marker) == expected_count, 'owned controls result set differs')""")
    marker = 'CFG = None  # Filled once by the local frozen-request generator.'
    body = once(template, marker, 'CFG = ' + repr(cfg))
    parsed = ast.parse(body)
    node = next(n for n in parsed.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CFG' for t in n.targets))
    assert ast.literal_eval(node.value) == cfg
    node.value = ast.Constant(None)
    assert ast.dump(parsed) == ast.dump(ast.parse(template))
    compile(body, 'matched_android_build16', 'exec')
    request = json.loads((OLD / 'request.json').read_bytes())
    request.update(stdin=body, idempotency_key='p4-owner16-init-log-android-build01-' + sha(body.encode())[:16])
    put('request.json', pretty(request)); put('build.py', body); put('build-template.py', template)
    put('build-template.diff', ''.join(difflib.unified_diff(old.splitlines(True), template.splitlines(True), fromfile='actual-ABI3/build-template.py', tofile='owner16/build-template.py')))
    put('config.json', pretty(cfg)); put('resource_guard.py', (OLD / 'resource_guard.py').read_bytes())
    put('init-log-control-include.diff', ''.join(difflib.unified_diff((PAIR / 'controls/init_log_controls.c').read_text().splitlines(True), source.splitlines(True), fromfile='local/init_log_controls.c', tofile='staged/init_log_controls.c')))
    put('evidence/new-dependencies.json', deps_raw); put('evidence/dlfcn.h', header_raw)
    put('evidence/prior-input-basis.json', pretty({'receipt_path': str(ACTUAL), 'bytes': len(actual_raw), 'sha256': sha(actual_raw),
        'original_147_input_closure_sha256': old_cfg['original_input_closure_sha256'],
        'new_actual_2_input_receipt': {'path': str(DEPS), 'bytes': len(deps_raw), 'sha256': sha(deps_raw)}}))
    put('validation.json', pretty({'schema': 1, 'execution_status': 'NOT_SUBMITTED', 'source_manifest_sha256': PAIR_SHA,
        'prior_actual_input_count': 147, 'added_actual_inputs': {row['path']: {'bytes': row['bytes'], 'sha256': row['sha256']} for row in deps['inputs']},
        'new_expected_MD_count': 141, 'original_147_inputs_unchanged': True, 'input_count': 149,
        'Android_no_undefined_retained': True, 'expected_needed': ['libc.so', 'libdl.so'],
        'host_control_results_required': {'protocol': 20, 'protocol-close-errno': 20, 'diagnostic': 7, 'cgroup-view': 8, 'init-log': 9},
        'expected_commands': 19, 'payload_count': 9, 'resource_guard_unchanged': True,
        'request_bytes': len(files['request.json']), 'request_sha256': sha(files['request.json']),
        'stdin_bytes': len(body.encode()), 'stdin_sha256': sha(body.encode()),
        'actual_KernelLogger_definition_qualified': False, 'Android_constructor_or_Owner_executed': False}))
    put('README.md', '''# Owner16 paired Android init logging build

Create-only CPU1/512MiB/180s successor to the actual ABI3 Android build.
Its original147 input pins remain unchanged. Exactly two actually observed
inputs are added: dlfcn.h8723/4fe89c… and libdl.so50760/cac32e… . The explicit
libdl path is the only new Android link argument; --no-undefined remains.
Preflight and real MD must match the exact141 headers/source set. Expected
DT_NEEDED is exactly libc.so and libdl.so, with original versioned ABI export,
INIT_ARRAY and x86_64 retained. The new source payload has9 exact members.

The original20/20/7/8 owned controls remain. New9 controls execute only host
owned memfd/fd/env/exec, use an explicit KernelLogger call seam, and require
their complete187-assertion receipt. They cannot qualify the Android logger.
19 actual commands, all source/header/compiler/link/tool before-after gates,
child cleanup and original own resource gate must pass for a build receipt.

The actual libdl observation qualifies this link input, not the defining
libbase KernelLogger bytes/cache/ABI. Only a future matched Owner runtime can
qualify its real logger markers after held HELLO and before broker startup.
This package performs no Android constructor, namespace, Main deployment or
Owner runtime. Its new ELF must be actually returned and externally bound.
''')
    put('make_android_build16.py', Path(__file__).read_bytes())
    put('SOURCE_PINS.json', pretty({'schema': 1, 'files': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(files.items())}}))
    OUT.mkdir()
    for name, raw in files.items():
        path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f: f.write(raw)
    print(pretty({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['SOURCE_PINS.json']),
        'request_bytes': len(files['request.json']), 'request_sha256': sha(files['request.json']),
        'stdin_bytes': len(body.encode()), 'stdin_sha256': sha(body.encode()), 'key': request['idempotency_key']}))

if __name__ == '__main__': main()
