//! Fixed original-machine ownership for a single qualification transaction.
//! This object proves live process, namespace and fixed-lock custody. It does
//! not admit a release, authorize data mutation, or grant permanent activation.
use crate::{Result, boot_files as files, ensure, fs, model::Identity};
use files::FilePin;
#[path = "cold_working_owner.rs"]
mod working;
use rustix::fs::{AtFlags, FileType, FlockOperation, Mode, OFlags};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs::File,
    io::{Read, Seek},
    path::{Path, PathBuf},
};
pub(super) use working::WorkingColdOwner;

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

fn complete_hash(mut file: &File) -> Result<String> {
    file.rewind()?;
    fs::hash(file)
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
    control_group: String,
    invocation_id: String,
    capabilities: BTreeMap<String, u64>,
}

fn same_observation(a: &OriginalObservation, b: &OriginalObservation) -> bool {
    a.boot_id == b.boot_id
        && a.kernel == b.kernel
        && a.pid == b.pid
        && a.starttime == b.starttime
        && a.namespaces == b.namespaces
        && a.root_mount_id == b.root_mount_id
        && a.root_device == b.root_device
        && a.control_group == b.control_group
        && a.invocation_id == b.invocation_id
        && a.capabilities == b.capabilities
        && same_directory(&a.root, &b.root)
        && same_directory(&a.boot, &b.boot)
}

fn starttime(stat: &str) -> Result<(char, u64)> {
    let end = stat.rfind(')').ok_or("process stat has no closing comm")?;
    let fields: Vec<_> = stat[end + 1..].split_whitespace().collect();
    ensure(fields.len() >= 20, "process stat is truncated")?;
    let state = fields[0].chars().next().ok_or("missing process state")?;
    Ok((state, fields[19].parse()?))
}

fn owner_capabilities(status: &str) -> Result<BTreeMap<String, u64>> {
    let mut values = BTreeMap::new();
    for line in status.lines() {
        let Some((key, text)) = line.split_once(':') else {
            continue;
        };
        if ![
            "CapEff",
            "CapPrm",
            "CapBnd",
            "CapInh",
            "CapAmb",
            "NoNewPrivs",
        ]
        .contains(&key)
        {
            continue;
        }
        let text = text.trim();
        let value = if key == "NoNewPrivs" {
            ensure(matches!(text, "0" | "1"), "invalid owner no-new-privileges")?;
            text.parse()?
        } else {
            ensure(
                text.len() == 16 && text.bytes().all(|b| b.is_ascii_hexdigit()),
                "invalid original owner capability observation",
            )?;
            u64::from_str_radix(text, 16)?
        };
        ensure(
            values.insert(key.into(), value).is_none(),
            "duplicate owner credential observation",
        )?;
    }
    ensure(values.len() == 6, "incomplete original owner capabilities")?;
    // These are required by the actual original-root metadata and generation-
    // handle operations. They are observed existing capabilities, never raised.
    const REQUIRED: u64 = (1 << 2) | (1 << 21) | (1 << 33);
    ensure(
        ["CapEff", "CapPrm", "CapBnd"]
            .iter()
            .all(|key| values[*key] & REQUIRED == REQUIRED)
            && values["CapInh"] == 0
            && values["CapAmb"] == 0
            && values["NoNewPrivs"] == 0,
        "original owner lacks its existing metadata capabilities or has inherited credentials",
    )?;
    Ok(values)
}

fn original_owner_unit(cgroup: &str, invocation: &str) -> Result<String> {
    let path = cgroup
        .strip_prefix("0::")
        .and_then(|s| s.strip_suffix('\n'))
        .ok_or("original owner is not in one cgroup-v2 unit")?;
    let candidate = path
        .strip_prefix("/system.slice/droidloom-original-qualification@")
        .and_then(|s| s.strip_suffix(".service"))
        .ok_or("original qualification is not owned by its independent system unit")?;
    ensure(
        fs::valid_digest(candidate)
            && invocation.len() == 32
            && invocation
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "original owner unit identity differs",
    )?;
    Ok(path.into())
}

fn original_observation() -> Result<OriginalObservation> {
    original_observation_for(false)
}

fn original_observation_for(thaw_guard: bool) -> Result<OriginalObservation> {
    original_observation_for_thaw_prefix(
        thaw_guard.then_some("/system.slice/droidloom-original-thaw@"),
    )
}

