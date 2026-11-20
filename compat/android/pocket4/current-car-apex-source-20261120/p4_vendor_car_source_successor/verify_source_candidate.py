"""Finite source checks against retrieved original BP declarations; no build/runtime."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT.parent / 'p4_vendor_car_source_audit'
BASE = ROOT / 'base'
CANDIDATE = ROOT / 'candidate'


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def selected(path, cones):
    path = PurePosixPath(path)
    parent = path.parent
    return not cones or any(path == c or c in path.parents or c == parent or parent in c.parents
                            for c in map(PurePosixPath, cones))


def string_references(body):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/|[A-Za-z_][A-Za-z0-9_]*|[^\s]', body, re.S)
    tokens = [x for x in tokens if not x.startswith(('//', '/*'))]
    properties = {'defaults', 'libs', 'static_libs', 'shared_libs', 'header_libs', 'jni_libs',
                  'whole_static_libs', 'generated_headers', 'export_generated_headers',
                  'bootclasspath_fragments', 'systemserverclasspath_fragments', 'contents',
                  'additional_stubs', 'required', 'tools', 'srcs', 'java_resources', 'imports',
                  'vintf_fragment_modules', 'impl_only_libs', 'stub_only_libs', 'flags_packages'}
    refs = []
    for i in range(len(tokens) - 2):
        if tokens[i] not in properties or tokens[i + 1:i + 3] != [':', '[']:
            continue
        depth = 1
        for token in tokens[i + 3:]:
            depth += token == '['
            depth -= token == ']'
            if not depth:
                break
            if token.startswith('"'):
                value = json.loads(token)
                if tokens[i] not in ('srcs', 'java_resources') or value.startswith(':'):
                    refs.append((tokens[i], value.lstrip(':')))
    return refs


manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
old = json.loads((BASE / manifest['base_profile_lock']['path']).read_text())
new = json.loads((CANDIDATE / manifest['new_profile_lock']['path']).read_text())
reversed_value = copy.deepcopy(new)
assert reversed_value['projects'].pop() == manifest['new_project']
for path, commit, cone in reversed(manifest['existing_provider_cones_added']):
    project = next(x for x in reversed_value['projects'] if x['path'] == path)
    assert project['commit'] == commit and project['sparse_paths'].pop() == cone
assert reversed_value == old
assert len(old['projects']) == 652 and len(new['projects']) == 653
for row in manifest['changes']:
    assert pin(CANDIDATE / row['path']) == row['after']
    if row['before'] is not None:
        assert pin(BASE / row['path']) == row['before']
patch = (ROOT / 'changes.patch').read_bytes()
for directory, flags in [(BASE, ['--check']), (CANDIDATE, ['--check', '--reverse'])]:
    result = subprocess.run(['git', 'apply', *flags, '-'], cwd=directory, input=patch,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    assert result.returncode == 0, result.stderr.decode()

old_car = next(x for x in old['projects'] if x['path'] == 'packages/services/Car')
new_car = next(x for x in new['projects'] if x['path'] == 'packages/services/Car')
tree = json.loads((AUDIT / 'car-physical-scope-observation.json').read_text())[0]['selected_paths']
bp_paths = [x for x in tree if x.endswith('/Android.bp')]
new_bps = sorted(x for x in bp_paths if selected(x, new_car['sparse_paths']) and not selected(x, old_car['sparse_paths']))
assert len(new_bps) == 12, new_bps
module_index = json.loads((AUDIT / 'original-module-index.json').read_text())[0]
assert module_index['exit'] == 0 and module_index['stderr'] == ''
modules = {}
for line in module_index['body'].splitlines():
    match = re.fullmatch(r'[0-9a-f]{40}:(.*?):(\d+):\s*name:\s*"([^"]+)",?\s*', line)
    if match:
        modules.setdefault(match[3], set()).add(match[1])


def original_definition(name):
    if name in modules:
        return name
    for suffix in ('.stubs.module_lib', '.stubs.system', '.stubs.test', '.stubs', '.impl', '-java', '-ndk', '-cpp'):
        if name.endswith(suffix) and name[:-len(suffix)] in modules:
            return name[:-len(suffix)]
    bare = re.sub(r'-V[0-9]+(?:-(?:java|ndk|cpp)(?:-source)?)?$', '', name)
    return bare if bare in modules else None


edges = []
external = []
for name in new_bps:
    body = (AUDIT / 'upstream' / name).read_text()
    for property_name, reference in string_references(body):
        definition = original_definition(reference)
        if definition is None:
            external.append({'from': name, 'property': property_name, 'reference': reference})
            continue
        possible = sorted(modules[definition])
        retained = [x for x in possible if selected(x, new_car['sparse_paths'])]
        assert retained, (name, reference, possible)
        edges.append({'from': name, 'property': property_name, 'reference': reference,
                      'definition': definition, 'original_providers': retained,
                      'previously_selected': all(selected(x, old_car['sparse_paths']) for x in retained)})

# Historical source restoration is byte-identical: only the normal future build's
# two production materializer call sites changed anywhere in android.rs.
a = (BASE / 'tools/droidloom-update/src/android.rs').read_text()
b = (CANDIDATE / 'tools/droidloom-update/src/android.rs').read_text()
for operation in ['materialize', 'verify_materialized']:
    b = b.replace('droidloom_source::production_car::' + operation + '(&lock, &source_lock, source)?;',
                  'droidloom_source::production_apex_tests::' + operation + '(&lock, &source_lock, source)?;')
assert a == b
assert not any((CANDIDATE / ('tools/droidloom-source/src/' + name)).exists()
               for name in ['production_full.rs', 'production_cmake.rs', 'production_lint.rs', 'production_apex_tests.rs'])
tests = []
for row in manifest['changes']:
    if row['path'].endswith('.rs'):
        after = (CANDIDATE / row['path']).read_text()
        before = (BASE / row['path']).read_text() if row['before'] else ''
        for name in re.findall(r'#\[test\]\s*fn ([A-Za-z0-9_]+)', after):
            if not re.search(r'\bfn ' + re.escape(name) + r'\b', before):
                tests.append({'path': row['path'], 'name': name})
assert len(tests) == 8
report = {'schema': 'p4-car-source-successor-finite-static-controls-v1',
          'passed_static_checks': True, 'exact_reverse_new_lock_equals_original_652': True,
          'full_forward_reverse_patch_checks': True, 'historical_recover_function_and_projection_code_byte_identical': True,
          'historical_source_profiles_not_modified': True,
          'new_car_blueprints': [{'path': x, **pin(AUDIT / 'upstream' / x)} for x in new_bps],
          'original_car_internal_edges': edges, 'new_car_edges_all_have_actual_selected_original_providers': True,
          'external_edges_for_normal_soong_validation': external,
          'new_rust_test_sources': tests, 'rust_tests_executed': False, 'rust_compiled': False,
          'complete_global_soong_graph_passed': False, 'operator_tree_changed': False,
          'runtime_qualified': False, 'production_ready': False,
          'limitations': ['Static references cover actual new Car BP arrays and source-filegroup edges. They do not replace normal Soong variant/type/source/visibility evaluation.',
                          'Original 652-project dependencies remain pinned; future materialization and normal full build must validate their real transitive variants.']}
p = ROOT / 'STATIC-SOURCE-CONTROLS.json'
p.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'report': str(p), **pin(p), 'new_car_blueprints': len(new_bps), 'car_edges': len(edges), 'external_edges': len(external), 'new_rust_tests': len(tests)}))
