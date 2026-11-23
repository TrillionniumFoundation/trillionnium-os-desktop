use super::*;

const NAME: &str = "system_ext_readiness.img";
const BUILDER: &str = include_str!("official_readiness_image.py");
const RC: &[u8] =
    include_bytes!("../../../android/framework/droidloom-readiness/droidloom-readiness.rc");

pub(crate) fn build(
    system: &Path,
    product: &Path,
    vendor_build: &Path,
    output: &Path,
) -> Result<Value> {
    let _scope = resources::Scope::writing(output, 32 * 1024 * 1024)?;
    let system = pin(system, MAX_IMAGE)?;
    let mut candidates = BTreeSet::new();
    for relative in ["system_ext", "system/system_ext"] {
        let dir = product.join(relative);
        if dir.join("bin/droidloom-readiness").is_file() {
            let location = dir.canonicalize()?;
            if !location.starts_with(product) {
                return fail("readiness install escaped its product");
            }
            candidates.insert(location);
        }
    }
    if candidates.len() != 1 {
        return fail("expected one system_ext installation of the normal readiness service");
    }
    let install = candidates
        .into_iter()
        .next()
        .expect("one checked candidate");
    let elf = pin(&install.join("bin/droidloom-readiness"), 8 * 1024 * 1024)?;
    let rc = pin(&install.join("etc/init/droidloom-readiness.rc"), 4096)?;
    if bound_body(&rc, 4096)? != RC {
        return fail("the installed readiness init script differs from the normal product");
    }
    let host = vendor_build.join("host/linux-x86/bin");
    let host_tool = |name: &str| -> Result<FileRef> {
        let path = host.join(name).canonicalize()?;
        if !path.starts_with(vendor_build) {
            return fail("Android readiness build tool outside its normal output");
        }
        pin(&path, 256 * 1024 * 1024)
    };
    let verifier = host_tool("host_init_verifier")?;
    checked_tool(&verifier, Command::new(&verifier.path).arg(&rc.path))?;
    let tools = BTreeMap::from([
        ("debugfs", reader_tool("debugfs")?),
        ("e2fsck", reader_tool("e2fsck")?),
        ("mke2fs", host_tool("mke2fs")?),
    ]);
    let tool_paths: BTreeMap<_, _> = tools.iter().map(|(k, v)| (k, &v.path)).collect();
    let temp = tempfile::Builder::new()
        .prefix("build-readiness-")
        .tempdir_in(output)?;
    let work = temp.path();
    let image = work.join(NAME);
    let config = json!({"system":system.path,"elf":elf.path,"rc":rc.path,"output":image,
        "sha256":{"system":system.sha256,"elf":elf.sha256,"rc":rc.sha256},"tools":tool_paths});
    write(&work.join("inputs.json"), serde_json::to_vec(&config)?)?;
    let python = reader_tool("python3")?;
    let record = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(work.join("readback.json"))?;
    checked_tool(
        &python,
        Command::new(&python.path)
            .args(["-I", "-c", BUILDER, "inputs.json"])
            .current_dir(work)
            .stdout(Stdio::from(record)),
    )?;
    let (_, readback) = read_json(&work.join("readback.json"))?;
    let artifact = pin(&image, 16 * 1024 * 1024)?;
    if readback["sha256"].as_str() != Some(artifact.sha256.as_str())
        || readback["bytes"].as_u64() != Some(artifact.bytes)
    {
        return fail("readiness carrier readback differs from its complete ext4 bytes");
    }
    for tool in tools.values() {
        recheck(tool, 256 * 1024 * 1024)?;
    }
    recheck(&system, MAX_IMAGE)?;
    recheck(&elf, 8 * 1024 * 1024)?;
    recheck(&rc, 4096)?;
    fs::hard_link(&artifact.path, output.join(NAME))?;
    File::open(output)?.sync_all()?;
    Ok(
        json!({"file":NAME,"bytes":artifact.bytes,"sha256":artifact.sha256,
        "source_system_sha256":system.sha256,"installed_elf":elf,"installed_rc":rc,
        "mount_subtrees": ["/system/system_ext/bin","/system/system_ext/etc/init"],
        "readback":readback,"host_init_verifier":verifier,"production_signed":false}),
    )
}
