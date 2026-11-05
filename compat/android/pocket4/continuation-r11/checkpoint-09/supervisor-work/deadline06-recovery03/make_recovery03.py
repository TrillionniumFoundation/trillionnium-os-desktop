from pathlib import Path
import ast
import difflib
import hashlib
import json
import os

OWN = Path(__file__).resolve().parent
OLD = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/supervisor/controller-recovery02')
OUT = OWN / 'controller-recovery03-work-02'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(name, raw):
    path = OUT / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


os.umask(0o077)
OUT.mkdir(mode=0o700)
old_compile = (OLD / 'compile.py').read_bytes()
old_run = (OLD / 'run.py').read_bytes()
assert sha(old_compile) == 'db8d361eaaf0c6e23cae093ca22fe13cac928f57f405e96be4bfc2131224affd'
assert sha(old_run) == 'f3aa25a0fc63e2e770e3eee5b18164b45b980a730bca9f58e6dfe0eee3b47f7a'
guard = (OWN / 'resource_guard.py').read_text()
ast.parse(guard)
programs = {}
for name, raw, anchor, memory in [
    ('compile.py', old_compile, '\nimport shutil\n', 1073741824),
    ('run.py', old_run, '\nimport sys\n', 536870912),
]:
    old = raw.decode()
    text = old.replace('producer06-deadline-recovery02', 'producer06-deadline-recovery03')
    text = text.replace('pocket4-supervisor-lmkd-deadline-r11-build-06-recovery02',
                        'pocket4-supervisor-lmkd-deadline-r11-build-06-recovery03')
    text = replace_once(text, anchor, '\n' + guard + '\n' + anchor)
    if name == 'compile.py':
        text = replace_once(text, '    before = None\n    try:\n',
                            '    resources = OwnJobResources(1073741824)\n'
                            '    report["resource_health"] = resources.record\n'
                            '    before = None\n    try:\n        resources.begin()\n')
    else:
        text = replace_once(text, '    cfg = None\n    try:\n',
                            '    resources = OwnJobResources(536870912)\n'
                            '    report["resource_health"] = resources.record\n'
                            '    cfg = None\n    try:\n        resources.begin()\n')
    text = replace_once(text, '    report["finished_at"] = now()\n',
                        '    finish_own_resource_gate(report, resources)\n'
                        '    report["finished_at"] = now()\n')
    ast.parse(text)
    programs[name] = text
    put(name, text.encode())
    diff = ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                      fromfile='recovery02/' + name,
                                      tofile='recovery03/' + name))
    put(name + '.diff', diff.encode())

cfg = json.loads((OLD / 'payload.json').read_bytes())
assert cfg['revision'] == 'producer06-deadline-recovery02'
cfg['revision'] = 'producer06-deadline-recovery03'
payload = json.dumps(cfg, indent=2, ensure_ascii=False) + '\n'
assert "'''" not in payload
put('payload.json', payload.encode())
stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
ast.parse(stdin)
request = json.loads((OLD / 'compile-request.json').read_bytes())
request['stdin'] = stdin
request['idempotency_key'] = 'p4-producer06-deadline-recovery03-compile01-' + sha(stdin.encode())[:16]
assert request['args'] == ['-I', '-B', '-']
assert request['memory_max_bytes'] == 1073741824
assert request['cpu_quota_percent'] == 100 and request['timeout_seconds'] == 600
put('compile-request.json', (json.dumps(request, indent=2, ensure_ascii=False) + '\n').encode())
template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
assert template['execution_ready'] is False
template['request_template']['stdin'] = programs['run.py']
template['request_template']['idempotency_key'] = 'p4-producer06-deadline-recovery03-ordinary01-REQUIRES_ACTUAL_SHA16'
template['requires'] = template['requires'].replace('recovery02', 'recovery03')
put('ordinary-run-request-template.json', (json.dumps(template, indent=2, ensure_ascii=False) + '\n').encode())
put('resource_guard.py', guard.encode())
for name in ('original-producer05-build-result.json',
             'original-producer05-build-template.py',
             'original-31-input-source-manifest.json'):
    put(name, (OLD / name).read_bytes())
summary = {
    'schema': 1, 'revision': 'producer06-deadline-recovery03',
    'parent_tree': 'd19aee7e36c96807c36609147378acdede0bb3c5',
    'source_change': 'none: all three deadline06 Rust overlays retain their original exact bytes',
    'controller_change': 'both compile and ordinary controllers add the same read-only held own-cgroup memory gate',
    'compile_stdin': {'bytes': len(stdin.encode()), 'sha256': sha(stdin.encode())},
    'request_sha256': sha((OUT / 'compile-request.json').read_bytes()),
    'key': request['idempotency_key'],
    'execution_status': 'NOT_SUBMITTED',
    'python_ast_parse_passed': True,
    'default_plan_and_semantic_controls_status': 'PENDING',
    'real_cgroup_sampling_performed': False,
    'rust_build_or_tests_executed': False,
    'full_owner_runtime_qualified': False,
    'whole_invocation_resource_gate_note': 'This source samples before receipt publication; durable outer terminal verification remains required.',
}
put('generation-summary.json', (json.dumps(summary, indent=2, sort_keys=True) + '\n').encode())
print(json.dumps(summary, indent=2, sort_keys=True))
