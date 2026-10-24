// SPDX-License-Identifier: MPL-2.0

//! Bounded successors for the exact frozen Root image.
//!
//! The private gate serializes preparation, publication, receipt replay and
//! Root closure. No image, PID-table or TaskSet lock spans CPU-owner work. All
//! fallible image/namespace work precedes the sole owner commit. Children then
//! enter the ordinary parent/PID/group path before any Thread::run.

use os_control::{NativeResourceReceipt, PublisherId};

use super::{trusted_roles::prepare_role, *};
use crate::{
    device::misc::{hepta_boot_id, hepta_image_space_id},
    fs::cgroupfs::NativeCpuManager,
    process::{
        clone::{CloneFlags, set_parent_and_group},
        process::trusted_control::{RetainedHistories, TrustedControlSlots},
        program_loader::elf::TrustedInitialSnapshot,
    },
};

const LAUNCH_BYTES: usize = 128;
const SUCCESSOR_BOOT_BYTES: u64 = 240;
const HISTORY_ROLE: u64 = 5;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LaunchCommand {
    Query,
    Advance,
    ReadRetirement,
    AckSaved,
}

#[derive(Clone, Copy)]
struct LaunchRequest {
    command: LaunchCommand,
    expected: u64,
}

impl LaunchRequest {
    fn decode(bytes: &[u8; LAUNCH_BYTES]) -> Result<Self> {
        let word = |offset| u64::from_le_bytes(bytes[offset..offset + 8].try_into().unwrap());
        if &bytes[..8] != b"HOS2LAUN" || word(8) != 1 || bytes[32..].iter().any(|byte| *byte != 0) {
            return_errno_with_message!(Errno::EINVAL, "invalid native launcher request")
        }
        match word(16) {
            0 if word(24) == 0 => Ok(Self {
                command: LaunchCommand::Query,
                expected: 0,
            }),
            1 => Ok(Self {
                command: LaunchCommand::Advance,
                expected: word(24),
            }),
            2 => Ok(Self {
                command: LaunchCommand::ReadRetirement,
                expected: word(24),
            }),
            3 => Ok(Self {
                command: LaunchCommand::AckSaved,
                expected: word(24),
            }),
            _ => return_errno_with_message!(Errno::EINVAL, "invalid native launcher command"),
        }
    }

    fn next_generation(self, current: u64) -> Result<Option<u64>> {
        if self.command != LaunchCommand::Advance {
            return_errno_with_message!(
                Errno::EINVAL,
                "only Advance selects a new launch generation"
            )
        }
        if current != 0 && self.expected.checked_add(1) == Some(current) {
            return Ok(None);
        }
        if self.expected != current {
            return_errno_with_message!(Errno::ESTALE, "native launch generation changed")
        }
        current.checked_add(1).map(Some).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "native launch generation exhausted")
        })
    }
}

#[derive(Clone, Copy)]
struct LaunchReceipt {
    generation: u64,
    root: crate::process::Pid,
    workload: crate::process::Pid,
    manager: crate::process::Pid,
    recovery: crate::process::Pid,
    history_only: crate::process::Pid,
    spaces: [[u8; 16]; 2],
}

impl LaunchReceipt {
    fn encode(self) -> [u8; LAUNCH_BYTES] {
        let mut bytes = [0u8; LAUNCH_BYTES];
        bytes[..8].copy_from_slice(b"HOS2LRES");
        let words = [
            1,
            if self.history_only == 0 { 1 } else { 2 },
            self.generation,
            u64::from(self.root),
            u64::from(self.workload),
            u64::from(self.manager),
            u64::from(self.recovery),
            u64::from(self.history_only),
            self.generation.saturating_sub(1),
        ];
        for (index, word) in words.into_iter().enumerate() {
            bytes[8 + index * 8..16 + index * 8].copy_from_slice(&word.to_le_bytes());
        }
        bytes[80..96].copy_from_slice(&self.spaces[0]);
        bytes[96..112].copy_from_slice(&self.spaces[1]);
        bytes
    }
}

/// One immutable original-owner retirement evidence record per completed
/// launch, plus its exact-generation acknowledgement. This is part of the
/// last launch receipt, not another D/K ledger. No previous origin is pinned.
struct SavedLaunchRetirement {
    generation: u64,
    bytes: [u8; LAUNCH_BYTES],
    acknowledged: bool,
}

