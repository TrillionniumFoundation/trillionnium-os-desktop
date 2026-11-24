use crate::model::{Content, Identity};
use crate::paths;
use crate::{Result, ensure};
use rustix::fs::{self, AtFlags, FileType, Mode, OFlags, Stat, XattrFlags};
use rustix::process::{Gid, Uid};
use serde::de::DeserializeOwned;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;

const XATTRS: [&str; 3] = [
    "security.capability",
    "system.posix_acl_access",
    "system.posix_acl_default",
];

pub fn identity(s: &Stat) -> Identity {
    Identity {
        dev: s.st_dev,
        ino: s.st_ino,
        mode: s.st_mode,
        uid: s.st_uid,
        gid: s.st_gid,
        nlink: s.st_nlink,
        size: s.st_size as u64,
        mtime_sec: s.st_mtime,
        mtime_nsec: s.st_mtime_nsec as i64,
        ctime_sec: s.st_ctime,
        ctime_nsec: s.st_ctime_nsec as i64,
    }
}

pub fn stat(file: &File) -> Result<Identity> {
    Ok(identity(&fs::fstat(file)?))
}
pub fn digest(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}
pub fn valid_digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn check_owner(s: &Identity, owner: u32, symlink: bool) -> Result<()> {
    ensure(
        s.uid == owner,
        "source or directory is not owned by the trusted uid",
    )?;
    if !symlink {
        ensure(
            s.mode & 0o022 == 0,
            "source or directory is writable by group/other",
        )?;
    }
    Ok(())
}

fn root_fd() -> Result<File> {
    Ok(File::from(fs::open(
        "/",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
        Mode::empty(),
    )?))
}

/// Every component is resolved relative to a pinned directory descriptor.
fn descend(root: &File, names: &[&str], owner: Option<u32>) -> Result<File> {
    let mut current = root.try_clone()?;
    for name in names {
        current = File::from(fs::openat(
            &current,
            *name,
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
            Mode::empty(),
        )?);
        if let Some(uid) = owner {
            check_owner(&stat(&current)?, uid, false)?;
        }
    }
    Ok(current)
}

pub fn absolute_parent(path: &str) -> Result<(File, String)> {
    let names = paths::parts(path)?;
    Ok((
        descend(&root_fd()?, &names[..names.len() - 1], None)?,
        names[names.len() - 1].to_owned(),
    ))
}

pub struct Tree {
    pub root: File,
    pub owner: u32,
}

impl Tree {
    pub fn open(path: &str, owner: u32) -> Result<Self> {
        let root = if path == "/" {
            root_fd()?
        } else {
            descend(&root_fd()?, &paths::parts(path)?, None)?
        };
        check_owner(&stat(&root)?, owner, false)?;
        Ok(Self { root, owner })
    }

