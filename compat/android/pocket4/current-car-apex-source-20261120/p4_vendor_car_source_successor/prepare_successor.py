"""Build an isolated source-only successor; never touches an operator source tree."""
from pathlib import Path
import copy
import difflib
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'base'
OUT = ROOT / 'candidate'
OLD_LOCK = 'android/manifest/production-full-apex-tests-source-lock.json'
NEW_LOCK = 'android/manifest/production-full-car-source-lock.json'
OLD_SHA = '14fd227541b01876c7e34d7e6a1ffcb2a202d97d94c6a8f6e14be369e4b79505'
SERVICES_PATH = 'frameworks/opt/car/services'
SERVICES_NAME = 'platform/frameworks/opt/car/services'
SERVICES_COMMIT = '2bb3349c1a84b9b15c5ef05ef9c2e3dc6dde427a'
SERVICES_PURPOSE = 'Original superproject Car framework system-server module, builtin API and protobuf source required by com.android.car.framework'
SERVICES_CONES = ['builtInServices/api', 'builtInServices/proto', 'builtInServices/src', 'updatableServices/src']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace(text, old, new, count=1):
    assert text.count(old) == count, (old[:100], text.count(old), count)
    return text.replace(old, new)


def read(name):
    return (BASE / name).read_text()


provider_source = (ROOT / 'production_car.rs').read_text()
providers = re.findall(r'\("([^"]+)", "([0-9a-f]{40})", "([^"]+)"\)', provider_source)
assert len(providers) == 18
old = (BASE / OLD_LOCK).read_bytes()
assert sha(old) == OLD_SHA and len(old) == 400720
original = json.loads(old)
current = copy.deepcopy(original)
for path, commit, cone in providers:
    selected = next(x for x in current['projects'] if x['path'] == path)
    assert selected['commit'] == commit and cone not in selected['sparse_paths']
    selected['sparse_paths'].append(cone)
assert not any(x['path'] == SERVICES_PATH for x in current['projects'])
current['projects'].append({'path': SERVICES_PATH, 'name': SERVICES_NAME, 'commit': SERVICES_COMMIT,
                            'purpose': SERVICES_PURPOSE, 'sparse_paths': SERVICES_CONES})
assert len(current['projects']) == 653
new_lock = (json.dumps(current, indent=2, sort_keys=True) + '\n').encode()
changes = {NEW_LOCK: new_lock, 'tools/droidloom-source/src/production_car.rs': provider_source.encode()}

s = read('tools/droidloom-source/src/lib.rs')
s = replace(s, 'pub mod production_apex_tests;', 'pub mod production_apex_tests;\n/// Exact original Car APEX dependency closure; previous profiles remain separate.\npub mod production_car;')
s = replace(s, '    Production652,', '    Production652,\n    Production653,')
s = replace(s, '            Self::Production652 => production_cmake::MAX_PROJECTS,', '            Self::Production652 => production_cmake::MAX_PROJECTS,\n            Self::Production653 => production_car::MAX_PROJECTS,')
s = replace(s, '            Self::Production652 => production_cmake::MAX_SPARSE_PATHS,', '            Self::Production652 => production_cmake::MAX_SPARSE_PATHS,\n            Self::Production653 => production_car::MAX_SPARSE_PATHS,')
s = replace(s, '            Self::Production652 => native_pair::is_project_name(name),', '            Self::Production652 => native_pair::is_project_name(name),\n            Self::Production653 => native_pair::is_project_name(name),')
changes['tools/droidloom-source/src/lib.rs'] = s.encode()

