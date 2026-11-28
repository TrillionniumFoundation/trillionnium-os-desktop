//! Fresh writable roots for original CP3A init's activation work.
//!
//! Initial root creates and labels only new detached tmpfs inodes. The actual
//! same-owner idmap is applied before transfer. No original image inode is
//! relabelled and no host pathname or configuration FD reaches Android.

use super::*;

const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const INITIAL_TMPFS: &[u8; 20] = b"u:object_r:tmpfs:s0\0";
pub(crate) const ACTIVATION_FLAGS: u64 = MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV | MOUNT_ATTR_NOEXEC;

/// Fixed empty containers only. Actual APEX payload mounts and linkerconfig
/// files require their separate original-init activation observations.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ActivationRootRole {
    Apex,
    Linkerconfig,
    BootstrapApex,
}

impl ActivationRootRole {
    pub(crate) const LEGACY: [Self; 2] = [Self::Apex, Self::Linkerconfig];
    pub(crate) const ALL: [Self; 3] = [Self::Apex, Self::Linkerconfig, Self::BootstrapApex];
    pub(crate) fn name(self) -> &'static CStr {
        match self {
            Self::Apex => c"apex",
            Self::Linkerconfig => c"linkerconfig",
            Self::BootstrapApex => c"bootstrap-apex",
        }
    }
    pub(crate) fn target(self) -> &'static str {
        match self {
            Self::Apex => "/apex",
            Self::Linkerconfig => "/linkerconfig",
            Self::BootstrapApex => "/bootstrap-apex",
        }
    }
    pub(crate) fn label(self) -> &'static [u8] {
        // Exact original CP3A root-directory EAs, including the trailing NUL.
        match self {
            Self::Apex | Self::BootstrapApex => b"u:object_r:apex_mnt_dir:s0\0",
            Self::Linkerconfig => b"u:object_r:linkerconfig_file:s0\0",
        }
    }
    pub(crate) fn bytes(self) -> u64 {
        match self {
            Self::Apex | Self::BootstrapApex => 64 * 1024 * 1024,
            Self::Linkerconfig => 16 * 1024 * 1024,
        }
    }
    pub(crate) fn inodes(self) -> u64 {
        match self {
            Self::Apex | Self::BootstrapApex => 16_384,
            Self::Linkerconfig => 4_096,
        }
    }
}

pub(crate) fn verify_activation_root(
    file: &File,
    role: ActivationRootRole,
    uid: u32,
    gid: u32,
) -> Result<()> {
    let m = file.metadata()?;
    let readable = open_leaf(file, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let rm = readable.metadata()?;
    require(
        (rm.dev(), rm.ino()) == (m.dev(), m.ino()),
        "activation root descriptor changed",
    )?;
    require(
        fs_type(file)? == TMPFS_MAGIC
            && m.mode() == libc::S_IFDIR | 0o755
            && m.uid() == uid
            && m.gid() == gid
            && m.nlink() >= 2,
        "activation root must remain its original mapped private tmpfs directory",
    )?;
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) })?;
    require(
        flags.f_flag as u64 & (ACTIVATION_FLAGS | MOUNT_ATTR_RDONLY) == ACTIVATION_FLAGS
            && (flags.f_blocks as u64).checked_mul(flags.f_frsize as u64) == Some(role.bytes())
            && flags.f_files as u64 == role.inodes(),
        "activation root must retain its bounded writable nosuid nodev noexec mount",
    )?;
    match role {
        ActivationRootRole::Apex | ActivationRootRole::BootstrapApex => require_exact_xattr(
            &readable,
            c"security.selinux",
            b"u:object_r:apex_mnt_dir:s0\0",
        )?,
        ActivationRootRole::Linkerconfig => require_exact_xattr(
            &readable,
            c"security.selinux",
            b"u:object_r:linkerconfig_file:s0\0",
        )?,
    }
    require_absent_xattr(&readable, c"security.capability")
}

#[derive(Clone, Copy)]
enum RootPurpose {
    Placeholder,
    OriginalInit,
}

#[derive(Debug)]
pub(super) struct WritableRoot {
    role: ActivationRootRole,
    mount: File,
    root: File,
    node: (u64, u64),
    mount_id: u64,
}

impl WritableRoot {
    pub(super) fn prepare(
        role: ActivationRootRole,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        Self::prepare_fixed(role, userns, uids, gids, RootPurpose::Placeholder)
    }