    pub fn create(path: &str, owner: u32) -> Result<Self> {
        let (parent, name) = absolute_parent(path)?;
        let parent_identity = stat(&parent)?;
        check_owner(&parent_identity, owner, false)?;
        ensure(
            parent_identity.mode & 0o077 == 0,
            "destination parent must be a private trusted directory",
        )?;
        fs::mkdirat(&parent, name.as_str(), Mode::from_raw_mode(0o700))?;
        let root = File::from(fs::openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::CLOEXEC | OFlags::NOFOLLOW,
            Mode::empty(),
        )?);
        ensure(
            stat(&root)?.mode & 0o777 == 0o700,
            "new fixture root is not private",
        )?;
        Ok(Self { root, owner })
    }

    pub fn parent(&self, path: &str) -> Result<(File, String)> {
        let names = paths::parts(path)?;
        Ok((
            descend(&self.root, &names[..names.len() - 1], Some(self.owner))?,
            names[names.len() - 1].to_owned(),
        ))
    }

    pub fn identity(&self, path: &str) -> Result<Identity> {
        let (parent, name) = self.parent(path)?;
        Ok(identity(&fs::statat(
            &parent,
            name.as_str(),
            AtFlags::SYMLINK_NOFOLLOW,
        )?))
    }

    pub fn dir(&self, path: &str) -> Result<File> {
        let names = paths::parts(path)?;
        descend(&self.root, &names, Some(self.owner))
    }

    pub fn file(&self, path: &str) -> Result<File> {
        let (parent, name) = self.parent(path)?;
        let file = File::from(fs::openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK,
            Mode::empty(),
        )?);
        let s = fs::fstat(&file)?;
        ensure(
            FileType::from_raw_mode(s.st_mode) == FileType::RegularFile,
            "input is not a regular file",
        )?;
        check_owner(&identity(&s), self.owner, false)?;
        Ok(file)
    }

    pub fn read_link(&self, path: &str) -> Result<(Identity, String)> {
        let (parent, name) = self.parent(path)?;
        let before = identity(&fs::statat(
            &parent,
            name.as_str(),
            AtFlags::SYMLINK_NOFOLLOW,
        )?);
        ensure(
            FileType::from_raw_mode(before.mode) == FileType::Symlink,
            "not a symlink",
        )?;
        check_owner(&before, self.owner, true)?;
        let link = fs::readlinkat(&parent, name.as_str(), Vec::new())?.into_string()?;
        let after = identity(&fs::statat(
            &parent,
            name.as_str(),
            AtFlags::SYMLINK_NOFOLLOW,
        )?);
        ensure(before == after, "symlink changed while read")?;
        Ok((before, link))
    }

    pub fn list(&self, path: &str) -> Result<Vec<String>> {
        let fd = self.dir(path)?;
        let before = stat(&fd)?;
        let mut result = Vec::new();
        let mut dir = fs::Dir::read_from(&fd)?;
        for entry in &mut dir {
            let entry = entry?;
            let name = entry.file_name().to_str()?;
            if name != "." && name != ".." {
                result.push(name.to_owned());
            }
        }
        ensure(stat(&fd)? == before, "directory changed while inventoried")?;
        result.sort();
        Ok(result)
    }

    pub fn mkdir(&self, path: &str) -> Result<()> {
        let (parent, name) = self.parent(path)?;
        fs::mkdirat(&parent, name.as_str(), Mode::from_raw_mode(0o700))?;
        Ok(())
    }

    pub fn create_file(&self, path: &str) -> Result<File> {
        let (parent, name) = self.parent(path)?;
        Ok(File::from(fs::openat(
            &parent,
            name.as_str(),
            OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::from_raw_mode(0o600),
        )?))
    }

    pub fn symlink(&self, path: &str, target: &str, source: &Identity) -> Result<()> {
        let (parent, name) = self.parent(path)?;
        fs::symlinkat(target, &parent, name.as_str())?;
        fs::chownat(
            &parent,
            name.as_str(),
            Some(Uid::from_raw(source.uid)),
            Some(Gid::from_raw(source.gid)),
            AtFlags::SYMLINK_NOFOLLOW,
        )?;
        Ok(())
    }

    pub fn hardlink(&self, path: &str, target: &str) -> Result<()> {
        let (from, old) = self.parent(target)?;
        let (to, new) = self.parent(path)?;
        fs::linkat(&from, old.as_str(), &to, new.as_str(), AtFlags::empty())?;
        Ok(())
    }
}

pub fn xattrs(file: &File) -> Result<BTreeMap<String, String>> {
    let mut result = BTreeMap::new();
    for name in XATTRS {
        let mut buf = vec![0u8; 65_536];
        match fs::fgetxattr(file, name, buf.as_mut_slice()) {
            Ok(n) => {
                result.insert(name.to_owned(), hex::encode(&buf[..n]));
            }
            Err(e) if e == rustix::io::Errno::NODATA || e == rustix::io::Errno::OPNOTSUPP => (),
            Err(e) => return Err(e.into()),
        }
    }
    Ok(result)
}

pub fn set_metadata(
    file: &File,
    source: &Identity,
    attrs: &BTreeMap<String, String>,
) -> Result<()> {
    fs::fchown(
        file,
        Some(Uid::from_raw(source.uid)),
        Some(Gid::from_raw(source.gid)),
    )?;
    fs::fchmod(file, Mode::from_raw_mode(source.mode & 0o7777))?;
    for (name, value) in attrs {
        ensure(
            XATTRS.contains(&name.as_str()),
            "unknown extended attribute in manifest",
        )?;
        fs::fsetxattr(
            file,
            name.as_str(),
            &hex::decode(value)?,
            XattrFlags::empty(),
        )?;
    }
    fs::fsync(file)?;
    Ok(())
}

pub fn hash(mut file: &File) -> Result<String> {
    let mut sha = Sha256::new();
    let mut buf = vec![0u8; 1024 * 1024];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        sha.update(&buf[..n]);
    }
    Ok(hex::encode(sha.finalize()))
}

