//! Original CP3A init's three fixed tmpfs mount requests. The notification,
//! original single task, native memory and deadline remain held through the
//! real helper operation and its response; no caller path or errno is trusted.
use super::*;
use crate::production_runtime_assets::{ActivationRootRole, OriginalInitMount};

const ORIGINAL_OPTIONS: &[u8] = b"mode=0755,uid=0,gid=0\0";

fn fixed_string(memory: &File, address: u64, expected: &[u8]) -> Result<()> {
    if address == 0
        || expected.is_empty()
        || expected.len() > 64
        || !expected.ends_with(b"\0")
        || address > (i64::MAX as u64).saturating_sub(expected.len() as u64)
    {
        return Err(NamespaceError::Rejected(
            "bounded original mount string pointer",
        ));
    }
    let mut bytes = [0_u8; 64];
    let mut at = 0;
    while at < expected.len() {
        let count = memory.read_at(&mut bytes[at..expected.len()], address + at as u64)?;
        if count == 0 {
            return Err(NamespaceError::Rejected("incomplete original mount string"));
        }
        at += count;
    }
    if &bytes[..expected.len()] != expected {
        return Err(NamespaceError::Rejected(
            "original mount string differs from pinned init",
        ));
    }
    Ok(())
}

fn target_role(memory: &File, address: u64) -> Result<ActivationRootRole> {
    const MAX: usize = b"/bootstrap-apex\0".len();
    if address == 0 || address > (i64::MAX as u64).saturating_sub(MAX as u64) {
        return Err(NamespaceError::Rejected(
            "bounded original mount target pointer",
        ));
    }
    let mut bytes = [0_u8; MAX];
    let mut at = 0;
    while at < MAX {
        let count = memory.read_at(&mut bytes[at..], address + at as u64)?;
        if count == 0 {
            return Err(NamespaceError::Rejected("incomplete original mount target"));
        }
        at += count;
        if let Some(end) = bytes[..at].iter().position(|v| *v == 0) {
            return match &bytes[..end] {
                b"/apex" => Ok(ActivationRootRole::Apex),
                b"/bootstrap-apex" => Ok(ActivationRootRole::BootstrapApex),
                b"/linkerconfig" => Ok(ActivationRootRole::Linkerconfig),
                _ => Err(NamespaceError::Rejected(
                    "original mount target is outside fixed roots",
                )),
            };
        }
    }
    Err(NamespaceError::Rejected(
        "unterminated original mount target",
    ))
}

fn original_mount_arguments(memory: &File, args: &[u64; 6]) -> Result<ActivationRootRole> {
    if args[3] != 0x0e {
        return Err(NamespaceError::Rejected(
            "original tmpfs mount flags differ",
        ));
    }
    fixed_string(memory, args[0], b"tmpfs\0")?;
    fixed_string(memory, args[2], b"tmpfs\0")?;
    fixed_string(memory, args[4], ORIGINAL_OPTIONS)?;
    target_role(memory, args[1])
}

pub(crate) struct OriginalInitTmpfsRequest<'a> {
    transport: RefMut<'a, Transport>,
    child: &'a TreeChild,
    notification: wire::Notification,
    memory: File,
    memory_node: Node,
    generation: ExecutedInitGeneration,
    role: ActivationRootRole,
    deadline: Instant,
}

impl InheritedNotifications {
    pub(crate) fn original_init_tmpfs<'a>(
        &'a self,
        child: &'a TreeChild,
        init: &ExecutedInitWitness<'_>,
        end: Instant,
    ) -> Result<OriginalInitTmpfsRequest<'a>> {
        self.revalidate(child)?;
        init.revalidate_capability_contract()?;
        if init.host_pid() != child.identity.pid || Instant::now() >= end {
            return Err(NamespaceError::Rejected(
                "original tmpfs request owner/deadline",
            ));
        }
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("original notification already borrowed"))?;
        let notification = transport.receive(end)?;
        if notification.pid != child.identity.pid
            || notification.operation() != Some(wire::Operation::Mount)
        {
            return Err(NamespaceError::Rejected(
                "only original init's native mount request",
            ));
        }
        let raw = unsafe {
            libc::openat(
                child.proc_dir.as_raw_fd(),
                c"mem".as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let memory = unsafe { File::from_raw_fd(raw) };
        if filesystem_kind(&memory)? != PROC_MAGIC {
            return Err(NamespaceError::Rejected(
                "original mount memory is not held procfs",
            ));
        }
        let memory_node = Node::of(&memory)?;
        transport.valid(&notification)?;
        let role = original_mount_arguments(&memory, &notification.data.args)?;
        let value = OriginalInitTmpfsRequest {
            transport,
            child,
            notification,
            memory,
            memory_node,
            generation: init.generation()?,
            role,
            deadline: end,
        };
        value.revalidate(init)?;
        Ok(value)
    }
}