    pub(super) fn prepare_original_init(
        role: ActivationRootRole,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        Self::prepare_fixed(role, userns, uids, gids, RootPurpose::OriginalInit)
    }

    fn prepare_fixed(
        role: ActivationRootRole,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
        purpose: RootPurpose,
    ) -> Result<Self> {
        let context = syscall_fd(unsafe {
            libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), FSOPEN_CLOEXEC)
        })?;
        if matches!(purpose, RootPurpose::OriginalInit) {
            configure(&context, FSCONFIG_SET_STRING, c"source", Some(c"tmpfs"))?;
        }
        configure(
            &context,
            FSCONFIG_SET_STRING,
            c"size",
            Some(&text_name(&role.bytes().to_string())?),
        )?;
        configure(
            &context,
            FSCONFIG_SET_STRING,
            c"nr_inodes",
            Some(&text_name(&role.inodes().to_string())?),
        )?;
        for (key, value) in [(c"mode", c"0755"), (c"uid", c"0"), (c"gid", c"0")] {
            configure(&context, FSCONFIG_SET_STRING, key, Some(value))?;
        }
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.as_raw_fd(),
                FSCONFIG_CMD_CREATE,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_char>(),
                0,
            )
        } as i32)?;
        let mount = syscall_fd(unsafe {
            libc::syscall(
                libc::SYS_fsmount,
                context.as_raw_fd(),
                FSMOUNT_CLOEXEC,
                ACTIVATION_FLAGS as u32,
            )
        })?;
        drop(context);
        require_detached(&mount)?;
        let root = open_leaf(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let m = root.metadata()?;
        require(
            fs_type(&root)? == TMPFS_MAGIC
                && m.mode() == libc::S_IFDIR | 0o755
                && m.uid() == 0
                && m.gid() == 0
                && m.nlink() == 2,
            "activation relabel requires its fresh initial-root-owned tmpfs inode",
        )?;
        require_exact_xattr(&root, c"security.selinux", INITIAL_TMPFS)?;
        let label = role.label();
        zero_rc(unsafe {
            libc::fsetxattr(
                root.as_raw_fd(),
                c"security.selinux".as_ptr(),
                label.as_ptr().cast(),
                label.len(),
                0,
            )
        })?;
        verify_activation_root(&root, role, 0, 0)?;
        let node = (m.dev(), m.ino());
        drop(root);
        let attr = MountAttr {
            attr_set: ACTIVATION_FLAGS | MOUNT_ATTR_IDMAP,
            attr_clr: 0,
            propagation: 0,
            userns_fd: u64::try_from(userns.as_raw_fd())
                .map_err(|_| MountError::Rejected("activation root user namespace FD"))?,
        };
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_mount_setattr,
                mount.as_raw_fd(),
                c"".as_ptr(),
                AT_EMPTY_PATH,
                &attr,
                std::mem::size_of::<MountAttr>(),
            )
        } as i32)?;
        let mount_id = require_detached(&mount)?;
        let root = open_leaf(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let value = Self {
            role,
            mount,
            root,
            node,
            mount_id,
        };
        value.verify_fresh(uids, gids)?;
        Ok(value)
    }

    pub(super) fn root(&self) -> &File {
        &self.root
    }
    pub(super) fn mount(&self) -> &File {
        &self.mount
    }

    /// Original descriptor/inode/protection custody after a separately proved
    /// mount transition. This does not assert detachment or any guest path.
    pub(super) fn verify_original_source(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        for file in [&self.root, &self.mount] {
            let m = file.metadata()?;
            require(
                (m.dev(), m.ino()) == self.node && mount_id(file)? == self.mount_id,
                "original writable source lost its held inode/mount identity",
            )?;
        }
        verify_activation_root(&self.root, self.role, uids.start, gids.start)
    }

    fn revalidate(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        for file in [&self.root, &self.mount] {
            let m = file.metadata()?;
            require(
                (m.dev(), m.ino()) == self.node && require_detached(file)? == self.mount_id,
                "activation root lost its original mount and inode custody",
            )?;
        }
        verify_activation_root(&self.root, self.role, uids.start, gids.start)
    }

    pub(super) fn verify_fresh(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        self.revalidate(uids, gids)?;
        let directory = open_leaf(&self.root, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            std::fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))?
                .next()
                .transpose()?
                .is_none()
                && self.root.metadata()?.nlink() == 2,
            "activation root must be entirely empty before its one transfer",
        )
    }
}

#[derive(Debug)]
pub(super) struct ActivationRoots {
    roots: [WritableRoot; 3],
}

