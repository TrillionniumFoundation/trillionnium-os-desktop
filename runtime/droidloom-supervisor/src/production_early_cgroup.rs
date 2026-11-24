//! Attach the retained boot child's PID 1 to the production unit's real budget.
use super::*;
use crate::production_selection::early_generation::EarlyBaseAdmission;

pub(super) struct EarlyPlacement {
    pidfd: File,
    proc_identity: (u64, u64),
    original_namespace: File,
    rooted_namespace: Option<File>,
}
fn named_cgroup_ns(child: &EarlyBaseAdmission<'_>) -> io::Result<File> {
    child.observe_init_metadata()?.namespaces[6].try_clone()
}
fn check_early_task_cgroup(child: &EarlyBaseAdmission<'_>, expected: &str) -> Result<()> {
    let observed = child.observe_init_metadata()?;
    require(
        parse_unified_cgroup(&observed.host.cgroup)? == expected,
        "owned task is in a different cgroup",
    )
}
fn kernel_owner(namespace: &File) -> io::Result<File> {
    let fd = unsafe { libc::ioctl(namespace.as_raw_fd(), 0xb701 as libc::c_ulong) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn reaped(pid: libc::pid_t) -> io::Result<i32> {
    let mut state = 0;
    loop {
        if unsafe { libc::waitpid(pid, &mut state, 0) } == pid {
            return if libc::WIFEXITED(state) {
                Ok(libc::WEXITSTATUS(state))
            } else {
                Err(io::Error::other("migration worker exited on a signal"))
            };
        }
        let e = io::Error::last_os_error();
        if e.kind() != io::ErrorKind::Interrupted {
            return Err(e);
        }
    }
}
// The numeric argument must be interpreted inside the selected PID namespace.
// Its PID 1 is never recycled there. Pinning a host pidfd alone does not give
// that guarantee when writing a host PID to cgroup.procs.
fn move_original_init(namespace: &File, target: &File) -> Result<()> {
    cgroup_filesystem(target)?;
    let procs = open_at(target, c"cgroup.procs", libc::O_WRONLY)?;
    cgroup_filesystem(&procs)?;
    let nfd = namespace.as_raw_fd();
    let cfd = procs.as_raw_fd();
    require(
        unsafe { libc::ioctl(nfd, NS_GET_NSTYPE) } == libc::CLONE_NEWPID,
        "original PID namespace required",
    )?;
    let parent = unsafe { libc::fork() };
    if parent < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if parent == 0 {
        // No allocation, formatted output, destructor or Rust runtime call
        // between fork and exit in either child.
        unsafe {
            if libc::setns(nfd, libc::CLONE_NEWPID) < 0 {
                libc::_exit(101);
            }
            let inside = libc::fork();
            if inside < 0 {
                libc::_exit(102);
            }
            if inside == 0 {
                if libc::getpid() <= 1 {
                    libc::_exit(103);
                }
                let one = [b'1'];
                let mut n = libc::write(cfd, one.as_ptr().cast(), 1);
                while n < 0 && *libc::__errno_location() == libc::EINTR {
                    n = libc::write(cfd, one.as_ptr().cast(), 1);
                }
                libc::_exit(if n == 1 { 0 } else { 104 });
            }
            let mut status = 0;
            let mut w = libc::waitpid(inside, &mut status, 0);
            while w < 0 && *libc::__errno_location() == libc::EINTR {
                w = libc::waitpid(inside, &mut status, 0);
            }
            libc::_exit(if w == inside && libc::WIFEXITED(status) {
                libc::WEXITSTATUS(status)
            } else {
                105
            });
        }
    }
    require(
        reaped(parent)? == 0,
        "original namespace PID 1 did not enter its own cgroup",
    )
}
impl PreparedCgroup {
    fn require_early_origin(
        &self,
        child: &EarlyBaseAdmission<'_>,
        owner: &RuntimeMacOwner,
    ) -> Result<()> {
        child
            .revalidate()
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        let (mac, selection) = owner
            .objects()
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        self.get()
            .unit_authority
            .context
            .require_pair(mac, selection)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        require(
            std::ptr::eq(self.admission().lease(), child.identity_lease())
                && child.board().selection().same_selection(selection),
            "early child belongs to another lease or selection",
        )?;
        let manager = self.systemd_owner(selection)?;
        mac.observe_systemd_owner(&manager)
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        Ok(())
    }
    pub(crate) fn place_early_payload(
        &self,
        child: &EarlyBaseAdmission<'_>,
        owner: &RuntimeMacOwner,
    ) -> Result<()> {
        self.revalidate()?;
        self.require_early_origin(child, owner)?;
        let r = self.get();
        require(
            r.placement.get() == Placement::Prepared
                && !r.clone_target_lent.get()
                && r.early.borrow().is_none(),
            "early cgroup was already assigned",
        )?;
        let payload = &r
            .payload
            .as_ref()
            .ok_or(CgroupError::Rejected("payload absent"))?
            .file;
        let keeper = &r
            .keeper
            .as_ref()
            .ok_or(CgroupError::Rejected("keeper absent"))?
            .file;
        require(
            read_pids(payload)?.is_empty()
                && read_pids(keeper)?.is_empty()
                && list_directories(payload)?.is_empty(),
            "fresh empty budget required",
        )?;
        check_early_task_cgroup(child, crate::production_selection::EARLY_FACTORY_CGROUP)?;
        let binding = EarlyPlacement {
            pidfd: child.board().pidfd().try_clone()?,
            proc_identity: child.observe_init_metadata()?.host.proc_identity(),
            original_namespace: named_cgroup_ns(child)?,
            rooted_namespace: None,
        };
        *r.early.borrow_mut() = Some(binding);
        r.placement.set(Placement::MigrationInProgress);
        crate::production_selection::move_original_init_from_factory(
            child.board().pidfd(),
            child.board().pid_namespace(),
            payload,
        )?;
        child.board().revalidate()?;
        check_early_task_cgroup(child, &format!("{UNIT_CGROUP}/cell-u1000/payload"))?;
        require(
            read_pids(payload)? == BTreeSet::from([child.board().host_pid() as u32])
                && read_pids(keeper)?.is_empty(),
            "original init migration readback differs",
        )?;
        Ok(())
    }
    pub(crate) fn finish_early_placement(
        &self,
        child: &EarlyBaseAdmission<'_>,
        rooted: &File,
    ) -> Result<()> {
        let r = self.get();
        require(
            r.placement.get() == Placement::MigrationInProgress,
            "early payload placement required",
        )?;
        child
            .revalidate()
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        require(
            std::ptr::eq(r.admission.lease(), child.identity_lease()),
            "different early child reservation",
        )?;
        let mut existing = r.early.borrow_mut();
        let binding = existing
            .as_mut()
            .ok_or(CgroupError::Rejected("missing early placement"))?;
        require(
            binding.rooted_namespace.is_none()
                && NodeIdentity::of(&binding.pidfd)? == NodeIdentity::of(child.board().pidfd())?
                && binding.proc_identity == child.observe_init_metadata()?.host.proc_identity()
                && NodeIdentity::of(rooted)? != NodeIdentity::of(&binding.original_namespace)?
                && NodeIdentity::of(rooted)? == NodeIdentity::of(&named_cgroup_ns(child)?)?
                && unsafe { libc::ioctl(rooted.as_raw_fd(), NS_GET_NSTYPE) }
                    == libc::CLONE_NEWCGROUP
                && NodeIdentity::of(&kernel_owner(rooted)?)?
                    == NodeIdentity::of(child.user_namespace())?,
            "invalid original child's payload-rooted cgroup namespace",
        )?;
        let payload = &r
            .payload
            .as_ref()
            .ok_or(CgroupError::Rejected("payload absent"))?
            .file;
        let pid = child.board().host_pid() as u32;
        check_early_task_cgroup(child, &format!("{UNIT_CGROUP}/cell-u1000/payload"))?;
        require(
            read_pids(payload)? == BTreeSet::from([pid]) && list_directories(payload)?.is_empty(),
            "payload changed before cgroup delegation",
        )?;
        binding.rooted_namespace = Some(rooted.try_clone()?);
        drop(existing);
        r.placement.set(Placement::DelegationInProgress);
        let (uids, gids) = r.admission.lease().broker_ranges();
        require(
            uids.count >= 100000 && gids.count >= 100000,
            "full original ranges required",
        )?;
        let gid = gids
            .start
            .checked_add(1000)
            .ok_or(CgroupError::Rejected("mapped system group overflow"))?;
        for entry in &r.delegated_controls {
            let named = open_at(payload, entry.name, libc::O_RDONLY)?;
            require(
                NodeIdentity::of(&named)? == entry.identity
                    && NodeIdentity::of(&entry.file)? == entry.identity,
                "payload control changed",
            )?;
            change_owner_mode(&entry.file, uids.start, gid, 0o664)?;
        }
        change_owner_mode(payload, uids.start, gid, 0o775)?;
        self.check_delegation()?;
        mkdir_at(payload, c"init", 0o775)?;
        let leaf = Directory::at(payload, c"init")?;
        for name in DELEGATED_CONTROLS {
            change_owner_mode(
                &open_at(&leaf.file, name, libc::O_RDONLY)?,
                uids.start,
                gid,
                0o664,
            )?;
        }
        change_owner_mode(&leaf.file, uids.start, gid, 0o775)?;
        *r.guest_init.borrow_mut() = Some(leaf);
        let leaf = r.guest_init.borrow();
        let leaf = leaf
            .as_ref()
            .ok_or(CgroupError::Rejected("early guest leaf absent"))?;
        move_original_init(child.board().pid_namespace(), &leaf.file)?;
        check_early_task_cgroup(child, INIT_CGROUP_PATH)?;
        require(
            read_pids(&leaf.file)? == BTreeSet::from([pid]) && read_pids(payload)?.is_empty(),
            "early guest leaf migration differs",
        )?;
        write_control(
            payload,
            c"cgroup.subtree_control",
            "+cpu +cpuset +io +memory +pids",
        )?;
        check_activated_guest(payload, &leaf.file, uids.start, gid)?;
        let limit = available_snapshot_capacity()?;
        require(limit >= 3, "cgroup retirement descriptor headroom")?;
        for (name, value) in native_teardown_limits(limit) {
            write_control(&r.budget.file, name, &value.to_string())?;
        }
        check_native_teardown_limits(&r.budget.file, limit)?;
        r.native_descendant_limit.set(Some(limit));
        child.board().revalidate()?;
        r.placement.set(Placement::GuestActive);
        let result = self.revalidate();
        if result.is_err() {
            r.placement.set(Placement::ActivationInProgress);
        }
        result
    }
    pub(crate) fn revalidate_early_member(
        &self,
        child: &EarlyBaseAdmission<'_>,
        owner: &RuntimeMacOwner,
    ) -> Result<()> {
        self.revalidate()?;
        self.require_early_origin(child, owner)?;
        let r = self.get();
        require(
            r.placement.get() == Placement::GuestActive,
            "early payload is not active",
        )?;
        let retained = r.early.borrow();
        let binding = retained
            .as_ref()
            .ok_or(CgroupError::Rejected("missing original child placement"))?;
        let rooted = binding
            .rooted_namespace
            .as_ref()
            .ok_or(CgroupError::Rejected("missing payload cgroup namespace"))?;
        require(
            NodeIdentity::of(&binding.pidfd)? == NodeIdentity::of(child.board().pidfd())?
                && binding.proc_identity == child.observe_init_metadata()?.host.proc_identity()
                && NodeIdentity::of(rooted)? == NodeIdentity::of(&named_cgroup_ns(child)?)?,
            "early owner left its original cgroup namespace",
        )?;
        check_early_task_cgroup(child, INIT_CGROUP_PATH)?;
        child.board().revalidate()?;
        Ok(())
    }
    pub(crate) fn early_payload(
        &self,
        child: &EarlyBaseAdmission<'_>,
        owner: &RuntimeMacOwner,
    ) -> Result<File> {
        self.revalidate_early_member(child, owner)?;
        Ok(self
            .get()
            .payload
            .as_ref()
            .ok_or(CgroupError::Rejected("missing payload"))?
            .file
            .try_clone()?)
    }
}

impl PreparedCgroup {
    pub(crate) fn verify_early_exit(
        &self,
        board: &crate::production_selection::EarlyBoardResources,
    ) -> Result<()> {
        let r = self.get();
        let state = r.early.borrow();
        let binding = state
            .as_ref()
            .ok_or(CgroupError::Rejected("early budget has no captured init"))?;
        require(
            !r.retired.get()
                && NodeIdentity::of(&binding.pidfd)? == NodeIdentity::of(board.pidfd())?
                && r.admission.lease().host_uid() == board.selection().spec().host_uid
                && r.admission.lease().broker_cohort() == board.selection().base_cohort(),
            "different or already retired early Android owner",
        )?;
        crate::production_selection::early_generation::verify_exit(&binding.pidfd)?;
        r.unit_authority.check_after_android_exit(&r.unit.file)?;
        r.budget.check(&r.unit.file, &r.name)?;
        require(
            !populated(&r.budget.file)? && read_pids(&r.budget.file)?.is_empty(),
            "original Android budget remains populated",
        )
    }
    pub(crate) fn retire_early_empty(
        &self,
        board: &crate::production_selection::EarlyBoardResources,
    ) -> Result<()> {
        self.verify_early_exit(board)?;
        self.remove_empty_owned_hierarchy()?;
        self.get().retired.set(true);
        Ok(())
    }
}

impl PreparedCgroup {
    pub(crate) fn retire_early_unstarted(&self) -> Result<()> {
        require(
            self.get().early.borrow().is_none(),
            "cannot retire an attempted early migration as unstarted",
        )?;
        self.retire_unstarted()
    }
    pub(crate) fn attempted_original(
        &self,
        board: &crate::production_selection::EarlyBoardResources,
    ) -> Result<bool> {
        let stored = self.get().early.borrow();
        let Some(binding) = stored.as_ref() else {
            return Ok(false);
        };
        require(
            NodeIdentity::of(&binding.pidfd)? == NodeIdentity::of(board.pidfd())?,
            "another early process owns this migration",
        )?;
        Ok(true)
    }
}

#[cfg(test)]
mod early_kernel_control {
    use super::*;
    use std::{fs, os::fd::FromRawFd, path::PathBuf};
    struct Child {
        pid: i32,
        fd: File,
        reaped: bool,
    }
    impl Child {
        fn finish(&mut self) -> io::Result<()> {
            let r = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    self.fd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                )
            };
            if r < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH) {
                return Err(io::Error::last_os_error());
            }
            let mut status = 0;
            loop {
                let n = unsafe { libc::waitpid(self.pid, &mut status, 0) };
                if n == self.pid {
                    self.reaped = true;
                    return Ok(());
                }
                let e = io::Error::last_os_error();
                if e.kind() != io::ErrorKind::Interrupted {
                    return Err(e);
                }
            }
        }
    }
    impl Drop for Child {
        fn drop(&mut self) {
            if !self.reaped {
                let _ = self.finish();
            }
        }
    }
    #[test]
    #[ignore = "requires a dedicated root-owned transient systemd test unit and a real Linux PID namespace"]
    fn physical_migration_writes_pid_one_only_in_the_original_namespace() {
        let host_group =
            parse_unified_cgroup(&fs::read_to_string("/proc/self/cgroup").unwrap()).unwrap();
        assert!(
            host_group.starts_with("/system.slice/p4-r65-original-pid-placement-")
                && host_group.ends_with(".service/broker")
        );
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let unit = format!(
            "/sys/fs/cgroup{}",
            host_group.strip_suffix("/broker").unwrap()
        );
        let target = PathBuf::from(&unit).join("probe-leaf");
        fs::create_dir(&target).unwrap();
        let leaf = File::open(&target).unwrap();
        let mut fd = -1_i32;
        let mut args = [0u64; 11];
        args[0] = (libc::CLONE_NEWPID | libc::CLONE_PIDFD) as u64;
        args[1] = (&mut fd as *mut i32) as usize as u64;
        args[4] = libc::SIGCHLD as u64;
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                args.as_ptr(),
                std::mem::size_of_val(&args),
            ) as i32
        };
        assert!(pid >= 0, "{}", io::Error::last_os_error());
        if pid == 0 {
            unsafe {
                if libc::getpid() != 1 {
                    libc::_exit(71);
                }
                loop {
                    libc::pause();
                }
            }
        }
        let mut child = Child {
            pid,
            fd: unsafe { File::from_raw_fd(fd) },
            reaped: false,
        };
        let proc_dir = File::open(format!("/proc/{pid}")).unwrap();
        let ns = File::open(format!("/proc/{pid}/ns/pid")).unwrap();
        let global = File::open("/proc/self/ns/pid").unwrap();
        assert_ne!(
            NodeIdentity::of(&global).unwrap(),
            NodeIdentity::of(&ns).unwrap()
        );
        let nspid = fs::read_to_string(format!("/proc/{pid}/status")).unwrap();
        let ids: Vec<_> = nspid
            .lines()
            .find_map(|l| l.strip_prefix("NSpid:"))
            .unwrap()
            .split_ascii_whitespace()
            .collect();
        assert_eq!(ids.last(), Some(&"1"));
        check_task_cgroup(&proc_dir, &host_group).unwrap();
        assert!(move_original_init(&proc_dir, &leaf).is_err());
        assert!(read_pids(&leaf).unwrap().is_empty());
        move_original_init(&ns, &leaf).unwrap();
        check_task_cgroup(
            &proc_dir,
            &format!("{}/probe-leaf", host_group.strip_suffix("/broker").unwrap()),
        )
        .unwrap();
        assert_eq!(read_pids(&leaf).unwrap(), BTreeSet::from([pid as u32]));
        let own = fs::read_to_string("/proc/self/cgroup").unwrap();
        assert_eq!(parse_unified_cgroup(&own).unwrap(), host_group);
        eprintln!(
            "original outer pid={pid}, nested PID=1, kernel cgroup inode={}, original PID namespace inode={}",
            leaf.metadata().unwrap().ino(),
            ns.metadata().unwrap().ino()
        );
        child.finish().unwrap();
        assert!(move_original_init(&ns, &leaf).is_err());
        assert!(read_pids(&leaf).unwrap().is_empty());
        drop(leaf);
        fs::remove_dir(&target).unwrap();
    }
}
