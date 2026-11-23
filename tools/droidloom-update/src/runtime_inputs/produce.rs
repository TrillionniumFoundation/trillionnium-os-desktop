//! The production input producer. All authority remains with later installation,
//! MAC, namespace, activation and execution providers.
use crate::contract::*;
use crate::io::{self, Deadline, Inputs, Runner};
use crate::{Result, require};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

fn field<'a>(v: &'a Value, name: &str) -> Result<&'a Value> {
    v.get(name)
        .ok_or_else(|| format!("original capture field missing: {name}").into())
}
fn string<'a>(v: &'a Value, name: &str) -> Result<&'a str> {
    field(v, name)?
        .as_str()
        .ok_or_else(|| format!("original capture string missing: {name}").into())
}
fn array<'a>(v: &'a Value, name: &str, max: usize) -> Result<&'a [Value]> {
    let a = field(v, name)?
        .as_array()
        .ok_or("original capture array type")?;
    require(a.len() <= max, "original capture array bound")?;
    Ok(a)
}
fn captured_ref(value: &Value, capture_root: Option<&Path>) -> Result<FileRef> {
    let path = PathBuf::from(string(value, "path")?);
    if let Some(root) = capture_root {
        let relative = string(value, "relative_path")?;
        let p = Path::new(relative);
        require(
            !p.is_absolute()
                && p.components()
                    .all(|c| matches!(c, std::path::Component::Normal(_)))
                && root.join(p) == path,
            "original member is beneath its exact capture root",
        )?;
    }
    let r = FileRef {
        path,
        bytes: field(value, "bytes")?
            .as_u64()
            .ok_or("original byte count")?,
        sha256: string(value, "sha256")?.into(),
        f9: serde_json::from_value(field(value, "identity")?.clone())?,
    };
    r.validate(MAX_INPUT)?;
    Ok(r)
}
struct Capture {
    init: FileRef,
    apexes: Vec<ApexInput>,
    original_files: BTreeMap<String, FileRef>,
    rc_inventory: Value,
    raw: Value,
    dependency_images: BTreeMap<String, FileRef>,
    original_apexes: BTreeMap<String, FileRef>,
}
fn read_capture(
    plan: &BuildPlan,
    raw: &[u8],
    inputs: &mut Inputs,
    deadline: &Deadline,
) -> Result<Capture> {
    let v: Value = serde_json::from_slice(raw)?;
    require(
        string(&v, "schema")? == "qpr1-official-runtime-inputs-v1"
            && string(&v, "state")? == "COMPLETE_OFFICIAL_IMAGE_INPUTS_EXTRACTED"
            && field(&v, "official_image_bytes_preserved")? == &Value::Bool(true)
            && field(&v, "old_overrides_included")? == &Value::Bool(false)
            && field(&v, "runtime_qualified")? == &Value::Bool(false),
        "actual original-input capture scope",
    )?;
    let system = captured_ref(field(&v, "system_image")?, None)?;
    require(
        system == plan.system,
        "capture is from this same held full system image",
    )?;
    let root = plan.capture.path.parent().ok_or("capture parent")?;
    let init_record = field(&v, "init")?;
    require(
        string(field(init_record, "image_origin")?, "path")? == "/system/bin/init",
        "original init has its actual fixed image source",
    )?;
    let init = captured_ref(field(init_record, "file")?, Some(root))?;
    require(
        (64..=32 * 1024 * 1024).contains(&init.bytes),
        "actual original init bound",
    )?;
    inputs.add(&init, deadline)?;
    let mut originals = BTreeMap::new();
    let mut rc_rows = Vec::new();
    for row in array(&v, "init_rc_files", 1024)?
        .iter()
        .chain(array(field(&v, "system_task_profile_inputs")?, "files", 128)?.iter())
    {
        let origin = field(row, "image_origin")?;
        let path = string(origin, "path")?;
        require(
            path.starts_with("/system/etc/") && Path::new(path).extension().is_some(),
            "fixed original system configuration inventory",
        )?;
        let r = captured_ref(field(row, "file")?, Some(root))?;
        require(
            r.bytes <= MAX_CONFIG && field(origin, "bytes")?.as_u64() == Some(r.bytes),
            "bounded actual source configuration size",
        )?;
        inputs.add(&r, deadline)?;
        require(
            originals.insert(path.into(), r.clone()).is_none(),
            "duplicate original configuration path",
        )?;
        rc_rows.push(json!({"image_origin":origin,"file":r}));
    }
    require(!rc_rows.is_empty(), "nonempty original RC provenance")?;
    for (_, path) in ORIGINAL_RC {
        require(
            originals.contains_key(path),
            "required actual original Android configuration absent",
        )?;
    }
    let mut apexes = Vec::new();
    let mut dependency_images = BTreeMap::from([
        ("system".into(), plan.system.clone()),
        ("vendor".into(), plan.vendor.clone()),
    ]);
    let rows = array(&v, "apexes", 128)?;
    require(
        field(&v, "apex_count")?.as_u64() == Some(rows.len() as u64),
        "actual APEX count",
    )?;
    let mut original_apexes = BTreeMap::new();
    for row in rows {
        let identity = field(row, "manifest_identity")?;
        let name = string(identity, "name")?.to_owned();
        let version = field(identity, "version")?
            .as_u64()
            .ok_or("actual original APEX version")?;
        let container = captured_ref(field(row, "original_container")?, Some(root))?;
        let original = captured_ref(field(row, "uncompressed_apex")?, Some(root))?;
        let payload = captured_ref(field(row, "payload")?, Some(root))?;
        require(
            original_apexes
                .insert(name.clone(), original.clone())
                .is_none(),
            "unique whole original APEX archive role",
        )?;
        require(
            dependency_images
                .insert(format!("apex:{name}"), payload.clone())
                .is_none(),
            "unique original payload source role",
        )?;
        for r in [&container, &original, &payload] {
            inputs.add(r, deadline)?;
        }
        let origin = field(row, "image_origin")?;
        let image_path = string(origin, "path")?;
        let container_file = string(origin, "name")?.to_owned();
        require(
            image_path == format!("/system/apex/{container_file}")
                && field(origin, "bytes")?.as_u64() == Some(container.bytes),
            "APEX original image path and byte-count lineage",
        )?;
        apexes.push(ApexInput {
            name,
            version,
            container_file,
            container_bytes: container.bytes,
            container_sha256: container.sha256,
            original_apex_bytes: original.bytes,
            original_apex_sha256: original.sha256,
            payload_bytes: payload.bytes,
            payload_sha256: payload.sha256,
        });
        // Manifest protobuf and original metadata remain real pinned files, not
        // a claim that signature or AVB cryptographic verification was performed.
        inputs.add(
            &captured_ref(field(row, "container_manifest")?, Some(root))?,
            deadline,
        )?;
        let metadata = field(row, "metadata")?
            .as_object()
            .ok_or("actual APEX metadata map")?;
        require(metadata.len() <= 16, "bounded original APEX metadata")?;
        for value in metadata.values() {
            inputs.add(&captured_ref(value, Some(root))?, deadline)?;
        }
    }
    apexes.sort_by(|a, b| a.name.cmp(&b.name));
    validate_apexes(&apexes)?;
    let rc_inventory = json!({
        "schema":"droidloom-original-rc-inventory-v1",
        "source_capture":plan.capture,"source_system":plan.system,
        "files":rc_rows,
        "init_rc_directory_inventory":field(&v,"init_rc_directory_inventory")?,
        "init_rc_symlinks":field(&v,"init_rc_symlinks")?,
        "task_profile_directory_inventory":field(field(&v,"system_task_profile_inputs")?,"directory_inventory")?,
        "task_profile_symlinks":field(field(&v,"system_task_profile_inputs")?,"symlinks")?,
        "task_profile_absent_paths":field(field(&v,"system_task_profile_inputs")?,"absent_paths")?,
    });
    Ok(Capture {
        init,
        apexes,
        original_files: originals,
        rc_inventory,
        raw: v,
        dependency_images,
        original_apexes,
    })
}

