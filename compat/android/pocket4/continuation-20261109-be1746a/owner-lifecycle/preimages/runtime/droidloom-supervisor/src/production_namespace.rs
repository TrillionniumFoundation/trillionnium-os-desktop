//! Owned user-namespace construction primitive for the future production broker.
//!
//! A bare identity reservation remains rejected. The admitted entry accepts
//! only an opaque HostAdmission holding complete fresh NSS/provider and live
//! namespace observations. No JSON, PID or numeric map grants authority.
//!
//! The private constructor owns a clone3-created child from birth, with an
//! atomic pidfd, held proc directory, start time, userns FD and nonce-bound
//! ready/go protocol. It never accepts an external PID. The fixed child only
//! creates a user namespace, changes to its mapped credentials and parks;
//! it cannot exec Android, mount data or publish a runtime. A private next
//! stage can create a fixed PID-1 namespace tree but remains unqualified until
//! its own normal and privileged controls pass. Idmapped data, runtime mounts,
//! seccomp and daemon wiring are still separate work.

use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::marker::PhantomData;
use std::os::fd::{AsFd, AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::rc::Rc;
use std::time::{Duration, Instant};

use thiserror::Error;

use crate::IdRange;
use crate::production_host_admission::{HostAdmission, HostAdmissionError};
use crate::production_identity::{IdentityError, IdentityLease};

#[path = "production_namespace_child.rs"]
mod child;
#[path = "production_namespace_tree.rs"]
mod tree;
use child::{Packet, Phase};
pub(crate) use tree::RetiredTreeWitness;

const PROC_MAGIC: libc::c_long = 0x9fa0;
const NSFS_MAGIC: libc::c_long = 0x6e736673;
const NS_GET_PARENT: libc::c_ulong = 0xb702;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_OWNER_UID: libc::c_ulong = 0xb704;
const PROC_LIMIT: u64 = 65536;
const PROTOCOL_TIMEOUT: Duration = Duration::from_secs(3);
const RETIRE_TIMEOUT: Duration = Duration::from_secs(2);

/// A closed authority gate, rejected child identity, or failed kernel operation.
#[derive(Debug, Error)]
pub enum NamespaceError {
    /// Selected ID grants alone cannot authorize namespace creation.
    #[error(
        "an identity reservation is not complete host admission; no namespace or ID map was created"
    )]
    HostAdmissionRequired,
    /// The held reservation no longer matches its authoritative inputs.
    #[error(transparent)]
    Identity(#[from] IdentityError),
    /// Fresh complete host admission changed or rejected the operation.
    #[error(transparent)]
    Admission(#[from] HostAdmissionError),
    /// A verified mount resource failed preparation or explicit retirement.
    #[error("owned base mount operation failed: {0}")]
    MountResource(String),
    /// A private device resource failed preparation or explicit retirement.
    #[error("owned private device operation failed: {0}")]
    DeviceResource(String),
    /// A held child or its protocol does not satisfy the construction contract.
    #[error("owned namespace rejected: {0}")]
    Rejected(&'static str),
    /// A syscall failed; there is no PID-lookup or development-mode fallback.
    #[error(transparent)]
    Io(#[from] io::Error),
    /// Cleanup did not establish exit; the resources and lease were retained.
    #[error("owned child exit was not proven; its lease remains quarantined")]
    RetirementUnproven,
}

type Result<T> = std::result::Result<T, NamespaceError>;

/// Refuse a bare reservation; complete opaque host admission is required.
///
/// This deliberately does not call the private syscall constructor. The lease
/// is not a full-NSS or live-namespace capability. It is released on rejection,
/// while its durable reservation is retained.
///
/// # Errors
///
/// A stale lease is rejected; otherwise this returns
/// [NamespaceError::HostAdmissionRequired] before cloning or writing maps.
pub fn prepare_user_namespace(lease: IdentityLease) -> Result<MappedUserNamespace> {
    lease.revalidate_for_broker()?;
    Err(NamespaceError::HostAdmissionRequired)
}

/// Create only an owned, mapped, parked user namespace from live admission.
///
/// HostAdmission has no public field, deserializer or numeric-PID constructor.
/// Every ID-map write is surrounded by fresh live observation tied to the
/// actual child witness. This does not mount data, exec Android, or qualify a
/// production runtime.
///
/// # Errors
///
/// Changed NSS/provider inputs, live conflicts, failed kernel ownership or an
/// incomplete child lifecycle reject construction and retain unproven custody.
pub fn prepare_admitted_user_namespace(admission: HostAdmission) -> Result<MappedUserNamespace> {
    admission.revalidate()?;
    let mut owner = Owner::spawn_with_authority(
        HeldAuthority::Admitted(admission),
        child::Mode::UserNamespace,
    )?;
    owner.enter_userns()?;
    let (uids, gids) = owner.install_maps()?;
    owner.mapped_go(uids, gids)?;
    Ok(MappedUserNamespace { owner })
}

/// Held ownership of a mapped, parked user-namespace child, not an Android cell.
///
/// It has no public constructor, PID-based adoption, execution or namespace-FD
/// export. The identity lease remains held until pidfd-bound exit is proven.
/// The handle is intentionally neither Send nor Sync: Linux parent-death
/// notification belongs to the creating thread.
pub struct MappedUserNamespace {
    owner: Owner,
}

/// Evidence of actual owned-child exit, with no runtime qualification.
#[derive(Debug, Eq, PartialEq)]
pub struct ChildExit {
    /// PID reported by the creation syscall and the final pidfd wait.
    pub pid: u32,
    /// Normal exit status, or the signal number for a signal exit.
    pub status: i32,
    /// The kernel waitid CLD_* reason.
    pub reason: i32,
}

impl MappedUserNamespace {
    /// Stop this fixed child and reap it through its held pidfd.
    ///
    /// # Errors
    ///
    /// If exit cannot be proven within the bounded cleanup, the held resources
    /// and reservation lease remain quarantined until this process exits.
    pub fn retire(mut self) -> Result<ChildExit> {
        self.owner.retire()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ProcessIdentity {
    pid: u32,
    parent: u32,
    start_ticks: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Node {
    device: u64,
    inode: u64,
}

impl Node {
    fn of(file: &File) -> io::Result<Self> {
        let meta = file.metadata()?;
        Ok(Self {
            device: meta.dev(),
            inode: meta.ino(),
        })
    }
}

// The production enum has exactly one constructible variant. Private syscall
// controls exist only in the test binary, never in either installed executable.
enum HeldAuthority {
    Admitted(HostAdmission),
    #[cfg(test)]
    PrivateControl(IdentityLease),
    #[cfg(test)]
    UnreservedControl,
}

impl HeldAuthority {
    fn lease(&self) -> Option<&IdentityLease> {
        match self {
            Self::Admitted(value) => Some(value.lease()),
            #[cfg(test)]
            Self::PrivateControl(value) => Some(value),
            #[cfg(test)]
            Self::UnreservedControl => None,
        }
    }

    fn revalidate(&self) -> Result<()> {
        match self {
            Self::Admitted(value) => value.revalidate().map_err(Into::into),
            #[cfg(test)]
            Self::PrivateControl(value) => value.revalidate_for_broker().map_err(Into::into),
            #[cfg(test)]
            Self::UnreservedControl => Ok(()),
        }
    }

    fn revalidate_live(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        match self {
            Self::Admitted(value) => value.revalidate_live(witness).map_err(Into::into),
            // The fixed private fixture controls are explicitly not production
            // admission. This arm is absent from non-test compilation.
            #[cfg(test)]
            Self::PrivateControl(value) => {
                witness.revalidate()?;
                value.revalidate_for_broker().map_err(Into::into)
            }
            #[cfg(test)]
            Self::UnreservedControl => Err(NamespaceError::HostAdmissionRequired),
        }
    }
}

struct Resources {
    // Drop order is explicit in Owner::retire/Drop. No lease is released merely
    // because a signal was sent or a path disappeared.
    authority: HeldAuthority,
    pidfd: OwnedFd,
    control: OwnedFd,
    proc_root: File,
    proc_dir: Option<File>,
    parent_userns: Option<File>,
    userns: Option<File>,
    proc_node: Option<Node>,
    identity: Option<ProcessIdentity>,
    pid: u32,
    parent_pid: u32,
    creator_tid: libc::pid_t,
    nonce: [u8; 16],
    entered: bool,
}

struct Owner {
    resources: Option<Resources>,
    _same_thread: PhantomData<Rc<()>>,
}

/// A non-constructible borrow of one actually owned namespace child.
/// This is crate-private, non-serializable and neither Send nor Sync. Numeric
/// PIDs, saved namespace inodes or JSON cannot create it.
pub(crate) struct OwnedNamespaceWitness<'a> {
    owner: &'a Owner,
    // Only an actually bound TreeOwner can lend this. No integer, saved inode
    // or complete-map boolean can create the descendant authority.
    tree: Option<&'a tree::TreeChild>,
}

impl OwnedNamespaceWitness<'_> {
    pub(crate) fn pidfd(&self) -> std::os::fd::BorrowedFd<'_> {
        self.owner.resources.as_ref().unwrap().pidfd.as_fd()
    }
    pub(crate) fn proc_directory(&self) -> &File {
        self.owner
            .resources
            .as_ref()
            .unwrap()
            .proc_dir
            .as_ref()
            .unwrap()
    }
    pub(crate) fn user_namespace(&self) -> &File {
        self.owner
            .resources
            .as_ref()
            .unwrap()
            .userns
            .as_ref()
            .unwrap()
    }
    pub(crate) fn host_pid(&self) -> u32 {
        self.owner.resources.as_ref().unwrap().pid
    }
    pub(crate) fn start_ticks(&self) -> u64 {
        self.owner
            .resources
            .as_ref()
            .unwrap()
            .identity
            .unwrap()
            .start_ticks
    }
    /// Borrow only the identity lease already held by this actual owner.
    pub(crate) fn identity_lease(&self) -> Result<&IdentityLease> {
        self.revalidate()?;
        self.owner
            .held()?
            .authority
            .lease()
            .ok_or(NamespaceError::HostAdmissionRequired)
    }

    /// Revalidate full live admission with this same keeper/PID-tree witness.
    /// Kernel-only revalidate() remains separate to avoid policy recursion.
    pub(crate) fn revalidate_live_admission(&self) -> Result<()> {
        self.revalidate()?;
        self.owner.held()?.authority.revalidate_live(self)
    }

    /// Exact borrowed PID namespace of an attested owned PID 1, if present.
    /// This is never populated by the ordinary map-construction witness.
    pub(crate) fn descendant_pid_namespace(&self) -> Option<&File> {
        self.tree.map(tree::TreeChild::pid_namespace)
    }

    // Only kernel ownership is checked here; admission calls this method and
    // must not recursively invoke its own NSS/map-range policy from it.
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.owner.verify_kernel_owned()?;
        if let Some(tree) = self.tree {
            tree.verify()?;
        }
        Ok(())
    }
}

impl Owner {
    #[cfg(test)]
    fn spawn(lease: Option<IdentityLease>, mode: child::Mode) -> Result<Self> {
        let authority = match lease {
            Some(lease) => HeldAuthority::PrivateControl(lease),
            None => HeldAuthority::UnreservedControl,
        };
        Self::spawn_with_authority(authority, mode)
    }

    fn spawn_with_authority(authority: HeldAuthority, mode: child::Mode) -> Result<Self> {
        authority.revalidate()?;
        let proc_root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_DIRECTORY | libc::O_NOFOLLOW)
            .open("/proc")?;
        check_fs(proc_root.as_raw_fd(), PROC_MAGIC)?;
        let (pid, pidfd, control, parent_pid, creator_tid, nonce) = child::spawn(mode)?;
        let mut owner = Self {
            resources: Some(Resources {
                authority,
                pidfd,
                control,
                proc_root,
                proc_dir: None,
                parent_userns: None,
                userns: None,
                proc_node: None,
                identity: None,
                pid,
                parent_pid,
                creator_tid,
                nonce,
                entered: false,
            }),
            _same_thread: PhantomData,
        };
        // The child remains at its CREATED barrier. Binding is performed only
        // for the PID returned together with the atomic clone3 pidfd.
        owner.receive(Phase::Created, None, PROTOCOL_TIMEOUT)?;
        let r = owner.held_mut()?;
        let proc_dir = open_proc_at(
            &r.proc_root,
            &r.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = read_identity(&proc_dir, r.pid)?;
        if identity.parent != r.parent_pid {
            return Err(NamespaceError::Rejected("created child parent differs"));
        }
        r.proc_node = Some(Node::of(&proc_dir)?);
        r.identity = Some(identity);
        let self_dir = open_proc_at(
            &r.proc_root,
            &r.parent_pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let self_identity = read_identity(&self_dir, r.parent_pid)?;
        if self_identity.pid != r.parent_pid {
            return Err(NamespaceError::Rejected(
                "procfs does not identify this parent",
            ));
        }
        r.parent_userns = Some(open_userns(&self_dir)?);
        let initial_ns = open_userns(&proc_dir)?;
        if Node::of(&initial_ns)? != Node::of(r.parent_userns.as_ref().unwrap())? {
            return Err(NamespaceError::Rejected(
                "child began in a foreign user namespace",
            ));
        }
        r.proc_dir = Some(proc_dir);
        owner.verify_owned()?;
        Ok(owner)
    }

    fn held(&self) -> Result<&Resources> {
        let r = self
            .resources
            .as_ref()
            .ok_or(NamespaceError::Rejected("child is retired"))?;
        // SAFETY: read-only scalar syscall.
        if unsafe { libc::syscall(libc::SYS_gettid) } != libc::c_long::from(r.creator_tid) {
            return Err(NamespaceError::Rejected(
                "owner moved away from its creating thread",
            ));
        }
        Ok(r)
    }

    fn held_mut(&mut self) -> Result<&mut Resources> {
        self.held()?;
        Ok(self.resources.as_mut().unwrap())
    }

    fn verify_kernel_owned(&self) -> Result<()> {
        let r = self.held()?;
        if pidfd_exited(&r.pidfd)? {
            return Err(NamespaceError::Rejected("owned child exited"));
        }
        let dir = r
            .proc_dir
            .as_ref()
            .ok_or(NamespaceError::Rejected("proc directory is not bound"))?;
        if Some(Node::of(dir)?) != r.proc_node || Some(read_identity(dir, r.pid)?) != r.identity {
            return Err(NamespaceError::Rejected("held child identity changed"));
        }
        // Independently prove its current procfs name refers to the held inode.
        let named = open_proc_at(
            &r.proc_root,
            &r.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        if Node::of(&named)? != Node::of(dir)? {
            return Err(NamespaceError::Rejected("proc directory name was rebound"));
        }
        if let Some(ns) = &r.userns {
            let actual = open_userns(dir)?;
            if Node::of(ns)? != Node::of(&actual)? {
                return Err(NamespaceError::Rejected("child user namespace changed"));
            }
        }
        if r.entered {
            require_privileged_initial_parent(&r.proc_root, r.parent_userns.as_ref().unwrap())?;
        }
        Ok(())
    }

    fn verify_owned(&self) -> Result<()> {
        self.verify_kernel_owned()?;
        self.held()?.authority.revalidate()
    }

    fn verify_live_admission(&self) -> Result<()> {
        let witness = self.witness()?;
        self.held()?.authority.revalidate_live(&witness)
    }

    fn witness(&self) -> Result<OwnedNamespaceWitness<'_>> {
        self.verify_kernel_owned()?;
        let r = self.held()?;
        if !r.entered || r.userns.is_none() {
            return Err(NamespaceError::Rejected(
                "owned user namespace is not bound",
            ));
        }
        Ok(OwnedNamespaceWitness {
            owner: self,
            tree: None,
        })
    }

    fn send(&self, phase: Phase) -> Result<()> {
        let r = self.held()?;
        send_packet(
            r.control.as_raw_fd(),
            &Packet::new(r.nonce, phase, 0, r.parent_pid),
        )
    }

    fn receive(
        &self,
        phase: Phase,
        mapped_ids: Option<(u32, u32)>,
        timeout: Duration,
    ) -> Result<Packet> {
        let r = self.held()?;
        let deadline = Instant::now() + timeout;
        loop {
            let now = Instant::now();
            if now >= deadline {
                return Err(NamespaceError::Io(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "owned child protocol deadline",
                )));
            }
            let millis = (deadline - now).as_millis().min(100) as i32;
            let mut fds = [
                libc::pollfd {
                    fd: r.control.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: r.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            // SAFETY: two initialized pollfds are writable for this call.
            let result = unsafe { libc::poll(fds.as_mut_ptr(), 2, millis) };
            if result < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e.into());
            }
            if fds
                .iter()
                .any(|p| p.revents & (libc::POLLNVAL | libc::POLLERR) != 0)
            {
                return Err(NamespaceError::Rejected("protocol descriptor failed"));
            }
            if fds[0].revents & libc::POLLIN != 0 {
                let (packet, credentials) = receive_packet(r.control.as_raw_fd())?;
                if !packet.matches(r.nonce, r.pid)
                    || credentials.pid != i32::try_from(r.pid).unwrap()
                {
                    return Err(NamespaceError::Rejected(
                        "nonce, PID or packet identity differs",
                    ));
                }
                if let Some((uid, gid)) = mapped_ids {
                    if credentials.uid != uid || credentials.gid != gid {
                        return Err(NamespaceError::Rejected("mapped peer credentials differ"));
                    }
                }
                if packet.phase == Phase::Failed as u32 {
                    if packet.errno <= 0 {
                        return Err(NamespaceError::Rejected("child failure has no valid errno"));
                    }
                    return Err(NamespaceError::Io(io::Error::from_raw_os_error(
                        packet.errno,
                    )));
                }
                if packet.phase != phase as u32 || packet.errno != 0 {
                    return Err(NamespaceError::Rejected("unexpected protocol phase"));
                }
                return Ok(packet);
            }
            if fds[0].revents & libc::POLLHUP != 0
                || fds[1].revents & (libc::POLLIN | libc::POLLHUP) != 0
            {
                return Err(NamespaceError::Rejected(
                    "child exited before its expected protocol phase",
                ));
            }
        }
    }

    fn enter_userns(&mut self) -> Result<()> {
        self.verify_owned()?;
        let r = self.held()?;
        require_privileged_initial_parent(&r.proc_root, r.parent_userns.as_ref().unwrap())?;
        self.send(Phase::Enter)?;
        self.receive(Phase::Ready, None, PROTOCOL_TIMEOUT)?;
        self.verify_owned()?;
        let r = self.held_mut()?;
        let dir = r.proc_dir.as_ref().unwrap();
        let ns = open_userns(dir)?;
        let parent = r.parent_userns.as_ref().unwrap();
        if Node::of(&ns)? == Node::of(parent)? {
            return Err(NamespaceError::Rejected(
                "child did not create a new user namespace",
            ));
        }
        // SAFETY: NS_GET_PARENT returns a new FD for the held namespace's
        // actual kernel parent; no namespace name is supplied.
        let parent_fd = unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_PARENT, 0 as libc::c_ulong) };
        if parent_fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        // SAFETY: successful ioctl transferred this new FD.
        let actual_parent = unsafe { File::from_raw_fd(parent_fd) };
        check_fs(actual_parent.as_raw_fd(), NSFS_MAGIC)?;
        if Node::of(&actual_parent)? != Node::of(parent)? {
            return Err(NamespaceError::Rejected(
                "new user namespace has a foreign parent",
            ));
        }
        let mut namespace_owner: libc::uid_t = u32::MAX;
        // SAFETY: the kernel writes one uid_t to the supplied valid pointer.
        if unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_OWNER_UID, &mut namespace_owner) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        if namespace_owner != 0 {
            return Err(NamespaceError::Rejected(
                "user namespace creator is not the admitted root broker",
            ));
        }
        r.userns = Some(ns);
        r.entered = true;
        self.verify_empty_maps_and_groups()?;
        Ok(())
    }

    fn verify_empty_maps_and_groups(&self) -> Result<()> {
        self.verify_owned()?;
        let dir = self.held()?.proc_dir.as_ref().unwrap();
        if !read_proc(dir, "uid_map")?.is_empty() || !read_proc(dir, "gid_map")?.is_empty() {
            return Err(NamespaceError::Rejected(
                "new namespace map was already populated",
            ));
        }
        let status = read_proc(dir, "status")?;
        require_empty_groups(&status)?;
        let setgroups = read_proc(dir, "setgroups")?;
        if setgroups != b"allow\n" {
            return Err(NamespaceError::Rejected("unexpected setgroups state"));
        }
        Ok(())
    }

    fn install_maps(&self) -> Result<(IdRange, IdRange)> {
        self.verify_empty_maps_and_groups()?;
        let r = self.held()?;
        if !r.entered || r.userns.is_none() {
            return Err(NamespaceError::Rejected("new user namespace is not bound"));
        }
        let lease = r
            .authority
            .lease()
            .ok_or(NamespaceError::Rejected("identity lease is absent"))?;
        let (uids, gids) = lease.broker_ranges();
        // A real initial-userns CAP_SETUID/CAP_SETGID broker can write these
        // maps without the unprivileged "deny" exception. Android must retain
        // setgroups for its service and app supplementary groups.
        self.write_owned(
            "uid_map",
            format!("0 {} {}\n", uids.start, uids.count).as_bytes(),
        )?;
        let dir = self.held()?.proc_dir.as_ref().unwrap();
        verify_map(&read_proc(dir, "uid_map")?, uids)?;
        self.write_owned(
            "gid_map",
            format!("0 {} {}\n", gids.start, gids.count).as_bytes(),
        )?;
        verify_map(&read_proc(dir, "uid_map")?, uids)?;
        verify_map(&read_proc(dir, "gid_map")?, gids)?;
        if read_proc(dir, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected(
                "setgroups allow was lost after mapping",
            ));
        }
        self.verify_owned()?;
        Ok((uids, gids))
    }

    fn write_owned(&self, leaf: &str, bytes: &[u8]) -> Result<()> {
        if !matches!(leaf, "uid_map" | "gid_map") {
            return Err(NamespaceError::Rejected(
                "not an allowed ID-map construction leaf",
            ));
        }
        self.verify_owned()?;
        self.verify_live_admission()?;
        let r = self.held()?;
        if !r.entered || r.userns.is_none() || r.authority.lease().is_none() {
            return Err(NamespaceError::Rejected(
                "mapping requires a held lease and new namespace",
            ));
        }
        let lease = r.authority.lease().unwrap();
        let (uids, gids) = lease.broker_ranges();
        let expected = match leaf {
            "uid_map" => format!("0 {} {}\n", uids.start, uids.count),
            "gid_map" => format!("0 {} {}\n", gids.start, gids.count),
            _ => unreachable!(),
        };
        if bytes != expected.as_bytes() {
            return Err(NamespaceError::Rejected(
                "map write does not match the held identity lease",
            ));
        }
        let dir = r.proc_dir.as_ref().unwrap();
        let uid_before = read_proc(dir, "uid_map")?;
        let gid_before = read_proc(dir, "gid_map")?;
        if !gid_before.is_empty() {
            return Err(NamespaceError::Rejected("GID map was already written"));
        }
        if leaf == "gid_map" {
            verify_map(&uid_before, uids)?;
        } else if !uid_before.is_empty() {
            return Err(NamespaceError::Rejected("UID map was already written"));
        }
        if read_proc(dir, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected(
                "setgroups allow required before map write",
            ));
        }
        let mut file = open_proc_at(dir, leaf, libc::O_WRONLY)?;
        // Exactly one write, through the owned proc descriptor. No retry of a
        // partial map and no setgroups-file mutation are supported.
        if file.write(bytes)? != bytes.len() {
            return Err(NamespaceError::Rejected("short ID-map write"));
        }
        self.verify_owned()?;
        if read_proc(dir, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected(
                "setgroups allow changed during map write",
            ));
        }
        self.verify_live_admission()?;
        Ok(())
    }

    fn mapped_go(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        self.verify_owned()?;
        self.verify_live_admission()?;
        let dir = self.held()?.proc_dir.as_ref().unwrap();
        verify_map(&read_proc(dir, "uid_map")?, uids)?;
        verify_map(&read_proc(dir, "gid_map")?, gids)?;
        if read_proc(dir, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected("setgroups allow absent at GO"));
        }
        self.send(Phase::Go)?;
        self.receive(
            Phase::Mapped,
            Some((uids.start, gids.start)),
            PROTOCOL_TIMEOUT,
        )?;
        self.verify_owned()?;
        verify_map(&read_proc(dir, "uid_map")?, uids)?;
        verify_map(&read_proc(dir, "gid_map")?, gids)?;
        let status = read_proc(dir, "status")?;
        require_empty_groups(&status)?;
        require_ids(&status, "Uid:", uids.start)?;
        require_ids(&status, "Gid:", gids.start)?;
        if read_proc(dir, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected(
                "mapped child lost setgroups allow",
            ));
        }
        self.verify_live_admission()?;
        Ok(())
    }

    fn retire(&mut self) -> Result<ChildExit> {
        let r = self.held()?;
        let _ = send_packet(
            r.control.as_raw_fd(),
            &Packet::new(r.nonce, Phase::Stop, 0, r.parent_pid),
        );
        if !wait_exited(&r.pidfd, RETIRE_TIMEOUT)? {
            signal_owned(&r.pidfd, libc::SIGKILL)?;
            if !wait_exited(&r.pidfd, RETIRE_TIMEOUT)? {
                return Err(NamespaceError::RetirementUnproven);
            }
        }
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        // SAFETY: exact held pidfd and initialized writable siginfo; the exit
        // poll completed, and WNOHANG prevents blocking on unexpected state.
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                r.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        } != 0
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        // SAFETY: successful waitid filled the SIGCHLD variant.
        let (pid, status) = unsafe { (info.si_pid(), info.si_status()) };
        if pid != i32::try_from(r.pid).unwrap()
            || !matches!(
                info.si_code,
                libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
            )
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        let evidence = ChildExit {
            pid: r.pid,
            status,
            reason: info.si_code,
        };
        self.resources.take(); // Only after proven, reaped exit; record persists.
        Ok(evidence)
    }
}

