//! Read-only held files and directories for one returned-copy observation.
//! No source pins supplied by a public caller enter this layer. Its callers
//! resolve every record from the fixed, source-produced first-once history.
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    ensure, fs,
    model::Identity,
};
use rustix::fs::FileType;
use std::{
    collections::BTreeMap,
    fs::File,
    io::Seek,
    path::{Path, PathBuf},
};

pub(super) struct HeldFile {
    pin: FilePin,
    held: File,
    identity: Identity,
    attributes: BTreeMap<String, String>,
}
impl HeldFile {
    pub(super) fn open(pin: &FilePin, limit: u64, mode: Option<u32>, label: bool) -> Result<Self> {
        ensure(
            pin.bytes <= limit && fs::valid_digest(&pin.sha256),
            "bounded returned-history file required",
        )?;
        let tree = fs::Tree::open("/", 0)?;
        let file = tree.file(&fs::absolute_string(&pin.path)?)?;
        let identity = fs::stat(&file)?;
        ensure(
            FileType::from_raw_mode(identity.mode) == FileType::RegularFile
                && identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.size == pin.bytes
                && identity.mode & 0o7022 == 0
                && mode.is_none_or(|m| identity.mode & 0o7777 == m),
            "returned-history file lost its fixed root ownership, mode, link or size",
        )?;
        let attributes = fs::xattrs(&file)?;
        ensure(
            attributes.is_empty() || (label && attributes.keys().all(|k| k == "security.selinux")),
            "returned-history file has an unapproved attribute",
        )?;
        let value = Self {
            pin: pin.clone(),
            held: file,
            identity,
            attributes,
        };
        value.guard()?;
        Ok(value)
    }
    pub(super) fn pin(&self) -> &FilePin {
        &self.pin
    }
    pub(super) fn identity(&self) -> &Identity {
        &self.identity
    }
    pub(super) fn guard_custody(&self) -> Result<()> {
        let named = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&self.pin.path)?)?;
        ensure(
            fs::stat(&self.held)? == self.identity
                && fs::stat(&named)? == self.identity
                && fs::xattrs(&self.held)? == self.attributes
                && fs::xattrs(&named)? == self.attributes
                && fs::stat(&self.held)? == self.identity
                && fs::stat(&named)? == self.identity,
            "held or named returned-history file changed",
        )
    }
    pub(super) fn guard(&self) -> Result<()> {
        self.guard_custody()?;
        (&self.held).rewind()?;
        ensure(
            fs::hash(&self.held)? == self.pin.sha256,
            "returned-history body changed",
        )?;
        self.guard_custody()
    }
    pub(super) fn bytes(&self, limit: u64) -> Result<Vec<u8>> {
        ensure(
            self.pin.bytes <= limit,
            "returned-history read exceeds its source bound",
        )?;
        self.guard_custody()?;
        let body = files::read_pin(&self.pin, limit)?;
        ensure(
            body.len() as u64 == self.pin.bytes && fs::digest(&body) == self.pin.sha256,
            "returned-history read differs from its held source",
        )?;
        self.guard_custody()?;
        Ok(body)
    }
    pub(super) fn json(&self, limit: u64) -> Result<serde_json::Value> {
        Ok(serde_json::from_slice(&self.bytes(limit)?)?)
    }
}

pub(super) struct HeldDirectory {
    path: PathBuf,
    file: File,
    identity: Identity,
    names: Vec<String>,
}
impl HeldDirectory {
    pub(super) fn open(path: &Path, max: usize) -> Result<Self> {
        let file = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(path)?)?;
        let identity = fs::stat(&file)?;
        ensure(
            identity.uid == 0 && identity.gid == 0 && identity.mode & 0o7777 == 0o700,
            "returned-history directory is not the protected normal directory",
        )?;
        let names = Self::names(path, max)?;
        let value = Self {
            path: path.to_owned(),
            file,
            identity,
            names,
        };
        value.guard()?;
        Ok(value)
    }
    fn names(path: &Path, max: usize) -> Result<Vec<String>> {
        let mut names = Vec::new();
        for e in std::fs::read_dir(path)? {
            ensure(
                names.len() < max,
                "returned-history directory member bound exceeded",
            )?;
            let name = e?
                .file_name()
                .into_string()
                .map_err(|_| "non-UTF8 history member")?;
            ensure(
                !name.is_empty() && name != "." && name != ".." && !name.contains('/'),
                "invalid returned-history member",
            )?;
            names.push(name);
        }
        names.sort();
        ensure(
            names.windows(2).all(|v| v[0] != v[1]),
            "duplicate returned-history member",
        )?;
        Ok(names)
    }
    pub(super) fn names_observed(&self) -> &[String] {
        &self.names
    }
    pub(super) fn guard(&self) -> Result<()> {
        let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(&self.path)?)?;
        ensure(
            fs::stat(&self.file)? == self.identity
                && fs::stat(&named)? == self.identity
                && Self::names(&self.path, self.names.len().saturating_add(1))? == self.names
                && fs::stat(&self.file)? == self.identity
                && fs::stat(&named)? == self.identity,
            "returned-history directory or its closed members changed",
        )
    }
}

