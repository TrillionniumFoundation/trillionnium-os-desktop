//! Fixed production cgroup ownership. This draft is not wired into the daemon.
//!
//! The initial-user-namespace broker creates the keeper atomically inside the
//! payload cgroup with CLONE_INTO_CGROUP. A mapped keeper cannot borrow its
//! parent's permission by receiving a cgroup FD. After the actual PID1 is
//! attested, this broker moves only its owned keeper outside the guest cgroup
//! namespace. The hard budget remains above the delegated guest hierarchy.
//!
//! This module grants no caller-selected path, PID, resource policy, or FD.
//! Unknown creation, migration, or retirement retains the entire admission.

use std::cell::Cell;
use std::collections::BTreeSet;
use std::ffi::{CStr, CString};
use std::fs::{File, Metadata};
use std::io::{self, Read};
use std::marker::PhantomData;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::rc::Rc;

use thiserror::Error;

use crate::production_host_admission::HostAdmission;
use crate::production_namespace::{CgroupTreeReadyWitness, OwnedAuthorityRetired};

const UNIT: &str = "droidloom-production.service";
const UNIT_CGROUP: &str = "/system.slice/droidloom-production.service";
const EXPECTED_CPUS: &str = "2-23";
const MEMORY_MAX: u64 = 8 * 1024 * 1024 * 1024;
const MEMORY_HIGH: u64 = 6 * 1024 * 1024 * 1024;
const MIN_AVAILABLE: u64 = 10 * 1024 * 1024 * 1024;
const CPU_MAX: &str = "600000 100000";
const PIDS_MAX: u64 = 32768;
const REQUIRED_CONTROLLERS: [&str; 4] = ["cpu", "cpuset", "memory", "pids"];
const CGROUP2_MAGIC: libc::c_long = 0x6367_7270;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const MAX_READ: usize = 1024 * 1024;
const MAX_GROUPS: usize = 4096;
const UNIT_BYTES: &[u8] = include_bytes!("droidloom-production.service");
const DELEGATED_CONTROLS: [&CStr; 3] = [
    c"cgroup.procs",
    c"cgroup.threads",
    c"cgroup.subtree_control",
];

/// A rejected fixed policy, changed owner, or actual kernel failure.
#[derive(Debug, Error)]
pub enum CgroupError {
    #[error("production cgroup rejected: {0}")]
    Rejected(&'static str),
    #[error("production cgroup admission: {0}")]
    Admission(String),
    #[error("production cgroup owner: {0}")]
    Owner(String),
    #[error(transparent)]
    Io(#[from] io::Error),
}
type Result<T> = std::result::Result<T, CgroupError>;

fn require(value: bool, message: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(CgroupError::Rejected(message))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct NodeIdentity {
    dev: u64,
    ino: u64,
}
impl NodeIdentity {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
        })
    }
}

