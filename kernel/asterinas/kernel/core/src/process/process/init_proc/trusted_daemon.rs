// SPDX-License-Identifier: MPL-2.0

//! Four frozen initial images for the original Root/Supervisor host path.
//!
//! The actual Root is PID 1 and owns the three actual children. Manager and
//! recovery receive their original CPU/history slots before first execution;
//! Root receives no such slot. Userspace Supervisor consumes these children
//! through its original lifecycle rather than execing or transferring a role.
//! All images still obey the original static snapshot and sealing bounds.

use os_control::PublisherId;

use super::{
    trusted_roles::{prepare_role, workload_credentials},
    *,
};
use crate::{
    device::misc::{hepta_boot_id, hepta_image_space_id},
    fs::{
        cgroupfs::NativeCpuManager,
        file::{
            FileLike,
            file_table::{FdFlags, FileTable},
        },
    },
    process::{
        clone::{CloneFlags, set_parent_and_group},
        process::trusted_control::TrustedControlSlots,
        rlimit::new_resource_limits_for_initial_workload,
    },
};

const BOOT_PAGE_BYTES: u64 = 200;
const ROOT_ROLE: u64 = 4;
// The original protected Host requires UID 60001. The untrusted workload must
// not share it: equal UIDs would bypass private Host paths and signal isolation.
const WORKLOAD_ID: u32 = 60002;
const WORKLOAD_AS_BYTES: u64 = 256 * 1024 * 1024;
const WORKLOAD_USER_PAGES: usize = 64 * 1024 * 1024 / PAGE_SIZE;

pub(super) fn spawn(
    path_resolver: PathResolver,
    executable_path: Path,
    argv: Vec<CString>,
    envp: Vec<CString>,
) -> Result<Arc<Process>> {
    let fs = ThreadFsInfo::new(path_resolver);
    let abs_path = fs
        .resolver()
        .read()
        .make_abs_path(&executable_path)
        .into_string();
    let executable = UndetectedExecutable::open(
        executable_path.clone(),
        ShebangScriptPath::Accessible(CString::new(abs_path.clone()).unwrap()),
    )?;
    // One original immutable snapshot feeds all final VMARs. There is no later
    // pathname lookup, shared writable image or userspace-selected grant.
    let snapshot = executable.snapshot_trusted_initial()?;
    let root = allocate_initial_process(&executable_path, new_resource_limits_for_init());
    if root.0.pid() != 1 {
        return_errno_with_message!(
            Errno::EINVAL,
            "trusted original Root must be the first process"
        );
    }
    let manager = allocate_initial_process(&executable_path, new_resource_limits_for_init());
    let workload = allocate_initial_process_with_owner(
        &executable_path,
        new_resource_limits_for_initial_workload(WORKLOAD_AS_BYTES),
        Some(crate::vm::user_memory::UserMemoryAccount::new(
            WORKLOAD_USER_PAGES,
        )),
    );
    let recovery = allocate_initial_process(&executable_path, new_resource_limits_for_init());
    let keys = [
        root.0.hepta_capspace_session()?,
        manager.0.hepta_capspace_session()?,
        workload.0.hepta_capspace_session()?,
        recovery.0.hepta_capspace_session()?,
    ];
    let root_pid = root.0.pid();
    let pids = [manager.0.pid(), workload.0.pid(), recovery.0.pid()];
    let spaces = [hepta_image_space_id(keys[1]), hepta_image_space_id(keys[3])];
    let pending_children = Arc::new(Mutex::new(None::<[Arc<Task>; 3]>));
    let workload_console = Arc::new(Mutex::new(None::<[Arc<dyn FileLike>; 3]>));
    let mut prepared = Vec::with_capacity(4);
    for (index, allocation) in [root, manager, workload, recovery].into_iter().enumerate() {
        let role = [ROOT_ROLE, 1, 2, 3][index];
        let page = boot_page(role, root_pid, pids, spaces);
        let startup: Box<dyn FnOnce(&Context<'_>) + Send> = if index == 0 {
            let pending_children = pending_children.clone();
            let workload_console = workload_console.clone();
            Box::new(move |ctx| {
                // Normal PID 1 device/console initialization precedes this
                // hook. Only its standard handles enter the workload table.
                let console = {
                    let borrowed = ctx.thread_local.borrow_file_table();
                    let files = borrowed.unwrap().read();
                    assert_eq!(files.len(), 3);
                    [0, 1, 2].map(|fd| files.get_file(fd.try_into().unwrap()).unwrap().clone())
                };
                *workload_console.lock() = Some(console);
                let children = pending_children
                    .lock()
                    .take()
                    .expect("sealed original-owner children were not prepared");
                for task in children {
                    task.as_thread().unwrap().run();
                }
            })
        } else if index == 2 {
            let workload_console = workload_console.clone();
            Box::new(move |ctx| {
                let console = workload_console
                    .lock()
                    .take()
                    .expect("original-owner workload console was not prepared");
                for file in console {
                    FileTable::reserve_fd(ctx, FdFlags::empty())
                        .unwrap()
                        .install(file);
                }
            })
        } else {
            Box::new(crate::fs::init_console_file_table)
        };
        // Manager/recovery must open their own root-only device in this SAME
        // final image, then drop to the original Host's fixed UID/caps before
        // original Root registration. Neither step grants a kernel capability.
        let credentials = if index == 2 {
            workload_credentials(WORKLOAD_ID)?
        } else {
            Credentials::new_root()
        };
        prepared.push(prepare_role(
            allocation,
            fs.clone(),
            &snapshot,
            &abs_path,
            argv.clone(),
            envp.clone(),
            page,
            credentials,
            startup,
        )?);
    }
    drop(snapshot);
    let (mut recovery, recovery_image, recovery_entry) = prepared.pop().unwrap();
    let (mut workload, workload_image, workload_entry) = prepared.pop().unwrap();
    let (mut manager, manager_image, manager_entry) = prepared.pop().unwrap();
    let (mut root, root_image, root_entry) = prepared.pop().unwrap();
    let (observer, issued) = NativeCpuObserver::prepare(&workload.process, workload.key.nonce())?;
    let managers = NativeCpuManager::prepare_pair(
        observer,
        [PublisherId::new(spaces[0]), PublisherId::new(spaces[1])],
        issued,
    )?;
    managers[0].arm_watchdog(workload.process.clone())?;
    let [manager_slots, recovery_slots] =
        TrustedControlSlots::prepare_original_owner_pair(managers, [manager.key, recovery.key])?;
    root.activate_root(root_image, root_entry)?;
    manager.activate_control(manager_image, manager_entry, manager_slots)?;
    workload_image.consume(&workload.vmar, workload_entry)?;
    recovery.activate_control(recovery_image, recovery_entry, recovery_slots)?;
    root.claim_resume()?;
    manager.claim_resume()?;
    workload.claim_resume()?;
    recovery.claim_resume()?;

    // All fallible role setup has completed. Publish the original Process
    // relationships, then release only Root; its startup hook releases the
    // already prepared children after standard descriptors are ready.
    set_bootstrap_session_and_group(&root.process);
    for child in [&manager.process, &workload.process, &recovery.process] {
        set_parent_and_group(CloneFlags::empty(), &root.process, child);
    }
    workload
        .process
        .to_new_session()
        .expect("fresh original-owner workload session must be available");
    println!(
        "[hepta-g2] initial roles activated: root={} manager={} workload={} recovery={} workload_uid=60002 bootstrap_version=3 bytes=200 hepta_durability=false",
        root_pid, pids[0], pids[1], pids[2]
    );
    let result = root.process.clone();
    *pending_children.lock() = Some([
        manager.task.clone(),
        workload.task.clone(),
        recovery.task.clone(),
    ]);
    root.task.as_thread().unwrap().run();
    Ok(result)
}

