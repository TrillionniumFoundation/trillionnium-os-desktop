//! The one nested invocation created by the authenticated working owner.
//!
//! Only the normal private command factory can register a group or a child.
//! The public owner merely checks this retained lease; a pathname, PID list or
//! saved observation cannot grant an exception to its empty-cgroup boundary.
use super::{
    OwnedCgroup, bounded_text, current_cgroup_parent, invalid, open_at, open_pidfd, pidfd_exited,
    process_identity,
};
use std::cell::RefCell;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, OwnedFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, Weak};
use std::time::Instant;

pub(super) const NAME: &str = "owned-probe";
const GROUP_LABEL: &[u8] = b"u:object_r:p4_linux_working_probe_t:s0";
const PROCS_LABEL: &[u8] = b"u:object_r:p4_linux_working_probe_membership_t:s0";
const EVENTS_LABEL: &[u8] = b"u:object_r:p4_linux_working_probe_events_t:s0";
const KILL_LABEL: &[u8] = b"u:object_r:p4_linux_working_probe_kill_t:s0";

thread_local! {
    // A weak reference cannot outlive the actual admitted owner or child.
    static CURRENT: RefCell<Option<Weak<ScopeCore>>> = const { RefCell::new(None) };
}

fn identity(file: &File) -> io::Result<[u64; 5]> {
    let m = file.metadata()?;
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
    ])
}
fn directory(path: &Path) -> io::Result<File> {
    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
}
fn no_subdirectories(path: &Path) -> io::Result<()> {
    for entry in fs::read_dir(path)? {
        if entry?.file_type()?.is_dir() {
            return Err(invalid("owned probe has an unretired nested cgroup"));
        }
    }
    Ok(())
}

struct ScopeCore {
    pid: u32,
    path: PathBuf,
    parent: File,
    pin: [u64; 5],
    end: Instant,
    active: Mutex<Option<Arc<InvocationLease>>>,
    documents: AtomicBool,
    poisoned: AtomicBool,
}
impl ScopeCore {
    fn guard(&self) -> io::Result<()> {
        if self.pid != std::process::id()
            || Instant::now() >= self.end
            || self.poisoned.load(Ordering::Acquire)
            || current_cgroup_parent()? != self.path
            || identity(&self.parent)? != self.pin
            || identity(&directory(&self.path)?)? != self.pin
        {
            return Err(invalid("working probe lost its actual admitted parent"));
        }
        super::physical_qualification_channel::require_working_actor()
    }
}

/// Retained only inside the actual parent or authenticated private child.
pub(super) struct Scope {
    core: Arc<ScopeCore>,
}
impl Scope {
    fn install(path: &Path, parent: &File, end: Instant) -> io::Result<Self> {
        super::physical_qualification_channel::require_working_actor()?;
        let expected = PathBuf::from(format!(
            "/sys/fs/cgroup/system.slice/{}",
            super::physical_qualification_channel::unit_name()
        ));
        if path != expected || current_cgroup_parent()? != expected {
            return Err(invalid("working probe scope requires the actual singleton"));
        }
        let core = Arc::new(ScopeCore {
            pid: std::process::id(),
            path: path.into(),
            parent: parent.try_clone()?,
            pin: identity(parent)?,
            end,
            active: Mutex::new(None),
            documents: AtomicBool::new(false),
            poisoned: AtomicBool::new(false),
        });
        core.guard()?;
        CURRENT.with(|slot| -> io::Result<()> {
            let mut value = slot
                .try_borrow_mut()
                .map_err(|_| invalid("working probe admission reentered"))?;
            if value.as_ref().and_then(Weak::upgrade).is_some() {
                return Err(invalid("working probe already has a live admitted owner"));
            }
            *value = Some(Arc::downgrade(&core));
            Ok(())
        })?;
        Ok(Self { core })
    }
    pub(super) fn parent(
        owner: &super::application_leaf_unit::qualification::UnitOwner,
        end: Instant,
    ) -> io::Result<Self> {
        let (path, parent) = owner.probe_parent(end).map_err(|e| invalid(&e))?;
        Self::install(path, parent, end)
    }
    pub(super) fn child(
        peer: &super::application_leaf_unit::qualification::ChildPeer,
        end: Instant,
    ) -> io::Result<Self> {
        peer.guard()?;
        let path = current_cgroup_parent()?;
        let parent = directory(&path)?;
        Self::install(&path, &parent, end)
    }
    pub(super) fn idle(&self) -> io::Result<()> {
        self.core.guard()?;
        if self
            .core
            .active
            .lock()
            .map_err(|_| invalid("working probe lease poisoned"))?
            .is_some()
        {
            return Err(invalid("working probe retirement has not completed"));
        }
        no_subdirectories(&self.core.path)
    }
    pub(super) fn begin_documents(&self) -> io::Result<()> {
        self.idle()?;
        if self.core.documents.swap(true, Ordering::AcqRel) {
            return Err(invalid("Documents resource scope already active"));
        }
        Ok(())
    }
    pub(super) fn finish_documents(&self) -> io::Result<()> {
        self.idle()?;
        if !self.core.documents.swap(false, Ordering::AcqRel) {
            return Err(invalid("Documents resource scope absent"));
        }
        Ok(())
    }
    pub(super) fn poison(&self) {
        self.core.poisoned.store(true, Ordering::Release);
    }
}

