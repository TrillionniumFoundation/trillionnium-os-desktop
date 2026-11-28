//! One consumed mutation of the actual original manager sock_file.
//!
//! No public descriptor/path/label constructor exists. A successful report is
//! data only; the ordinary manager owner must capture a fresh immutable endpoint.
use super::*;
use crate::production_mac::{LoaderMacWitness, MacError};
use crate::production_selection::ProductionSelection;
use serde::Serialize;

const TARGET: &[u8] = b"u:object_r:droidloom_manager_private_socket:s0";

fn mac<T>(value: Result<T>) -> std::result::Result<T, MacError> {
    value.map_err(|error| match error {
        CgroupError::Io(error) => MacError::Io(error),
        other => MacError::Owner(other.to_string()),
    })
}

#[derive(Debug, thiserror::Error)]
pub(crate) enum ManagerLabelError {
    #[error("manager label rejected before any write: {0}")]
    Before(MacError),
    #[error("manager label write was attempted; success and rollback are not inferred: {0}")]
    Attempted(MacError),
}

/// This value cannot be converted to the original endpoint or any admission.
/// Its numbers are reporting only and must never be used to reopen ownership.
#[derive(Serialize)]
pub(crate) struct ManagerLabelReport {
    scope: &'static str,
    changed: bool,
    manager_start_ticks: u64,
    original_server_device: u64,
    original_server_inode: u64,
    before_ctime: (i64, i64),
    after_ctime: (i64, i64),
    original_server_label: &'static str,
}

/// Only the immutable original endpoint can produce this consumed stage.
struct LabelTarget {
    custody: EndpointCustody,
    before: Metadata,
}

/// Retains a distinct post-write seal. Never exported as ordinary custody.
struct ObservedLabel {
    target: LabelTarget,
    after: Metadata,
}

fn unchanged_except_ctime(before: &Metadata, after: &Metadata) -> bool {
    before.dev() == after.dev()
        && before.ino() == after.ino()
        && before.mode() == after.mode()
        && before.uid() == after.uid()
        && before.gid() == after.gid()
        && before.nlink() == after.nlink()
        && before.size() == after.size()
        && before.rdev() == after.rdev()
        && before.mtime() == after.mtime()
        && before.mtime_nsec() == after.mtime_nsec()
}

impl LabelTarget {
    fn view(&self) -> ManagerLabelObservation<'_> {
        ManagerLabelObservation {
            custody: &self.custody,
            seal: &self.before,
        }
    }
    fn write_fixed(&self) -> std::result::Result<(), MacError> {
        // On the exact target kernel fgetxattr/getxattrat's fdget rejects
        // O_PATH. This is this process's owned FD alias, never a fresh lookup
        // of /run/systemd/private and never the connected client's inode.
        let path = CString::new(format!("/proc/self/fd/{}", self.custody.file.as_raw_fd()))
            .map_err(|_| MacError::Rejected("invalid owned manager FD alias"))?;
        let rc = unsafe {
            libc::setxattr(
                path.as_ptr(),
                c"security.selinux".as_ptr(),
                TARGET.as_ptr().cast(),
                TARGET.len(),
                0,
            )
        };
        if rc != 0 {
            return Err(io::Error::last_os_error().into());
        }
        // No forced SID, errno fallback or rollback. The actual target
        // kernel performs relabelfrom/to, validatetrans and FS association.
        Ok(())
    }
}
impl ObservedLabel {
    fn view(&self) -> ManagerLabelObservation<'_> {
        ManagerLabelObservation {
            custody: &self.target.custody,
            seal: &self.after,
        }
    }
    fn report(&self, changed: bool) -> ManagerLabelReport {
        ManagerLabelReport {
            scope: "original-systemd-server-label-only-v1",
            changed,
            manager_start_ticks: self.target.custody.manager.start,
            original_server_device: self.after.dev(),
            original_server_inode: self.after.ino(),
            before_ctime: (self.target.before.ctime(), self.target.before.ctime_nsec()),
            after_ctime: (self.after.ctime(), self.after.ctime_nsec()),
            original_server_label: "u:object_r:droidloom_manager_private_socket:s0",
        }
    }
}

impl AuthenticatedManagerEndpoint {
    /// Only the actual fixed loader can enter this consumed operation. Even
    /// an already-labeled socket undergoes all current original-owner, exact
    /// executable, loaded-policy, mount, context and deadline observations.
    pub(crate) fn seal_fixed_manager_label(
        self,
        loader: &LoaderMacWitness,
        selection: &ProductionSelection,
        deadline: Instant,
    ) -> std::result::Result<ManagerLabelReport, ManagerLabelError> {
        mac(self.revalidate_until(deadline)).map_err(ManagerLabelError::Before)?;
        let target = LabelTarget {
            custody: self.custody,
            before: self.file_seal,
        };
        let permit = loader
            .manager_label_permit(selection, &target.view(), deadline)
            .map_err(ManagerLabelError::Before)?;
        permit
            .revalidate_original(&target.view(), deadline)
            .map_err(ManagerLabelError::Before)?;
        mac(before(deadline)).map_err(ManagerLabelError::Before)?;
        let changed = !permit.already_labeled();
        if changed {
            // Exactly one call; any failure from this point remains a failed
            // attempted mutation. Drop closes only our own FDs, never the
            // original socket name or manager process, and never rolls back.
            target.write_fixed().map_err(ManagerLabelError::Attempted)?;
        }
        let observe = || -> std::result::Result<Metadata, MacError> {
            mac(before(deadline))?;
            mac(target.custody.check_until(deadline))?;
            let after = target.custody.file.metadata()?;
            if !unchanged_except_ctime(&target.before, &after) {
                return Err(MacError::Rejected(
                    "unexpected original server metadata mutation",
                ));
            }
            if !changed && file_seal(&target.before) != file_seal(&after) {
                return Err(MacError::Rejected("already-labeled original inode changed"));
            }
            Ok(after)
        };
        let after = observe().map_err(|e| {
            if changed {
                ManagerLabelError::Attempted(e)
            } else {
                ManagerLabelError::Before(e)
            }
        })?;
        let observed = ObservedLabel { target, after };
        permit
            .revalidate_labeled(&observed.view(), deadline)
            .map_err(|e| {
                if changed {
                    ManagerLabelError::Attempted(e)
                } else {
                    ManagerLabelError::Before(e)
                }
            })?;
        mac(before(deadline)).map_err(|e| {
            if changed {
                ManagerLabelError::Attempted(e)
            } else {
                ManagerLabelError::Before(e)
            }
        })?;
        Ok(observed.report(changed))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn same_real_inode_label_stage_rejects_unrelated_metadata_change() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("one-inode");
        std::fs::write(&path, b"original").unwrap();
        let file = File::open(&path).unwrap();
        let before = file.metadata().unwrap();
        // Ordinary metadata control only. No endpoint, role or SELinux
        // mutation capability can be built from this regular test file.
        assert!(unchanged_except_ctime(&before, &file.metadata().unwrap()));
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400)).unwrap();
        assert!(!unchanged_except_ctime(&before, &file.metadata().unwrap()));
        std::fs::remove_file(&path).unwrap();
        assert!(!unchanged_except_ctime(&before, &file.metadata().unwrap()));
    }
}