impl Drop for Owner {
    fn drop(&mut self) {
        if self.resources.is_some() && self.retire().is_err() {
            if let Some(resources) = self.resources.take() {
                // Retain all FDs and the exclusive lease until process death
                // if lifecycle proof is unavailable. Never signal a PID lookup.
                std::mem::forget(resources);
            }
        }
    }
}

// Only the separately reviewed private fixture binary may use this constructor.
// The production build has no path from a bare lease to map-writing authority.
#[cfg(test)]
#[allow(dead_code)]
fn prepare_owned_user_namespace(lease: IdentityLease) -> Result<MappedUserNamespace> {
    // SAFETY: argument-free scalar credential queries.
    if unsafe { libc::geteuid() } != 0 || unsafe { libc::getuid() } != 0 {
        return Err(NamespaceError::Rejected(
            "real and effective root broker required",
        ));
    }
    lease.revalidate_for_broker()?;
    let mut owner = Owner::spawn(Some(lease), child::Mode::UserNamespace)?;
    owner.enter_userns()?;
    let (uids, gids) = owner.install_maps()?;
    owner.mapped_go(uids, gids)?;
    Ok(MappedUserNamespace { owner })
}

fn check_fs(fd: RawFd, magic: libc::c_long) -> Result<()> {
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    // SAFETY: stat is writable and fd is retained by the caller.
    if unsafe { libc::fstatfs(fd, &mut stat) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if stat.f_type != magic {
        return Err(NamespaceError::Rejected(
            "descriptor is not on the required kernel filesystem",
        ));
    }
    Ok(())
}

// Linux UAPI include/uapi/linux/nsfs.h exports both reserved initial-userns
// identifiers. This check does not infer "initial" from NS_GET_PARENT EPERM:
// that error can also mean an inaccessible parent of a nested user namespace.
// Source: https://github.com/torvalds/linux/blob/v7.0/include/uapi/linux/nsfs.h
const USER_NS_INIT_INO: u64 = 0xEFFF_FFFD;
const USER_NS_INIT_ID: u64 = 3;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;

fn require_initial_userns(namespace: &File) -> Result<()> {
    check_fs(namespace.as_raw_fd(), NSFS_MAGIC)?;
    if Node::of(namespace)?.inode != USER_NS_INIT_INO {
        return Err(NamespaceError::Rejected(
            "broker is not in the initial user namespace",
        ));
    }
    let mut id = 0_u64;
    // SAFETY: NS_GET_ID writes one u64 into this live output. Unsupported
    // kernels fail closed rather than treating an inaccessible parent as root.
    if unsafe { libc::ioctl(namespace.as_raw_fd(), NS_GET_ID, &mut id) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if id != USER_NS_INIT_ID {
        return Err(NamespaceError::Rejected(
            "kernel user namespace ID is not initial",
        ));
    }
    Ok(())
}

#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[derive(Clone, Copy, Default)]
#[repr(C)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}

fn require_privileged_initial_parent(proc_root: &File, held_namespace: &File) -> Result<()> {
    // SAFETY: read-only scalar credential queries.
    if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
        return Err(NamespaceError::Rejected(
            "real/effective root mapping broker required",
        ));
    }
    require_initial_userns(held_namespace)?;
    let pid = unsafe { libc::getpid() };
    let self_dir = open_proc_at(
        proc_root,
        &pid.to_string(),
        libc::O_RDONLY | libc::O_DIRECTORY,
    )?;
    let actual = open_userns(&self_dir)?;
    require_initial_userns(&actual)?;
    if Node::of(held_namespace)? != Node::of(&actual)? {
        return Err(NamespaceError::Rejected(
            "broker changed its user namespace",
        ));
    }
    verify_map(
        &read_proc(&self_dir, "uid_map")?,
        IdRange {
            start: 0,
            count: u32::MAX,
        },
    )?;
    verify_map(
        &read_proc(&self_dir, "gid_map")?,
        IdRange {
            start: 0,
            count: u32::MAX,
        },
    )?;
    let mut header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut data = [CapData::default(); 2];
    // SAFETY: Linux capability ABI v3 uses a header and exactly two data words,
    // querying this calling thread only. No capabilities are changed.
    if unsafe { libc::syscall(libc::SYS_capget, &mut header, data.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let needed = (1_u32 << 6) | (1_u32 << 7); // CAP_SETGID, CAP_SETUID
    if data[0].effective & needed != needed || data[0].permitted & needed != needed {
        return Err(NamespaceError::Rejected(
            "initial-userns CAP_SETUID/CAP_SETGID required",
        ));
    }
    Ok(())
}

fn open_proc_at(parent: &File, leaf: &str, flags: i32) -> Result<File> {
    if leaf.is_empty() || leaf.contains('/') || matches!(leaf, "." | "..") {
        return Err(NamespaceError::Rejected(
            "proc leaf is not a single component",
        ));
    }
    let name =
        std::ffi::CString::new(leaf).map_err(|_| NamespaceError::Rejected("NUL proc leaf"))?;
    // SAFETY: held proc directory, terminated single component, no symlinks.
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: new descriptor from successful openat.
    let file = unsafe { File::from_raw_fd(fd) };
    check_fs(file.as_raw_fd(), PROC_MAGIC)?;
    if flags & libc::O_DIRECTORY == 0 && !file.metadata()?.is_file() {
        return Err(NamespaceError::Rejected(
            "proc leaf is not a regular kernel file",
        ));
    }
    Ok(file)
}

fn open_userns(proc_dir: &File) -> Result<File> {
    let ns_dir = open_proc_at(proc_dir, "ns", libc::O_RDONLY | libc::O_DIRECTORY)?;
    // SAFETY: this one kernel magic link under the bound proc directory is
    // followed deliberately; the returned inode must be a user namespace.
    let fd = unsafe {
        libc::openat(
            ns_dir.as_raw_fd(),
            c"user".as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: newly acquired descriptor.
    let file = unsafe { File::from_raw_fd(fd) };
    check_fs(file.as_raw_fd(), NSFS_MAGIC)?;
    // SAFETY: scalar ioctl on the held namespace.
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) }
        != libc::CLONE_NEWUSER
    {
        return Err(NamespaceError::Rejected(
            "held namespace is not a user namespace",
        ));
    }
    Ok(file)
}

fn read_proc(dir: &File, leaf: &str) -> Result<Vec<u8>> {
    let file = open_proc_at(dir, leaf, libc::O_RDONLY)?;
    let mut value = Vec::new();
    file.take(PROC_LIMIT + 1).read_to_end(&mut value)?;
    if value.len() as u64 > PROC_LIMIT {
        return Err(NamespaceError::Rejected(
            "proc response exceeds its fixed bound",
        ));
    }
    Ok(value)
}

fn read_identity(dir: &File, expected: u32) -> Result<ProcessIdentity> {
    let bytes = read_proc(dir, "stat")?;
    let text =
        std::str::from_utf8(&bytes).map_err(|_| NamespaceError::Rejected("non-text proc stat"))?;
    if !text.starts_with(&format!("{expected} (")) {
        return Err(NamespaceError::Rejected("proc stat PID differs"));
    }
    let (_, tail) = text
        .rsplit_once(") ")
        .ok_or(NamespaceError::Rejected("malformed proc stat"))?;
    let fields: Vec<_> = tail.split_ascii_whitespace().collect();
    if fields.len() < 20 || matches!(fields[0], "Z" | "X" | "x") {
        return Err(NamespaceError::Rejected(
            "process is not a live owned child",
        ));
    }
    let parent = fields[1]
        .parse()
        .map_err(|_| NamespaceError::Rejected("invalid parent PID"))?;
    let start_ticks = fields[19]
        .parse()
        .map_err(|_| NamespaceError::Rejected("invalid process start time"))?;
    Ok(ProcessIdentity {
        pid: expected,
        parent,
        start_ticks,
    })
}

fn status_field<'a>(bytes: &'a [u8], field: &str) -> Result<&'a str> {
    let text =
        std::str::from_utf8(bytes).map_err(|_| NamespaceError::Rejected("non-text proc status"))?;
    let mut matching = text.lines().filter_map(|line| line.strip_prefix(field));
    let value = matching
        .next()
        .ok_or(NamespaceError::Rejected("required status field missing"))?;
    if matching.next().is_some() {
        return Err(NamespaceError::Rejected("duplicate status field"));
    }
    Ok(value)
}

fn require_empty_groups(status: &[u8]) -> Result<()> {
    if !status_field(status, "Groups:")?.trim().is_empty() {
        return Err(NamespaceError::Rejected(
            "child retained supplementary host groups",
        ));
    }
    Ok(())
}

fn require_ids(status: &[u8], field: &str, expected: u32) -> Result<()> {
    let values = status_field(status, field)?
        .split_ascii_whitespace()
        .map(str::parse::<u32>)
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|_| NamespaceError::Rejected("invalid status IDs"))?;
    if values != [expected; 4] {
        return Err(NamespaceError::Rejected(
            "mapped real/effective/saved/fs IDs differ",
        ));
    }
    Ok(())
}