/// Factory-only token for the still-uncreated fixed invocation group.
pub(super) struct FactoryScope {
    core: Arc<ScopeCore>,
}
impl FactoryScope {
    pub(super) fn path(&self) -> PathBuf {
        self.core.path.join(NAME)
    }
    pub(super) fn documents(&self) -> bool {
        self.core.documents.load(Ordering::Acquire)
    }
    pub(super) fn register(self, group: &OwnedCgroup) -> io::Result<Lease> {
        self.core.guard()?;
        if group.path != self.path() {
            return Err(invalid("working factory created another cgroup"));
        }
        let files = [
            group.directory.try_clone()?,
            group.procs.try_clone()?,
            group.events.try_clone()?,
            group.kill.try_clone()?,
        ];
        let pins = files.iter().map(identity).collect::<io::Result<Vec<_>>>()?;
        let entry = Arc::new(InvocationLease {
            path: group.path.clone(),
            files,
            pins,
            child: Mutex::new(None),
        });
        entry.guard_group()?;
        let mut active = self
            .core
            .active
            .lock()
            .map_err(|_| invalid("working probe lease poisoned"))?;
        if active.is_some() {
            return Err(invalid("another working probe still owns its group"));
        }
        *active = Some(entry.clone());
        drop(active);
        Ok(Lease {
            core: self.core,
            entry,
        })
    }
}

pub(super) fn factory() -> io::Result<Option<FactoryScope>> {
    let core = CURRENT.with(|slot| {
        slot.try_borrow()
            .map_err(|_| invalid("working probe admission reentered"))
            .map(|value| value.as_ref().and_then(Weak::upgrade))
    })?;
    let Some(core) = core else { return Ok(None) };
    core.guard()?;
    if core
        .active
        .lock()
        .map_err(|_| invalid("working probe lease poisoned"))?
        .is_some()
    {
        return Err(invalid("previous working probe has not been retired"));
    }
    no_subdirectories(&core.path)?;
    Ok(Some(FactoryScope { core }))
}

