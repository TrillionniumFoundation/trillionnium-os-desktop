use crate::{
    Result, ensure, fs, materialize,
    model::{Content, Manifest},
};
use rustix::fs::{FileType, Mode, OFlags};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::File,
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FilePin {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}

pub fn open_pin(pin: &FilePin) -> Result<(File, crate::model::Identity)> {
    ensure(fs::valid_digest(&pin.sha256), "invalid file digest")?;
    ensure(
        pin.bytes <= 128 * 1024 * 1024 * 1024,
        "input exceeds bounded image size",
    )?;
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(&pin.path)?)?;
    let file = File::from(rustix::fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC | OFlags::NONBLOCK,
        Mode::empty(),
    )?);
    let before = fs::stat(&file)?;
    ensure(
        FileType::from_raw_mode(before.mode) == FileType::RegularFile && before.size == pin.bytes,
        "pinned input type or size differs",
    )?;
    Ok((file, before))
}

pub fn read_pin(pin: &FilePin, limit: u64) -> Result<Vec<u8>> {
    ensure(
        pin.bytes <= limit,
        "pinned input exceeds this operation's limit",
    )?;
    let (mut file, before) = open_pin(pin)?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 == pin.bytes
            && fs::digest(&bytes) == pin.sha256
            && fs::stat(&file)? == before,
        "input changed or digest differs",
    )?;
    Ok(bytes)
}

pub fn checked_file(pin: &FilePin) -> Result<File> {
    let (mut file, before) = open_pin(pin)?;
    ensure(
        fs::hash(&file)? == pin.sha256 && fs::stat(&file)? == before,
        "input changed or digest differs",
    )?;
    file.seek(SeekFrom::Start(0))?;
    Ok(file)
}

pub fn new_file(path: &Path, mode: u32) -> Result<File> {
    ensure(mode & !0o777 == 0, "unexpected file mode")?;
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(path)?)?;
    let p = fs::stat(&parent)?;
    ensure(
        p.uid == rustix::process::geteuid().as_raw() && p.mode & 0o022 == 0,
        "output parent is not protected by the current owner",
    )?;
    let f = File::from(rustix::fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o600),
    )?);
    rustix::fs::fchmod(&f, Mode::from_raw_mode(mode))?;
    Ok(f)
}

pub fn write_new(path: &Path, bytes: &[u8], mode: u32) -> Result<()> {
    let mut f = new_file(path, mode)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    f.seek(SeekFrom::Start(0))?;
    ensure(
        fs::hash(&f)? == fs::digest(bytes),
        "new output full readback differs",
    )
}

/// Copy from one held no-follow descriptor; zero runs become holes only in a new file.
pub fn copy_pin(pin: &FilePin, path: &Path, mode: u32) -> Result<()> {
    copy_pin_with_identity(pin, path, mode).map(|_| ())
}

/// Return the unchanged identity of the held source descriptor actually copied.
pub fn copy_pin_with_identity(pin: &FilePin, path: &Path, mode: u32) -> Result<crate::model::Identity> {
    let (mut input, before) = open_pin(pin)?;
    let mut output = new_file(path, mode)?;
    let mut hash = Sha256::new();
    let mut buffer = vec![0u8; 1024 * 1024];
    let mut count = 0u64;
    loop {
        let n = input.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        count = count.checked_add(n as u64).ok_or("input size overflow")?;
        ensure(count <= pin.bytes, "input grew during copy")?;
        hash.update(&buffer[..n]);
        if buffer[..n].iter().all(|v| *v == 0) {
            output.seek(SeekFrom::Current(n as i64))?;
        } else {
            output.write_all(&buffer[..n])?;
        }
    }
    ensure(
        count == pin.bytes
            && hex::encode(hash.finalize()) == pin.sha256
            && fs::stat(&input)? == before,
        "source identity or full content changed",
    )?;
    output.set_len(count)?;
    output.sync_all()?;
    output.seek(SeekFrom::Start(0))?;
    ensure(
        fs::hash(&output)? == pin.sha256,
        "independent destination readback differs",
    )?;
    Ok(before)
}

pub fn pin_file(path: &Path) -> Result<FilePin> {
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(path)?)?;
    let f = File::from(rustix::fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC | OFlags::NONBLOCK,
        Mode::empty(),
    )?);
    let before = fs::stat(&f)?;
    ensure(
        FileType::from_raw_mode(before.mode) == FileType::RegularFile,
        "output not regular",
    )?;
    let sha256 = fs::hash(&f)?;
    ensure(fs::stat(&f)? == before, "output changed while pinned")?;
    Ok(FilePin {
        path: path.to_owned(),
        bytes: before.size,
        sha256,
    })
}