s = read('tools/droidloom-source/src/main.rs')
s = replace(s, '    ProductionFullApexTests,', '    ProductionFullApexTests,\n    ProductionFullCar,')
s = replace(s, '        Profile::ProductionFullApexTests => droidloom_source::production_apex_tests::build_plan,', '        Profile::ProductionFullApexTests => droidloom_source::production_apex_tests::build_plan,\n        Profile::ProductionFullCar => droidloom_source::production_car::build_plan,')
anchor = '        Profile::ProductionFullApexTests => (droidloom_source::production_apex_tests::materialize, droidloom_source::production_apex_tests::reconcile, droidloom_source::production_apex_tests::verify_materialized),'
s = replace(s, anchor, anchor + '\n        Profile::ProductionFullCar => (droidloom_source::production_car::materialize, droidloom_source::production_car::reconcile, droidloom_source::production_car::verify_materialized),')
s = replace(s, 'mod tests {\n    use super::*;', '''mod tests {
    use super::*;

    #[test]
    fn source_cli_requires_named_car_profile_and_preserves_original_652_recovery() {
        for argv in [
            ["droidloom-source", "--profile", "production-full-car", "verify-lock"],
            ["droidloom-source", "verify-lock", "--profile", "production-full-car"],
        ] {
            assert!(matches!(Cli::try_parse_from(argv).unwrap().profile, Profile::ProductionFullCar));
        }
        assert!(matches!(Cli::try_parse_from([
            "droidloom-source", "--profile", "production-full-apex-tests", "verify-lock",
        ]).unwrap().profile, Profile::ProductionFullApexTests));
        assert!(matches!(Cli::try_parse_from([
            "droidloom-source", "verify-lock",
        ]).unwrap().profile, Profile::Audio));
        for alias in ["car", "653", "production-latest", "unbounded"] {
            assert!(Cli::try_parse_from([
                "droidloom-source", "--profile", alias, "verify-lock",
            ]).is_err());
        }
    }''')
changes['tools/droidloom-source/src/main.rs'] = s.encode()

s = read('tools/droidloom-update/src/production_source.rs')
old_constants = '''pub(super) const LOCK_PATH: &str = "android/manifest/production-full-apex-tests-source-lock.json";
pub(super) const LOCK_SHA: &str =
    "14fd227541b01876c7e34d7e6a1ffcb2a202d97d94c6a8f6e14be369e4b79505";
pub(super) const LOCK_BYTES: usize = 400720;'''
new_constants = f'''const APEX_TEST_LOCK_PATH: &str = "{OLD_LOCK}";
const APEX_TEST_LOCK_SHA: &str = "{OLD_SHA}";
const APEX_TEST_LOCK_BYTES: usize = 400720;
pub(super) const LOCK_PATH: &str = "{NEW_LOCK}";
pub(super) const LOCK_SHA: &str = "{sha(new_lock)}";
pub(super) const LOCK_BYTES: usize = {len(new_lock)};'''
s = replace(s, old_constants, new_constants)
start = s.index('pub(super) fn source_lock_path(repo: &Path) -> Result<PathBuf> {')
end = s.index('\n/// Shared source', start)
historical = s[start:end]
historical = replace(historical, 'pub(super) fn source_lock_path', 'fn apex_test_source_lock_path')
historical = replace(historical, 'repo.join(LOCK_PATH)', 'repo.join(APEX_TEST_LOCK_PATH)')
historical = replace(historical, 'exact_file(&path, LOCK_BYTES, LOCK_SHA)', 'exact_file(&path, APEX_TEST_LOCK_BYTES, APEX_TEST_LOCK_SHA)')
new_function = '''
pub(super) fn source_lock_path(repo: &Path) -> Result<PathBuf> {
    let old_path = apex_test_source_lock_path(repo)?;
    let mut expected: Value = serde_json::from_slice(&exact_file(
        &old_path, APEX_TEST_LOCK_BYTES, APEX_TEST_LOCK_SHA,
    )?)?;
    let projects = expected["projects"].as_array_mut()
        .ok_or("original APEX-test projects missing")?;
    for &(path, commit, cone) in droidloom_source::production_car::PROVIDERS {
        let project = projects.iter_mut().find(|project| project["path"] == path)
            .ok_or("original Car dependency project missing")?;
        if project["commit"] != commit {
            return fail("Car provider must retain its original superproject Gitlink");
        }
        project["sparse_paths"].as_array_mut()
            .ok_or("original Car provider sparse scope missing")?.push(json!(cone));
    }
    projects.push(json!({
        "path": droidloom_source::production_car::SERVICES_PATH,
        "name": droidloom_source::production_car::SERVICES_NAME,
        "commit": droidloom_source::production_car::SERVICES_COMMIT,
        "purpose": droidloom_source::production_car::SERVICES_PURPOSE,
        "sparse_paths": droidloom_source::production_car::SERVICES_CONES,
    }));
    let path = repo.join(LOCK_PATH);
    let raw = exact_file(&path, LOCK_BYTES, LOCK_SHA)?;
    if serde_json::from_slice::<Value>(&raw)? != expected {
        return fail("production Car lock differs from the complete fixed original provider closure");
    }
    droidloom_source::production_car::build_plan(&droidloom_source::load_lock(&path)?)?;
    Ok(path)
}
'''
s = s[:start] + historical + new_function + s[end:]
s = replace(s, 'plan: droidloom_source::production_apex_tests::build_plan(lock)?,', 'plan: droidloom_source::production_car::build_plan(lock)?,')
s = replace(s, 'droidloom_source::production_apex_tests::verify_materialized(lock_path, lock, source)?;', 'droidloom_source::production_car::verify_materialized(lock_path, lock, source)?;')
s = replace(s, 'let plan = droidloom_source::production_apex_tests::build_plan(\n', 'let plan = droidloom_source::production_car::build_plan(\n')
s = replace(s, 'assert_eq!(plan.projects.len(), 652);', 'assert_eq!(plan.projects.len(), 653);')
s = s.replace('droidloom-production-full652-', 'droidloom-production-full653-')
s = replace(s, 'mod tests {\n    use super::*;', '''mod tests {
    use super::*;

    #[test]
    fn original_652_apex_manifest_requires_explicit_car_source_reconciliation() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
            .canonicalize().unwrap();
        let old_path = apex_test_source_lock_path(&repo).unwrap();
        let selected = source_lock_path(&repo).unwrap();
        let old = droidloom_source::load_lock(&old_path).unwrap();
        let current = droidloom_source::load_lock(&selected).unwrap();
        assert!(droidloom_source::production_car::build_plan(&old).is_err());
        assert!(droidloom_source::production_apex_tests::build_plan(&current).is_err());
        let prior = droidloom_source::MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: APEX_TEST_LOCK_SHA.into(),
            plan: droidloom_source::production_apex_tests::build_plan(&old).unwrap(),
        };
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("source");
        fs::create_dir(&source).unwrap();
        let manifest = source.join(".droidloom-source-manifest.json");
        let original = serde_json::to_vec_pretty(&prior).unwrap();
        fs::write(&manifest, &original).unwrap();
        assert!(verify_source_workspace(&selected, &current, &source).is_err());
        assert_eq!(fs::read(manifest).unwrap(), original);
        assert_eq!(fs::read_dir(source).unwrap().count(), 1);
    }''')
