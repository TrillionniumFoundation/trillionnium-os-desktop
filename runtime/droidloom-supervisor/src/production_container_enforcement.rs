//! The shared-kernel owner retains the original selinuxfs mode, policy epoch
//! and mount until its last Android readiness observation has been withdrawn.
use super::*;
use std::os::unix::fs::FileExt;

fn read_enforcing(file: &File) -> Result<()> {
    let mut bytes = [0; 3];
    let n = file.read_at(&mut bytes, 0).map_err(|e| {
        io::Error::new(
            e.kind(),
            format!("cannot read /sys/fs/selinux/enforce: {e}"),
        )
    })?;
    match &bytes[..n] {
        b"1" | b"1\n" => Ok(()),
        b"0" | b"0\n" => Err(MacError::Rejected(
            "the kernel reports permissive mode at /sys/fs/selinux/enforce",
        )),
        _ => Err(MacError::Rejected(
            "invalid kernel enforcement value at /sys/fs/selinux/enforce",
        )),
    }
}

fn same_epoch(original: Epoch, current: Epoch) -> Result<()> {
    current.valid()?;
    require(
        original == current,
        "the original enforcing SELinux policy epoch changed",
    )
}

struct KernelEnforcement {
    root: File,
    enforce: File,
    status: StatusMap,
    epoch: Epoch,
}

impl KernelEnforcement {
    fn from_root(root: File) -> Result<Self> {
        require(
            kind(&root)? == SELINUX_MAGIC,
            "current backend needs a genuine selinuxfs mount",
        )?;
        let enforce = relative(&root, &["enforce"], libc::O_RDONLY).map_err(|e| {
            io::Error::other(format!("cannot open kernel /sys/fs/selinux/enforce: {e}"))
        })?;
        // A permissive boot should identify the actual rejected mode even when
        // the initial policy has not yet populated the status page.
        read_enforcing(&enforce)?;
        let status = StatusMap::open(&root)?;
        let epoch = status.read()?;
        let guard = Self {
            root,
            enforce,
            status,
            epoch,
        };
        guard.check_epoch()?;
        Ok(guard)
    }

    fn acquire() -> io::Result<Self> {
        let root = open_absolute(SELINUX_ROOT, libc::O_PATH | libc::O_DIRECTORY).map_err(|e| {
            io::Error::other(format!(
                "current MAC backend needs an active selinuxfs at {SELINUX_ROOT}: {e}"
            ))
        })?;
        let guard = Self::from_root(root).map_err(io::Error::other)?;
        let ordered = kernel_text("/sys/kernel/security/lsm", SECURITYFS_MAGIC, 4096)
            .map_err(io::Error::other)?;
        if !ordered.trim_end().split(',').any(|lsm| lsm == "apparmor")
            || !ordered.trim_end().split(',').any(|lsm| lsm == "selinux")
        {
            return Err(io::Error::other(
                "both SELinux and AppArmor must be registered for this boot",
            ));
        }
        if kernel_bytes("/sys/module/apparmor/parameters/enabled", SYSFS_MAGIC, 16)
            .map_err(io::Error::other)?
            != b"Y\n"
        {
            return Err(io::Error::other("AppArmor is disabled for this boot"));
        }
        guard.revalidate().map_err(io::Error::other)?;
        Ok(guard)
    }

    fn check_epoch(&self) -> Result<()> {
        same_epoch(self.epoch, self.status.read()?)?;
        read_enforcing(&self.enforce)?;
        same_epoch(self.epoch, self.status.read()?)
    }

    fn revalidate(&self) -> Result<()> {
        let current = open_absolute(SELINUX_ROOT, libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            kind(&current)? == SELINUX_MAGIC
                && Node::of(&self.root)?.same_inode(Node::of(&current)?),
            "the original selinuxfs mount was replaced",
        )?;
        for (name, held) in [("enforce", &self.enforce), ("status", &self.status._file)] {
            let live = relative(&current, &[name], libc::O_RDONLY)?;
            require(
                Node::of(held)?.same_inode(Node::of(&live)?),
                "the selected selinuxfs enforcement or status inode changed",
            )?;
        }
        self.check_epoch()
    }
}

/// Verify the live kernel interfaces supported by the shared-kernel backend.
///
/// # Errors
/// Reports an unavailable kernel interface or a non-enforcing platform.
pub fn check_installed_mac_platform() -> io::Result<()> {
    KernelEnforcement::acquire().map(drop)
}

/// Security state held by the actual systemd MainPID for one Android generation.
pub struct ContainerManagerMac(KernelEnforcement);
impl ContainerManagerMac {
    /// Acquire the current kernel mode, policy epoch and distinct manager role.
    ///
    /// # Errors
    /// Rejects any missing, permissive or wrongly identified security backend.
    pub fn acquire() -> io::Result<Self> {
        let guard = Self(KernelEnforcement::acquire()?);
        guard.revalidate()?;
        Ok(guard)
    }

    /// Check the retained kernel ABI immediately before reporting progress.
    ///
    /// # Errors
    /// An unreadable mode or a change in enforcement or policy retires the generation.
    pub fn check_epoch(&self) -> io::Result<()> {
        self.0.check_epoch().map_err(io::Error::other)
    }

    /// Reopen the fixed kernel interfaces and recheck the role of the actual owner.
    ///
    /// # Errors
    /// Changed inodes, task roles or enforcement invalidate the original grant.
    pub fn revalidate(&self) -> io::Result<()> {
        self.0.revalidate().map_err(io::Error::other)?;
        check_current_container_manager_role()?;
        self.check_epoch()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn a_regular_directory_cannot_supply_kernel_mode_or_epoch() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("enforce"), b"1").unwrap();
        std::fs::write(dir.path().join("status"), [0u8; 4096]).unwrap();
        assert!(KernelEnforcement::from_root(File::open(dir.path()).unwrap()).is_err());
    }

    #[test]
    fn mode_requires_readable_exact_enforcing_bytes() {
        for bytes in [b"0".as_slice(), b"0\n", b"", b"10", b"1\n1"] {
            let mut file = tempfile::tempfile().unwrap();
            file.write_all(bytes).unwrap();
            assert!(read_enforcing(&file).is_err());
        }
        let dir = tempfile::tempdir().unwrap();
        let mut write_only = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(dir.path().join("write-only"))
            .unwrap();
        write_only.write_all(b"1").unwrap();
        assert!(read_enforcing(&write_only).is_err());
        let mut valid = tempfile::tempfile().unwrap();
        valid.write_all(b"1").unwrap();
        read_enforcing(&valid).unwrap();
    }

    #[test]
    fn permissive_or_changed_epoch_invalidates_previous_permission() {
        let original = Epoch {
            version: 1,
            sequence: 2,
            enforcing: 1,
            policyload: 1,
            deny_unknown: 1,
        };
        same_epoch(original, original).unwrap();
        assert!(
            same_epoch(
                original,
                Epoch {
                    enforcing: 0,
                    ..original
                }
            )
            .is_err()
        );
        assert!(
            same_epoch(
                original,
                Epoch {
                    sequence: 6,
                    ..original
                }
            )
            .is_err()
        );
        assert!(
            same_epoch(
                original,
                Epoch {
                    policyload: 2,
                    ..original
                }
            )
            .is_err()
        );
    }
}
