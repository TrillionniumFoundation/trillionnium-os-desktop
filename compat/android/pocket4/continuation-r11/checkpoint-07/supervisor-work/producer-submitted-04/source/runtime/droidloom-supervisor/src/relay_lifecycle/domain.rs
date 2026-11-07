//! FD-relative finite cgroup-v2 envelope owned by one new generation.
//!
//! The outer envelope is never projected into Android. Only its "android"
//! child becomes the guest cgroup namespace root. Android cannot increase the
//! ancestor's aggregate limits even if its own root controls change.
use super::policy::{PressureRelaySpec, hex};
use std::ffi::{CStr, CString};
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Component, Path};
use serde::Serialize;

const CGROUP2_MAGIC: libc::c_long = 0x6367_7270;
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct Identity { pub device: u64, pub inode: u64 }
impl Identity {
    pub(crate) fn of(file: &File) -> io::Result<Self> {
        let m = file.metadata()?;
        Ok(Self { device: m.dev(), inode: m.ino() })
    }
}
pub(crate) fn error(message: &'static str) -> io::Error { io::Error::other(message) }
pub(crate) fn at(parent: RawFd, name: &CStr, flags: i32, mode: u32) -> io::Result<File> {
    // SAFETY: caller supplies a held parent and an owned NUL-terminated name.
    let raw = unsafe { libc::openat(parent, name.as_ptr(), flags | libc::O_NOFOLLOW | libc::O_CLOEXEC, mode) };
    if raw < 0 { Err(io::Error::last_os_error()) } else {
        // SAFETY: openat returned one fresh owned descriptor.
        Ok(unsafe { File::from_raw_fd(raw) })
    }
}
pub(crate) fn named(parent: &File, name: &str, flags: i32) -> io::Result<File> {
    let name = CString::new(name).map_err(|_| error("NUL in fixed relative capability path"))?;
    if name.as_bytes().contains(&b'/') { return Err(error("relative capability component contains slash")); }
    at(parent.as_raw_fd(), &name, flags, 0)
}
pub(crate) fn directory(path: &Path) -> io::Result<File> {
    if !path.is_absolute() { return Err(error("capability directory is not absolute")); }
    let mut file = OpenOptions::new().read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW).open("/")?;
    for component in path.components().skip(1) {
        let Component::Normal(name) = component else { return Err(error("capability path is not normalized")); };
        let name = CString::new(name.as_bytes()).map_err(|_| error("NUL in directory component"))?;
        file = at(file.as_raw_fd(), &name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
    }
    Ok(file)
}
pub(crate) fn beneath(root: &File, path: &str, flags: i32) -> io::Result<File> {
    let components: Vec<_> = Path::new(path).components().collect();
    if components.is_empty() || components.iter().any(|x| !matches!(x, Component::Normal(_))) {
        return Err(error("relative capability path is not normalized"));
    }
    let mut parent = root.try_clone()?;
    for (index, component) in components.iter().enumerate() {
        let Component::Normal(name) = component else { unreachable!() };
        let name = CString::new(name.as_bytes()).map_err(|_| error("NUL in relative component"))?;
        let current = if index + 1 == components.len() { flags } else { libc::O_RDONLY | libc::O_DIRECTORY };
        parent = at(parent.as_raw_fd(), &name, current, 0)?;
    }
    Ok(parent)
}
pub(crate) fn read(file: File, maximum: u64) -> io::Result<String> {
    let mut bytes = Vec::new();
    file.take(maximum + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > maximum { return Err(error("bounded capability read exceeded")); }
    String::from_utf8(bytes).map_err(|_| error("capability metadata is not UTF-8"))
}
pub(crate) fn read_name(parent: &File, name: &str) -> io::Result<String> {
    read(named(parent, name, libc::O_RDONLY)?, 16 * 1024)
}
fn write_name(parent: &File, name: &str, value: &str) -> io::Result<()> {
    named(parent, name, libc::O_WRONLY)?.write_all(value.as_bytes())
}
pub(crate) fn filesystem(file: &File, kind: libc::c_long) -> io::Result<()> {
    let mut value = std::mem::MaybeUninit::<libc::statfs>::uninit();
    // SAFETY: fstatfs initializes exactly the supplied statfs object.
    if unsafe { libc::fstatfs(file.as_raw_fd(), value.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: fstatfs succeeded.
    if unsafe { value.assume_init() }.f_type != kind { return Err(error("capability filesystem differs")); }
    Ok(())
}
fn root_directory(file: &File) -> io::Result<()> {
    let m = file.metadata()?;
    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
        return Err(error("cgroup parent type/owner/mode is unsafe"));
    }
    filesystem(file, CGROUP2_MAGIC)
}
fn exact_number(text: &str) -> io::Result<u64> {
    let value = text.strip_suffix('\n').ok_or_else(|| error("cgroup value lacks newline"))?;
    if value.is_empty() || value.bytes().any(|byte| !byte.is_ascii_digit()) {
        return Err(error("cgroup value is not a finite decimal"));
    }
    value.parse().map_err(|_| error("cgroup value overflows"))
}
fn limits(root: &File, policy: &PressureRelaySpec) -> io::Result<()> {
    for (name, expected) in [
        ("memory.max", policy.memory_max_bytes), ("memory.high", policy.memory_high_bytes),
        ("memory.swap.max", policy.memory_swap_max_bytes), ("pids.max", u64::from(policy.tasks_max)),
    ] {
        if exact_number(&read_name(root, name)?)? != expected { return Err(error("immutable generation budget differs")); }
    }
    if read_name(root, "cpu.max")? != format!("{} {}\n", policy.cpu_quota_us, policy.cpu_period_us) {
        return Err(error("immutable CPU budget differs"));
    }
    Ok(())
}
fn set_limits(root: &File, policy: &PressureRelaySpec) -> io::Result<()> {
    empty(root)?;
    for (name, value) in [
        ("memory.max", format!("{}\n", policy.memory_max_bytes)),
        ("memory.high", format!("{}\n", policy.memory_high_bytes)),
        ("memory.swap.max", format!("{}\n", policy.memory_swap_max_bytes)),
        ("cpu.max", format!("{} {}\n", policy.cpu_quota_us, policy.cpu_period_us)),
        ("pids.max", format!("{}\n", policy.tasks_max)),
    ] {
        write_name(root, name, &value)?;
    }
    limits(root, policy)?;
    empty(root)
}
pub(crate) fn empty(root: &File) -> io::Result<()> {
    if exact_number(&read_name(root, "pids.current")?)? != 0 {
        return Err(error("generation aggregate still has live tasks"));
    }
    empty_descendant(root)
}
fn empty_descendant(root: &File) -> io::Result<()> {
    // pids.current can be absent in a child where Android did not activate
    // that controller. The private outer/Android roots are checked with
    // aggregate pids.current=0 before this walk. cgroup.events is recursive.
    if !read_name(root, "cgroup.procs")?.trim().is_empty() {
        return Err(error("generation still has live tasks"));
    }
    let events = read_name(root, "cgroup.events")?;
    let mut populated = events.lines().filter_map(|line| line.strip_prefix("populated "));
    if populated.next() != Some("0") || populated.next().is_some() {
        return Err(error("generation or an unknown descendant remains populated"));
    }
    Ok(())
}
fn child(parent: &File, name: &CStr) -> io::Result<File> {
    // SAFETY: held parent and new fixed/nonce component; EEXIST is never reused.
    if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let result = at(parent.as_raw_fd(), name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
    root_directory(&result)?;
    if read_name(&result, "cgroup.type")? != "domain\n" { return Err(error("new cgroup is not a domain")); }
    Ok(result)
}

pub(crate) struct Domain {
    parent: File,
    outer: File,
    android: File,
    name: CString,
    outer_id: Identity,
    android_id: Identity,
    policy: PressureRelaySpec,
    removed: bool,
    failed_retirement: bool,
}
impl Domain {
    /// Requires an already persisted generation claim and an explicitly
    /// delegated parent. Only newly created descendants are ever configured.
    pub(crate) fn create(policy: &PressureRelaySpec, nonce: &[u8; 32]) -> io::Result<Self> {
        if unsafe { libc::geteuid() } != 0 || nonce == &[0; 32] {
            return Err(error("finite domain requires root and a fresh nonzero nonce"));
        }
        let parent = directory(&policy.cgroup_parent)?;
        root_directory(&parent)?;
        if !read_name(&parent, "cgroup.procs")?.trim().is_empty() {
            return Err(error("delegated parent has internal processes"));
        }
        let enabled = read_name(&parent, "cgroup.subtree_control")?;
        if ["memory", "cpu", "pids"].iter().any(|name| !enabled.split_whitespace().any(|word| word == *name)) {
            return Err(error("required controllers were not delegated by the host"));
        }
        let name = CString::new(format!("g-{}", hex(nonce))).expect("hex name");
        let outer = child(&parent, &name)?;
        set_limits(&outer, policy)?;
        // The host-created outer envelope is still empty. Its private
        // subtree is the only place this code enables controllers.
        write_name(&outer, "cgroup.subtree_control", "+memory +cpu +pids\n")?;
        let android = child(&outer, c"android")?;
        set_limits(&android, policy)?;
        let outer_id = Identity::of(&outer)?;
        let android_id = Identity::of(&android)?;
        Ok(Self { parent, outer, android, name, outer_id, android_id, policy: policy.clone(),
            removed: false, failed_retirement: false })
    }
    pub(crate) fn android(&self) -> &File { &self.android }
    pub(crate) fn identity(&self) -> Identity { self.android_id }
    pub(crate) fn validate(&self) -> io::Result<()> {
        if self.removed || self.failed_retirement { return Err(error("generation domain is retired or poisoned")); }
        let outer = at(self.parent.as_raw_fd(), &self.name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        let android = named(&outer, "android", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if Identity::of(&outer)? != self.outer_id || Identity::of(&android)? != self.android_id
            || Identity::of(&self.outer)? != self.outer_id || Identity::of(&self.android)? != self.android_id {
            return Err(error("generation cgroup identity was replaced"));
        }
        limits(&self.outer, &self.policy)?;
        limits(&self.android, &self.policy)
    }
    pub(crate) fn prove_empty(&self) -> io::Result<()> {
        self.validate()?; empty(&self.android)?; empty(&self.outer)
    }
    /// Caller first proves joined broker and exact owner/init death. A failed
    /// traversal is sticky; it never removes the generation marker.
    pub(crate) fn remove_after(&mut self, proof: impl FnOnce() -> io::Result<()>) -> io::Result<()> {
        if self.failed_retirement { return Err(error("domain retirement is poisoned")); }
        if self.removed { return Ok(()); }
        let result = (|| {
            proof()?; self.prove_empty()?;
            let mut visited = 0;
            remove_empty_children(&self.android, self.android_id.device, 0, &mut visited)?;
            empty(&self.android)?; empty(&self.outer)?;
            let named_android = named(&self.outer, "android", libc::O_RDONLY | libc::O_DIRECTORY)?;
            if Identity::of(&named_android)? != self.android_id { return Err(error("Android cgroup changed before removal")); }
            // SAFETY: held private outer and exact previously validated child.
            if unsafe { libc::unlinkat(self.outer.as_raw_fd(), c"android".as_ptr(), libc::AT_REMOVEDIR) } != 0 {
                return Err(io::Error::last_os_error());
            }
            empty(&self.outer)?;
            let named_outer = at(self.parent.as_raw_fd(), &self.name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
            if Identity::of(&named_outer)? != self.outer_id { return Err(error("outer cgroup changed before removal")); }
            // SAFETY: this exact generation is empty and all owned children are removed.
            if unsafe { libc::unlinkat(self.parent.as_raw_fd(), self.name.as_ptr(), libc::AT_REMOVEDIR) } != 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        })();
        if result.is_err() { self.failed_retirement = true; } else { self.removed = true; }
        result
    }
    pub(crate) fn prove_removed(&self) -> io::Result<()> {
        if !self.removed || self.failed_retirement { return Err(error("domain has no completed removal proof")); }
        match at(self.parent.as_raw_fd(), &self.name, libc::O_PATH, 0) {
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
            _ => Err(error("retired generation cgroup name reappeared")),
        }
    }
}
fn remove_empty_children(parent: &File, device: u64, depth: usize, visited: &mut usize) -> io::Result<()> {
    if depth >= 16 { return Err(error("cgroup cleanup depth exceeded")); }
    empty_descendant(parent)?;
    // The path addresses our already-held descriptor, not a discovered host
    // cgroup name. Each entry is reopened NOFOLLOW before any effect.
    for entry in std::fs::read_dir(format!("/proc/self/fd/{}", parent.as_raw_fd()))? {
        let entry = entry?;
        let name = CString::new(entry.file_name().as_bytes()).map_err(|_| error("invalid cgroup child name"))?;
        let file = at(parent.as_raw_fd(), &name, libc::O_PATH, 0)?;
        let metadata = file.metadata()?;
        if metadata.file_type().is_symlink() { return Err(error("symlink in private cgroup tree")); }
        if !metadata.is_dir() { continue; }
        *visited += 1;
        if *visited > 4096 || metadata.dev() != device { return Err(error("private cgroup traversal bound/filesystem differs")); }
        let directory = at(parent.as_raw_fd(), &name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        let identity = Identity::of(&directory)?;
        if identity != Identity::of(&file)? { return Err(error("private cgroup child changed")); }
        remove_empty_children(&directory, device, depth + 1, visited)?;
        empty_descendant(&directory)?;
        let named = at(parent.as_raw_fd(), &name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        if Identity::of(&named)? != identity { return Err(error("private cgroup replaced before removal")); }
        // SAFETY: relative exact held empty descendant; never crosses a mount/symlink.
        if unsafe { libc::unlinkat(parent.as_raw_fd(), name.as_ptr(), libc::AT_REMOVEDIR) } != 0 {
            return Err(io::Error::last_os_error());
        }
    }
    empty_descendant(parent)
}
/// Called only in the single-threaded private entry, before cgroup namespace
/// sealing or helper execution. "0" selects the caller, never a numeric peer.
pub(crate) fn enter_self(domain: &File, policy: &PressureRelaySpec) -> io::Result<()> {
    root_directory(domain)?;
    limits(domain, policy)?;
    write_name(domain, "cgroup.procs", "0\n")?;
    limits(domain, policy)
}
/// After CLONE_NEWCGROUP, expose only the current private domain. The outer
/// finite envelope is absent from this mount's namespace root.
pub(crate) fn mount_private_view(root: &Path, expected: Identity) -> io::Result<()> {
    let root = directory(root)?;
    let target = beneath(&root, "sys/fs/cgroup", libc::O_PATH | libc::O_DIRECTORY)?;
    let target_path = CString::new(format!("/proc/self/fd/{}", target.as_raw_fd())).expect("descriptor path");
    // SAFETY: owned target descriptor and static filesystem/options.
    if unsafe { libc::mount(c"none".as_ptr(), target_path.as_ptr(), c"cgroup2".as_ptr(),
        libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC, std::ptr::null()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let projected = beneath(&root, "sys/fs/cgroup", libc::O_RDONLY | libc::O_DIRECTORY)?;
    filesystem(&projected, CGROUP2_MAGIC)?;
    if Identity::of(&projected)? != expected { return Err(error("private cgroup mount is not the held Android domain")); }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn foreign_filesystem_is_rejected_without_creating_a_cgroup() {
        let temp = tempfile::tempdir().unwrap();
        let root = directory(temp.path()).unwrap();
        assert!(filesystem(&root, CGROUP2_MAGIC).is_err());
        assert_eq!(std::fs::read_dir(temp.path()).unwrap().count(), 0);
    }
    #[test]
    fn relative_capability_traversal_rejects_escape_and_symlink() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("value"), b"owned").unwrap();
        std::os::unix::fs::symlink("value", temp.path().join("link")).unwrap();
        let root = directory(temp.path()).unwrap();
        assert!(beneath(&root, "../value", libc::O_RDONLY).is_err());
        assert!(beneath(&root, "/value", libc::O_RDONLY).is_err());
        assert!(beneath(&root, "link", libc::O_RDONLY).is_err());
        assert_eq!(read(beneath(&root, "value", libc::O_RDONLY).unwrap(), 5).unwrap(), "owned");
    }
    #[test]
    fn finite_numbers_and_bounded_reads_reject_ambiguous_or_unlimited_input() {
        for value in ["max\n", " 1\n", "1", "+1\n", "1\n2\n", "18446744073709551616\n"] {
            assert!(exact_number(value).is_err(), "{value:?}");
        }
        assert_eq!(exact_number("0\n").unwrap(), 0);
        let temp = tempfile::tempfile().unwrap();
        (&temp).write_all(b"123456").unwrap();
        use std::io::{Seek, SeekFrom};
        (&temp).seek(SeekFrom::Start(0)).unwrap();
        assert!(read(temp, 5).is_err());
    }
}
