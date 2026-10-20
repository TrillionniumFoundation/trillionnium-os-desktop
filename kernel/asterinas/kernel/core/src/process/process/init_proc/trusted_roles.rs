// SPDX-License-Identifier: MPL-2.0

//! Fixed, sealed G1-d bootstrap roles from one immutable executable snapshot.
//!
//! IDs, argv, UID and pathname never assign a role. This kernel boot plan owns
//! the three actual allocations and final-image tokens. All resource setup,
//! grants, page contents and first-run claims precede every Thread::run.

use os_control::PublisherId;

use super::*;
use crate::{
    device::misc::{hepta_boot_id, hepta_image_space_id},
    fs::cgroupfs::NativeCpuManager,
    process::{
        clone::{CloneFlags, set_parent_and_group},
        process::trusted_control::TrustedControlSlots,
        program_loader::elf::TrustedInitialSnapshot,
    },
};

const BOOT_PAGE_BYTES: u64 = 192;

pub(super) fn spawn(
    path_resolver: PathResolver,
    executable_path: Path,
    argv: Vec<CString>,
    envp: Vec<CString>,
) -> Result<Arc<Process>> {
    let fs = ThreadFsInfo::new(path_resolver);
    let abs_path = fs.resolver().read().make_abs_path(&executable_path).into_string();
    let executable = UndetectedExecutable::open(
        executable_path.clone(),
        ShebangScriptPath::Accessible(CString::new(abs_path.clone()).unwrap()),
    )?;
    // Exactly one bounded read of the input. No role loads from a later inode
    // snapshot, and the compiled manifest is not replaced for negative boots.
    let snapshot = executable.snapshot_trusted_initial()?;
    let manager = allocate_initial_process(&executable_path);
    let workload = allocate_initial_process(&executable_path);
    let recovery = allocate_initial_process(&executable_path);
    let keys = [manager.0.hepta_capspace_session()?, workload.0.hepta_capspace_session()?,
        recovery.0.hepta_capspace_session()?];
    let pids = [manager.0.pid(), workload.0.pid(), recovery.0.pid()];
    let spaces = [hepta_image_space_id(keys[0]), hepta_image_space_id(keys[2])];
    let mut prepared = Vec::with_capacity(3);
    for (index, allocation) in [manager, workload, recovery].into_iter().enumerate() {
        let page = boot_page(index as u64 + 1, pids, spaces);
        prepared.push(prepare_role(allocation, fs.clone(), &snapshot, &abs_path,
            argv.clone(), envp.clone(), page)?);
    }
    drop(snapshot);
    let (mut recovery, recovery_image, recovery_entry) = prepared.pop().unwrap();
    let (mut workload, workload_image, workload_entry) = prepared.pop().unwrap();
    let (mut manager, manager_image, manager_entry) = prepared.pop().unwrap();
    let (observer, issued) = NativeCpuObserver::prepare(&workload.process, workload.key.nonce())?;
    let managers = NativeCpuManager::prepare_pair(observer,
        [PublisherId::new(spaces[0]), PublisherId::new(spaces[1])], issued)?;
    let [manager_slots, recovery_slots] = TrustedControlSlots::prepare_pair(managers,
        [manager.key, recovery.key])?;
    // Each private token is consumed against its actual final VMAR/entry.
    // The workload is sealed but receives no management or history capability.
    manager.activate_control(manager_image, manager_entry, manager_slots)?;
    println!("[hepta-g1d] trusted role committed: role=1 pid={}", pids[0]);
    workload_image.consume(&workload.vmar, workload_entry)?;
    println!("[hepta-g1d] trusted role committed: role=2 pid={}", pids[1]);
    recovery.activate_control(recovery_image, recovery_entry, recovery_slots)?;
    println!("[hepta-g1d] trusted role committed: role=3 pid={}", pids[2]);
    manager.claim_resume()?;
    workload.claim_resume()?;
    recovery.claim_resume()?;

    // Reuse normal parent, process-group and PID-table ownership. No fallible
    // setup remains after publication; no role has run at this point.
    set_bootstrap_session_and_group(&manager.process);
    set_parent_and_group(CloneFlags::empty(), &manager.process, &workload.process);
    set_parent_and_group(CloneFlags::empty(), &manager.process, &recovery.process);
    println!("[hepta-g1d] initial control activated: manager={} workload={} recovery={} cap_ns=50000000 period_ns=100000000 lease_ns=300000000000 hepta_durability=false",
        pids[0], pids[1], pids[2]);
    let result = manager.process.clone();
    workload.task.as_thread().unwrap().run();
    recovery.task.as_thread().unwrap().run();
    manager.task.as_thread().unwrap().run();
    Ok(result)
}

fn prepare_role(
    (process, vmar): (Arc<Process>, VmarHandle),
    fs: ThreadFsInfo,
    snapshot: &TrustedInitialSnapshot,
    abs_path: &str,
    argv: Vec<CString>,
    envp: Vec<CString>,
    boot: Box<[u8; PAGE_SIZE]>,
) -> Result<(PreparedInitialProcess, LoadedInitialImage, Vaddr)> {
    let loaded_vmar = vmar.clone_arc();
    let (info, image) = snapshot.load(loaded_vmar.clone(), argv, envp, boot)?;
    let mut user_ctx = UserContext::default();
    user_ctx.set_instruction_pointer(info.entry_point as _);
    user_ctx.set_stack_pointer(info.user_stack_top as _);
    let task = PosixThreadBuilder::new(
        process.pid(), derive_thread_name(abs_path), Box::new(user_ctx), Credentials::new_root(), vmar,
    ).process(Arc::downgrade(&process)).fs(Arc::new(fs)).build();
    process.tasks().lock().insert(task.clone()).unwrap();
    let prepared = PreparedInitialProcess::new(process, loaded_vmar, task)?;
    Ok((prepared, image, info.entry_point))
}

fn boot_page(role: u64, pids: [crate::process::Pid; 3], spaces: [[u8; 16]; 2])
    -> Box<[u8; PAGE_SIZE]>
{
    let mut page = Box::new([0u8; PAGE_SIZE]);
    page[..8].copy_from_slice(b"HOS2BOOT");
    let has_grants = role == 1 || role == 3;
    let words = [2, role, BOOT_PAGE_BYTES,
        if has_grants { 1 } else { 0 }, if has_grants { 1 } else { 0 },
        if has_grants { 2 } else { 0 }, if has_grants { 1 } else { 0 },
        if has_grants { 3 } else { 0 }, if has_grants { 1 } else { 0 },
        if role == 3 { 4 } else { 0 }, if role == 3 { 1 } else { 0 }];
    for (index, word) in words.into_iter().enumerate() {
        page[8 + index * 8..16 + index * 8].copy_from_slice(&word.to_le_bytes());
    }
    page[96..112].copy_from_slice(&hepta_boot_id());
    page[112..128].copy_from_slice(&spaces[0]);
    page[128..144].copy_from_slice(&spaces[1]);
    let tail = [u64::from(pids[0]), u64::from(pids[1]), u64::from(pids[2]),
        50_000_000, 100_000_000, 300_000_000_000];
    for (index, word) in tail.into_iter().enumerate() {
        page[144 + index * 8..152 + index * 8].copy_from_slice(&word.to_le_bytes());
    }
    page
}