impl SavedLaunchRetirement {
    fn policy(
        generation: u64,
        spaces: [[u8; 16]; 2],
        status: u8,
        evaluated_ns: Option<u64>,
        receipt: Option<NativeResourceReceipt>,
    ) -> Self {
        let mut result = Self::history_only(generation, spaces);
        result.bytes[24..32].copy_from_slice(&u64::from(status).to_le_bytes());
        result.bytes[32..40].copy_from_slice(&evaluated_ns.unwrap_or(0).to_le_bytes());
        let flags = 1u64 | if evaluated_ns.is_some() { 2 } else { 0 };
        result.bytes[120..128].copy_from_slice(&flags.to_le_bytes());
        if let Some(receipt) = receipt {
            result.bytes[40..56].copy_from_slice(&receipt.stable_object_id().bytes());
            let words = [
                receipt.previous_revision(),
                receipt.revision(),
                receipt.effective_boottime_ns(),
                receipt.consumed_at_apply_ns(),
            ];
            for (index, word) in words.into_iter().enumerate() {
                result.bytes[56 + index * 8..64 + index * 8].copy_from_slice(&word.to_le_bytes());
            }
        }
        result
    }

    fn history_only(generation: u64, spaces: [[u8; 16]; 2]) -> Self {
        let mut bytes = [0u8; LAUNCH_BYTES];
        bytes[..8].copy_from_slice(b"HOS2LWDR");
        bytes[8..16].copy_from_slice(&1u64.to_le_bytes());
        bytes[16..24].copy_from_slice(&generation.to_le_bytes());
        bytes[88..104].copy_from_slice(&spaces[0]);
        bytes[104..120].copy_from_slice(&spaces[1]);
        Self {
            generation,
            bytes,
            acknowledged: false,
        }
    }

    fn read(&self, generation: u64) -> Result<[u8; LAUNCH_BYTES]> {
        if self.generation != generation {
            return_errno_with_message!(
                Errno::ESTALE,
                "native retirement receipt generation changed"
            )
        }
        Ok(self.bytes)
    }

    fn acknowledge(&mut self, generation: u64) -> Result<()> {
        self.read(generation)?;
        self.acknowledged = true;
        Ok(())
    }

    fn require_saved(&self) -> Result<()> {
        if !self.acknowledged {
            return_errno_with_message!(
                Errno::EBUSY,
                "Root has not acknowledged saving the last native retirement receipt"
            )
        }
        Ok(())
    }
}

struct LauncherState {
    closed: bool,
    receipt: LaunchReceipt,
    // Only the two management children OR one history-only child. Their
    // parent's normal children map owns them until the original consuming wait.
    children: [Option<Weak<Process>>; 2],
    managers: [Arc<NativeCpuManager>; 2],
    histories: RetainedHistories,
    retirement: Option<SavedLaunchRetirement>,
}

impl LauncherState {
    fn previous_children_reaped(&self) -> bool {
        children_reaped(&self.children)
    }
}

fn children_reaped(children: &[Option<Weak<Process>>; 2]) -> bool {
    children
        .iter()
        .flatten()
        .all(|child| child.upgrade().is_none())
}

/// The only constructor is the kernel-owned initial four-role transaction.
/// Image bytes always come from one original bounded immutable snapshot.
/// The retained executable Path is metadata and is never opened again.
pub(in crate::process::process) struct TrustedLauncher {
    root: Weak<Process>,
    key: ProcessImageKey,
    workload: Weak<Process>,
    snapshot: TrustedInitialSnapshot,
    fs: ThreadFsInfo,
    path: Path,
    abs_path: String,
    argv: Vec<CString>,
    envp: Vec<CString>,
    state: Mutex<LauncherState>,
}