pub(crate) fn init_elf(raw: &[u8]) -> Result<Option<String>> {
    require(raw.len() >= 64, "original init ELF header")?;
    let u16_at = |n| u16::from_le_bytes([raw[n], raw[n + 1]]);
    let u32_at = |n| u32::from_le_bytes(raw[n..n + 4].try_into().unwrap());
    let u64_at = |n| u64::from_le_bytes(raw[n..n + 8].try_into().unwrap());
    require(
        &raw[..4] == b"\x7fELF"
            && raw[4..7] == [2, 1, 1]
            && matches!(u16_at(16), 2 | 3)
            && u16_at(18) == 62
            && u32_at(20) == 1
            && u64_at(24) != 0
            && u16_at(52) == 64
            && u16_at(54) == 56,
        "complete original x86_64 ELF executable",
    )?;
    let offset = u64_at(32);
    let count = u16_at(56) as u64;
    require(
        (1..=128).contains(&count)
            && offset >= 64
            && offset
                .checked_add(count * 56)
                .is_some_and(|v| v <= raw.len() as u64),
        "bounded actual init program headers",
    )?;
    let mut executable = false;
    let mut interp = None;
    for i in 0..count {
        let start = (offset + i * 56) as usize;
        let ph = &raw[start..start + 56];
        let n32 = |n| u32::from_le_bytes(ph[n..n + 4].try_into().unwrap());
        let n64 = |n| u64::from_le_bytes(ph[n..n + 8].try_into().unwrap());
        let file_start = n64(8);
        let file_bytes = n64(32);
        let mem_bytes = n64(40);
        require(
            file_start
                .checked_add(file_bytes)
                .is_some_and(|n| n <= raw.len() as u64),
            "original ELF segment escapes input",
        )?;
        if n32(0) == 1 {
            require(file_bytes <= mem_bytes, "original ELF load size")?;
            executable |= n32(4) & 1 != 0 && file_bytes > 0;
        }
        if n32(0) == 3 {
            require(
                interp.is_none() && (2..=256).contains(&file_bytes),
                "one bounded original interpreter",
            )?;
            let value = &raw[file_start as usize..(file_start + file_bytes) as usize];
            require(
                value.last() == Some(&0) && !value[..value.len() - 1].contains(&0),
                "exact single terminated original interpreter",
            )?;
            interp = Some(std::str::from_utf8(&value[..value.len() - 1])?.to_owned());
        }
    }
    require(
        executable
            && matches!(
                interp.as_deref(),
                None | Some("/system/bin/bootstrap/linker64")
                    | Some("/system/bin/linker64")
                    | Some("/apex/com.android.runtime/bin/linker64")
            ),
        "executable load and fixed supported Android interpreter",
    )?;
    Ok(interp)
}
pub(crate) fn original_cat(
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    plan: &BuildPlan,
    path: &str,
) -> Result<Vec<u8>> {
    require(
        path.starts_with("/system/")
            && path
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(&b)),
        "fixed original Android image path",
    )?;
    let args = [
        "-R".into(),
        format!("cat {path}").into(),
        inputs.descriptor_path(&plan.system)?.into_os_string(),
    ];
    Ok(runner.run(inputs, &plan.tools.debugfs, &args)?.0)
}
fn original_init_metadata(
    inputs: &Inputs,
    runner: &mut Runner<'_>,
    plan: &BuildPlan,
    root: &Path,
    deadline: &Deadline,
) -> Result<Value> {
    let image = inputs.descriptor_path(&plan.system)?;
    let label_path = root.join("original-init-selinux.bin");
    let request = format!(
        "ea_get -f \"{}\" /system/bin/init security.selinux",
        label_path.display()
    );
    runner.run(
        inputs,
        &plan.tools.debugfs,
        &["-R".into(), request.into(), image.as_os_str().to_owned()],
    )?;
    let label = fs::read(&label_path)?;
    require(
        label == b"u:object_r:init_exec:s0\0",
        "actual original init security label",
    )?;
    let (attributes, _) = runner.run(
        inputs,
        &plan.tools.debugfs,
        &[
            "-R".into(),
            "ea_list /system/bin/init".into(),
            image.into_os_string(),
        ],
    )?;
    let rows: Vec<_> = std::str::from_utf8(&attributes)?
        .lines()
        .filter(|s| !s.trim().is_empty())
        .collect();
    require(
        rows.len() == 2
            && rows[0] == "Extended attributes:"
            && rows[1].trim_start().starts_with("security.selinux ("),
        "exact original init xattr inventory, including capability absence",
    )?;
    let label_ref = io::actual_ref(&label_path, deadline)?;
    Ok(
        json!({"source_system":plan.system,"source_path":"/system/bin/init","label_bytes":label_ref,
        "security_capability_present":false,"installed_label_observed":false,
        "required_installed_mode":0o555,"required_installed_uid":0,"required_installed_gid":0}),
    )
}

