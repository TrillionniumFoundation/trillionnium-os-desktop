//! Fresh normal-source and complete-image readback for original initramfs.
//! Reads the actual archives again; old success flags grant no authority.
use super::*;

fn pin(value: &Value) -> Result<FilePin> {
    let pin: FilePin = serde_json::from_value(value.clone())?;
    trusted(&pin)?;
    Ok(pin)
}

fn producer_identity(producer: &FilePin) -> Result<Value> {
    trusted(producer)?;
    ensure(
        producer.path.file_name() == Some(std::ffi::OsStr::new("droidloom-ubuntu-fixture")),
        "normal initramfs producer executable name differs",
    )?;
    let directory = producer.path.parent().ok_or("producer directory missing")?;
    let record_pin = actual_pin(&directory.join("FIXTURE-RESULT.json"))?;
    let record: Value = read(&record_pin, 2 * 1024 * 1024)?;
    let imported_pin = actual_pin(&directory.join("IMPORT.json"))?;
    let imported: Value = read(&imported_pin, 2 * 1024 * 1024)?;
    let deps_pin = actual_pin(&directory.join("droidloom-ubuntu-fixture.d"))?;
    ensure(
        record["schema"] == "p4-r126-combined-fixture-v8"
            && imported["schema"] == "droidloom-original-initramfs-producer-protected-import-v1"
            && record["source_commit"] == imported["source_commit"]
            && record["source_tree"] == imported["source_tree"],
        "normal producer source/import identities differ",
    )?;
    for key in ["source_commit", "source_tree"] {
        let v = record[key]
            .as_str()
            .ok_or("normal producer git identity missing")?;
        ensure(
            v.len() == 40
                && v.bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
            "normal producer git identity is malformed",
        )?;
    }
    ensure(
        record["artifact"]["name"] == "droidloom-ubuntu-fixture"
            && record["artifact"]["bytes"] == producer.bytes
            && record["artifact"]["sha256"] == producer.sha256
            && record["artifact"]["dependency_file"]["bytes"] == deps_pin.bytes
            && record["artifact"]["dependency_file"]["sha256"] == deps_pin.sha256
            && record["artifact"]["foreign_project_paths"] == json!([]),
        "normal producer executable or complete dependency record differs",
    )?;
    let rows = imported["files"]
        .as_array()
        .ok_or("producer import files missing")?;
    ensure(
        rows.len() == 3,
        "normal producer import has an unexpected payload",
    )?;
    for expected in [producer, &record_pin, &deps_pin] {
        let matches = rows
            .iter()
            .filter(|v| {
                v["path"] == expected.path.to_string_lossy().as_ref()
                    && v["bytes"] == expected.bytes
                    && v["sha256"] == expected.sha256
            })
            .collect::<Vec<_>>();
        ensure(
            matches.len() == 1,
            "normal producer imported member pin differs",
        )?;
        let id = trusted(expected)?.1;
        ensure(
            matches[0]["identity"]
                == json!([
                    id.dev,
                    id.ino,
                    id.mode,
                    id.uid,
                    id.gid,
                    id.nlink,
                    id.size,
                    i128::from(id.mtime_sec) * 1_000_000_000 + i128::from(id.mtime_nsec),
                    i128::from(id.ctime_sec) * 1_000_000_000 + i128::from(id.ctime_nsec)
                ]),
            "normal producer imported member inode differs",
        )?;
    }
    validate_normal_build(&record)?;
    let build = &record["normal_build"];
    Ok(
        json!({"producer":producer,"normal_build_record":record_pin,"protected_import":imported_pin,
        "dependency_file":deps_pin,"source_commit":record["source_commit"],"source_tree":record["source_tree"],
        "project_dependencies":record["artifact"]["project_dependencies"],"normal_build":build}),
    )
}