fn boot_page(
    role: u64,
    root_pid: crate::process::Pid,
    pids: [crate::process::Pid; 3],
    spaces: [[u8; 16]; 2],
) -> Box<[u8; PAGE_SIZE]> {
    let mut page = Box::new([0u8; PAGE_SIZE]);
    page[..8].copy_from_slice(b"HOS2BOOT");
    let has_grants = role == 1 || role == 3;
    let words = [
        3,
        role,
        BOOT_PAGE_BYTES,
        if has_grants { 1 } else { 0 },
        if has_grants { 1 } else { 0 },
        if has_grants { 2 } else { 0 },
        if has_grants { 1 } else { 0 },
        if has_grants { 3 } else { 0 },
        if has_grants { 1 } else { 0 },
        if role == 3 { 4 } else { 0 },
        if role == 3 { 1 } else { 0 },
    ];
    for (index, word) in words.into_iter().enumerate() {
        page[8 + index * 8..16 + index * 8].copy_from_slice(&word.to_le_bytes());
    }
    page[96..112].copy_from_slice(&hepta_boot_id());
    page[112..128].copy_from_slice(&spaces[0]);
    page[128..144].copy_from_slice(&spaces[1]);
    for (index, pid) in pids.into_iter().enumerate() {
        page[144 + index * 8..152 + index * 8].copy_from_slice(&(pid as u64).to_le_bytes());
    }
    page[168..176].copy_from_slice(&50_000_000u64.to_le_bytes());
    page[176..184].copy_from_slice(&100_000_000u64.to_le_bytes());
    page[184..192].copy_from_slice(&300_000_000_000u64.to_le_bytes());
    page[192..200].copy_from_slice(&(root_pid as u64).to_le_bytes());
    page
}
