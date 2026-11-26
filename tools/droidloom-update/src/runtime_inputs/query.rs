//! Derive all five fixed query inputs from the same held CP3A system image.
//! No caller path, substituted executable, new query command or admission is
//! selected here. The original filesystem and its inode labels are read-only.

#[path = "../../../../runtime/droidloom-supervisor/src/production_query_input_profile.rs"]
mod fixed;
use crate::contract::{BuildPlan, FileRef, ImageDeclaration, MAX_INPUT};
use crate::io::{self, Deadline, Inputs, Runner};
use crate::{Result, require};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::os::unix::fs::FileExt;
use std::path::Path;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct QueryInput {
    scope: String,
}

impl QueryInput {
    pub(crate) fn validate(&self, system: &FileRef) -> Result<()> {
        system.validate(MAX_INPUT)?;
        require(
            self.scope == fixed::INPUT_SCOPE
                && system.bytes == fixed::SYSTEM_BYTES
                && system.sha256 == fixed::SYSTEM_SHA256,
            "fixed query input selection requires the exact held CP3A system image",
        )
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct QueryDeclaration {
    scope: &'static str,
    source_system_sha256: &'static str,
    cmd: QuerySource,
    toybox: QuerySource,
    toolbox: QuerySource,
    contacts: ContactsInputs,
}

#[derive(Debug, Serialize)]
struct ContactsInputs {
    scope: &'static str,
    app_process64: QuerySource,
    content_jar: QuerySource,
}

#[derive(Debug, Serialize)]
struct QuerySource {
    original: ImageDeclaration,
    source_path: &'static str,
    interpreter: Option<&'static str>,
}

#[path = "../query_input_metadata.rs"]
mod metadata;
use metadata::{original_stat, original_xattrs};

fn original_body(role: fixed::FixedQueryInput, raw: &[u8]) -> Result<()> {
    require(
        raw.len() as u64 == role.bytes && io::hash(raw) == role.sha256,
        "whole original query code/data body differs from its exact CP3A role",
    )?;
    if let Some(interpreter) = role.interpreter {
        require(
            crate::produce::init_elf(raw)?.as_deref() == Some(interpreter),
            "actual original query ELF interpreter differs",
        )
    } else {
        require(
            raw.starts_with(b"PK\x03\x04"),
            "fixed original content JAR format",
        )
    }
}

pub(crate) fn prepare(
    selected: &QueryInput,
    plan: &BuildPlan,
    inputs: &mut Inputs,
    runner: &mut Runner<'_>,
    output: &Path,
    deadline: &Deadline,
) -> Result<QueryDeclaration> {
    selected.validate(&plan.system)?;
    inputs.add(&plan.system, deadline)?;
    let image = inputs.descriptor_path(&plan.system)?;
    let mut sources = Vec::with_capacity(fixed::INPUTS.len());
    let mut observations: Vec<Value> = Vec::with_capacity(fixed::INPUTS.len());
    for role in fixed::INPUTS {
        deadline.check()?;
        let (body, _) = runner.run(
            inputs,
            &plan.tools.debugfs,
            &[
                "-R".into(),
                format!("cat {}", role.source_path).into(),
                image.as_os_str().to_owned(),
            ],
        )?;
        original_body(role, &body)?;
        let (stat, _) = runner.run(
            inputs,
            &plan.tools.debugfs,
            &[
                "-R".into(),
                format!("stat {}", role.source_path).into(),
                image.as_os_str().to_owned(),
            ],
        )?;
        let inode = original_stat(role, &stat)?;
        let (xattrs, _) = runner.run(
            inputs,
            &plan.tools.debugfs,
            &[
                "-R".into(),
                format!("ea_list {}", role.source_path).into(),
                image.as_os_str().to_owned(),
            ],
        )?;
        let label_path = output.join(format!("{}-original-label.bin", role.output_name));
        crate::contract::absolute(&label_path)?;
        require(
            !label_path.try_exists()?,
            "create-only original query label capture",
        )?;
        runner.run(
            inputs,
            &plan.tools.debugfs,
            &[
                "-R".into(),
                format!(
                    "ea_get -f \"{}\" {} security.selinux",
                    label_path.display(),
                    role.source_path
                )
                .into(),
                image.as_os_str().to_owned(),
            ],
        )?;
        let label_file = io::open_file(&label_path)?;
        let label_identity = io::f9(&label_file.metadata()?)?;
        require(
            label_identity[2] & 0o170000 == 0o100000
                && label_identity[5] == 1
                && label_identity[6] == role.original_label.len() as u64,
            "original query exact label length",
        )?;
        let mut label = vec![0; role.original_label.len()];
        label_file.read_exact_at(&mut label, 0)?;
        original_xattrs(role, &xattrs, &label)?;
        let label_ref = io::actual_ref(&label_path, deadline)?;
        require(
            label_ref.f9 == label_identity && io::f9(&label_file.metadata()?)? == label_identity,
            "same held original query label inode",
        )?;
        let copy = io::write_new(
            &output.join(role.output_name),
            &body,
            role.installed_mode(),
            deadline,
        )?;
        observations.push(json!({
            "source_path":role.source_path,"source_inode":inode,
            "source_mode":role.original_mode,"source_uid":0,"source_gid":role.original_gid,
            "source_label_bytes":label_ref,"copied_input":copy,
            "required_installed_mode":role.installed_mode(),"required_installed_uid":0,"required_installed_gid":0,
            "required_original_label_preserved":true,"required_security_capability_absent":true,
            "installed_label_observed":false
        }));
        sources.push(QuerySource {
            original: ImageDeclaration {
                file: role.output_name.into(),
                bytes: copy.bytes,
                sha256: copy.sha256,
            },
            source_path: role.source_path,
            interpreter: role.interpreter,
        });
    }
    io::json_new(
        &output.join("QUERY-INSTALL-REQUIREMENTS.json"),
        &json!({
            "schema":"droidloom-fixed-cp3a-query-inputs-v2","source_system":plan.system,
            "sources":observations,"input_count":fixed::INPUTS.len(),"private_query_projection_observed":false,
            "original_query_executions":0,"application_admission":false,"runtime_qualified":false
        }),
        deadline,
    )?;
    let [cmd, toybox, app_process64, content_jar, toolbox]: [QuerySource; 5] =
        sources
            .try_into()
            .map_err(|_| "fixed original query input count changed")?;
    Ok(QueryDeclaration {
        scope: "fixed_application_query_v2",
        source_system_sha256: fixed::SYSTEM_SHA256,
        cmd,
        toybox,
        toolbox,
        contacts: ContactsInputs {
            scope: "fixed_contacts_content_query_v1",
            app_process64,
            content_jar,
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_query_selection_rejects_arbitrary_paths_and_other_images() {
        let mut system = FileRef {
            path: "/ordinary-inputs/system.img".into(),
            bytes: fixed::SYSTEM_BYTES,
            sha256: fixed::SYSTEM_SHA256.into(),
            f9: [1, 2, 0o100400, 0, 0, 1, fixed::SYSTEM_BYTES, 0, 0],
        };
        let input: QueryInput =
            serde_json::from_value(json!({"scope":fixed::INPUT_SCOPE})).unwrap();
        input.validate(&system).unwrap();
        for extra in [
            json!({"scope":fixed::INPUT_SCOPE,"cmd":"/other/program"}),
            json!({"scope":fixed::INPUT_SCOPE,"runtime_qualified":true}),
        ] {
            assert!(serde_json::from_value::<QueryInput>(extra).is_err());
        }
        assert!(
            serde_json::from_value::<QueryInput>(json!({"scope":"arbitrary_query"}))
                .unwrap()
                .validate(&system)
                .is_err()
        );
        system.sha256 = "0".repeat(64);
        assert!(input.validate(&system).is_err());
        system.sha256 = fixed::SYSTEM_SHA256.into();
        system.bytes -= 512;
        system.f9[6] = system.bytes;
        assert!(input.validate(&system).is_err());
    }

    #[test]
    fn original_query_metadata_rejects_wrong_shell_group_modes_labels_and_extra_xattrs() {
        for role in fixed::INPUTS {
            let stat = format!(
                "Inode: 293 Type: regular Mode: {:04o} Flags: 0x80000\nUser: 0 Group: {} Project: 0 Size: {}\nLinks: 1 Blockcount: 104\n",
                role.original_mode & 0o7777,
                role.original_gid,
                role.bytes
            );
            assert_eq!(original_stat(role, stat.as_bytes()).unwrap(), 293);
            for wrong in [
                stat.replace("regular", "symlink"),
                stat.replace("User: 0", "User: 2000"),
                stat.replace(&format!("Group: {}", role.original_gid), "Group: 65534"),
                stat.replace("Links: 1", "Links: 2"),
                stat.replace("Mode:", "Mode: 0777 Duplicate:"),
            ] {
                assert!(original_stat(role, wrong.as_bytes()).is_err());
            }
            let attrs = format!(
                "Extended attributes:\n  security.selinux ({}) = original-label\n",
                role.original_label.len()
            );
            original_xattrs(role, attrs.as_bytes(), role.original_label).unwrap();
            assert!(original_xattrs(role, attrs.as_bytes(), b"u:object_r:other:s0\0").is_err());
            assert!(
                original_xattrs(
                    role,
                    format!("{attrs}  security.capability (20) = hidden\n").as_bytes(),
                    role.original_label
                )
                .is_err()
            );
            assert!(original_body(role, &vec![0; role.bytes as usize]).is_err());
            assert!(original_body(role, &[0_u8; 64]).is_err());
        }
        let cmd = fixed::INPUTS[0];
        assert!(original_stat(cmd,b"Inode: 293 Type: regular Mode: 0755 Flags: 0x80000\nUser: 0 Group: 0 Project: 0 Size: 52160\nLinks: 1 Blockcount: 104\n").is_err());
    }
}