// Plain host observation shared by the two distinct thaw-only units. Neither
// path creates qualification authority or opens a mutation owner's locks.
fn original_observation_for_thaw_prefix(thaw_prefix: Option<&str>) -> Result<OriginalObservation> {
    ensure(
        rustix::process::getuid().as_raw() == 0
            && rustix::process::geteuid().as_raw() == 0
            && rustix::process::getgid().as_raw() == 0
            && rustix::process::getegid().as_raw() == 0,
        "original qualification requires actual original root credentials",
    )?;
    let capabilities = owner_capabilities(&bounded(Path::new("/proc/self/status"), 64 * 1024)?)?;
    let invocation_id = std::env::var("INVOCATION_ID")?;
    let observed_cgroup = bounded(Path::new("/proc/self/cgroup"), 4096)?;
    let control_group = if let Some(thaw_prefix) = thaw_prefix {
        let translated = observed_cgroup.replacen(
            thaw_prefix,
            "/system.slice/droidloom-original-qualification@",
            1,
        );
        ensure(
            translated != observed_cgroup,
            "thaw guard is not its independent system unit",
        )?;
        original_owner_unit(&translated, &invocation_id)?;
        observed_cgroup
            .strip_prefix("0::")
            .and_then(|s| s.strip_suffix('\n'))
            .ok_or("thaw cgroup")?
            .to_owned()
    } else {
        original_owner_unit(&observed_cgroup, &invocation_id)?
    };
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
        control_group,
        invocation_id,
        capabilities,
    })
}

/// The independent thaw process receives no transaction authority or data
/// adapter. This verifies the same original host, but its own fixed unit.
pub(super) fn verify_thaw_owner(candidate: &str, boot: &str) -> Result<serde_json::Value> {
    ensure(
        fs::valid_digest(candidate) && uuid(boot),
        "thaw identity fields",
    )?;
    let actual = original_observation_for(true)?;
    ensure(
        actual.boot_id == boot
            && actual.control_group
                == format!("/system.slice/droidloom-original-thaw@{candidate}.service"),
        "thaw owner boot/unit differs",
    )?;
    Ok(serde_json::to_value(actual)?)
}

pub(super) fn verify_working_thaw_owner(candidate: &str, boot: &str) -> Result<serde_json::Value> {
    ensure(fs::valid_digest(candidate) && uuid(boot), "working thaw identity fields")?;
    let actual = original_observation_for_thaw_prefix(
        Some("/system.slice/droidloom-working-thaw@"),
    )?;
    ensure(
        actual.boot_id == boot
            && actual.control_group == format!("/system.slice/droidloom-working-thaw@{candidate}.service"),
        "working thaw owner boot/unit differs",
    )?;
    Ok(serde_json::to_value(actual)?)
}

/// Pins a pre-existing lock. No create, chmod, truncate or inode replacement.
struct ExistingLock {
    parent: File,
    parent_identity: Identity,
    name: String,
    held: File,
    identity: Identity,
    sha256: String,
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
                && identity.size <= 1024 * 1024
                && identity.mode & 0o7022 == 0,
            "existing lock is not a protected ordinary inode",
        )?;
        rustix::fs::flock(&held, FlockOperation::NonBlockingLockExclusive)?;
        let sha256 = complete_hash(&held)?;
        ensure(
            fs::stat(&held)? == identity,
            "fixed lock changed while pinning complete contents",
        )?;
        let result = Self {
            parent,
            parent_identity,
            name,
            held,
            identity,
            sha256,
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
        ensure(
            complete_hash(&self.held)? == self.sha256 && fs::stat(&self.held)? == self.identity,
            "fixed lock contents changed",
        )?;
        Ok(())
    }

    fn accept_label_identity(&mut self, before: &Identity, after: &Identity) -> Result<()> {
        let mut comparable = after.clone();
        comparable.ctime_sec = before.ctime_sec;
        comparable.ctime_nsec = before.ctime_nsec;
        ensure(
            (self.identity == *before || self.identity == *after) && comparable == *before,
            "lock label derivation changes more than the observed ctime",
        )?;
        let (parent, leaf) = fs::absolute_parent(&fs::absolute_string(&self.path)?)?;
        ensure(
            leaf == self.name
                && same_directory(&fs::stat(&parent)?, &self.parent_identity)
                && same_directory(&fs::stat(&self.parent)?, &self.parent_identity)
                && fs::stat(&self.held)? == *after
                && fs::identity(&rustix::fs::statat(
                    &parent,
                    leaf.as_str(),
                    AtFlags::SYMLINK_NOFOLLOW,
                )?) == *after
                && complete_hash(&self.held)? == self.sha256,
            "labelled fixed lock was replaced or its contents changed",
        )?;
        rustix::fs::flock(&self.held, FlockOperation::NonBlockingLockExclusive)?;
        self.identity = after.clone();
        self.revalidate()
    }
}

pub(super) struct OriginalOwner {
    observation: OriginalObservation,
    locks: Vec<ExistingLock>,
}

impl OriginalOwner {
    pub(super) fn acquire(expected_boot_id: &str, candidate_id: &str) -> Result<Self> {
        ensure(
            uuid(expected_boot_id),
            "expected original boot ID is invalid",
        )?;
        let before = original_observation()?;
        ensure(
            before.boot_id == expected_boot_id
                && fs::valid_digest(candidate_id)
                && before.control_group
                    == format!(
                        "/system.slice/droidloom-original-qualification@{candidate_id}.service"
                    ),
            "original boot or independently owned qualification unit differs",
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
            same_observation(&current, &self.observation),
            "original qualification owner changed",
        )?;
        Ok(())
    }

