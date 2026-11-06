#!/usr/bin/env python3
"""Offline source derivation only; never materialize, compile, or touch Android."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "candidate-r3"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def replace_one(text, old, new):
    assert text.count(old) == 1, (old[:120], text.count(old))
    return text.replace(old, new, 1)

before_bytes = (ROOT / "reference/builder469-native_role_ingress.rs").read_bytes()
before = before_bytes.decode()
old_lock_bytes = (ROOT.parent / "normal05/source-r2/actual-provider-source-lock.json").read_bytes()
new_lock_bytes = (ROOT / "candidate-lock-r1/m2-role-ingress-provider3-source-lock.draft.json").read_bytes()
assert len(old_lock_bytes) == 96957
assert digest(old_lock_bytes) == "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d"
assert len(new_lock_bytes) == 103409
assert digest(new_lock_bytes) == "f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772"
old_lock = json.loads(old_lock_bytes)
new_lock = json.loads(new_lock_bytes)
assert len(old_lock["projects"]) == 225 and len(new_lock["projects"]) == 242
old_projects = {p["path"]: p for p in old_lock["projects"]}
assert [p["path"] for p in new_lock["projects"][:225]] == list(old_projects)
extensions = []
expected = json.loads(old_lock_bytes)
for before_project, after_project in zip(expected["projects"], new_lock["projects"]):
    if before_project == after_project:
        continue
    assert before_project["path"] == after_project["path"]
    old_paths = before_project["sparse_paths"]
    new_paths = after_project["sparse_paths"]
    assert new_paths[:len(old_paths)] == old_paths
    additions = new_paths[len(old_paths):]
    assert additions and len(set(new_paths)) == len(new_paths) and len(new_paths) <= 256
    check = dict(after_project)
    check["sparse_paths"] = old_paths
    assert check == before_project
    extensions.append((before_project["path"], additions))
    before_project["sparse_paths"] = new_paths
additions = new_lock["projects"][225:]
assert len(additions) == 17 and len(extensions) == 9
assert all(p["path"] not in old_projects for p in additions)
expected["projects"].extend(additions)
assert expected == new_lock

consts = "const SYSTEMUI_PROVIDER_EXTENSIONS: &[(&str, &[&str])] = &[\n"
for project, paths in extensions:
    consts += "    (" + json.dumps(project) + ", &[" + ", ".join(json.dumps(x) for x in paths) + "]),\n"
consts += "];\n"
consts += 'const SYSTEMUI_PROVIDER_ADDITIONS_JSON: &str = r#"' + json.dumps(additions, separators=(",", ":")) + '"#;\n'

text = replace_one(before,
    'const SOURCE_LOCK: &str = "android/manifest/m2-role-ingress-provider2-source-lock.json";',
    'const PREVIOUS_NATIVE_PROVIDER_LOCK: &str = "android/manifest/m2-role-ingress-provider2-source-lock.json";\n'
    'const SOURCE_LOCK: &str = "android/manifest/m2-role-ingress-provider3-source-lock.json";')
text = replace_one(text,
    'const SOURCE_LOCK_BYTES: usize = 96957;\nconst SOURCE_LOCK_SHA: &str = "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d";',
    '// Preserve the actual normal05 provider2 lock before the SystemUI successor.\n'
    'const PREVIOUS_NATIVE_PROVIDER_LOCK_BYTES: usize = 96957;\n'
    'const PREVIOUS_NATIVE_PROVIDER_LOCK_SHA: &str = "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d";\n'
    f'const SOURCE_LOCK_BYTES: usize = {len(new_lock_bytes)};\n'
    f'const SOURCE_LOCK_SHA: &str = "{digest(new_lock_bytes)}";\n'
    '// Exact original-superproject providers observed for the retained SystemUI graph.\n' + consts.rstrip())

function = '''fn validate_systemui_provider_extension(previous: &Value, expanded: &Value) -> Result<()> {
    let mut expected = previous.clone();
    let projects = expected.get_mut("projects").and_then(Value::as_array_mut)
        .ok_or("previous native provider lock lacks projects")?;
    for (path, additions) in SYSTEMUI_PROVIDER_EXTENSIONS {
        let indices: Vec<_> = projects.iter().enumerate()
            .filter(|(_, project)| project.get("path").and_then(Value::as_str) == Some(*path))
            .map(|(index, _)| index).collect();
        if indices.len() != 1 || additions.is_empty() {
            return fail("SystemUI extension requires one exact existing project");
        }
        let paths = projects[indices[0]].get_mut("sparse_paths").and_then(Value::as_array_mut)
            .ok_or("SystemUI extension project lacks its original sparse selection")?;
        for addition in *additions {
            let value = Value::String((*addition).to_owned());
            if paths.contains(&value) {
                return fail("SystemUI extension repeats an existing sparse path");
            }
            paths.push(value);
        }
        if paths.len() > 256 {
            return fail("SystemUI extension exceeds bounded sparse paths");
        }
    }
    let additions: Vec<Value> = serde_json::from_str(SYSTEMUI_PROVIDER_ADDITIONS_JSON)?;
    for addition in additions {
        let path = addition.get("path").and_then(Value::as_str)
            .ok_or("SystemUI provider addition lacks its exact path")?;
        if projects.iter().any(|project| project.get("path").and_then(Value::as_str) == Some(path)) {
            return fail("SystemUI extension replaces an existing project");
        }
        projects.push(addition);
    }
    if &expected != expanded {
        return fail("SystemUI extension changed fixed commits, metadata, order or source paths");
    }
    Ok(())
}

'''
text = replace_one(text, "fn materialized_previous_lock(value: &Value)", function + "fn materialized_previous_lock(value: &Value)")
text = replace_one(text, "        Some(SOURCE_LOCK_SHA) => Ok(None),", "        Some(SOURCE_LOCK_SHA) => Ok(None),\n"
    '        Some(PREVIOUS_NATIVE_PROVIDER_LOCK_SHA) => Ok(Some(("m2-role-ingress-provider2-source-lock.json", Pin {\n'
    '            bytes: PREVIOUS_NATIVE_PROVIDER_LOCK_BYTES, sha256: PREVIOUS_NATIVE_PROVIDER_LOCK_SHA,\n'
    '        }))),')
text = replace_one(text,
    "    validate_native_provider_extension(&previous_provider_value, &serde_json::from_slice(&expanded)?)?;",
    "    let previous_native = fixed_file(&repo.join(PREVIOUS_NATIVE_PROVIDER_LOCK), Pin {\n"
    "        bytes: PREVIOUS_NATIVE_PROVIDER_LOCK_BYTES, sha256: PREVIOUS_NATIVE_PROVIDER_LOCK_SHA,\n"
    "    })?;\n"
    "    let previous_native_value: Value = serde_json::from_slice(&previous_native)?;\n"
    "    validate_native_provider_extension(&previous_provider_value, &previous_native_value)?;\n"
    "    validate_systemui_provider_extension(&previous_native_value, &serde_json::from_slice(&expanded)?)?;")
text = replace_one(text,
    "            // Select the exact current, provider1 or earlier independent typed lock before",
    "            // Select the exact current, provider2, provider1 or earlier typed lock before")
text = replace_one(text,
    '        "previous_provider_source_lock_sha256": PREVIOUS_PROVIDER_LOCK_SHA,',
    '        "previous_provider_source_lock_sha256": PREVIOUS_PROVIDER_LOCK_SHA,\n'
    '        "previous_native_provider_source_lock_sha256": PREVIOUS_NATIVE_PROVIDER_LOCK_SHA,\n'
    '        "systemui_provider_extension_exact": true,')
text = replace_one(text,
    '''        let expanded: Value = serde_json::from_slice(&fs::read(repo.join(SOURCE_LOCK)).unwrap()).unwrap();
        validate_native_provider_extension(&previous, &expanded).unwrap();''',
    '''        let expanded: Value = serde_json::from_slice(&fs::read(repo.join(PREVIOUS_NATIVE_PROVIDER_LOCK)).unwrap()).unwrap();
        validate_native_provider_extension(&previous, &expanded).unwrap();''')
text = replace_one(text,
    '                            (PREVIOUS_PROVIDER_LOCK_SHA, "m2-role-ingress-provider-source-lock.json")] {',
    '                            (PREVIOUS_PROVIDER_LOCK_SHA, "m2-role-ingress-provider-source-lock.json"),\n'
    '                            (PREVIOUS_NATIVE_PROVIDER_LOCK_SHA, "m2-role-ingress-provider2-source-lock.json")] {')
text = replace_one(text,
    '                                             (PREVIOUS_PROVIDER_LOCK, PREVIOUS_PROVIDER_LOCK_SHA)] {',
    '                                             (PREVIOUS_PROVIDER_LOCK, PREVIOUS_PROVIDER_LOCK_SHA),\n'
    '                                             (PREVIOUS_NATIVE_PROVIDER_LOCK, PREVIOUS_NATIVE_PROVIDER_LOCK_SHA)] {')

test = '''    #[test]
    fn systemui_extension_rejects_missing_provider_wrong_revision_or_scope() {
        let repo = repository();
        let previous: Value = serde_json::from_slice(&fs::read(repo.join(PREVIOUS_NATIVE_PROVIDER_LOCK)).unwrap()).unwrap();
        let expanded: Value = serde_json::from_slice(&fs::read(repo.join(SOURCE_LOCK)).unwrap()).unwrap();
        validate_systemui_provider_extension(&previous, &expanded).unwrap();
        let mut changed = expanded.clone();
        changed["projects"].as_array_mut().unwrap().last_mut().unwrap()["commit"] =
            Value::String("0000000000000000000000000000000000000000".to_owned());
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["projects"].as_array_mut().unwrap().pop();
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        let project = changed["projects"].as_array_mut().unwrap().iter_mut()
            .find(|project| project["path"] == SYSTEMUI_PROVIDER_EXTENSIONS[0].0).unwrap();
        project["sparse_paths"].as_array_mut().unwrap().pop();
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["projects"].as_array_mut().unwrap().swap(0, 1);
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["projects"][0]["commit"] =
            Value::String("0000000000000000000000000000000000000000".to_owned());
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["policy"]["allow_unrestricted_repo_sync"] = Value::Bool(true);
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
        let mut changed = expanded.clone();
        changed["links"].as_array_mut().unwrap().pop();
        assert!(validate_systemui_provider_extension(&previous, &changed).is_err());
    }

'''
text = replace_one(text, "    #[test]\n    fn published_workspace_selects_only_exact_current_or_previous_typed_lock()", test + "    #[test]\n    fn published_workspace_selects_only_exact_current_or_previous_typed_lock()")
assert 'pub const TARGETS: &[&str] = &["framework-minus-apex", "libandroid_runtime"];' in text
assert text.count('"runtime_authorization_enabled": false') == before.count('"runtime_authorization_enabled": false')
assert text.count('"transitive_build_closure_qualified": false') == before.count('"transitive_build_closure_qualified": false')
assert not OUT.exists(), "immutable candidate already exists"
OUT.mkdir()
for source in sorted((ROOT / "candidate-r2").rglob("*")):
    if source.is_file() and source.name != "SOURCE_CANDIDATE.json":
        destination = OUT / source.relative_to(ROOT / "candidate-r2")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
native_path = OUT / "tools/droidloom-update/src/native_role_ingress.rs"
native_path.write_text(text)
lock_path = OUT / "android/manifest/m2-role-ingress-provider3-source-lock.json"
lock_path.parent.mkdir(parents=True, exist_ok=True)
lock_path.write_bytes(new_lock_bytes)
changes = []
for name, original in [("android.rs", ROOT / "reference/builder469-android.rs"), ("native_role_ingress.rs", ROOT / "reference/builder469-native_role_ingress.rs")]:
    after_path = OUT / "tools/droidloom-update/src" / name
    changes.append("".join(difflib.unified_diff(original.read_text().splitlines(True), after_path.read_text().splitlines(True), fromfile="a/tools/droidloom-update/src/" + name, tofile="b/tools/droidloom-update/src/" + name)))
patch_bytes = "".join(changes).encode()
(ROOT / "candidate-r3-builder.diff").write_bytes(patch_bytes)
files = []
for path in sorted(OUT.rglob("*")):
    if path.is_file():
        data = path.read_bytes()
        files.append({"path": path.relative_to(OUT).as_posix(), "bytes": len(data), "sha256": digest(data)})
manifest = {
    "schema": "pocket4-normal06-candidate-r3-source-v1",
    "state": "STATIC_SOURCE_CANDIDATE_FOR_REVIEW_NOT_COMPILED",
    "source_baseline": {"builder": 469, "native_role_ingress_sha256": digest(before_bytes), "provider2_lock_sha256": digest(old_lock_bytes)},
    "files": files,
    "source_lock": {"projects": 242, "unchanged_original_project_revisions": 225, "added_original_superproject_projects": 17, "existing_sparse_selections_extended": 9, "original_links_preserved": 8, "bytes": len(new_lock_bytes), "sha256": digest(new_lock_bytes)},
    "builder_diff": {"path": "../candidate-r3-builder.diff", "bytes": len(patch_bytes), "sha256": digest(patch_bytes)},
    "device_state_flags_lib": "Existing genuine foldable provider already in actual normal05 BP list; references unchanged, no alias.",
    "known_source_gap_disposition": "Original root default/provider omissions repaired with full upstream module bodies. Recursive lock is exact observed project/path expansion. Source coverage gaps and generated variants are left to strict normal Soong, not declared missing or passed.",
    "new_project_selection": "17 complete exact-revision projects; broader child Blueprint graphs and resource cost remain subject to actual strict materialization/build.",
    "local_controls": "Pending separate receipt; Rust tests added but not executed.",
    "new_host_mutation_authorized": False,
    "full_dependency_closure_qualified": False,
    "framework_build_attempted": False,
    "runtime_qualification_inherited": False,
    "production_ready": False,
    "cleanup_eligible": False,
}
manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
(OUT / "SOURCE_CANDIDATE.json").write_bytes(manifest_bytes)
print(json.dumps({"candidate": str(OUT), "files": len(files), "native_role_ingress_bytes": len(text.encode()), "native_role_ingress_sha256": digest(text.encode()), "manifest_bytes": len(manifest_bytes), "manifest_sha256": digest(manifest_bytes), "diff_bytes": len(patch_bytes), "diff_sha256": digest(patch_bytes)}))
