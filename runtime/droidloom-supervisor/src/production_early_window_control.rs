//! Public window actions borrow the existing early Android owner and frontend.
//! The broker retains the original presenter pidfd and exact installed identity.
use super::*;
#[path = "production_early_window_capture.rs"]
mod capture;
use crate::production_selection::early_generation::EarlyApplicationAuthority;

pub(crate) type WindowCall<'a> = dyn Fn(
        &window::Command,
        Option<&window::Session>,
        Instant,
    ) -> io::Result<(window::Reply, window::Session)>
    + 'a;

pub(super) struct Lease {
    token: [u8; 16],
    application: application_probe::ApplicationInspection,
    session: window::Session,
}
fn same_application(
    authority: &EarlyApplicationAuthority<'_>,
    expected: &application_probe::ApplicationInspection,
    quarantine: &mut bool,
) -> Result<(), ControlError> {
    validate_package(&expected.package)?;
    validate_android_user(expected.user)?;
    let now = crate::production_application::inspect_with_custody_early(
        authority,
        &expected.package,
        expected.user,
    )
    .map_err(|e| early_application_error(e, quarantine))?;
    if now.application != *expected {
        return Err(ControlError::Invalid(
            "owned window package, installed APKs, UID, version or physical epoch changed".into(),
        ));
    }
    Ok(())
}
fn observed(reply: window::Reply) -> Result<window::Observation, ControlError> {
    reply
        .result()
        .cloned()
        .map_err(|e| ControlError::Invalid(e.to_string()))
}
fn invoke(
    call: &WindowCall<'_>,
    command: &window::Command,
    session: Option<&window::Session>,
    until: Instant,
) -> Result<(window::Reply, window::Session), ControlError> {
    if Instant::now() >= until {
        return Err(ControlError::Invalid(
            "owned window deadline expired".into(),
        ));
    }
    let value =
        call(command, session, until).map_err(|e| io_error("original presenter window", e))?;
    if Instant::now() >= until {
        return Err(ControlError::Invalid(
            "owned window result exceeded its deadline".into(),
        ));
    }
    Ok(value)
}
impl EarlyApplicationControl {
    pub(super) fn launch_owned(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        peer: u32,
        expected: application_probe::ApplicationInspection,
        component: String,
        spec: PathBuf,
        call: &WindowCall<'_>,
        until: Instant,
        response: &mut ControlResponse,
        quarantine: &mut bool,
    ) -> Result<(), ControlError> {
        let request =
            early_launch_request(&expected.package, Some(&component), None, expected.user)?;
        same_application(authority, &expected, quarantine)?;
        let guard =
            ConfigurationReadGuard::acquire().map_err(|e| ControlError::Invalid(e.to_string()))?;
        let selected = ProductionSelection::load(&guard, &spec, peer)
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        authority
            .verify_selection(&selected)
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        let catalog = crate::production_application::catalog_early(
            authority,
            crate::production_application::CatalogCommand::List {
                user: expected.user,
            },
            until,
        )
        .map_err(|e| early_application_error(e, quarantine))?;
        let catalog: Vec<AndroidApplication> = serde_json::from_str(&catalog)?;
        validate_application_catalog(&catalog)?;
        if catalog
            .iter()
            .filter(|a| a.package == expected.package && a.component == component)
            .count()
            != 1
        {
            return Err(ControlError::Invalid(
                "owned window component is not one exact enabled launcher".into(),
            ));
        }
        let mut held = self.window_lease.borrow_mut();
        if let Some(previous) = held.as_ref() {
            let (reply, _) = invoke(
                call,
                &window::Command::Action {
                    lease: previous.token,
                    action: window::Action::Observe,
                },
                Some(&previous.session),
                until,
            )?;
            let previous = observed(reply)?;
            if !previous.destroy_observed || previous.mapped {
                return Err(ControlError::Invalid(
                    "previous original window has not retired; no second launch was issued".into(),
                ));
            }
        }
        let token = window::fresh_token().map_err(|e| io_error("mint original window lease", e))?;
        let (reply, session) = invoke(
            call,
            &window::Command::Arm {
                lease: token,
                package: expected.package.clone(),
            },
            None,
            until,
        )?;
        let armed = observed(reply)?;
        if armed.phase != window::Phase::Armed || armed.package != expected.package {
            return Err(ControlError::Invalid(
                "presenter did not arm the exact new window".into(),
            ));
        }
        // Retain authority before launch can have an effect. A failed or lost
        // response never permits another launch or token reconstructed from JSON.
        *held = Some(Lease {
            token,
            application: expected.clone(),
            session,
        });
        response.window = Some(armed);
        let launched =
            crate::production_application::launch_application_early(authority, &request, until)
                .map_err(|e| early_application_error(e, quarantine))?;
        if launched.application != expected {
            return Err(ControlError::Invalid(
                "launch changed the exact installed application identity".into(),
            ));
        }
        let lease = held.as_ref().unwrap();
        let binding = launched.binding;
        loop {
            let (reply, _) = invoke(
                call,
                &window::Command::Bind {
                    lease: token,
                    object: binding.object,
                    task: binding.task,
                },
                Some(&lease.session),
                until,
            )?;
            let now = observed(reply)?;
            response.window = Some(now.clone());
            if now.phase == window::Phase::Bound {
                if now.object != Some(binding.object)
                    || now.android_task != Some(binding.task)
                    || now.package != expected.package
                    || now.creation_serial.is_none()
                {
                    return Err(ControlError::Invalid(
                        "fresh presenter birth differs from actual launcher binding".into(),
                    ));
                }
                break;
            }
            if now.phase != window::Phase::Armed {
                return Err(ControlError::Invalid(
                    "new window left its original arming lifecycle".into(),
                ));
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        guard
            .revalidate()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        authority
            .verify_selection(&selected)
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        same_application(authority, &expected, quarantine)?;
        if Instant::now() >= until {
            return Err(ControlError::Invalid(
                "owned launch validation exceeded deadline".into(),
            ));
        }
        response.inspection = Some(expected);
        response.launch = Some(format!(
            "object={} composer_display={} android_display={} task={}",
            binding.object, binding.composer_display, binding.android_display, binding.task
        ));
        response.message =
            "Fresh original native window bound; rendering and business acceptance remain pending"
                .into();
        Ok(())
    }
    pub(super) fn window_action(
        &self,
        authority: &EarlyApplicationAuthority<'_>,
        token: [u8; 16],
        action: window::Action,
        call: &WindowCall<'_>,
        until: Instant,
        response: &mut ControlResponse,
        quarantine: &mut bool,
    ) -> Result<(), ControlError> {
        window::valid_token(token).map_err(|e| ControlError::Invalid(e.to_string()))?;
        action
            .validate()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        let held = self.window_lease.borrow();
        let lease = held.as_ref().filter(|l| l.token == token).ok_or_else(|| {
            ControlError::Invalid("no broker-held original window matches this lease".into())
        })?;
        same_application(authority, &lease.application, quarantine)?;
        let close = matches!(action, window::Action::Close);
        let capture = matches!(action, window::Action::Capture);
        let (mut reply, _) = invoke(
            call,
            &window::Command::Action {
                lease: token,
                action,
            },
            Some(&lease.session),
            until,
        )?;
        let first_capture = reply.capture.take();
        let mut now = observed(reply)?;
        response.window = Some(now.clone());
        if capture {
            let first = first_capture
                .ok_or_else(|| ControlError::Invalid("original capture bytes absent".into()))?;
            response.window_image = Some(capture::collect(first, &now, lease, call, until)?);
        } else if first_capture.is_some() {
            return Err(ControlError::Invalid(
                "unexpected captured content in a non-capture operation".into(),
            ));
        }
        // Close uses the same compositor endpoint as a normal native window
        // close; completion requires the actual DestroyTask and native unmap.
        while close && (!now.destroy_observed || now.mapped) {
            std::thread::sleep(Duration::from_millis(5));
            let (reply, _) = invoke(
                call,
                &window::Command::Action {
                    lease: token,
                    action: window::Action::Observe,
                },
                Some(&lease.session),
                until,
            )?;
            now = observed(reply)?;
            response.window = Some(now.clone());
        }
        same_application(authority, &lease.application, quarantine)?;
        if Instant::now() >= until {
            return Err(ControlError::Invalid(
                "owned window validation exceeded deadline".into(),
            ));
        }
        response.inspection = Some(lease.application.clone());
        response.message=if close {
            "Original Android DestroyTask and native surface retirement observed; no force-stop or data deletion"
        } else {
            "Original window observation/input transport completed; business and rendered-result verification remain pending"
        }.into();
        Ok(())
    }
}