    // Only the parent qualification module can reach this identity helper.
    // It first revalidates the opaque actual SELinux/xattr/generation derivation.
    pub(super) fn accept_lock_label(
        &mut self,
        path: &Path,
        before: &Identity,
        after: &Identity,
    ) -> Result<bool> {
        let index = self.locks.iter().position(|l| l.path == path);
        let Some(index) = index else {
            self.revalidate()?;
            return Ok(false);
        };
        ensure(
            index != 0,
            "the excluded VM-controller lock is never relabelled",
        )?;
        for (i, lock) in self.locks.iter().enumerate() {
            if i != index {
                lock.revalidate()?;
            }
        }
        let current = original_observation()?;
        ensure(
            same_observation(&current, &self.observation),
            "original label owner observation changed",
        )?;
        self.locks[index].accept_label_identity(before, after)?;
        self.revalidate()?;
        Ok(true)
    }

    pub(super) fn label_sensitive_paths(&self) -> std::collections::BTreeSet<PathBuf> {
        self.locks.iter().skip(1).map(|v| v.path.clone()).collect()
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

    /// Used only inside a separately held, bounded label window. Full bytes
    /// are verified when entering/leaving that window; every step still binds
    /// the same open/named inode and every metadata/xattr field.
    pub(super) fn revalidate_custody(&self) -> Result<()> {
        if self.identity.uid == 0 {
            fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&self.pin.path)?)?;
        }
        let (named, identity) = files::open_pin(&self.pin)?;
        ensure(
            fs::stat(&self.held)? == self.identity
                && identity == self.identity
                && fs::xattrs(&self.held)?.is_empty()
                && fs::xattrs(&named)?.is_empty()
                && fs::stat(&self.held)? == self.identity
                && fs::stat(&named)? == self.identity,
            "once held or named immutable evidence or its attributes changed",
        )
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.revalidate_custody()?;
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
    fn lock_rebind_retains_original_flock_contents_and_every_nonctime_field() -> Result<()> {
        let tmp = tempfile::tempdir()?;
        let path = tmp.path().join("setup.lock");
        files::write_new(&path, b"original-lock", 0o644)?;
        let mut lock = ExistingLock::acquire(&path, rustix::process::geteuid().as_raw())?;
        let before = fs::stat(&lock.held)?;
        rustix::fs::fsetxattr(
            &lock.held,
            "user.original-once-test",
            b"label-test",
            rustix::fs::XattrFlags::CREATE,
        )?;
        let after = fs::stat(&lock.held)?;
        assert!(lock.revalidate().is_err());
        lock.accept_label_identity(&before, &after)?;
        lock.accept_label_identity(&before, &after)?; // exact already-rebound replay
        assert!(ExistingLock::acquire(&path, rustix::process::geteuid().as_raw()).is_err());
        assert_eq!(std::fs::read(&path)?, b"original-lock");
        std::fs::write(&path, b"unrelated-new-contents")?;
        let changed = fs::stat(&lock.held)?;
        assert!(lock.accept_label_identity(&after, &changed).is_err());
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
    fn original_owner_requires_its_own_system_unit_and_observed_metadata_capabilities() -> Result<()>
    {
        let cg = format!(
            "0::/system.slice/droidloom-original-qualification@{}.service\n",
            "a".repeat(64)
        );
        assert!(original_owner_unit(&cg, &"b".repeat(32)).is_ok());
        for other in [
            cg.replace("/system.slice/", "/user.slice/"),
            cg.replace("droidloom-original-qualification@", "hepta-runtime@"),
            cg.clone() + "1:name=systemd:/\n",
            cg.replace(&"a".repeat(64), "short"),
        ] {
            assert!(original_owner_unit(&other, &"b".repeat(32)).is_err());
        }
        assert!(original_owner_unit(&cg, "").is_err());
        let status = "CapEff:\t000001ffffffffff\nCapPrm:\t000001ffffffffff\nCapBnd:\t000001ffffffffff\nCapInh:\t0000000000000000\nCapAmb:\t0000000000000000\nNoNewPrivs:\t0\n";
        assert_eq!(owner_capabilities(status)?["CapEff"], 0x1ffffffffff);
        for changed in [
            status.replace("CapEff:\t000001ffffffffff", "CapEff:\t000001ffffdffffb"),
            status.replace("CapInh:\t0000000000000000", "CapInh:\t0000000800000000"),
            status.replace("NoNewPrivs:\t0", "NoNewPrivs:\t1"),
            status.to_owned() + "CapEff:\t000001ffffffffff\n",
            status.replace("CapBnd:\t000001ffffffffff\n", ""),
        ] {
            assert!(owner_capabilities(&changed).is_err());
        }
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