struct Directory {
    file: File,
    identity: NodeIdentity,
}
impl Directory {
    fn at(parent: &File, name: &CStr) -> Result<Self> {
        let file = open_at(parent, name, libc::O_RDONLY | libc::O_DIRECTORY)?;
        let value = Self {
            identity: NodeIdentity::of(&file)?,
            file,
        };
        require(value.file.metadata()?.is_dir(), "directory required")?;
        cgroup_filesystem(&value.file)?;
        Ok(value)
    }
    fn check(&self, parent: &File, name: &CStr) -> Result<()> {
        require(
            NodeIdentity::of(&self.file)? == self.identity,
            "held cgroup changed",
        )?;
        let named = open_at(parent, name, libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            NodeIdentity::of(&named)? == self.identity,
            "named cgroup replaced",
        )?;
        cgroup_filesystem(&self.file)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Placement {
    Prepared,
    MigrationInProgress,
    KeeperOutside,
    DelegationInProgress,
    GuestDelegated,
}

struct UnitAuthority {
    directories: Vec<File>,
    identities: Vec<NodeIdentity>,
    file: File,
    seal: Metadata,
}

impl UnitAuthority {
    fn open() -> Result<Self> {
        let mut directories = vec![open_absolute(c"/", libc::O_RDONLY | libc::O_DIRECTORY)?];
        for name in [c"etc", c"systemd", c"system"] {
            trusted_directory(directories.last().unwrap())?;
            directories.push(open_at(
                directories.last().unwrap(),
                name,
                libc::O_RDONLY | libc::O_DIRECTORY,
            )?);
        }
        trusted_directory(directories.last().unwrap())?;
        let identities = directories
            .iter()
            .map(NodeIdentity::of)
            .collect::<Result<Vec<_>>>()?;
        let file = open_at(
            directories.last().unwrap(),
            c"droidloom-production.service",
            libc::O_RDONLY,
        )?;
        let seal = file.metadata()?;
        require(
            seal.is_file()
                && seal.uid() == 0
                && seal.gid() == 0
                && seal.nlink() == 1
                && seal.mode() & 0o022 == 0,
            "root-owned fixed unit required",
        )?;
        let mut bytes = Vec::new();
        (&file).take(65537).read_to_end(&mut bytes)?;
        require(
            bytes == UNIT_BYTES,
            "installed production unit differs from reviewed source",
        )?;
        let value = Self {
            directories,
            identities,
            file,
            seal,
        };
        value.check()?;
        Ok(value)
    }

    fn check(&self) -> Result<()> {
        let names = [c"etc", c"systemd", c"system"];
        require(
            self.directories.len() == 4 && self.identities.len() == 4,
            "complete unit directory custody required",
        )?;
        let root = open_absolute(c"/", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            NodeIdentity::of(&root)? == self.identities[0],
            "host root changed",
        )?;
        for (index, file) in self.directories.iter().enumerate() {
            trusted_directory(file)?;
            require(
                NodeIdentity::of(file)? == self.identities[index],
                "held unit parent changed",
            )?;
            if index > 0 {
                let named = open_at(
                    &self.directories[index - 1],
                    names[index - 1],
                    libc::O_RDONLY | libc::O_DIRECTORY,
                )?;
                require(
                    NodeIdentity::of(&named)? == self.identities[index],
                    "named unit parent changed",
                )?;
            }
        }
        let named = open_at(
            self.directories.last().unwrap(),
            c"droidloom-production.service",
            libc::O_RDONLY,
        )?;
        require(
            file_seal(&self.seal) == file_seal(&self.file.metadata()?)
                && file_seal(&self.seal) == file_seal(&named.metadata()?),
            "installed unit changed",
        )
    }
}

struct DelegatedControl {
    name: &'static CStr,
    file: File,
    identity: NodeIdentity,
}

struct PendingResources {
    admission: HostAdmission,
    root: File,
    slice: Directory,
    unit: Directory,
    unit_authority: UnitAuthority,
    name: CString,
    mems: String,
}

struct CreationGuard {
    resources: Option<Box<PendingResources>>,
    attempted: bool,
}

impl Drop for CreationGuard {
    fn drop(&mut self) {
        if self.attempted {
            if let Some(resources) = self.resources.take() {
                // A directory operation with an unknown result retains the
                // actual admission and all ancestor descriptors together.
                std::mem::forget(resources);
            }
        }
    }
}

struct Resources {
    admission: HostAdmission,
    root: File,
    slice: Directory,
    unit: Directory,
    unit_authority: UnitAuthority,
    name: CString,
    budget: Directory,
    keeper: Option<Directory>,
    payload: Option<Directory>,
    delegated_controls: Vec<DelegatedControl>,
    mems: String,
    placement: Cell<Placement>,
    clone_target_lent: Cell<bool>,
    retired: Cell<bool>,
    _thread_bound: PhantomData<Rc<()>>,
}

/// Opaque, non-serializable cgroup and admission custody.
pub struct PreparedCgroup {
    resources: Option<Box<Resources>>,
}

impl PreparedCgroup {
    /// Create the sole fixed budget below the installed delegated service.
    /// No existing budget or partial hierarchy is adopted.
    pub(crate) fn prepare(admission: HostAdmission) -> Result<Self> {
        require_initial_broker()?;
        admission
            .revalidate()
            .map_err(|e| CgroupError::Admission(e.to_string()))?;
        require(
            admission.lease().host_uid() == 1000,
            "this reviewed policy is for host UID 1000",
        )?;
        require(
            available_memory()? >= MIN_AVAILABLE,
            "10 GiB fresh host admission required",
        )?;
        let unit_authority = UnitAuthority::open()?;
        let root = open_absolute(c"/sys/fs/cgroup", libc::O_RDONLY | libc::O_DIRECTORY)?;
        cgroup_filesystem(&root)?;
        trusted_directory(&root)?;
        let slice = Directory::at(&root, c"system.slice")?;
        trusted_directory(&slice.file)?;
        let unit = Directory::at(&slice.file, c"droidloom-production.service")?;
        trusted_directory(&unit.file)?;
        let own = read_absolute(c"/proc/self/cgroup")?;
        require(
            parse_unified_cgroup(&own)? == format!("{UNIT_CGROUP}/broker"),
            "broker must occupy DelegateSubgroup=broker",
        )?;
        require(
            read_control(&unit.file, c"cgroup.type")? == "domain",
            "domain cgroup required",
        )?;
        require(
            read_pids(&unit.file)?.is_empty(),
            "delegation root has internal tasks",
        )?;
        check_limits(&unit.file)?;
        check_affinity()?;
        require(
            parse_id_list(&read_control(&unit.file, c"cpuset.cpus.effective")?)?
                == (2..=23).collect(),
            "service cpuset does not reserve CPUs 0 and 1",
        )?;
        let present = words(&read_control(&unit.file, c"cgroup.controllers")?);
        require(
            REQUIRED_CONTROLLERS.iter().all(|n| present.contains(*n)),
            "required controllers not delegated",
        )?;
        let enabled = words(&read_control(&unit.file, c"cgroup.subtree_control")?);
        require(
            REQUIRED_CONTROLLERS.iter().all(|n| enabled.contains(*n)),
            "unit controllers must already be enabled by systemd",
        )?;
        let mems = read_control(&unit.file, c"cpuset.mems.effective")?;
        let parsed_mems = parse_id_list(&mems)?;
        require(!parsed_mems.is_empty(), "effective memory nodes required")?;
        let name = CString::new("cell-u1000").expect("fixed name");
        let mut pending = CreationGuard {
            resources: Some(Box::new(PendingResources {
                admission,
                root,
                slice,
                unit,
                unit_authority,
                name,
                mems,
            })),
            attempted: false,
        };
        pending.attempted = true;
        let p = pending.resources.as_ref().unwrap();
        mkdir_at(&p.unit.file, &p.name, 0o755)?;
        // Once a directory exists, a guard owns the admission even when later
        // setup fails. Only known-empty, never-lent construction may unwind.
        let budget = Directory::at(&p.unit.file, &p.name)?;
        let p = *pending.resources.take().unwrap();
        let mut value = Self {
            resources: Some(Box::new(Resources {
                admission: p.admission,
                root: p.root,
                slice: p.slice,
                unit: p.unit,
                unit_authority: p.unit_authority,
                name: p.name,
                budget,
                keeper: None,
                payload: None,
                delegated_controls: Vec::new(),
                mems: p.mems,
                placement: Cell::new(Placement::Prepared),
                clone_target_lent: Cell::new(false),
                retired: Cell::new(false),
                _thread_bound: PhantomData,
            })),
        };
        let setup = value.finish_creation().and_then(|()| value.revalidate());
        if let Err(error) = setup {
            // There cannot yet be a clone: no descriptor has escaped prepare.
            let _ = value.retire_unstarted();
            return Err(error);
        }
        Ok(value)
    }

    fn get(&self) -> &Resources {
        self.resources
            .as_ref()
            .expect("prepared cgroup owns resources")
    }

    fn finish_creation(&mut self) -> Result<()> {
        let r = self.resources.as_mut().expect("owned resources");
        trusted_directory(&r.budget.file)?;
        write_control(&r.budget.file, c"memory.max", &MEMORY_MAX.to_string())?;
        write_control(&r.budget.file, c"memory.high", &MEMORY_HIGH.to_string())?;
        write_control(&r.budget.file, c"memory.swap.max", "0")?;
        write_control(&r.budget.file, c"cpu.max", CPU_MAX)?;
        write_control(&r.budget.file, c"pids.max", &PIDS_MAX.to_string())?;
        write_control(&r.budget.file, c"cpuset.cpus", EXPECTED_CPUS)?;
        write_control(&r.budget.file, c"cpuset.mems", &r.mems)?;
        require(
            read_pids(&r.budget.file)?.is_empty(),
            "new budget unexpectedly occupied",
        )?;
        write_control(
            &r.budget.file,
            c"cgroup.subtree_control",
            "+cpu +cpuset +memory +pids",
        )?;
        mkdir_at(&r.budget.file, c"keeper", 0o755)?;
        r.keeper = Some(Directory::at(&r.budget.file, c"keeper")?);
        mkdir_at(&r.budget.file, c"payload", 0o755)?;
        r.payload = Some(Directory::at(&r.budget.file, c"payload")?);
        for d in [r.keeper.as_ref().unwrap(), r.payload.as_ref().unwrap()] {
            trusted_directory(&d.file)?;
            require(
                read_pids(&d.file)?.is_empty(),
                "new leaf unexpectedly occupied",
            )?;
            require(
                read_control(&d.file, c"cgroup.subtree_control")?.is_empty(),
                "new leaf has controllers enabled",
            )?;
        }
        for name in DELEGATED_CONTROLS {
            let file = open_at(&r.payload.as_ref().unwrap().file, name, libc::O_RDONLY)?;
            cgroup_filesystem(&file)?;
            let metadata = file.metadata()?;
            require(
                metadata.is_file()
                    && metadata.uid() == 0
                    && metadata.gid() == 0
                    && metadata.mode() & 0o022 == 0,
                "new delegated control is not root owned",
            )?;
            r.delegated_controls.push(DelegatedControl {
                name,
                identity: NodeIdentity::of(&file)?,
                file,
            });
        }
        check_limits(&r.budget.file)?;
        check_placement_masks(&r.budget.file, &r.mems)?;
        Ok(())
    }

    pub(crate) fn admission(&self) -> &HostAdmission {
        &self.get().admission
    }

    /// Only Owner's initial-root clone3 consumes this borrowed descriptor.
    /// The fixed parent API also adds CLONE_INTO_CGROUP, never a PID write.
    pub(crate) fn initial_clone_target(&self) -> Result<BorrowedFd<'_>> {
        self.revalidate()?;
        let r = self.get();
        require(
            r.placement.get() == Placement::Prepared,
            "initial clone target already consumed",
        )?;
        require(
            !r.clone_target_lent.get(),
            "initial clone descriptor is single use",
        )?;
        let payload = &r
            .payload
            .as_ref()
            .ok_or(CgroupError::Rejected("payload absent"))?
            .file;
        require(
            read_pids(payload)?.is_empty(),
            "initial clone target not empty",
        )?;
        r.clone_target_lent.set(true);
        Ok(payload.as_fd())
    }

    /// Read-only resource and ownership checks; this does not grant map writes.
    pub(crate) fn revalidate(&self) -> Result<()> {
        let r = self.get();
        require(!r.retired.get(), "cgroup is retired")?;
        require_initial_broker()?;
        r.admission
            .revalidate()
            .map_err(|e| CgroupError::Admission(e.to_string()))?;
        r.unit_authority.check()?;
        r.slice.check(&r.root, c"system.slice")?;
        r.unit
            .check(&r.slice.file, c"droidloom-production.service")?;
        r.budget.check(&r.unit.file, &r.name)?;
        trusted_directory(&r.unit.file)?;
        trusted_directory(&r.budget.file)?;
        require(
            read_pids(&r.unit.file)?.is_empty() && read_pids(&r.budget.file)?.is_empty(),
            "budget/delegation root gained internal tasks",
        )?;
        check_limits(&r.unit.file)?;
        check_limits(&r.budget.file)?;
        check_placement_masks(&r.budget.file, &r.mems)?;
        check_affinity()?;
        require(
            parse_id_list(&read_control(&r.unit.file, c"cpuset.cpus.effective")?)?
                == (2..=23).collect(),
            "service effective CPU placement changed",
        )?;
        if let Some(keeper) = &r.keeper {
            keeper.check(&r.budget.file, c"keeper")?;
            trusted_directory(&keeper.file)?;
        }
        if let Some(payload) = &r.payload {
            payload.check(&r.budget.file, c"payload")?;
            if r.placement.get() != Placement::GuestDelegated {
                trusted_directory(&payload.file)?;
            } else {
                self.check_delegation()?;
            }
        }
        require(
            !matches!(
                r.placement.get(),
                Placement::MigrationInProgress | Placement::DelegationInProgress
            ),
            "cgroup transition result has not been proven",
        )
    }

    /// Move only the attested keeper out of the guest namespace's root.
    /// The target name and host PID cannot be supplied by a caller.
    pub(crate) fn move_keeper_outside(&self, witness: &CgroupTreeReadyWitness<'_>) -> Result<()> {
        self.revalidate()?;
        let r = self.get();
        require(
            r.placement.get() == Placement::Prepared,
            "keeper migration is single-use",
        )?;
        require(
            r.clone_target_lent.get(),
            "owned initial clone must precede migration",
        )?;
        let payload = &r.payload.as_ref().unwrap().file;
        let keeper = &r.keeper.as_ref().unwrap().file;
        witness
            .revalidate_for_migration(payload)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        let kp = witness.keeper_host_pid();
        let tp = witness.tree_host_pid();
        require(
            kp != tp && kp > 1 && tp > 1,
            "distinct owned keeper and PID1 required",
        )?;
        let expected_payload = format!("{UNIT_CGROUP}/cell-u1000/payload");
        let expected_keeper = format!("{UNIT_CGROUP}/cell-u1000/keeper");
        check_task_cgroup(witness.keeper_proc_directory(), &expected_payload)?;
        check_task_cgroup(witness.tree_proc_directory(), &expected_payload)?;
        require(
            read_pids(payload)? == BTreeSet::from([kp, tp]) && read_pids(keeper)?.is_empty(),
            "unexpected tasks before keeper migration",
        )?;
        r.placement.set(Placement::MigrationInProgress);
        write_control(keeper, c"cgroup.procs", &kp.to_string())?;
        witness
            .revalidate_for_migration(payload)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        check_task_cgroup(witness.keeper_proc_directory(), &expected_keeper)?;
        check_task_cgroup(witness.tree_proc_directory(), &expected_payload)?;
        require(
            read_pids(payload)? == BTreeSet::from([tp])
                && read_pids(keeper)? == BTreeSet::from([kp]),
            "unexpected tasks after keeper migration",
        )?;
        r.placement.set(Placement::KeeperOutside);
        self.revalidate()
    }

    /// Delegate only the guest root below the immutable outer hard budget.
    /// Child phase 44/45 must move PID1 into its own init subgroup before
    /// enabling its controllers. This method does not claim that phase passed.
    pub(crate) fn delegate_guest_hierarchy(
        &self,
        witness: &CgroupTreeReadyWitness<'_>,
    ) -> Result<()> {
        self.revalidate()?;
        let r = self.get();
        require(
            r.placement.get() == Placement::KeeperOutside,
            "keeper must be proven outside first",
        )?;
        let payload = &r.payload.as_ref().unwrap().file;
        witness
            .revalidate_for_migration(payload)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        self.check_after_migration(witness)?;
        let (uids, gids) = r.admission.lease().broker_ranges();
        require(
            uids.count >= 100000 && gids.count >= 100000,
            "complete existing ranges required",
        )?;
        let system_gid = gids
            .start
            .checked_add(1000)
            .ok_or(CgroupError::Rejected("mapped system group overflow"))?;
        // No controller limit in the outer budget is delegated. Kernel
        // nsdelegate and ancestor write checks remain independently required.
        r.placement.set(Placement::DelegationInProgress);
        require(
            r.delegated_controls.len() == 3,
            "complete delegation control custody required",
        )?;
        for control in &r.delegated_controls {
            let named = open_at(payload, control.name, libc::O_RDONLY)?;
            require(
                NodeIdentity::of(&named)? == control.identity
                    && NodeIdentity::of(&control.file)? == control.identity,
                "delegation control changed",
            )?;
            change_owner_mode(&control.file, uids.start, system_gid, 0o664)?;
        }
        change_owner_mode(payload, uids.start, system_gid, 0o775)?;
        let m = payload.metadata()?;
        require(
            m.uid() == uids.start && m.gid() == system_gid && m.mode() & 0o7777 == 0o775,
            "guest root delegation differs",
        )?;
        witness
            .revalidate_for_migration(payload)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        self.check_after_migration(witness)?;
        self.check_delegation()?;
        r.placement.set(Placement::GuestDelegated);
        self.revalidate()
    }

    fn check_after_migration(&self, witness: &CgroupTreeReadyWitness<'_>) -> Result<()> {
        let r = self.get();
        let kp = witness.keeper_host_pid();
        let tp = witness.tree_host_pid();
        require(
            kp != tp && kp > 1 && tp > 1,
            "distinct owned tasks required",
        )?;
        check_task_cgroup(
            witness.keeper_proc_directory(),
            &format!("{UNIT_CGROUP}/cell-u1000/keeper"),
        )?;
        check_task_cgroup(
            witness.tree_proc_directory(),
            &format!("{UNIT_CGROUP}/cell-u1000/payload"),
        )?;
        require(
            read_pids(&r.keeper.as_ref().unwrap().file)? == BTreeSet::from([kp])
                && read_pids(&r.payload.as_ref().unwrap().file)? == BTreeSet::from([tp]),
            "owned pre-exec task placement changed",
        )
    }

    fn check_delegation(&self) -> Result<()> {
        let r = self.get();
        let payload = &r
            .payload
            .as_ref()
            .ok_or(CgroupError::Rejected("payload absent"))?
            .file;
        let (uids, gids) = r.admission.lease().broker_ranges();
        let group = gids
            .start
            .checked_add(1000)
            .ok_or(CgroupError::Rejected("mapped group overflow"))?;
        let m = payload.metadata()?;
        require(
            m.uid() == uids.start && m.gid() == group && m.mode() & 0o7777 == 0o775,
            "guest cgroup root owner/mode changed",
        )?;
        require(
            r.delegated_controls.len() == 3,
            "complete delegated controls required",
        )?;
        for control in &r.delegated_controls {
            let named = open_at(payload, control.name, libc::O_RDONLY)?;
            require(
                NodeIdentity::of(&named)? == control.identity
                    && NodeIdentity::of(&control.file)? == control.identity,
                "delegated control replaced",
            )?;
            let m = control.file.metadata()?;
            require(
                m.is_file()
                    && m.uid() == uids.start
                    && m.gid() == group
                    && m.mode() & 0o7777 == 0o664,
                "delegated control owner/mode changed",
            )?;
        }
        Ok(())
    }

    /// Call only after the same Owner has proved keeper and any PID1 reaped.
    /// The witness also binds this exact held payload cgroup. It is not JSON.
    pub(crate) fn retire(&self, witness: &OwnedAuthorityRetired<'_>) -> Result<()> {
        let r = self.get();
        let payload = &r
            .payload
            .as_ref()
            .ok_or(CgroupError::Rejected("payload absent"))?
            .file;
        witness
            .revalidate_cgroup_retirement(payload)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        self.remove_empty_owned_hierarchy()?;
        r.retired.set(true);
        Ok(())
    }

    fn retire_unstarted(&self) -> Result<()> {
        require(
            self.get().placement.get() == Placement::Prepared
                && !self.get().clone_target_lent.get(),
            "unstarted cleanup after a descriptor was lent is forbidden",
        )?;
        self.remove_empty_owned_hierarchy()?;
        self.get().retired.set(true);
        Ok(())
    }

    fn remove_empty_owned_hierarchy(&self) -> Result<()> {
        let r = self.get();
        r.budget.check(&r.unit.file, &r.name)?;
        require(
            !populated(&r.budget.file)?,
            "owned hierarchy remains populated",
        )?;
        require(
            read_pids(&r.budget.file)?.is_empty(),
            "budget root still occupied",
        )?;
        // The returned snapshot owns each open directory and its inode; no
        // later dynamic enumeration is used to authorize deletion.
        let mut count = 0;
        let snapshot = snapshot_children(&r.budget.file, 0, &mut count)?;
        let roots: BTreeSet<_> = snapshot
            .iter()
            .map(|x| x.name.as_bytes().to_vec())
            .collect();
        let mut expected = BTreeSet::new();
        if r.payload.is_some() {
            expected.insert(b"payload".to_vec());
        }
        if r.keeper.is_some() {
            expected.insert(b"keeper".to_vec());
        }
        require(roots == expected, "unowned immediate cgroup appeared")?;
        for child in &snapshot {
            remove_snapshot(&r.budget.file, child)?;
        }
        require(
            list_directories(&r.budget.file)?.is_empty() && !populated(&r.budget.file)?,
            "cgroup tree changed during retirement",
        )?;
        r.budget.check(&r.unit.file, &r.name)?;
        unlink_directory(&r.unit.file, &r.name)?;
        match open_at(&r.unit.file, &r.name, libc::O_RDONLY | libc::O_DIRECTORY) {
            Err(CgroupError::Io(e)) if e.raw_os_error() == Some(libc::ENOENT) => Ok(()),
            _ => Err(CgroupError::Rejected("owned budget removal not confirmed")),
        }
    }
}

impl Drop for PreparedCgroup {
    fn drop(&mut self) {
        if let Some(resources) = self.resources.take() {
            if resources.retired.get() {
                drop(resources);
            } else {
                std::mem::forget(resources);
            }
        }
    }
}

fn open_absolute(path: &CStr, flags: i32) -> Result<File> {
    let fd = unsafe {
        libc::open(
            path.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn open_at(parent: &File, name: &CStr, flags: i32) -> Result<File> {
    require(
        !name.to_bytes().contains(&b'/') && name.to_bytes() != b"..",
        "fixed single component required",
    )?;
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn bounded_read(file: File) -> Result<String> {
    let mut bytes = Vec::new();
    file.take((MAX_READ + 1) as u64).read_to_end(&mut bytes)?;
    require(bytes.len() <= MAX_READ, "bounded kernel record exceeded")?;
    String::from_utf8(bytes).map_err(|_| CgroupError::Rejected("non-UTF8 kernel record"))
}
fn read_absolute(path: &CStr) -> Result<String> {
    bounded_read(open_absolute(path, libc::O_RDONLY)?)
}
fn read_control(dir: &File, name: &CStr) -> Result<String> {
    let file = open_at(dir, name, libc::O_RDONLY)?;
    cgroup_filesystem(&file)?;
    Ok(bounded_read(file)?.trim_end_matches('\n').to_owned())
}
fn write_control(dir: &File, name: &CStr, text: &str) -> Result<()> {
    require(
        !text.is_empty() && text.len() < 4096 && !text.contains('\n') && !text.contains('\0'),
        "bounded single cgroup operation required",
    )?;
    let file = open_at(dir, name, libc::O_WRONLY)?;
    cgroup_filesystem(&file)?;
    let bytes = text.as_bytes();
    let n = unsafe { libc::write(file.as_raw_fd(), bytes.as_ptr().cast(), bytes.len()) };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(n as usize == bytes.len(), "partial cgroup operation")
}
fn trusted_directory(file: &File) -> Result<()> {
    let m = file.metadata()?;
    require(
        m.is_dir() && m.uid() == 0 && m.gid() == 0 && m.mode() & 0o022 == 0,
        "root-owned non-writable cgroup parent required",
    )
}
fn cgroup_filesystem(file: &File) -> Result<()> {
    let mut st = unsafe { std::mem::zeroed::<libc::statfs>() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut st) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        st.f_type == CGROUP2_MAGIC,
        "actual unified cgroup filesystem required",
    )
}
fn mkdir_at(dir: &File, name: &CStr, mode: libc::mode_t) -> Result<()> {
    if unsafe { libc::mkdirat(dir.as_raw_fd(), name.as_ptr(), mode) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}
fn unlink_directory(dir: &File, name: &CStr) -> Result<()> {
    if unsafe { libc::unlinkat(dir.as_raw_fd(), name.as_ptr(), libc::AT_REMOVEDIR) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(())
}
fn change_owner_mode(file: &File, uid: u32, gid: u32, mode: libc::mode_t) -> Result<()> {
    require(
        uid != u32::MAX && gid != u32::MAX,
        "sentinel identity forbidden",
    )?;
    if unsafe { libc::fchown(file.as_raw_fd(), uid, gid) } != 0
        || unsafe { libc::fchmod(file.as_raw_fd(), mode) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let m = file.metadata()?;
    require(
        m.uid() == uid && m.gid() == gid && m.mode() & 0o7777 == mode,
        "delegated control ownership differs",
    )
}
fn words(text: &str) -> BTreeSet<String> {
    text.split_whitespace().map(str::to_owned).collect()
}
fn parse_number(text: &str) -> Result<u64> {
    require(
        !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit()),
        "canonical unsigned counter required",
    )?;
    let value = text
        .parse::<u64>()
        .map_err(|_| CgroupError::Rejected("counter overflow"))?;
    require(value.to_string() == text, "noncanonical counter")?;
    Ok(value)
}
fn parse_id_list(text: &str) -> Result<BTreeSet<u32>> {
    require(
        !text.is_empty() && text.len() < 4096,
        "bounded nonempty id list required",
    )?;
    let mut set = BTreeSet::new();
    for item in text.split(',') {
        let parts: Vec<_> = item.split('-').collect();
        require(parts.len() == 1 || parts.len() == 2, "id range grammar")?;
        let first = u32::try_from(parse_number(parts[0])?)
            .map_err(|_| CgroupError::Rejected("id overflow"))?;
        let last = if parts.len() == 2 {
            u32::try_from(parse_number(parts[1])?)
                .map_err(|_| CgroupError::Rejected("id overflow"))?
        } else {
            first
        };
        require(first <= last && last < 4096, "id range bound")?;
        for id in first..=last {
            require(set.insert(id), "overlapping id range")?;
        }
    }
    Ok(set)
}
fn parse_unified_cgroup(text: &str) -> Result<String> {
    let mut lines = text.lines();
    let line = lines
        .next()
        .ok_or(CgroupError::Rejected("missing unified cgroup"))?;
    require(lines.next().is_none(), "multiple hierarchy records")?;
    let path = line
        .strip_prefix("0::/")
        .ok_or(CgroupError::Rejected("unified hierarchy required"))?;
    require(
        !path.contains("//")
            && !path.split('/').any(|x| x == "." || x == "..")
            && !path.contains('\0'),
        "noncanonical cgroup path",
    )?;
    Ok(format!("/{path}"))
}
fn check_task_cgroup(proc_directory: &File, expected: &str) -> Result<()> {
    require(
        parse_unified_cgroup(&bounded_read(open_at(
            proc_directory,
            c"cgroup",
            libc::O_RDONLY,
        )?)?)?
            == expected,
        "owned task is in a different cgroup",
    )
}
fn read_pids(dir: &File) -> Result<BTreeSet<u32>> {
    let text = read_control(dir, c"cgroup.procs")?;
    let mut pids = BTreeSet::new();
    for line in text.lines() {
        let p = u32::try_from(parse_number(line)?)
            .map_err(|_| CgroupError::Rejected("PID overflow"))?;
        require(
            p > 0 && pids.insert(p) && pids.len() <= PIDS_MAX as usize,
            "invalid/duplicate task set",
        )?;
    }
    Ok(pids)
}
fn populated(dir: &File) -> Result<bool> {
    let text = read_control(dir, c"cgroup.events")?;
    let mut result = None;
    for line in text.lines() {
        let fields: Vec<_> = line.split(' ').collect();
        require(fields.len() == 2, "cgroup event grammar")?;
        if fields[0] == "populated" {
            require(
                result.is_none() && matches!(fields[1], "0" | "1"),
                "invalid population event",
            )?;
            result = Some(fields[1] == "1");
        }
    }
    result.ok_or(CgroupError::Rejected("population event absent"))
}
fn check_limits(dir: &File) -> Result<()> {
    for (name, wanted) in [
        (c"memory.max", MEMORY_MAX),
        (c"memory.high", MEMORY_HIGH),
        (c"memory.swap.max", 0),
        (c"pids.max", PIDS_MAX),
    ] {
        require(
            parse_number(&read_control(dir, name)?)? == wanted,
            "fixed cgroup budget changed",
        )?;
    }
    require(
        read_control(dir, c"cpu.max")? == CPU_MAX,
        "fixed CPU quota changed",
    )?;
    require(
        parse_number(&read_control(dir, c"memory.swap.current")?)? == 0,
        "swap observed",
    )?;
    Ok(())
}
fn check_placement_masks(dir: &File, mems: &str) -> Result<()> {
    require(
        parse_id_list(&read_control(dir, c"cpuset.cpus")?)? == (2..=23).collect(),
        "budget CPU placement changed",
    )?;
    require(
        parse_id_list(&read_control(dir, c"cpuset.cpus.effective")?)? == (2..=23).collect(),
        "effective CPU placement changed",
    )?;
    require(
        parse_id_list(&read_control(dir, c"cpuset.mems")?)? == parse_id_list(mems)?,
        "memory-node placement changed",
    )
}
fn check_affinity() -> Result<()> {
    let mut set = unsafe { std::mem::zeroed::<libc::cpu_set_t>() };
    if unsafe { libc::sched_getaffinity(0, std::mem::size_of_val(&set), &mut set) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    for cpu in 0..libc::CPU_SETSIZE as usize {
        require(
            unsafe { libc::CPU_ISSET(cpu, &set) } == (2..=23).contains(&cpu),
            "broker affinity changed",
        )?;
    }
    Ok(())
}
fn available_memory() -> Result<u64> {
    let text = read_absolute(c"/proc/meminfo")?;
    let lines: Vec<_> = text
        .lines()
        .filter(|x| x.starts_with("MemAvailable:"))
        .collect();
    require(lines.len() == 1, "unique MemAvailable required")?;
    let parts: Vec<_> = lines[0].split_whitespace().collect();
    require(parts.len() == 3 && parts[2] == "kB", "MemAvailable grammar")?;
    parse_number(parts[1])?
        .checked_mul(1024)
        .ok_or(CgroupError::Rejected("memory size overflow"))
}
fn require_initial_broker() -> Result<()> {
    require(
        unsafe { libc::getuid() == 0 && libc::geteuid() == 0 },
        "initial-root broker required",
    )?;
    require(
        read_absolute(c"/proc/self/attr/apparmor/current")?
            == "droidloom-production-broker (enforce)\n",
        "reviewed enforcing broker AppArmor domain required",
    )?;
    for (path, ns_type, identity) in [
        (c"/proc/self/ns/user", libc::CLONE_NEWUSER, 3_u64),
        (c"/proc/self/ns/pid", libc::CLONE_NEWPID, 4_u64),
    ] {
        // Namespace entries are kernel magic links: the exact fixed path is
        // intentionally followed and the resulting nsfs descriptor is typed.
        let fd = unsafe { libc::open(path.as_ptr(), libc::O_RDONLY | libc::O_CLOEXEC) };
        if fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let ns = unsafe { File::from_raw_fd(fd) };
        let actual_type = unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) };
        let mut actual_id = 0_u64;
        let rc = unsafe { libc::ioctl(ns.as_raw_fd(), NS_GET_ID, &mut actual_id as *mut u64) };
        require(
            actual_type == ns_type && rc == 0 && actual_id == identity,
            "initial user/PID namespace required",
        )?;
    }
    Ok(())
}
fn file_seal(m: &Metadata) -> (u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64) {
    (
        m.dev(),
        m.ino(),
        m.mode(),
        m.uid(),
        m.gid(),
        m.nlink(),
        m.size(),
        m.mtime(),
        m.mtime_nsec(),
        m.ctime(),
        m.ctime_nsec(),
    )
}

struct Snapshot {
    name: CString,
    dir: Directory,
    children: Vec<Snapshot>,
}
fn list_directories(dir: &File) -> Result<Vec<CString>> {
    let file = open_at(dir, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    cgroup_filesystem(&file)?;
    let mut buffer = [0_u8; 16384];
    let mut names = Vec::new();
    loop {
        let n = unsafe {
            libc::syscall(
                libc::SYS_getdents64,
                file.as_raw_fd(),
                buffer.as_mut_ptr(),
                buffer.len(),
            )
        };
        if n < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if n == 0 {
            break;
        }
        let mut at = 0;
        while at < n as usize {
            require(at + 19 <= n as usize, "short directory record")?;
            let len = u16::from_ne_bytes([buffer[at + 16], buffer[at + 17]]) as usize;
            require(
                len >= 20 && at + len <= n as usize,
                "directory record bounds",
            )?;
            let kind = buffer[at + 18];
            let body = &buffer[at + 19..at + len];
            let end = body
                .iter()
                .position(|x| *x == 0)
                .ok_or(CgroupError::Rejected("directory name not terminated"))?;
            let bytes = &body[..end];
            if bytes != b"." && bytes != b".." {
                require(
                    !bytes.is_empty() && !bytes.contains(&b'/'),
                    "invalid cgroup child name",
                )?;
                require(
                    kind == libc::DT_DIR || kind == libc::DT_REG,
                    "non-cgroup filesystem child",
                )?;
                if kind == libc::DT_DIR {
                    names.push(
                        CString::new(bytes)
                            .map_err(|_| CgroupError::Rejected("invalid directory name"))?,
                    );
                    require(names.len() <= MAX_GROUPS, "too many child cgroups")?;
                }
            }
            at += len;
        }
    }
    names.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    require(
        names.windows(2).all(|w| w[0] != w[1]),
        "duplicate cgroup directory",
    )?;
    Ok(names)
}
fn snapshot_children(parent: &File, depth: usize, count: &mut usize) -> Result<Vec<Snapshot>> {
    require(depth < 64, "cgroup tree depth exceeded")?;
    let names = list_directories(parent)?;
    let mut out = Vec::new();
    for name in names {
        *count += 1;
        require(*count <= MAX_GROUPS, "cgroup tree size exceeded")?;
        let dir = Directory::at(parent, &name)?;
        require(
            !populated(&dir.file)? && read_pids(&dir.file)?.is_empty(),
            "cgroup still occupied at retirement",
        )?;
        let children = snapshot_children(&dir.file, depth + 1, count)?;
        dir.check(parent, &name)?;
        out.push(Snapshot {
            name,
            dir,
            children,
        });
    }
    Ok(out)
}
fn remove_snapshot(parent: &File, node: &Snapshot) -> Result<()> {
    node.dir.check(parent, &node.name)?;
    require(
        !populated(&node.dir.file)? && read_pids(&node.dir.file)?.is_empty(),
        "task arrived during retirement",
    )?;
    let names: Vec<_> = node.children.iter().map(|x| x.name.clone()).collect();
    require(
        list_directories(&node.dir.file)? == names,
        "new child appeared during retirement",
    )?;
    for child in &node.children {
        remove_snapshot(&node.dir.file, child)?;
    }
    require(
        list_directories(&node.dir.file)?.is_empty(),
        "new child appeared before removal",
    )?;
    node.dir.check(parent, &node.name)?;
    unlink_directory(parent, &node.name)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cgroup_fixed_policy_keeps_two_cpus_outside() {
        assert_eq!(parse_id_list(EXPECTED_CPUS).unwrap(), (2..=23).collect());
        assert_eq!(MEMORY_MAX, 8589934592);
        assert_eq!(MEMORY_HIGH, 6442450944);
        assert_eq!(MIN_AVAILABLE, 10737418240);
        assert_eq!(CPU_MAX, "600000 100000");
        assert_eq!(PIDS_MAX, 32768);
    }
    #[test]
    fn cgroup_rejects_ambiguous_masks_and_counters() {
        for text in ["", "2-1", "2,2", "2-3,3", "02", "-1", "2-4096", "2-3-4"] {
            assert!(parse_id_list(text).is_err(), "{text}");
        }
        for text in ["", "max", "-1", "01", "1 ", "18446744073709551616"] {
            assert!(parse_number(text).is_err(), "{text}");
        }
    }
    #[test]
    fn cgroup_rejects_v1_and_parent_path_records() {
        assert_eq!(
            parse_unified_cgroup("0::/system.slice/example.service/broker\n").unwrap(),
            "/system.slice/example.service/broker"
        );
        for text in ["1:cpu:/x\n", "0::/a\n0::/b\n", "0::/a/../b\n", "0::/a//b\n"] {
            assert!(parse_unified_cgroup(text).is_err(), "{text}");
        }
    }
    #[test]
    fn cgroup_unit_uses_normal_entry_and_delegated_broker() {
        let unit = std::str::from_utf8(UNIT_BYTES).unwrap();
        assert!(unit.contains("DelegateSubgroup=broker\n"));
        assert!(unit.contains("--socket /run/droidloom/control.sock\n"));
        assert!(!unit.contains("--production-broker"));
        assert!(unit.contains("AppArmorProfile=droidloom-production-broker\n"));
        assert_eq!(UNIT, "droidloom-production.service");
    }
}
