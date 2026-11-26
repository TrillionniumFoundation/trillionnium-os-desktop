//! Fixed original-machine ownership for a single qualification transaction.
//! This object proves live process, namespace and fixed-lock custody. It does
//! not admit a release, authorize data mutation, or grant permanent activation.
use crate::{Result, boot_files as files, ensure, fs, model::Identity};
use files::FilePin;
use rustix::fs::{AtFlags, FileType, FlockOperation, Mode, OFlags};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs::File,
    io::{Read, Seek},
    path::{Path, PathBuf},
};

pub(super) const ORIGINAL_KERNEL: &str = "7.0.14-p4cred1";
pub(super) const ROOT_UUID: &str = "01c27223-3933-481e-9836-7bd0ef1be8c9";
pub(super) const ORIGINAL_ENTRY: &str = "gnulinux-advanced-01c27223-3933-481e-9836-7bd0ef1be8c9>gnulinux-7.0.14-p4cred1-advanced-01c27223-3933-481e-9836-7bd0ef1be8c9";
const LOCK_PATHS: &[&str] = &[
    "/var/lib/droidloom-qualification/.p4-vm-controller-516eec.lock",
    "/etc/droidloom/setup.lock",
    "/var/lib/droidloom/identity-reservations/registry.lock",
    "/var/lib/droidloom/identity-reservations/u1000.lease",
];
const PROC_LIMIT: u64 = 16 * 1024 * 1024;

fn bounded(path: &Path, maximum: u64) -> Result<String> {
    let mut bytes = Vec::new();
    File::open(path)?
        .take(maximum + 1)
        .read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 <= maximum,
        "kernel observation exceeded bound",
    )?;
    Ok(String::from_utf8(bytes)?)
}

fn uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

