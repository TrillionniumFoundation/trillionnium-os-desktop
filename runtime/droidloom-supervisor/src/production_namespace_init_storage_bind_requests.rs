//! Original CP3A storage bind/slave/shared calls, with the notification and native
//! memory retained through the real helper operation and exact response.
use super::*;
use crate::production_runtime_assets::{OriginalInitStorageBind, OriginalInitStorageBindKind};

fn original_path(memory: &File, address: u64) -> Result<Vec<u8>> {
    const MAX: usize = b"/mnt/androidwritable\0".len();
    if address == 0 || address > (i64::MAX as u64).saturating_sub(MAX as u64) {
        return Err(NamespaceError::Rejected(
            "bounded original storage pathname",
        ));
    }
    let mut bytes = Vec::with_capacity(MAX);
    for offset in 0..MAX {
        let mut byte = [0_u8; 1];
        if memory.read_at(&mut byte, address + offset as u64)? != 1 {
            return Err(NamespaceError::Rejected(
                "incomplete original storage pathname",
            ));
        }
        if byte[0] == 0 {
            return Ok(bytes);
        }
        bytes.push(byte[0]);
    }
    Err(NamespaceError::Rejected(
        "unterminated original storage pathname",
    ))
}

fn original_storage_bind_arguments(
    memory: &File,
    args: &[u64; 6],
) -> Result<OriginalInitStorageBindKind> {
    if args[2] != 0 || args[4] != 0 {
        return Err(NamespaceError::Rejected(
            "original storage bind type/data must be null",
        ));
    }
    let target = original_path(memory, args[1])?;
    let kind = OriginalInitStorageBindKind::ALL
        .into_iter()
        .find(|kind| kind.target().to_bytes() == target && kind.flags() == args[3])
        .ok_or(NamespaceError::Rejected(
            "foreign storage target or mount flags",
        ))?;
    if kind.is_bind() {
        if original_path(memory, args[0])? != b"/mnt/user" {
            return Err(NamespaceError::Rejected(
                "original storage bind source differs",
            ));
        }
    } else if args[0] != 0 {
        return Err(NamespaceError::Rejected(
            "original storage propagation source must be null",
        ));
    }
    Ok(kind)
}

pub(crate) struct OriginalInitStorageBindRequest<'a> {
    transport: RefMut<'a, Transport>,
    child: &'a TreeChild,
    mount_owner: OwnedNamespaceWitness<'a>,
    mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'a>,
    notification: wire::Notification,
    memory: File,
    memory_node: Node,
    generation: ExecutedInitGeneration,
    kind: OriginalInitStorageBindKind,
    deadline: Instant,
}

impl InheritedNotifications {
    pub(crate) fn original_init_storage_bind<'a>(
        &'a self,
        child: &'a TreeChild,
        init: &ExecutedInitWitness<'_>,
        end: Instant,
        mount_owner: OwnedNamespaceWitness<'a>,
        mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'a>,
    ) -> Result<OriginalInitStorageBindRequest<'a>> {
        self.revalidate(child)?;
        init.revalidate_capability_contract()?;
        if init.host_pid() != child.identity.pid || Instant::now() >= end {
            return Err(NamespaceError::Rejected(
                "original storage bind request owner/deadline",
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
        let kind = original_storage_bind_arguments(&memory, &notification.data.args)?;
        let value = OriginalInitStorageBindRequest {
            transport,
            child,
            mount_owner,
            mount_actors,
            notification,
            memory,
            memory_node,
            generation: init.generation()?,
            kind,
            deadline: end,
        };
        value.revalidate(init)?;
        Ok(value)
    }
}

impl OriginalInitStorageBindRequest<'_> {
    pub(crate) fn kind(&self) -> OriginalInitStorageBindKind {
        self.kind
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
            return Err(NamespaceError::Rejected(
                "original storage bind request deadline",
            ));
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
                "original pending storage bind request identity changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        self.mount_actors
            .revalidate(&self.mount_owner)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.transport
            .original_mount_barrier(self.child, &self.notification)?;
        self.transport.valid(&self.notification)?;
        if original_storage_bind_arguments(&self.memory, &self.notification.data.args)? != self.kind
        {
            return Err(NamespaceError::Rejected(
                "original storage bind request changed in memory",
            ));
        }
        self.transport.valid(&self.notification)?;
        init.revalidate()?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "original storage bind observation exceeded deadline",
            ));
        }
        Ok(())
    }

    pub(crate) fn complete(
        mut self,
        init: &ExecutedInitWitness<'_>,
        completed: &OriginalInitStorageBind,
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
                "actual storage bind reply exceeded original deadline",
            ));
        }
        self.transport.failed = false;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(kind: OriginalInitStorageBindKind) -> (File, [u64; 6]) {
        let file = tempfile::tempfile().unwrap();
        file.write_all_at(kind.target().to_bytes_with_nul(), 64)
            .unwrap();
        file.write_all_at(b"/mnt/user\0", 128).unwrap();
        (
            file,
            [
                if kind.is_bind() { 128 } else { 0 },
                64,
                0,
                kind.flags(),
                0,
                0,
            ],
        )
    }

    #[test]
    fn original_storage_bind_requests_read_all_six_exact_native_argument_sets() {
        for kind in OriginalInitStorageBindKind::ALL {
            let (file, args) = fixture(kind);
            assert_eq!(original_storage_bind_arguments(&file, &args).unwrap(), kind);
            for index in [2, 4] {
                let mut wrong = args;
                wrong[index] = 128;
                assert!(original_storage_bind_arguments(&file, &wrong).is_err());
            }
            for flag in [
                0, 0x1000, 0x4000, 0x5001, 0x40000, 0x104000, 0x84000, 0x80000000,
            ] {
                let mut wrong = args;
                wrong[3] = flag;
                assert!(original_storage_bind_arguments(&file, &wrong).is_err());
            }
            let mut wrong = args;
            wrong[0] = if kind.is_bind() { 0 } else { 128 };
            assert!(original_storage_bind_arguments(&file, &wrong).is_err());
        }
    }

    #[test]
    fn original_storage_bind_memory_rejects_foreign_sources_targets_and_unbounded_reads() {
        for kind in OriginalInitStorageBindKind::ALL {
            let (file, args) = fixture(kind);
            for address in [0, 8192, i64::MAX as u64, u64::MAX] {
                let mut wrong = args;
                wrong[1] = address;
                assert!(original_storage_bind_arguments(&file, &wrong).is_err());
            }
            for path in [
                b"//mnt/installer\0".as_slice(),
                b"/mnt/installer/..\0",
                b"/mnt/user\0",
                b"/mnt/androidwritabX\0",
            ] {
                let (file, args) = fixture(kind);
                file.write_all_at(path, 64).unwrap();
                assert!(original_storage_bind_arguments(&file, &args).is_err());
            }
            if kind.is_bind() {
                for path in [
                    b"/mnt\0".as_slice(),
                    b"//mnt/user\0",
                    b"/mnt/user/..\0",
                    b"/vendor\0",
                ] {
                    let (file, args) = fixture(kind);
                    file.write_all_at(path, 128).unwrap();
                    assert!(original_storage_bind_arguments(&file, &args).is_err());
                }
            }
        }
    }
}
