from pathlib import Path
import ast
import difflib
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'controller-recovery03-freeze-01'
OUT = ROOT / 'controller-recovery04-work-01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(name, data):
    with (OUT / name).open('xb') as stream:
        stream.write(data)


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


os.umask(0o077)
OUT.mkdir(mode=0o700)
programs = {}
old_targets = '''EXPECTED_TEST_TARGETS = {
    ("droidloom_pressure_relay", "lib"),
    ("droidloom_supervisor", "lib"),
    ("droidloomd", "bin"),
    ("droidloom-supervisor", "bin"),
    ("droidloom-psi-owner", "bin"),
    ("owned-ipc-controls", "bin"),
}'''
new_targets = '''EXPECTED_TEST_TARGETS = {
    ("droidloom_pressure_relay", "lib"),
    ("droidloom_supervisor", "lib"),
}'''
for name, expected in [('compile.py', '8990fe98f79338694963fb0310ff997c248630662c0ebc7ec898137b30367292'),
                       ('run.py', '6c2e1503db551faab2f48a66d6c87640af2dd1473ff488d3ad89dba5179597ec')]:
    raw = (OLD / name).read_bytes()
    assert sha(raw) == expected
    old = raw.decode()
    text = old.replace('producer06-deadline-recovery03', 'producer06-deadline-recovery04')
    text = text.replace('pocket4-supervisor-lmkd-deadline-r11-build-06-recovery03',
                        'pocket4-supervisor-lmkd-deadline-r11-build-06-recovery04')
    text = once(text, old_targets, new_targets)
    if name == 'compile.py':
        text = once(text, '            "--no-run", "--message-format=json"\n',
                    '            "--lib", "--no-run", "--message-format=json"\n')
    else:
        text = once(text, 'result = test_summary(out, 1, 24)', 'result = test_summary(out, 1, 22)')
        text = once(text, 'expected_count = (25 if key == ("droidloom_pressure_relay", "lib") else\n'
                          '                              122 if key == ("droidloom_supervisor", "lib") else 0)',
                    'expected_count = 23 if key == ("droidloom_pressure_relay", "lib") else 112')
        text = once(text, 'rust_tests_passed={"droidloom-pressure-relay": 25, "droidloom-supervisor": 122},',
                    'rust_tests_passed={"droidloom-pressure-relay": 23, "droidloom-supervisor": 112},\n'
                    '            rust_test_scope="selected library targets only; integration/bin test suites excluded",')
    ast.parse(text)
    programs[name] = text
    put(name, text.encode())
    put(name + '.diff', ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
             fromfile='recovery03/' + name, tofile='recovery04/' + name)).encode())

cfg = json.loads((OLD / 'payload.json').read_bytes())
assert cfg['revision'] == 'producer06-deadline-recovery03'
cfg['revision'] = 'producer06-deadline-recovery04'
payload = json.dumps(cfg, indent=2, ensure_ascii=False) + '\n'
put('payload.json', payload.encode())
stdin = programs['compile.py'] + "\ncompile_recovery(json.loads(r'''" + payload + "'''))\n"
ast.parse(stdin)
request = json.loads((OLD / 'compile-request.json').read_bytes())
request['stdin'] = stdin
request['idempotency_key'] = 'p4-producer06-deadline-recovery04-compile01-' + sha(stdin.encode())[:16]
put('compile-request.json', (json.dumps(request, indent=2, ensure_ascii=False) + '\n').encode())
template = json.loads((OLD / 'ordinary-run-request-template.json').read_bytes())
assert template['execution_ready'] is False
template['request_template']['stdin'] = programs['run.py']
template['request_template']['idempotency_key'] = 'p4-producer06-deadline-recovery04-ordinary01-REQUIRES_ACTUAL_SHA16'
template['requires'] = template['requires'].replace('recovery03', 'recovery04')
template['scope'] = 'Only the two selected library test ELFs (23 relay/112 supervisor), two targeted public retirement controls, seven ordinary IPC controls, worker-token control and pure entry ABI. No integration/bin-test suites, real Owner, Android, pressure, namespace or network execution.'
put('ordinary-run-request-template.json', (json.dumps(template, indent=2, ensure_ascii=False) + '\n').encode())
for name in ('resource_guard.py', 'original-producer05-build-result.json',
             'original-producer05-build-template.py', 'original-31-input-source-manifest.json'):
    put(name, (OLD / name).read_bytes())
summary = {'schema': 1, 'revision': 'producer06-deadline-recovery04',
           'parent_tree': 'de2d33c0c41b99e0e7254a0018bb4fa00a3c2168',
           'source_overlays_changed': False, 'resource_guard_changed': False,
           'compile_stdin': {'bytes': len(stdin.encode()), 'sha256': sha(stdin.encode())},
           'request_sha256': sha((OUT / 'compile-request.json').read_bytes()),
           'key': request['idempotency_key'], 'execution_status': 'NOT_SUBMITTED',
           'selected_test_targets': [['droidloom_pressure_relay', 'lib'], ['droidloom_supervisor', 'lib']],
           'expected_library_tests': {'droidloom-pressure-relay': 23, 'droidloom-supervisor': 112},
           'targeted_control_expected_passed_filtered': [1, 22],
           'rust_build_or_tests_executed_by_this_revision': False,
           'full_owner_runtime_qualified': False}
put('generation-summary.json', (json.dumps(summary, indent=2, sort_keys=True) + '\n').encode())
print(json.dumps(summary, indent=2, sort_keys=True))
