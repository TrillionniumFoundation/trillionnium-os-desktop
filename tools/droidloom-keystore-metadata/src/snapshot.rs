use crate::Result;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};
use tempfile::TempDir;

const MAX_DATABASE_BYTES: u64 = 1024 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Fingerprint {
    pub(crate) sha256: String,
    metadata: Identity,
}
#[derive(Clone, Debug, PartialEq, Eq)]
struct Identity {
    dev: u64,
    ino: u64,
    len: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    atime: i64,
    atime_ns: i64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
fn identity(m: &Metadata) -> Identity {
    Identity {
        dev: m.dev(),
        ino: m.ino(),
        len: m.len(),
        mode: m.mode(),
        uid: m.uid(),
        gid: m.gid(),
        nlink: m.nlink(),
        atime: m.atime(),
        atime_ns: m.atime_nsec(),
        mtime: m.mtime(),
        mtime_ns: m.mtime_nsec(),
        ctime: m.ctime(),
        ctime_ns: m.ctime_nsec(),
    }
}
fn no_links(path: &Path) -> Result<()> {
    if !path.is_absolute() {
        return Err("absolute_path_required");
    }
    let mut prefix = PathBuf::new();
    for component in path.components() {
        match component {
            Component::RootDir | Component::Normal(_) => prefix.push(component.as_os_str()),
            _ => return Err("normalized_path_required"),
        }
        let m = fs::symlink_metadata(&prefix).map_err(|_| "path_unavailable")?;
        if m.file_type().is_symlink() {
            return Err("symlink_refused");
        }
    }
    Ok(())
}
fn open_input(path: &Path) -> Result<(File, Identity)> {
    no_links(path)?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NOATIME)
        .open(path)
        .map_err(|_| "readonly_noatime_open_failed")?;
    let m = file.metadata().map_err(|_| "input_metadata_failed")?;
    if !m.is_file() || m.nlink() != 1 {
        return Err("nonregular_or_hardlinked_input_refused");
    }
    Ok((file, identity(&m)))
}
fn verify_identity(path: &Path, file: &File, before: &Identity) -> Result<()> {
    let fd = file.metadata().map_err(|_| "input_metadata_failed")?;
    let path_m = fs::symlink_metadata(path).map_err(|_| "input_path_changed")?;
    if identity(&fd) != *before || identity(&path_m) != *before {
        return Err("input_changed_during_read");
    }
    Ok(())
}
pub(crate) fn hash_file(path: &Path) -> Result<Fingerprint> {
    let (mut file, before) = open_input(path)?;
    let mut hash = Sha256::new();
    let mut buf = [0_u8; 128 * 1024];
    loop {
        let n = file.read(&mut buf).map_err(|_| "input_read_failed")?;
        if n == 0 {
            break;
        }
        hash.update(&buf[..n]);
    }
    verify_identity(path, &file, &before)?;
    Ok(Fingerprint {
        sha256: hex::encode(hash.finalize()),
        metadata: before,
    })
}
pub(crate) fn read_json(path: &Path) -> Result<(Value, String)> {
    let (mut file, before) = open_input(path)?;
    if before.len > 1024 * 1024 {
        return Err("evidence_too_large");
    }
    let mut bytes = Vec::with_capacity(before.len as usize);
    file.read_to_end(&mut bytes)
        .map_err(|_| "evidence_read_failed")?;
    verify_identity(path, &file, &before)?;
    let value = serde_json::from_slice(&bytes).map_err(|_| "evidence_json_invalid")?;
    Ok((value, hex::encode(Sha256::digest(&bytes))))
}
fn no_sidecars(input: &Path) -> Result<()> {
    for suffix in ["-wal", "-shm", "-journal"] {
        let mut name = input.as_os_str().to_os_string();
        name.push(suffix);
        match fs::symlink_metadata(PathBuf::from(name)) {
            Ok(_) => return Err("sqlite_sidecar_requires_reviewed_snapshot_workflow"),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err("sidecar_state_unknown"),
        }
    }
    Ok(())
}
pub(crate) struct PrivateCopy {
    input: PathBuf,
    original: Fingerprint,
    private_dir: TempDir,
    pub(crate) input_sha256: String,
}
impl PrivateCopy {
    pub(crate) fn new(input: &Path, workspace: &Path) -> Result<Self> {
        if input.file_name().and_then(|s| s.to_str()) != Some("persistent.sqlite") {
            return Err("persistent_database_filename_required");
        }
        no_links(input)?;
        no_links(workspace)?;
        if !workspace.is_dir() {
            return Err("workspace_not_directory");
        }
        let parent = input.parent().ok_or("input_parent_missing")?;
        if workspace.starts_with(parent) {
            return Err("workspace_inside_input_refused");
        }
        no_sidecars(input)?;
        let original = hash_file(input)?;
        if original.metadata.len > MAX_DATABASE_BYTES {
            return Err("database_too_large");
        }
        let private_dir = tempfile::Builder::new()
            .prefix("droidloom-keystore-clone-")
            .tempdir_in(workspace)
            .map_err(|_| "private_directory_create_failed")?;
        fs::set_permissions(private_dir.path(), fs::Permissions::from_mode(0o700))
            .map_err(|_| "private_directory_mode_failed")?;
        let (mut source, before) = open_input(input)?;
        if before != original.metadata {
            return Err("input_changed_before_copy");
        }
        let database = private_dir.path().join("persistent.sqlite");
        let mut destination = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&database)
            .map_err(|_| "private_file_create_failed")?;
        std::io::copy(&mut source, &mut destination).map_err(|_| "private_copy_failed")?;
        destination
            .sync_all()
            .map_err(|_| "private_copy_sync_failed")?;
        verify_identity(input, &source, &before)?;
        let copied = hash_file(&database)?;
        if copied.sha256 != original.sha256 || copied.metadata.len != original.metadata.len {
            return Err("copied_bytes_mismatch");
        }
        no_sidecars(input)?;
        let result = Self {
            input: input.to_owned(),
            input_sha256: original.sha256.clone(),
            original,
            private_dir,
        };
        result.verify_input_unchanged()?;
        Ok(result)
    }
    pub(crate) fn directory(&self) -> &Path {
        self.private_dir.path()
    }
    pub(crate) fn database_path(&self) -> PathBuf {
        self.private_dir.path().join("persistent.sqlite")
    }
    pub(crate) fn verify_input_unchanged(&self) -> Result<()> {
        no_sidecars(&self.input)?;
        if hash_file(&self.input)? != self.original {
            return Err("source_changed_after_copy");
        }
        Ok(())
    }
    pub(crate) fn persist(self) -> Result<PathBuf> {
        self.verify_input_unchanged()?;
        Ok(self.private_dir.keep())
    }
}
pub(crate) fn write_new_json(path: &Path, value: &Value) -> Result<()> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|_| "receipt_create_failed")?;
    let bytes = serde_json::to_vec_pretty(value).map_err(|_| "receipt_serialize_failed")?;
    file.write_all(&bytes).map_err(|_| "receipt_write_failed")?;
    file.sync_all().map_err(|_| "receipt_sync_failed")
}
