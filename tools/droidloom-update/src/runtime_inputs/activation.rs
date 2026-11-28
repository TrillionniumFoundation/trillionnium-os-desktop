//! Produce the two exact CP3A linkerconfig inputs. Whole held bytes, original
//! image membership and xattrs are checked; installation and execution remain
//! independent later gates. A build record never substitutes for an ELF pin.

#[path = "../../../../runtime/droidloom-supervisor/src/production_activation_input_profile.rs"]
mod fixed;
use crate::contract::{BuildPlan, FileRef, ImageDeclaration, MAX_PLAN};
use crate::io::{self, Deadline, Inputs, Runner};
use crate::{Result, require};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::os::unix::fs::FileExt;
use std::path::Path;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ActivationInput {
    scope: String,
    original: FileRef,
    trampoline: FileRef,
    build_provenance: FileRef,
}

impl ActivationInput {
    pub(crate) fn validate(&self) -> Result<()> {
        for file in [&self.original, &self.trampoline] {
            file.validate(4 * 1024 * 1024)?;
        }
        self.build_provenance.validate(MAX_PLAN)?;
        require(
            self.scope == fixed::INPUT_SCOPE
                && self.original.bytes == fixed::ORIGINAL_BYTES
                && self.original.sha256 == fixed::ORIGINAL_SHA256
                && self.trampoline.bytes == fixed::TRAMPOLINE_BYTES
                && self.trampoline.sha256 == fixed::TRAMPOLINE_SHA256
                && self.original.path != self.trampoline.path,
            "activation input must be the exact original CP3A linkerconfig and fixed reproducible trampoline",
        )
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct ActivationDeclaration {
    scope: &'static str,
    original: ImageDeclaration,
    original_source_path: &'static str,
    original_source_sha256: &'static str,
    original_interpreter: &'static str,
    trampoline: ImageDeclaration,
}

fn payload_identity(file: &FileRef) -> Result<()> {
    require(
        file.bytes == fixed::RUNTIME_PAYLOAD_BYTES && file.sha256 == fixed::RUNTIME_PAYLOAD_SHA256,
        "activation source is the exact original CP3A runtime APEX payload",
    )
}

fn build_record(raw: &[u8]) -> Result<Value> {
    let value: Value = serde_json::from_slice(raw)?;
    let sources = value["sources"]
        .as_object()
        .ok_or("trampoline source record missing")?;
    require(
        value["schema"] == "droidloom-fixed-trampoline-build-observation-v1"
            && sources.len() == 2
            && sources.get("linkerconfig_trampoline.rs")
                == Some(&json!(fixed::TRAMPOLINE_SOURCE_SHA256))
            && sources.get("production_activation_protocol.rs")
                == Some(&json!(fixed::PROTOCOL_SOURCE_SHA256))
            && value["toolchain_channel_manifest_sha256"] == fixed::RUST_CHANNEL_SHA256
            && value["runtime_qualified"] == false,
        "fixed trampoline build provenance must bind its actual current source and pinned toolchain without runtime credit",
    )?;
    let builds = value["builds"]
        .as_array()
        .ok_or("trampoline actual build records missing")?;
    require(
        builds.len() == 2
            && builds.iter().all(|row| {
                row["bytes"] == fixed::TRAMPOLINE_BYTES
                    && row["sha256"] == fixed::TRAMPOLINE_SHA256
                    && row["exit_code"] == 0
            }),
        "both recorded trampoline outputs must match the separately verified exact ELF bytes",
    )?;
    Ok(value)
}

fn original_metadata(
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    plan: &BuildPlan,
    payload: &FileRef,
    output: &Path,
    deadline: &Deadline,
) -> Result<FileRef> {
    let target = output.join("original-linkerconfig-selinux.bin");
    crate::contract::absolute(&target)?;
    require(
        !target.try_exists()?,
        "create-only original linkerconfig label capture",
    )?;
    let image = inputs.descriptor_path(payload)?;
    runner.run(
        inputs,
        &plan.tools.debugfs,
        &[
            "-R".into(),
            format!(
                "ea_get -f \"{}\" {} security.selinux",
                target.display(),
                fixed::ORIGINAL_IMAGE_PATH
            )
            .into(),
            image.as_os_str().to_owned(),
        ],
    )?;
    require(
        std::fs::read(&target)? == b"u:object_r:linkerconfig_exec:s0\0",
        "actual original linkerconfig label must retain its complete EA bytes",
    )?;
    let (attributes, _) = runner.run(
        inputs,
        &plan.tools.debugfs,
        &[
            "-R".into(),
            format!("ea_list {}", fixed::ORIGINAL_IMAGE_PATH).into(),
            image.into_os_string(),
        ],
    )?;
    let rows: Vec<_> = std::str::from_utf8(&attributes)?
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    require(
        rows.len() == 2
            && rows[0] == "Extended attributes:"
            && rows[1].trim_start().starts_with("security.selinux ("),
        "complete original linkerconfig xattr inventory must contain no file capabilities or extra attributes",
    )?;
    io::actual_ref(&target, deadline)
}

pub(crate) fn prepare(
    selected: &ActivationInput,
    plan: &BuildPlan,
    sources: &BTreeMap<String, FileRef>,
    inputs: &mut Inputs,
    runner: &mut Runner<'_>,
    output: &Path,
    deadline: &Deadline,
) -> Result<ActivationDeclaration> {
    selected.validate()?;
    let payload = sources
        .get("apex:com.android.runtime")
        .ok_or("original runtime APEX payload is missing")?;
    payload_identity(payload)?;
    inputs.add(payload, deadline)?;
    let mut magic = [0_u8; 2];
    inputs.file(payload)?.read_exact_at(&mut magic, 0x438)?;
    require(
        magic == [0x53, 0xef],
        "fixed original runtime payload must be its actual ext4 filesystem",
    )?;
    let original = inputs.bytes(&selected.original, 4 * 1024 * 1024, deadline)?;
    require(
        crate::produce::init_elf(&original)?.as_deref() == Some(fixed::ORIGINAL_INTERPRETER),
        "actual original linkerconfig interpreter differs",
    )?;
    let (actual, _) = runner.run(
        inputs,
        &plan.tools.debugfs,
        &[
            "-R".into(),
            format!("cat {}", fixed::ORIGINAL_IMAGE_PATH).into(),
            inputs.descriptor_path(payload)?.into_os_string(),
        ],
    )?;
    require(
        actual == original,
        "complete original linkerconfig bytes differ from the selected actual APEX inode",
    )?;
    let label = original_metadata(inputs, runner, plan, payload, output, deadline)?;
    let trampoline = inputs.bytes(&selected.trampoline, 4 * 1024 * 1024, deadline)?;
    require(
        crate::produce::init_elf(&trampoline)?.is_none(),
        "fixed trampoline must be a freestanding actual x86-64 ELF",
    )?;
    let provenance_raw = inputs.bytes(&selected.build_provenance, MAX_PLAN, deadline)?;
    let provenance = build_record(&provenance_raw)?;
    io::write_new(
        &output.join("TRAMPOLINE-BUILD-PROVENANCE.json"),
        &provenance_raw,
        0o400,
        deadline,
    )?;
    let original_copy = inputs.copy_new(
        &selected.original,
        &output.join("linkerconfig-original"),
        0o555,
        deadline,
    )?;
    let trampoline_copy = inputs.copy_new(
        &selected.trampoline,
        &output.join("linkerconfig-trampoline"),
        0o555,
        deadline,
    )?;
    io::json_new(
        &output.join("ACTIVATION-INSTALL-REQUIREMENTS.json"),
        &json!({
            "schema":"droidloom-fixed-cp3a-activation-inputs-v1", "source_system":plan.system,
            "source_payload":payload,"source_path":fixed::ORIGINAL_SOURCE_PATH,
            "original_input":selected.original,"trampoline_input":selected.trampoline,
            "original_copy":original_copy,"trampoline_copy":trampoline_copy,
            "original_label_bytes":label,"trampoline_build_provenance":selected.build_provenance,
            "recorded_build_sources":provenance["sources"],
            "required_installed_mode":0o555,"required_installed_uid":0,"required_installed_gid":0,
            "required_label":"u:object_r:linkerconfig_exec:s0","required_label_trailing_nul":true,
            "required_security_capability_absent":true,"installed_label_observed":false,
            "original_linkerconfig_executions":0,"linkerconfig_generated":false,"runtime_qualified":false
        }),
        deadline,
    )?;
    Ok(ActivationDeclaration {
        scope: "original_linkerconfig_trampoline_v1",
        original: ImageDeclaration {
            file: "linkerconfig-original".into(),
            bytes: original_copy.bytes,
            sha256: original_copy.sha256,
        },
        original_source_path: fixed::ORIGINAL_SOURCE_PATH,
        original_source_sha256: fixed::RUNTIME_PAYLOAD_SHA256,
        original_interpreter: fixed::ORIGINAL_INTERPRETER,
        trampoline: ImageDeclaration {
            file: "linkerconfig-trampoline".into(),
            bytes: trampoline_copy.bytes,
            sha256: trampoline_copy.sha256,
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input() -> Value {
        let file = |path: &str, bytes: u64, sha: &str| {
            json!({"path":path,"bytes":bytes,"sha256":sha,
            "f9":[1,2,0o100400,0,0,1,bytes,0,0]})
        };
        json!({"scope":fixed::INPUT_SCOPE,
            "original":file("/ordinary-schema/original", fixed::ORIGINAL_BYTES, fixed::ORIGINAL_SHA256),
            "trampoline":file("/ordinary-schema/trampoline", fixed::TRAMPOLINE_BYTES, fixed::TRAMPOLINE_SHA256),
            "build_provenance":file("/ordinary-schema/build", 100, &"a".repeat(64))})
    }

    #[test]
    fn fixed_activation_input_rejects_other_code_payloads_and_caller_authority() {
        serde_json::from_value::<ActivationInput>(input())
            .unwrap()
            .validate()
            .unwrap();
        for field in ["original", "trampoline"] {
            let mut value = input();
            value[field]["sha256"] = json!("0".repeat(64));
            assert!(
                serde_json::from_value::<ActivationInput>(value)
                    .unwrap()
                    .validate()
                    .is_err()
            );
            let mut value = input();
            value[field]["bytes"] = json!(64);
            value[field]["f9"][6] = json!(64);
            assert!(
                serde_json::from_value::<ActivationInput>(value)
                    .unwrap()
                    .validate()
                    .is_err()
            );
        }
        for field in [
            "command",
            "source_path",
            "qualified",
            "activation_completed",
            "capabilities",
        ] {
            let mut value = input();
            value[field] = json!(true);
            assert!(serde_json::from_value::<ActivationInput>(value).is_err());
        }
        let mut value = input();
        value["scope"] = json!("generic_executable");
        assert!(
            serde_json::from_value::<ActivationInput>(value)
                .unwrap()
                .validate()
                .is_err()
        );
        let mut payload: FileRef = serde_json::from_value(input()["original"].clone()).unwrap();
        assert!(payload_identity(&payload).is_err());
        payload.bytes = fixed::RUNTIME_PAYLOAD_BYTES;
        payload.sha256 = fixed::RUNTIME_PAYLOAD_SHA256.into();
        payload_identity(&payload).unwrap();
        payload.bytes += 1;
        assert!(payload_identity(&payload).is_err());
    }

    #[test]
    fn fixed_trampoline_pins_match_actual_current_source_bytes() {
        assert_eq!(
            io::hash(include_bytes!(
                "../../../../runtime/droidloom-supervisor/src/linkerconfig_trampoline.rs"
            )),
            fixed::TRAMPOLINE_SOURCE_SHA256
        );
        assert_eq!(
            io::hash(include_bytes!(
                "../../../../runtime/droidloom-supervisor/src/production_activation_protocol.rs"
            )),
            fixed::PROTOCOL_SOURCE_SHA256
        );
    }

    #[test]
    fn trampoline_build_record_cannot_substitute_other_sources_toolchain_or_elf() {
        let valid = json!({"schema":"droidloom-fixed-trampoline-build-observation-v1",
            "sources":{"linkerconfig_trampoline.rs":fixed::TRAMPOLINE_SOURCE_SHA256,"production_activation_protocol.rs":fixed::PROTOCOL_SOURCE_SHA256},
            "toolchain_channel_manifest_sha256":fixed::RUST_CHANNEL_SHA256,
            "builds":[{"bytes":fixed::TRAMPOLINE_BYTES,"sha256":fixed::TRAMPOLINE_SHA256,"exit_code":0},
                {"bytes":fixed::TRAMPOLINE_BYTES,"sha256":fixed::TRAMPOLINE_SHA256,"exit_code":0}],"runtime_qualified":false});
        build_record(&serde_json::to_vec(&valid).unwrap()).unwrap();
        for change in 0..7 {
            let mut wrong = valid.clone();
            match change {
                0 => wrong["sources"]["linkerconfig_trampoline.rs"] = json!("0".repeat(64)),
                1 => wrong["sources"]["production_activation_protocol.rs"] = json!("0".repeat(64)),
                2 => wrong["sources"]["extra.rs"] = json!("0".repeat(64)),
                3 => wrong["toolchain_channel_manifest_sha256"] = json!("0".repeat(64)),
                4 => wrong["builds"][0]["sha256"] = json!("0".repeat(64)),
                5 => wrong["builds"][1]["exit_code"] = json!(1),
                _ => wrong["runtime_qualified"] = json!(true),
            }
            assert!(build_record(&serde_json::to_vec(&wrong).unwrap()).is_err());
        }
    }
}
