//! Complete loaded-policy and kernel observations shared by fixed role observers.
//!
//! Only the two fixed role constructors in this module's parent may acquire
//! this value. It owns the actual input/export/derivation closure, both LSM
//! policy generations and original calling thread. It is not a role, relabel,
//! execution or Android readiness capability.
use super::*;

const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;

fn initial_credentials(proc: &File) -> Result<()> {
    let status = open_at(proc.as_raw_fd(), c"status", libc::O_RDONLY)?;
    require(
        kind(&status)? == PROC_MAGIC,
        "actual MAC observer credentials from procfs",
    )?;
    let bytes = bounded(&status, 65536)?;
    let text =
        std::str::from_utf8(&bytes).map_err(|_| MacError::Rejected("MAC observer status UTF-8"))?;
    for key in ["Uid:", "Gid:"] {
        let rows: Vec<_> = text
            .lines()
            .filter_map(|line| line.strip_prefix(key))
            .collect();
        require(
            rows.len() == 1
                && rows[0].split_whitespace().collect::<Vec<_>>() == ["0", "0", "0", "0"],
            "MAC observer requires original root credentials",
        )?;
    }
    Ok(())
}

// The fixed policy labels the kernel nsfs superblock, never generic unlabeled
// objects. Observe the actual held inode SID in addition to both kernel ioctls.
pub(super) fn fixed_namespace_label(file: &File, declaration: &Declaration) -> Result<()> {
    let before = Node::of(file)?;
    let mut context = [0_u8; 128];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            context.as_mut_ptr().cast(),
            context.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count > 0
            && count as usize <= context.len()
            && context_matches(&context[..count as usize], declaration.nsfs())
            && Node::of(file)? == before,
        "actual held namespace inode must keep its fixed nsfs label",
    )
}

