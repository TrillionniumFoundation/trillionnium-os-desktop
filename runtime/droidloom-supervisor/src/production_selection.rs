//! The one root-selected production cell and its exact public source inputs.
//!
//! Selection is configuration, never identity or namespace authority. The
//! caller still has to obtain IdentityAuthority, its durable reservation and
//! complete HostAdmission. No request can supply a runtime path, executable,
//! UID map, callback, or serialized privilege token.

use std::ffi::{CString, OsStr};
use std::fs::{File, Metadata};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};

use serde::Deserialize;
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::{AndroidImageLayout, CellSpec};

const SELECTION: &str = "/etc/droidloom/production/selected.json";
const SPECIFICATION: &str = "/etc/droidloom/cell.json";
const SELECTION_LIMIT: u64 = 16 * 1024;
const SPEC_LIMIT: u64 = 1024 * 1024;
const SCHEMA: &str = "droidloom-production-selection-v1";

#[derive(Debug, Error)]
pub(crate) enum SelectionError {
    #[error("production selection rejected: {0}")]
    Rejected(&'static str),
    #[error("production selection or its exact cell specification changed")]
    Changed,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error("invalid production selection JSON: {0}")]
    Json(#[from] serde_json::Error),
}

type Result<T> = std::result::Result<T, SelectionError>;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    schema: String,
    host_uid: u32,
    cell_spec_bytes: u64,
    cell_spec_sha256: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Node {
    device: u64,
    inode: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    modified: (i64, i64),
    changed: (i64, i64),
}

impl Node {
    fn from(metadata: &Metadata) -> Self {
        Self {
            device: metadata.dev(),
            inode: metadata.ino(),
            mode: metadata.mode(),
            uid: metadata.uid(),
            gid: metadata.gid(),
            links: metadata.nlink(),
            bytes: metadata.len(),
            modified: (metadata.mtime(), metadata.mtime_nsec()),
            changed: (metadata.ctime(), metadata.ctime_nsec()),
        }
    }
}

struct SealedFile {
    path: PathBuf,
    file: File,
    node: Node,
    sha256: String,
    limit: u64,
}

/// Not serializable or constructible from a parsed JSON record. Both held
/// files have already passed the fixed root custody and exact-byte checks.
pub(crate) struct ProductionSelection {
    selected: SealedFile,
    specification: SealedFile,
    spec: CellSpec,
    base_cohort: String,
    runtime_manifest: String,
}

impl ProductionSelection {
    pub(crate) fn load(spec_path: &Path, peer_uid: u32) -> Result<Self> {
        if spec_path.as_os_str() != OsStr::new(SPECIFICATION) {
            return Err(SelectionError::Rejected(
                "production accepts only the fixed package cell specification",
            ));
        }
        let (selected, selected_bytes) = SealedFile::read(Path::new(SELECTION), SELECTION_LIMIT)?;
        let record: Record = serde_json::from_slice(&selected_bytes)?;
        validate_record(&record)?;
        if peer_uid != 0 && peer_uid != record.host_uid {
            return Err(SelectionError::Rejected(
                "SO_PEERCRED does not own the selected host user",
            ));
        }
        // Only the fixed public configuration can be opened, even by root.
        // All components are traversed from a held / descriptor without
        // following links; complete bytes match the selection before parsing.
        let (specification, specification_bytes) = SealedFile::read(spec_path, SPEC_LIMIT)?;
        if specification.node.bytes != record.cell_spec_bytes
            || specification.sha256 != record.cell_spec_sha256
        {
            return Err(SelectionError::Rejected(
                "cell specification is not the exact root selection",
            ));
        }
        let spec: CellSpec = serde_json::from_slice(&specification_bytes)?;
        validate_spec(&record, &spec)?;
        selected.revalidate()?;
        specification.revalidate()?;
        Ok(Self {
            selected,
            specification,
            spec,
            base_cohort: record.base_cohort_sha256,
            runtime_manifest: record.runtime_manifest_sha256,
        })
    }

    pub(crate) fn spec(&self) -> &CellSpec {
        &self.spec
    }

    pub(crate) fn base_cohort(&self) -> &str {
        &self.base_cohort
    }

    /// This digest is configuration only. PreparedRuntime must independently
    /// validate its root-sealed manifest against the actual witness and lease.
    pub(crate) fn runtime_manifest(&self) -> &str {
        &self.runtime_manifest
    }