changes['tools/droidloom-update/src/production_source.rs'] = s.encode()

s = read('tools/droidloom-update/src/android.rs')
for operation in ['materialize', 'verify_materialized']:
    s = replace(s, 'droidloom_source::production_apex_tests::' + operation + '(&lock, &source_lock, source)?;',
                'droidloom_source::production_car::' + operation + '(&lock, &source_lock, source)?;')
changes['tools/droidloom-update/src/android.rs'] = s.encode()

for name, count in [('coherent_images.rs', 3), ('official_vendor.rs', 1)]:
    s = read('tools/droidloom-update/src/' + name)
    s = replace(s, 'droidloom-production-full652-', 'droidloom-production-full653-', count=count)
    changes['tools/droidloom-update/src/' + name] = s.encode()

s = read('tools/droidloom-update/src/coherent_images_tests.rs')
s = replace(s, '../../../' + OLD_LOCK, '../../../' + NEW_LOCK)
s = replace(s, '"schema": "droidloom-production-full652-inputs-v1",', '"schema": "droidloom-production-full653-inputs-v1",')
s = replace(s, '    for (schema, source_sha) in [\n', f'''    for (schema, source_sha) in [
        ("droidloom-production-full653-inputs-v1", "{OLD_SHA}"),
        ("droidloom-production-full652-inputs-v1", actual_sha.as_str()),
        ("droidloom-production-full652-inputs-v1", "{OLD_SHA}"),
''')
changes['tools/droidloom-update/src/coherent_images_tests.rs'] = s.encode()

