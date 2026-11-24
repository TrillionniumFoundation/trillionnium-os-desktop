//! Admit and seal the four fixed original query inputs used by kernel-first v2.
//! Fixture preparation proves input custody only; application execution remains
//! an independently observed boot outcome.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use rustix::fs::{FileType, XattrFlags};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    path::Path,
};

#[path = "../../../runtime/droidloom-supervisor/src/production_query_input_profile.rs"]
pub(crate) mod fixed;
#[path = "../../../runtime/droidloom-supervisor/src/production_cp3a_init_identity.rs"]
mod original_init;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeEntry {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    source_system_sha256: String,
    init_path: String,
    init_bytes: u64,
    init_sha256: String,
    argv: Vec<String>,
    #[serde(default, deserialize_with = "present_query")]
    query_inputs: Option<QueryDeclaration>,
}

fn present_query<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<QueryDeclaration>, D::Error> {
    // Absent is allowed for v1; an explicit null is never a declaration.
    QueryDeclaration::deserialize(deserializer).map(Some)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct QueryDeclaration {
    scope: String,
    source_system_sha256: String,
    cmd: QuerySource,
    toybox: QuerySource,
    contacts: ContactsInputs,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ContactsInputs {
    scope: String,
    app_process64: QuerySource,
    content_jar: QuerySource,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct QuerySource {
    original: ImageDeclaration,
    source_path: String,
    #[serde(deserialize_with = "explicit_interpreter")]
    interpreter: Option<String>,
}
fn explicit_interpreter<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<String>, D::Error> {
    Option::<String>::deserialize(deserializer)
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ImageDeclaration {
    file: String,
    bytes: u64,
    sha256: String,
}

pub struct QueryPlan {
    runtime: String,
    pins: [FilePin; 4],
}

impl QueryPlan {
    pub fn runtime(&self) -> &str {
        &self.runtime
    }
}

/// Parse the original bytes rather than a Value round trip, so duplicate keys
/// cannot erase an earlier authority-bearing member before admission.
pub fn admit(
    raw: &[u8],
    cohort: &str,
    runtime: &str,
    system: &FilePin,
    pins: Option<&BTreeMap<String, FilePin>>,
) -> Result<Option<QueryPlan>> {
    ensure(
        raw.len() <= 256 * 1024
            && fs::valid_digest(cohort)
            && fs::valid_digest(runtime)
            && fs::digest(raw) == runtime,
        "kernel-first runtime bytes or selected manifest digest differ",
    )?;
    let entry: RuntimeEntry = serde_json::from_slice(raw)?;
    ensure(
        system.bytes == fixed::SYSTEM_BYTES
            && system.sha256 == fixed::SYSTEM_SHA256
            && entry.base_cohort_sha256 == cohort
            && entry.source_system_sha256 == fixed::SYSTEM_SHA256
            && entry.init_path == "/system/bin/init"
            && entry.init_bytes == original_init::INIT_BYTES
            && entry.init_sha256 == original_init::INIT_SHA256
            && entry.argv == ["/system/bin/init", "second_stage"],
        "kernel-first runtime must bind the original CP3A system, init and selected cohort",
    )?;
    match (entry.schema, entry.scope.as_str(), entry.query_inputs) {
        (1, "android_kernel_first_stage_v1", None) => {
            ensure(
                pins.is_none(),
                "kernel-first v1 cannot import query authority",
            )?;
            Ok(None)
        }
        (2, "android_kernel_first_stage_v2", Some(query)) => {
            ensure(
                query.scope == "fixed_application_query_v1"
                    && query.source_system_sha256 == fixed::SYSTEM_SHA256
                    && query.contacts.scope == "fixed_contacts_content_query_v1",
                "kernel-first query declaration scope or original system differs",
            )?;
            let sources = [
                query.cmd,
                query.toybox,
                query.contacts.app_process64,
                query.contacts.content_jar,
            ];
            let pins = pins.ok_or("kernel-first v2 requires all four original query pins")?;
            ensure(
                pins.keys().map(String::as_str).collect::<BTreeSet<_>>()
                    == fixed::INPUTS.iter().map(|role| role.output_name).collect(),
                "kernel-first v2 input set must contain exactly the four fixed query roles",
            )?;
            let mut selected = Vec::with_capacity(4);
            for (source, role) in sources.iter().zip(fixed::INPUTS) {
                ensure(
                    source.original.file == role.output_name
                        && source.original.bytes == role.bytes
                        && source.original.sha256 == role.sha256
                        && source.source_path == role.source_path
                        && source.interpreter.as_deref() == role.interpreter,
                    "kernel-first query member differs from the fixed original CP3A role",
                )?;
                let pin = &pins[role.output_name];
                ensure(
                    pin.path.is_absolute()
                        && pin.path.file_name().and_then(|name| name.to_str())
                            == Some(role.output_name)
                        && pin.bytes == role.bytes
                        && pin.sha256 == role.sha256,
                    "external query pin is not the exact named original role",
                )?;
                selected.push(pin.clone());
            }
            Ok(Some(QueryPlan {
                runtime: runtime.to_owned(),
                pins: selected
                    .try_into()
                    .map_err(|_| "fixed query role count changed")?,
            }))
        }
        _ => Err("kernel-first runtime schema, scope and query declaration disagree".into()),
    }
}

pub fn guest_paths(runtime: &str) -> Result<Vec<String>> {
    ensure(
        fs::valid_digest(runtime),
        "invalid fixed-query runtime namespace",
    )?;
    Ok(fixed::INPUTS
        .iter()
        .map(|role| {
            format!(
                "/var/lib/droidloom/runtime-cohorts/{runtime}/images/{}",
                role.output_name
            )
        })
        .collect())
}

fn sealed_file(
    root: &Path,
    guest: &str,
    role: fixed::FixedQueryInput,
    labelled: bool,
) -> Result<File> {
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let file = tree.file(guest)?;
    let before = fs::stat(&file)?;
    ensure(
        FileType::from_raw_mode(before.mode) == FileType::RegularFile
            && before.mode & 0o7777 == role.installed_mode()
            && before.uid == 0
            && before.gid == 0
            && before.nlink == 1
            && before.size == role.bytes
            && fs::xattrs(&file)?.is_empty()
            && fs::hash(&file)? == role.sha256,
        "installed query input bytes, singleton owner, sealed mode or privilege attributes differ",
    )?;
    if labelled {
        let mut raw = [0u8; 256];
        let count = rustix::fs::fgetxattr(&file, "security.selinux", &mut raw[..])?;
        ensure(
            &raw[..count] == role.original_label,
            "installed query input lost its original role label",
        )?;
    }
    ensure(
        fs::stat(&file)? == before && tree.identity(guest)? == before,
        "installed query input changed during descriptor admission",
    )?;
    Ok(file)
}

pub fn install(root: &Path, plan: &QueryPlan) -> Result<Value> {
    // All external byte pins are checked before the first query directory write.
    for (pin, role) in plan.pins.iter().zip(fixed::INPUTS) {
        let file = boot_files::checked_file(pin)?;
        let before = fs::stat(&file)?;
        ensure(
            before.nlink == 1 && fs::xattrs(&file)?.is_empty() && fs::stat(&file)? == before,
            "published query source has extra links or privilege attributes",
        )?;
        ensure(
            pin.bytes == role.bytes && pin.sha256 == role.sha256,
            "fixed query plan changed",
        )?;
    }
    let paths = guest_paths(plan.runtime())?;
    let parent = format!("/var/lib/droidloom/runtime-cohorts/{}/images", plan.runtime);
    boot_files::ensure_dir(root, &parent, 0o755)?;
    let mut rows = Vec::new();
    for ((pin, role), guest) in plan.pins.iter().zip(fixed::INPUTS).zip(paths) {
        boot_files::copy_pin(
            pin,
            &boot_files::guest_path(root, &guest)?,
            role.installed_mode(),
        )?;
        let file = sealed_file(root, &guest, role, false)?;
        rows.push(
            json!({"path":guest,"source":pin,"identity":fs::stat(&file)?,
            "original_source_mode":role.original_mode,"original_source_gid":role.original_gid,
            "required_original_label_hex":hex::encode(role.original_label),
            "original_label_observed":false}),
        );
    }
    Ok(
        json!({"input_scope":fixed::INPUT_SCOPE,"runtime_manifest_sha256":plan.runtime,
        "source_system_sha256":fixed::SYSTEM_SHA256,"files":rows,
        "query_executions":0,"guest_qualified":false}),
    )
}

/// Global Linux file_contexts normally give /var data its Linux label. The
/// sealed original Android roles retain their original stock labels, matching
/// the production consumer; label them before recording the complete inventory.
pub fn label_inputs(root: &Path, runtime: &str) -> Result<Value> {
    let paths = guest_paths(runtime)?;
    let mut rows = Vec::new();
    for (guest, role) in paths.iter().zip(fixed::INPUTS) {
        let file = sealed_file(root, guest, role, false)?;
        rustix::fs::fsetxattr(
            &file,
            "security.selinux",
            role.original_label,
            XattrFlags::empty(),
        )?;
        file.sync_all()?;
        let observed = sealed_file(root, guest, role, true)?;
        rows.push(json!({"path":guest,"bytes":role.bytes,"sha256":role.sha256,
            "identity":fs::stat(&observed)?,"label_hex":hex::encode(role.original_label),
            "original_label_observed":true,"privilege_attributes_absent":true}));
    }
    Ok(
        json!({"input_scope":fixed::INPUT_SCOPE,"runtime_manifest_sha256":runtime,
        "source_system_sha256":fixed::SYSTEM_SHA256,"files":rows,
        "query_executions":0,"guest_qualified":false}),
    )
}

pub fn verify_sealed(root: &Path, runtime: &str) -> Result<()> {
    for (guest, role) in guest_paths(runtime)?.iter().zip(fixed::INPUTS) {
        sealed_file(root, guest, role, true)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (Value, String, FilePin, BTreeMap<String, FilePin>) {
        let role = |index: usize| {
            let r = fixed::INPUTS[index];
            json!({"original":{"file":r.output_name,"bytes":r.bytes,"sha256":r.sha256},
                "source_path":r.source_path,"interpreter":r.interpreter})
        };
        let cohort = "a".repeat(64);
        let runtime = json!({"schema":2,"scope":"android_kernel_first_stage_v2",
            "base_cohort_sha256":cohort,"source_system_sha256":fixed::SYSTEM_SHA256,
            "init_path":"/system/bin/init","init_bytes":original_init::INIT_BYTES,
            "init_sha256":original_init::INIT_SHA256,"argv":["/system/bin/init","second_stage"],
            "query_inputs":{"scope":"fixed_application_query_v1","source_system_sha256":fixed::SYSTEM_SHA256,
                "cmd":role(0),"toybox":role(1),"contacts":{"scope":"fixed_contacts_content_query_v1",
                    "app_process64":role(2),"content_jar":role(3)}}});
        let system = FilePin {
            path: "/intentionally-absent/system.img".into(),
            bytes: fixed::SYSTEM_BYTES,
            sha256: fixed::SYSTEM_SHA256.into(),
        };
        let pins = fixed::INPUTS
            .iter()
            .map(|r| {
                (
                    r.output_name.into(),
                    FilePin {
                        path: Path::new("/intentionally-absent").join(r.output_name),
                        bytes: r.bytes,
                        sha256: r.sha256.into(),
                    },
                )
            })
            .collect();
        (runtime, cohort, system, pins)
    }
    fn check(
        value: &Value,
        cohort: &str,
        system: &FilePin,
        pins: Option<&BTreeMap<String, FilePin>>,
    ) -> Result<Option<QueryPlan>> {
        let bytes = serde_json::to_vec(value)?;
        admit(&bytes, cohort, &fs::digest(&bytes), system, pins)
    }
    #[test]
    fn complete_v2_admission_is_metadata_only_and_binds_all_four_paths() -> Result<()> {
        let (value, cohort, system, pins) = fixture();
        let plan = check(&value, &cohort, &system, Some(&pins))?.ok_or("query plan missing")?;
        let paths = guest_paths(plan.runtime())?;
        assert_eq!(paths.len(), 4);
        for (path, role) in paths.iter().zip(fixed::INPUTS) {
            assert_eq!(
                Path::new(path).file_name().and_then(|v| v.to_str()),
                Some(role.output_name)
            );
        }
        assert!(guest_paths("../outside").is_err());
        assert!(guest_paths(&"A".repeat(64)).is_err());
        Ok(())
    }
    #[test]
    fn original_cohort_system_init_and_schema_are_jointly_bound() {
        let (value, cohort, system, pins) = fixture();
        for (path, bad) in [
            ("/schema", json!(1)),
            ("/scope", json!("android_kernel_first_stage_v1")),
            ("/base_cohort_sha256", json!("b".repeat(64))),
            ("/source_system_sha256", json!("b".repeat(64))),
            ("/init_path", json!("/init")),
            ("/init_bytes", json!(10)),
            ("/init_sha256", json!("b".repeat(64))),
            ("/argv", json!(["/system/bin/init"])),
        ] {
            let mut changed = value.clone();
            *changed.pointer_mut(path).unwrap() = bad;
            assert!(
                check(&changed, &cohort, &system, Some(&pins)).is_err(),
                "{path}"
            );
        }
        let mut changed = system.clone();
        changed.bytes += 1;
        assert!(check(&value, &cohort, &changed, Some(&pins)).is_err());
        changed = system.clone();
        changed.sha256 = "b".repeat(64);
        assert!(check(&value, &cohort, &changed, Some(&pins)).is_err());
        let bytes = serde_json::to_vec(&value).unwrap();
        assert!(admit(&bytes, &cohort, &"b".repeat(64), &system, Some(&pins)).is_err());
    }
    #[test]
    fn all_declared_role_fields_are_fixed_and_contacts_are_required() {
        let (value, cohort, system, pins) = fixture();
        for prefix in [
            "/query_inputs/cmd",
            "/query_inputs/toybox",
            "/query_inputs/contacts/app_process64",
            "/query_inputs/contacts/content_jar",
        ] {
            for (suffix, bad) in [
                ("/original/file", json!("other")),
                ("/original/bytes", json!(1)),
                ("/original/sha256", json!("b".repeat(64))),
                ("/source_path", json!("/bin/sh")),
                ("/interpreter", json!("/other/linker")),
            ] {
                let mut changed = value.clone();
                *changed.pointer_mut(&format!("{prefix}{suffix}")).unwrap() = bad;
                assert!(
                    check(&changed, &cohort, &system, Some(&pins)).is_err(),
                    "{prefix}{suffix}"
                );
            }
            for missing in ["original", "source_path", "interpreter"] {
                let mut changed = value.clone();
                changed
                    .pointer_mut(prefix)
                    .unwrap()
                    .as_object_mut()
                    .unwrap()
                    .remove(missing);
                assert!(
                    check(&changed, &cohort, &system, Some(&pins)).is_err(),
                    "{prefix}/{missing}"
                );
            }
        }
        let mut changed = value.clone();
        changed["query_inputs"]
            .as_object_mut()
            .unwrap()
            .remove("contacts");
        assert!(check(&changed, &cohort, &system, Some(&pins)).is_err());
    }
    #[test]
    fn missing_extra_and_disguised_external_pins_are_rejected_before_io() {
        let (value, cohort, system, pins) = fixture();
        assert!(check(&value, &cohort, &system, None).is_err());
        for role in fixed::INPUTS {
            let mut changed = pins.clone();
            changed.remove(role.output_name);
            assert!(check(&value, &cohort, &system, Some(&changed)).is_err());
            changed = pins.clone();
            changed.get_mut(role.output_name).unwrap().bytes += 1;
            assert!(check(&value, &cohort, &system, Some(&changed)).is_err());
            changed = pins.clone();
            changed.get_mut(role.output_name).unwrap().sha256 = "c".repeat(64);
            assert!(check(&value, &cohort, &system, Some(&changed)).is_err());
            changed = pins.clone();
            changed.get_mut(role.output_name).unwrap().path = "/outside/alias".into();
            assert!(check(&value, &cohort, &system, Some(&changed)).is_err());
        }
        let mut changed = pins.clone();
        changed.insert("arbitrary".into(), pins["cmd-original"].clone());
        assert!(check(&value, &cohort, &system, Some(&changed)).is_err());
    }
    #[test]
    fn v1_has_no_query_declaration_or_import_authority() -> Result<()> {
        let (mut value, cohort, system, pins) = fixture();
        value["schema"] = json!(1);
        value["scope"] = json!("android_kernel_first_stage_v1");
        assert!(check(&value, &cohort, &system, None).is_err());
        value["query_inputs"] = Value::Null;
        assert!(check(&value, &cohort, &system, None).is_err());
        value.as_object_mut().unwrap().remove("query_inputs");
        assert!(check(&value, &cohort, &system, None)?.is_none());
        assert!(check(&value, &cohort, &system, Some(&pins)).is_err());
        Ok(())
    }
    #[test]
    fn duplicate_keys_and_extra_authority_are_not_erased_by_json_value() {
        let (value, cohort, system, pins) = fixture();
        for pointer in [
            "",
            "/query_inputs",
            "/query_inputs/cmd",
            "/query_inputs/cmd/original",
            "/query_inputs/contacts",
            "/query_inputs/contacts/content_jar",
        ] {
            let mut changed = value.clone();
            changed
                .pointer_mut(pointer)
                .unwrap()
                .as_object_mut()
                .unwrap()
                .insert("unexpected".into(), json!(true));
            assert!(
                check(&changed, &cohort, &system, Some(&pins)).is_err(),
                "{pointer}"
            );
        }
        let raw = serde_json::to_string(&value).unwrap();
        for (needle, replacement) in [
            (r#""schema":2"#, r#""schema":1,"schema":2"#),
            (
                r#""source_path":"/system/bin/cmd""#,
                r#""source_path":"/bin/sh","source_path":"/system/bin/cmd""#,
            ),
            (
                r#""file":"cmd-original""#,
                r#""file":"other","file":"cmd-original""#,
            ),
        ] {
            assert!(raw.contains(needle));
            let changed = raw.replace(needle, replacement);
            assert!(
                admit(
                    changed.as_bytes(),
                    &cohort,
                    &fs::digest(changed.as_bytes()),
                    &system,
                    Some(&pins)
                )
                .is_err()
            );
        }
    }
}