struct SpawnedChild {
    directory: File,
    identity: super::ProcessIdentity,
    pidfd: OwnedFd,
}
struct InvocationLease {
    path: PathBuf,
    files: [File; 4],
    pins: Vec<[u64; 5]>,
    child: Mutex<Option<SpawnedChild>>,
}
impl InvocationLease {
    fn guard_group(&self) -> io::Result<()> {
        let labels = [GROUP_LABEL, PROCS_LABEL, EVENTS_LABEL, KILL_LABEL];
        let names = [
            None,
            Some(c"cgroup.procs"),
            Some(c"cgroup.events"),
            Some(c"cgroup.kill"),
        ];
        for (i, (file, label)) in self.files.iter().zip(labels).enumerate() {
            let named = match names[i] {
                None => directory(&self.path)?,
                Some(name) => open_at(
                    self.files[0].as_raw_fd(),
                    name,
                    if i == 1 || i == 3 {
                        libc::O_WRONLY | libc::O_NOFOLLOW
                    } else {
                        libc::O_RDONLY | libc::O_NOFOLLOW
                    },
                )?,
            };
            if identity(file)? != self.pins[i]
                || identity(&named)? != self.pins[i]
                || crate::native_hardware_label::label(file)? != label
                || crate::native_hardware_label::label(&named)? != label
            {
                return Err(invalid(
                    "working probe held cgroup or exact control was replaced",
                ));
            }
        }
        no_subdirectories(&self.path)
    }
    fn guard_live(&self) -> io::Result<()> {
        self.guard_group()?;
        let child = self
            .child
            .lock()
            .map_err(|_| invalid("working probe child lease poisoned"))?;
        let child = child
            .as_ref()
            .ok_or_else(|| invalid("working probe has no factory-spawned child"))?;
        if pidfd_exited(&child.pidfd)? || process_identity(&child.directory)? != child.identity {
            return Err(invalid("working probe factory child exited or changed"));
        }
        let membership = bounded_text(
            open_at(child.directory.as_raw_fd(), c"cgroup", libc::O_RDONLY)?,
            8192,
        )?;
        let relative = self
            .path
            .strip_prefix("/sys/fs/cgroup")
            .map_err(|_| invalid("working probe prefix"))?;
        if membership.trim() != format!("0::{}", relative.display()) {
            return Err(invalid("working probe child left its owned cgroup"));
        }
        Ok(())
    }
}

/// Retained by the private OwnedCgroup, including its unresolved-retirement slot.
pub(super) struct Lease {
    core: Arc<ScopeCore>,
    entry: Arc<InvocationLease>,
}
impl Lease {
    pub(super) fn bind_spawned(&self, child: &std::process::Child) -> io::Result<()> {
        // This PID comes directly from Command::spawn while its Child is still
        // unreaped. Even an immediate exit cannot recycle this process number.
        let pid = child.id();
        let dir = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(format!("/proc/{pid}"))?;
        let identity = process_identity(&dir)?;
        if identity.pid != pid {
            return Err(invalid("spawned working child proc identity differs"));
        }
        let pidfd = open_pidfd(pid)?;
        let mut slot = self
            .entry
            .child
            .lock()
            .map_err(|_| invalid("working probe child lease poisoned"))?;
        if slot.is_some() {
            return Err(invalid("working probe child already bound"));
        }
        *slot = Some(SpawnedChild {
            directory: dir,
            identity,
            pidfd,
        });
        self.entry.guard_group()
    }
    pub(super) fn guard_group(&self) -> io::Result<()> {
        self.entry.guard_group()
    }
    pub(super) fn retired(&self) -> io::Result<()> {
        // Called only after actual child reaping, populated=0 and exact rmdir.
        if self.entry.path.try_exists()? {
            return Err(invalid("working probe still has a named group"));
        }
        let mut active = self
            .core
            .active
            .lock()
            .map_err(|_| invalid("working probe lease poisoned"))?;
        if !active
            .as_ref()
            .is_some_and(|actual| Arc::ptr_eq(actual, &self.entry))
        {
            return Err(invalid(
                "working probe retirement does not own the active lease",
            ));
        }
        *active = None;
        Ok(())
    }
}

pub(super) fn verify_preparation_children(path: &Path, parent: &File) -> io::Result<()> {
    let mut nested = Vec::new();
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            nested.push(entry.path());
        }
    }
    if nested.is_empty() {
        return Ok(());
    }
    let core = CURRENT
        .with(|slot| {
            slot.try_borrow()
                .map_err(|_| invalid("working probe admission reentered"))
                .map(|v| v.as_ref().and_then(Weak::upgrade))
        })?
        .ok_or_else(|| invalid("nested cgroup has no live working owner"))?;
    core.guard()?;
    if core.path != path || identity(parent)? != core.pin || nested != [path.join(NAME)] {
        return Err(invalid("working owner has an unregistered nested group"));
    }
    let active = core
        .active
        .lock()
        .map_err(|_| invalid("working probe lease poisoned"))?
        .clone()
        .ok_or_else(|| invalid("nested group has no private factory lease"))?;
    active.guard_live()
}

