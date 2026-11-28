//! One actual original-init /bootstrap-apex -> /apex recursive bind request.
use super::super::original_ptrace::OriginalBootstrapBindChange;
use super::*;

fn path(memory: &File, address: u64) -> Result<Vec<u8>> {
    const LIMIT: usize = b"/bootstrap-apex\0".len();
    if address == 0 || address > (i64::MAX as u64).saturating_sub(LIMIT as u64) {
        return Err(NamespaceError::Rejected(
            "bounded original bootstrap bind pathname",
        ));
    }
    let mut value = Vec::with_capacity(LIMIT);
    for offset in 0..LIMIT {
        let mut byte = [0u8; 1];
        if memory.read_at(&mut byte, address + offset as u64)? != 1 {
            return Err(NamespaceError::Rejected(
                "incomplete original bootstrap bind pathname",
            ));
        }
        if byte[0] == 0 {
            return Ok(value);
        }
        value.push(byte[0]);
    }
    Err(NamespaceError::Rejected(
        "unterminated original bootstrap bind pathname",
    ))
}

fn arguments(memory: &File, args: &[u64; 6]) -> Result<()> {
    if args[2] != 0
        || args[4] != 0
        || args[3] != 0x5000
        || path(memory, args[0])? != b"/bootstrap-apex"
        || path(memory, args[1])? != b"/apex"
    {
        return Err(NamespaceError::Rejected(
            "original bootstrap bind arguments differ",
        ));
    }
    Ok(())
}

pub(crate) struct OriginalInitBootstrapBindRequest<'a> {
    transport: RefMut<'a, Transport>,
    child: &'a TreeChild,
    mount_owner: OwnedNamespaceWitness<'a>,
    mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'a>,
    notification: wire::Notification,
    memory: File,
    memory_node: Node,
    generation: ExecutedInitGeneration,
    deadline: Instant,
    change: OriginalBootstrapBindChange,
}

impl InheritedNotifications {
    pub(crate) fn original_init_bootstrap_bind<'a>(
        &'a self,
        child: &'a TreeChild,
        init: &ExecutedInitWitness<'_>,
        end: Instant,
        mount_owner: OwnedNamespaceWitness<'a>,
        mount_actors: crate::production_runtime_assets::NativeMountActorGuard<'a>,
    ) -> Result<OriginalInitBootstrapBindRequest<'a>> {
        self.revalidate(child)?;
        init.revalidate_capability_contract()?;
        if init.host_pid() != child.identity.pid || Instant::now() >= end {
            return Err(NamespaceError::Rejected(
                "bootstrap bind original init or deadline",
            ));
        }
        let mut transport = self
            .transport
            .try_borrow_mut()
            .map_err(|_| NamespaceError::Rejected("bootstrap listener already borrowed"))?;
        if transport.original_trace.is_some() || transport.successor_deadline.is_some() {
            return Err(NamespaceError::Rejected(
                "bootstrap bind requires completed original trace handoff",
            ));
        }
        transport
            .successors
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "bootstrap bind original successor owner absent",
            ))?
            .idle()?;
        let notification = transport.receive(end)?;
        if notification.pid != child.identity.pid
            || notification.operation() != Some(wire::Operation::Mount)
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind only accepts the original init mount",
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
                "bootstrap bind memory is not original procfs",
            ));
        }
        let memory_node = Node::of(&memory)?;
        transport.valid(&notification)?;
        arguments(&memory, &notification.data.args)?;
        let change = transport
            .successors
            .as_ref()
            .unwrap()
            .begin_original_bootstrap_bind(child, transport.node, notification)?;
        let value = OriginalInitBootstrapBindRequest {
            transport,
            child,
            mount_owner,
            mount_actors,
            notification,
            memory,
            memory_node,
            generation: init.generation()?,
            deadline: end,
            change,
        };
        value.revalidate(init)?;
        Ok(value)
    }
}