fn verify_map(bytes: &[u8], expected: IdRange) -> Result<()> {
    let text =
        std::str::from_utf8(bytes).map_err(|_| NamespaceError::Rejected("non-text ID map"))?;
    if !text.ends_with('\n') || text.lines().count() != 1 {
        return Err(NamespaceError::Rejected(
            "map is not exactly one complete line",
        ));
    }
    let words: Vec<_> = text.split_ascii_whitespace().collect();
    if words.len() != 3
        || words
            .iter()
            .any(|word| word.is_empty() || !word.bytes().all(|b| b.is_ascii_digit()))
    {
        return Err(NamespaceError::Rejected("invalid map fields"));
    }
    let values = words
        .iter()
        .map(|s| s.parse::<u32>())
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|_| NamespaceError::Rejected("invalid map range"))?;
    if values != [0, expected.start, expected.count] {
        return Err(NamespaceError::Rejected(
            "read-back ID map differs from the held lease",
        ));
    }
    Ok(())
}

fn pidfd_exited(fd: &OwnedFd) -> Result<bool> {
    let mut event = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one initialized pollfd, zero timeout.
    let rc = unsafe { libc::poll(&mut event, 1, 0) };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if event.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
        return Err(NamespaceError::Rejected("pidfd poll error"));
    }
    Ok(event.revents & (libc::POLLIN | libc::POLLHUP) != 0)
}