pub fn read_regular(
    tree: &Tree,
    path: &str,
) -> Result<(Identity, String, BTreeMap<String, String>)> {
    let file = tree.file(path)?;
    let before = stat(&file)?;
    let attrs = xattrs(&file)?;
    let sha = hash(&file)?;
    ensure(
        stat(&file)? == before && tree.identity(path)? == before,
        &format!("source changed while hashed: {path}"),
    )?;
    Ok((before, sha, attrs))
}

pub fn copy_regular(
    source: &Tree,
    dest: &Tree,
    path: &str,
    expected: &Identity,
    expected_sha: &str,
    attrs: &BTreeMap<String, String>,
) -> Result<()> {
    let mut input = source.file(path)?;
    ensure(
        stat(&input)? == *expected,
        &format!("source identity changed before copy: {path}"),
    )?;
    ensure(
        xattrs(&input)? == *attrs,
        "source privilege attributes changed",
    )?;
    let mut output = dest.create_file(path)?;
    let mut sha = Sha256::new();
    let mut buf = vec![0u8; 1024 * 1024];
    let mut copied = 0u64;
    loop {
        let n = input.read(&mut buf)?;
        if n == 0 {
            break;
        }
        ensure(
            copied
                .checked_add(n as u64)
                .is_some_and(|next| next <= expected.size),
            "source grew beyond the reviewed size",
        )?;
        output.write_all(&buf[..n])?;
        sha.update(&buf[..n]);
        copied += n as u64;
    }
    ensure(
        copied == expected.size && hex::encode(sha.finalize()) == expected_sha,
        &format!("source content changed during copy: {path}"),
    )?;
    ensure(
        stat(&input)? == *expected && source.identity(path)? == *expected,
        "source identity changed during copy",
    )?;
    set_metadata(&output, expected, attrs)?;
    Ok(())
}

pub fn same_metadata(actual: &Identity, expected: &Identity) -> bool {
    actual.mode == expected.mode && actual.uid == expected.uid && actual.gid == expected.gid
}

pub fn read_json<T: DeserializeOwned>(path: &str, expected: &str) -> Result<T> {
    ensure(valid_digest(expected), "invalid expected SHA-256")?;
    let (parent, name) = absolute_parent(path)?;
    let mut file = File::from(fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDONLY | OFlags::CLOEXEC | OFlags::NOFOLLOW | OFlags::NONBLOCK,
        Mode::empty(),
    )?);
    let before = stat(&file)?;
    ensure(
        FileType::from_raw_mode(before.mode) == FileType::RegularFile
            && before.size <= 128 * 1024 * 1024,
        "JSON input must be a bounded regular file",
    )?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(128 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 == before.size && stat(&file)? == before,
        "JSON changed while read",
    )?;
    ensure(digest(&bytes) == expected, "JSON digest mismatch")?;
    Ok(serde_json::from_slice(&bytes)?)
}

pub fn write_json<T: serde::Serialize>(path: &str, value: &T, owner: u32) -> Result<String> {
    let (parent, name) = absolute_parent(path)?;
    let s = stat(&parent)?;
    check_owner(&s, owner, false)?;
    ensure(s.mode & 0o077 == 0, "artifact parent must be private")?;
    let bytes = serde_json::to_vec_pretty(value)?;
    let mut f = File::from(fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDWR | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::from_raw_mode(0o600),
    )?);
    f.write_all(&bytes)?;
    f.sync_all()?;
    let mut back = File::from(fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    let before = stat(&back)?;
    let mut readback = Vec::new();
    back.read_to_end(&mut readback)?;
    ensure(
        readback == bytes && stat(&back)? == before,
        "artifact full readback differs",
    )?;
    Ok(digest(&bytes))
}

pub fn content_type_matches(identity: &Identity, content: &Content) -> bool {
    let actual = FileType::from_raw_mode(identity.mode);
    match content {
        Content::Directory => actual == FileType::Directory,
        Content::Symlink { .. } => actual == FileType::Symlink,
        Content::Regular { .. } | Content::Hardlink { .. } => actual == FileType::RegularFile,
    }
}

pub fn assert_root_namespace(path: &str, tree: &Tree) -> Result<()> {
    let reopened = Tree::open(path, tree.owner)?;
    let a = stat(&reopened.root)?;
    let b = stat(&tree.root)?;
    ensure(
        a.dev == b.dev && a.ino == b.ino,
        "fixture root pathname was replaced",
    )
}

pub fn absolute_string(path: &Path) -> Result<String> {
    let s = path.to_str().ok_or("non-UTF8 input path")?.to_owned();
    if s != "/" {
        paths::parts(&s)?;
    }
    Ok(s)
}
