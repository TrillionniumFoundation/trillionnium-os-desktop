//! Explicit build-only projection for the paired ART generation ABI.
//!
//! This route preserves the normal source lock, projection journal and strict
//! dependency semantics. It does not build an APEX, install artifacts, or grant
//! runtime readiness. The caller must separately qualify the actual compile
//! commands, dependency closure, linked artifacts and lifecycle behavior.
use crate::util::*;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};

pub const TARGETS: &[&str] = &["libart-runtime", "libnativebridge"];
const INPUT_ROOT: &str = "android/native-generation-art/source";
const MACRO_ENABLED: &str = "-DDROIDLOOM_NATIVE_GENERATION_RUNTIME=1";
const MACRO_DISABLED: &str = "-DDROIDLOOM_NATIVE_GENERATION_RUNTIME=0";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub enum Flavor {
    Disabled,
    EnabledBuildOnly,
}
impl Flavor {
    pub fn from_build_only_flag(enabled: bool) -> Self {
        if enabled { Self::EnabledBuildOnly } else { Self::Disabled }
    }
    fn value(self) -> u8 {
        match self { Self::Disabled => 0, Self::EnabledBuildOnly => 1 }
    }
}

#[derive(Clone, Copy, Serialize)]
struct Input {
    path: &'static str,
    bytes: usize,
    sha256: &'static str,
}
const INPUTS: &[Input] = &[
    Input { path: "art/libnativebridge/Android.bp", bytes: 2840, sha256: "33ea5fb3bdcfe55c038ef5599b08fb643276aa50fe05a8757e351bf7478f7e74" },
    Input { path: "art/libnativebridge/droidloom_generation.cc", bytes: 2462, sha256: "1e43381bdb0eba44777317bb1372346eca99322139c5b2662932724fdc82aa68" },
    Input { path: "art/libnativebridge/droidloom_generation.h", bytes: 410, sha256: "28facfdf31818b2dd7e4f08b3ca0359dae0e5fdb2f5b243dc7455ac3edd966fe" },
    Input { path: "art/libnativebridge/include/nativebridge/droidloom_generation_protocol.h", bytes: 1110, sha256: "913d7a0dd717ff9d697bc926906958029b1be7ba9fb612b57218bc40fe6e27dd" },
    Input { path: "art/libnativebridge/include/nativebridge/native_bridge.h", bytes: 20874, sha256: "664dd6ed2a71d90f4bc3f84ab621d7ebbdedc148284c452d6ca2f8e8d9888760" },
    Input { path: "art/libnativebridge/libnativebridge.map.txt", bytes: 1062, sha256: "5b64217bcc16eba7083942783b920da59de9e16255ba5a3adb92e8ce7428de31" },
    Input { path: "art/libnativebridge/native_bridge.cc", bytes: 24851, sha256: "4fc33d917915886fccabaf76dbf7a6bee949cf08cd6b8ac9be429dc8614706a4" },
    Input { path: "art/runtime/Android.bp", bytes: 47356, sha256: "deac350bd467f39dddb657c8a137ef7800998d4039381045875cf41fd8af8cf9" },
    Input { path: "art/runtime/native_bridge_art_interface.cc", bytes: 5919, sha256: "d71e569e0f782ed461bdc167c6228e35414a02b209072b8cba9b7534bc8b3a5a" },
    Input { path: "art/runtime/runtime.cc", bytes: 148153, sha256: "ec7105503380ec505dbe58b822a4ac46edb48311e6093eb3e396d0768e111bc3" },
];

fn digest(data: &[u8]) -> String {
    format!("{:x}", Sha256::digest(data))
}

fn real_existing_parents(path: &Path) -> Result<()> {
    for parent in path.ancestors().skip(1) {
        let metadata = fs::symlink_metadata(parent)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return fail("paired ART input/output parent is not a real directory");
        }
    }
    Ok(())
}

pub fn validated_output(work: &Path, out: &Path) -> Result<PathBuf> {
    let source = work.join("aosp-source");
    if !out.is_absolute()
        || out.components().any(|part| matches!(part, Component::CurDir | Component::ParentDir))
        || out.starts_with(&source) || source.starts_with(out)
    {
        return fail("paired ART output must be fresh, absolute and separate from aosp-source");
    }
    real_existing_parents(out)?;
    match fs::symlink_metadata(out) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(out.to_owned()),
        Err(error) => Err(error.into()),
        Ok(_) => fail("paired ART output already exists; a new flavor/attempt requires a fresh path"),
    }
}

fn create_record(path: &Path, value: serde_json::Value) -> Result<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(&serde_json::to_vec_pretty(&value)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    Ok(())
}

pub fn begin_attempt(work: &Path, out: &Path, flavor: Flavor) -> Result<()> {
    validated_output(work, out)?;
    fs::create_dir(out)?;
    create_record(&out.join("droidloom-art-generation-attempt.json"), serde_json::json!({
        "schema": 1, "state": "CLAIMED_BEFORE_SOURCE_PROJECTION", "flavor": flavor,
        "macro_value": flavor.value(), "targets": TARGETS, "dependency_mode": "Strict",
        "source_projection_journal": work.join("source-projection.json"),
        "installation_performed": false, "runtime_enabled": false,
        "full_tu_qualification_verified": false,
    }))
}