    pub(crate) fn same_selection(&self, other: &Self) -> bool {
        self.selected.sha256 == other.selected.sha256
            && self.specification.sha256 == other.specification.sha256
            && self.spec == other.spec
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        self.selected.revalidate()?;
        self.specification.revalidate()
    }
}

fn validate_record(record: &Record) -> Result<()> {
    if record.schema != SCHEMA
        || record.host_uid == 0
        || record.host_uid == u32::MAX
        || record.cell_spec_bytes == 0
        || record.cell_spec_bytes > SPEC_LIMIT
        || !digest(&record.cell_spec_sha256)
        || !digest(&record.base_cohort_sha256)
        || !digest(&record.runtime_manifest_sha256)
    {
        return Err(SelectionError::Rejected(
            "unsupported or incomplete root selection",
        ));
    }
    Ok(())
}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn validate_spec(record: &Record, spec: &CellSpec) -> Result<()> {
    if spec.host_uid != record.host_uid {
        return Err(SelectionError::Rejected(
            "selected host user differs from the specification",
        ));
    }
    spec.validate()
        .map_err(|_| SelectionError::Rejected("cell specification violates the normal contract"))?;
    let images = PathBuf::from("/var/lib/droidloom/cohorts")
        .join(&record.base_cohort_sha256)
        .join("images");
    if spec.image_layout != AndroidImageLayout::GsiSystemAsRoot
        || spec.image_dir != images
        || spec.vendor_image != images.join("vendor.img")
        || spec.data_dir
            != PathBuf::from(format!("/var/lib/droidloom/users/{}/data", spec.host_uid))
    {
        return Err(SelectionError::Rejected(
            "production requires the selected GSI base and original user-data identity",
        ));
    }
    // These development fields are not silently ignored. A separately
    // reviewed same-cohort runtime manifest is the only override authority.
    // Original user data is reserved by identity metadata only; this initial
    // production backend assembles fresh private tmpfs data and metadata.
    if spec.gapps_dir.is_some()
        || spec.android_init.is_some()
        || !spec.android_file_overrides.is_empty()
        || !spec.android_runtime_directories.is_empty()
        || !spec.shared_storage_directories.is_empty()
    {
        return Err(SelectionError::Rejected(
            "legacy init, overrides, runtime trees, GApps or host shares are not production inputs",
        ));
    }
    Ok(())
}

impl SealedFile {
    fn read(path: &Path, limit: u64) -> Result<(Self, Vec<u8>)> {
        let file = open_root_trusted(path)?;
        let node = Node::from(&file.metadata()?);
        require_public_regular(&node, limit)?;
        require_no_capability(&file)?;
        let bytes = read_exact_file(&file, &node, limit)?;
        let sha256 = format!("{:x}", Sha256::digest(&bytes));
        let sealed = Self {
            path: path.to_owned(),
            file,
            node,
            sha256,
            limit,
        };
        sealed.revalidate_path()?;
        Ok((sealed, bytes))
    }

    fn revalidate_path(&self) -> Result<()> {
        if Node::from(&self.file.metadata()?) != self.node {
            return Err(SelectionError::Changed);
        }
        let fresh = open_root_trusted(&self.path)?;
        if Node::from(&fresh.metadata()?) != self.node {
            return Err(SelectionError::Changed);
        }
        require_no_capability(&self.file)?;
        Ok(())
    }