pub(crate) fn run(plan_path: &Path, plan_sha256: &str, output: &Path) -> Result<()> {
    let (plan_raw, plan_ref) = io::read_small_unpinned(plan_path, plan_sha256, MAX_PLAN)?;
    let plan: BuildPlan = serde_json::from_slice(&plan_raw)?;
    plan.validate()?;
    let deadline = Deadline::new(plan.deadline_seconds);
    let parent = output.parent().ok_or("new output parent")?;
    absolute(output)?;
    let meta = fs::symlink_metadata(parent)?;
    require(
        meta.is_dir() && meta.uid() == unsafe { libc::geteuid() } && meta.mode() & 0o022 == 0,
        "output must have an existing caller-owned nonwritable-to-others parent",
    )?;
    // Resolve parent components as directories, without a symlink alias.
    let probe = parent.join(".");
    require(
        fs::canonicalize(parent)? == parent && probe.is_dir(),
        "actual normalized output parent",
    )?;
    io::create_directory(output)?;
    let work_result = produce(output, &plan, &plan_ref, &plan_raw, &deadline);
    if let Err(error) = &work_result {
        let observation = Deadline::new(10);
        let _ = io::json_new(
            &output.join("FAILED.json"),
            &json!({
                "schema":"droidloom-runtime-input-producer-failure-v1","error":error.to_string(),
                "runtime_qualified":false,"selection_written":false,"host_policy_loaded":false
            }),
            &observation,
        );
    }
    work_result
}
fn produce(
    output: &Path,
    plan: &BuildPlan,
    plan_ref: &FileRef,
    plan_raw: &[u8],
    deadline: &Deadline,
) -> Result<()> {
    let mut inputs = Inputs::new();
    inputs.add(plan_ref, deadline)?;
    io::write_new(&output.join("BUILD-PLAN.json"), plan_raw, 0o400, deadline)?;
    for r in [
        &plan.system,
        &plan.vendor,
        &plan.tools.mke2fs,
        &plan.tools.debugfs,
        &plan.tools.e2fsck,
    ] {
        inputs.add(r, deadline)?;
    }
    let base_raw = inputs.bytes(&plan.base, MAX_PLAN, deadline)?;
    let base: BaseDeclaration = serde_json::from_slice(&base_raw)?;
    base.validate(plan)?;
    io::write_new(&output.join("BASE.json"), &base_raw, 0o400, deadline)?;
    let capture_raw = inputs.bytes(&plan.capture, MAX_CAPTURE, deadline)?;
    let capture = read_capture(plan, &capture_raw, &mut inputs, deadline)?;
    io::write_new(
        &output.join("ORIGINAL-CAPTURE.json"),
        &capture_raw,
        0o400,
        deadline,
    )?;
    let adapter_raw = inputs.bytes(&plan.adapter, MAX_PLAN, deadline)?;
    let adapter: Adapter = serde_json::from_slice(&adapter_raw)?;
    adapter.validate(plan)?;
    io::write_new(&output.join("ADAPTER.json"), &adapter_raw, 0o400, deadline)?;
    for (r, name) in [
        (&adapter.provenance, "ADAPTER-PROVENANCE.json"),
        (&adapter.bootconfig_provenance, "BOOTCONFIG-PROVENANCE.json"),
    ] {
        let raw = inputs.bytes(r, MAX_PLAN, deadline)?;
        require(!raw.is_empty(), "actual provenance record")?;
        io::write_new(&output.join(name), &raw, 0o400, deadline)?;
    }
    let commands = output.join("commands");
    io::create_directory(&commands)?;
    let mut runner = Runner {
        root: &commands,
        deadline,
        epoch: plan.epoch_seconds,
        commands: Vec::new(),
    };
    let init_raw = inputs.bytes(&capture.init, 32 * 1024 * 1024, deadline)?;
    if let Some(execution) = &adapter.execution {
        execution.validate_init(&capture.init)?;
        crate::apex_inputs::validate(&capture.apexes)?;
        for (index, row) in capture.apexes.iter().enumerate() {
            let reference = capture
                .original_apexes
                .get(&row.name)
                .ok_or("same-cohort original APEX archive missing")?;
            let archive = crate::apex_inputs::archive::VerifiedArchive::inspect(
                inputs.file(reference)?,
                index,
                deadline.end(),
            )?;
            archive.matches(inputs.file(reference)?)?;
        }
    }
    let interpreter = init_elf(&init_raw)?;
    require(
        field(field(field(&capture.raw, "init")?, "elf")?, "interpreter")?
            == &serde_json::to_value(&interpreter)?,
        "actual init ELF interpreter differs from capture",
    )?;
    require(
        original_cat(&inputs, &mut runner, plan, "/system/bin/init")? == init_raw,
        "original init bytes differ from selected actual system image",
    )?;
    let init_metadata = original_init_metadata(&inputs, &mut runner, plan, output, deadline)?;
    let init = inputs.copy_new(&capture.init, &output.join("init"), 0o555, deadline)?;
    io::json_new(
        &output.join("INIT-INSTALL-REQUIREMENTS.json"),
        &init_metadata,
        deadline,
    )?;
    let mut contents = BTreeMap::new();
    for (name, item) in &adapter.files {
        let body = inputs.bytes(&item.content, MAX_CONFIG, deadline)?;
        require(
            !body.is_empty() && !body.contains(&0) && std::str::from_utf8(&body).is_ok(),
            "nonempty exact UTF-8 runtime configuration",
        )?;
        if let Some(path) = &item.source_path {
            let original = capture
                .original_files
                .get(path)
                .ok_or("adapter original source absent")?;
            let original_raw = inputs.bytes(original, MAX_CONFIG, deadline)?;
            require(
                original_cat(&inputs, &mut runner, plan, path)? == original_raw,
                "actual source configuration differs from selected system image",
            )?;
            require(
                apply_changes(&original_raw, &item.changes)? == body,
                "unrecorded adapter edit or wrong destination body",
            )?;
        } else {
            require(
                name == "bootconfig" && !std::str::from_utf8(&body)?.trim().is_empty(),
                "actual explicit bootconfig body",
            )?;
        }
        if name.ends_with(".json") {
            let value: Value = serde_json::from_slice(&body)?;
            require(value.is_object(), "Android configuration JSON object")?;
        }
        contents.insert(name.clone(), body);
    }
    let native_v2 = if let Some(native) = &adapter.native_v2 {
        Some(crate::native::prepare(
            native,
            plan,
            &adapter,
            &mut contents,
            &mut inputs,
            &mut runner,
            output,
            deadline,
            &capture.dependency_images,
        )?)
    } else {
        None
    };
    let activation = if let Some(selected) = &adapter.activation {
        Some(crate::activation::prepare(
            selected,
            plan,
            &capture.dependency_images,
            &mut inputs,
            &mut runner,
            output,
            deadline,
        )?)
    } else {
        None
    };
    let query = if let Some(selected) = &adapter.query {
        Some(crate::query::prepare(
            selected,
            plan,
            &mut inputs,
            &mut runner,
            output,
            deadline,
        )?)
    } else {
        None
    };
    let rc_inventory = io::json_new(
        &output.join("original-rc-inventory.json"),
        &capture.rc_inventory,
        deadline,
    )?;
    let built = crate::image::build(
        output,
        plan,
        &adapter,
        &contents,
        &inputs,
        &mut runner,
        deadline,
    )?;
    // Input manifests are emitted only after all actual image checks and all
    // original input bodies/F9 have been read again. No selection is written.
    let observed = inputs.revalidate_all(deadline)?;
    io::json_new(&output.join("INPUTS-AFTER.json"), &observed, deadline)?;
    let declaration = RuntimeDeclaration {
        schema: if native_v2.is_some() { 2 } else { 1 },
        scope: if native_v2.is_some() {
            "android_runtime_assets_v2"
        } else {
            "android_runtime_assets_v1"
        },
        base_cohort_sha256: plan.base.sha256.clone(),
        source_system: base.system,
        runtime_image: ImageDeclaration {
            file: "runtime.img".into(),
            bytes: built.image.bytes,
            sha256: built.image.sha256.clone(),
        },
        init: ImageDeclaration {
            file: "init".into(),
            bytes: init.bytes,
            sha256: init.sha256.clone(),
        },
        init_source_path: "/system/bin/init",
        init_interpreter: interpreter,
        original_rc_inventory_sha256: rc_inventory.sha256.clone(),
        reviewed_adapter_sha256: plan.adapter.sha256.clone(),
        runtime_tree_inventory_sha256: built.inventory.sha256.clone(),
        apexes: capture.apexes,
        native_v2,
        execution: adapter.execution,
        activation,
        query,
    };
    let mut manifest_raw = serde_json::to_vec_pretty(&declaration)?;
    manifest_raw.push(b'\n');
    require(
        manifest_raw.len() <= 256 * 1024,
        "consumer runtime manifest bound",
    )?;
    let manifest_hash = io::hash(&manifest_raw);
    let manifest = io::write_new(
        &output.join(format!("{manifest_hash}.json")),
        &manifest_raw,
        0o400,
        deadline,
    )?;
    io::json_new(
        &output.join("RESULT.json"),
        &json!({
            "schema":"droidloom-runtime-input-producer-v1",
            "state":"ACTUAL_PREINIT_INPUTS_BUILT_INSTALLATION_AND_RUNTIME_PENDING",
            "plan":plan_ref,"base":plan.base,"original_capture":plan.capture,"adapter":plan.adapter,
            "runtime_manifest":manifest,"runtime_image":built.image,"original_init":init,
            "original_rc_inventory":rc_inventory,"runtime_tree_inventory":built.inventory,
            "actual_commands":runner.commands,"verified_original_files":observed.len(),
            "original_apex_signature_qualification":false,"original_avb_signature_qualification":false,
            "apex_activated":false,"linkerconfig_generated":false,"runtime_qualified":false,
            "selection_written":false,"host_policy_loaded":false,"Android_executions":0,
            "installation":"pending actual root sealing, original init xattr, required sidecars and admission"
        }),
        deadline,
    )?;
    File::open(output)?.sync_all()?;
    deadline.check()?;
    println!(
        "{}",
        json!({"runtime_manifest_sha256":manifest_hash,"output":output,
        "runtime_qualified":false,"selection_written":false})
    );
    deadline.check()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn truncated_or_wrong_architecture_init_is_not_accepted() {
        assert!(init_elf(b"").is_err());
        let mut raw = vec![0_u8; 120];
        raw[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        raw[16..18].copy_from_slice(&3_u16.to_le_bytes());
        raw[18..20].copy_from_slice(&183_u16.to_le_bytes());
        raw[20..24].copy_from_slice(&1_u32.to_le_bytes());
        assert!(init_elf(&raw).is_err());
    }
}