fn validate_normal_build(record: &Value) -> Result<()> {
    let build = &record["normal_build"];
    let args = build["args"]
        .as_array()
        .ok_or("normal producer build arguments missing")?;
    ensure(
        args.len() == 12
            && args[0] == "/home/qq/.cargo/bin/cargo"
            && args[1] == "+1.93.0"
            && args[2] == "build"
            && args[3] == "--manifest-path"
            && args[4].as_str().is_some_and(|s| {
                s.starts_with("/home/qq/work/")
                    && s.ends_with("/tools/droidloom-ubuntu-fixture/Cargo.toml")
                    && !s.contains("/../")
            })
            && args[5] == "--release"
            && args[6] == "--locked"
            && args[7] == "--offline"
            && args[8] == "-j"
            && ["1", "2"].iter().any(|v| args[9] == *v)
            && args[10] == "-p"
            && args[11] == "droidloom-ubuntu-fixture"
            && build["exit_code"] == 0
            && build["seconds"].as_f64().is_some_and(|n| n > 0.0),
        "producer did not record the exact normal bounded locked release build",
    )?;
    let rows = record["artifact"]["project_dependencies"]
        .as_array()
        .ok_or("producer source dependency inventory missing")?;
    let mut names = BTreeSet::new();
    for row in rows {
        let path = row["path"]
            .as_str()
            .ok_or("producer source member path missing")?;
        ensure(
            !path.is_empty()
                && Path::new(path)
                    .components()
                    .all(|part| matches!(part, std::path::Component::Normal(_)))
                && row["bytes"].as_u64().is_some_and(|v| v > 0)
                && row["sha256"].as_str().is_some_and(fs::valid_digest)
                && names.insert(path),
            "producer source inventory has an invalid or duplicate member",
        )?;
    }
    for required in [
        "tools/droidloom-ubuntu-fixture/src/cold_original_initramfs.rs",
        "packaging/ubuntu/production/cold_modules.rs",
        "packaging/ubuntu/production/cold_transaction.py",
        "packaging/ubuntu/production/cold_apply.py",
        "packaging/ubuntu/production/native_release.py",
        "packaging/ubuntu/production/release.py",
    ] {
        ensure(
            names.contains(required),
            "normal initramfs producer source dependency is missing",
        )?;
    }
    Ok(())
}

fn admit_materials(plan: &Plan, work: &Path) -> Result<(Materials, Value)> {
    let modules = work.join("controller");
    files::private_dir(&modules)?;
    let mut module_pins = Vec::new();
    for (name, bytes) in cold_modules::FILES {
        let path = modules.join(
            Path::new(name)
                .file_name()
                .ok_or("normal module filename missing")?,
        );
        files::write_new(&path, bytes, 0o444)?;
        module_pins.push(actual_pin(&path)?);
    }
    let materials = work.join("MATERIALS.json");
    let command=run(work,"fresh-normal-public-native-admission",PYTHON,vec![
        "-I".into(),"-B".into(),"-c".into(),
        "import sys; sys.path.insert(0, sys.argv.pop(1)); from cold_transaction import main; main()".into(),
        fs::absolute_string(&modules)?,"initramfs-materials".into(),"--bundle".into(),
        fs::absolute_string(plan.public_release.path.parent().ok_or("public bundle missing")?)?,
        "--release".into(),plan.public_release.sha256.clone(),"--native-bundle".into(),
        fs::absolute_string(plan.native_release.path.parent().ok_or("native bundle missing")?)?,
        "--native-release".into(),plan.native_release_id.clone(),"--output".into(),fs::absolute_string(&materials)?],600)?;
    let materials_pin = actual_pin(&materials)?;
    let value: Materials = read(&materials_pin, 2 * 1024 * 1024)?;
    validate_materials(&value)?;
    ensure(
        same_pin(&value.public_release, &plan.public_release)
            && same_pin(&value.native_release, &plan.native_release)
            && value.native_release_id == plan.native_release_id,
        "fresh archive admission changed the planned public/native sources",
    )?;
    for p in &module_pins {
        trusted(p)?;
    }
    Ok((
        value,
        json!({"materials":materials_pin,"command":command,"source_modules":module_pins}),
    ))
}