pub fn private_dir(path: &Path) -> Result<()> {
    fs::Tree::create(
        &fs::absolute_string(path)?,
        rustix::process::geteuid().as_raw(),
    )?;
    Ok(())
}

/// Only trusted guest absolute paths, with no alias in any parent.
pub fn guest_path(root: &Path, guest: &str) -> Result<PathBuf> {
    let names = crate::paths::parts(guest)?;
    ensure(!names.is_empty(), "guest root is not a file destination")?;
    Ok(root.join(names.join("/")))
}

/// Resolve only public in-fixture aliases. Absolute symlinks are guest names,
/// never host paths; each component is inspected without following it.
pub fn resolve_public_file(root: &Path, guest: &str) -> Result<(FilePin, serde_json::Value)> {
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let mut current = guest.to_owned();
    let mut aliases = Vec::new();
    for _ in 0..32 {
        let names = crate::paths::parts(&current)?;
        let mut prefix = String::new();
        let mut next = None;
        for (index, name) in names.iter().enumerate() {
            prefix.push('/');
            prefix.push_str(name);
            let id = tree.identity(&prefix)?;
            match FileType::from_raw_mode(id.mode) {
                FileType::Symlink => {
                    let (_, target) = tree.read_link(&prefix)?;
                    let resolved = crate::paths::normalize_link(&prefix, &target)?;
                    aliases.push(serde_json::json!({"path":prefix,"target":target,"identity":id}));
                    next = Some(if index + 1 == names.len() {
                        resolved
                    } else {
                        format!("{resolved}/{}", names[index + 1..].join("/"))
                    });
                    break;
                }
                FileType::Directory if index + 1 != names.len() => {
                    ensure(
                        id.uid == 0 && id.mode & 0o022 == 0,
                        "public dependency parent is not root controlled",
                    )?;
                }
                FileType::RegularFile if index + 1 == names.len() => {
                    ensure(
                        id.uid == 0 && id.gid == 0 && id.mode & 0o022 == 0,
                        "public dependency file is not root controlled",
                    )?;
                }
                _ => {
                    return Err(
                        "public dependency resolves through a special or invalid object".into(),
                    );
                }
            }
        }
        if let Some(path) = next {
            current = path;
            continue;
        }
        let pin = pin_file(&guest_path(root, &current)?)?;
        return Ok((
            pin,
            serde_json::json!({"guest_path":guest,"resolved_path":current,"aliases":aliases}),
        ));
    }
    Err("public dependency alias cycle or excessive depth".into())
}

pub fn ensure_dir(root: &Path, guest: &str, mode: u32) -> Result<()> {
    let names = crate::paths::parts(guest)?;
    let tree = fs::Tree::open(
        &fs::absolute_string(root)?,
        rustix::process::geteuid().as_raw(),
    )?;
    let mut current = String::new();
    for name in names {
        current.push('/');
        current.push_str(name);
        match tree.identity(&current) {
            Ok(i) => ensure(
                FileType::from_raw_mode(i.mode) == FileType::Directory,
                "directory path is an alias or special file",
            )?,
            Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
                tree.mkdir(&current)?;
                rustix::fs::fchmod(&tree.dir(&current)?, Mode::from_raw_mode(0o755))?;
            }
            Err(e) => return Err(e),
        }
    }
    rustix::fs::fchmod(&tree.dir(guest)?, Mode::from_raw_mode(mode))?;
    Ok(())
}

