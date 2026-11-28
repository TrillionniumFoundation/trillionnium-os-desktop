//! The fixed public application transport borrowed by the early resource owner.
//! Every request is dispatched against that owner's live capabilities.
use super::*;
#[path = "production_native_leaf_apk_session.rs"]
mod apk_session;
#[path = "production_native_fixture_slot.rs"]
mod fixture_slot;

pub(crate) struct EarlyApplicationControl {
    // The session drops its reader and accepted stream before the listener.
    apk: std::cell::RefCell<Option<apk_session::Slot>>,
    fixture: std::cell::RefCell<fixture_slot::Slot>,
    listener: OwnedListener,
    account_key: crate::production_application::AccountAnonymityKey,
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
        let bind_deadline = Instant::now() + Duration::from_secs(10);
        let listener =
            OwnedListener::bind_early_at(parent, owner.clone(), bind_deadline)?.initialize()?;
        owner
            .objects()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        let account_key = crate::production_application::AccountAnonymityKey::new(bind_deadline)
            .map_err(|_| {
                ControlError::Invalid("private account observer initialization failed".into())
            })?;
        Ok(Self {
            apk: std::cell::RefCell::new(None),
            fixture: std::cell::RefCell::new(fixture_slot::Slot::default()),
            listener,
            account_key,
        })
    }
    pub(crate) fn poll<'owner>(
        &self,
        host_pid: u32,
        host_uid: u32,
        acquire: impl FnOnce(
            Option<Instant>,
        ) -> std::result::Result<
            crate::production_selection::early_generation::EarlyApplicationAuthority<'owner>,
            crate::production_namespace::NamespaceError,
        >,
    ) -> Result<Option<crate::control::package::ServerTransaction<'_>>, ControlError> {
        let apk_progress = {
            let mut slot=self.apk.borrow_mut();
            match slot.as_mut() {
                Some(slot)=>Some(slot.poll()),
                None=>None,
            }
        };
        match apk_progress {
            Some(Ok(apk_session::Progress::NeedOwner(end))) => {
                // Do not retain a RefCell borrow across a normal query's
                // progress callback. The real accepted stream still fences a
                // second APK session while this source-owned slot is local.
                let mut slot=self.apk.borrow_mut().take().expect("original APK slot");
                let result=(|| {
                    let authority=acquire(Some(end)).map_err(|e|ControlError::Invalid(e.to_string()))?;
                    slot.with_owner(&authority,end)
                })();
                if let Err(error)=result {
                    slot.retire()?;
                    return Err(error);
                }
                if self.apk.borrow().is_some() {
                    slot.retire()?;
                    return Err(ControlError::Invalid("APK slot was replaced during its owner callback".into()));
                }
                *self.apk.borrow_mut()=Some(slot);
                return Ok(None);
            }
            Some(Ok(apk_session::Progress::Done)) => {
                if let Some(mut slot)=self.apk.borrow_mut().take(){slot.retire()?;}
            }
            Some(Err(error)) => {
                if let Some(mut slot)=self.apk.borrow_mut().take(){slot.retire()?;}
                return Err(error);
            }
            Some(Ok(apk_session::Progress::Idle)) | None => {}
        }
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
        match crate::control::package::is_package(
            accepted
                .stream()
                .map_err(|e| io_error("observe early package stream", e))?,
        ) {
            Ok(true) => {
                return match crate::control::package::ServerTransaction::receive(
                    accepted.into_package()?,
                ) {
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
        let apk = crate::production_application::apk_transport::is_apk(
            accepted.stream().map_err(|e|io_error("classify original APK session",e))?.as_raw_fd())
            .map_err(|e|io_error("classify bounded APK magic",e))?;
        if apk {
            if self.apk.borrow().is_some() {
                return Err(ControlError::Invalid("one original APK session is already active".into()));
            }
            let slot=apk_session::Slot::accept(accepted.into_apk()?)?;
            *self.apk.borrow_mut()=Some(slot);
            return Ok(None);
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
            runtime_vintf: None,
        };
        let mut authority = None;
        let mut acquisition_quarantined = false;
        let mut vintf_budget = None;
        let mut vintf_failure = None;
        let mut preparation_peer = None;
        let mut empty_meituan_peer = None;
        let mut preparation_end = None;
        let mut preparation_failure = None;
        let mut native_ui_deadline = None;
        let mut native_ui_peer = None;
        let handled = (|| -> Result<(), ControlError> {
            let (peer, request, file, streaming) = receive_request(stream)?;
            let launch_deadline = Instant::now()
                .checked_add(droidloom_task_launcher::effects::LAUNCH_LIMIT)
                .ok_or_else(|| ControlError::Invalid("early launch deadline overflow".into()))?;
            let fixed_preparation_end = match &request {
                ControlRequest::ObservePreparationRead { request } => {
                    request.validate().map_err(ControlError::Invalid)?;
                    Some(request.deadline().map_err(ControlError::Invalid)?)
                }
                ControlRequest::ObservePackageHelp { request } => {
                    request.validate().map_err(ControlError::Invalid)?;
                    Some(request.deadline().map_err(ControlError::Invalid)?)
                }
                ControlRequest::InstallWorkingOriginals { request } => {
                    request.validate().map_err(ControlError::Invalid)?;
                    Some(request.deadline().map_err(ControlError::Invalid)?)
                }
                ControlRequest::InstallEmptyMeituan { request } => {
                    request.validate().map_err(ControlError::Invalid)?;
                    Some(request.deadline().map_err(ControlError::Invalid)?)
                }
                ControlRequest::InstallIhgHelper { request } => {
                    request.validate().map_err(ControlError::Invalid)?;
                    Some(request.deadline().map_err(ControlError::Invalid)?)
                }
                ControlRequest::ObserveIhgHelperState { request } => {
                    request.validate().map_err(ControlError::Invalid)?;
                    Some(request.deadline().map_err(ControlError::Invalid)?)
                }
                _ => None,
            };
            if let Some(end) = fixed_preparation_end {
                if matches!(&request,ControlRequest::InstallEmptyMeituan{..}) {
                    empty_meituan_peer=Some(crate::control::package::EmptyMeituanPeer::bind(stream,end)
                        .map_err(|e|io_error("admit fixed independent EMPTY peer",e))?);
                } else { preparation_peer = Some(
                    crate::control::package::PreparationPeer::bind(stream, end)
                        .map_err(|e| io_error("admit fixed preparation query peer", e))?,
                ); }
                preparation_end = Some(end);
            } else {
                authorize_uid(peer, host_uid)?;
            }
            if let ControlRequest::RunNativeUi { request } = &request {
                request.validate().map_err(ControlError::Invalid)?;
                let end = request.deadline().map_err(ControlError::Invalid)?;
                native_ui_deadline = Some(end);
                native_ui_peer = Some(
                    crate::control::package::NativeUiPeer::bind(stream, end)
                        .map_err(|e| io_error("admit actual normal native UI peer", e))?,
                );
            }
            if let ControlRequest::NativeFixture { request } = &request {
                request.validate().map_err(ControlError::Invalid)?;
                let end=request.deadline().map_err(ControlError::Invalid)?;
                native_ui_deadline=Some(end);
                native_ui_peer=Some(crate::control::package::NativeUiPeer::bind(stream,end)
                    .map_err(|e|io_error("admit actual physical fixture peer",e))?);
            }
            let installation = matches!(
                &request,
                ControlRequest::Install { .. } | ControlRequest::InstallMultiple { .. }
                    | ControlRequest::InstallWorkingOriginals { .. }
                    | ControlRequest::InstallEmptyMeituan { .. }
            );
            if file.is_some() != installation {
                return Err(ControlError::Invalid(
                    "only installation accepts exactly one original APK descriptor".into(),
                ));
            }
            // The finite read starts its one absolute budget before original
            // owner acquisition. Main custody uses this same metadata-only budget;
            // other request lifetimes keep their existing limits.
            vintf_budget = matches!(
                &request,
                ControlRequest::ObserveRuntimeVintf { .. }
                    | ControlRequest::ObserveRuntimeMain { .. }
                    | ControlRequest::ObserveCurrentRuntimeMain {}
                    | ControlRequest::ObserveApplicationEngine { .. }
                    | ControlRequest::ObserveUserZeroPackageInventory { .. }
                    | ControlRequest::ObserveApplicationExitState { .. }
                    | ControlRequest::ObserveApplicationPermissionState { .. }
                    | ControlRequest::ObserveApplicationAppOpsState { .. }
                    | ControlRequest::ObserveApplicationAccountState { .. }
            )
            .then(crate::production_application::RuntimeVintfBudget::start);
            let observation_deadline = preparation_end.or(native_ui_deadline)
                .or_else(|| vintf_budget.as_ref().map(|budget| budget.work_deadline()));
            // Request-local acquisition starts only after transport admission.
            // While original init is crossing stock exec, report Starting to
            // the caller and keep the actual boot owner/frontend loop alive.
            authority = Some(match acquire(observation_deadline) {
                Ok(value) => value,
                Err(error) => {
                    acquisition_quarantined = matches!(
                        error,
                        crate::production_namespace::NamespaceError::RetirementUnproven,
                    );
                    if let Some(deadline) = observation_deadline {
                        vintf_failure = Some(classify_vintf_failure(&error, deadline));
                        if preparation_end.is_some() {
                            preparation_failure = Some(classify_vintf_failure(&error, deadline));
                        }
                    }
                    return Err(ControlError::Invalid(error.to_string()));
                }
            });
            let authority = authority
                .as_ref()
                .expect("acquired original application owner");
            let progress = Reporter::new(stream, streaming)?;
            match request {
                ControlRequest::InstallEmptyMeituan { request } => {
                    let end=preparation_end.expect("admitted independent EMPTY end");
                    let caller=empty_meituan_peer.as_ref().expect("actual fixed EMPTY peer");
                    caller.revalidate(stream,end).map_err(|e|io_error("EMPTY caller precheck",e))?;
                    let payload=file.ok_or_else(||ControlError::Invalid("complete fixed official APK payload absent".into()))?;
                    let reply=crate::production_application::install_empty_meituan(authority,request,payload,end)
                        .map_err(|e|{preparation_failure=Some(classify_vintf_failure(&e,end));
                            early_application_error(e,&mut acquisition_quarantined)})?;
                    caller.revalidate(stream,end).map_err(|e|io_error("EMPTY caller postcheck",e))?;
                    let body=serde_json::to_string(&reply)?;
                    if body.len()>crate::native_empty_meituan_install::MAX_REPLY_BYTES {
                        return Err(ControlError::Invalid("complete EMPTY installation response exceeded bound".into()));
                    }
                    response.diagnostics=Some(body);
                    response.message="One official APK create-only transaction retired on the independent EMPTY generation; original data migration and business acceptance remain unqualified".into();
                }
                ControlRequest::ObservePreparationRead { request } => {
                    let end = preparation_end.expect("admitted fixed preparation read end");
                    let caller = preparation_peer
                        .as_ref()
                        .expect("admitted actual preparation peer");
                    caller
                        .revalidate(stream, end)
                        .map_err(|e| io_error("revalidate preparation caller", e))?;
                    let observed = crate::production_application::execute_preparation_read(
                        authority, request, end,
                    )
                    .map_err(|e| {
                        preparation_failure = Some(classify_vintf_failure(&e, end));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let reply =
                        crate::native_preparation_read::PreparationReadReply::from_observation(
                            &observed,
                        )
                        .map_err(ControlError::Invalid)?;
                    caller
                        .revalidate(stream, end)
                        .map_err(|e| io_error("finish preparation caller bookend", e))?;
                    let body = serde_json::to_string(&reply)?;
                    if body.len() > crate::native_preparation_read::MAX_RESPONSE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete preparation reply exceeds its bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message = "Fixed preparation diagnostic actually retired in the original Main; no UI or application acceptance issued".into();
                }
                ControlRequest::ObservePackageHelp { request } => {
                    let end = preparation_end.expect("admitted fixed package help end");
                    let caller = preparation_peer
                        .as_ref()
                        .expect("admitted actual preparation peer");
                    caller
                        .revalidate(stream, end)
                        .map_err(|e| io_error("revalidate preparation caller", e))?;
                    let observed = crate::production_application::execute_package_help(
                        authority, request, end,
                    )
                    .map_err(|e| {
                        preparation_failure = Some(classify_vintf_failure(&e, end));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let reply =
                        crate::native_package_help::PackageHelpReply::from_observation(
                            &observed,
                        )
                        .map_err(ControlError::Invalid)?;
                    caller
                        .revalidate(stream, end)
                        .map_err(|e| io_error("finish preparation caller bookend", e))?;
                    let body = serde_json::to_string(&reply)?;
                    if body.len() > crate::native_package_help::MAX_RESPONSE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete package help reply exceeds its bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message = "Fixed cmd package help actually retired in the original Main; no UI or application acceptance issued".into();
                }
                ControlRequest::InstallWorkingOriginals { request } => {
                    let end = preparation_end.expect("admitted original public APK installation end");
                    let caller = preparation_peer.as_ref().expect("actual fixed preparation peer");
                    caller.revalidate(stream, end).map_err(|e| io_error("public APK caller precheck", e))?;
                    let payload = file.ok_or_else(|| ControlError::Invalid("complete original APK payload absent".into()))?;
                    let reply = crate::production_application::install_working_originals(authority, request, payload, end)
                        .map_err(|e| {
                            preparation_failure = Some(classify_vintf_failure(&e, end));
                            early_application_error(e, &mut acquisition_quarantined)
                        })?;
                    caller.revalidate(stream, end).map_err(|e| io_error("public APK caller postcheck", e))?;
                    let body = serde_json::to_string(&reply)?;
                    if body.len() > crate::native_working_install::MAX_REPLY_BYTES {
                        return Err(ControlError::Invalid("complete public APK install reply exceeds its bound".into()));
                    }
                    response.diagnostics = Some(body);
                    response.message = "Normal original APK replace transaction retired in the same working-copy Main; fresh PM and business verification remain pending".into();
                }
                ControlRequest::InstallIhgHelper { request } => {
                    let end = preparation_end.expect("admitted original IHG installation end");
                    let caller = preparation_peer.as_ref().expect("admitted actual preparation peer");
                    caller.revalidate(stream,end).map_err(|e|io_error("IHG preparation caller precheck",e))?;
                    let reply = crate::production_application::install_ihg_helper(authority,request,end)
                        .map_err(|e| {
                            preparation_failure=Some(classify_vintf_failure(&e,end));
                            early_application_error(e,&mut acquisition_quarantined)
                        })?;
                    caller.revalidate(stream,end).map_err(|e|io_error("IHG preparation caller postcheck",e))?;
                    let body=serde_json::to_string(&reply)?;
                    if body.len()>crate::native_ihg_helper::MAX_RESPONSE_BYTES {
                        return Err(ControlError::Invalid("complete IHG installation reply too large".into()));
                    }
                    response.diagnostics=Some(body);
                    response.message="Source-fixed IHG helper create-only transaction retired; actual Main and complete inventory bookends retained".into();
                }
                ControlRequest::ObserveIhgHelperState { request } => {
                    let end=preparation_end.expect("admitted original IHG state end");
                    let caller=preparation_peer.as_ref().expect("admitted actual preparation peer");
                    caller.revalidate(stream,end).map_err(|e|io_error("IHG state caller precheck",e))?;
                    let reply=crate::production_application::observe_ihg_helper_state(authority,request,end)
                        .map_err(|e| {
                            preparation_failure=Some(classify_vintf_failure(&e,end));
                            early_application_error(e,&mut acquisition_quarantined)
                        })?;
                    caller.revalidate(stream,end).map_err(|e|io_error("IHG state caller postcheck",e))?;
                    let body=serde_json::to_string(&reply)?;
                    if body.len()>crate::native_ihg_helper::MAX_RESPONSE_BYTES {
                        return Err(ControlError::Invalid("complete IHG state reply too large".into()));
                    }
                    response.diagnostics=Some(body);
                    response.message="Fixed IHG state-only instrumentation retired in the same original Main; no target launch or business acceptance issued".into();
                }
                ControlRequest::NativeFixture { request } => {
                    let end=native_ui_deadline.expect("admitted original fixture operation end");
                    let caller=native_ui_peer.take().expect("actual normal physical fixture peer");
                    let value=fixture_slot::Slot::execute(&self.fixture,authority,stream,caller,request,end)
                        .map_err(|e|{
                            vintf_failure=Some(classify_vintf_failure(&e,end));
                            early_application_error(e,&mut acquisition_quarantined)
                        })?;
                    let body=serde_json::to_string(&value)?;
                    if body.len()>crate::native_leaf_fixture::MAX_RESPONSE_BYTES {
                        return Err(ControlError::Invalid("complete actual fixture reply exceeds its fixed bound".into()));
                    }
                    response.diagnostics=Some(body);
                    response.message="Source-owned fixture transaction retired in the same Main; no business or production acceptance issued".into();
                }
                ControlRequest::RunNativeUi { request } => {
                    let deadline =
                        native_ui_deadline.expect("admitted original native UI deadline");
                    let observed = crate::production_application::execute_native_ui(
                        authority, request, deadline,
                    )
                    .map_err(|error| {
                        vintf_failure = Some(classify_vintf_failure(&error, deadline));
                        early_application_error(error, &mut acquisition_quarantined)
                    })?;
                    let reply =
                        crate::native_application_ui_gateway::GatewayReply::from_observation(
                            &observed,
                        )
                        .map_err(ControlError::Invalid)?;
                    let body = serde_json::to_string(&reply)?;
                    if body.len() > crate::native_application_ui_gateway::MAX_RESPONSE_BYTES {
                        return Err(ControlError::Invalid(
                            "native UI response exceeds its fixed bound".into(),
                        ));
                    }
                    native_ui_peer
                        .as_ref()
                        .expect("actual native UI peer")
                        .revalidate(stream, deadline)
                        .map_err(|error| {
                            vintf_failure = Some(classify_vintf_failure(&error, deadline));
                            io_error("revalidate actual native UI peer", error)
                        })?;
                    response.diagnostics = Some(body);
                    response.message = "Fixed native UI command executed and retired by the original factory; actual status and complete output are retained for its operation journal".into();
                }
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
                ControlRequest::ObserveRuntimeVintf { expected_epoch } => {
                    progress.report("Reading fixed public VINTF, APEX and properties in the current Ready generation...");
                    let observed = crate::production_application::observe_runtime_vintf(
                        authority,
                        &expected_epoch,
                        vintf_budget.as_ref().expect("fixed VINTF request budget"),
                    )
                    .map_err(|e| {
                        let deadline = vintf_budget
                            .as_ref()
                            .expect("fixed VINTF budget")
                            .work_deadline();
                        vintf_failure = Some(classify_vintf_failure(&e, deadline));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    response.runtime_vintf = Some(observed);
                    response.message = "Public runtime metadata observed with unchanged owner and namespace bookends; VINTF compatibility and application acceptance remain unevaluated".into();
                }
                ControlRequest::ObserveApplicationExitState {
                    package,
                    expected_epoch,
                } => {
                    validate_package(&package)?;
                    if !crate::engine_custody::selected_package(&package) {
                        return Err(ControlError::Invalid(
                            "exit-state requires a source-selected application".into(),
                        ));
                    }
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed exit-state request budget")
                        .work_deadline();
                    let observed = crate::production_application::read_application_exit_state(
                        authority,
                        &package,
                        &expected_epoch,
                        deadline,
                    )
                    .map_err(|e| {
                        vintf_failure = Some(classify_vintf_failure(&e, deadline));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let facts =
                        crate::application_exit_state::ApplicationExitStateFacts::from_actual(
                            &observed,
                            &expected_epoch,
                        )
                        .map_err(ControlError::Invalid)?;
                    let body = serde_json::to_string(&facts)?;
                    if body.len() > crate::application_exit_state::MAX_WIRE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete exit-state exceeded its fixed bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message="Complete selected-package exit history observed with actual query retirement; elapsed stability and business acceptance remain separate".into();
                }
                ControlRequest::ObserveApplicationPermissionState {
                    package,
                    expected_epoch,
                } => {
                    validate_package(&package)?;
                    if !crate::engine_custody::selected_package(&package) {
                        return Err(ControlError::Invalid(
                            "PM-permission requires a source-selected application".into(),
                        ));
                    }
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed PM-permission request budget")
                        .work_deadline();
                    let observed =
                        crate::production_application::read_application_permission_state(
                            authority,
                            &package,
                            &expected_epoch,
                            deadline,
                        )
                        .map_err(|e| {
                            vintf_failure = Some(classify_vintf_failure(&e, deadline));
                            early_application_error(e, &mut acquisition_quarantined)
                        })?;
                    let facts=crate::application_permission_state::ApplicationPermissionStateFacts::from_actual(
                        &observed,&expected_epoch,
                    ).map_err(ControlError::Invalid)?;
                    let body = serde_json::to_string(&facts)?;
                    if body.len() > crate::application_permission_state::MAX_WIRE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete PM-permission exceeded its fixed bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message="Complete user-zero PackageManager permissions observed with actual query retirement; account, AppOps, persistent data and acceptance remain separate".into();
                }
                ControlRequest::ObserveApplicationAppOpsState {
                    package,
                    expected_epoch,
                } => {
                    validate_package(&package)?;
                    if !crate::engine_custody::selected_package(&package) {
                        return Err(ControlError::Invalid(
                            "AppOps requires a source-selected application".into(),
                        ));
                    }
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed AppOps request budget")
                        .work_deadline();
                    let observed = crate::production_application::read_application_appops_state(
                        authority,
                        &package,
                        &expected_epoch,
                        deadline,
                    )
                    .map_err(|e| {
                        vintf_failure = Some(classify_vintf_failure(&e, deadline));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let facts =
                        crate::application_appops_state::ApplicationAppOpsStateFacts::from_actual(
                            &observed,
                            &expected_epoch,
                        )
                        .map_err(ControlError::Invalid)?;
                    let body = serde_json::to_string(&facts)?;
                    if body.len() > crate::application_appops_state::MAX_WIRE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete AppOps exceeded its fixed bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message="Complete user-zero scoped AppOps modes observed with actual query retirement; account, PM permissions, persistent data and acceptance remain separate".into();
                }
                ControlRequest::ObserveApplicationAccountState {
                    package,
                    expected_epoch,
                } => {
                    validate_package(&package)?;
                    if !crate::engine_custody::selected_package(&package) {
                        return Err(ControlError::Invalid(
                            "Account requires a source-selected application".into(),
                        ));
                    }
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed Account request budget")
                        .work_deadline();
                    let observed = crate::production_application::read_application_account_state(
                        authority,
                        &self.account_key,
                        &package,
                        &expected_epoch,
                        deadline,
                    )
                    .map_err(|e| {
                        vintf_failure = Some(classify_vintf_failure(&e, deadline));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let facts=crate::application_account_state::ApplicationAccountStateFacts::from_actual(
                        &observed,&expected_epoch,
                    ).map_err(ControlError::Invalid)?;
                    let body = serde_json::to_string(&facts)?;
                    if body.len() > crate::application_account_state::MAX_WIRE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete Account exceeded its fixed bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message="Anonymous registered-account and target-visibility comparison observed with actual query retirement; no credential, login-state, persistent-data or acceptance result is claimed".into();
                }
                ControlRequest::ObserveUserZeroPackageInventory { expected_epoch } => {
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed user-0 inventory budget")
                        .work_deadline();
                    let observed = crate::production_application::read_user_zero_package_inventory(
                        authority, deadline,
                    )
                    .map_err(|e| {
                        vintf_failure = Some(classify_vintf_failure(&e, deadline));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let facts = crate::package_inventory_observation::UserZeroPackageInventoryFacts::from_actual(
                        &observed, &expected_epoch,
                    ).map_err(ControlError::Invalid)?;
                    let body = serde_json::to_string(&facts)?;
                    if body.len() > crate::package_inventory_observation::MAX_WIRE_BYTES {
                        return Err(ControlError::Invalid(
                            "complete user-0 inventory exceeded its bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message = "Complete user-0 package UID table observed with actual query retirement; package business and data contents remain unevaluated".into();
                }
                ControlRequest::ObserveRuntimeMain { expected_epoch } => {
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed Main request budget")
                        .work_deadline();
                    let observed = authority
                        .observe_main_custody(&expected_epoch, deadline)
                        .map_err(|e| {
                            vintf_failure = Some(classify_vintf_failure(&e, deadline));
                            acquisition_quarantined |= matches!(
                                e,
                                crate::production_namespace::NamespaceError::RetirementUnproven
                            );
                            ControlError::Invalid(e.to_string())
                        })?;
                    let body = serde_json::to_string(&observed)?;
                    if body.len() > 32768 {
                        return Err(ControlError::Invalid(
                            "fixed Main observation exceeds its bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message = "Current Main and writable resource custody observed; data-origin business acceptance remains separate".into();
                }
                ControlRequest::ObserveCurrentRuntimeMain {} => {
                    let deadline = vintf_budget
                        .as_ref()
                        .expect("fixed current Main request budget")
                        .work_deadline();
                    let observed =
                        authority
                            .observe_current_main_custody(deadline)
                            .map_err(|e| {
                                vintf_failure = Some(classify_vintf_failure(&e, deadline));
                                acquisition_quarantined |=
                                    matches!(
                                e, crate::production_namespace::NamespaceError::RetirementUnproven);
                                ControlError::Invalid(e.to_string())
                            })?;
                    let body = serde_json::to_string(&observed)?;
                    if body.len() > 32768 {
                        return Err(ControlError::Invalid(
                            "fixed current Main observation exceeds its bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message = "Actual current Ready Main and storage owner observed; application and original-data business acceptance remain separate".into();
                }
                ControlRequest::ObserveApplicationEngine {
                    package,
                    user,
                    expected_epoch,
                } => {
                    validate_package(&package)?;
                    if user != 0 || !crate::engine_custody::selected_package(&package) {
                        return Err(ControlError::Invalid(
                            "engine observation requires a fixed selected user-0 package".into(),
                        ));
                    }
                    let budget = vintf_budget
                        .as_ref()
                        .expect("fixed engine observation budget");
                    let observed = crate::production_application::observe_running_engine(
                        authority,
                        &package,
                        user,
                        &expected_epoch,
                        budget,
                    )
                    .map_err(|e| {
                        vintf_failure = Some(classify_vintf_failure(&e, budget.work_deadline()));
                        early_application_error(e, &mut acquisition_quarantined)
                    })?;
                    let body = serde_json::to_string(&observed)?;
                    if body.len() > crate::engine_custody::MAX_WIRE_BYTES {
                        return Err(ControlError::Invalid(
                            "engine observation exceeds its bound".into(),
                        ));
                    }
                    response.diagnostics = Some(body);
                    response.message="Actual running package engine mapping observed; translation business acceptance remains separate".into();
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
                ControlRequest::ObserveApplicationTasks { expected } => {
                    progress.report("Reading this package's current Android task metadata...");
                    let observed = crate::production_application::observe_application_tasks_early(
                        authority,
                        &expected,
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    response.inspection = Some(observed.application.clone());
                    response.diagnostics = Some(serde_json::to_string(&observed)?);
                    response.message = "Current package task metadata observed in the original early generation; host pixels, close authority and business acceptance remain pending".into();
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
                    authority
                        .verify_selection(&selected)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    progress
                        .report("Persisting and reading back Android's primary display density...");
                    let observed = crate::production_application::set_density_early(
                        authority,
                        dpi,
                        launch_deadline,
                    )
                    .map_err(|e| early_application_error(e, &mut acquisition_quarantined))?;
                    guard
                        .revalidate()
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    authority
                        .verify_selection(&selected)
                        .map_err(|e| ControlError::Invalid(e.to_string()))?;
                    response.message = format!(
                        "Android primary display density persisted and read back as {observed} dpi"
                    );
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
            authority.ready().map_err(|e| {
                if let Some(deadline) = observation_deadline {
                    vintf_failure = Some(classify_vintf_failure(&e, deadline));
                    if preparation_end.is_some() {
                        preparation_failure = Some(classify_vintf_failure(&e, deadline));
                    }
                    acquisition_quarantined |= matches!(
                        e,
                        crate::production_namespace::NamespaceError::RetirementUnproven
                    );
                }
                ControlError::Invalid(e.to_string())
            })?;
            response.state = CellState::Running;
            response.ok = true;
            Ok(())
        })();
        if let Err(error) = handled {
            response.message = error.to_string();
            if preparation_end.is_some() {
                preparation_failure.get_or_insert(VintfFailure::Other);
                response.diagnostics = None;
            }
            if vintf_budget.is_some() || native_ui_deadline.is_some() {
                vintf_failure.get_or_insert(VintfFailure::Other);
                response.runtime_vintf = None;
                response.diagnostics = None;
            }
        }
        // A command that could not retire its real children quarantines the
        // original cgroup. That failure must leave the main service loop.
        let original = if acquisition_quarantined {
            Err(ControlError::Invalid(
                "original application or metadata helper retirement remains quarantined".into(),
            ))
        } else if let Some(end) = preparation_end {
            finish_bounded_request(
                &mut response,
                preparation_failure,
                end,
                || authority.as_ref().map_or(Ok(()), |owner| owner.revalidate()),
                || authority.as_ref().map_or(Ok(()), |owner| owner.expired_request_bookend(end)),
                "Fixed preparation request exhausted its original absolute deadline; no result was accepted",
            )
        } else if let Some(deadline) = native_ui_deadline
            .or_else(|| vintf_budget.as_ref().map(|budget| budget.work_deadline()))
        {
            finish_bounded_request(
                &mut response,
                vintf_failure,
                deadline,
                || {
                    authority
                        .as_ref()
                        .map_or(Ok(()), |owner| owner.revalidate())
                },
                || {
                    authority
                        .as_ref()
                        .map_or(Ok(()), |owner| owner.expired_request_bookend(deadline))
                },
                if native_ui_deadline.is_some() {
                    "Fixed native UI request exhausted its original absolute deadline; no command result was accepted"
                } else {
                    VINTF_EXPIRED_MESSAGE
                },
            )
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
            if vintf_budget.is_some() || preparation_end.is_some() || native_ui_deadline.is_some() {
                response.runtime_vintf = None;
                response.diagnostics = None;
            }
        }
        let delivery = match native_ui_deadline {
            Some(deadline) => send_native_ui_response(stream, &response, deadline),
            None => send_response(stream, &response),
        };
        if let Err(error) = delivery {
            eprintln!("could not deliver early application observation: {error}");
        }
        original.map(|()| None)
    }
    pub(crate) fn retire(self) -> Result<(), ControlError> {
        if let Some(mut slot)=self.apk.into_inner() {slot.retire()?;}
        let fixture=self.fixture.into_inner().require_retired();
        self.listener.retire()?;
        fixture
    }
}

fn send_native_ui_response(
    stream: &mut UnixStream,
    response: &ControlResponse,
    deadline: Instant,
) -> Result<(), ControlError> {
    let mut encoded = serde_json::to_vec(response)?;
    encoded.push(b'\n');
    if encoded.len() > crate::native_application_ui_gateway::MAX_RESPONSE_BYTES {
        return Err(ControlError::Invalid(
            "native UI response framing bound exceeded".into(),
        ));
    }
    let mut pending = encoded.as_slice();
    while !pending.is_empty() {
        let left = deadline
            .checked_duration_since(Instant::now())
            .filter(|v| !v.is_zero())
            .ok_or_else(|| {
                ControlError::Invalid("native UI original delivery deadline expired".into())
            })?;
        stream
            .set_write_timeout(Some(left.min(CLIENT_TIMEOUT)))
            .map_err(|e| io_error("bound native UI response delivery", e))?;
        match stream.write(pending) {
            Ok(0) => {
                return Err(ControlError::Invalid(
                    "native UI response write returned zero".into(),
                ));
            }
            Ok(count) => pending = &pending[count..],
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(io_error("deliver bounded native UI response", error)),
        }
    }
    if Instant::now() >= deadline {
        return Err(ControlError::Invalid(
            "native UI delivery exceeded its original end".into(),
        ));
    }
    Ok(())
}

const VINTF_EXPIRED_MESSAGE: &str = "Fixed public metadata request exhausted its observation budget; no compatibility or application result was accepted";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum VintfFailure {
    Expired,
    Other,
}
fn classify_vintf_failure(
    error: &(dyn std::error::Error + 'static),
    expected: Instant,
) -> VintfFailure {
    if crate::production_host_admission::observation_expiry(error) == Some(expected)
        && Instant::now() >= expected
    {
        VintfFailure::Expired
    } else {
        VintfFailure::Other
    }
}
/// Complete only the finite read. A typed pure expiry never starts a new
/// observer and never promotes an old body to success. Other failures keep the
/// existing original-owner isolation path; all ordinary requests are unchanged.
#[cfg(test)]
fn finish_vintf_request(
    response: &mut ControlResponse,
    prior: Option<VintfFailure>,
    deadline: Instant,
    final_check: impl FnOnce() -> std::result::Result<(), crate::production_namespace::NamespaceError>,
    expiry_bookend: impl FnOnce()
        -> std::result::Result<(), crate::production_namespace::NamespaceError>,
) -> Result<(), ControlError> {
    finish_bounded_request(
        response,
        prior,
        deadline,
        final_check,
        expiry_bookend,
        VINTF_EXPIRED_MESSAGE,
    )
}
fn finish_bounded_request(
    response: &mut ControlResponse,
    prior: Option<VintfFailure>,
    deadline: Instant,
    final_check: impl FnOnce() -> std::result::Result<(), crate::production_namespace::NamespaceError>,
    expiry_bookend: impl FnOnce()
        -> std::result::Result<(), crate::production_namespace::NamespaceError>,
    expired_message: &str,
) -> Result<(), ControlError> {
    let expired = if prior == Some(VintfFailure::Expired) {
        true
    } else {
        match final_check() {
            Ok(()) => false,
            Err(error)
                if prior.is_none()
                    && classify_vintf_failure(&error, deadline) == VintfFailure::Expired =>
            {
                true
            }
            Err(error) => return Err(ControlError::Invalid(error.to_string())),
        }
    };
    if expired {
        response.ok = false;
        response.runtime_vintf = None;
        response.diagnostics = None;
        response.state = CellState::Starting;
        response.message = expired_message.into();
        // If acquisition itself expired, it returned no new authority or live
        // query child; its original typed retirement flag was already checked.
        // Otherwise only the same held owner's kernel custody is sampled here.
        expiry_bookend().map_err(|e| ControlError::Invalid(e.to_string()))?;
    }
    Ok(())
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
    fn vintf_test_response() -> ControlResponse {
        use crate::control::application_custody::{CustodyFileIdentity, CustodyOwner};
        use crate::control::application_probe::RuntimeEpoch;
        use crate::control::runtime_vintf::{
            PublicStat, RuntimeVintfBinding, RuntimeVintfObservation, VintfDocument,
        };
        // An opaque unit-test sentinel verifies removal of an actual Some body.
        // It is never validated, serialized, or represented as runtime evidence.
        let epoch = RuntimeEpoch {
            boot_id: "unit-test-only".into(),
            cell_host_pid: 19,
            framework_host_pid: 20,
            framework_start_ticks: 1,
        };
        let binding = RuntimeVintfBinding {
            owner: CustodyOwner {
                host_uid: 1000,
                cell_host_pid: 19,
                cell_start_ticks: 1,
                selection_binding_sha256: "unit-test-only".into(),
                base_cohort_sha256: "unit-test-only".into(),
                runtime_manifest_sha256: "unit-test-only".into(),
                namespaces: Vec::new(),
            },
            framework_namespaces: Vec::new(),
            framework_root: CustodyFileIdentity {
                device: 1,
                inode: 2,
                mode: 0o40755,
                uid: 0,
                gid: 0,
                links: 1,
                bytes: 0,
                modified: (0, 0),
                changed: (0, 0),
            },
            base_images: Vec::new(),
            image_bodies_rehashed_by_this_observation: false,
        };
        let body = RuntimeVintfObservation {
            schema: "unit-test-only".into(),
            expected_epoch: epoch.clone(),
            epoch_before: epoch.clone(),
            epoch_after: epoch,
            binding_before: binding.clone(),
            binding_after: binding,
            kernel_release: "unit-test-only".into(),
            machine: "unit-test-only".into(),
            properties: Vec::new(),
            apex_inventory: VintfDocument {
                path: "/apex/apex-info-list.xml".into(),
                bytes: 0,
                sha256: "unit-test-only".into(),
                stat: PublicStat {
                    path: "/apex/apex-info-list.xml".into(),
                    mode: 0o100444,
                    uid: 0,
                    gid: 0,
                    links: 1,
                    device: 1,
                    inode: 3,
                    bytes: 0,
                    modified: "unit-test-only".into(),
                    changed: "unit-test-only".into(),
                },
                utf8: String::new(),
            },
            active_apex: Vec::new(),
            root_mappings: std::collections::BTreeMap::new(),
            missing: Vec::new(),
            odm_links: Vec::new(),
            directories: Vec::new(),
            documents: Vec::new(),
            query_receipts: Vec::new(),
            elapsed_millis: 1,
            compatibility_checked: false,
            application_acceptance: false,
        };
        ControlResponse {
            ok: true,
            state: CellState::Running,
            message: "body completed".into(),
            host_pid: Some(19),
            launch: None,
            applications: None,
            application_icon: None,
            diagnostics: None,
            inspection: None,
            image_custody: None,
            runtime_vintf: Some(body),
        }
    }
    #[test]
    fn vintf_expiry_returns_to_owner_without_starting_another_observer() {
        let end = Instant::now() - Duration::from_millis(1);
        let called = std::cell::Cell::new(0);
        let mut response = vintf_test_response();
        finish_vintf_request(
            &mut response,
            Some(VintfFailure::Expired),
            end,
            || panic!("an expired request cannot open a new owner observer"),
            || {
                called.set(called.get() + 1);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(called.get(), 1);
        assert!(!response.ok);
        assert!(response.runtime_vintf.is_none());
        assert_ne!(response.state, CellState::Quarantined);
    }
    #[test]
    fn vintf_final_expiry_cannot_publish_a_successful_body() {
        let end = Instant::now() - Duration::from_millis(1);
        let mut response = vintf_test_response();
        assert!(response.runtime_vintf.is_some());
        finish_vintf_request(
            &mut response,
            None,
            end,
            || Err(crate::production_host_admission::observation_expired_error(end).into()),
            || Ok(()),
        )
        .unwrap();
        assert!(!response.ok);
        assert!(response.runtime_vintf.is_none());
        assert!(!response.message.contains("body completed"));
    }
    #[test]
    fn main_custody_expiry_discards_body_without_reopening_owner() {
        let end = Instant::now() - Duration::from_millis(1);
        let mut response = vintf_test_response();
        response.runtime_vintf = None;
        response.diagnostics =
            Some(serde_json::to_string(&crate::main_custody::tests::sample()).unwrap());
        let checked = std::cell::Cell::new(false);
        finish_vintf_request(
            &mut response,
            Some(VintfFailure::Expired),
            end,
            || panic!("expired Main custody must not start another observer"),
            || {
                checked.set(true);
                Ok(())
            },
        )
        .unwrap();
        assert!(checked.get());
        assert!(!response.ok);
        assert!(response.diagnostics.is_none());
        assert_eq!(response.state, CellState::Starting);
    }

    #[test]
    fn vintf_owner_failure_and_unretired_children_are_never_expiry_exemptions() {
        use crate::production_namespace::NamespaceError;
        let end = Instant::now() - Duration::from_millis(1);
        let mut response = vintf_test_response();
        assert!(
            finish_vintf_request(
                &mut response,
                Some(VintfFailure::Other),
                end,
                || Err(crate::production_host_admission::observation_expired_error(end).into()),
                || panic!("prior substantive failure cannot take expiry path")
            )
            .is_err()
        );
        for error in [
            NamespaceError::Rejected("original owner changed"),
            NamespaceError::RetirementUnproven,
        ] {
            assert!(
                finish_vintf_request(
                    &mut response,
                    Some(VintfFailure::Expired),
                    end,
                    || panic!("expiry may only take kernel bookend"),
                    || Err(error)
                )
                .is_err()
            );
        }
        let arbitrary = io::Error::new(
            io::ErrorKind::TimedOut,
            "original request observation deadline reached",
        );
        assert_eq!(classify_vintf_failure(&arbitrary, end), VintfFailure::Other);
        let other = crate::production_host_admission::observation_expired_error(
            end - Duration::from_millis(1),
        );
        assert_eq!(classify_vintf_failure(&other, end), VintfFailure::Other);
        let future = Instant::now() + Duration::from_secs(1);
        let forged_early = crate::production_host_admission::observation_expired_error(future);
        assert_eq!(
            classify_vintf_failure(&forged_early, future),
            VintfFailure::Other
        );
    }
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
