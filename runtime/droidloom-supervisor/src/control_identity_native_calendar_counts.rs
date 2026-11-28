//! Actual Calendar counts and complete provider PM bookends from one normal peer.
//! The source-fixed request has no SQL, path, UID or caller-selected package input.
use super::*;
use crate::native_application_ui_gateway::{GatewayCommand, GatewayReply, GatewayRequest};
use crate::native_calendar_counts::{self as fixed, ParsedCalendarCounts};

pub(crate) struct NativeLeafCalendarCountsObservation {
    request: GatewayRequest,
    reply: GatewayReply,
    parsed: ParsedCalendarCounts,
    provider_before: ActualApplicationObservation,
    provider_after: ActualApplicationObservation,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    started_at: Instant,
    observed_at: Instant,
}
impl NativeLeafCalendarCountsObservation {
    pub(crate) fn require_same_database(&self, prior: &Self) -> Result<(), ControlError> {
        if self.peer != prior.peer || self.request.main() != prior.request.main()
            || self.request.application() != prior.request.application()
            || self.provider_before.facts() != prior.provider_before.facts()
            || self.started_at <= prior.observed_at
        {
            return Err(ControlError::Invalid(
                "Calendar observations differ in actual Main, application, provider or order".into()));
        }
        self.parsed.require_same_database(&prior.parsed).map_err(ControlError::Invalid)
    }
    pub(crate) fn comparison(
        &self,
        inspector: &NativeApplicationInspector,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        end: Instant,
    ) -> Result<serde_json::Value, ControlError> {
        inspector.require_observations_local(main, application, end)?;
        inspector.require_observations_local(main, &self.provider_before, end)?;
        inspector.require_observations_local(main, &self.provider_after, end)?;
        live(&self.pidfd).map_err(|e| io_error("check Calendar observer peer", e))?;
        let original = self.pidfd.metadata().map_err(|e| io_error("stat Calendar observer peer", e))?;
        let current = inspector.pidfd.metadata().map_err(|e| io_error("stat current Calendar peer", e))?;
        if self.peer != inspector.observation()?
            || (original.dev(), original.ino()) != (current.dev(), current.ino())
            || self.request.main() != main.facts()
            || self.request.application() != application.facts()
            || self.request.command() != &(GatewayCommand::CalendarCounts {})
            || self.provider_before.facts() != self.provider_after.facts()
            || self.provider_before.observed_at() <= self.started_at
            || self.provider_after.observed_at() <= self.provider_before.observed_at()
            || self.observed_at < self.provider_after.observed_at()
            || self.observed_at >= end
        {
            return Err(ControlError::Invalid(
                "Calendar counts differ from their actual original peer, provider or invocation".into()));
        }
        // The reply was checked against its actual request while that command
        // end was live. Historical comparison neither reissues nor renews it.
        let value = serde_json::json!({
            "schema": "droidloom.native-leaf-calendar-counts.v1",
            "counts": self.parsed.comparison(),
            "provider_before": self.provider_before.facts(),
            "provider_after": self.provider_after.facts(),
            "gateway": &self.reply,
            "comparison_only": true,
            "business_actions_admitted": false,
        });
        if serde_json::to_vec(&value)?.len() > 262144 {
            return Err(ControlError::Invalid("Calendar comparison exceeds its sealed channel bound".into()));
        }
        inspector.require_observations_local(main, application, end)?;
        Ok(value)
    }
}
fn fixed_provider(
    inspector: &NativeApplicationInspector,
    main: &MainCustodyObservation,
    provider: &ActualApplicationObservation,
    end: Instant,
) -> Result<(), ControlError> {
    inspector.require_observations_local(main, provider, end)?;
    let facts = provider.facts();
    if facts.package != fixed::PROVIDER || facts.user != 0 || facts.uid != fixed::OBSERVER_UID
        || facts.version_code == 0 || facts.apks.is_empty()
    {
        return Err(ControlError::Invalid("actual complete Calendar provider PM identity differs".into()));
    }
    Ok(())
}
impl NativeApplicationInspector {
    pub(crate) fn read_native_leaf_calendar_counts_until(
        &mut self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        original_end: Instant,
    ) -> Result<NativeLeafCalendarCountsObservation, ControlError> {
        let started_at = Instant::now();
        let end = original_end.min(started_at + fixed::MAX_DURATION);
        self.require_observations_local(main, application, end)?;
        if application.facts().package != fixed::SUBJECT || application.facts().user != 0 {
            return Err(ControlError::Invalid("Calendar counts require the actual user-zero Calendar subject".into()));
        }
        let provider_before = self.inspect_observed_until(fixed::PROVIDER, 0, end)?;
        fixed_provider(self, main, &provider_before, end)?;
        let command = GatewayCommand::CalendarCounts {};
        let literal = command.literal_arguments().map_err(ControlError::Invalid)?;
        let result = self.execute_native_ui_observed_until(main, application, &literal, false, end);
        // A failed/unknown query is never followed by another PM request or
        // replay. Local original custody is still checked on that failure.
        let post = self.require_observations_local(main, application, end);
        let (request, reply, output) = match (result, post) {
            (Ok(value), Ok(())) => value,
            (Err(error), Ok(())) => return Err(error),
            (Ok(_), Err(error)) => return Err(error),
            (Err(error), Err(post)) => return Err(ControlError::Invalid(
                format!("{error}; Calendar local postcheck also failed: {post}"))),
        };
        let provider_after = self.inspect_observed_until(fixed::PROVIDER, 0, end)?;
        fixed_provider(self, main, &provider_after, end)?;
        if provider_before.facts() != provider_after.facts() {
            return Err(ControlError::Invalid("complete Calendar provider APK/PM identity changed during counts".into()));
        }
        if !output.status.success() || !output.stderr.is_empty() {
            use sha2::{Digest, Sha256};
            return Err(ControlError::Invalid(format!(
                "actual Calendar query failed: {}; stdout {} bytes sha256 {:x}; stderr {} bytes sha256 {:x}",
                output.status, output.stdout.len(), Sha256::digest(&output.stdout),
                output.stderr.len(), Sha256::digest(&output.stderr))));
        }
        let parsed = fixed::parse(&output.stdout, end).map_err(ControlError::Invalid)?;
        let peer = self.observation()?;
        let pidfd = self.pidfd.try_clone().map_err(|e| io_error("retain actual Calendar peer", e))?;
        live(&pidfd).map_err(|e| io_error("check actual Calendar peer", e))?;
        self.require_observations_local(main, application, end)?;
        let observed_at = Instant::now();
        check_deadline(Some(end))?;
        Ok(NativeLeafCalendarCountsObservation {
            request, reply, parsed, provider_before, provider_after, peer, pidfd, started_at, observed_at,
        })
    }
}
