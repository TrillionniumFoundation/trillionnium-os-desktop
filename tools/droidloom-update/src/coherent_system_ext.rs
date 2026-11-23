use super::*;

const TARGET: &str = "/system/system_ext/lib64";
const NAME: &str = "system_ext_lib64.img";
const BUILDER: &str = include_str!("official_vendor_system_ext.py");

/// Create the complete private system-extension lib64 view from the exact two
/// finished input images and the already validated Soong host module digests.
pub(crate) fn build(
    system_image: &Path,
    vendor_image: &Path,
    vendor_build: &Path,
    output_dir: &Path,
    modules: &BTreeMap<String, String>,
) -> Result<Value> {
    let _scope = resources::Scope::writing(output_dir, 2 * resources::GIB)?;
    let temporary = tempfile::Builder::new()
        .prefix("platform-nativebridge-")
        .tempdir_in(output_dir)?;
    let work = temporary.path();
    let system = pin(system_image, MAX_IMAGE)?;
    let vendor = pin(vendor_image, MAX_IMAGE)?;
    let (raw_vendor, converter) = decode_image(&vendor, &work.join("vendor.raw.img"))?;
    let host = vendor_build.join("host/linux-x86/bin");
    let output = output_dir.join(NAME);
    if output.symlink_metadata().is_ok() {
        return fail("the platform extension destination already exists");
    }
    let python = reader_tool("python3")?;
    let mut tools = BTreeMap::new();
    tools.insert("debugfs", reader_tool("debugfs")?);
    for name in ["e2fsdroid", "mke2fs", "e2fsck"] {
        let normal = host.join(name);
        let reference = if normal.is_file() {
            let actual = normal.canonicalize()?;
            if !actual.starts_with(vendor_build) {
                return fail(format!("normal image tool outside its build: {name}"));
            }
            pin(&actual, 256 * 1024 * 1024)?
        } else if name == "e2fsck" {
            reader_tool(name)?
        } else {
            return fail(format!("normal vendor image tool was not built: {name}"));
        };
        tools.insert(name, reference);
    }
    let tool_paths: BTreeMap<_, _> = tools
        .iter()
        .map(|(name, value)| (name, &value.path))
        .collect();
    let parameters = json!({
        "system": system.path, "vendor": raw_vendor.path,
        "native_hashes": modules, "tools": tool_paths
    });
    write(&work.join("inputs.json"), serde_json::to_vec(&parameters)?)?;
    checked_tool(
        &python,
        Command::new(&python.path)
            .args(["-I", "-c", BUILDER, "inputs.json"])
            .current_dir(work),
    )?;
    for tool in tools.values() {
        recheck(tool, 256 * 1024 * 1024)?;
    }
    recheck(&system, MAX_IMAGE)?;
    recheck(&raw_vendor, MAX_IMAGE)?;
    recheck(&vendor, MAX_IMAGE)?;
    let (_, detail) = read_json(&work.join("receipt.json"))?;
    let image = pin(&work.join(NAME), 32 * 1024 * 1024)?;
    if detail["sha256"].as_str() != Some(&image.sha256)
        || detail["bytes"].as_u64() != Some(image.bytes)
        || detail["target"].as_str() != Some(TARGET)
    {
        return fail("the platform-private filesystem receipt differs from the actual image");
    }
    let declaration = json!({"file":NAME, "bytes":image.bytes, "sha256":image.sha256,
        "target":TARGET, "source_system_sha256":system.sha256, "source_vendor_sha256":raw_vendor.sha256});
    fs::hard_link(&image.path, &output)?;
    fs::remove_file(&image.path)?;
    let published = pin(&output, 32 * 1024 * 1024)?;
    if published.sha256 != image.sha256 || published.bytes != image.bytes {
        return fail("the published private system extension differs from the completed image");
    }
    Ok(
        json!({"declaration":declaration,"members":detail["member_sha256"],
        "platform_file_contexts_sha256":detail["platform_contexts_sha256"],
        "system":system,"vendor":vendor,"raw_vendor_sha256":raw_vendor.sha256,
        "sparse_converter":converter,"tools":tools,"production_signed":false}),
    )
}
