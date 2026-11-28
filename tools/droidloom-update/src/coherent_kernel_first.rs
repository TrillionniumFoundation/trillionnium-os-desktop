//! Publish the exact stock init referenced by an independently selected four-image base.
use super::*;
use std::os::unix::fs::PermissionsExt;

#[path = "coherent_device_source.rs"]
mod device_source;
#[path = "coherent_kernel_query.rs"]
mod query_inputs;

const SCOPE: &str = "android_kernel_first_stage_v2";
const INIT_SHA256: &str = "9f69cc83a88db5f8533014cfea5ad9ea8e0454120335329aec27f8d65b2a9537";
const INIT_BYTES: u64 = 2_934_488;

pub(super) fn install(root: &Path, cohort: &str, system: &FileRef) -> Result<Value> {
    if system.sha256 != droidloom_contracts::system_ext::SYSTEM_SHA256 {
        return fail("kernel-first init must come from the selected original CP3A system");
    }
    let temp = tempfile::Builder::new().prefix("kernel-first-init-").tempdir_in(root)?;
    let reader = reader_tool("debugfs")?;
    checked_tool(&reader, Command::new(&reader.path).current_dir(temp.path())
        .args(["-R", "dump /system/bin/init stock-init"]).arg(&system.path))?;
    let init = pin(&temp.path().join("stock-init"), INIT_BYTES)?;
    let header = bound_header(&init, 20)?;
    if init.bytes != INIT_BYTES || init.sha256 != INIT_SHA256 ||
        &header[..7] != b"\x7fELF\x02\x01\x01" || header[18..20] != [62, 0] {
        return fail("selected /system/bin/init is not the expected original x86_64 CP3A ELF");
    }
    recheck(system, MAX_IMAGE)?;
    let query = query_inputs::prepare(temp.path(), system, &reader)?;
    let value = json!({"schema":2,"scope":SCOPE,"base_cohort_sha256":cohort,
        "source_system_sha256":system.sha256,"init_path":"/system/bin/init","init_bytes":init.bytes,
        "init_sha256":init.sha256,"argv":["/system/bin/init","second_stage"],
        "query_inputs":query.declaration});
    let mut bytes = serde_json::to_vec_pretty(&value)?;
    bytes.push(b'\n');
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let relative = Path::new("etc/droidloom/runtime-cohorts").join(format!("{digest}.json"));
    let query_inputs = query.publish(root, &digest)?;
    let devices = device_source::publish(root, temp.path(), system, cohort, &digest)?;
    let dest = root.join(&relative);
    let dir = dest.parent().ok_or("missing runtime manifest parent")?;
    resources::prepare_output_directory(dir)?;
    let mut file = tempfile::NamedTempFile::new_in(dir)?;
    file.as_file().set_permissions(fs::Permissions::from_mode(0o444))?;
    file.write_all(&bytes)?;
    file.as_file().sync_all()?;
    match file.persist_noclobber(&dest) {
        Ok(_) => {}
        Err(e) if e.error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(e) => return Err(e.error.into()),
    }
    if pin(&dest, MAX_JSON)?.sha256 != digest {
        return fail("published kernel-first runtime manifest differs");
    }
    for path in dir.ancestors().take_while(|p| p.starts_with(root)) {
        File::open(path)?.sync_all()?;
    }
    Ok(json!({"runtime_manifest_sha256":digest, "manifest":relative,"runtime":value,"board_device_source":devices,"query_inputs":query_inputs}))
}

/// Recheck and add only the content-addressed runtime declaration to an already published v3 base.
pub(crate) fn bind_existing(root: &Path, cohort: &str) -> Result<Value> {
    use droidloom_contracts::system_ext as library;
    if cohort.len() != 64 || !cohort.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
        return fail("invalid base selection digest");
    }
    let _scope = resources::Scope::writing(root, 32 * 1024 * 1024)?;
    let (manifest, base) = read_json(&root.join("etc/droidloom/cohorts").join(format!("{cohort}.json")))?;
    if manifest.sha256 != cohort || base["schema"] != 3 || base["scope"] != "android_base_images_v3"
        || base["layout"] != "gsi_system_as_root" {
        return fail("kernel-first runtime requires its complete selected four-image manifest");
    }
    let images = root.join("var/lib/droidloom/cohorts").join(cohort).join("images");
    let mut checked = Vec::new();
    for (role, filename) in [("system","system.img"), ("vendor","vendor.img"), ("system_ext_lib64",library::FILE),
                            ("system_ext_readiness",library::READINESS_FILE)] {
        let image = pin(&images.join(filename), MAX_IMAGE)?;
        let entry = &base[role];
        if entry["file"] != filename || entry["bytes"] != image.bytes || entry["sha256"] != image.sha256 {
            return fail(format!("complete selected raw input differs for {role}"));
        }
        checked.push(image);
    }
    let lib = serde_json::from_value(base["system_ext_lib64"].clone())?;
    let ready = serde_json::from_value(base["system_ext_readiness"].clone())?;
    if !library::accepts_base(3,"android_base_images_v3",Some(&lib),Some(&ready),&checked[0].sha256,&checked[1].sha256) {
        return fail("kernel-first runtime requires the library and readiness media of the same selected release");
    }
    let result = install(root, cohort, &checked[0])?;
    recheck(&manifest, MAX_JSON)?;
    for image in &checked { recheck(image, MAX_IMAGE)?; }
    Ok(result)
}