fn wait_exited(fd: &OwnedFd, duration: Duration) -> Result<bool> {
    let deadline = Instant::now() + duration;
    loop {
        if pidfd_exited(fd)? {
            return Ok(true);
        }
        if Instant::now() >= deadline {
            return Ok(false);
        }
        std::thread::sleep(Duration::from_millis(5));
    }
}

fn signal_owned(fd: &OwnedFd, signal: i32) -> Result<()> {
    // SAFETY: only the retained clone3 pidfd, never a numeric PID lookup.
    if unsafe {
        libc::syscall(
            libc::SYS_pidfd_send_signal,
            fd.as_raw_fd(),
            signal,
            std::ptr::null::<libc::siginfo_t>(),
            0,
        )
    } != 0
    {
        let e = io::Error::last_os_error();
        if e.raw_os_error() != Some(libc::ESRCH) {
            return Err(e.into());
        }
    }
    Ok(())
}

fn send_packet(fd: RawFd, packet: &Packet) -> Result<()> {
    // SAFETY: Packet is repr(C) with checked no-padding layout, borrowed for
    // one nonblocking record. MSG_NOSIGNAL needs no global SIGPIPE change.
    let rc = unsafe {
        libc::send(
            fd,
            (packet as *const Packet).cast(),
            std::mem::size_of::<Packet>(),
            libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT,
        )
    };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if rc as usize != std::mem::size_of::<Packet>() {
        return Err(NamespaceError::Rejected("short protocol record"));
    }
    Ok(())
}

