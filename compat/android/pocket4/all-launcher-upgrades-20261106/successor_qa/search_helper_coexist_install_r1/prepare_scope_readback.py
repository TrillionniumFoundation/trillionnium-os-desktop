#!/usr/bin/env python3
"""Locally derive one fixed metadata reader from the actual install receipt."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'post_install_scope_readback_r1'
PARENT = PROJECT / 'successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1'
ACTUAL = HERE / 'host-candidate-r1/actual-install'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def functions(source):
    lines = source.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


def main():
    source_path = PARENT / 'read_actual_scope_once.py'
    source = source_path.read_text()
    assert pin(source_path)['bytes'] == 3557 and pin(source_path)['sha256'] == '06a5319f04bd54eacf359c73bfd8a0aa51a027aad8d7b5333a9674e1ffb29c08'
    original = (ACTUAL / 'stdout.original.json').read_bytes()
    terminal_raw = (ACTUAL / 'terminal.original.json').read_bytes()
    assert len(original) == 33582 and sha(original) == '5d7d4e22f8351a3ab58b99bb9236bda69bcf51a1a3a115f079f2834d8d83fbcf'
    assert len(terminal_raw) == 733 and sha(terminal_raw) == '5350ed913cfb078591d6bf2a13a7fc39b7f74990d9e26009f38bb16a67365bfc'
    value, terminal = json.loads(original), json.loads(terminal_raw)
    assert terminal['job_id'] == '1a1b34fadf6-fc05-81f2' and terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[k] is True for k in ('audit_recorded','output_complete','output_durable','terminal_publication_confirmed'))
    assert all(terminal[k] is False for k in ('timed_out','cancelled','automatic_retry'))
    assert terminal['log_bytes'] == {'stdout': {'seen':33582,'stored':33582}, 'stderr': {'seen':0,'stored':0}}
    assert terminal['log_synced'] == {'stdout':True,'stderr':True} and terminal['log_truncated'] == {'stdout':False,'stderr':False}
    assert terminal['log_errors'] == {'stdout':None,'stderr':None}
    assert value['ok'] is True and value['errors'] == [] and value['helper_uid'] == 10167
    assert value['observed_explicit_packages'] == 49 and value['observed_APKs'] == 89 and value['all_original48_unchanged'] is True
    expected = {'bytes':60614, 'path':'/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/install-search-helper-r2-01/app-scope-after.private.json',
                'sha256':'7187bc544cf6812ad47efdf141cd111897a1124b9532f84b7cf599b0c0fee1e3'}
    assert value['next_app_scope'] == expected
    joint = dict(value); joint_pin = joint.pop('joint_artifact')
    joint_raw = json.dumps(joint,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    assert len(joint_raw) == joint_pin['bytes'] == 33367 and sha(joint_raw) == joint_pin['sha256'] == '19f172494dcf57397d19c95934dd9e2ff1826d11fa601e7098ac5d87516b703b'
    assignment = next(n for n in ast.parse(source).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id == 'PIN')
    lines = source.splitlines(keepends=True)
    lines[assignment.lineno-1:assignment.end_lineno] = ['PIN = ' + repr(expected) + '\n']
    new_source = ''.join(lines).replace('pocket4-zbj-post-install48-scope-readback-v1','pocket4-owned-r2-post-install49-scope-readback-v1')
    old_functions, new_functions = functions(source), functions(new_source)
    assert old_functions['need'] == new_functions['need'] and old_functions['census'] == new_functions['census']
    assert old_functions['main'].replace('pocket4-zbj-post-install48-scope-readback-v1','pocket4-owned-r2-post-install49-scope-readback-v1') == new_functions['main']
    compile(new_source, '<fixed-scope49-reader>', 'exec')
    OUT.mkdir(exist_ok=False)
    (OUT / 'read_actual_scope_once.py').write_text(new_source)
    (OUT / 'source-against-actual-zbj-reader.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True), new_source.splitlines(True),
        fromfile=str(source_path.relative_to(PROJECT)), tofile=str((OUT/'read_actual_scope_once.py').relative_to(PROJECT)))))
    packet = json.loads((PARENT / 'process-request.review-only.json').read_bytes())
    assert packet['args'][-1] == source
    packet['args'][-1] = new_source
    packet['idempotency_key'] = 'pocket4-owned-r2-post-install49-scope-readback-r1-20261107'
    (OUT / 'process-request.review-only.json').write_text(json.dumps(packet,sort_keys=True,indent=2)+'\n')
    manifest = {'schema':'pocket4-owned-r2-post-install49-reader-source-pins-v1',
        'inputs':[pin(source_path), pin(PARENT/'process-request.review-only.json'),pin(ACTUAL/'stdout.original.json'),pin(ACTUAL/'terminal.original.json'),pin(Path(__file__))],
        'outputs':[pin(p) for p in sorted(OUT.iterdir()) if p.is_file()], 'actual_scope_pin':expected,
        'changes_only':['exact actual installed49 metadata pin','output schema label','independent request idempotency key'],
        'need_and_census_unchanged':True,'main_unchanged_except_schema':True,'reading_already_published_metadata_only':True,
        'new_runtime_observation':False,'Main_commands':0,'namespace_entries':0,'UI_actions':0,'permission_changes':0,
        'remote_submitted':False,'scope_raw_available_locally':False,'reconstructed':False}
    (OUT / 'SOURCE_PINS.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'status':'FIXED_READONLY_REQUEST_PREPARED_NOT_SUBMITTED','outputs':[pin(p) for p in sorted(OUT.iterdir()) if p.is_file()]},sort_keys=True))


if __name__ == '__main__':
    main()