fn frozen_inputs(repo: &Path, flavor: Flavor) -> Result<Vec<(PathBuf, Vec<u8>)>> {
    let mut values = Vec::with_capacity(INPUTS.len());
    for input in INPUTS {
        let relative = Path::new(input.path);
        if relative.is_absolute()
            || relative.components().any(|part| !matches!(part, Component::Normal(_)))
            || !input.path.starts_with("art/")
        {
            return fail("invalid fixed paired ART source table");
        }
        let path = repo.join(INPUT_ROOT).join(relative);
        real_existing_parents(&path)?;
        let before = fs::symlink_metadata(&path)?;
        if !before.is_file() || before.file_type().is_symlink()
            || before.len() != input.bytes as u64 || input.bytes > 1024 * 1024
        {
            return fail("paired ART source type, size or fixed bound differs");
        }
        let mut data = fs::read(&path)?;
        let after = fs::symlink_metadata(&path)?;
        if (before.dev(), before.ino(), before.len(), before.mtime(), before.mtime_nsec(),
            before.ctime(), before.ctime_nsec())
            != (after.dev(), after.ino(), after.len(), after.mtime(), after.mtime_nsec(),
                after.ctime(), after.ctime_nsec())
            || digest(&data) != input.sha256
        {
            return fail("paired ART source identity or frozen bytes changed");
        }
        if input.path.ends_with("/Android.bp") {
            let text = std::str::from_utf8(&data)?;
            if text.matches(MACRO_ENABLED).count() != 1 || text.contains(MACRO_DISABLED) {
                return fail("paired ART common-defaults macro does not match its frozen source");
            }
            if flavor == Flavor::Disabled {
                data = text.replacen(MACRO_ENABLED, MACRO_DISABLED, 1).into_bytes();
            }
        }
        values.push((relative.to_owned(), data));
    }
    if values.len() != 10 {
        return fail("paired ART source table is incomplete");
    }
    Ok(values)
}

pub fn project(
    repo: &Path,
    source: &Path,
    projection: &mut crate::android::Projection,
    flavor: Flavor,
) -> Result<()> {
    // Read and verify the whole immutable input set before the first mutation.
    // Every write uses the normal journal and is restored by that same owner.
    let inputs = frozen_inputs(repo, flavor)?;
    for (relative, data) in inputs {
        projection.put(&source.join(relative), data)?;
    }
    Ok(())
}

pub fn write_inputs(
    out: &Path,
    flavor: Flavor,
    selected_targets: &[PathBuf],
    projection_inventory: serde_json::Value,
) -> Result<()> {
    let selected: Vec<_> = selected_targets.iter().map(|path| path.to_str()).collect();
    if selected != TARGETS.iter().map(|name| Some(*name)).collect::<Vec<_>>() {
        return fail("paired ART resolved target list was widened");
    }
    create_record(&out.join("droidloom-art-generation-inputs.json"), serde_json::json!({
        "schema": 1, "flavor": flavor, "macro_value": flavor.value(),
        "targets": selected_targets, "dependency_mode": "Strict",
        "frozen_art_inputs": INPUTS, "source_projection": projection_inventory,
        "required_actual_compile_sources": ["art/runtime/runtime.cc",
            "art/runtime/native_bridge_art_interface.cc", "art/libnativebridge/native_bridge.cc",
            "art/libnativebridge/droidloom_generation.cc"],
        "required_matching_defaults": ["libart-runtime_common_defaults", "libnativebridge-defaults"],
        "full_tu_qualification_verified": false,
        "complete_APEX_signature_and_runtime_pair_verified": false,
    }))
}

pub fn write_command_completion(out: &Path, flavor: Flavor) -> Result<()> {
    // A normal build exit is deliberately not called an artifact/runtime gate.
    // Exact command/dependency/linked-output qualification remains external.
    create_record(&out.join("droidloom-art-generation-command.json"), serde_json::json!({
        "schema": 1, "state": "NORMAL_BUILD_COMMAND_SUCCEEDED", "flavor": flavor,
        "source_projection_restored": true, "full_tu_qualification_verified": false,
        "actual_enabled_ART_lifecycle_validated": false,
        "installation_performed": false, "runtime_enabled": false,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn output_rejects_source_overlap_alias_and_reuse() {
        let temp = tempfile::tempdir().unwrap();
        let work = temp.path().join("work");
        fs::create_dir_all(work.join("aosp-source")).unwrap();
        assert!(validated_output(&work, Path::new("relative")).is_err());
        assert!(validated_output(&work, &work).is_err());
        assert!(validated_output(&work, &work.join("aosp-source/out")).is_err());
        let output = temp.path().join("out");
        assert_eq!(validated_output(&work, &output).unwrap(), output);
        fs::create_dir(&output).unwrap();
        assert!(validated_output(&work, &output).is_err());
        let alias = temp.path().join("alias");
        std::os::unix::fs::symlink(&output, &alias).unwrap();
        assert!(validated_output(&work, &alias.join("new")).is_err());
    }

    #[test]
    fn records_are_create_only_and_never_grant_runtime_readiness() {
        let temp = tempfile::tempdir().unwrap();
        let work = temp.path().join("work");
        fs::create_dir(&work).unwrap();
        let out = temp.path().join("art-out");
        begin_attempt(&work, &out, Flavor::EnabledBuildOnly).unwrap();
        let claim = out.join("droidloom-art-generation-attempt.json");
        let original = fs::read(&claim).unwrap();
        assert!(begin_attempt(&work, &out, Flavor::EnabledBuildOnly).is_err());
        assert_eq!(fs::read(&claim).unwrap(), original);
        write_command_completion(&out, Flavor::EnabledBuildOnly).unwrap();
        assert!(write_command_completion(&out, Flavor::EnabledBuildOnly).is_err());
        let result: serde_json::Value = serde_json::from_slice(
            &fs::read(out.join("droidloom-art-generation-command.json")).unwrap()).unwrap();
        assert_eq!(result["full_tu_qualification_verified"], false);
        assert_eq!(result["runtime_enabled"], false);
    }
}
