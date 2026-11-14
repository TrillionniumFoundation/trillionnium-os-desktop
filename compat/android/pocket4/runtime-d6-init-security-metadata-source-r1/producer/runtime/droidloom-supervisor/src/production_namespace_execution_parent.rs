//! Parent-side Android exec and readiness observation. Preparation does not
//! construct this type: the same owned child must pass the final admission,
//! authenticated ExecArmed, control CLOEXEC and actual executable checks.
use super::*;
use crate::production_execution::ExecutionAdmission;
use crate::production_readiness::{BootProperty, ReadinessError, read_boot_complete};
use crate::production_selection::ProductionSelection;
use std::ffi::CStr;

const BOOT_PROPERTY: &CStr = c"u:object_r:boot_status_prop:s0";
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;

pub(crate) struct ExecutedNamespaces {
    tree: IsolatedNamespaces,
}

/// A borrow of one actually executed, live and ready tree. No caller can
/// construct it from a PID, a property value, a digest or a test declaration.
pub(crate) struct ReadyTreeWitness<'a> {
    owner: &'a ExecutedNamespaces,
}

impl ReadyTreeWitness<'_> {
    pub(crate) fn host_uid(&self) -> Result<u32> {
        Ok(self.owner.tree.witness()?.identity_lease()?.host_uid())
    }
}

fn fixed_at(parent: &File, name: &CStr, directory: bool, body: bool) -> Result<File> {
    let flags = libc::O_CLOEXEC
        | libc::O_NOFOLLOW
        | libc::O_NONBLOCK
        | if body { libc::O_RDONLY } else { libc::O_PATH }
        | if directory { libc::O_DIRECTORY } else { 0 };
    let fd = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags) };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    if file.metadata()?.mode() & libc::S_IFMT == libc::S_IFLNK {
        return Err(NamespaceError::Rejected(
            "production property path is a symlink",
        ));
    }
    Ok(file)
}

