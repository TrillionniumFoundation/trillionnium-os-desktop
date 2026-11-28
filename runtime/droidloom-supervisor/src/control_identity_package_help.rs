//! Fixed DocumentsUI package-help query through the original authenticated normal owner.
//!
//! Only live Main/complete-PM observations enter this method. The request's
//! source-owned literal parser selects a closed operation; no raw argv, PID,
//! host executable, namespace descriptor or caller result is sent as authority.
use super::*;
use crate::native_package_help::{PackageHelpReply, PackageHelpRequest};
use std::fs::File;
use std::process::Output;

/// Historical actual transport/execution observation. There is no public
/// constructor, Clone or Deserialize, and no operation can borrow it as Main.
pub struct PackageHelpObservation {
    reply: PackageHelpReply,
    output: Output,
    _peer_pidfd: File,
}
impl PackageHelpObservation {
    pub fn output(&self) -> &Output {
        &self.output
    }
    pub fn comparison(&self) -> Result<serde_json::Value, String> {
        self.reply.comparison()
    }
    /// Bind this historical output to the same still-live Main/PM peer.
    /// This never turns a nonzero command exit into successful preparation.
    pub fn require_main(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
    ) -> Result<(), ControlError> {
        let id = |file: &File| -> Result<(u64, u64), ControlError> {
            live(file).map_err(|e| io_error("recheck package help peer", e))?;
            let m = file.metadata().map_err(|e| io_error("stat package help peer", e))?;
            Ok((m.dev(), m.ino()))
        };
        let own = id(&self._peer_pidfd)?;
        if own != id(&main.pidfd)?
            || own != id(&application.pidfd)?
            || main.peer != application.peer
            || !self.reply.matches_original(main.facts(), application.facts())
        {
            return Err(ControlError::Invalid(
                "package help output belongs to another actual Main/PM peer".into(),
            ));
        }
        live(&self._peer_pidfd).map_err(|e| io_error("finish package help peer check", e))
    }
}

impl NativeApplicationInspector {
    pub fn observe_package_help_until(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        end: Instant,
    ) -> Result<PackageHelpObservation, ControlError> {
        self.require_observations_local(main, application, end)?;
        if application.facts().user != 0 || application.facts().epoch.boot_id != self.boot_id {
            return Err(ControlError::Invalid(
                "package help actual application differs from the original user-0 owner".into(),
            ));
        }
        let request =
            PackageHelpRequest::from_owned(main.facts(), application.facts(), end)
                .map_err(ControlError::Invalid)?;
        check_deadline(Some(end))?;
        // connect is nonblocking and never retries a full accept queue. A fresh
        // connection allows this borrowed Inspector method to keep its original
        // peer/PIDFD while the existing request framing owns the stream.
        let stream = progress::connect(Path::new(DEFAULT_CONTROL_SOCKET))
            .map_err(|e| io_error("connect fixed package help peer", e))?;
        let peer = peer_credentials_checked(&stream)?;
        let current_pidfd = peer_pidfd(&stream)
            .map_err(|e| io_error("capture current package help peer", e))?;
        let current = current_pidfd
            .metadata()
            .map_err(|e| io_error("stat current package help peer", e))?;
        let original = self
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat original package help peer", e))?;
        if peer.pid as u32 != self.peer_pid
            || (current.dev(), current.ino()) != (original.dev(), original.ino())
        {
            return Err(ControlError::Invalid(
                "package help socket was replaced by another daemon".into(),
            ));
        }
        self.require_observations_local(main, application, end)?;
        let result = progress::request_on_until(
            stream,
            &ControlRequest::ObservePackageHelp {
                request: request.clone(),
            },
            end,
        );
        // Always recheck actual custody, including on a failed request. Preserve
        // the first request error if the postcheck also fails; never retry an
        // operation whose execution or retirement was not proven.
        let after = (|| {
            live(&current_pidfd)
                .map_err(|e| io_error("recheck current package help peer", e))?;
            self.require_observations_local(main, application, end)
        })();
        let response = match (result, after) {
            (Ok(response), Ok(())) => response,
            (Err(error), Ok(())) => return Err(error),
            (Ok(_), Err(error)) => return Err(error),
            (Err(error), Err(post)) => {
                return Err(ControlError::Invalid(format!(
                    "{error}; package help original custody postcheck also failed: {post}"
                )));
            }
        };
        let body = gateway_body(&response, main.facts().epoch.cell_host_pid)?;
        let reply: PackageHelpReply = serde_json::from_str(body)?;
        let output = reply.output_for(&request).map_err(ControlError::Invalid)?;
        self.require_observations_local(main, application, end)?;
        Ok(PackageHelpObservation {
            reply,
            output,
            _peer_pidfd: current_pidfd,
        })
    }
}

fn gateway_body(response: &ControlResponse, host_pid: u32) -> Result<&str, ControlError> {
    if !response.ok || response.state != CellState::Running || response.host_pid != Some(host_pid) {
        return Err(ControlError::Invalid(format!(
            "package help response failed or belongs to another actual owner: {}",
            response.message
        )));
    }
    response.diagnostics.as_deref().ok_or_else(|| {
        ControlError::Invalid("package help actual gateway reply is absent".into())
    })
}
