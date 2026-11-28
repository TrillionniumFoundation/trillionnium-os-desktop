//! Separate actual whole-image observations from the normal Gallery producer.
//! The broker borrows its original base-image owner and retains the original APK
//! descriptor across both complete byte passes. This client token records that
//! completed observation and holds its real peer PIDFD; it does not claim to
//! hold the broker's image descriptors after the response or to grant a gate.
use super::*;

pub struct ActualImageApplicationObservation {
    facts: application_custody::ImageApplicationCustody,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl ActualImageApplicationObservation {
    /// Historical comparison data from the actual whole-image operation.
    pub fn facts(&self) -> &application_custody::ImageApplicationCustody {
        &self.facts
    }
    pub fn observed_at(&self) -> Instant {
        self.observed_at
    }
}

fn gallery_response(
    mut response: ControlResponse,
) -> Result<(application_probe::ApplicationInspection, application_custody::ImageApplicationCustody), ControlError> {
    if response.diagnostics.is_some() {
        return Err(ControlError::Invalid("Gallery image observation returned unrelated diagnostics".into()));
    }
    let image = response.image_custody.take().ok_or_else(|| {
        ControlError::Invalid("actual Gallery operation omitted whole-image custody".into())
    })?;
    // This private split consumes the actual RPC response. The unchanged
    // generic parser still rejects an image field supplied to that path.
    let application = application_response(response, application_custody::GALLERY_PACKAGE, 0)?;
    image.validate(&application).map_err(ControlError::Invalid)?;
    Ok((application, image))
}

fn catalog_response(
    response: ControlResponse,
    epoch: &application_probe::RuntimeEpoch,
) -> Result<Vec<AndroidApplication>, ControlError> {
    if !response.ok || response.state != CellState::Running
        || response.host_pid != Some(epoch.cell_host_pid)
        || response.launch.is_some() || response.application_icon.is_some()
        || response.diagnostics.is_some() || response.inspection.is_some()
        || response.image_custody.is_some() || response.runtime_vintf.is_some()
    {
        return Err(ControlError::Invalid("actual launcher catalog belongs to another operation or Main".into()));
    }
    response.applications.ok_or_else(|| {
        ControlError::Invalid("actual launcher catalog is absent".into())
    })
}

impl NativeApplicationInspector {
    /// Local revalidation of these two actual tokens; no PM/Main RPC is added.
    pub fn require_application_local(
        &self, main: &MainCustodyObservation, application: &ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main, application, deadline)
    }