/// A finite set of source-produced pins; readback never creates missing files.
pub(super) struct Records {
    files: BTreeMap<PathBuf, HeldFile>,
}
impl Records {
    pub(super) fn new() -> Self {
        Self {
            files: BTreeMap::new(),
        }
    }
    pub(super) fn read(&mut self, pin: &FilePin, limit: u64) -> Result<serde_json::Value> {
        if let Some(old) = self.files.get(&pin.path) {
            ensure(
                old.pin().bytes == pin.bytes && old.pin().sha256 == pin.sha256,
                "one returned-history path acquired two source identities",
            )?;
            return old.json(limit);
        }
        ensure(
            self.files.len() < 4096,
            "returned-history source count exceeded",
        )?;
        let file = HeldFile::open(pin, limit, Some(0o400), false)?;
        let body = file.json(limit)?;
        self.files.insert(pin.path.clone(), file);
        Ok(body)
    }
    pub(super) fn read_mode(
        &mut self,
        pin: &FilePin,
        limit: u64,
        mode: u32,
    ) -> Result<serde_json::Value> {
        self.include_file(pin, limit, mode)?;
        self.files[&pin.path].json(limit)
    }
    pub(super) fn include_file(&mut self, pin: &FilePin, limit: u64, mode: u32) -> Result<()> {
        if let Some(old) = self.files.get(&pin.path) {
            ensure(
                old.pin().bytes == pin.bytes
                    && old.pin().sha256 == pin.sha256
                    && old.identity().mode & 0o7777 == mode,
                "one historical file acquired two identities",
            )?;
            return old.guard_custody();
        }
        ensure(
            self.files.len() < 4096,
            "returned-history source count exceeded",
        )?;
        self.files.insert(
            pin.path.clone(),
            HeldFile::open(pin, limit, Some(mode), false)?,
        );
        Ok(())
    }
    pub(super) fn include_source(&mut self, pin: &FilePin, expected: &Identity) -> Result<()> {
        ensure(![
            "/var/lib/droidloom/users/1000/data/data.img",
            "/var/lib/droidloom/users/1000/data/metadata.img",
            "/var/lib/droidloom-qualification/p4-private-account-working-copy-516eec-r1/data.img",
            "/var/lib/droidloom-qualification/p4-private-account-working-copy-516eec-r1/metadata.img",
        ].iter().any(|p| pin.path == Path::new(p)),
            "private image bodies cannot enter the historical source reader")?;
        if let Some(old) = self.files.get(&pin.path) {
            ensure(
                old.identity() == expected
                    && old.pin().bytes == pin.bytes
                    && old.pin().sha256 == pin.sha256,
                "duplicate historical source differs",
            )?;
            return old.guard_custody();
        }
        ensure(
            self.files.len() < 4096,
            "returned-history source count exceeded",
        )?;
        let file = HeldFile::open(pin, pin.bytes, None, false)?;
        ensure(
            file.identity() == expected,
            "historical source inode differs from actual first-once admission",
        )?;
        self.files.insert(pin.path.clone(), file);
        Ok(())
    }
    pub(super) fn guard(&self) -> Result<()> {
        for file in self.files.values() {
            file.guard_custody()?;
        }
        Ok(())
    }
    pub(super) fn pins(&self) -> Vec<&FilePin> {
        self.files.values().map(HeldFile::pin).collect()
    }
}
