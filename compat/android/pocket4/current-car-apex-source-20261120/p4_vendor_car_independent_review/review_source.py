"""Independent finite review of the frozen Car source successor; no host build."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'p4_vendor_car_source_successor'
AUDIT = HERE.parent / 'p4_vendor_car_source_audit'


def pin(path):
    body = path.read_bytes()
    return {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


def exact(path, expected):
    actual = pin(path)
    assert {k: actual[k] for k in ('bytes', 'sha256')} == expected
    return actual


manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
closure = json.loads((ROOT / 'SOURCE-CLOSURE.json').read_text())
before = json.loads((ROOT / 'base' / manifest['base_profile_lock']['path']).read_text())
after = json.loads((ROOT / 'candidate' / manifest['new_profile_lock']['path']).read_text())
inputs = [pin(ROOT / n) for n in ('MANIFEST.json', 'HANDOFF.json', 'SOURCE-CLOSURE.json',
                                  'changes.patch', 'STATIC-SOURCE-CONTROLS.json')]
changes = []
for row in manifest['changes']:
    entry = {'path': row['path'], 'after': exact(ROOT / 'candidate' / row['path'], row['after'])}
    if row['before'] is not None:
        entry['before'] = exact(ROOT / 'base' / row['path'], row['before'])
    changes.append(entry)
assert len(changes) == 12

# Forward construct the complete allowed new lock; every non-extension field remains exact.
expected = copy.deepcopy(before)
by_path = {p['path']: p for p in expected['projects']}
assert len(expected['projects']) == len(by_path) == 652
for path, commit, cone in manifest['existing_provider_cones_added']:
    project = by_path[path]
    assert project['commit'] == commit and cone not in project['sparse_paths']
    project['sparse_paths'].append(cone)
expected['projects'].append(manifest['new_project'])
assert len(manifest['existing_provider_cones_added']) == 18
assert expected == after and len(after['projects']) == 653
assert max(len(p.get('sparse_paths', [])) for p in after['projects']) <= 534
assert after['policy'] == before['policy'] == {
    'add_dependencies_only_from_superproject': True,
    'allow_unrestricted_repo_sync': False,
    'base_partitions_come_from_aosp_ci_artifact': True,
    'require_exact_commits': True,
}
assert after['superproject'] == before['superproject']
assert after['superproject']['commit'] == '28f0bbddc24d56c8ec5a8df5342ac7a292184039'

# Authenticate the new project's fixed Gitlink against the retrieved original superproject body.
observation = json.loads((AUDIT / 'actual-manifest-observation.json').read_text())
gitlink = observation['upstream_superproject']
body = gitlink['body'].encode()
assert len(body) == gitlink['bytes'] and hashlib.sha256(body).hexdigest() == gitlink['sha256']
assert gitlink['url'] == ('https://android.googlesource.com/platform/superproject/+/'
                          + after['superproject']['commit'] + '/frameworks/opt/car/?format=JSON')
assert body.startswith(b")]}'\n")
entries = json.loads(body[5:])['entries']
assert [e for e in entries if e['name'] == 'services'] == [{
    'mode': 57344, 'type': 'commit', 'id': '2bb3349c1a84b9b15c5ef05ef9c2e3dc6dde427a',
    'name': 'services',
}]
assert manifest['new_project']['commit'] == entries[0]['id']

raw_evidence = []
for row in closure['source_raw_evidence']:
    raw_evidence.append(exact(HERE.parent / row['path'], {k: row[k] for k in ('bytes', 'sha256')}))
assert len(raw_evidence) == 24

# Recompute which actual BP files become visible under ordinary Git cone semantics.
def selected(path, cones):
    file = PurePosixPath(path)
    return not cones or any(file == cone or cone in file.parents or file.parent == cone
                            or file.parent in cone.parents for cone in map(PurePosixPath, cones))

old_car = next(p for p in before['projects'] if p['path'] == 'packages/services/Car')
new_car = next(p for p in after['projects'] if p['path'] == 'packages/services/Car')
physical = json.loads((AUDIT / 'car-physical-scope-observation.json').read_text())[0]
assert physical['args'] == ['ls-tree', '-r', '--name-only', old_car['commit']]
assert physical['exit'] == 0
new_blueprints = sorted(p for p in physical['selected_paths'] if p.endswith('/Android.bp')
                        and selected(p, new_car['sparse_paths'])
                        and not selected(p, old_car['sparse_paths']))
assert new_blueprints == sorted(p['path'] for p in closure['new_car_blueprints'])
assert len(new_blueprints) == 12

# This exact complete-file equality covers the whole original recovery/Projection code.
android_path = 'tools/droidloom-update/src/android.rs'
old_android = (ROOT / 'base' / android_path).read_bytes()
new_android = (ROOT / 'candidate' / android_path).read_bytes()
assert new_android.count(b'droidloom_source::production_car::materialize(&lock, &source_lock, source)?;') == 1
assert new_android.count(b'droidloom_source::production_car::verify_materialized(&lock, &source_lock, source)?;') == 1
reversed_android = new_android.replace(
    b'droidloom_source::production_car::materialize(&lock, &source_lock, source)?;',
    b'droidloom_source::production_apex_tests::materialize(&lock, &source_lock, source)?;'
).replace(
    b'droidloom_source::production_car::verify_materialized(&lock, &source_lock, source)?;',
    b'droidloom_source::production_apex_tests::verify_materialized(&lock, &source_lock, source)?;'
)
assert reversed_android == old_android
historical = ['native_pair.rs', 'production_full.rs', 'production_cmake.rs',
              'production_lint.rs', 'production_apex_tests.rs']
assert all(not (ROOT / 'candidate/tools/droidloom-source/src' / name).exists() for name in historical)
assert all('tools/droidloom-source/src/' + name not in {c['path'] for c in changes} for name in historical)

# Apply validation is read-only; both the before and after complete files are checked.
patch = (ROOT / 'changes.patch').read_bytes()
patch_checks = []
for directory, flags in [('base', ['--check']), ('candidate', ['--check', '--reverse'])]:
    result = subprocess.run(['git', 'apply', *flags, '-'], input=patch,
                            cwd=ROOT / directory, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr.decode()
    patch_checks.append({'direction': directory, 'exit_code': result.returncode,
                         'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr)})

# Named source tests are counted, never executed by this review.
test_pattern = re.compile(r'#\[test\]\s*(?:#\[[^\n]*\]\s*)*fn\s+(\w+)\s*\(')
added = []
retained = 0
for row in manifest['changes']:
    if not row['path'].endswith('.rs'):
        continue
    current = test_pattern.findall((ROOT / 'candidate' / row['path']).read_text())
    original = test_pattern.findall((ROOT / 'base' / row['path']).read_text()) if row['before'] else []
    assert len(set(current)) == len(current)
    assert set(original) <= set(current)
    retained += len(original)
    added.extend({'path': row['path'], 'name': name} for name in current if name not in original)
assert len(added) == 8

source = (ROOT / 'candidate/tools/droidloom-update/src/production_source.rs').read_text()
coherent = (ROOT / 'candidate/tools/droidloom-update/src/coherent_images.rs').read_text()
vendor = (ROOT / 'candidate/tools/droidloom-update/src/official_vendor.rs').read_text()
assert 'droidloom-production-full653-inputs-v1' in source and 'droidloom-production-full653-inputs-v1' in coherent
assert 'droidloom-production-full653-vendor-normal-result.json' in source and 'droidloom-production-full653-vendor-normal-result.json' in vendor
assert 'strict_allow_missing_dependencies' in source and 'selinux_ignore_neverallows' in source

report = {
    'schema': 'p4-car-source-independent-semantic-review-v1',
    'reviewer': 'android_runtime_audit',
    'author': 'android_apps_cleanup_audit',
    'passed_source_review': True,
    'inputs': inputs,
    'changes': changes,
    'checks': {
        'complete_652_lock_preserved_with_only_18_cones_and_one_gitlink_project': True,
        'original_superproject_gitlink_body_and_source_pins_verified': True,
        'retrieved_original_blueprint_bodies_verified': len(raw_evidence),
        'new_car_blueprints_recomputed_from_original_tree': new_blueprints,
        'all_ten_modified_file_hunks_and_two_additions_semantically_reviewed': True,
        'complete_android_recovery_and_projection_bytes_preserved': True,
        'historical_source_profile_modules_not_changed': historical,
        'forward_reverse_patch_checks': patch_checks,
        'normal_input_and_vendor_result_schema_consumers_synchronized_to_653': True,
        'original_strict_soong_and_selinux_neverallow_requirements_retained': True,
        'old_named_tests_retained_in_changed_files': retained,
        'new_ordinary_test_sources': added,
    },
    'semantic_notes': [
        'Production653 is an explicit new profile. build_plan compares the complete derived plan to the exact immutable 652 predecessor plus the fixed Car cones and project, and separately preserves status, selected_at and source_ref.',
        'The unchanged generic validator rejects unknown JSON fields, malformed/duplicate paths and projects, nonofficial remote, changed policy and invalid exact commits before materialization. New wrappers validate the complete Car profile before invoking unchanged atomic materialize/reconcile/verify operations.',
        'The original APEX declaration supplies com.android.car.framework, android.car-module, CarServiceUpdatable, ScriptExecutor, and the original classpath fragments. The new framework services project supplies car-frameworks-service-module, builtin API and protobuf providers from the authenticated same superproject Gitlink.',
        'The complete service/proto/res/src, ScriptExecutor/res/src, generated props, watchdog/procfs clients, telemetry and power AIDL cones supply the original declarations. The unavoidable telemetry daemon ancestor BP requires actual src and tests; its unrelated sampleclient remains excluded.',
        'The original apex JNI list is commented out; no new service/jni dependency is manufactured. Immediate ancestor files (manifests, resource configuration, BP/rc/XML and API metadata) are retained by the existing cone materializer.',
        'The updater validates the full old lock chain before deriving and exact-hashing the new lock, requires explicit reconciliation of existing old source manifests, and does not automatically rewrite a 652 workspace during verification.',
        'Only the two normal production materializer/verification calls change in android.rs; complete-file inverse equality establishes that recover and Projection code remain unchanged.',
    ],
    'limits': [
        'This is independent source and retrieved-evidence review. It does not execute Rust, materialize AOSP, run Soong or access AI395/Pocket4 runtime.',
        'The retained external dependency references still require real normal Soong variant, visibility, source and type checks. Static closure is not a complete normal build success claim.',
        'Eight added Rust tests remain pending the next coherent full-source CI. Old named tests are preserved, with expected profile/consumer assertions updated where required.',
    ],
    'rust_compiled_by_this_review': False,
    'normal_soong_passed': False,
    'materialized': False,
    'runtime_qualified': False,
    'production_ready': False,
    'CURRENT_writes': 0,
}
out = HERE / 'SOURCE-REVIEW.json'
out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'report': pin(out), 'new_tests': len(added), 'old_tests_retained': retained,
                  'new_blueprints': len(new_blueprints), 'passed_source_review': True}))