    /// Exactly the existing user-zero Gallery operation. The server keeps its
    /// original 300-second work/retirement end and transport keeps 330 seconds.
    /// This has no caller-selected package, image pathname, FD or receipt.
    pub fn inspect_gallery_observed_until(
        &mut self,
        deadline: Instant,
    ) -> Result<(ActualApplicationObservation, ActualImageApplicationObservation), ControlError> {
        check_deadline(Some(deadline))?;
        let request = ControlRequest::InspectApplication {
            package: application_custody::GALLERY_PACKAGE.into(), user: 0,
        };
        if deadline.saturating_duration_since(Instant::now()) < progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original window cannot fit complete Gallery observation".into()));
        }
        let (facts, image) = gallery_response(self.inspect_until(
            application_custody::GALLERY_PACKAGE, 0, deadline,
        )?)?;
        let application = ActualApplicationObservation {
            facts,
            peer: self.observation()?,
            pidfd: self.pidfd.try_clone().map_err(|e| io_error("retain actual Gallery PM peer", e))?,
            observed_at: Instant::now(),
        };
        let observation = ActualImageApplicationObservation {
            facts: image,
            peer: self.observation()?,
            pidfd: self.pidfd.try_clone().map_err(|e| io_error("retain actual Gallery image peer", e))?,
            observed_at: Instant::now(),
        };
        for fd in [&application.pidfd, &observation.pidfd] {
            live(fd).map_err(|e| io_error("check actual Gallery observation peer", e))?;
        }
        self.revalidate()?;
        check_deadline(Some(deadline))?;
        Ok((application, observation))
    }

    /// Compare two separately acquired actual observations under the same Main.
    /// No new RPC, whole-image pass, or lease extension is performed.
    pub fn require_image_application_local(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        image: &ActualImageApplicationObservation,
        deadline: Instant,
    ) -> Result<(), ControlError> {
        self.require_observations_local(main, application, deadline)?;
        live(&image.pidfd).map_err(|e| io_error("recheck actual image peer", e))?;
        let held = image.pidfd.metadata().map_err(|e| io_error("stat actual image peer", e))?;
        let current = self.pidfd.metadata().map_err(|e| io_error("stat current image peer", e))?;
        if (held.dev(), held.ino()) != (current.dev(), current.ino())
            || image.peer != self.observation()?
            || image.facts.owner != main.facts.owner
            || image.facts.application != application.facts
            || image.facts.application.epoch != main.facts.epoch
        {
            return Err(ControlError::Invalid("whole-image observation belongs to another actual Main or PM owner".into()));
        }
        image.facts.validate(&application.facts).map_err(ControlError::Invalid)?;
        check_deadline(Some(deadline))
    }

    fn require_preparation_main_local(
        &self, main: &MainCustodyObservation, deadline: Instant,
    ) -> Result<(), ControlError> {
        check_deadline(Some(deadline))?;
        live(&main.pidfd).map_err(|e| io_error("recheck catalog Main peer", e))?;
        let held = main.pidfd.metadata().map_err(|e| io_error("stat catalog Main peer", e))?;
        let current = self.pidfd.metadata().map_err(|e| io_error("stat catalog current peer", e))?;
        if (held.dev(), held.ino()) != (current.dev(), current.ino())
            || main.peer != self.observation()? || main.facts.epoch.boot_id != self.boot_id
        {
            return Err(ControlError::Invalid("catalog Main belongs to another actual normal peer".into()));
        }
        check_deadline(Some(deadline))
    }

    /// One complete normal launcher query for user zero, borrowing the actual
    /// Main and original caller end. It does not filter out blocked packages.
    pub fn list_applications_for_main_until(
        &mut self, main: &MainCustodyObservation, deadline: Instant,
    ) -> Result<Vec<AndroidApplication>, ControlError> {
        self.require_preparation_main_local(main, deadline)?;
        let request = ControlRequest::ListApplications { user: 0 };
        if deadline.saturating_duration_since(Instant::now()) < progress::response_timeout(&request) {
            return Err(ControlError::Invalid("original preparation window cannot fit the full catalog".into()));
        }
        let response = self.request_fixed_until(&request, Some(deadline))?;
        let result = catalog_response(response, &main.facts.epoch)?;
        self.require_preparation_main_local(main, deadline)?;
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn response() -> ControlResponse {
        serde_json::from_value(serde_json::json!({
            "ok":true, "state":"running", "message":"comparison test", "host_pid":321
        })).unwrap()
    }
    #[test]
    fn working_preparation_gallery_requires_real_whole_image_response() {
        let mut missing = response();
        let epoch = crate::main_custody::tests::sample().epoch;
        missing.inspection = Some(serde_json::from_value(serde_json::json!({
            "package":"com.android.gallery3d","user":0,"uid":10064,"version_code":40030,
            "epoch":epoch,"apks":[{"name":"base.apk","path":"/system/product/app/Gallery2/Gallery2.apk",
                "bytes":7390425,"sha256":application_custody::GALLERY_SHA256}]
        })).unwrap());
        assert!(gallery_response(missing).is_err());
    }
    #[test]
    fn working_preparation_catalog_rejects_other_owner_and_payload() {
        let epoch = crate::main_custody::tests::sample().epoch;
        let mut valid = response();
        valid.host_pid = Some(epoch.cell_host_pid);
        valid.applications = Some(Vec::new());
        assert!(catalog_response(valid.clone(), &epoch).unwrap().is_empty());
        let mut other = valid.clone();
        other.host_pid = Some(epoch.cell_host_pid + 1);
        assert!(catalog_response(other, &epoch).is_err());
        let mut unrelated = valid;
        unrelated.launch = Some("not a catalog".into());
        assert!(catalog_response(unrelated, &epoch).is_err());
    }
}
