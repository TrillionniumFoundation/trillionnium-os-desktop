//! Fixed original-systemd socket label installer entry.
//!
//! No argument can select a process, path, context, command, policy or role.
//! It never loads a policy or returns any Android admission capability.
use crate::production_cgroup::AuthenticatedManagerEndpoint;
use crate::production_configuration::ConfigurationReadGuard;
use crate::production_mac::LoaderHostPeerOwner;
use crate::production_selection::ProductionSelection;
use std::path::Path;
use std::time::{Duration, Instant};

/// Seal only the original host manager's private server inode.
///
/// Returns a serialized observation after the actual fixed operation. Any
/// failed post-write check remains an error; no rollback is attempted. The
/// report is not accepted by production execution or by the ordinary manager
/// owner, which must subsequently capture and validate its own fresh endpoint.
pub fn seal_systemd_private() -> Result<String, String> {
    let deadline = Instant::now() + Duration::from_secs(30);
    let guard = ConfigurationReadGuard::acquire().map_err(|e| e.to_string())?;
    let selection =
        ProductionSelection::load(&guard, Path::new("/etc/droidloom/cell.json"), unsafe {
            libc::getuid()
        })
        .map_err(|e| e.to_string())?;
    let original = LoaderHostPeerOwner::acquire(selection).map_err(|e| e.to_string())?;
    let endpoint = AuthenticatedManagerEndpoint::capture_loader(original.clone(), deadline)
        .map_err(|e| e.to_string())?;
    let (loader, selection) = original.objects().map_err(|e| e.to_string())?;
    guard.revalidate().map_err(|e| e.to_string())?;
    let observed = endpoint
        .seal_fixed_manager_label(loader, selection, deadline)
        .map_err(|e| e.to_string())?;
    guard.revalidate().map_err(|e| e.to_string())?;
    serde_json::to_string(&observed).map_err(|e| e.to_string())
}

/// Capture a release from the selected four images and this boot's enforcing kernel.
pub fn export_kernel_first_release() -> Result<droidloom_contracts::mac_release::Release, String> {
    crate::production_mac::capture_kernel_first_release().map_err(|error|error.to_string())
}
