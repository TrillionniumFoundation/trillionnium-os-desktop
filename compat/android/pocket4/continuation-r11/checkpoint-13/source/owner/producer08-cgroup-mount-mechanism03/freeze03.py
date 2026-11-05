#!/usr/bin/env python3
"""Freeze only; never dispatch or enter a namespace."""
import ast
import base64
import copy
import difflib
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
BASE = WORK.parent
OLD = BASE / 'cgroup-mount-mechanism-freeze-02'
OUT = BASE / 'cgroup-mount-mechanism-freeze-03'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def pretty(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
def put(name, raw):
    if isinstance(raw, str): raw = raw.encode()
    raw.decode('utf-8')
    path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output: output.write(raw)

def main():
    old_manifest = (OLD / 'manifest.json').read_bytes()
    assert sha(old_manifest) == 'd5974490d49961963fc2a44dbbadde263899cb593523d9d974d217ac05d459bb'
    for row in json.loads(old_manifest)['files']:
        raw = (OLD / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    actual_path = BASE.parent / 'root-recovery-20261104-02/evidence/owner-cgroup-mount-mechanism02/result.json'
    actual = actual_path.read_bytes()
    assert sha(actual) == '7157140c9e0afb5b79d87f41cc804423e543608db6e1a320e0bce625c4043e6c'
    old_result = json.loads(actual)
    assert old_result['success'] is False and old_result['commands'][3]['returncode'] == 1
    child = json.loads(old_result['commands'][3]['stdout'])
    assert child['parent_errno'] == 71 and child['forced_kill'] is True and child['child_wait_status'] == 0
    assert child['child_reaped'] is True and child['all_private_mounts_unmounted'] is True
    controls_raw = (WORK / 'local-controls01/result.json').read_bytes()
    controls = json.loads(controls_raw)
    assert controls['success'] is True and controls['passed'] == 15 and len(controls['commands']) == 3
    assert all(row['returncode'] == 0 for row in controls['commands'])
    old_profile = json.loads((OLD / 'profile.json').read_bytes())
    profile = copy.deepcopy(old_profile)
    profile['root'] = '/opt/p4-cgroup-mount-mechanism-20261105-02'
    profile['nonce'] = (WORK / 'nonce.txt').read_text().strip()
    assert len(profile['nonce']) == 32 and int(profile['nonce'], 16) and profile['nonce'] != old_profile['nonce']
    assert {k:v for k,v in profile.items() if k not in ('root','nonce')} == {k:v for k,v in old_profile.items() if k not in ('root','nonce')}
    sources = {'probe.c': (WORK / 'source/probe.c').read_bytes()}
    for name in ('pinned_support.py', 'resource_guard.py'):
        sources[name] = (OLD / 'source' / name).read_bytes()
    probe = sources['probe.c'].decode()
    old_probe = (OLD / 'source/probe.c').read_text()
    normalized = probe.replace(profile['root'], old_profile['root']).replace(profile['nonce'], old_profile['nonce'])
    assert normalized[:normalized.index('struct collection {')] == old_probe[:old_probe.index('int main(')]
    old_template = (OLD / 'controller-template.py').read_text()
    template = old_template.replace(old_profile['root'], profile['root']).replace("'owned-cgroup-repeat-mount-mechanism01'", "'owned-cgroup-repeat-mount-mechanism03'")
    predicate = "need(control['child_reaped'] and not control['forced_kill']"
    assert template.count(predicate) == 1
    template = template.replace(predicate, "need(control['peer_eof'] is True and control['child_reaped'] and not control['forced_kill']")
    cfg = copy.deepcopy(profile)
    cfg['sources'] = {name: {'bytes': len(raw), 'sha256': sha(raw), 'base64': base64.b64encode(raw).decode()} for name,raw in sources.items()}
    stdin = template.replace('CFG = None', 'CFG = ' + repr(cfg))
    assert template.count('CFG = None') == 1
    t, s = ast.parse(template), ast.parse(stdin)
    node = next(n for n in s.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'CFG')
    assert ast.literal_eval(node.value) == cfg
    node.value = ast.Constant(None)
    assert ast.dump(s, include_attributes=False) == ast.dump(t, include_attributes=False)
    old_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(old_template).body if isinstance(n, ast.FunctionDef)}
    new_functions = {n.name: ast.dump(n, include_attributes=False) for n in t.body if isinstance(n, ast.FunctionDef)}
    assert set(old_functions) == set(new_functions)
    assert all(new_functions[n] == value for n,value in old_functions.items() if n != 'main')
    request = json.loads((OLD / 'request.json').read_bytes())
    request['stdin'] = stdin
    request['idempotency_key'] = 'p4-owned-cgroup-repeat-mount03-' + sha(stdin.encode())[:16]
    assert request['cpu_quota_percent'] == 100 and request['memory_max_bytes'] == 536870912 and request['timeout_seconds'] == 120
    OUT.mkdir(exist_ok=False)
    put('profile.json', pretty(profile)); put('controller-template.py', template)
    put('stdin.py', stdin); put('request.json', pretty(request))
    for name,raw in sources.items(): put('source/' + name, raw)
    put('controls/parent_controls.c', (WORK / 'source/parent_controls.c').read_bytes())
    put('controls/result.json', controls_raw)
    for path in sorted((WORK / 'local-controls01').glob('command*.*')):
        if path.suffix in ('.stdout', '.stderr'): put('controls/' + path.name, path.read_bytes())
    put('evidence/original-mechanism02-result.json', actual)
    put('preimage/probe.c', old_probe)
    delta = ''.join(difflib.unified_diff(old_probe.splitlines(True), probe.splitlines(True), fromfile='mechanism02/probe.c', tofile='mechanism03/probe.c'))
    delta += ''.join(difflib.unified_diff(old_template.splitlines(True), template.splitlines(True), fromfile='mechanism02/controller-template.py', tofile='mechanism03/controller-template.py'))
    delta += ''.join(difflib.unified_diff((OLD / 'profile.json').read_text().splitlines(True), pretty(profile).decode().splitlines(True), fromfile='mechanism02/profile.json', tofile='mechanism03/profile.json'))
    put('revision02-to03.diff', delta); put('freeze03.py', Path(__file__).read_bytes())
    put('binding-result.json', pretty({'schema':1, 'request_stdin_exact':True, 'template_CFG_AST_only':True,
        'unchanged_controller_functions':len(old_functions)-1, 'support_resource_bytes_unchanged':True,
        'mount_child_logic_unchanged_except_fresh_path_nonce':True, 'actual_local_parent_controls_passed':15,
        'actual_local_tool_chunk':'17bff5', 'local_controls_sha256':sha(controls_raw),
        'original02_failure_preserved_sha256':sha(actual), 'actual_device_execution':False,
        'new_root':profile['root'], 'new_nonce':profile['nonce'], 'kernel_control_or_Android_qualified':False}))
    put('README.md', '''# Owned repeated cgroup mount mechanism 03

This is a fresh once-only probe after actual mechanism02 failed. The old full
result remains FAIL: the child recorded first/fresh mounts successful and both
same-target remounts EBUSY, then the parent incorrectly rejected ordinary EOF
after the sole frame and attempted forced cleanup. The old receipt is preserved.

The new parent accepts exactly one complete nonce/child-bound frame, then EOF,
and separately requires exact child exit/reap. It drains the socket even when
the child exits first, so any queued additional nonempty frame still rejects.
EOF before the frame, malformed/extra frames, wrong nonce/PID, nonzero exit,
missing EOF, missing exit, deadline expiry, and any forced cleanup fail.
The 15-second production deadline and 3-second cleanup deadline remain fixed.

Fifteen real local socketpair/direct-child controls passed using the production
collection function, including EOF before pidfd readiness, data pending after
exit, extra data after exit, and both timeout paths. Strict probe and fixture
compilation passed. The former predicate also reproduced the EOF rejection on
a real socket. No local namespace, mount, Android, or pressure operation ran.

Root/nonce are fresh. The three mount arms, held finite own-job cgroup authority,
UID/GID/mode identity comparison, original user namespace, private propagation,
all mount/FD cleanup, Main fences and CPU1/512MiB/120s resource gates are unchanged.
The controller additionally requires the explicit peer_eof result. Local tests
do not qualify the new Pocket4 invocation or attribute the old Owner08 journal.
''')
    files=[]
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            raw=path.read_bytes();files.append({'path':path.relative_to(OUT).as_posix(),'bytes':len(raw),'sha256':sha(raw)})
    put('manifest.json',pretty({'schema':1,'files':files}))
    print(json.dumps({'root':str(OUT),'files':len(files),'request_bytes':len((OUT/'request.json').read_bytes()),'request_sha256':sha((OUT/'request.json').read_bytes()),'stdin_bytes':len(stdin.encode()),'stdin_sha256':sha(stdin.encode()),'manifest_sha256':sha((OUT/'manifest.json').read_bytes()),'diff_sha256':sha(delta.encode()),'diff_bytes':len(delta.encode()),'key':request['idempotency_key']}))

if __name__ == '__main__': main()
