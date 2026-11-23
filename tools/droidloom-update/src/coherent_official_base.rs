//! Publish the immutable official GSI, decoded independent vendor and optional
//! platform library view into the root-relative layout read by the image broker.
//! Producing a private tree neither selects a cohort nor starts its processes.
use super::*;
use droidloom_contracts::system_ext as library;
use std::ffi::CString;
use std::os::unix::ffi::OsStrExt;

fn raw_filesystem(role: &str, image: &FileRef) -> Result<()> {
    let header = bound_header(image, 1082)?;
    let raw = header[1080..1082] == [0x53, 0xef] || header[1024..1028] == [0xe2, 0xe1, 0xf5, 0xe0];
    if !raw || image.bytes % 512 != 0 || image.bytes < 4096 {
        return fail(format!("{role} must be an aligned raw Android filesystem"));
    }
    Ok(())
}

fn row(file: &str, image: &FileRef) -> Value {
    json!({"file":file,"bytes":image.bytes,"sha256":image.sha256})
}

fn declaration(system: &FileRef, vendor: &FileRef, extension: Option<&FileRef>) -> Value {
    let mut value = json!({"schema":1,"scope":"android_base_images_v1","layout":"gsi_system_as_root",
        "system":row("system.img",system),"vendor":row("vendor.img",vendor)});
    if let Some(ext) = extension {
        value["schema"] = json!(2);
        value["scope"] = json!("android_base_images_v2");
        value["system_ext_lib64"] = json!({"file":library::FILE,"bytes":ext.bytes,"sha256":ext.sha256,
            "target":library::TARGET,"source_system_sha256":system.sha256,"source_vendor_sha256":vendor.sha256});
    }
    value
}

fn rename_new(staging: &Path, destination: &Path) -> Result<()> {
    let old = CString::new(staging.as_os_str().as_bytes())?;
    let new = CString::new(destination.as_os_str().as_bytes())?;
    let rc = unsafe {
        libc::syscall(
            libc::SYS_renameat2,
            libc::AT_FDCWD,
            old.as_ptr(),
            libc::AT_FDCWD,
            new.as_ptr(),
            libc::RENAME_NOREPLACE,
        )
    };
    if rc != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}

/// Inputs are pins of the verified complete official image, the actual decoded
/// normal vendor and, if present, the read-back platform extension.
pub(super) fn publish(
    output: &Path,
    system: &FileRef,
    vendor: &FileRef,
    extension: Option<&FileRef>,
) -> Result<Value> {
    if system.sha256 != library::SYSTEM_SHA256 {
        return fail("base package requires the original reviewed CP3A system image");
    }
    let parent = output
        .parent()
        .ok_or("private base output needs a parent")?;
    let required = (system.bytes)
        .checked_add(vendor.bytes)
        .and_then(|n| n.checked_add(extension.map_or(0, |v| v.bytes)))
        .ok_or("base package size overflow")?;
    let _scope = resources::Scope::writing(parent, required)?;
    raw_filesystem("system", system)?;
    raw_filesystem("vendor", vendor)?;
    if let Some(ext) = extension {
        raw_filesystem("system extension", ext)?;
    }
    if output.symlink_metadata().is_ok() {
        return fail("official base output already exists");
    }
    let value = declaration(system, vendor, extension);
    let mut canonical = serde_json::to_vec_pretty(&value)?;
    canonical.push(b'\n');
    let cohort = format!("{:x}", Sha256::digest(&canonical));
    let temporary = tempfile::Builder::new()
        .prefix("official-base-stage-")
        .tempdir_in(parent)?;
    let stage = temporary.path();
    let images_path = PathBuf::from("var/lib/droidloom/cohorts")
        .join(&cohort)
        .join("images");
    let images = stage.join(&images_path);
    for (name, source) in [("system.img", system), ("vendor.img", vendor)]
        .into_iter()
        .chain(extension.map(|ext| (library::FILE, ext)))
    {
        copy_bound(source, &images.join(name))?;
    }
    let relative_manifest = PathBuf::from("etc/droidloom/cohorts").join(format!("{cohort}.json"));
    let manifest = stage.join(&relative_manifest);
    resources::prepare_output_directory(manifest.parent().unwrap())?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o444)
        .open(&manifest)?;
    file.write_all(&canonical)?;
    file.sync_all()?;
    drop(file);
    if pin(&manifest, MAX_JSON)?.sha256 != cohort {
        return fail("staged base declaration changed");
    }
    for tree in [&images, manifest.parent().unwrap()] {
        for dir in tree.ancestors().take_while(|p| p.starts_with(stage)) {
            File::open(dir)?.sync_all()?;
        }
    }
    for source in [system, vendor].into_iter().chain(extension) {
        recheck(source, MAX_IMAGE)?;
    }
    rename_new(stage, output)?;
    let _published_path = temporary.keep();
    File::open(parent)?.sync_all()?;
    Ok(
        json!({"layout":"droidloom-private-cohort-package-v1","cohort_sha256":cohort,
        "manifest":relative_manifest,"images_directory":images_path,"base":value}),
    )
}

