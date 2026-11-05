"""Local-only exact request generator; never contacts or executes a device."""
import ast
import base64
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
SOURCE = BASE / 'init-project-diagnostic-freeze-01'
WORK = BASE / 'init-project-repair-work-01'
OUT = BASE / 'init-project-diagnostic-build-freeze-01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest_bytes = (SOURCE / 'manifest.json').read_bytes()
    assert sha(manifest_bytes) == '7ae7bc262f09ede128f1ee6b2fd7f3e8710c47b69c4df68370f2ca9ae2918c9f'
    manifest = json.loads(manifest_bytes)
    for row in manifest['files']:
        data = (SOURCE / row['path']).read_bytes()
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
    closure_raw = (SOURCE / 'references/android-input-closure-01.json').read_bytes()
    original = json.loads((SOURCE / 'references/android-build-01.json').read_bytes())
    closure = json.loads(closure_raw)
    assert closure['actual_MD_equals_preflight'] is True and closure['inputs_before'] == closure['inputs_after']
    assert len(closure['inputs_before']) == original['input_count'] == 147
    original_root = str(Path(original['artifact']['path']).parent)
    source_names = ['init_relay_barrier.c', 'init_relay_protocol.h', 'protocol_controls.c',
                    'diagnostic_controls.c', 'close_errno_seam.h', 'Android.bp', 'exported.map.txt']
    payload = {}
    for name in source_names:
        data = (SOURCE / 'source' / name).read_bytes()
        payload[name] = {'bytes': len(data), 'sha256': sha(data), 'base64': base64.b64encode(data).decode()}
    guard_path = BASE / 'producer07-controller-freeze-02/resource_guard.py'
    guard = guard_path.read_bytes()
    non_md = [p for p in closure['inputs_before'] if p.endswith(('/crtbegin_so.o', '/crtend_so.o',
              '/bin/clang++', '/bin/ld.lld', '/libclang_rt.builtins-x86_64-android.a', '/deps/libc.so',
              '/source/exported.map.txt'))]
    assert len(non_md) == 7 and 147 - len(non_md) == original['dependency_count'] == 140
    cfg = {'kind': 'p4-init-project-diagnostic-build01',
           'root': '/home/alex/pocket4-init-project-diagnostic-20261105-build-01',
           'source_manifest_sha256': sha(manifest_bytes), 'payload': payload,
           'original_input_closure_sha256': sha(closure_raw), 'original_root': original_root,
           'original_inputs': {p: {'bytes': v['bytes'], 'sha256': v['sha256']} for p, v in closure['inputs_before'].items()},
           'original_android_argv': [c['argv'] for c in original['commands']], 'non_MD_inputs': sorted(non_md),
           'resource_guard': {'sha256': sha(guard), 'base64': base64.b64encode(guard).decode()}}
    template = (WORK / 'build-template.py').read_text()
    needle = 'CFG = None  # Filled once by the local frozen-request generator.'
    assert template.count(needle) == 1
    body = template.replace(needle, 'CFG = ' + repr(cfg))
    compile(body, '<frozen-build>', 'exec')
    parsed = ast.parse(body)
    assign = next(x for x in parsed.body if isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CFG' for t in x.targets))
    assert ast.literal_eval(assign.value) == cfg
    assign.value = ast.Constant(value=None)
    assert ast.dump(parsed, include_attributes=False) == ast.dump(ast.parse(template), include_attributes=False)
    raw = body.encode()
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo', 'args': ['-n', '/usr/bin/python3', '-I', '-B', '-'],
               'cwd': '/', 'stdin': body, 'idempotency_key': 'p4-init-project-diagnostic01-build01-' + sha(raw)[:16],
               'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10, 'timeout_seconds': 180}
    request_raw = (json.dumps(request, indent=2, sort_keys=True) + '\n').encode()
    OUT.mkdir(exist_ok=False)
    members = {'build.py': raw, 'build-template.py': template.encode(), 'resource_guard.py': guard,
               'request.json': request_raw, 'config.json': (json.dumps(cfg, indent=2, sort_keys=True) + '\n').encode(),
               'make_build_request.py': Path(__file__).read_bytes()}
    proof = {'schema': 1, 'actual_device_execution': False, 'AST_controller_equals_template_except_CFG': True,
             'request_stdin_bytes': len(raw), 'request_stdin_sha256': sha(raw), 'request_sha256': sha(request_raw),
             'idempotency_key': request['idempotency_key'], 'source_payload_count': len(payload),
             'original_input_count': len(cfg['original_inputs']), 'expected_Android_MD_count': 140,
             'original_commands_preserved_except_output_root': True, 'original_frozen_payloads_verified': len(manifest['files'])}
    members['source-binding-result.json'] = (json.dumps(proof, indent=2, sort_keys=True) + '\n').encode()
    rows = []
    for name, data in members.items():
        (OUT / name).write_bytes(data)
        rows.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
    result = {'schema': 1, 'kind': cfg['kind'], 'actual_device_execution': False,
              'source_manifest_sha256': cfg['source_manifest_sha256'], 'files': sorted(rows, key=lambda r: r['path'])}
    data = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    (OUT / 'manifest.json').write_bytes(data)
    print(json.dumps({'freeze': str(OUT), 'manifest_sha256': sha(data), **proof}, indent=2))


if __name__ == '__main__':
    main()