/// Parent-side local watch of the exact source-created suite probe. Unlike a
/// case boundary this does not assert retirement. It never admits another name,
/// a caller PID list or a new owner; every live process must actually descend
/// from the still-held private suite child. The suite's own invocation lease
/// and all strict empty-group case boundaries remain unchanged.
pub(super) fn verify_live_suite_children(
    path: &Path,
    parent: &File,
    suite: &super::BoundProcess,
) -> io::Result<()> {
    suite.validate()?;
    if current_cgroup_parent()? != path || identity(parent)? != identity(&directory(path)?)? {
        return Err(invalid("working suite pulse parent changed"));
    }
    let nested = fs::read_dir(path)?
        .map(|entry| {
            let entry = entry?;
            Ok(if entry.file_type()?.is_dir() {
                Some(entry.path())
            } else {
                None
            })
        })
        .collect::<io::Result<Vec<_>>>()?
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    if nested.is_empty() {
        return Ok(());
    }
    if nested != [path.join(NAME)] {
        return Err(invalid("working suite has a foreign nested group"));
    }
    let group_path = &nested[0];
    let group = directory(group_path)?;
    let pin = identity(&group)?;
    if crate::native_hardware_label::label(&group)? != GROUP_LABEL || pin[3..5] != [0, 0] {
        return Err(invalid(
            "working suite probe has another kernel label/owner",
        ));
    }
    no_subdirectories(group_path)?;
    let procs = open_at(
        group.as_raw_fd(),
        c"cgroup.procs",
        libc::O_RDONLY | libc::O_NOFOLLOW,
    )?;
    if crate::native_hardware_label::label(&procs)? != PROCS_LABEL {
        return Err(invalid("working suite probe membership label changed"));
    }
    let pids = bounded_text(procs, 8192)?
        .lines()
        .map(|s| {
            s.parse::<u32>()
                .map_err(|_| invalid("working suite probe PID is not canonical"))
        })
        .collect::<io::Result<Vec<_>>>()?;
    if pids.len() > 64 {
        return Err(invalid(
            "working suite probe exceeds the actual fixed process bound",
        ));
    }
    let mut held = Vec::new();
    for pid in pids {
        let process = super::BoundProcess::capture(pid)?;
        let membership = bounded_text(process.open("cgroup", false)?, 8192)?;
        let relative = group_path
            .strip_prefix("/sys/fs/cgroup")
            .map_err(|_| invalid("working suite group prefix"))?;
        if membership.trim() != format!("0::{}", relative.display()) {
            return Err(invalid("working suite probe process changed group"));
        }
        let mut ancestor = process;
        let mut chain = Vec::new();
        for _ in 0..64 {
            let stat = bounded_text(ancestor.open("stat", false)?, 4096)?;
            let (_, fields) = stat
                .rsplit_once(") ")
                .ok_or_else(|| invalid("working suite ancestry stat malformed"))?;
            let parent_pid = fields
                .split_ascii_whitespace()
                .nth(1)
                .ok_or_else(|| invalid("working suite ancestry parent absent"))?
                .parse::<u32>()
                .map_err(|_| invalid("working suite ancestry parent invalid"))?;
            ancestor.validate()?;
            chain.push(ancestor);
            if parent_pid == suite.identity.pid {
                suite.validate()?;
                break;
            }
            if parent_pid <= 1
                || chain.iter().any(|p| p.identity.pid == parent_pid)
                || chain.len() == 64
            {
                return Err(invalid(
                    "working probe is not descended from the actual private suite",
                ));
            }
            ancestor = super::BoundProcess::capture(parent_pid)?;
        }
        for process in &chain {
            process.validate()?;
        }
        held.extend(chain);
    }
    no_subdirectories(group_path)?;
    if identity(&group)? != pin
        || identity(&directory(group_path)?)? != pin
        || crate::native_hardware_label::label(&group)? != GROUP_LABEL
    {
        return Err(invalid(
            "working suite probe changed during local observation",
        ));
    }
    for process in &held {
        process.validate()?;
    }
    suite.validate()
}