fn verify_normal_vendor(value: &Value, vendor: &FileRef) -> Result<BTreeMap<String, String>> {
    if value["schema"] != "droidloom-official-gsi-independent-vendor-normal-result-v1"
        || value["normal_user_commands_returned_success"] != true
        || value["official_system_bytes_preserved"] != true
        || value["official_inputs"]["schema"] != "droidloom-official-cp3a-vendor-inputs-v1"
        || value["official_inputs"]["source_system_sha256"] != library::SYSTEM_SHA256
        || value["official_inputs"]["official_system_bytes_preserved"] != true
        || value["normal_vendor_image"]["bytes"].as_u64() != Some(vendor.bytes)
        || value["normal_vendor_image"]["sha256"].as_str() != Some(&vendor.sha256)
    {
        return fail(
            "complete independent normal vendor output differs from its selected provenance",
        );
    }
    let items = value["native_binaries"]
        .as_object()
        .ok_or("missing checked normal vendor libraries")?;
    library::HOST_MODULES
        .iter()
        .map(|module| {
            let name = format!("{module}.so");
            let key = format!("lib64/droidloom/nativebridge/{name}");
            let reference = items
                .get(&key)
                .ok_or("missing normal host translation library")?;
            let hash = reference["sha256"]
                .as_str()
                .ok_or("missing normal native library digest")?;
            if hash.len() != 64
                || !hash
                    .bytes()
                    .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
                || reference["bytes"].as_u64().unwrap_or(0) == 0
            {
                return fail("invalid normal host library reference");
            }
            Ok((name, hash.to_owned()))
        })
        .collect()
}