    fn revalidate(&self) -> Result<()> {
        self.revalidate_path()?;
        let bytes = read_exact_file(&self.file, &self.node, self.limit)?;
        if format!("{:x}", Sha256::digest(bytes)) != self.sha256 {
            return Err(SelectionError::Changed);
        }
        self.revalidate_path()
    }
}

fn require_public_regular(node: &Node, limit: u64) -> Result<()> {
    if node.mode & libc::S_IFMT != libc::S_IFREG
        || node.uid != 0
        || node.gid != 0
        || node.links != 1
        || node.mode & 0o6022 != 0
        || node.bytes == 0
        || node.bytes > limit
    {
        return Err(SelectionError::Rejected(
            "bounded single-link root-owned non-writable regular input required",
        ));
    }
    Ok(())
}

fn require_no_capability(file: &File) -> Result<()> {
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    if count >= 0 {
        return Err(SelectionError::Rejected(
            "public configuration carries a file capability",
        ));
    }
    let error = io::Error::last_os_error();
    if !matches!(error.raw_os_error(), Some(libc::ENODATA | libc::EOPNOTSUPP)) {
        return Err(error.into());
    }
    Ok(())
}

fn read_exact_file(file: &File, expected: &Node, limit: u64) -> Result<Vec<u8>> {
    // pread avoids shared-offset races with this same held open file.
    use std::os::unix::fs::FileExt;
    if Node::from(&file.metadata()?) != *expected {
        return Err(SelectionError::Changed);
    }
    require_public_regular(expected, limit)?;
    let mut bytes = vec![0_u8; expected.bytes as usize];
    let mut offset = 0;
    while offset < bytes.len() {
        match file.read_at(&mut bytes[offset..], offset as u64) {
            Ok(0) => return Err(SelectionError::Changed),
            Ok(n) => offset += n,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        }
    }
    let mut extra = [0_u8; 1];
    if file.read_at(&mut extra, expected.bytes)? != 0 || Node::from(&file.metadata()?) != *expected
    {
        return Err(SelectionError::Changed);
    }
    Ok(bytes)
}

fn open_root_trusted(path: &Path) -> Result<File> {
    let mut components = path.components();
    if components.next() != Some(Component::RootDir) {
        return Err(SelectionError::Rejected(
            "normalized absolute root-selected input required",
        ));
    }
    let names: Vec<&OsStr> = components
        .map(|component| match component {
            Component::Normal(name) => Ok(name),
            _ => Err(SelectionError::Rejected(
                "input contains a non-normal path component",
            )),
        })
        .collect::<Result<_>>()?;
    if names.is_empty() || names.len() > 32 {
        return Err(SelectionError::Rejected("bounded file path required"));
    }
    let mut normalized = PathBuf::from("/");
    for name in &names {
        normalized.push(name);
    }
    if normalized.as_os_str() != path.as_os_str() {
        return Err(SelectionError::Rejected(
            "input path is not in exact normalized form",
        ));
    }
    // O_PATH permits traversal but grants no directory enumeration or body
    // access. O_NOFOLLOW is checked at every component, including the leaf.
    let root = unsafe {
        libc::open(
            c"/".as_ptr(),
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if root < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut directory = unsafe { File::from_raw_fd(root) };
    require_trusted_directory(&directory)?;
    for (index, name) in names.iter().enumerate() {
        let name = CString::new(name.as_bytes())
            .map_err(|_| SelectionError::Rejected("NUL in input path"))?;
        let last = index + 1 == names.len();
        let flags = libc::O_NOFOLLOW
            | libc::O_CLOEXEC
            | libc::O_NONBLOCK
            | if last {
                libc::O_RDONLY
            } else {
                libc::O_PATH | libc::O_DIRECTORY
            };
        let raw = unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(), flags) };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let next = unsafe { File::from_raw_fd(raw) };
        require_trusted_directory(&directory)?;
        if last {
            return Ok(next);
        }
        require_trusted_directory(&next)?;
        directory = next;
    }
    Err(SelectionError::Rejected("input leaf absent"))
}

fn require_trusted_directory(file: &File) -> Result<()> {
    let metadata = file.metadata()?;
    if !metadata.is_dir()
        || metadata.uid() != 0
        || metadata.gid() != 0
        || metadata.mode() & 0o6022 != 0
    {
        return Err(SelectionError::Rejected(
            "root-owned non-writable directory chain required",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record() -> Record {
        Record {
            schema: SCHEMA.into(),
            host_uid: 1000,
            cell_spec_bytes: 800,
            cell_spec_sha256: "a".repeat(64),
            base_cohort_sha256: "b".repeat(64),
            runtime_manifest_sha256: "c".repeat(64),
        }
    }

    #[test]
    fn production_selection_rejects_non_digest_or_unbounded_source() {
        let mut r = record();
        validate_record(&r).unwrap();
        r.runtime_manifest_sha256 = "../runtime".into();
        assert!(validate_record(&r).is_err());
        r = record();
        r.runtime_manifest_sha256 = "C".repeat(64);
        assert!(validate_record(&r).is_err());
        r = record();
        r.cell_spec_bytes = SPEC_LIMIT + 1;
        assert!(validate_record(&r).is_err());
        r = record();
        r.host_uid = 0;
        assert!(validate_record(&r).is_err());
    }

    #[test]
    fn production_selection_json_cannot_supply_a_token_path_or_callback() {
        let raw = format!(
            r#"{{"schema":"{SCHEMA}","host_uid":1000,"cell_spec_bytes":800,"cell_spec_sha256":"{}","base_cohort_sha256":"{}","runtime_manifest_sha256":"{}"}}"#,
            "a".repeat(64),
            "b".repeat(64),
            "c".repeat(64)
        );
        validate_record(&serde_json::from_str(&raw).unwrap()).unwrap();
        for member in [
            r#""runtime_path":"/tmp/x""#,
            r#""admitted":true"#,
            r#""pid":1"#,
        ] {
            let changed = format!("{},{}{}", &raw[..raw.len() - 1], member, "}");
            assert!(serde_json::from_str::<Record>(&changed).is_err());
        }
    }

    #[test]
    fn production_selection_metadata_rejects_links_writable_and_special_inputs() {
        let regular = Node {
            device: 1,
            inode: 2,
            mode: libc::S_IFREG | 0o600,
            uid: 0,
            gid: 0,
            links: 1,
            bytes: 80,
            modified: (1, 0),
            changed: (1, 0),
        };
        require_public_regular(&regular, 100).unwrap();
        for n in [
            Node {
                links: 2,
                ..regular.clone()
            },
            Node {
                uid: 1000,
                ..regular.clone()
            },
            Node {
                mode: libc::S_IFREG | 0o620,
                ..regular.clone()
            },
            Node {
                mode: libc::S_IFIFO | 0o600,
                ..regular.clone()
            },
            Node {
                mode: libc::S_IFREG | 0o4600,
                ..regular.clone()
            },
            Node {
                bytes: 101,
                ..regular.clone()
            },
        ] {
            assert!(require_public_regular(&n, 100).is_err());
        }
    }

    #[test]
    fn production_selection_refuses_relative_or_parent_paths_before_open() {
        for p in ["relative", "/", "/etc/../etc/passwd"] {
            assert!(open_root_trusted(Path::new(p)).is_err());
        }
    }
}