fn receive_packet(fd: RawFd) -> Result<(Packet, libc::ucred)> {
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 32]; // cmsghdr-aligned storage
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen = std::mem::size_of_val(&ancillary);
    // SAFETY: only live writable buffers; any received FDs are CLOEXEC and
    // closed below on rejection, including unknown ancillary records.
    let rc = unsafe {
        libc::recvmsg(
            fd,
            &mut message,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut credentials = None;
    let mut bad = message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0;
    // SAFETY: CMSG_* traverse the bounded kernel-returned ancillary buffer.
    let mut item = unsafe { libc::CMSG_FIRSTHDR(&message) };
    while !item.is_null() {
        let header = unsafe { &*item };
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        if header.cmsg_len < base {
            bad = true;
            break;
        }
        let len = header.cmsg_len - base;
        let data = unsafe { libc::CMSG_DATA(item) };
        if header.cmsg_level == libc::SOL_SOCKET
            && header.cmsg_type == libc::SCM_CREDENTIALS
            && len == std::mem::size_of::<libc::ucred>()
            && credentials.is_none()
        {
            credentials = Some(unsafe { std::ptr::read_unaligned(data.cast::<libc::ucred>()) });
        } else {
            bad = true;
            if header.cmsg_level == libc::SOL_SOCKET && header.cmsg_type == libc::SCM_RIGHTS {
                for index in 0..len / std::mem::size_of::<i32>() {
                    let got = unsafe {
                        std::ptr::read_unaligned(
                            data.add(index * std::mem::size_of::<i32>()).cast::<i32>(),
                        )
                    };
                    unsafe {
                        libc::close(got);
                    }
                }
            }
        }
        item = unsafe { libc::CMSG_NXTHDR(&message, item) };
    }
    if bad || rc as usize != std::mem::size_of::<Packet>() {
        return Err(NamespaceError::Rejected(
            "truncated or unexpected protocol control data",
        ));
    }
    Ok((
        packet,
        credentials.ok_or(NamespaceError::Rejected("kernel peer credentials missing"))?,
    ))
}

#[cfg(test)]
#[path = "production_namespace_tests.rs"]
mod tests;