impl TrustedLauncher {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn new(
        root: &PreparedInitialProcess,
        manager: &PreparedInitialProcess,
        workload: &PreparedInitialProcess,
        recovery: &PreparedInitialProcess,
        managers: [Arc<NativeCpuManager>; 2],
        histories: RetainedHistories,
        snapshot: TrustedInitialSnapshot,
        fs: ThreadFsInfo,
        path: Path,
        abs_path: String,
        argv: Vec<CString>,
        envp: Vec<CString>,
    ) -> Arc<Self> {
        let receipt = LaunchReceipt {
            generation: 0,
            root: root.process.pid(),
            workload: workload.process.pid(),
            manager: manager.process.pid(),
            recovery: recovery.process.pid(),
            history_only: 0,
            spaces: histories.spaces(),
        };
        Arc::new(Self {
            root: Arc::downgrade(&root.process),
            key: root.key,
            workload: Arc::downgrade(&workload.process),
            snapshot,
            fs,
            path,
            abs_path,
            argv,
            envp,
            state: Mutex::new(LauncherState {
                closed: false,
                receipt,
                children: [
                    Some(Arc::downgrade(&manager.process)),
                    Some(Arc::downgrade(&recovery.process)),
                ],
                managers,
                histories,
                retirement: None,
            }),
        })
    }

    pub(in crate::process::process) fn belongs_to(&self, key: ProcessImageKey) -> bool {
        self.key == key
    }

    pub(in crate::process::process) fn close(&self) {
        let mut state = self.state.lock();
        if !state.closed {
            state.closed = true;
            for manager in &state.managers {
                manager.revoke();
            }
        }
    }

    fn dispatch(
        &self,
        caller: &Process,
        key: ProcessImageKey,
        input: &[u8; LAUNCH_BYTES],
    ) -> Result<[u8; LAUNCH_BYTES]> {
        let root = self
            .root
            .upgrade()
            .ok_or_else(|| Error::new(Errno::ESTALE))?;
        if !core::ptr::eq(root.as_ref(), caller) || key != self.key {
            return_errno_with_message!(
                Errno::EPERM,
                "native launcher belongs to another Root image"
            )
        }
        let request = LaunchRequest::decode(input)?;
        let mut state = self.state.lock();
        caller.hepta_image.lock().initial_launcher(key)?;
        if state.closed {
            return_errno_with_message!(Errno::ESTALE, "native Root launcher is closed")
        }
        match request.command {
            LaunchCommand::Query => return Ok(state.receipt.encode()),
            LaunchCommand::ReadRetirement => {
                let saved = state.retirement.as_ref().ok_or_else(|| {
                    Error::with_message(
                        Errno::ENODATA,
                        "no native successor retirement receipt yet",
                    )
                })?;
                return saved.read(request.expected);
            }
            LaunchCommand::AckSaved => {
                let saved = state.retirement.as_mut().ok_or_else(|| {
                    Error::with_message(
                        Errno::ENODATA,
                        "no native successor retirement receipt yet",
                    )
                })?;
                saved.acknowledge(request.expected)?;
                return Ok(state.receipt.encode());
            }
            LaunchCommand::Advance => {}
        }
        // The previous successful transaction is its own bounded replay
        // record. A failed userspace copyout cannot cause a duplicate launch.
        let Some(generation) = request.next_generation(state.receipt.generation)? else {
            return Ok(state.receipt.encode());
        };
        if let Some(saved) = &state.retirement {
            saved.require_saved()?;
        }
        if !state.previous_children_reaped() {
            return_errno_with_message!(
                Errno::EBUSY,
                "previous native children have not been reaped"
            )
        }
        if state.histories.fully_retired() {
            let workload = self
                .workload
                .upgrade()
                .filter(|process| !process.status().is_zombie())
                .ok_or_else(|| {
                    Error::with_message(Errno::ESRCH, "original native workload ended")
                })?;
            self.launch_pair(&root, &workload, &mut state, generation)?;
        } else {
            // Historical D remains drainable after its workload dies. This
            // branch never resolves that numeric PID or grants a CPU effect.
            self.launch_history(&root, &mut state, generation)?;
        }
        Ok(state.receipt.encode())
    }

    fn prepare(
        &self,
        allocation: (Arc<Process>, VmarHandle),
        page: Box<[u8; PAGE_SIZE]>,
    ) -> Result<(PreparedInitialProcess, LoadedInitialImage, Vaddr)> {
        prepare_role(
            allocation,
            self.fs.clone(),
            &self.snapshot,
            &self.abs_path,
            self.argv.clone(),
            self.envp.clone(),
            page,
            Credentials::new_root(),
            Box::new(crate::fs::init_console_file_table),
        )
    }

