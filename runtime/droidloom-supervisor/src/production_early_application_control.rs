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
        let listener = OwnedListener::bind_early_at(
            parent,
            owner.clone(),
            Instant::now() + Duration::from_secs(10),
        )?
        .initialize()?;
        owner
            .objects()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        Ok(Self { listener })
    }
    pub(crate) fn poll<'owner>(
        &self,
        host_pid: u32,
        host_uid: u32,
        acquire: impl FnOnce() -> std::result::Result<
            crate::production_selection::early_generation::EarlyApplicationAuthority<'owner>,
            crate::production_namespace::NamespaceError,
        >,
    ) -> Result<Option<crate::control::package::ServerTransaction<'_>>, ControlError> {
        let mut accepted = match self.listener.accept() {
            Ok(value) => value,
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) =>
            {
                return Ok(None);
            }
            Err(e) => return Err(io_error("accept original early application client", e)),
        };
        match crate::control::package::is_package(accepted.stream().map_err(|e| io_error("observe early package stream", e))?) {
            Ok(true) => {
                return match crate::control::package::ServerTransaction::receive(accepted.into_package()?) {
                    Ok(transaction) => Ok(Some(transaction)),
                    Err(error) => {
                        eprintln!("fixed early package transaction refused: {error}");
                        Ok(None)
                    }
                };
            }
            Ok(false) => {}
            Err(error) => {
                eprintln!("could not classify bounded early request: {error}");
                return Ok(None);
            }
        }
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
            let launch_deadline = Instant::now()
                .checked_add(droidloom_task_launcher::effects::LAUNCH_LIMIT)
                .ok_or_else(|| ControlError::Invalid("early launch deadline overflow".into()))?;
            authorize_uid(peer, host_uid)?;
            let installation = matches!(
                &request,
                ControlRequest::Install { .. } | ControlRequest::InstallMultiple { .. }
            );
            if file.is_some() != installation {
                return Err(ControlError::Invalid(
                    "only installation accepts exactly one original APK descriptor".into(),
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
                ControlRequest::ListApplications { user } => {
                    validate_android_user(user)?;
                    progress.report("Reading the current Android launcher catalog...");
                    let output = crate::production_application::catalog_early(
                        authority,
                        crate::production_application::CatalogCommand::List { user },
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    let applications: Vec<AndroidApplication> = serde_json::from_str(&output)
                        .map_err(|e| {
                            ControlError::Invalid(format!("Android catalog JSON differs: {e}"))
                        })?;
                    validate_application_catalog(&applications)?;
                    response.message = format!(
                        "observed {} enabled Android launcher activities",
                        applications.len()
                    );
                    response.applications = Some(applications);
                }
                ControlRequest::ApplicationIcon {
                    component,
                    user,
                    size,
                } => {
                    validate_component(&component)?;
                    validate_android_user(user)?;
                    if !(MIN_ICON_SIZE..=MAX_ICON_SIZE).contains(&size) {
                        return Err(ControlError::Invalid(
                            "application icon extent is outside the fixed bound".into(),
                        ));
                    }
                    progress.report("Rendering the current Android application icon...");
                    let icon = crate::production_application::catalog_early(
                        authority,
                        crate::production_application::CatalogCommand::Icon {
                            user,
                            component: component.clone(),
                            size,
                        },
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.message = format!("rendered Android application icon for {component}");
                    response.application_icon = Some(icon);
                }
                ControlRequest::Install { user } => {
                    validate_android_user(user)?;
                    let file = file.ok_or_else(|| {
                        ControlError::Invalid("original APK descriptor missing".into())
                    })?;
                    let bytes = apk::validate(&file)?;
                    progress.report(
                        "Installing the original APK through Android's atomic package session...",
                    );
                    let result = crate::production_application::install_early(
                        authority,
                        user,
                        file,
                        &[bytes],
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.message = format!(
                        "Android confirmed atomic install session {}; installed {} original APK bytes; application acceptance remains pending",
                        result.session, result.bytes
                    );
                }
                ControlRequest::InstallMultiple { user, lengths } => {
                    validate_android_user(user)?;
                    let file = file.ok_or_else(|| {
                        ControlError::Invalid("original APK set descriptor missing".into())
                    })?;
                    apk_set::validate(&file, &lengths)?;
                    progress.report("Installing the complete original APK split set atomically...");
                    let result = crate::production_application::install_early(
                        authority,
                        user,
                        file,
                        &lengths,
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.message = format!(
                        "Android confirmed atomic install session {} with {} original APK segments; application acceptance remains pending",
                        result.session,
                        result.segments.len()
                    );
                }
                ControlRequest::InspectApplication { package, user } => {
                    validate_package(&package)?;
                    validate_android_user(user)?;
                    progress.report(
                        "Reading the current Android package and exact installed APK bytes...",
                    );
                    let inspection = crate::production_application::inspect_with_custody_early(
                        authority, &package, user,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.image_custody = inspection.image_custody;
                    response.inspection = Some(inspection.application);
                    response.message = "Current package metadata and APK bytes observed in the original early Android generation; application acceptance remains pending".into();
                }
                ControlRequest::Launch {
                    spec,
                    package,
                    component,
                    resolution,
                    user,
                } => {
                    let request = early_launch_request(
                        &package,
                        component.as_deref(),
                        resolution.as_deref(),
                        user,
                    )?;
                    if Instant::now() >= launch_deadline {
                        return Err(ControlError::Invalid(
                            "early launch deadline expired".into(),
                        ));
                    }
                    let guard = ConfigurationReadGuard::acquire()
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    let selected = ProductionSelection::load(&guard, &spec, peer)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    authority
                        .verify_selection(&selected)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    progress
                        .report("Launching the application in the current Android generation...");
                    let observed = crate::production_application::launch_application_early(
                        authority,
                        &request,
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    guard
                        .revalidate()
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    authority
                        .verify_selection(&selected)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    if Instant::now() >= launch_deadline {
                        return Err(ControlError::Invalid(
                            "early launch completed after its absolute deadline".into(),
                        ));
                    }
                    let binding = observed.binding;
                    response.launch = Some(format!(
                        "object={} composer_display={} android_display={} task={}",
                        binding.object,
                        binding.composer_display,
                        binding.android_display,
                        binding.task,
                    ));
                    response.inspection = Some(observed.application);
                    response.message = format!("launched {package}");
                }
                ControlRequest::OpenBrowser { expected, url } => {
                    validate_android_user(expected.user)?;
                    application_probe::validate_https_url(&url).map_err(ControlError::Invalid)?;
                    progress.report("Opening the reviewed HTTPS page through Android's current browser resolver...");
                    let (inspection, output) = crate::production_application::open_browser_early(
                        authority, &expected, &url,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.inspection = Some(inspection);
                    response.launch = Some(output);
                    response.message = "Implicit Firefox HTTPS activity opened in the original early Android generation; rendered content, media and whole-app acceptance remain pending".into();
                }
                ControlRequest::InspectContactsFixture { contacts, provider } => {
                    progress.report("Reading the fixed Contacts provider baseline...");
                    let observed = crate::production_application::inspect_contacts_baseline_early(
                        authority, &contacts, &provider,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.inspection = Some(contacts);
                    response.diagnostics = Some(serde_json::to_string(&observed)?);
                    response.message = "Contacts provider baseline observed in the original early generation; account topology and create/edit/search/delete acceptance remain pending".into();
                }
                ControlRequest::SetDpi { spec, dpi } => {
                    validate_display_density(dpi)?;
                    let guard = ConfigurationReadGuard::acquire()
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    let selected = ProductionSelection::load(&guard, &spec, peer)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    authority.verify_selection(&selected)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    progress.report("Persisting and reading back Android's primary display density...");
                    let observed = crate::production_application::set_density_early(
                        authority, dpi, launch_deadline,
                    ).map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    guard.revalidate().map_err(|e| ControlError::Invalid(e.to_string()))?;
                    authority.verify_selection(&selected)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    response.message = format!("Android primary display density persisted and read back as {observed} dpi");
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
                "original application or metadata helper retirement remains quarantined".into(),
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
        original.map(|()| None)
    }
    pub(crate) fn retire(self) -> Result<(), ControlError> {
        self.listener.retire()
    }
}

fn early_application_error(
    error: crate::production_application::ApplicationError,
    quarantined: &mut bool,
) -> ControlError {
    *quarantined |= matches!(
        error,
        crate::production_application::ApplicationError::RetirementUnproven
    );
    ControlError::Invalid(error.to_string())
}

fn early_launch_request(
    package: &str,
    component: Option<&str>,
    resolution: Option<&str>,
    user: u32,
) -> Result<droidloom_task_launcher::LaunchRequest, ControlError> {
    validate_package(package)?;
    validate_android_user(user)?;
    if let Some(component) = component {
        validate_component(component)?;
        if component
            .split_once('/')
            .is_none_or(|(owner, _)| owner != package)
        {
            return Err(ControlError::Invalid(
                "launcher component belongs to another package".into(),
            ));
        }
    }
    let resolution = resolution
        .map(|value| {
            let checked = parse_launch_resolution(value)?;
            let (width, height) = checked.split_once('x').ok_or_else(|| {
                ControlError::Invalid("validated launch extent is incomplete".into())
            })?;
            let dimension = |value: &str| {
                value
                    .parse::<u32>()
                    .map_err(|_| ControlError::Invalid("invalid launch extent".into()))
            };
            Ok::<_, ControlError>((dimension(width)?, dimension(height)?))
        })
        .transpose()?;
    Ok(droidloom_task_launcher::LaunchRequest {
        package: package.into(),
        component: component.map(str::to_owned),
        resolution,
        user,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn early_public_launch_keeps_exact_package_alias_user_and_extent() {
        let request = early_launch_request(
            "org.mozilla.firefox",
            Some("org.mozilla.firefox/org.mozilla.firefox.App"),
            Some("1080x1920"),
            0,
        )
        .unwrap();
        assert_eq!(request.package, "org.mozilla.firefox");
        assert_eq!(
            request.component.as_deref(),
            Some("org.mozilla.firefox/org.mozilla.firefox.App")
        );
        assert_eq!(request.resolution, Some((1080, 1920)));
        assert!(
            early_launch_request("org.mozilla.firefox", Some("other.app/.Main"), None, 0).is_err()
        );
        assert!(early_launch_request("org.mozilla.firefox;id", None, None, 0).is_err());
        assert!(early_launch_request("org.mozilla.firefox", None, Some("0x1920"), 0).is_err());
        assert!(early_launch_request("org.mozilla.firefox", None, None, u32::MAX).is_err());
    }
}