impl ActivationRoots {
    /// Borrow only the original fresh root inode. This does not adopt another
    /// namespace, a replacement filesystem or an init-created submount.
    pub(super) fn original_root(&self, role: ActivationRootRole) -> &File {
        &self
            .roots
            .iter()
            .find(|root| root.role == role)
            .expect("fixed activation root")
            .root
    }

    pub(super) fn prepare(
        owner: &OwnedNamespaceWitness<'_>,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        crate::production_devices::require_initial_broker()
            .map_err(|error| MountError::Io(io::Error::other(error.to_string())))?;
        owner.revalidate_live_admission()?;
        let actual = owner.user_namespace().metadata()?;
        let selected = userns.metadata()?;
        require(
            (actual.dev(), actual.ino()) == (selected.dev(), selected.ino())
                && owner.identity_lease()?.broker_ranges() == (uids, gids),
            "activation writable roots require the same live owned namespace and maps",
        )?;
        let apex = WritableRoot::prepare(ActivationRootRole::Apex, userns, uids, gids)?;
        let linkerconfig =
            WritableRoot::prepare(ActivationRootRole::Linkerconfig, userns, uids, gids)?;
        let bootstrap_apex =
            WritableRoot::prepare(ActivationRootRole::BootstrapApex, userns, uids, gids)?;
        require(
            [apex.node.0, linkerconfig.node.0, bootstrap_apex.node.0]
                .into_iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                == 3
                && [
                    apex.mount_id,
                    linkerconfig.mount_id,
                    bootstrap_apex.mount_id,
                ]
                .into_iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                    == 3,
            "activation roots must be distinct fresh filesystems",
        )?;
        let value = Self {
            roots: [apex, linkerconfig, bootstrap_apex],
        };
        owner.revalidate_live_admission()?;
        value.revalidate(uids, gids)?;
        Ok(value)
    }

    pub(super) fn revalidate(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        for (root, role) in self.roots.iter().zip(ActivationRootRole::ALL) {
            require(root.role == role, "activation root order differs")?;
            root.revalidate(uids, gids)?;
        }
        Ok(())
    }

    pub(super) fn for_transfer(&self, uids: IdRange, gids: IdRange) -> Result<[BorrowedFd<'_>; 3]> {
        for root in &self.roots {
            root.verify_fresh(uids, gids)?;
        }
        Ok([
            self.roots[0].mount.as_fd(),
            self.roots[1].mount.as_fd(),
            self.roots[2].mount.as_fd(),
        ])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn activation_roots_keep_distinct_fixed_labels_bounds_and_nonexecution_flags() {
        assert_eq!(ActivationRootRole::Apex.target(), "/apex");
        assert_eq!(ActivationRootRole::Linkerconfig.target(), "/linkerconfig");
        assert_eq!(
            ActivationRootRole::BootstrapApex.target(),
            "/bootstrap-apex"
        );
        assert_eq!(ActivationRootRole::BootstrapApex.name(), c"bootstrap-apex");
        assert_eq!(
            ActivationRootRole::BootstrapApex.label(),
            ActivationRootRole::Apex.label()
        );
        assert_eq!(ActivationRootRole::BootstrapApex.bytes(), 64 * 1024 * 1024);
        assert_eq!(ActivationRootRole::BootstrapApex.inodes(), 16_384);
        assert_eq!(
            ActivationRootRole::ALL
                .into_iter()
                .map(ActivationRootRole::target)
                .collect::<std::collections::BTreeSet<_>>()
                .len(),
            3
        );
        assert_ne!(
            ActivationRootRole::Apex.label(),
            ActivationRootRole::Linkerconfig.label()
        );
        for role in ActivationRootRole::ALL {
            assert!(
                role.label().ends_with(b"\0")
                    && !role.label()[..role.label().len() - 1].contains(&0)
            );
            assert!((16 * 1024 * 1024..=64 * 1024 * 1024).contains(&role.bytes()));
            assert!((4096..=16384).contains(&role.inodes()));
            let directory = tempfile::tempdir().unwrap();
            let file = File::open(directory.path()).unwrap();
            // An ordinary directory, its pathname or copied metadata cannot
            // stand in for the actually created bounded labelled filesystem.
            assert!(
                verify_activation_root(&file, role, unsafe { libc::geteuid() }, unsafe {
                    libc::getegid()
                })
                .is_err()
            );
        }
        assert_eq!(ACTIVATION_FLAGS, 2 | 4 | 8);
    }
}
