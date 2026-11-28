//! Fixed NativeUi requests through the original authenticated normal owner.
//!
//! Only live Main/complete-PM observations enter this method. The request's
//! source-owned literal parser selects a closed operation; no raw argv, PID,
//! host executable, namespace descriptor or caller result is sent as authority.
use super::*;
use crate::native_application_ui_gateway::{GatewayReply, GatewayRequest};
use std::process::Output;

impl NativeApplicationInspector {
    pub(crate) fn execute_native_ui_until(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        literal: &[String],
        shell: bool,
        end: Instant,
    ) -> Result<Output, ControlError> {
        let (_, _, output) =
            self.execute_native_ui_observed_until(main, application, literal, shell, end)?;
        Ok(output)
    }

    // Source-private shared transport for fixed typed read observers. Returning
    // these comparisons requires this actual authenticated request, its genuine
    // query retirement and the same before/after opaque owner. No saved reply
    // can enter this factory.
    pub(super) fn execute_native_ui_observed_until(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        literal: &[String],
        shell: bool,
        end: Instant,
    ) -> Result<(GatewayRequest, GatewayReply, Output), ControlError> {
        self.require_observations_local(main, application, end)?;
        if application.facts().user != 0 || application.facts().epoch.boot_id != self.boot_id {
            return Err(ControlError::Invalid(
                "native UI actual application differs from the original user-0 owner".into(),
            ));
        }
        let request =
            GatewayRequest::from_owned(main.facts(), application.facts(), literal, shell, end)
                .map_err(ControlError::Invalid)?;
        check_deadline(Some(end))?;
        // connect is nonblocking and never retries a full accept queue. A fresh
        // connection allows this borrowed Inspector method to keep its original
        // peer/PIDFD while the existing request framing owns the stream.
        let stream = progress::connect(Path::new(DEFAULT_CONTROL_SOCKET))
            .map_err(|e| io_error("connect fixed native UI peer", e))?;
        let peer = peer_credentials_checked(&stream)?;
        let current_pidfd =
            peer_pidfd(&stream).map_err(|e| io_error("capture current native UI peer", e))?;
        let current = current_pidfd
            .metadata()
            .map_err(|e| io_error("stat current native UI peer", e))?;
        let original = self
            .pidfd
            .metadata()
            .map_err(|e| io_error("stat original native UI peer", e))?;
        if peer.pid as u32 != self.peer_pid
            || (current.dev(), current.ino()) != (original.dev(), original.ino())
        {
            return Err(ControlError::Invalid(
                "native UI socket was replaced by another daemon".into(),
            ));
        }
        self.require_observations_local(main, application, end)?;
        let result = progress::request_on_until(
            stream,
            &ControlRequest::RunNativeUi {
                request: request.clone(),
            },
            end,
        );
        // Always recheck actual custody, including on a failed request. Preserve
        // the first request error if the postcheck also fails; never retry an
        // operation whose execution or retirement was not proven.
        let after = (|| {
            live(&current_pidfd).map_err(|e| io_error("recheck current native UI peer", e))?;
            self.require_observations_local(main, application, end)
        })();
        let response = match (result, after) {
            (Ok(response), Ok(())) => response,
            (Err(error), Ok(())) => return Err(error),
            (Ok(_), Err(error)) => return Err(error),
            (Err(error), Err(post)) => {
                return Err(ControlError::Invalid(format!(
                    "{error}; native UI original custody postcheck also failed: {post}"
                )));
            }
        };
        let body = gateway_body(&response, main.facts().epoch.cell_host_pid)?;
        let reply: GatewayReply = serde_json::from_str(body)?;
        let output = reply.output_for(&request).map_err(ControlError::Invalid)?;
        self.require_observations_local(main, application, end)?;
        Ok((request, reply, output))
    }
}

fn gateway_body(response: &ControlResponse, host_pid: u32) -> Result<&str, ControlError> {
    if !response.ok || response.state != CellState::Running || response.host_pid != Some(host_pid) {
        return Err(ControlError::Invalid(format!(
            "native UI response failed or belongs to another actual owner: {}",
            response.message
        )));
    }
    response
        .diagnostics
        .as_deref()
        .ok_or_else(|| ControlError::Invalid("native UI actual gateway reply is absent".into()))
}

#[cfg(test)]
mod tests {
    use super::*;

    // This exercises only the public comparison envelope. It cannot construct
    // either opaque input, a GatewayReply, or a successful live observation.
    #[test]
    fn native_ui_gateway_response_requires_running_same_owner_and_body() {
        let mut response = ControlResponse {
            ok: true,
            state: CellState::Running,
            message: "comparison fixture".into(),
            host_pid: Some(41),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: Some("comparison body".into()),
            inspection: None,
            image_custody: None,
            runtime_vintf: None,
        };
        assert_eq!(gateway_body(&response, 41).unwrap(), "comparison body");
        assert!(gateway_body(&response, 42).is_err());
        response.ok = false;
        assert!(gateway_body(&response, 41).is_err());
        response.ok = true;
        response.state = CellState::Starting;
        assert!(gateway_body(&response, 41).is_err());
        response.state = CellState::Running;
        response.host_pid = None;
        assert!(gateway_body(&response, 41).is_err());
        response.host_pid = Some(41);
        response.diagnostics = None;
        assert!(gateway_body(&response, 41).is_err());
    }
}