fn initial_namespaces(proc: &File, declaration: &Declaration) -> Result<[File; 2]> {
    let directory = open_at(proc.as_raw_fd(), c"ns", libc::O_PATH | libc::O_DIRECTORY)?;
    require(
        kind(&directory)? == PROC_MAGIC,
        "actual MAC observer namespace directory",
    )?;
    let mut values = Vec::with_capacity(2);
    for (name, kind, expected_id) in [
        (c"user", libc::CLONE_NEWUSER, 3_u64),
        (c"pid", libc::CLONE_NEWPID, 4_u64),
    ] {
        // Follow only the held actual thread's two fixed kernel namespace links.
        let fd = unsafe {
            libc::openat(
                directory.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(fd) };
        fixed_namespace_label(&file, declaration)?;
        let actual_kind = unsafe { libc::ioctl(fd, NS_GET_NSTYPE, 0 as libc::c_ulong) };
        if actual_kind < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let mut id = 0_u64;
        if unsafe { libc::ioctl(fd, NS_GET_ID, &mut id as *mut u64) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(
            actual_kind == kind && id == expected_id,
            "MAC observer must remain in the original initial namespaces",
        )?;
        values.push(file);
    }
    values
        .try_into()
        .map_err(|_| MacError::Rejected("complete original MAC namespaces required"))
}

pub(crate) struct LoadedPolicyWitness {
    pub(super) declaration: Declaration,
    pub(super) contract: Sealed,
    pub(super) policy: Sealed,
    pub(super) policy_export: Sealed,
    pub(super) derivation: Sealed,
    pub(super) root: File,
    pub(super) root_node: Node,
    pub(super) status: StatusMap,
    pub(super) epoch: Epoch,
    pub(super) av_sequence: u32,
    pub(super) apparmor: AaPolicy,
    pub(super) boot: String,
    pub(super) own_proc: File,
    pub(super) own_proc_node: Node,
    initial_namespaces: [File; 2],
    early_media: Option<crate::production_selection::EarlyReleaseMedia>,
    pub(super) tid: libc::pid_t,
    pub(super) host_uid: u32,
    pub(super) _same_thread: PhantomData<Rc<()>>,
}
impl LoadedPolicyWitness {
    pub(super) fn acquire(selection: &ProductionSelection) -> Result<Self> {
        selection
            .revalidate()
            .map_err(|e| MacError::Selection(e.to_string()))?;
        require(
            unsafe { libc::getuid() == 0 && libc::geteuid() == 0 },
            "actual root MAC observer required",
        )?;
        let (contract, raw) = Sealed::read(CONTRACT, MAX_RECORD)?;
        let declaration: Declaration = serde_json::from_slice(&raw)?;
        declaration.validate(selection)?;
        let early_media = if declaration.early() {
            Some(
                crate::production_selection::EarlyReleaseMedia::acquire(selection)
                    .map_err(|e| MacError::Selection(e.to_string()))?,
            )
        } else {
            None
        };
        let (policy, policy_bytes) = Sealed::read(POLICY, MAX_POLICY)?;
        exact_policy_bytes(
            &policy_bytes,
            declaration.policy_input_bytes,
            &declaration.policy_input_sha256,
        )?;
        let (policy_export, expected_export) = Sealed::read(POLICY_EXPORT, MAX_POLICY)?;
        exact_policy_bytes(
            &expected_export,
            declaration.policy_export_bytes,
            &declaration.policy_export_sha256,
        )?;
        require(
            !policy.node.same_inode(policy_export.node),
            "policy input and expected kernel export require distinct sealed files",
        )?;
        let (derivation, derivation_bytes) = Sealed::read(DERIVATION, MAX_DERIVATION)?;
        require(
            derivation_bytes.len() as u64 == declaration.derivation_bytes
                && sha(&derivation_bytes) == declaration.derivation_sha256,
            "installed derivation differs from exact selection",
        )?;
        let root = open_absolute(SELINUX_ROOT, libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            kind(&root)? == SELINUX_MAGIC,
            "actual SELinux filesystem required",
        )?;
        let root_node = Node::of(&root)?;
        let status = StatusMap::open(&root)?;
        let epoch = status.read()?;
        let loaded = relative(&root, &["policy"], libc::O_RDONLY)?;
        let loaded_bytes = bounded(&loaded, MAX_POLICY)?;
        exact_policy_bytes(
            &loaded_bytes,
            declaration.policy_export_bytes,
            &declaration.policy_export_sha256,
        )?;
        require(
            loaded_bytes == expected_export,
            "complete actually loaded policy differs from the sealed kernel export",
        )?;
        let capabilities: &[&str] = if declaration.early() {
            &["nnp_nosuid_transition", "netlink_xperm"]
        } else {
            &[
                "nnp_nosuid_transition",
                "userspace_initial_context",
                "netlink_xperm",
            ]
        };
        for &capability in capabilities {
            let file = relative(&root, &["policy_capabilities", capability], libc::O_RDONLY)?;
            require(
                bounded(&file, 16)? == b"1",
                "required actual policy capability is absent",
            )?;
        }
        let own_proc = own_proc()?;
        let own_proc_node = Node::of(&own_proc)?;
        initial_credentials(&own_proc)?;
        let initial_namespaces = initial_namespaces(&own_proc, &declaration)?;
        let boot = kernel_text("/proc/sys/kernel/random/boot_id", PROC_MAGIC, 64)?;
        require(valid_boot(&boot), "complete current boot identity")?;
        let apparmor = AaPolicy::acquire(&declaration)?;
        let mut sequence = None;
        if declaration.early() {
            kernel_first::required(&root, &mut sequence)?;
        } else {
            required_decisions(&root, &mut sequence)?;
        }
        let av_sequence = sequence.ok_or(MacError::Rejected("no actual kernel decision"))?;
        require(
            status.read()? == epoch && (epoch.policyload == 0 || epoch.policyload == av_sequence),
            "policy and status observations did not share one epoch",
        )?;
        let value = Self {
            declaration,
            contract,
            policy,
            policy_export,
            derivation,
            root,
            root_node,
            status,
            epoch,
            av_sequence,
            apparmor,
            boot,
            own_proc,
            own_proc_node,
            initial_namespaces,
            early_media,
            tid: unsafe { libc::syscall(libc::SYS_gettid) as libc::pid_t },
            host_uid: selection.spec().host_uid,
            _same_thread: PhantomData,
        };
        value.revalidate(selection)?;
        Ok(value)
    }
    pub(super) fn early_media_held(&self) -> bool {
        self.early_media.is_some()
    }

    pub(crate) fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) as libc::pid_t } == self.tid,
            "MAC owner moved threads",
        )?;
        require(
            unsafe { libc::getuid() == 0 && libc::geteuid() == 0 },
            "MAC observer credentials changed",
        )?;
        selection
            .revalidate()
            .map_err(|e| MacError::Selection(e.to_string()))?;
        require(
            selection.spec().host_uid == self.host_uid,
            "MAC selection owner changed",
        )?;
        self.declaration.validate(selection)?;
        require(
            self.declaration.early() == self.early_media.is_some(),
            "kernel-first four-image custody differs",
        )?;
        if let Some(media) = &self.early_media {
            media
                .revalidate()
                .map_err(|e| MacError::Selection(e.to_string()))?;
        }
        self.contract.revalidate()?;
        self.policy.revalidate()?;
        self.policy_export.revalidate()?;
        self.derivation.revalidate()?;
        self.apparmor.revalidate()?;
        require(
            self.status.read()? == self.epoch,
            "SELinux policy/enforcement epoch changed",
        )?;
        let root = open_absolute(SELINUX_ROOT, libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            kind(&root)? == SELINUX_MAGIC && self.root_node.same_inode(Node::of(&root)?),
            "SELinux mount was replaced",
        )?;
        require(
            kernel_text("/proc/sys/kernel/random/boot_id", PROC_MAGIC, 64)? == self.boot,
            "kernel boot changed",
        )?;
        let release = if self.declaration.early() {
            // uname obtains this namespace's actual kernel release without a
            // grant to all ordinary procfs files carrying the shared label.
            let mut system = std::mem::MaybeUninit::<libc::utsname>::uninit();
            if unsafe { libc::uname(system.as_mut_ptr()) } != 0 {
                return Err(io::Error::last_os_error().into());
            }
            let system = unsafe { system.assume_init() };
            unsafe { CStr::from_ptr(system.release.as_ptr()) }
                .to_str()
                .map_err(|_| MacError::Rejected("invalid kernel release"))?
                .to_owned()
        } else {
            kernel_text("/proc/sys/kernel/osrelease", PROC_MAGIC, 256)?
        };
        require(
            release.strip_suffix('\n').unwrap_or(&release) == self.declaration.kernel_release,
            "kernel release differs from installed MAC contract",
        )?;
        let notes = kernel_bytes("/sys/kernel/notes", SYSFS_MAGIC, 1024 * 1024)?;
        require(
            notes.len() as u64 == self.declaration.kernel_notes_bytes
                && sha(&notes) == self.declaration.kernel_notes_sha256,
            "running kernel notes differ from exact MAC build",
        )?;
        let lsms = kernel_text("/sys/kernel/security/lsm", SECURITYFS_MAGIC, 4096)?;
        require(
            self.declaration.context_lsms(&lsms)?
                == self
                    .declaration
                    .active_lsms
                    .iter()
                    .map(String::as_str)
                    .collect::<Vec<_>>(),
            "registered LSM providers or order differ",
        )?;
        require(
            kernel_bytes("/sys/module/apparmor/parameters/enabled", SYSFS_MAGIC, 16)? == b"Y\n",
            "AppArmor is not actually enabled",
        )?;
        require(
            self.own_proc_node.same_inode(Node::of(&self.own_proc)?)
                && self.own_proc_node.same_inode(Node::of(&own_proc()?)?),
            "original MAC observer thread proc identity changed",
        )?;
        initial_credentials(&self.own_proc)?;
        let namespaces = initial_namespaces(&self.own_proc, &self.declaration)?;
        for (current, original) in namespaces.iter().zip(&self.initial_namespaces) {
            require(
                Node::of(current)?.same_inode(Node::of(original)?),
                "MAC observer left its original initial namespaces",
            )?;
        }
        let mut sequence = Some(self.av_sequence);
        // Bind a live AV to the acquired sequence even if the status page started at zero.
        if self.declaration.early() {
            access(
                &self.root,
                KERNEL,
                INIT,
                "process",
                &["transition"],
                true,
                &mut sequence,
            )?;
            access(
                &self.root,
                BROKER,
                INIT,
                "process",
                &["transition", "dyntransition"],
                false,
                &mut sequence,
            )?;
            return self.stable_epoch();
        }
        access(
            &self.root,
            BROKER,
            INIT,
            "process",
            &["transition"],
            true,
            &mut sequence,
        )?;
        self.stable_epoch()
    }

    pub(super) fn stable_epoch(&self) -> Result<()> {
        require(
            self.status.read()? == self.epoch
                && aa_revision(&self.apparmor.security)? == self.apparmor.revision,
            "loaded SELinux or AppArmor epoch changed during observation",
        )
    }
}
