//! Actual preparation-peer installation from source-held original descriptors.
//! The returned value is opaque. A serialized reply cannot recreate its live
//! PIDFD, installed source, current Main, or successful normal PM transaction.
use super::*;
use crate::native_working_install::{self as wire, WorkingInstallRequest, WorkingInstallReply};
use std::{fs::File, time::{Duration, Instant}};

pub struct WorkingOriginalInstallObservation {
    reply: WorkingInstallReply,
    peer_pidfd: File,
    peer: NativeInspectionPeer,
    payload_birth: crate::production_application::working_payload_birth::Retirement,
}
fn node(file: &File) -> Result<(u64, u64), ControlError> {
    live(file).map_err(|e| io_error("retain original install peer", e))?;
    let m = file.metadata().map_err(|e| io_error("inspect original install peer", e))?;
    Ok((m.dev(), m.ino()))
}
impl WorkingOriginalInstallObservation {
    pub fn comparison(&self) -> Result<serde_json::Value, String> {
        let mut value = self.reply.comparison()?;
        value["payload_birth"] = self.payload_birth.comparison().map_err(|e|e.to_string())?;
        Ok(value)
    }
    pub fn require_main(&self, inspector: &NativeApplicationInspector,
        main: &MainCustodyObservation, end: Instant) -> Result<(), ControlError>
    {
        self.payload_birth.guard().map_err(|e|ControlError::Invalid(e.to_string()))?;
        inspector.require_working_install_main(main, end)?;
        if node(&self.peer_pidfd)? != node(&main.pidfd)? || self.peer != main.peer
            || self.reply.main() != main.facts() {
            return Err(ControlError::Invalid("original install history belongs to another actual Main".into()));
        }
        Ok(())
    }
}
impl NativeApplicationInspector {
    fn require_working_install_main(&self, main: &MainCustodyObservation, end: Instant) -> Result<(), ControlError> {
        check_deadline(Some(end))?;
        crate::production_application::working_payload_birth::require_retired()
            .map_err(|e|ControlError::Invalid(e.to_string()))?;
        self.revalidate()?;
        if node(&self.pidfd)? != node(&main.pidfd)? || main.peer != self.observation()? {
            return Err(ControlError::Invalid("original installation uses another actual control peer".into()));
        }
        check_deadline(Some(end))
    }
    /// Complete untouched APKs are the only input. Package selection is checked
    /// against the compiled 41-app source; Main is an actual opaque observation.
    /// The receiving factory independently re-observes that same Main before any
    /// mutation, then performs Android's existing -r transaction without retry.
    pub fn install_working_application_until(&mut self, main: &MainCustodyObservation,
        package: &str, originals: &[&File], end: Instant) -> Result<WorkingOriginalInstallObservation, ControlError>
    {
        let end = end.min(Instant::now() + wire::PACKAGE_LIMIT);
        self.require_working_install_main(main, end)?;
        let expected = wire::application(package).map_err(ControlError::Invalid)?;
        let payload_end = end.min(Instant::now() + Duration::from_secs(120));
        let (empty, payload_birth) = crate::production_application::working_payload_birth::create(payload_end)
            .map_err(|e|ControlError::Invalid(e.to_string()))?;
        let (payload, lengths) = super::super::apk_payload::prepare_born_held_set_until(originals, empty, payload_end)?;
        payload_birth.require_payload(&payload).map_err(|e|ControlError::Invalid(e.to_string()))?;
        if lengths != expected.lengths() {
            return Err(ControlError::Invalid("source-held APK base/split lengths differ from the compiled set".into()));
        }
        expected.require_payload(&payload, payload_end).map_err(ControlError::Invalid)?;
        self.require_working_install_main(main, end)?;
        let request = WorkingInstallRequest::from_owned(main, package, end).map_err(ControlError::Invalid)?;
        let stream = progress::connect(Path::new(DEFAULT_CONTROL_SOCKET))
            .map_err(|e| io_error("connect normal original install owner", e))?;
        let peer = peer_credentials_checked(&stream)?;
        let fd = peer_pidfd(&stream).map_err(|e| io_error("retain normal install socket owner", e))?;
        if peer.pid as u32 != self.peer_pid || node(&fd)? != node(&self.pidfd)? {
            return Err(ControlError::Invalid("normal install socket changed actual owner".into()));
        }
        self.require_working_install_main(main, end)?;
        let response = progress::request_on_with_file_until(stream,
            &ControlRequest::InstallWorkingOriginals { request: request.clone() }, Some(&payload), end);
        let after = (|| { node(&fd)?; self.require_working_install_main(main, end) })();
        let response = match (response, after) {
            (Ok(value), Ok(())) => value,
            (Err(e), Ok(())) => return Err(e),
            (Ok(_), Err(e)) => return Err(e),
            (Err(e), Err(post)) => return Err(ControlError::Invalid(
                format!("{e}; original installation peer postcheck also failed: {post}"))),
        };
        if !response.ok || response.state != CellState::Running
            || response.host_pid != Some(main.facts().epoch.cell_host_pid) {
            return Err(ControlError::Invalid(format!(
                "normal original APK install failed; no automatic retry and no data deletion: {}", response.message)));
        }
        let raw = response.diagnostics.as_deref()
            .ok_or_else(|| ControlError::Invalid("actual original installation receipt absent".into()))?;
        if raw.len() > wire::MAX_REPLY_BYTES {
            return Err(ControlError::Invalid("actual original installation receipt exceeded its bound".into()));
        }
        let reply: WorkingInstallReply = serde_json::from_str(raw)?;
        reply.validate(&request).map_err(ControlError::Invalid)?;
        self.require_working_install_main(main, end)?;
        payload_birth.require_payload(&payload).map_err(|e|ControlError::Invalid(e.to_string()))?;
        Ok(WorkingOriginalInstallObservation { reply, peer_pidfd: fd, peer: self.observation()?, payload_birth })
    }
}