impl OriginalInitBootstrapBindRequest<'_> {
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
            return Err(NamespaceError::Rejected("bootstrap bind original deadline"));
        }
        init.revalidate_capability_contract()?;
        self.child.verify()?;
        if init.generation()? != self.generation
            || init.host_pid() != self.child.identity.pid
            || self.notification.pid != self.child.identity.pid
            || self.transport.pending != Some(self.notification)
            || self.transport.failed
            || self.transport.receiving.is_some()
            || self.transport.original_trace.is_some()
            || self.transport.successor_deadline.is_some()
            || Node::of(&self.memory)? != self.memory_node
        {
            return Err(NamespaceError::Rejected(
                "bootstrap bind original owner or pending call changed",
            ));
        }
        self.transport.valid(&self.notification)?;
        self.mount_actors
            .revalidate(&self.mount_owner)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.transport
            .successors
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "bootstrap bind successor custody lost",
            ))?
            .original_bootstrap_bind_barrier(
                self.child,
                self.transport.node,
                &self.notification,
                &self.change,
            )?;
        arguments(&self.memory, &self.notification.data.args)?;
        self.transport.valid(&self.notification)?;
        init.revalidate()?;
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "bootstrap bind revalidation exceeded deadline",
            ));
        }
        Ok(())
    }

    pub(crate) fn before_mount(
        &self,
        init: &ExecutedInitWitness<'_>,
        source: &File,
        target: &File,
    ) -> Result<()> {
        self.revalidate(init)?;
        self.change.before_mount(self.child, source, target)?;
        self.revalidate(init)
    }

    pub(crate) fn execute(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &crate::production_mac::MacPreflight,
    ) -> Result<()> {
        self.revalidate(init)?;
        let worker = init
            .runtime_owner()?
            .prepare_original_init_bootstrap_bind(init, mac, self)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.change.install_worker(self.child, worker)?;
        {
            let mut worker = self.change.worker_mut()?;
            worker
                .run(init, self)
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        let worker = self.change.worker()?;
        let errno = worker
            .actual_errno(init, self)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        let (source, target) = worker
            .original_views(init, self)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.change
            .observe_actual(self.child, source, target, errno)?;
        self.revalidate(init)
    }

    pub(crate) fn complete(mut self, init: &ExecutedInitWitness<'_>) -> Result<i32> {
        self.revalidate(init)?;
        let errno = {
            let worker = self.change.worker()?;
            worker
                .actual_errno(init, &self)
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?
        };
        self.change.require_actual(self.child, errno)?;
        self.revalidate(init)?;
        let response = wire::Response {
            id: self.notification.id,
            value: 0,
            error: -errno,
            flags: 0,
        };
        let delivery = self.change.prepare_response(self.child, errno)?;
        self.transport.failed = true;
        if unsafe { libc::ioctl(self.transport.file.as_raw_fd(), wire::SEND, &response) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        // The held original journal is committed before any operation that
        // could fail after the original task has been released.
        delivery.sent();
        self.transport.pending.take();
        if Instant::now() >= self.deadline {
            return Err(NamespaceError::Rejected(
                "bootstrap bind reply exceeded original deadline",
            ));
        }
        self.change.complete_response(self.child, errno)?;
        self.transport.failed = false;
        Ok(errno)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn memory() -> (File, [u64; 6]) {
        let file = tempfile::tempfile().unwrap();
        file.write_all_at(b"/bootstrap-apex\0", 64).unwrap();
        file.write_all_at(b"/apex\0", 128).unwrap();
        (file, [64, 128, 0, 0x5000, 0, 0])
    }

    #[test]
    fn original_bootstrap_bind_reads_exact_original_pathnames_and_flags() {
        let (file, args) = memory();
        arguments(&file, &args).unwrap();
        for index in [0, 1, 2, 4] {
            let mut wrong = args;
            wrong[index] = if index < 2 { 0 } else { 64 };
            assert!(arguments(&file, &wrong).is_err());
        }
        for flags in [0, 0x1000, 0x4000, 0x5001, 0x104000, 0x40000, u64::MAX] {
            let mut wrong = args;
            wrong[3] = flags;
            assert!(arguments(&file, &wrong).is_err());
        }
        for (address, value) in [
            (64, b"/apex\0".as_slice()),
            (64, b"//bootstrap-apex\0"),
            (128, b"/apex/..\0"),
            (128, b"/bootstrap-apex\0"),
        ] {
            let (file, args) = memory();
            file.write_all_at(value, address).unwrap();
            assert!(arguments(&file, &args).is_err());
        }
    }

    #[test]
    fn original_bootstrap_bind_rejects_short_unterminated_and_unbounded_memory() {
        for address in [0, 4096, i64::MAX as u64, u64::MAX] {
            let (file, mut args) = memory();
            args[0] = address;
            assert!(arguments(&file, &args).is_err());
        }
        let (file, args) = memory();
        file.write_all_at(b"/bootstrap-apexX", 64).unwrap();
        assert!(arguments(&file, &args).is_err());
        let (file, args) = memory();
        file.set_len(69).unwrap();
        assert!(arguments(&file, &args).is_err());
    }
}