fn executable(child: &TreeChild) -> Result<File> {
    child.verify()?;
    // The sole intentional proc magic-link follow. It is relative to the
    // original held proc directory, then compared to the already held init
    // inode. O_NOFOLLOW here would incorrectly inspect the proc symlink itself.
    let fd = unsafe {
        libc::openat(
            child.proc_dir.as_raw_fd(),
            c"exe".as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    child.verify()?;
    Ok(file)
}

fn exec_failed_record(child: &TreeChild) -> Result<()> {
    let (packet, peer) = receive_packet(child.control.as_raw_fd())?;
    if !packet.matches(child.nonce, 1)
        || peer.pid != child.identity.pid as i32
        || peer.uid != child.uids.start
        || peer.gid != child.gids.start
    {
        return Err(NamespaceError::Rejected(
            "exec failure original nonce/SCM peer differs",
        ));
    }
    if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
        return Err(io::Error::from_raw_os_error(packet.errno).into());
    }
    Err(NamespaceError::Rejected(
        "unexpected record after ExecArmed",
    ))
}

fn wait_exec_cloexec(child: &TreeChild) -> Result<()> {
    let deadline = Instant::now() + PROTOCOL_TIMEOUT;
    loop {
        if pidfd_exited(&child.pidfd)? {
            // A real EOF caused by process death is not evidence of exec.
            return Err(NamespaceError::Rejected(
                "owned init exited before exec observation",
            ));
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(NamespaceError::Rejected("owned exec CLOEXEC deadline"));
        }
        let mut fds = [
            libc::pollfd {
                fd: child.control.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: child.pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let ms = remaining.as_millis().max(1).min(i32::MAX as u128) as i32;
        let rc = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, ms) };
        if rc < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        if rc == 0 {
            continue;
        }
        if fds.iter().any(|fd| fd.revents & libc::POLLNVAL != 0) {
            return Err(NamespaceError::Rejected(
                "owned exec descriptor became invalid",
            ));
        }
        if fds[0].revents & (libc::POLLIN | libc::POLLHUP | libc::POLLERR) != 0 {
            let mut byte = [0_u8; 1];
            let n = unsafe {
                libc::recv(
                    child.control.as_raw_fd(),
                    byte.as_mut_ptr().cast(),
                    1,
                    libc::MSG_PEEK | libc::MSG_DONTWAIT,
                )
            };
            if n == 0 {
                child.verify()?;
                return Ok(());
            }
            if n > 0 {
                return exec_failed_record(child);
            }
            let error = io::Error::last_os_error();
            if matches!(error.raw_os_error(), Some(libc::EINTR | libc::EAGAIN)) {
                continue;
            }
            return Err(error.into());
        }
    }
}

impl IsolatedNamespaces {
    pub(crate) fn execute_runtime(
        mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<ExecutedNamespaces> {
        admission
            .revalidate_tree(selection, &self.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.verify_live_admission()?;
        let child = self
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        self.runtime_observation
            .as_mut()
            .ok_or(NamespaceError::Rejected("no prepared same-cohort runtime"))?
            .verify(child)?;
        send_packet(
            child.control.as_raw_fd(),
            &Packet::new(child.nonce, Phase::ExecInit, 0, child.parent_pid),
        )?;
        child.receive_phase(Phase::ExecArmed)?;
        wait_exec_cloexec(child)?;
        let target = executable(child)?;
        self.runtime_observation
            .as_ref()
            .unwrap()
            .verify_executable_target(&target)?;
        drop(target);
        admission
            .revalidate_tree(selection, &self.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        // No additional mount/root/namespace FD is held outside the tree's
        // existing retirement machinery. The observation above is transient.
        Ok(ExecutedNamespaces { tree: self })
    }
}

impl ExecutedNamespaces {
    pub(crate) fn host_pid(&self) -> u32 {
        // Display only. This value is never fed back to a constructor, signal,
        // map write, namespace entry or Android command implementation.
        self.tree
            .init
            .as_ref()
            .expect("executed owner holds init")
            .identity
            .pid
    }

    pub(crate) fn termination_observed(&self) -> Result<bool> {
        let keeper = self
            .tree
            .keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let resources = keeper.owner.held()?;
        if unsafe { libc::syscall(libc::SYS_gettid) } != libc::c_long::from(resources.creator_tid) {
            return Err(NamespaceError::Rejected("executed owner moved threads"));
        }
        let init = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        Ok(pidfd_exited(&init.pidfd)? || pidfd_exited(&resources.pidfd)?)
    }

    fn verify_exec(
        &mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<()> {
        admission
            .revalidate_tree(selection, &self.tree.witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        let child = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        child.verify()?;
        let target = executable(child)?;
        let runtime = self
            .tree
            .runtime_observation
            .as_mut()
            .ok_or(NamespaceError::Rejected("executed runtime custody absent"))?;
        runtime.verify_executable_target(&target)?;
        drop(target);
        // An unexpected namespace or mount transition is rejected. Stock
        // init's required transitions need their own reviewed typed adapter;
        // this observer does not adopt a new numeric PID or namespace FD.
        runtime.verify(child)
    }

    pub(crate) fn readiness(
        &mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<BootProperty> {
        self.verify_exec(selection, admission)?;
        let child = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        let value = (|| -> Result<BootProperty> {
            let root = held_child_root(child)?;
            let dev = fixed_at(&root, c"dev", true, false)?;
            if Some(Node::of(&dev)?) != self.tree.device_node
                || filesystem_kind(&dev)? != TMPFS_MAGIC
            {
                return Err(NamespaceError::Rejected(
                    "property DEV differs from owned private mount",
                ));
            }
            let property_dir = fixed_at(&dev, c"__properties__", true, false)?;
            let metadata = property_dir.metadata()?;
            if metadata.uid() != child.uids.start
                || metadata.gid() != child.gids.start
                || metadata.mode() & 0o6022 != 0
                || filesystem_kind(&property_dir)? != TMPFS_MAGIC
            {
                return Err(NamespaceError::Rejected(
                    "private property directory custody",
                ));
            }
            let file = fixed_at(&property_dir, BOOT_PROPERTY, false, true)?;
            if filesystem_kind(&file)? != TMPFS_MAGIC {
                return Err(NamespaceError::Rejected("property area filesystem differs"));
            }
            match read_boot_complete(&file, child.uids.start, child.gids.start) {
                Ok(value) => Ok(value),
                Err(ReadinessError::Changed) => Ok(BootProperty::Updating),
                Err(error) => Err(NamespaceError::RuntimeResource(error.to_string())),
            }
        })();
        let value = match value {
            Err(NamespaceError::Io(error)) if error.kind() == io::ErrorKind::NotFound => {
                BootProperty::Absent
            }
            other => other?,
        };
        self.verify_exec(selection, admission)?;
        Ok(value)
    }

    pub(crate) fn ready_witness<'a>(
        &'a mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<Option<ReadyTreeWitness<'a>>> {
        if self.readiness(selection, admission)? == BootProperty::Complete {
            Ok(Some(ReadyTreeWitness { owner: self }))
        } else {
            Ok(None)
        }
    }

    pub(crate) fn retire(self) -> Result<TreeExit> {
        self.tree.retire()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_exec_property_walk_rejects_actual_directory_and_leaf_symlinks() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::create_dir(temp.path().join("real")).unwrap();
        std::fs::write(temp.path().join("real/value"), b"property").unwrap();
        std::os::unix::fs::symlink("real", temp.path().join("alias")).unwrap();
        std::os::unix::fs::symlink("value", temp.path().join("real/alias")).unwrap();
        let root = File::open(temp.path()).unwrap();
        assert!(fixed_at(&root, c"alias", true, false).is_err());
        let real = fixed_at(&root, c"real", true, false).unwrap();
        assert!(fixed_at(&real, c"alias", false, true).is_err());
        assert_eq!(
            fixed_at(&real, c"value", false, true)
                .unwrap()
                .metadata()
                .unwrap()
                .len(),
            8
        );
    }
}
