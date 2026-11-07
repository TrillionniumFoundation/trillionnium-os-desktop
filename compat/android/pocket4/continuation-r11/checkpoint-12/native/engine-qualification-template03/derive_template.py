#!/usr/bin/env python3
"""Prepare candidate07 artifact bindings; retain all original qualification runners."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
BASE = WORK / 'engine-qualification-template-02'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        assert stream.write(raw) == len(raw)


def exact(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    old_raw = (BASE / 'make_qualification.py').read_bytes()
    assert sha(old_raw) == '7f0cef4c9ebb4f339c140925b0f74fe8b6a8986c0c3b18cdad8c08cdf893ff96'
    old = old_raw.decode()
    text = old.replace('candidate06', 'candidate07').replace('combined06', 'combined07')
    text = exact(text, 'CANDIDATE_MANIFEST = "3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376"',
                 'CANDIDATE_MANIFEST = "e10024548a5b2b5a391ecc9ddb3ea2f19b95a6fea3437f40207a0f4721745a93"')
    text = exact(text, 'PARENT_MANIFEST = "4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba"',
                 'PARENT_MANIFEST = "3c780a398075f77d1f6b1c477c6ceaa35349de17b88e77896aa22820259c0376"')
    text = exact(text, 'COMPOSITION_SHA = "f49173e0527e336f5d5ff5af489a2dfa97ceaba247f0fc3657c9a68ca242922a"',
                 'COMPOSITION_SHA = "44d4b170ed158802cd12a5f59fd3ebf31d86bce6a621b6f2904f13fed8737f08"\n'
                 'UAPI_TU_GATE_SHA = "5a09aa094c960a2bcc2d357fa732aac0cdb95203d25d3b690ced62497bb1c1d1"')
    begin = text.index('def readmission_binding(config, root):')
    end = text.index('def build_binding(config):', begin)
    helper = '''def prior_candidate06_failure_preserved():
    # These are the original failed predecessor build receipts, never candidate07
    # acceptance evidence. The new candidate uses a fresh root and fence01.
    inner = read_reference("prior-candidate06-inner-failure.json")
    outer = read_reference("prior-candidate06-outer-failure.json")
    need(inner["state"] == "FAILED" and inner["builder_returncode"] == 1 and
         inner["artifact_gate"] is None and inner["cleanup"]["complete"] is True and
         outer["state"] == "FAILED" and outer["inner_returncode"] == 1,
         "failed candidate06 predecessor evidence was not retained exactly")


'''
    text = text[:begin] + helper + text[end:]
    text = text.replace('== 925', '== 926').replace('engine925.json', 'engine926.json').replace('complete925', 'complete926')
    text = exact(text, 'prep["actual_candidate07_composition_sha256"] == COMPOSITION_SHA and',
                 'prep["actual_candidate07_composition_sha256"] == COMPOSITION_SHA and\n'
                 '         prep["actual_complete_TU_gate_sha256"] == UAPI_TU_GATE_SHA and')
    text = exact(text, 'str(root / "build-fences-02/terminal.json")', 'str(root / "build-fences-01/terminal.json")')
    text = exact(text, '    readmission_binding(config, root)\n', '    prior_candidate06_failure_preserved()\n')
    ast.parse(text)
    put('make_qualification.py', text.encode())
    put('template02-to-candidate07.patch', ''.join(difflib.unified_diff(
        old.splitlines(True), text.splitlines(True), fromfile='template02/make_qualification.py',
        tofile='template03/make_qualification.py')).encode())
    reference_pins = json.loads((BASE / 'reference-pins.json').read_bytes())
    for name, row in reference_pins['files'].items():
        raw = (BASE / 'references' / name).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
        put('references/' + name, raw)
    controller = WORK / 'full-engine-candidate07-go5-bound-01/combined_build_streaming.py'
    assert sha(controller.read_bytes()) == '702697443b0e1ffa351733a29141be866a81b8be2d2b210b3d36963aa49f5058'
    scope = {'__name__': 'read_only_frozen_plan', '__file__': str(controller)}
    exec(compile(controller.read_bytes(), str(controller), 'exec'), scope, scope)
    extra = {'candidate07-build-plan.json': encode(scope['plan']()),
             'candidate07-engine926.json': (WORK / 'candidate07-host-uapi-integration-01/expected-engine926.json').read_bytes()}
    evidence = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/candidate06-go5-build02')
    for source, name, expected in (
        ('attempt-01/terminal.json','prior-candidate06-inner-failure.json','51b2d236f90ebb709eb907e7fa6ad64a7b017822faec1655c5c23b12f0c0b19a'),
        ('build-fences-02/terminal.json','prior-candidate06-outer-failure.json','1abb05239ee80d9afbd208f760541956606746f6249986b4f5078a7e0233bc72')):
        raw = (evidence / source).read_bytes()
        assert sha(raw) == expected
        extra[name] = raw
    for name, raw in extra.items():
        assert name not in reference_pins['files']
        put('references/' + name, raw)
        reference_pins['files'][name] = {'bytes': len(raw), 'sha256': sha(raw)}
    reference_pins['source_scope'] = ('All 20 original R1/R5 and candidate06 references retained byte-for-byte; '
                                      'four new candidate07 plan/source and original candidate06 failure references. '
                                      'No runner or suite changed or executed.')
    put('reference-pins.json', encode(reference_pins))
    config = json.loads((BASE / 'binding.template.json').read_bytes())
    for row in config['build'].values():
        row['path'] = row['path'].replace('combined06', 'combined07')
    config['build']['fence']['path'] = config['build']['fence']['path'].replace('build-fences-02', 'build-fences-01')
    del config['readmission']
    put('binding.template.json', encode(config))
    old_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(old).body if isinstance(n, ast.FunctionDef)}
    new_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    unchanged = sorted(k for k in old_functions.keys() & new_functions.keys() if old_functions[k] == new_functions[k])
    changed = sorted(k for k in old_functions.keys() & new_functions.keys() if old_functions[k] != new_functions[k])
    put('LOCAL_SOURCE_BINDING.json', encode({
        'schema': 1, 'state': 'UNBOUND_ACTUAL_ARTIFACTS_REQUIRED',
        'original_generator_sha256': sha(old_raw), 'new_generator_sha256': sha(text.encode()),
        'all_20_prior_references_unchanged': True, 'new_references': sorted(extra),
        'unchanged_functions': unchanged, 'changed_functions': changed,
        'new_root_fence01_required': True, 'old_candidate06_failures_preserved': True,
        'full_host_suite_and_four_signal_runners_unchanged': True,
        'tests_executed': False, 'remote_requests_dispatched': 0, 'production_ready': False}))
    print(json.dumps({'generator_sha256': sha(text.encode()), 'references': len(reference_pins['files']),
                      'full_host_suite_and_signal_runners_unchanged': True, 'remote_actions': 0}))


if __name__ == '__main__':
    main()
