//! Original CP3A propagation calls, with the actual notification and native
//! memory retained through the real helper operation and exact response.
use super::*;
use crate::production_runtime_assets::{OriginalInitPropagation, OriginalInitPropagationKind};

fn original_propagation_arguments(
    memory: &File,
    args: &[u64; 6],
) -> Result<OriginalInitPropagationKind> {
    const MAX: usize = b"/linkerconfig\0".len();
    if args[0] != 0
        || args[2] != 0
        || args[4] != 0
        || args[1] == 0
        || args[1] > (i64::MAX as u64).saturating_sub(MAX as u64)
    {
        return Err(NamespaceError::Rejected(
            "original propagation requires null source/type/data and bounded target",
        ));
    }
    let mut bytes = [0_u8; MAX];
    let mut at = 0;
    while at < MAX {
        let count = memory.read_at(&mut bytes[at..], args[1] + at as u64)?;
        if count == 0 {
            return Err(NamespaceError::Rejected(
                "incomplete original propagation target",
            ));
        }
        at += count;
        if let Some(end) = bytes[..at].iter().position(|v| *v == 0) {
            let kind = match &bytes[..end] {
                b"/" => OriginalInitPropagationKind::RootShared,
                b"/apex" => OriginalInitPropagationKind::ApexPrivate,
                b"/linkerconfig" => OriginalInitPropagationKind::LinkerconfigPrivate,
                _ => return Err(NamespaceError::Rejected("foreign propagation target")),
            };
            if args[3] != kind.flags() {
                return Err(NamespaceError::Rejected(
                    "original propagation flags differ",
                ));
            }
            return Ok(kind);
        }
    }
    Err(NamespaceError::Rejected(
        "unterminated original propagation target",
    ))
}

pub(crate) struct OriginalInitPropagationRequest<'a> {
    transport: RefMut<'a, Transport>,
    child: &'a TreeChild,
    mount_owner: OwnedNamespaceWitness<'a>,
    mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'a>,
    notification: wire::Notification,
    memory: File,
    memory_node: Node,
    generation: ExecutedInitGeneration,
    kind: OriginalInitPropagationKind,
    deadline: Instant,
}

impl InheritedNotifications {
    pub(crate) fn original_init_propagation<'a>(
        &'a self,
        child: &'a TreeChild,
        init: &ExecutedInitWitness<'_>,
        end: Instant,
        mount_owner: OwnedNamespaceWitness<'a>,
        mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'a>,
    ) -> Result<OriginalInitPropagationRequest<'a>> {
        self.revalidate(child)?;
        init.revalidate_capability_contract()?;
        if init.host_pid() != child.identity.pid || Instant::now() >= end {
            return Err(NamespaceError::Rejected(
                "original propagation request owner/deadline",
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
        let kind = original_propagation_arguments(&memory, &notification.data.args)?;
        let value = OriginalInitPropagationRequest {
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

impl OriginalInitPropagationRequest<'_> {
    pub(crate) fn kind(&self) -> OriginalInitPropagationKind {
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
                "original propagation request deadline",
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
                "original pending propagation request identity changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        self.mount_actors
            .revalidate(&self.mount_owner)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.transport
            .original_mount_barrier(self.child, &self.notification)?;
        self.transport.valid(&self.notification)?;
        if original_propagation_arguments(&self.memory, &self.notification.data.args)? != self.kind
        {
            return Err(NamespaceError::Rejected(
                "original propagation request changed in memory",
            ));
        }
        self.transport.valid(&self.notification)?;
        init.revalidate()?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "original propagation observation exceeded deadline",
            ));
        }
        Ok(())
    }

    pub(crate) fn complete(
        mut self,
        init: &ExecutedInitWitness<'_>,
        completed: &OriginalInitPropagation,
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
                "actual propagation reply exceeded original deadline",
            ));
        }
        self.transport.failed = false;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(kind: OriginalInitPropagationKind) -> (File, [u64; 6]) {
        let file = tempfile::tempfile().unwrap();
        file.write_all_at(kind.target().to_bytes_with_nul(), 64)
            .unwrap();
        (file, [0, 64, 0, kind.flags(), 0, 0])
    }

    #[test]
    fn original_init_propagation_reads_exact_native_targets_flags_and_null_arguments() {
        for kind in OriginalInitPropagationKind::ALL {
            let (file, args) = fixture(kind);
            assert_eq!(original_propagation_arguments(&file, &args).unwrap(), kind);
            for flag in [
                0, 1, 0x1000, 0x4000, 0x40000, 0x44000, 0x80000, 0x100000, 0x104000,
            ] {
                if flag != kind.flags() {
                    let mut wrong = args;
                    wrong[3] = flag;
                    assert!(original_propagation_arguments(&file, &wrong).is_err());
                }
            }
            for index in [0, 2, 4] {
                let mut wrong = args;
                wrong[index] = 64;
                assert!(original_propagation_arguments(&file, &wrong).is_err());
            }
        }
    }

    #[test]
    fn original_init_propagation_memory_rejects_escapes_foreign_paths_and_unbounded_reads() {
        for path in [
            b"//apex\0".as_slice(),
            b"/apex/..\0",
            b"/vendor\0",
            b"/bootstrap-apex\0",
            b"/linkerconfigX",
        ] {
            let (file, args) = fixture(OriginalInitPropagationKind::ApexPrivate);
            file.write_all_at(path, 64).unwrap();
            assert!(original_propagation_arguments(&file, &args).is_err());
        }
        let (file, args) = fixture(OriginalInitPropagationKind::RootShared);
        for address in [0, 8192, i64::MAX as u64, u64::MAX] {
            let mut wrong = args;
            wrong[1] = address;
            assert!(original_propagation_arguments(&file, &wrong).is_err());
        }
    }
}
