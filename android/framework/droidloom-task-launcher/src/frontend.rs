//! Acquire the one platform task channel through the selected Composer extension.

use binder::ParcelFileDescriptor;
use std::fs::File;
use std::os::fd::AsFd;
use std::path::Path;

use binder::{binder_impl::IBinderInternal, Strong};
use droidloom_denial_ipc::SeqPacket;
use org_droidloom_frontend::aidl::org::droidloom::frontend::IFrontendChannels::{
    IFrontendChannels, HASH, VERSION,
};

use super::{DEFAULT_CONTROL_SOCKET, LaunchError};

pub(super) fn connect(path: &Path) -> Result<(SeqPacket, SeqPacket), LaunchError> {
    if path != Path::new(DEFAULT_CONTROL_SOCKET) {
        return Err(LaunchError::Control(
            "Android task channel has no caller-selected path".into(),
        ));
    }
    let failure = |error: &dyn std::fmt::Debug| {
        LaunchError::Control(format!("Composer frontend Binder: {error:?}"))
    };
    let mut composer = binder::get_service("android.hardware.graphics.composer3.IComposer/default")
        .ok_or_else(|| LaunchError::Control("selected Composer Binder is unavailable".into()))?;
    let extension = composer
        .get_extension()
        .map_err(|e| failure(&e))?
        .ok_or_else(|| {
            LaunchError::Control("selected Composer has no frontend extension".into())
        })?;
    let channel: Strong<dyn IFrontendChannels> =
        extension.into_interface().map_err(|e| failure(&e))?;
    if channel.getInterfaceVersion().map_err(|e| failure(&e))? != VERSION {
        return Err(LaunchError::Control(
            "incompatible Composer frontend version".into(),
        ));
    }
    // The declared frozen V1 Rust dependency owns both generated constants.
    // Reading its .hash again would be an undeclared Soong compilation input.
    if channel.getInterfaceHash().map_err(|e| failure(&e))? != HASH {
        return Err(LaunchError::Control(
            "incompatible Composer frontend hash".into(),
        ));
    }
    let (proof, lifetime) = SeqPacket::pair()?;
    let proof = ParcelFileDescriptor::new(File::from(proof.as_fd().try_clone_to_owned()?));
    let file = channel
        .openTaskControlChannel(&proof)
        .map_err(|e| failure(&e))?;
    let socket = SeqPacket::from_owned_fd(file.as_fd().try_clone_to_owned()?)?;
    let credentials = socket.peer_credentials()?;
    if credentials.pid <= 0 || credentials.uid != 1000 || credentials.gid != 1000 {
        return Err(LaunchError::Control(
            "Binder task descriptor is not the Composer-created endpoint".into(),
        ));
    }
    Ok((socket, lifetime))
}
