//! Build the generation-local source of fixed Android device inodes from the selected factory image.
use super::*;
use std::os::unix::fs::PermissionsExt;

const BUILDER: &str = include_str!("official_device_source.py");
const NAME: &str = "android-device-source.img";
use droidloom_contracts::system_ext::{DEVICE_SOURCE_BYTES as IMAGE_BYTES, DEVICE_SOURCE_SHA256};

pub(super) fn publish(
    root: &Path,
    temp: &Path,
    system: &FileRef,
    cohort: &str,
    runtime: &str,
) -> Result<Value> {
    let work = tempfile::Builder::new()
        .prefix("stock-devices-")
        .tempdir_in(temp)?;
    let work = work.path();
    let tools = BTreeMap::from([
        ("mke2fs", reader_tool("mke2fs")?),
        ("debugfs", reader_tool("debugfs")?),
        ("e2fsck", reader_tool("e2fsck")?),
    ]);
    let paths: BTreeMap<_, _> = tools
        .iter()
        .map(|(key, value)| (key, &value.path))
        .collect();
    write(
        &work.join("input.json"),
        serde_json::to_vec(&json!({"system":system.path, "tools":paths}))?,
    )?;
    let record = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(work.join("readback.json"))?;
    let python = reader_tool("python3")?;
    checked_tool(
        &python,
        Command::new(&python.path)
            .args(["-I", "-B", "-c", BUILDER, "input.json"])
            .current_dir(work)
            .stdout(Stdio::from(record)),
    )?;
    for tool in tools.values() {
        recheck(tool, 256 * 1024 * 1024)?;
    }
    recheck(system, MAX_IMAGE)?;
    let image = pin(&work.join(NAME), IMAGE_BYTES)?;
    let (_, record) = read_json(&work.join("readback.json"))?;
    if image.bytes != IMAGE_BYTES
        || image.sha256 != DEVICE_SOURCE_SHA256
        || record["bytes"] != image.bytes
        || record["sha256"] != image.sha256
    {
        return fail("full Android device source differs from its completed inode readback");
    }
    let directory = root
        .join("var/lib/droidloom/cohorts")
        .join(cohort)
        .join("board");
    resources::prepare_output_directory(&directory)?;
    let relative = format!("{}.img", image.sha256);
    let destination = directory.join(&relative);
    fs::set_permissions(&image.path, fs::Permissions::from_mode(0o444))?;
    File::open(&image.path)?.sync_all()?;
    match fs::hard_link(&image.path, &destination) {
        Ok(()) => {
            fs::remove_file(&image.path)?;
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error.into()),
    }
    if pin(&destination, IMAGE_BYTES)?.sha256 != image.sha256 {
        return fail("existing board device source changed");
    }
    File::open(&directory)?.sync_all()?;
    let declaration = json!({"schema":1, "scope":"android_private_device_source_v1", "base_cohort_sha256":cohort,
        "runtime_manifest_sha256":runtime, "source_system_sha256":system.sha256, "file":relative,
        "bytes":image.bytes, "sha256":image.sha256, "readback":record});
    let mut body = serde_json::to_vec_pretty(&declaration)?;
    body.push(b'\n');
    let digest = format!("{:x}", Sha256::digest(&body));
    let relative = Path::new("etc/droidloom/board-devices").join(format!("{digest}.json"));
    let output = root.join(&relative);
    let directory = output.parent().ok_or("missing device declaration parent")?;
    resources::prepare_output_directory(directory)?;
    let mut file = tempfile::NamedTempFile::new_in(directory)?;
    file.as_file()
        .set_permissions(fs::Permissions::from_mode(0o444))?;
    file.write_all(&body)?;
    file.as_file().sync_all()?;
    match file.persist_noclobber(&output) {
        Ok(_) => {}
        Err(e) if e.error.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(e) => return Err(e.error.into()),
    }
    if pin(&output, MAX_JSON)?.sha256 != digest {
        return fail("selected device declaration changed");
    }
    File::open(directory)?.sync_all()?;
    Ok(json!({"manifest":relative, "sha256":digest, "source":declaration}))
}
