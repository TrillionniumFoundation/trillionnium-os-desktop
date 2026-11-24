//! The fixed public application transport borrowed by the early resource owner.
//! Every request is dispatched against that owner's live capabilities.
use super::*;

pub(crate) struct EarlyApplicationControl {
    listener: OwnedListener,
}
impl EarlyApplicationControl {
    pub(crate) fn bind(
        owner: &crate::production_execution::RuntimeMacOwner,
    ) -> Result<Self, ControlError> {
        owner
            .objects()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        let root = trusted_directory(libc::AT_FDCWD, c"/")?;
        let run = trusted_directory(root.as_raw_fd(), c"run")?;
        let parent = trusted_directory(run.as_raw_fd(), c"droidloom")?;
        let issuer = HostPeerIssuer::broker(owner.clone()).map_err(selected_socket_control)?;
        let listener = OwnedListener::bind_selected_at(
            parent,
            issuer,
            Instant::now() + Duration::from_secs(10),
        )?
        .initialize()?;
        owner
            .objects()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        Ok(Self { listener })
    }
    pub(crate) fn poll<'owner>(
        &mut self,
        host_pid: u32,
        host_uid: u32,
        acquire: impl FnOnce() -> std::result::Result<
            crate::production_selection::early_generation::EarlyApplicationAuthority<'owner>,
            crate::production_namespace::NamespaceError,
        >,
    ) -> Result<(), ControlError> {
        let mut accepted = match self.listener.accept() {
            Ok(value) => value,
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) =>
            {
                return Ok(());
            }
            Err(e) => return Err(io_error("accept original early application client", e)),
        };
        let stream = accepted
            .stream_mut()
            .map_err(|e| io_error("observe early application client", e))?;
        let mut response = ControlResponse {
            ok: false,
            state: CellState::Starting,
            message: String::new(),
            host_pid: Some(host_pid),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: None,
            inspection: None,
            image_custody: None,
        };
        let mut authority = None;
        let mut acquisition_quarantined = false;
        let handled = (|| -> Result<(), ControlError> {
            let (peer, request, file, streaming) = receive_request(stream)?;
            authorize_uid(peer, host_uid)?;
            if file.is_some() {
                return Err(ControlError::Invalid(
                    "early application control does not accept a descriptor".into(),
                ));
            }
            // Request-local acquisition starts only after transport admission.
            // While original init is crossing stock exec, report Starting to
            // the caller and keep the actual boot owner/frontend loop alive.
            authority = Some(match acquire() {
                Ok(value) => value,
                Err(error) => {
                    acquisition_quarantined = matches!(
                        error,
                        crate::production_namespace::NamespaceError::RetirementUnproven,
                    );
                    return Err(ControlError::Invalid(error.to_string()));
                }
            });
            let authority = authority
                .as_ref()
                .expect("acquired original application owner");
            let progress = Reporter::new(stream, streaming)?;
            match request {
                ControlRequest::InspectApplication { package, user } => {
                    validate_package(&package)?;
                    validate_android_user(user)?;
                    progress.report(
                        "Reading the current Android package and exact installed APK bytes...",
                    );
                    let inspection =
                        crate::production_application::inspect_early(authority, &package, user)
                            .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    response.inspection = Some(inspection);
                    response.message = "Current package metadata and APK bytes observed in the original early Android generation; application acceptance remains pending".into();
                }
                ControlRequest::Status | ControlRequest::Readiness => {
                    authority
                        .ready()
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    authority
                        .observe_framework()
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    response.message = "The original early Android init completed boot and its current framework lineage is live".into();
                }
                _ => {
                    return Err(ControlError::Invalid(
                        "this early application operation requires its fixed owned-tree adapter"
                            .into(),
                    ));
                }
            }
            authority
                .ready()
                .map_err(|e| ControlError::Invalid(e.to_string()))?;
            response.state = CellState::Running;
            response.ok = true;
            Ok(())
        })();
        if let Err(error) = handled {
            response.message = error.to_string();
        }
        // A command that could not retire its real children quarantines the
        // original cgroup. That failure must leave the main service loop.
        let original = if acquisition_quarantined {
            Err(ControlError::Invalid(
                "original metadata helper retirement remains quarantined".into(),
            ))
        } else {
            authority.as_ref().map_or(Ok(()), |authority| {
                authority
                    .revalidate()
                    .map_err(|e| ControlError::Invalid(e.to_string()))
            })
        };
        if original.is_err() {
            response.ok = false;
            response.state = CellState::Quarantined;
        }
        if let Err(error) = send_response(stream, &response) {
            eprintln!("could not deliver early application observation: {error}");
        }
        original
    }
    pub(crate) fn retire(self) -> Result<(), ControlError> {
        self.listener.retire()
    }
}