    fn launch_pair(
        &self,
        root: &Arc<Process>,
        workload: &Arc<Process>,
        state: &mut LauncherState,
        generation: u64,
    ) -> Result<()> {
        let manager = allocate_initial_process(&self.path, new_resource_limits_for_init());
        let recovery = allocate_initial_process(&self.path, new_resource_limits_for_init());
        let keys = [
            manager.0.hepta_capspace_session()?,
            recovery.0.hepta_capspace_session()?,
        ];
        let spaces = keys.map(hepta_image_space_id);
        let pids = [manager.0.pid(), workload.pid(), recovery.0.pid()];
        let receipt = LaunchReceipt {
            generation,
            root: root.pid(),
            workload: workload.pid(),
            manager: pids[0],
            recovery: pids[2],
            history_only: 0,
            spaces,
        };
        let mut pending = PendingLaunch::new();
        let (prepared, image, entry) =
            self.prepare(manager, successor_page(1, receipt, pids[0], spaces[0]))?;
        pending.push(prepared);
        let (prepared, recovery_image, recovery_entry) =
            self.prepare(recovery, successor_page(3, receipt, pids[2], spaces[1]))?;
        pending.push(prepared);
        let plan = NativeCpuManager::prepare_successor_pair(
            state.managers.clone(),
            spaces.map(PublisherId::new),
        )?;
        let managers = plan.managers();
        let [manager_slots, recovery_slots] =
            TrustedControlSlots::prepare_original_owner_pair(managers.clone(), keys)?;
        let histories = recovery_slots.retained_histories()?;
        pending.processes[0].activate_control(image, entry, manager_slots)?;
        pending.processes[1].activate_control(recovery_image, recovery_entry, recovery_slots)?;
        pending.claim_all()?;
        // No fallible operation remains after this canonical owner commit.
        // In particular no path reopen, image load or namespace allocation is
        // permitted between publication and first scheduling.
        let retired = plan.commit()?;
        let retirement = SavedLaunchRetirement::policy(
            generation,
            state.histories.spaces(),
            retired.status_code(),
            retired.evaluated_ns(),
            retired.resource_receipt(),
        );
        let children = pending.children();
        pending.publish(root);
        state.managers = managers;
        state.histories = histories;
        state.children = children;
        state.receipt = receipt;
        state.retirement = Some(retirement);
        println!(
            "[hepta-g2] successor roles activated: generation={} manager={} workload={} recovery={} bootstrap_version=4 bytes=240 hepta_durability=false",
            generation, pids[0], pids[1], pids[2]
        );
        pending.run();
        Ok(())
    }

    fn launch_history(
        &self,
        root: &Arc<Process>,
        state: &mut LauncherState,
        generation: u64,
    ) -> Result<()> {
        let allocation = allocate_initial_process(&self.path, new_resource_limits_for_init());
        let key = allocation.0.hepta_capspace_session()?;
        let pid = allocation.0.pid();
        let receipt = LaunchReceipt {
            generation,
            root: root.pid(),
            workload: state.receipt.workload,
            manager: 0,
            recovery: 0,
            history_only: pid,
            spaces: state.histories.spaces(),
        };
        let (prepared, image, entry) = self.prepare(
            allocation,
            successor_page(HISTORY_ROLE, receipt, pid, hepta_image_space_id(key)),
        )?;
        let mut pending = PendingLaunch::new();
        pending.push(prepared);
        let slots = TrustedControlSlots::prepare_history_only(key, &state.histories);
        pending.processes[0].activate_control(image, entry, slots)?;
        pending.claim_all()?;
        let retirement = SavedLaunchRetirement::history_only(generation, state.histories.spaces());
        let children = pending.children();
        pending.publish(root);
        // The original CPU policy and both original history owners stay in
        // place. This process has no management grant or new effect namespace.
        state.children = children;
        state.receipt = receipt;
        state.retirement = Some(retirement);
        println!(
            "[hepta-g2] history successor activated: generation={} history={} workload={} bootstrap_version=4 bytes=240 hepta_durability=false",
            generation, pid, receipt.workload
        );
        pending.run();
        Ok(())
    }
}