impl OriginalInitTmpfsRequest<'_> {
    pub(crate) fn role(&self) -> ActivationRootRole {
        self.role
    }
    pub(crate) fn notification(&self) -> wire::Notification {
        self.notification
    }
    pub(crate) fn generation(&self) -> ExecutedInitGeneration {
        self.generation
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }

    pub(crate) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected("original tmpfs request deadline"));
        }
        init.revalidate_capability_contract()?;
        self.child.verify()?;
        if init.host_pid() != self.child.identity.pid
            || init.generation()? != self.generation
            || self.notification.pid != self.child.identity.pid
            || self.notification.operation() != Some(wire::Operation::Mount)
            || self.transport.pending != Some(self.notification)
            || self.transport.failed
            || Node::of(&self.memory)? != self.memory_node
        {
            return Err(NamespaceError::Rejected(
                "original pending tmpfs request identity changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        original_single_process(&self.child.proc_dir, self.child.identity.pid)?;
        self.transport.valid(&self.notification)?;
        if original_mount_arguments(&self.memory, &self.notification.data.args)? != self.role {
            return Err(NamespaceError::Rejected(
                "original tmpfs request changed in memory",
            ));
        }
        self.transport.valid(&self.notification)?;
        init.revalidate()?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "original tmpfs observation exceeded deadline",
            ));
        }
        Ok(())
    }

    pub(crate) fn complete(
        mut self,
        init: &ExecutedInitWitness<'_>,
        completed: &OriginalInitMount,
    ) -> Result<()> {
        self.revalidate(init)?;
        let errno = completed
            .actual_errno(init, &self)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.revalidate(init)?;
        let response = wire::Response {
            id: self.notification.id,
            value: 0,
            error: -errno,
            flags: 0,
        };
        self.transport.failed = true;
        if unsafe { libc::ioctl(self.transport.file.as_raw_fd(), wire::SEND, &response) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        self.transport.pending.take();
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "actual tmpfs reply exceeded original deadline",
            ));
        }
        self.transport.failed = false;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(role: ActivationRootRole) -> (File, [u64; 6]) {
        let file = tempfile::tempfile().unwrap();
        file.write_all_at(b"tmpfs\0", 64).unwrap();
        file.write_all_at(format!("{}\0", role.target()).as_bytes(), 128)
            .unwrap();
        file.write_all_at(b"tmpfs\0", 192).unwrap();
        file.write_all_at(ORIGINAL_OPTIONS, 256).unwrap();
        (file, [64, 128, 192, 0x0e, 256, 0])
    }

    #[test]
    fn original_init_tmpfs_memory_reads_exact_three_targets_options_and_flags() {
        for role in [
            ActivationRootRole::Apex,
            ActivationRootRole::BootstrapApex,
            ActivationRootRole::Linkerconfig,
        ] {
            let (file, args) = fixture(role);
            assert_eq!(original_mount_arguments(&file, &args).unwrap(), role);
            for flags in [0, 1, 2, 4, 8, 0x0f, 0x100e] {
                let mut changed = args;
                changed[3] = flags;
                assert!(original_mount_arguments(&file, &changed).is_err());
            }
            for index in [0, 1, 2, 4] {
                for address in [0, i64::MAX as u64, u64::MAX, 8192] {
                    let mut changed = args;
                    changed[index] = address;
                    assert!(original_mount_arguments(&file, &changed).is_err());
                }
            }
        }
    }

    #[test]
    fn original_init_tmpfs_memory_rejects_foreign_sources_paths_and_options() {
        for (at, wrong) in [
            (64, b"ext4\0".as_slice()),
            (128, b"//apex\0"),
            (128, b"/apex/../linkerconfig\0"),
            (128, b"/vendor\0"),
            (192, b"ramfs\0"),
            (256, b"mode=0777,uid=0,gid=0\0"),
            (256, b"mode=0755,uid=1,gid=0\0"),
            (256, b"mode=0755,uid=0,gid=1\0"),
        ] {
            let (file, args) = fixture(ActivationRootRole::Apex);
            file.write_all_at(wrong, at).unwrap();
            assert!(
                original_mount_arguments(&file, &args).is_err(),
                "{at}: {wrong:?}"
            );
        }
        let (file, args) = fixture(ActivationRootRole::BootstrapApex);
        file.write_all_at(b"/bootstrap-apexX", 128).unwrap();
        assert!(original_mount_arguments(&file, &args).is_err());
    }
}