pub fn clone_materialized(
    pin: &FilePin,
    source: &Path,
    destination: &Path,
) -> Result<serde_json::Value> {
    let manifest: Manifest = serde_json::from_slice(&read_pin(pin, 128 * 1024 * 1024)?)?;
    let source_name = fs::absolute_string(source)?;
    let destination_name = fs::absolute_string(destination)?;
    let original = materialize::verify(&manifest, &pin.sha256, &source_name, 0)?;
    let input = fs::Tree::open(&source_name, 0)?;
    let output = fs::Tree::create(&destination_name, 0)?;
    let mut dirs: Vec<_> = manifest
        .entries
        .iter()
        .filter(|e| e.content == Content::Directory)
        .collect();
    dirs.sort_by_key(|e| (e.path.matches('/').count(), e.path.as_str()));
    for e in &dirs {
        output.mkdir(&e.path)?;
    }
    for e in &manifest.entries {
        match &e.content {
            Content::Regular { sha256 } => {
                let id = input.identity(&e.path)?;
                ensure(
                    fs::same_metadata(&id, &e.source) && id.size == e.source.size,
                    "fixture metadata changed",
                )?;
                fs::copy_regular(&input, &output, &e.path, &id, sha256, &e.xattrs)?;
            }
            Content::Hardlink { target, .. } => output.hardlink(&e.path, target)?,
            Content::Symlink { target } => {
                let (id, actual) = input.read_link(&e.path)?;
                ensure(
                    actual == *target && fs::same_metadata(&id, &e.source),
                    "fixture link changed",
                )?;
                output.symlink(&e.path, target, &id)?;
            }
            Content::Directory => (),
        }
    }
    for e in dirs.iter().rev() {
        fs::set_metadata(&output.dir(&e.path)?, &e.source, &e.xattrs)?;
    }
    rustix::fs::fsync(&output.root)?;
    fs::assert_root_namespace(&source_name, &input)?;
    let result = materialize::verify(&manifest, &pin.sha256, &destination_name, 0)?;
    Ok(
        serde_json::json!({"source_verification":original,"clone_verification":result,"guest_qualified":false}),
    )
}

#[derive(Debug, Serialize)]
pub struct CommandResult {
    pub program: String,
    pub args: Vec<String>,
    pub exit_code: Option<i32>,
    pub timed_out: bool,
    pub log: FilePin,
}

pub fn run_logged(
    work: &Path,
    name: &str,
    program: &str,
    args: &[String],
    seconds: u64,
) -> Result<CommandResult> {
    run_logged_env(work, name, program, args, seconds, &BTreeMap::new())
}
pub fn run_logged_env(
    work: &Path,
    name: &str,
    program: &str,
    args: &[String],
    seconds: u64,
    extra: &BTreeMap<String, String>,
) -> Result<CommandResult> {
    ensure(
        extra
            .iter()
            .all(|(k, v)| k == "LD_LIBRARY_PATH" && Path::new(v).is_absolute()),
        "only a private explicit library path is supported",
    )?;
    ensure(
        name.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
            && !name.is_empty(),
        "invalid command evidence name",
    )?;
    ensure(
        Path::new(program).is_absolute() && seconds > 0 && seconds <= 3600,
        "command must be absolute and bounded",
    )?;
    let log_path = work.join(format!("{name}.log"));
    let log = new_file(&log_path, 0o600)?;
    let mut command = Command::new(program);
    command
        .args(args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C.UTF-8")
        .env("HOME", "/root")
        .envs(extra)
        .stdin(Stdio::null())
        .stdout(Stdio::from(log.try_clone()?))
        .stderr(Stdio::from(log));
    let mut child = crate::boot_child::OwnedChild::spawn(&mut command)?;
    let started = Instant::now();
    let mut timed_out = false;
    let status = loop {
        if let Some(s) = child.try_wait()? {
            break s;
        }
        if started.elapsed() > Duration::from_secs(seconds)
            || std::fs::metadata(&log_path)?.len() > 64 * 1024 * 1024
        {
            timed_out = true;
            break child.stop_and_reap()?;
        }
        std::thread::sleep(Duration::from_millis(100));
    };
    let result = CommandResult {
        program: program.into(),
        args: args.to_owned(),
        exit_code: status.code(),
        timed_out,
        log: pin_file(&log_path)?,
    };
    fs::write_json(
        &fs::absolute_string(&work.join(format!("{name}.json")))?,
        &result,
        rustix::process::geteuid().as_raw(),
    )?;
    ensure(
        !timed_out && status.success(),
        &format!("command {name} failed; inspect its retained original log"),
    )?;
    Ok(result)
}

pub fn clean_metadata(mode: u32) -> crate::model::Identity {
    crate::model::Identity {
        dev: 0,
        ino: 0,
        mode,
        uid: 0,
        gid: 0,
        nlink: 1,
        size: 0,
        mtime_sec: 0,
        mtime_nsec: 0,
        ctime_sec: 0,
        ctime_nsec: 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pinned_reads_reject_alias_and_content_change() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let path = dir.path().join("source");
        std::fs::write(&path, b"original")?;
        let pin = pin_file(&path)?;
        assert_eq!(read_pin(&pin, 100)?, b"original");
        std::fs::write(&path, b"modified")?;
        assert!(read_pin(&pin, 100).is_err());
        std::fs::remove_file(&path)?;
        std::os::unix::fs::symlink("target", &path)?;
        std::fs::write(dir.path().join("target"), b"original")?;
        assert!(read_pin(&pin, 100).is_err());
        Ok(())
    }
}