/// A claimed first run is still private until normal Process registration.
/// On any preparation/commit error explicitly close even claimed images; the
/// original PreparedInitialProcess Drop alone only cancels unclaimed images.
struct PendingLaunch {
    processes: Vec<PreparedInitialProcess>,
    published: bool,
}

impl PendingLaunch {
    fn new() -> Self {
        Self {
            processes: Vec::with_capacity(2),
            published: false,
        }
    }

    fn push(&mut self, prepared: PreparedInitialProcess) {
        assert!(self.processes.len() < 2);
        self.processes.push(prepared);
    }

    fn claim_all(&mut self) -> Result<()> {
        for prepared in &mut self.processes {
            prepared.claim_resume()?;
        }
        Ok(())
    }

    fn children(&self) -> [Option<Weak<Process>>; 2] {
        [
            self.processes
                .first()
                .map(|prepared| Arc::downgrade(&prepared.process)),
            self.processes
                .get(1)
                .map(|prepared| Arc::downgrade(&prepared.process)),
        ]
    }

    fn publish(&mut self, root: &Arc<Process>) {
        for prepared in &self.processes {
            set_parent_and_group(CloneFlags::empty(), root, &prepared.process);
        }
        self.published = true;
    }

    fn run(self) {
        assert!(self.published);
        for prepared in &self.processes {
            prepared.task.as_thread().unwrap().run();
        }
    }
}

impl Drop for PendingLaunch {
    fn drop(&mut self) {
        if !self.published {
            for prepared in &self.processes {
                let cancelled = prepared
                    .process
                    .hepta_image
                    .lock()
                    .cancel_unpublished_initial(prepared.key);
                if cancelled {
                    prepared.process.close_hepta_image();
                }
            }
        }
    }
}

fn successor_page(
    role: u64,
    receipt: LaunchReceipt,
    self_pid: crate::process::Pid,
    local_space: [u8; 16],
) -> Box<[u8; PAGE_SIZE]> {
    let mut page = Box::new([0u8; PAGE_SIZE]);
    page[..8].copy_from_slice(b"HOS2BOOT");
    let manage = role == 1 || role == 3;
    let second_history = role == 3 || role == HISTORY_ROLE;
    let words = [
        4,
        role,
        SUCCESSOR_BOOT_BYTES,
        if manage { 1 } else { 0 },
        if manage { 1 } else { 0 },
        if manage { 2 } else { 0 },
        if manage { 1 } else { 0 },
        3,
        1,
        if second_history { 4 } else { 0 },
        if second_history { 1 } else { 0 },
    ];
    for (index, word) in words.into_iter().enumerate() {
        page[8 + index * 8..16 + index * 8].copy_from_slice(&word.to_le_bytes());
    }
    page[96..112].copy_from_slice(&hepta_boot_id());
    page[112..128].copy_from_slice(&receipt.spaces[0]);
    page[128..144].copy_from_slice(&receipt.spaces[1]);
    for (index, pid) in [receipt.manager, receipt.workload, receipt.recovery]
        .into_iter()
        .enumerate()
    {
        page[144 + index * 8..152 + index * 8].copy_from_slice(&u64::from(pid).to_le_bytes());
    }
    page[168..176].copy_from_slice(&(if manage { 50_000_000u64 } else { 0 }).to_le_bytes());
    page[176..184].copy_from_slice(&100_000_000u64.to_le_bytes());
    page[184..192].copy_from_slice(&(if manage { 300_000_000_000u64 } else { 0 }).to_le_bytes());
    page[192..200].copy_from_slice(&u64::from(receipt.root).to_le_bytes());
    page[200..208].copy_from_slice(&u64::from(self_pid).to_le_bytes());
    page[208..224].copy_from_slice(&local_space);
    page[224..232].copy_from_slice(&receipt.generation.to_le_bytes());
    page
}

impl Process {
    pub(crate) fn dispatch_hepta_launcher(
        &self,
        key: ProcessImageKey,
        input: &[u8; LAUNCH_BYTES],
    ) -> Result<[u8; LAUNCH_BYTES]> {
        let launcher = self.hepta_image.lock().initial_launcher(key)?.clone();
        launcher.dispatch(self, key, input)
    }
}

#[cfg(ktest)]
mod tests;
