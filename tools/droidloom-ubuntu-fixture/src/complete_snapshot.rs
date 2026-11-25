//! Descriptor based complete snapshots of a fresh, offline distribution root.
//! This is separate from the public-file selector: its authority is the normal
//! bootstrap/install receipt and a root-owned private enclosing directory.
use crate::model::{Content, Identity};
use crate::{Result, ensure, fs, paths};
use rustix::fs::{self as rfs, AtFlags, FileType, Mode, OFlags, ResolveFlags};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::Read;
use std::path::Path;

pub(super) const MAX_ENTRIES: usize = 500_000;
const MAX_BYTES: u64 = 64 * 1024 * 1024 * 1024;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct CompleteEntry {
    pub path: String,
    pub source: Identity,
    pub content: Content,
    pub xattrs: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StaticDevice {
    pub path: String,
    pub source: Identity,
    pub major: u32,
    pub minor: u32,
}

pub(super) fn device_allowed(path: &str, major: u32, minor: u32) -> bool {
    matches!(
        (path, major, minor),
        ("/dev/null", 1, 3)
            | ("/dev/zero", 1, 5)
            | ("/dev/full", 1, 7)
            | ("/dev/random", 1, 8)
            | ("/dev/urandom", 1, 9)
            | ("/dev/tty", 5, 0)
            | ("/dev/console", 5, 1)
            | ("/dev/ptmx", 5, 2)
    )
}

pub(super) struct Snapshot {
    pub root: File,
}

impl Snapshot {
    pub fn open(path: &Path) -> Result<Self> {
        let name = fs::absolute_string(path)?;
        ensure(
            path.file_name().and_then(|v| v.to_str()) == Some("root")
                && path.parent().and_then(Path::parent)
                    == Some(Path::new("/var/lib/droidloom-qualification")),
            "complete root must be a protected qualification root",
        )?;
        let parent = fs::Tree::open(
            &fs::absolute_string(path.parent().ok_or("root parent")?)?,
            0,
        )?;
        let id = fs::stat(&parent.root)?;
        ensure(
            id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o700,
            "complete root enclosing directory is not private",
        )?;
        let tree = fs::Tree::open(&name, 0)?;
        let id = fs::stat(&tree.root)?;
        ensure(
            id.uid == 0 && id.gid == 0 && [0o700, 0o755].contains(&(id.mode & 0o7777)),
            "complete root mode or owner differs",
        )?;
        Ok(Self { root: tree.root })
    }

    #[cfg(test)]
    pub fn test_open(path: &Path) -> Result<Self> {
        let root = File::from(rfs::open(
            path,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        Ok(Self { root })
    }

    fn beneath(&self, path: &str, flags: OFlags) -> Result<File> {
        let parts = paths::parts(path)?;
        Ok(File::from(rfs::openat2(
            &self.root,
            parts.join("/"),
            flags | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
            ResolveFlags::BENEATH
                | ResolveFlags::NO_SYMLINKS
                | ResolveFlags::NO_MAGICLINKS
                | ResolveFlags::NO_XDEV,
        )?))
    }

    pub fn directory(&self, path: &str) -> Result<File> {
        if path == "/" {
            return Ok(self.root.try_clone()?);
        }
        self.beneath(path, OFlags::RDONLY | OFlags::DIRECTORY)
    }

    pub fn parent(&self, path: &str) -> Result<(File, String)> {
        let parts = paths::parts(path)?;
        let name = parts.last().ok_or("missing leaf")?.to_string();
        let parent = if parts.len() == 1 {
            self.root.try_clone()?
        } else {
            self.directory(&format!("/{}", parts[..parts.len() - 1].join("/")))?
        };
        Ok((parent, name))
    }

    pub fn raw_stat(&self, path: &str) -> Result<rfs::Stat> {
        let (parent, name) = self.parent(path)?;
        Ok(rfs::statat(&parent, name, AtFlags::SYMLINK_NOFOLLOW)?)
    }

    pub fn identity(&self, path: &str) -> Result<Identity> {
        Ok(fs::identity(&self.raw_stat(path)?))
    }

    pub fn file(&self, path: &str) -> Result<File> {
        let file = self.beneath(path, OFlags::RDONLY | OFlags::NONBLOCK)?;
        ensure(
            FileType::from_raw_mode(fs::stat(&file)?.mode) == FileType::RegularFile,
            "complete source input is not a regular file",
        )?;
        Ok(file)
    }

    pub fn bytes(&self, path: &str, limit: u64) -> Result<Vec<u8>> {
        let mut file = self.file(path)?;
        let before = fs::stat(&file)?;
        ensure(before.size <= limit, "complete input exceeds size bound")?;
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(limit + 1)
            .read_to_end(&mut bytes)?;
        ensure(
            bytes.len() as u64 == before.size
                && fs::stat(&file)? == before
                && self.identity(path)? == before,
            "complete input changed while read",
        )?;
        Ok(bytes)
    }

    pub fn link(&self, path: &str) -> Result<(Identity, String)> {
        let (parent, name) = self.parent(path)?;
        let before = self.identity(path)?;
        ensure(
            FileType::from_raw_mode(before.mode) == FileType::Symlink,
            "not a symlink",
        )?;
        let target = rfs::readlinkat(&parent, name, Vec::new())?.into_string()?;
        ensure(self.identity(path)? == before, "complete symlink changed")?;
        normalize_link(path, &target)?;
        Ok((before, target))
    }

    pub fn names(&self, path: &str) -> Result<Vec<String>> {
        let directory = self.directory(path)?;
        let before = fs::stat(&directory)?;
        let mut stream = rfs::Dir::read_from(&directory)?;
        let mut names = Vec::new();
        for entry in &mut stream {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if name != "." && name != ".." {
                ensure(!name.contains(['\n', '\r']), "invalid complete source name")?;
                names.push(name.to_owned());
            }
        }
        ensure(
            fs::stat(&directory)? == before,
            "complete directory changed during inventory",
        )?;
        names.sort();
        Ok(names)
    }

    fn walk_inner(&self, parent: &str, paths: &mut BTreeMap<String, Identity>) -> Result<()> {
        for name in self.names(parent)? {
            let path = format!("{}/{name}", parent.trim_end_matches('/'));
            let id = self.identity(&path)?;
            ensure(
                path.matches('/').count() <= 128,
                "complete directory depth exceeds bound",
            )?;
            ensure(
                paths.len() < MAX_ENTRIES && paths.insert(path.clone(), id.clone()).is_none(),
                "complete tree is oversized or has duplicate names",
            )?;
            if FileType::from_raw_mode(id.mode) == FileType::Directory {
                self.walk_inner(&path, paths)?;
            }
        }
        Ok(())
    }

    pub fn inventory(&self) -> Result<BTreeMap<String, Identity>> {
        let mut paths = BTreeMap::new();
        self.walk_inner("/", &mut paths)?;
        Ok(paths)
    }

    pub fn regular(&self, path: &str) -> Result<(Identity, String, BTreeMap<String, String>)> {
        let file = self.file(path)?;
        let before = fs::stat(&file)?;
        let attrs = fs::xattrs(&file)?;
        let sha = fs::hash(&file)?;
        ensure(
            fs::stat(&file)? == before && self.identity(path)? == before,
            "complete source changed while hashed",
        )?;
        Ok((before, sha, attrs))
    }
}

pub(super) fn normalize_link(path: &str, target: &str) -> Result<String> {
    ensure(
        !target.is_empty() && !target.contains(['\0', '\n', '\r']),
        "invalid complete source symlink target",
    )?;
    let mut parts: Vec<&str> = if target.starts_with('/') {
        Vec::new()
    } else {
        paths::parent(path)
            .split('/')
            .filter(|p| !p.is_empty())
            .collect()
    };
    for part in target.split('/') {
        match part {
            "" | "." => (),
            ".." => ensure(parts.pop().is_some(), "complete symlink escapes guest root")?,
            value => parts.push(value),
        }
    }
    Ok(format!("/{}", parts.join("/")))
}

pub(super) fn capture(tree: &Snapshot) -> Result<(Vec<CompleteEntry>, Vec<StaticDevice>)> {
    let inventory = tree.inventory()?;
    let mut entries = Vec::new();
    let mut devices = Vec::new();
    let mut originals =
        BTreeMap::<(u64, u64), (String, Identity, String, BTreeMap<String, String>)>::new();
    let mut counts = BTreeMap::<(u64, u64), u64>::new();
    let mut total = 0u64;
    for (path, before) in &inventory {
        let (content, xattrs) = match FileType::from_raw_mode(before.mode) {
            FileType::Directory => {
                let fd = tree.directory(path)?;
                ensure(
                    fs::stat(&fd)? == *before,
                    "complete directory identity changed",
                )?;
                (Content::Directory, fs::xattrs(&fd)?)
            }
            FileType::RegularFile => {
                let key = (before.dev, before.ino);
                *counts.entry(key).or_default() += 1;
                if let Some((primary, id, sha, attrs)) = originals.get(&key) {
                    ensure(id == before, "complete hardlink identity changed")?;
                    (
                        Content::Hardlink {
                            target: primary.clone(),
                            sha256: sha.clone(),
                        },
                        attrs.clone(),
                    )
                } else {
                    let (id, sha, attrs) = tree.regular(path)?;
                    ensure(id == *before, "complete source changed before content read")?;
                    total = total
                        .checked_add(id.size)
                        .ok_or("complete root size overflow")?;
                    ensure(total <= MAX_BYTES, "complete root exceeds byte limit")?;
                    originals.insert(key, (path.clone(), id, sha.clone(), attrs.clone()));
                    (Content::Regular { sha256: sha }, attrs)
                }
            }
            FileType::Symlink => {
                let (id, target) = tree.link(path)?;
                ensure(id == *before, "complete link identity changed")?;
                (Content::Symlink { target }, BTreeMap::new())
            }
            FileType::CharacterDevice => {
                let actual = tree.raw_stat(path)?;
                let (major, minor) = (rfs::major(actual.st_rdev), rfs::minor(actual.st_rdev));
                ensure(
                    fs::identity(&actual) == *before
                        && before.uid == 0
                        && before.nlink == 1
                        && device_allowed(path, major, minor),
                    "complete root contains an unapproved special device",
                )?;
                devices.push(StaticDevice {
                    path: path.clone(),
                    source: before.clone(),
                    major,
                    minor,
                });
                continue;
            }
            _ => {
                return Err(
                    format!("complete root contains live or unsupported inode: {path}").into(),
                );
            }
        };
        entries.push(CompleteEntry {
            path: path.clone(),
            source: before.clone(),
            content,
            xattrs,
        });
    }
    for (key, (_, id, _, _)) in originals {
        ensure(
            counts.get(&key) == Some(&id.nlink),
            "complete source has a regular hardlink outside the frozen root",
        )?;
    }
    ensure(
        tree.inventory()? == inventory,
        "complete root changed during full capture",
    )?;
    Ok((entries, devices))
}

pub(super) fn verify(
    tree: &Snapshot,
    entries: &[CompleteEntry],
    devices: &[StaticDevice],
) -> Result<(usize, u64)> {
    let inventory = tree.inventory()?;
    let expected: BTreeSet<_> = entries
        .iter()
        .map(|e| e.path.clone())
        .chain(devices.iter().map(|e| e.path.clone()))
        .collect();
    ensure(
        expected.len() == entries.len() + devices.len()
            && inventory.keys().cloned().collect::<BTreeSet<_>>() == expected,
        "complete root has missing or unexpected members",
    )?;
    let mut regular = 0usize;
    let mut bytes = 0u64;
    for e in entries {
        let current = inventory.get(&e.path).ok_or("complete member absent")?;
        ensure(
            fs::same_metadata(current, &e.source),
            "complete member metadata differs",
        )?;
        match &e.content {
            Content::Directory => ensure(
                fs::xattrs(&tree.directory(&e.path)?)? == e.xattrs,
                "complete directory privilege metadata differs",
            )?,
            Content::Symlink { target } => ensure(
                tree.link(&e.path)?.1 == *target,
                "complete link target differs",
            )?,
            Content::Regular { sha256 } | Content::Hardlink { sha256, .. } => {
                let (id, hash, attrs) = tree.regular(&e.path)?;
                ensure(
                    id.size == e.source.size
                        && id.nlink == e.source.nlink
                        && hash == *sha256
                        && attrs == e.xattrs,
                    "complete member bytes or privilege metadata differ",
                )?;
                regular += 1;
                if let Content::Hardlink { target, .. } = &e.content {
                    let primary = tree.identity(target)?;
                    ensure(
                        id.dev == primary.dev && id.ino == primary.ino,
                        "complete hardlink topology differs",
                    )?;
                } else {
                    bytes = bytes.checked_add(id.size).ok_or("complete size overflow")?;
                }
            }
        }
    }
    for e in devices {
        let raw = tree.raw_stat(&e.path)?;
        ensure(
            fs::same_metadata(&fs::identity(&raw), &e.source)
                && raw.st_rdev == rfs::makedev(e.major, e.minor)
                && device_allowed(&e.path, e.major, e.minor),
            "complete static device differs",
        )?;
    }
    ensure(
        tree.inventory()? == inventory,
        "complete root changed during verification",
    )?;
    Ok((regular, bytes))
}

enum CopyInput<'a> {
    Tree(&'a Snapshot),
    Payload(&'a mut File),
}

pub(super) fn copy(
    source: &Snapshot,
    destination: &Path,
    entries: &[CompleteEntry],
    devices: &[StaticDevice],
) -> Result<Snapshot> {
    copy_inner(CopyInput::Tree(source), destination, entries, devices)
}

pub(super) fn copy_payload(
    payload: &mut File,
    destination: &Path,
    entries: &[CompleteEntry],
    devices: &[StaticDevice],
) -> Result<Snapshot> {
    copy_inner(CopyInput::Payload(payload), destination, entries, devices)
}

fn copy_inner(
    mut input: CopyInput<'_>,
    destination: &Path,
    entries: &[CompleteEntry],
    devices: &[StaticDevice],
) -> Result<Snapshot> {
    ensure(
        destination.file_name().and_then(|v| v.to_str()) == Some("root")
            && destination.parent().and_then(Path::parent)
                == Some(Path::new("/var/lib/droidloom-qualification")),
        "complete destination must be a protected qualification root",
    )?;
    let parent = fs::Tree::open(
        &fs::absolute_string(destination.parent().ok_or("destination parent")?)?,
        0,
    )?;
    let id = fs::stat(&parent.root)?;
    ensure(
        id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o700,
        "complete destination parent is not private",
    )?;
    let created = fs::Tree::create(&fs::absolute_string(destination)?, 0)?;
    let output = Snapshot { root: created.root };
    let mut directories: Vec<_> = entries
        .iter()
        .filter(|e| e.content == Content::Directory)
        .collect();
    directories.sort_by_key(|e| (e.path.matches('/').count(), e.path.as_str()));
    for e in &directories {
        let (parent, name) = output.parent(&e.path)?;
        rfs::mkdirat(&parent, name, Mode::from_raw_mode(0o700))?;
    }
    for e in entries {
        match &e.content {
            Content::Regular { sha256 } => {
                let (parent, name) = output.parent(&e.path)?;
                let mut new = File::from(rfs::openat(
                    &parent,
                    name,
                    OFlags::RDWR
                        | OFlags::CREATE
                        | OFlags::EXCL
                        | OFlags::NOFOLLOW
                        | OFlags::CLOEXEC,
                    Mode::from_raw_mode(0o600),
                )?);
                match &mut input {
                    CopyInput::Tree(source) => {
                        let mut file = source.file(&e.path)?;
                        let before = fs::stat(&file)?;
                        ensure(
                            fs::same_metadata(&before, &e.source)
                                && before.size == e.source.size
                                && fs::xattrs(&file)? == e.xattrs,
                            "complete source differs before copy",
                        )?;
                        let copied = std::io::copy(
                            &mut Read::by_ref(&mut file).take(before.size + 1),
                            &mut new,
                        )?;
                        ensure(
                            copied == before.size
                                && fs::stat(&file)? == before
                                && source.identity(&e.path)? == before,
                            "complete source changed during copy",
                        )?;
                    }
                    CopyInput::Payload(payload) => {
                        let copied = std::io::copy(
                            &mut Read::by_ref(*payload).take(e.source.size),
                            &mut new,
                        )?;
                        ensure(
                            copied == e.source.size,
                            "complete transport truncated an original file",
                        )?;
                    }
                }
                use std::io::{Seek, SeekFrom};
                new.seek(SeekFrom::Start(0))?;
                ensure(fs::hash(&new)? == *sha256, "complete copied bytes differ")?;
                fs::set_metadata(&new, &e.source, &e.xattrs)?;
            }
            Content::Hardlink { target, .. } => {
                let (parent, name) = output.parent(&e.path)?;
                let (old_parent, old_name) = output.parent(target)?;
                rfs::linkat(&old_parent, old_name, &parent, name, AtFlags::empty())?;
            }
            Content::Symlink { target } => {
                if let CopyInput::Tree(source) = &input {
                    ensure(
                        source.link(&e.path)?.1 == *target,
                        "complete source link changed",
                    )?;
                }
                let (parent, name) = output.parent(&e.path)?;
                rfs::symlinkat(target, &parent, name.as_str())?;
                rfs::chownat(
                    &parent,
                    name,
                    Some(rustix::process::Uid::from_raw(e.source.uid)),
                    Some(rustix::process::Gid::from_raw(e.source.gid)),
                    AtFlags::SYMLINK_NOFOLLOW,
                )?;
            }
            Content::Directory => (),
        }
    }
    for e in devices {
        ensure(
            device_allowed(&e.path, e.major, e.minor),
            "unapproved complete static node",
        )?;
        let (parent, name) = output.parent(&e.path)?;
        rfs::mknodat(
            &parent,
            name.as_str(),
            FileType::CharacterDevice,
            Mode::from_raw_mode(e.source.mode & 0o7777),
            rfs::makedev(e.major, e.minor),
        )?;
        rfs::chownat(
            &parent,
            name.as_str(),
            Some(rustix::process::Uid::from_raw(e.source.uid)),
            Some(rustix::process::Gid::from_raw(e.source.gid)),
            AtFlags::SYMLINK_NOFOLLOW,
        )?;
        rfs::chmodat(
            &parent,
            name,
            Mode::from_raw_mode(e.source.mode & 0o7777),
            AtFlags::empty(),
        )?;
    }
    for e in directories.iter().rev() {
        fs::set_metadata(&output.directory(&e.path)?, &e.source, &e.xattrs)?;
    }
    rfs::fsync(&output.root)?;
    Ok(output)
}

#[cfg(test)]
mod complete_tests {
    use super::*;
    use std::os::unix::fs::symlink;

    fn fixture() -> (tempfile::TempDir, Snapshot) {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("var/lib/dpkg/info")).unwrap();
        std::fs::write(
            dir.path().join("var/lib/dpkg/status"),
            b"actual package status\n",
        )
        .unwrap();
        std::fs::write(
            dir.path().join("var/lib/dpkg/info/test.list"),
            b"/usr/bin/test\n",
        )
        .unwrap();
        let tree = Snapshot::test_open(dir.path()).unwrap();
        (dir, tree)
    }

    #[test]
    fn complete_tree_preserves_database_links_and_rejects_changed_payload() {
        let (dir, tree) = fixture();
        std::fs::hard_link(
            dir.path().join("var/lib/dpkg/status"),
            dir.path().join("var/lib/dpkg/status-alias"),
        )
        .unwrap();
        symlink("/var/lib/dpkg/status", dir.path().join("status-link")).unwrap();
        let (entries, devices) = capture(&tree).unwrap();
        assert!(
            entries
                .iter()
                .any(|e| e.path == "/var/lib/dpkg/info/test.list")
        );
        assert!(entries.iter().any(
            |e| matches!(&e.content,Content::Hardlink{target,..} if target=="/var/lib/dpkg/status")
        ));
        verify(&tree, &entries, &devices).unwrap();
        std::fs::write(
            dir.path().join("var/lib/dpkg/info/test.list"),
            b"replaced payload\n",
        )
        .unwrap();
        assert!(verify(&tree, &entries, &devices).is_err());
    }

    #[test]
    fn complete_tree_never_follows_guest_symlink_or_external_hardlink() {
        let (dir, tree) = fixture();
        symlink("var/lib/dpkg", dir.path().join("alias")).unwrap();
        assert!(tree.file("/alias/status").is_err());
        let outside = tempfile::tempdir().unwrap();
        std::fs::hard_link(
            dir.path().join("var/lib/dpkg/status"),
            outside.path().join("alias"),
        )
        .unwrap();
        assert!(capture(&tree).is_err());
    }

    #[test]
    fn complete_tree_rejects_live_socket_and_extra_member() {
        let (dir, tree) = fixture();
        let (entries, devices) = capture(&tree).unwrap();
        let _listener =
            std::os::unix::net::UnixListener::bind(dir.path().join("live.sock")).unwrap();
        assert!(capture(&tree).is_err());
        assert!(verify(&tree, &entries, &devices).is_err());
    }

    #[test]
    fn complete_link_lexical_boundary_does_not_open_host_paths() {
        assert_eq!(normalize_link("/lib", "usr/lib").unwrap(), "/usr/lib");
        assert_eq!(
            normalize_link("/dev/fd", "/proc/self/fd").unwrap(),
            "/proc/self/fd"
        );
        assert!(normalize_link("/etc/a", "../../host").is_err());
        assert!(normalize_link("/etc/a", "bad\0name").is_err());
    }
}
