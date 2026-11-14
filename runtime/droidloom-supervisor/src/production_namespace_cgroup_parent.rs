//! Same-owner cgroup phase44/45. Preparation and readiness are distinct.
use super::*;

impl IsolatedNamespaces {
    pub(crate) fn configure_cgroup_hierarchy(&self) -> Result<()> {
        self.verify_live_admission()?;
        if self.writable_proc.is_none() || self.runtime.is_some() {
            return Err(NamespaceError::Rejected("guest cgroup activation requires the writable-proc barrier before runtime"));
        }
        let r = self.keeper.as_ref().ok_or(NamespaceError::RetirementUnproven)?.owner.held()?;
        let witness = CgroupTreeReadyWitness { tree: self };
        let child = self.init.as_ref().ok_or(NamespaceError::RetirementUnproven)?;
        match &r.authority {
            HeldAuthority::Budgeted(cgroup) => {
                cgroup.move_keeper_outside(&witness)
                    .map_err(|e| NamespaceError::CgroupResource(e.to_string()))?;
                cgroup.delegate_guest_hierarchy(&witness)
                    .map_err(|e| NamespaceError::CgroupResource(e.to_string()))?;
                // A failed/unknown send retains ActivationInProgress and all
                // original custody. It cannot be retried with another FD.
                let held = cgroup.begin_guest_activation(&witness)
                    .map_err(|e| NamespaceError::CgroupResource(e.to_string()))?;
                send_base_fds(child.control.as_raw_fd(),
                    &Packet::new(child.nonce, Phase::PrepareCgroup, 0, child.parent_pid),
                    [held[0].as_fd(), held[1].as_fd()])?;
                child.receive_phase(Phase::CgroupReady)?;
                cgroup.finish_guest_activation(&witness)
                    .map_err(|e| NamespaceError::CgroupResource(e.to_string()))?;
                self.require_cgroup_hierarchy_ready()?;
                self.verify_live_admission()
            }
            #[cfg(test)]
            _ => Err(NamespaceError::HostAdmissionRequired),
        }
    }

    pub(super) fn require_cgroup_hierarchy_ready(&self) -> Result<()> {
        let r = self.keeper.as_ref().ok_or(NamespaceError::RetirementUnproven)?.owner.held()?;
        let witness = CgroupTreeReadyWitness { tree: self };
        match &r.authority {
            HeldAuthority::Budgeted(cgroup) => cgroup.require_guest_active(&witness)
                .map_err(|e| NamespaceError::CgroupResource(e.to_string())),
            #[cfg(test)]
            _ => Err(NamespaceError::HostAdmissionRequired),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::production_cgroup::private_control::PrivateCgroup;
    use crate::production_identity::tests::broker_fixture;
    use std::fs;

    fn children() -> String {
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        fs::read_to_string(format!("/proc/self/task/{tid}/children")).unwrap()
    }

    fn lease_available(root: &std::path::Path) -> bool {
        let file = OpenOptions::new().read(true).write(true)
            .open(root.join("registry/u1000.lease")).unwrap();
        let rc = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if rc == 0 {
            assert_eq!(unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_UN) }, 0);
            true
        } else {
            assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
            false
        }
    }

    #[test]
    #[ignore = "requires reviewed initial-root VM with cgroup2 and four root controllers; no Android execution"]
    fn privileged_private_cgroup_activation_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let original_cgroup = fs::read("/proc/self/cgroup").unwrap();
        let maps = [fs::read("/proc/self/uid_map").unwrap(), fs::read("/proc/self/gid_map").unwrap()];
        let namespaces = || {
            ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"].map(|name| {
                Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap()
            })
        };
        let original_namespaces = namespaces();
        for kind in ["valid", "wrong_nonce", "wrong_phase", "no_fd", "one_fd",
            "duplicate_fd", "regular_fd", "missing_controller"] {
            let mut fixture = PrivateCgroup::prepare().unwrap();
            let (identity_root, lease) = broker_fixture();
            let mut owner = Owner::spawn(Some(lease), child::Mode::CgroupControl).unwrap();
            fixture.place_created_keeper(&OwnedNamespaceWitness { owner: &owner, tree: None }).unwrap();
            // Test-only setup records the same original directory custody.
            // Production supplies it atomically through CLONE_INTO_CGROUP.
            owner.held_mut().unwrap().clone_target = Some(fixture.payload().try_clone().unwrap());
            owner.enter_userns().unwrap();
            let (uids, gids) = owner.install_maps().unwrap();
            owner.mapped_go(uids, gids).unwrap();
            let tree = IsolatedNamespaces::from_mapped(MappedUserNamespace { owner }).unwrap();
            let child = tree.init.as_ref().unwrap();
            let uid = child.uids.start;
            let gid = child.gids.start.checked_add(1000).unwrap();
            fixture.delegate(&CgroupTreeReadyWitness { tree: &tree }, uid, gid).unwrap();
            if kind == "missing_controller" { fixture.withhold_controller().unwrap(); }
            let mut nonce = child.nonce;
            if kind == "wrong_nonce" { nonce[0] ^= 1; }
            let phase = if kind == "wrong_phase" { Phase::MountRuntime } else { Phase::PrepareCgroup };
            let packet = Packet::new(nonce, phase, 0, child.parent_pid);
            let unrelated = File::open("/dev/null").unwrap();
            match kind {
                "no_fd" => send_packet(child.control.as_raw_fd(), &packet).unwrap(),
                "one_fd" => send_one_fd(child.control.as_raw_fd(), &packet, fixture.payload().as_fd()).unwrap(),
                "duplicate_fd" => send_base_fds(child.control.as_raw_fd(), &packet,
                    [fixture.payload().as_fd(), fixture.payload().as_fd()]).unwrap(),
                "regular_fd" => send_base_fds(child.control.as_raw_fd(), &packet,
                    [fixture.payload().as_fd(), unrelated.as_fd()]).unwrap(),
                _ => send_base_fds(child.control.as_raw_fd(), &packet,
                    [fixture.payload().as_fd(), fixture.init().as_fd()]).unwrap(),
            }
            let ready = child.receive_phase(Phase::CgroupReady);
            if kind == "valid" {
                ready.unwrap();
                fixture.verify_active(&CgroupTreeReadyWitness { tree: &tree }, uid, gid).unwrap();
                assert!(matches!(tree.require_cgroup_hierarchy_ready(), Err(NamespaceError::HostAdmissionRequired)));
            } else {
                assert!(ready.is_err(), "negative case {kind} produced READY");
                fixture.verify_not_activated().unwrap();
            }
            assert!(!lease_available(identity_root.path()));
            let exit = tree.retire().unwrap();
            assert_eq!(exit.init.reason, libc::CLD_EXITED);
            assert_eq!(exit.init.status, if kind == "valid" { 0 } else { 127 });
            assert_eq!((exit.keeper.reason, exit.keeper.status), (libc::CLD_EXITED, 0));
            fixture.retire().unwrap();
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            assert_eq!(fs::read("/proc/self/cgroup").unwrap(), original_cgroup);
            assert_eq!(fs::read("/proc/self/uid_map").unwrap(), maps[0]);
            assert_eq!(fs::read("/proc/self/gid_map").unwrap(), maps[1]);
            assert_eq!(namespaces(), original_namespaces);
            println!("private cgroup phase44/45 {kind}: exact owned PID1/namespace, controller readback, unchanged hard budget, PIDFD reap and original subtree retirement; execution_admitted=false Android=0");
        }
    }
}