/// Freshly re-admits normal public/native22 archives, unpacks the actual image,
/// and applies the same full inventory, exact required-five and signed-module
/// validators as the normal producer. This record alone never grants boot or
/// final application authority; the once owner cross-binds its source identities.
pub(crate) fn verify_prepared_original_initramfs(receipt: &FilePin, work: &Path) -> Result<Value> {
    allowed_work(work)?;
    ensure(
        receipt.path.file_name() == Some(std::ffi::OsStr::new("ORIGINAL-INITRAMFS-PREPARED.json")),
        "normal prepared initramfs receipt name differs",
    )?;
    let prepared: Value = read(receipt, 2 * 1024 * 1024)?;
    ensure(
        prepared["schema"] == "droidloom.original-host-initramfs-prepared.v1"
            && prepared["phase"] == "candidate_preparation"
            && prepared["kernel_release"] == KERNEL
            && prepared["kernel_sha256"] == KERNEL_SHA
            && prepared["root_uuid"] == ROOT_UUID,
        "prepared initramfs is not this original shared-kernel candidate",
    )?;
    let input = pin(&prepared["input"])?;
    let plan: Plan = read(&input, 2 * 1024 * 1024)?;
    ensure(
        plan.schema == "droidloom.original-host-initramfs-plan.v1"
            && receipt.path == plan.work_directory.join("ORIGINAL-INITRAMFS-PREPARED.json")
            && work != plan.work_directory,
        "original producer input and prepared location differ",
    )?;
    allowed_work(&plan.work_directory)?;
    let old_materials_pin = pin(&prepared["normal_materials"])?;
    ensure(
        old_materials_pin.path == plan.work_directory.join("MATERIALS.json"),
        "original material receipt is outside its protected work",
    )?;
    let old_materials: Materials = read(&old_materials_pin, 2 * 1024 * 1024)?;
    validate_materials(&old_materials)?;
    let public = pin(&prepared["normal_public_release"])?;
    let native = pin(&prepared["normal_native_release"])?;
    ensure(
        same_pin(&public, &plan.public_release)
            && same_pin(&native, &plan.native_release)
            && same_pin(&old_materials.public_release, &public)
            && same_pin(&old_materials.native_release, &native),
        "prepared normal sources differ from the immutable producer input",
    )?;
    let preflight_pin = pin(&prepared["target_preflight"])?;
    ensure(
        same_pin(&preflight_pin, &plan.target_preflight),
        "prepared original preflight differs",
    )?;
    let before = original_context()?;
    ensure(
        before == prepared["original_host"],
        "original machine context changed since normal preparation",
    )?;
    let preflight: Value = read(&preflight_pin, 2 * 1024 * 1024)?;
    let guards = source_guards(&preflight, &before)?;
    let _locks = original_package_read_locks()?;
    guard_readback(&guards)?;
    let build = plan.work_directory.join("build");
    let inner_pin = pin(&prepared["actual_private_build"])?;
    ensure(
        inner_pin.path == build.join("BUILT.json"),
        "actual normal build receipt is outside its producer work",
    )?;
    let inner: Value = read(&inner_pin, 16 * 1024 * 1024)?;
    let stage_pin = actual_pin(&build.join("INNER-INPUTS.json"))?;
    let stage: Stage = read(&stage_pin, 2 * 1024 * 1024)?;
    ensure(
        stage.schema == "droidloom.original-host-initramfs-stage.v1"
            && stage.work_directory == plan.work_directory
            && same_pin(&stage.input, &input)
            && stage.original == before
            && inner["stage_sha256"] == stage_pin.sha256
            && inner["schema"] == "droidloom.original-host-normal-initramfs-build.v1"
            && inner["kernel_release"] == KERNEL
            && inner["package_count"] == 24,
        "normal private stage and complete build receipt differ",
    )?;
    let mut stage_materials = serde_json::to_value(&stage.materials)?;
    ensure(
        stage.materials.packages.len() == old_materials.packages.len(),
        "private build package list length differs",
    )?;
    for (index, (actual, wanted)) in stage
        .materials
        .packages
        .iter()
        .zip(&old_materials.packages)
        .enumerate()
    {
        ensure(
            actual.package.path == PathBuf::from(format!("/inputs/{index:02}.deb"))
                && actual.package.bytes == wanted.package.bytes
                && actual.package.sha256 == wanted.package.sha256,
            "normal private build substituted a selected package",
        )?;
        stage_materials["packages"][index]["package"]["path"] = json!(wanted.package.path);
    }
    ensure(
        stage_materials == serde_json::to_value(&old_materials)?,
        "private build material semantics differ from normal source admission",
    )?;
    let original_status = pin(&before["dpkg_status"])?;
    let status_before: FilePin = serde_json::from_value(inner["status_before"].clone())?;
    let status_after: FilePin = serde_json::from_value(inner["status_after"].clone())?;
    let retained: FilePin = serde_json::from_value(inner["retained_private_status"].clone())?;
    ensure(
        same_pin(&status_before, &original_status)
            && status_after.path == Path::new("/var/lib/dpkg/status")
            && retained.path == Path::new("/build/PRIVATE-DPKG-STATUS")
            && retained.bytes == status_after.bytes
            && retained.sha256 == status_after.sha256,
        "normal private status source/retained pins differ",
    )?;
    let private_status = actual_pin(&build.join("PRIVATE-DPKG-STATUS"))?;
    ensure(
        private_status.bytes == retained.bytes && private_status.sha256 == retained.sha256,
        "retained normal private package database changed",
    )?;
    let original_roster = roster(&files::read_pin(&original_status, 32 * 1024 * 1024)?)?;
    let private_roster = roster(&files::read_pin(&private_status, 32 * 1024 * 1024)?)?;
    ensure(
        private_roster == expected_roster(&original_roster, &old_materials.packages)?,
        "normal private package state does not preserve the complete original roster",
    )?;
    let normal_package_state = json!({"original_status":original_status,
        "retained_private_status":private_status,"original_roster":original_roster,
        "private_roster":private_roster,"selected_packages":old_materials.packages});
    let producer = producer_identity(&stage.producer)?;
    let image = pin(&prepared["initrd"])?;
    ensure(
        image.path == build.join("initrd.img")
            && inner["initrd"]["bytes"] == image.bytes
            && inner["initrd"]["sha256"] == image.sha256,
        "actual normal initramfs image differs",
    )?;
    files::private_dir(work)?;
    let (materials, admission) = admit_materials(&plan, work)?;
    ensure(
        serde_json::to_value(&materials)? == serde_json::to_value(&old_materials)?,
        "fresh normal public/native admission no longer matches the produced candidate",
    )?;
    let kernel = materials
        .packages
        .iter()
        .find(|p| p.role == "kernel")
        .ok_or("normal kernel package missing")?;
    trusted(&kernel.package)?;
    let kernel_root = work.join("normal-kernel-payload");
    files::private_dir(&kernel_root)?;
    let kernel_command = run(
        work,
        "extract-admitted-normal-kernel",
        "/usr/bin/dpkg-deb",
        vec![
            "--extract".into(),
            fs::absolute_string(&kernel.package.path)?,
            fs::absolute_string(&kernel_root)?,
        ],
        180,
    )?;
    trusted(&kernel.package)?;
    let module_source =
        actual_pin(&kernel_root.join(materials.module_manifest.path.strip_prefix("/")?))?;
    ensure(
        module_source.bytes == materials.module_manifest.bytes
            && module_source.sha256 == materials.module_manifest.sha256,
        "fresh normal kernel package module manifest differs",
    )?;
    let complete = readback_image(work, &materials, &image.path, &module_source, false)?;
    let original_files_unchanged = guard_readback(&guards)?;
    ensure(
        original_context()? == before,
        "original machine changed during read-only image admission",
    )?;
    for p in [
        receipt,
        &input,
        &old_materials_pin,
        &inner_pin,
        &stage_pin,
        &image,
        &public,
        &native,
        &preflight_pin,
        &private_status,
    ] {
        trusted(p)?;
    }
    let release: Value = read(&public, 2 * 1024 * 1024)?;
    let output = json!({"schema":"droidloom.original-initramfs-readback.v1","source_prepared":receipt,
        "producer_input":input,"producer_stage":stage_pin,"normal_producer":producer,
        "actual_private_build":inner_pin,"normal_package_state":normal_package_state,
        "original_host":before,"original_files_unchanged":original_files_unchanged,
        "normal_materials":materials,"fresh_admission":admission,"initrd":image,
        "host_source_commit":release["source_commit"],"host_source_tree":release["source_tree"],
        "kernel_payload_extract":kernel_command,"complete_readback":complete,
        "physical_install":false,"qualification_boot_authorized":false,"production_ready":false});
    save(&work.join("ORIGINAL-INITRAMFS-READBACK.json"), &output)?;
    Ok(output)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadbackPlan {
    schema: String,
    work_directory: PathBuf,
    prepared: FilePin,
}
pub(crate) fn verify_original_initramfs_files(path: &Path, expected: &str) -> Result<()> {
    let (plan, _): (ReadbackPlan, FilePin) = config(path, expected)?;
    ensure(
        plan.schema == "droidloom.original-initramfs-readback-plan.v1",
        "original initramfs readback plan schema",
    )?;
    let result = verify_prepared_original_initramfs(&plan.prepared, &plan.work_directory)?;
    println!(
        "{}",
        json!({"receipt":actual_pin(&plan.work_directory.join("ORIGINAL-INITRAMFS-READBACK.json"))?,
        "initrd":result["initrd"],"physical_install":false,"qualification_boot_authorized":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn record() -> Value {
        let rows = [
            "tools/droidloom-ubuntu-fixture/src/cold_original_initramfs.rs",
            "packaging/ubuntu/production/cold_modules.rs",
            "packaging/ubuntu/production/cold_transaction.py",
            "packaging/ubuntu/production/cold_apply.py",
            "packaging/ubuntu/production/native_release.py",
            "packaging/ubuntu/production/release.py",
        ]
        .iter()
        .map(|p| json!({"path":p,"bytes":1,"sha256":"a".repeat(64)}))
        .collect::<Vec<_>>();
        json!({"normal_build":{"args":["/home/qq/.cargo/bin/cargo","+1.93.0","build","--manifest-path",
            "/home/qq/work/source/tools/droidloom-ubuntu-fixture/Cargo.toml","--release","--locked","--offline","-j","2","-p","droidloom-ubuntu-fixture"],
            "exit_code":0,"seconds":1.0},"artifact":{"project_dependencies":rows}})
    }
    #[test]
    fn source_inventory_and_actual_normal_build_arguments_are_required() {
        let good = record();
        validate_normal_build(&good).unwrap();
        for bad in 0..5 {
            let mut value = good.clone();
            match bad {
                0 => {
                    value["normal_build"]["args"]
                        .as_array_mut()
                        .unwrap()
                        .push(json!("--features"));
                }
                1 => value["normal_build"]["exit_code"] = json!(1),
                2 => value["normal_build"]["args"][9] = json!("24"),
                3 => {
                    value["artifact"]["project_dependencies"]
                        .as_array_mut()
                        .unwrap()
                        .pop();
                }
                _ => {
                    let row = value["artifact"]["project_dependencies"][0].clone();
                    value["artifact"]["project_dependencies"]
                        .as_array_mut()
                        .unwrap()
                        .push(row);
                }
            };
            assert!(validate_normal_build(&value).is_err());
        }
    }
}
