use super::*;
use droidloom_contracts::system_ext as contract;

const NAME: &str = contract::READINESS_FILE;
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

pub(super) struct Checked {
    pub(super) image: FileRef,
    pub(super) declaration: contract::ReadinessDeclaration,
}

/// Check a completed normal component directly against the selected whole GSI,
/// the normal Soong installation digests, and the contents and labels of the
/// fourth filesystem. No paths from the recorded builder are reopened here.
pub(super) fn verify_retained(
    system: &FileRef,
    vendor: &FileRef,
    library: &FileRef,
    image: FileRef,
    normal: &Value,
    workspace: &Path,
) -> Result<Checked> {
    let installed = |name: &str, limit: u64| -> Result<&str> {
        let entry = &normal[name];
        if !entry["bytes"].as_u64().is_some_and(|n| n > 0 && n <= limit) {
            return fail("invalid normal installed observer member size");
        }
        entry["sha256"]
            .as_str()
            .ok_or_else(|| "missing normal observer member digest".into())
    };
    let elf_sha = installed("installed_elf", 8 * 1024 * 1024)?;
    let rc_sha = installed("installed_rc", 4096)?;
    if normal["file"] != NAME
        || normal["bytes"].as_u64() != Some(image.bytes)
        || normal["sha256"].as_str() != Some(&image.sha256)
        || normal["source_system_sha256"].as_str() != Some(&system.sha256)
        || normal["mount_subtrees"] != json!(contract::READINESS_TARGETS)
        || rc_sha != format!("{:x}", Sha256::digest(RC))
        || normal["readback"]["parents"]
            != json!({"system":system.sha256,"elf":elf_sha,"rc":rc_sha})
        || !normal["host_init_verifier"]["bytes"]
            .as_u64()
            .is_some_and(|n| n > 0)
    {
        return fail(
            "the normal readiness receipt does not bind these installed members and source",
        );
    }
    let (checked, members) =
        verify_members(system, vendor, library, image, elf_sha, rc_sha, workspace)?;
    if members != normal["readback"]["members"] {
        return fail("fourth filesystem contents differ from the normal build");
    }
    Ok(checked)
}

/// Compare the complete carrier to its original GSI and to the reviewed two added files.
pub(super) fn verify_members(
    system: &FileRef,
    vendor: &FileRef,
    library: &FileRef,
    image: FileRef,
    elf_sha: &str,
    rc_sha: &str,
    workspace: &Path,
) -> Result<(Checked, Value)> {
    let decl = contract::ReadinessDeclaration {
        file: NAME.to_owned(),
        bytes: image.bytes,
        sha256: image.sha256.clone(),
        targets: contract::READINESS_TARGETS.map(str::to_owned),
        source_system_sha256: system.sha256.clone(),
        source_vendor_sha256: vendor.sha256.clone(),
        source_system_ext_lib64_sha256: library.sha256.clone(),
        observer_sha256: elf_sha.to_owned(),
        init_rc_sha256: rc_sha.to_owned(),
    };
    let temp = tempfile::Builder::new()
        .prefix("verify-system-readiness-")
        .tempdir_in(workspace)?;
    let cwd = temp.path();
    let python = reader_tool("python3")?;
    let debug = reader_tool("debugfs")?;
    let fsck = reader_tool("e2fsck")?;
    let inputs = json!({"system":system.path,"existing_image":image.path,
        "sha256":{"system":system.sha256,"elf":elf_sha,"rc":rc_sha},
        "tools":{"debugfs":debug.path,"e2fsck":fsck.path}});
    write(&cwd.join("inputs.json"), serde_json::to_vec(&inputs)?)?;
    let log = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(cwd.join("readback.json"))?;
    checked_tool(
        &python,
        Command::new(&python.path)
            .args(["-I", "-c", BUILDER, "inputs.json"])
            .current_dir(cwd)
            .stdout(Stdio::from(log)),
    )?;
    let (_, actual) = read_json(&cwd.join("readback.json"))?;
    if actual["sha256"].as_str() != Some(&image.sha256)
        || actual["bytes"].as_u64() != Some(image.bytes)
    {
        return fail("fourth image members differ from the normal build and the original GSI");
    }
    for tool in [&debug, &fsck] {
        recheck(tool, 256 * 1024 * 1024)?;
    }
    for input in [system, vendor, library, &image] {
        recheck(input, MAX_IMAGE)?;
    }
    Ok((
        Checked {
            image,
            declaration: decl,
        },
        actual["members"].clone(),
    ))
}
