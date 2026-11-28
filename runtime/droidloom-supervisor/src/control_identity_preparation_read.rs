//! Fixed PreparationRead requests through the original authenticated normal owner.
//!
//! Only live Main/complete-PM observations enter this method. The request's
//! source-owned literal parser selects a closed operation; no raw argv, PID,
//! host executable, namespace descriptor or caller result is sent as authority.
use super::*;
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use crate::native_preparation_read::PreparationReadKind;
use crate::native_preparation_read::{PreparationReadReply, PreparationReadRequest};
use std::fs::File;
use std::process::Output;

/// Historical actual transport/execution observation. There is no public
/// constructor, Clone or Deserialize, and no operation can borrow it as Main.
pub(crate) struct PreparationReadObservation {
    reply: PreparationReadReply,
    output: Output,
    _peer_pidfd: File,
}
impl PreparationReadObservation {
    pub(crate) fn output(&self) -> &Output {
        &self.output
    }
    pub(crate) fn comparison(&self) -> Result<serde_json::Value, String> {
        self.reply.comparison()
    }
    pub(crate) fn matches_original(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
        kind: PreparationReadKind,
    ) -> bool {
        self.reply.matches_original(main, application, kind)
            && self.output.status.success()
            && self.output.stdout == kind.expected_stdout()
            && self.output.stderr.is_empty()
    }
}

impl NativeApplicationInspector {
    pub(crate) fn execute_preparation_read_until(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        kind: PreparationReadKind,
        end: Instant,
    ) -> Result<PreparationReadObservation, ControlError> {
        self.require_observations_local(main, application, end)?;
        if application.facts().user != 0 || application.facts().epoch.boot_id != self.boot_id {
            return Err(ControlError::Invalid(
                "preparation read actual application differs from the original user-0 owner".into(),
            ));
        }
        let request =
            PreparationReadRequest::from_owned(main.facts(), application.facts(), kind, end)
                .map_err(ControlError::Invalid)?;
        check_deadline(Some(end))?;
        // connect is nonblocking and never retries a full accept queue. A fresh
        // connection allows this borrowed Inspector method to keep its original
        // peer/PIDFD while the existing request framing owns the stream.
        let stream = progress::connect(Path::new(DEFAULT_CONTROL_SOCKET))
            .map_err(|e| io_error("connect fixed preparation read peer", e))?;
        let peer = peer_credentials_checked(&stream)?;
        let current_pidfd = peer_pidfd(&stream)
            .map_err(|e| io_error("capture current preparation read peer", e))?;
        let current = current_pidfd
            .metadata()
            .map_err(|e| io_error("stat current preparation read peer", e))?;
        let original = self
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat original preparation read peer", e))?;
        if peer.pid as u32 != self.peer_pid
            || (current.dev(), current.ino()) != (original.dev(), original.ino())
        {
            return Err(ControlError::Invalid(
                "preparation read socket was replaced by another daemon".into(),
            ));
        }
        self.require_observations_local(main, application, end)?;
        let result = progress::request_on_until(
            stream,
            &ControlRequest::ObservePreparationRead {
                request: request.clone(),
            },
            end,
        );
        // Always recheck actual custody, including on a failed request. Preserve
        // the first request error if the postcheck also fails; never retry an
        // operation whose execution or retirement was not proven.
        let after = (|| {
            live(&current_pidfd)
                .map_err(|e| io_error("recheck current preparation read peer", e))?;
            self.require_observations_local(main, application, end)
        })();
        let response = match (result, after) {
            (Ok(response), Ok(())) => response,
            (Err(error), Ok(())) => return Err(error),
            (Ok(_), Err(error)) => return Err(error),
            (Err(error), Err(post)) => {
                return Err(ControlError::Invalid(format!(
                    "{error}; preparation read original custody postcheck also failed: {post}"
                )));
            }
        };
        let body = gateway_body(&response, main.facts().epoch.cell_host_pid)?;
        let reply: PreparationReadReply = serde_json::from_str(body)?;
        let output = reply.output_for(&request).map_err(ControlError::Invalid)?;
        self.require_observations_local(main, application, end)?;
        Ok(PreparationReadObservation {
            reply,
            output,
            _peer_pidfd: current_pidfd,
        })
    }
}

fn gateway_body(response: &ControlResponse, host_pid: u32) -> Result<&str, ControlError> {
    if !response.ok || response.state != CellState::Running || response.host_pid != Some(host_pid) {
        return Err(ControlError::Invalid(format!(
            "preparation read response failed or belongs to another actual owner: {}",
            response.message
        )));
    }
    response.diagnostics.as_deref().ok_or_else(|| {
        ControlError::Invalid("preparation read actual gateway reply is absent".into())
    })
}