for name in ['framework_asb_security.rs', 'wm_security.rs']:
    s = read('tools/droidloom-update/src/' + name)
    s = replace(s, 'let plan = droidloom_source::production_apex_tests::build_plan(&lock).unwrap();',
                'let plan = droidloom_source::production_car::build_plan(&lock).unwrap();')
    s = replace(s, 'assert_eq!(plan.projects.len(), 652);', 'assert_eq!(plan.projects.len(), 653);')
    anchor = '''        assert_eq!(&plan.projects[..651], expected_projects.as_slice());'''
    added = '''        for &(path, _, cone) in droidloom_source::production_car::PROVIDERS {
            expected_projects.iter_mut()
                .find(|project| project.path == Path::new(path))
                .unwrap().sparse_paths.push(cone.into());
        }
'''
    s = replace(s, anchor, added + anchor)
    changes['tools/droidloom-update/src/' + name] = s.encode()

s = read('tools/droidloom-update/src/settings_asb_security_tests.rs')
s = replace(s, 'assert_eq!(parsed.projects.len(), 652);', 'assert_eq!(parsed.projects.len(), 653);')
anchor = '''            for &(provider, _, cone) in droidloom_source::production_apex_tests::PROVIDERS {
                if path == Path::new(provider) {
                    expected_sparse.push(cone.into());
                }
            }'''
s = replace(s, anchor, anchor + '''
            for &(provider, _, cone) in droidloom_source::production_car::PROVIDERS {
                if path == Path::new(provider) {
                    expected_sparse.push(cone.into());
                }
            }''')
anchor = '''        let settings = parsed
            .projects'''
s = replace(s, anchor, '''        let service = &parsed.projects[652];
        assert_eq!(service.path, Path::new(droidloom_source::production_car::SERVICES_PATH));
        assert_eq!(service.name, droidloom_source::production_car::SERVICES_NAME);
        assert_eq!(service.commit, droidloom_source::production_car::SERVICES_COMMIT);
        assert_eq!(service.purpose, droidloom_source::production_car::SERVICES_PURPOSE);
        assert_eq!(service.sparse_paths, droidloom_source::production_car::SERVICES_CONES
            .iter().map(PathBuf::from).collect::<Vec<_>>());
''' + anchor)
changes['tools/droidloom-update/src/settings_asb_security_tests.rs'] = s.encode()

OUT.mkdir(exist_ok=True)
patch = ''
records = []
for name, after in changes.items():
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(after)
    before_path = BASE / name
    before = before_path.read_bytes() if before_path.exists() else b''
    records.append({'path': name, 'before': {'bytes': len(before), 'sha256': sha(before)} if before_path.exists() else None,
                    'after': {'bytes': len(after), 'sha256': sha(after)}})
    patch += ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                        fromfile='a/' + name if before_path.exists() else '/dev/null', tofile='b/' + name))
(ROOT / 'changes.patch').write_text(patch)
manifest = {'schema': 'p4-production-original-car-source-successor-v1',
            'base_source_tree': 'fd0ef624e436d1eb5c8d2c4083335088811a6a42',
            'base_profile_lock': {'path': OLD_LOCK, 'bytes': len(old), 'sha256': OLD_SHA},
            'new_profile_lock': {'path': NEW_LOCK, 'bytes': len(new_lock), 'sha256': sha(new_lock)},
            'changes': records, 'projects': 653, 'existing_provider_cones_added': providers,
            'new_project': current['projects'][-1], 'old_652_recovery_profiles_unchanged': True,
            'strict_dependencies_and_selinux_neverallows_unchanged': True,
            'materialized': False, 'compiled': False, 'soong_passed': False, 'runtime_qualified': False,
            'production_ready': False, 'normal_vendor_result_filename': 'droidloom-production-full653-vendor-normal-result.json',
            'patch': {'path': 'changes.patch', 'bytes': len(patch.encode()), 'sha256': sha(patch.encode())}}
(ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
print(json.dumps({'new_lock': manifest['new_profile_lock'], 'changes': len(changes), 'patch': manifest['patch']}))