/// Package an already completed independent vendor. An optional extension is
/// checked again against the actual original GSI and each normal vendor ELF.
pub(crate) fn stage_existing(
    system_path: &Path,
    vendor_path: &Path,
    normal_path: &Path,
    normal_sha: &str,
    extension_path: Option<&Path>,
    output: &Path,
) -> Result<Value> {
    let parent = output
        .parent()
        .ok_or("private output needs an existing parent")?;
    if output.symlink_metadata().is_ok() {
        return fail("official base output already exists");
    }
    let scope = resources::Scope::writing(parent, 2 * resources::GIB)?;
    let (receipt, value) = read_json(normal_path)?;
    if receipt.sha256 != normal_sha {
        return fail("selected normal vendor receipt digest differs");
    }
    let system = pin(system_path, MAX_IMAGE)?;
    let vendor = pin(vendor_path, MAX_IMAGE)?;
    if system.sha256 != library::SYSTEM_SHA256 {
        return fail("official system is not the selected CP3A image");
    }
    let hosts = verify_normal_vendor(&value, &vendor)?;
    let temp = tempfile::Builder::new()
        .prefix("official-base-input-")
        .tempdir_in(parent)?;
    let (raw, converter) = decode_image(&vendor, &temp.path().join("vendor.raw.img"))?;
    let ext = extension_path
        .map(|p| pin(p, 32 * 1024 * 1024))
        .transpose()?;
    if value.get("system_ext_lib64").is_some() && ext.is_none() {
        return fail("the selected normal release requires its library extension");
    }
    if let Some(ext) = &ext {
        if let Some(normal) = value.get("system_ext_lib64") {
            let expected = declaration(&system, &raw, Some(ext));
            if normal.get("declaration") != expected.get("system_ext_lib64") {
                return fail("normal vendor and supplied extension select different raw artifacts");
            }
        }
        super::system_ext::verify_retained(&system, &raw, ext, &hosts, temp.path())?;
    }
    recheck(&receipt, MAX_JSON)?;
    recheck(&vendor, MAX_IMAGE)?;
    drop(scope);
    let package = publish(output, &system, &raw, ext.as_ref())?;
    Ok(
        json!({"package":package,"normal_vendor_receipt_sha256":receipt.sha256,
        "vendor_source_sha256":vendor.sha256,"raw_vendor_sha256":raw.sha256,"sparse_converter":converter}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn member(tag: &str) -> FileRef {
        FileRef {
            path: PathBuf::from("/cohort/image"),
            bytes: 4096,
            sha256: tag.repeat(64),
            identity: [0; 9],
        }
    }

    #[test]
    fn retained_base_declarations_bind_only_the_selected_raw_artifacts() {
        let (system, vendor, ext) = (member("1"), member("2"), member("3"));
        let v1 = declaration(&system, &vendor, None);
        assert_eq!(v1["schema"], 1);
        assert_eq!(v1["scope"], "android_base_images_v1");
        assert!(v1.get("system_ext_lib64").is_none());
        let v2 = declaration(&system, &vendor, Some(&ext));
        assert_eq!(v2["schema"], 2);
        assert_eq!(v2["scope"], "android_base_images_v2");
        assert_eq!(v1["system"], v2["system"]);
        assert_eq!(v1["vendor"], v2["vendor"]);
        assert_eq!(v2["vendor"]["file"], "vendor.img");
        let e = &v2["system_ext_lib64"];
        assert_eq!(e["target"], library::TARGET);
        assert_eq!(e["sha256"], ext.sha256);
        assert_eq!(e["source_system_sha256"], system.sha256);
        assert_eq!(e["source_vendor_sha256"], vendor.sha256);
    }

    #[test]
    fn retained_vendor_checks_source_hash_and_each_host_member() {
        let vendor = member("a");
        let libraries: serde_json::Map<_, _> = library::HOST_MODULES
            .iter()
            .map(|m| {
                (
                    format!("lib64/droidloom/nativebridge/{m}.so"),
                    json!({"bytes":8,"sha256":"5".repeat(64)}),
                )
            })
            .collect();
        let mut record = json!({"schema":"droidloom-official-gsi-independent-vendor-normal-result-v1","official_system_bytes_preserved":true,"normal_user_commands_returned_success":true,"official_inputs":{"schema":"droidloom-official-cp3a-vendor-inputs-v1","source_system_sha256":library::SYSTEM_SHA256,"official_system_bytes_preserved":true},"normal_vendor_image":row("vendor.img",&vendor),"native_binaries":libraries});
        assert_eq!(
            verify_normal_vendor(&record, &vendor).unwrap().len(),
            library::HOST_MODULES.len()
        );
        assert!(verify_normal_vendor(&record, &member("b")).is_err());
        let mut other_system = record.clone();
        other_system["official_inputs"]["source_system_sha256"] = json!("f".repeat(64));
        assert!(verify_normal_vendor(&other_system, &vendor).is_err());
        record["normal_vendor_image"]["bytes"] = json!(1);
        assert!(verify_normal_vendor(&record, &vendor).is_err());
        record["normal_vendor_image"]["bytes"] = json!(vendor.bytes);
        record["native_binaries"]
            .as_object_mut()
            .unwrap()
            .remove(&format!(
                "lib64/droidloom/nativebridge/{}.so",
                library::HOST_MODULES[0]
            ));
        assert!(verify_normal_vendor(&record, &vendor).is_err());
    }

    #[test]
    fn atomic_publication_keeps_a_concurrent_existing_package() {
        let temp = tempfile::tempdir().unwrap();
        let incoming = temp.path().join("incoming");
        let target = temp.path().join("selected");
        fs::create_dir(&incoming).unwrap();
        fs::create_dir(&target).unwrap();
        fs::write(target.join("owner"), b"existing").unwrap();
        assert!(rename_new(&incoming, &target).is_err());
        assert_eq!(fs::read(target.join("owner")).unwrap(), b"existing");
        assert!(incoming.is_dir());
        let new = temp.path().join("new");
        rename_new(&incoming, &new).unwrap();
        assert!(new.is_dir());
        assert!(!incoming.exists());
    }
}