fn same_directory(a: &Identity, b: &Identity) -> bool {
    (a.dev, a.ino, a.mode, a.uid, a.gid) == (b.dev, b.ino, b.mode, b.uid, b.gid)
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct OriginalObservation {
    boot_id: String,
    kernel: String,
    pid: u32,
    starttime: u64,
    namespaces: BTreeMap<String, String>,
    root: Identity,
    boot: Identity,
    root_mount_id: u64,
    root_device: String,
}

fn starttime(stat: &str) -> Result<(char, u64)> {
    let end = stat.rfind(')').ok_or("process stat has no closing comm")?;
    let fields: Vec<_> = stat[end + 1..].split_whitespace().collect();
    ensure(fields.len() >= 20, "process stat is truncated")?;
    let state = fields[0].chars().next().ok_or("missing process state")?;
    Ok((state, fields[19].parse()?))
}

fn original_observation() -> Result<OriginalObservation> {
    ensure(
        rustix::process::getuid().as_raw() == 0
            && rustix::process::geteuid().as_raw() == 0
            && rustix::process::getgid().as_raw() == 0
            && rustix::process::getegid().as_raw() == 0,
        "original qualification requires actual original root credentials",
    )?;
    let pid = std::process::id();
    ensure(pid > 1, "original qualification owner cannot be PID1")?;
    let kernel = bounded(Path::new("/proc/sys/kernel/osrelease"), 256)?
        .trim()
        .to_owned();
    ensure(
        kernel == ORIGINAL_KERNEL,
        "qualification preparation is not on the original kernel",
    )?;
    let boot_id = bounded(Path::new("/proc/sys/kernel/random/boot_id"), 80)?
        .trim()
        .to_owned();
    ensure(uuid(&boot_id), "actual kernel boot ID is invalid")?;
    let (_, starttime) = starttime(&bounded(Path::new("/proc/self/stat"), 8192)?)?;
    let mut namespaces = BTreeMap::new();
    for kind in ["user", "pid", "mnt", "net", "ipc", "uts"] {
        let own = std::fs::read_link(format!("/proc/self/ns/{kind}"))?;
        let initial = std::fs::read_link(format!("/proc/1/ns/{kind}"))?;
        ensure(
            own == initial,
            "qualification owner is outside an original PID1 namespace",
        )?;
        let value = own
            .into_os_string()
            .into_string()
            .map_err(|_| "non-UTF8 namespace identity")?;
        if kind == "user" {
            ensure(
                value == "user:[4026531837]",
                "initial user namespace required",
            )?;
        }
        namespaces.insert(kind.into(), value);
    }
    ensure(
        bounded(Path::new("/proc/self/uid_map"), 256)?
            .split_whitespace()
            .collect::<Vec<_>>()
            == ["0", "0", "4294967295"],
        "original full uid mapping required",
    )?;
    let tree = fs::Tree::open("/", 0)?;
    let root = fs::stat(&tree.root)?;
    let pid1_root = File::from(rustix::fs::open(
        "/proc/1/root",
        OFlags::PATH | OFlags::DIRECTORY | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    ensure(
        same_directory(&root, &fs::stat(&pid1_root)?),
        "qualification owner is chrooted",
    )?;
    ensure(
        rustix::fs::fstatfs(&tree.root)?.f_type as u64 == 0xef53,
        "original root is not ext4",
    )?;
    let boot = fs::stat(&tree.dir("/boot")?)?;
    ensure(
        boot.dev == root.dev,
        "original /boot is on a different filesystem",
    )?;
    let mountinfo = bounded(Path::new("/proc/self/mountinfo"), PROC_LIMIT)?;
    let mut roots = Vec::new();
    for line in mountinfo.lines() {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure(fields.len() >= 10, "invalid original mountinfo record")?;
        if fields[4] != "/" {
            continue;
        }
        let dash = fields
            .iter()
            .position(|v| *v == "-")
            .ok_or("mountinfo separator missing")?;
        ensure(
            fields[3] == "/"
                && fields.get(dash + 1) == Some(&"ext4")
                && fields[5].split(',').any(|x| x == "rw"),
            "original root mount contract differs",
        )?;
        roots.push((fields[0].parse::<u64>()?, fields[2].to_owned()));
    }
    ensure(roots.len() == 1, "ambiguous original root mount")?;
    let (root_mount_id, root_device) = roots.remove(0);
    ensure(
        root_device
            == format!(
                "{}:{}",
                rustix::fs::major(root.dev),
                rustix::fs::minor(root.dev)
            ),
        "root mount major/minor differs from held root",
    )?;
    let uuid_path = format!("/dev/disk/by-uuid/{ROOT_UUID}");
    let (link_id, target) = tree.read_link(&uuid_path)?;
    ensure(
        link_id.uid == 0 && link_id.gid == 0,
        "root UUID link is not root owned",
    )?;
    let leaf = target
        .strip_prefix("../../")
        .ok_or("unexpected root UUID alias")?;
    ensure(
        !leaf.is_empty()
            && leaf
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
        "unsafe root UUID device alias",
    )?;
    let device = File::from(rustix::fs::openat(
        &tree.dir("/dev")?,
        leaf,
        OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    let stat = rustix::fs::fstat(&device)?;
    ensure(
        FileType::from_raw_mode(stat.st_mode) == FileType::BlockDevice
            && stat.st_uid == 0
            && stat.st_rdev == root.dev,
        "actual original UUID device does not own this root",
    )?;
    Ok(OriginalObservation {
        boot_id,
        kernel,
        pid,
        starttime,
        namespaces,
        root,
        boot,
        root_mount_id,
        root_device,
    })
}

/// Pins a pre-existing lock. No create, chmod, truncate or inode replacement.
struct ExistingLock {
    parent: File,
    parent_identity: Identity,
    name: String,
    held: File,
    identity: Identity,
    path: PathBuf,
}

impl ExistingLock {
    fn acquire(path: &Path, owner: u32) -> Result<Self> {
        let tree = fs::Tree::open("/", 0)?;
        let absolute = fs::absolute_string(path)?;
        let (parent, name) = if owner == 0 {
            tree.parent(&absolute)?
        } else {
            fs::absolute_parent(&absolute)?
        };
        let parent_identity = fs::stat(&parent)?;
        ensure(
            parent_identity.uid == owner && parent_identity.mode & 0o022 == 0,
            "fixed lock parent custody differs",
        )?;
        let held = File::from(rustix::fs::openat(
            &parent,
            name.as_str(),
            OFlags::RDONLY | OFlags::NONBLOCK | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let identity = fs::stat(&held)?;
        ensure(
            FileType::from_raw_mode(identity.mode) == FileType::RegularFile
                && identity.uid == owner
                && identity.gid == rustix::process::getegid().as_raw()
                && identity.nlink == 1
                && identity.mode & 0o7022 == 0,
            "existing lock is not a protected ordinary inode",
        )?;
        rustix::fs::flock(&held, FlockOperation::NonBlockingLockExclusive)?;
        let result = Self {
            parent,
            parent_identity,
            name,
            held,
            identity,
            path: path.to_owned(),
        };
        result.revalidate()?;
        Ok(result)
    }

    fn revalidate(&self) -> Result<()> {
        if self.identity.uid == 0 {
            fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&self.path)?)?;
        }
        let (named_parent, leaf) = fs::absolute_parent(&fs::absolute_string(&self.path)?)?;
        let named = fs::identity(&rustix::fs::statat(
            &self.parent,
            self.name.as_str(),
            AtFlags::SYMLINK_NOFOLLOW,
        )?);
        ensure(
            leaf == self.name
                && same_directory(&fs::stat(&named_parent)?, &self.parent_identity)
                && same_directory(&fs::stat(&self.parent)?, &self.parent_identity)
                && named == self.identity
                && fs::stat(&self.held)? == self.identity,
            "fixed held lock or ancestor was replaced",
        )?;
        // This is the same private open file description; there is no exposed
        // descriptor or unlock API. Reassert the kernel lock at every fence.
        rustix::fs::flock(&self.held, FlockOperation::NonBlockingLockExclusive)?;
        Ok(())
    }
}

pub(super) struct OriginalOwner {
    observation: OriginalObservation,
    locks: Vec<ExistingLock>,
}

impl OriginalOwner {
    pub(super) fn acquire(expected_boot_id: &str) -> Result<Self> {
        ensure(
            uuid(expected_boot_id),
            "expected original boot ID is invalid",
        )?;
        let before = original_observation()?;
        ensure(
            before.boot_id == expected_boot_id,
            "original boot changed before qualification",
        )?;
        let locks = LOCK_PATHS
            .iter()
            .map(|p| ExistingLock::acquire(Path::new(p), 0))
            .collect::<Result<Vec<_>>>()?;
        let result = Self {
            observation: before,
            locks,
        };
        result.revalidate()?;
        Ok(result)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        for lock in &self.locks {
            lock.revalidate()?;
        }
        let current = original_observation()?;
        ensure(
            current.boot_id == self.observation.boot_id
                && current.kernel == self.observation.kernel
                && current.pid == self.observation.pid
                && current.starttime == self.observation.starttime
                && current.namespaces == self.observation.namespaces
                && current.root_mount_id == self.observation.root_mount_id
                && current.root_device == self.observation.root_device
                && same_directory(&current.root, &self.observation.root)
                && same_directory(&current.boot, &self.observation.boot),
            "original qualification owner changed",
        )?;
        Ok(())
    }

    pub(super) fn boot_id(&self) -> &str {
        &self.observation.boot_id
    }

    pub(super) fn evidence(&self) -> serde_json::Value {
        serde_json::json!({"actual_original":self.observation,"original_entry":ORIGINAL_ENTRY,
            "root_uuid":ROOT_UUID,"locks":self.locks.iter().map(|l|
                serde_json::json!({"path":l.path,"identity":l.identity})).collect::<Vec<_>>()})
    }
}

/// Immutable evidence is kept open; both the name and same original inode are
/// checked with complete bytes on each mutation fence, including after reboot.
pub(super) struct SealedInput {
    pin: FilePin,
    held: File,
    identity: Identity,
}

impl SealedInput {
    pub(super) fn open(pin: &FilePin) -> Result<Self> {
        Self::open_owned(pin, 0)
    }

    fn open_owned(pin: &FilePin, owner: u32) -> Result<Self> {
        ensure(
            pin.bytes > 0 && pin.bytes <= 128 * 1024 * 1024,
            "once evidence size out of bounds",
        )?;
        if owner == 0 {
            fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&pin.path)?)?;
        }
        let (held, identity) = files::open_pin(pin)?;
        ensure(
            identity.uid == owner
                && identity.gid == rustix::process::getegid().as_raw()
                && identity.nlink == 1
                && identity.mode & 0o7777 == 0o400,
            "once immutable evidence must be root-owned mode 0400",
        )?;
        let result = Self {
            pin: pin.clone(),
            held,
            identity,
        };
        result.revalidate()?;
        Ok(result)
    }

    pub(super) fn pin(&self) -> &FilePin {
        &self.pin
    }

    pub(super) fn read(&self) -> Result<Vec<u8>> {
        self.revalidate()?;
        let bytes = files::read_pin(&self.pin, self.pin.bytes)?;
        self.revalidate()?;
        Ok(bytes)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        if self.identity.uid == 0 {
            fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&self.pin.path)?)?;
        }
        ensure(
            fs::stat(&self.held)? == self.identity
                && files::open_pin(&self.pin)?.1 == self.identity,
            "once held or named immutable evidence was replaced",
        )?;
        let mut file = &self.held;
        file.rewind()?;
        ensure(
            fs::hash(file)? == self.pin.sha256 && fs::stat(&self.held)? == self.identity,
            "once immutable evidence bytes changed",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn existing_lock_preserves_0644_inode_and_excludes_independent_description() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("setup.lock");
        files::write_new(&path, b"", 0o644)?;
        let before = std::fs::metadata(&path)?;
        use std::os::unix::fs::MetadataExt;
        let lock = ExistingLock::acquire(&path, rustix::process::geteuid().as_raw())?;
        assert!(ExistingLock::acquire(&path, rustix::process::geteuid().as_raw()).is_err());
        lock.revalidate()?;
        let after = std::fs::metadata(&path)?;
        assert_eq!(
            (
                before.ino(),
                before.mode(),
                before.ctime(),
                before.ctime_nsec()
            ),
            (after.ino(), after.mode(), after.ctime(), after.ctime_nsec())
        );
        std::fs::rename(&path, tmp.path().join("original.lock"))?;
        files::write_new(&path, b"", 0o644)?;
        assert!(lock.revalidate().is_err());
        Ok(())
    }

    #[test]
    fn immutable_intent_rejects_same_bytes_on_a_replaced_inode_and_in_place_write() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("INTENT.json");
        files::write_new(&path, b"{\"fixed\":true}\n", 0o400)?;
        let pin = files::pin_file(&path)?;
        let sealed = SealedInput::open_owned(&pin, rustix::process::geteuid().as_raw())?;
        assert_eq!(sealed.read()?, b"{\"fixed\":true}\n");
        std::fs::rename(&path, tmp.path().join("original"))?;
        files::write_new(&path, b"{\"fixed\":true}\n", 0o400)?;
        assert!(sealed.revalidate().is_err());
        let newer = SealedInput::open_owned(&pin, rustix::process::geteuid().as_raw())?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        std::fs::write(&path, b"{\"fixed\":null}\n")?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400))?;
        assert!(newer.revalidate().is_err());
        Ok(())
    }

    #[test]
    fn original_stat_parser_does_not_split_a_process_name_with_spaces_or_parentheses() -> Result<()>
    {
        let mut fields = vec!["S"; 20];
        fields[19] = "123456";
        let input = format!("134 (a name ) with ( nested) {}", fields.join(" "));
        assert_eq!(starttime(&input)?, ('S', 123456));
        assert!(starttime("134 (short) S 2").is_err());
        Ok(())
    }
}
