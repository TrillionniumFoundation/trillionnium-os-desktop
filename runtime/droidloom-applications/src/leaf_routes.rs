//! Finite execution routes for the selected, already qualified application leaves.
//!
//! These routes call the original entry, including its source closure, Main,
//! package identity, display lease, limits and cleanup checks. A verified leaf
//! result is scoped progress; it cannot satisfy a whole application release.
use std::collections::BTreeSet;
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

use droidloom_supervisor::control::{self, application_probe::ApplicationInspection};
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::working_leaf_release::{NativeSourceRelease as NativeRelease, SourceContext};
use droidloom_supervisor::control::physical_qualification_channel::WorkingNativeSourceCustody;
use std::sync::Arc;
use super::{ApplicationPlan, FilePin, RuntimePlan, pinned};
use super::runtime_identity::{IdentityObservation, VerifiedMaterialBatch};

const QUALIFICATION: &str = "/var/lib/droidloom/qualification/pocket4";
const SELECTION_PATH: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/selection/selection-14.json";
const SELECTION_BYTES: u64 = 4769;
const SELECTION_SHA: &str = "e46570ce965d4cb1abd9a9b2433fa71293525ccad8b4ed6ed65e19c4dfc85c73";
const SOURCE_CATALOG: &str = include_str!("leaf_sources.json");

pub(super) fn compiled_release_sources() -> (FilePin, &'static str) {
    (
        FilePin {
            path: SELECTION_PATH.into(),
            bytes: SELECTION_BYTES,
            sha256: SELECTION_SHA.into(),
        },
        SOURCE_CATALOG,
    )
}

/// Hold the already adopted source/native release before the fixed unit's
/// initial PM query. Actual business validation and the original claim remain
/// in execute; this method grants neither Main nor application acceptance.
pub(super) fn owned_route_release(
    plan: &LeafPlan,
    selection: &FilePin,
) -> Result<NativeRelease, String> {
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let source = &sources[plan.route.definition().source];
    if plan.route.current_gallery() {
        let request = value(&plan.request)?;
        NativeRelease::bind(
            &ref_field(&request, "native_release")?,
            selection,
            SOURCE_CATALOG,
            &source.preparation,
            &source.entry,
        )
    } else if matches!(
        plan.route,
        Route::CalendarReminder | Route::SettingsSupportedPages
    ) {
        NativeRelease::bind_current(
            selection,
            SOURCE_CATALOG,
            &source.preparation,
            &source.entry,
        )
    } else {
        Err(
            "owned unit release binding supports only current Calendar/Gallery/Settings routes"
                .into(),
        )
    }
}


/// Held normal Main/copy-origin fact for one exact live package identity.
/// There is no JSON, boolean, Clone or Deserialize constructor. The only
/// constructor asks the authenticated normal inspector for its opaque fact.
pub(super) struct HeldMainCustody {
    observation: control::MainCustodyObservation,
    application: control::ActualApplicationObservation,
    completed: Option<(control::MainCustodyObservation, control::ActualApplicationObservation)>,
}

impl fmt::Debug for HeldMainCustody {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HeldMainCustody")
            .field("application", self.application.facts())
            .field("facts", self.observation.facts())
            .field("peer", self.observation.peer()).finish()
    }
}

impl Serialize for HeldMainCustody {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut out = serializer.serialize_struct("HeldMainCustody", 5)?;
        out.serialize_field("schema", "droidloom.application-main-custody.v2")?;
        out.serialize_field("application", self.application.facts())?;
        out.serialize_field("facts", self.observation.facts())?;
        out.serialize_field("peer", self.observation.peer())?;
        out.serialize_field("final_observations", &self.completed.as_ref().map(|(main, application)| {
            json!({"main":main.facts(), "application":application.facts(), "peer":main.peer()})
        }))?;
        out.end()
    }
}

// This comparison helper cannot authenticate the wire projection or construct
// HeldMainCustody. Authentication and source admission belong to the opaque
// normal inspector fact; the consumer additionally requires its copy origin.
fn require_working_origin(
    origin: Option<&droidloom_supervisor::main_custody::MainOriginalCopyOrigin>,
    actual: [[u64; 7]; 2],
) -> Result<(), String> {
    let origin = origin.ok_or("normal Main has no source-admitted original-copy origin")?;
    require(origin.working == actual,
        "normal Main working data/metadata differ from the admitted copy lineage")
}

impl HeldMainCustody {
    pub(super) fn actual_application(&self) -> &ApplicationInspection { self.application.facts() }
    pub(super) fn require_completed(&self) -> Result<(),String> {
        self.guard_projection()?;
        require(self.completed.is_some(),"case has no actual final Main and PM observations")
    }

    pub(super) fn observe(
        inspector: &mut control::NativeApplicationInspector,
        application: control::ActualApplicationObservation,
        end: Instant,
    ) -> Result<Self, String> {
        let observation = inspector.observe_main_until(&application.facts().epoch, end)
            .map_err(|error| error.to_string())?;
        require(observation.peer() == application.peer(),
            "normal PM and Main observations belong to different authenticated peers")?;
        let held = Self { observation, application, completed:None };
        held.guard_projection()?;
        Ok(held)
    }

    pub(super) fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        use droidloom_supervisor::main_custody::MainDataRole;
        let facts = self.observation.facts();
        let data = &facts.persistent_data;
        require(self.application.facts() == actual && facts.epoch == actual.epoch
            && self.application.peer() == self.observation.peer()
            && actual.user == 0
            && data.backings[0].role == MainDataRole::Data
            && data.backings[1].role == MainDataRole::Metadata,
            "leaf Main differs in package/user/UID/version/full APKs, epoch or backing roles")?;
        require_working_origin(data.original_copy_origin.as_ref(),
            [data.backings[0].backing.stable7(), data.backings[1].backing.stable7()])
    }

    /// Replace the old revalidation call with its same one normal RPC, retaining
    /// the returned actual token so the baseline can check its private timestamp.
    pub(super) fn refresh(
        &self,
        inspector: &mut control::NativeApplicationInspector,
        actual: &control::ActualApplicationObservation,
        end: Instant,
    ) -> Result<control::MainCustodyObservation, String> {
        self.require_application(actual.facts())?;
        require(actual.peer() == self.observation.peer(),
            "normal leaf final PM observation changed peer")?;
        let after = inspector.refresh_main_until(&self.observation, end)
            .map_err(|error| error.to_string())?;
        self.require_application(actual.facts())?;
        Ok(after)
    }

    pub(super) fn baseline<'a>(
        &'a self, inspector: &control::NativeApplicationInspector, end: Instant,
    ) -> Result<NativeLeafBaselineObservation<'a>, String> {
        NativeLeafBaselineObservation::capture_from_observed(
            inspector, &self.observation, &self.application, end,
        ).map_err(|error| error.to_string())
    }

    /// Called only after the actual shared context's final finish/local checks.
    /// These real peer-held observations survive until the row is submitted.
    pub(super) fn retain_completed(
        &mut self,
        main: control::MainCustodyObservation,
        application: control::ActualApplicationObservation,
    ) -> Result<(), String> {
        require(self.completed.is_none() && main.facts() == self.observation.facts()
            && main.peer() == self.observation.peer()
            && application.facts() == self.application.facts()
            && application.peer() == self.application.peer(),
            "normal leaf final tokens differ or were already consumed")?;
        self.completed = Some((main, application));
        self.guard_projection()
    }

    pub(super) fn guard_projection(&self) -> Result<(), String> {
        self.require_application(self.application.facts())?;
        if let Some((main, application)) = &self.completed {
            require(main.facts() == self.observation.facts()
                && main.peer() == self.observation.peer()
                && application.facts() == self.application.facts()
                && application.peer() == self.application.peer(),
                "retained completed normal observations differ")?;
        }
        Ok(())
    }

    /// Borrow the actual opaque fact; serialized facts do not recreate it.
    pub(super) fn require_engine(&self, engine: &control::NativeLeafEngineEvidence) -> Result<(), String> {
        self.guard_projection()?;
        engine.require_identity(&self.observation, self.application.facts())
    }

    pub(super) fn normal_observation(&self) -> &control::MainCustodyObservation {
        &self.observation
    }
}

/// Only the completed normal leaf factory creates this custody. It retains the
/// original source/owner lease, Main PIDFD and first-read result FD through the
/// dispatcher's final package/material bookend and record submission.
pub(super) struct HeldLeafCustody {
    main: HeldMainCustody,
    release: NativeRelease,
    result: super::clock_timer::ClockResultCustody,
    final_identity: Option<IdentityObservation>,
    end: Instant,
}

impl fmt::Debug for HeldLeafCustody {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HeldLeafCustody").field("main", &self.main)
            .field("result", self.result.reference()).finish_non_exhaustive()
    }
}

impl Serialize for HeldLeafCustody {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut out = serializer.serialize_struct("HeldLeafCustody", 3)?;
        out.serialize_field("main", &self.main)?;
        out.serialize_field("result", self.result.reference())?;
        out.serialize_field("result_f9",
            &self.result.identity().map_err(serde::ser::Error::custom)?)?;
        out.end()
    }
}

impl HeldLeafCustody {
    fn guard(&self) -> Result<(), String> {
        self.main.guard_projection()?;
        self.release.guard()?;
        self.result.guard()
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Route {
    ContactsSearch,
    CalendarCore,
    CalendarReminder,
    SettingsSupportedPages,
    CameraPhoto,
    ClockTimer,
    ClockTimerPair,
    ClockTimerRemaining,
    ClockExpiry,
    ClockAlarm,
    IhgLondon,
    DocumentsSaf,
    DocumentsSearchSort,
    GalleryRotation,
    GalleryVideo,
    GallerySeek,
    GalleryAlbum,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct LeafPlan {
    pub route: Route,
    pub request: FilePin,
    /// Only the camera display wrapper takes its new output directory in argv.
    pub output: Option<PathBuf>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct SelectedSource {
    index: usize,
    preparation: FilePin,
    entry: FilePin,
}

#[derive(Debug, Serialize)]
pub(super) struct LeafObservation {
    pub route: Route,
    pub request: FilePin,
    pub preparation: FilePin,
    pub entry_source: FilePin,
    pub result: FilePin,
    pub state: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) custody: Option<HeldLeafCustody>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) engine_observations: Option<control::NativeLeafEngineEvidence>,
    pub original_entry_result_verified: bool,
    pub original_business_success_reported: bool,
    pub business_outcome_unknown: bool,
    pub main_epoch_unchanged: bool,
    pub owned_host_tree_retired: bool,
    pub automatic_retry: bool,
    pub whole_app_business_accepted: bool,
    pub production_ready: bool,
    pub remaining_scope: &'static str,
}

impl LeafObservation {
    pub(super) fn retained_bookends(&self) -> Result<(), String> {
        let custody = self.custody.as_ref().ok_or("leaf has no actual normal Main/result custody")?;
        custody.guard()?;
        if let Some(engine) = &self.engine_observations { custody.main.require_engine(engine)?; }
        Ok(())
    }

    pub(super) fn has_main_custody(&self) -> bool { self.custody.is_some() }

    /// Move the one actual final package/material fact, never deserialize or
    /// synthesize a replacement. The opaque Main and all result FDs stay held.
    pub(super) fn take_final_identity(&mut self) -> Result<IdentityObservation, String> {
        self.retained_bookends()?;
        self.custody.as_mut().ok_or("normal leaf custody missing")?
            .final_identity.take().ok_or("normal leaf final identity already consumed".into())
    }

    pub(super) fn main_observation(&self) -> Option<&control::MainCustodyObservation> {
        self.custody.as_ref().map(|held| held.main.normal_observation())
    }

    /// Only the Settings terminal contract currently verifies entire named
    /// registry assertions. Other cases remain narrower observations.
    pub(super) fn verified_business_gates(&self) -> &'static [&'static str] {
        if self.custody.is_some()
            && self.route == Route::SettingsSupportedPages
            && self.state == "SETTINGS_FONT_SCALE_RESTORED_WITH_PAGES"
            && self.original_entry_result_verified && self.original_business_success_reported
            && !self.business_outcome_unknown && self.main_epoch_unchanged
            && self.owned_host_tree_retired && !self.automatic_retry
            && !self.whole_app_business_accepted && !self.production_ready
        {
            &["settings.pages", "settings.roundtrip"]
        } else {
            &[]
        }
    }
}


/// A completed historical case cannot launch work or renew a source lease.
/// It retains actual PM/Main tokens, Engine observations, original result FD,
/// source witness and final material fact from the one successful invocation.
pub(super) struct HistoricalLeafObservation {
    route: Route,
    main: HeldMainCustody,
    source: super::working_leaf_release::HistoricalNativeSourceWitness,
    result: super::clock_timer::ClockResultCustody,
    engine: Option<control::NativeLeafEngineEvidence>,
    identity: IdentityObservation,
}
impl HistoricalLeafObservation {
    pub(super) fn route(&self) -> Route { self.route }
    pub(super) fn binding(&self) -> &droidloom_supervisor::main_custody::RuntimeMainCustody {
        self.main.normal_observation().facts()
    }
    pub(super) fn guard_immutable(&self) -> Result<(),String> {
        self.main.guard_projection()?;
        require(self.main.completed.is_some(), "historical leaf lacks its actual final PM/Main bookend")?;
        self.source.guard_immutable()?;
        self.result.guard()?;
        self.identity.require_application(self.main.application.facts())?;
        if let Some(engine)=&self.engine { self.main.require_engine(engine)?; }
        Ok(())
    }
}

impl LeafObservation {
    pub(super) fn actual_application(&self) -> Result<&ApplicationInspection,String> {
        Ok(self.custody.as_ref().ok_or("leaf has no actual application custody")?.main.application.facts())
    }
    pub(super) fn retained_result_value(&self) -> Result<Value,String> {
        self.retained_bookends()?;
        let value=self.custody.as_ref().ok_or("leaf has no result custody")?.result.read()?;
        self.retained_bookends()?;
        Ok(value)
    }
    pub(super) fn seal_history_before(mut self, end: Instant) -> Result<(
        HistoricalLeafObservation,Vec<super::common_gate::CommonGateFact>,Vec<&'static str>,
        Value,ApplicationInspection,Value),String>
    {
        let original_end=self.custody.as_ref().ok_or("leaf history lacks actual custody")?.end.min(end);
        leaf_window(original_end,0)?;
        self.retained_bookends()?;
        require(self.original_entry_result_verified && self.main_epoch_unchanged
            && self.owned_host_tree_retired && !self.automatic_retry,
            "only the successful original retired leaf can seal case history")?;
        let identity=self.take_final_identity()?;
        let common=super::common_gate::from_leaf(&self,&identity)?;
        let business=self.verified_business_gates().to_vec();
        let evidence=serde_json::json!({
            "original_execution":serde_json::to_value(&self).map_err(|error|error.to_string())?,
            "actual_material_identity":serde_json::to_value(&identity).map_err(|error|error.to_string())?,
        });
        let actual=self.actual_application()?.clone();
        let HeldLeafCustody {main,release,result,final_identity:_,end:_} =
            self.custody.take().ok_or("leaf history custody already consumed")?;
        require(main.completed.is_some(), "history needs the real completed Main/PM pair")?;
        let source=release.seal_history_before(original_end)?;
        let source_comparison=source.comparison()?;
        let history=HistoricalLeafObservation {route:self.route,main,source,result,
            engine:self.engine_observations.take(),identity};
        history.guard_immutable()?;
        leaf_window(original_end,0)?;
        Ok((history,common,business,evidence,actual,source_comparison))
    }
}

struct Definition {
    source: usize,
    package: &'static str,
    request_schema: Option<&'static str>,
    plan_schema: Option<&'static str>,
    kind: Option<&'static str>,
    seconds: u64,
    state: Option<&'static str>,
    result_schema: &'static str,
}

impl Route {
    fn definition(self) -> Definition {
        use Route::*;
        match self {
            ContactsSearch => Definition {
                source: 0,
                package: "com.android.contacts",
                request_schema: None,
                plan_schema: Some("pocket4-final-system-case-plan-v1"),
                kind: Some("contacts_search"),
                seconds: 420,
                state: Some("ORIGINAL_CASE_VERIFIED_CLEAN"),
                result_schema: "pocket4-final-original-system-case-result-v1",
            },
            CalendarCore => Definition {
                source: 0,
                package: "com.android.calendar",
                request_schema: None,
                plan_schema: Some("pocket4-final-system-case-plan-v1"),
                kind: Some("calendar_core"),
                seconds: 930,
                state: Some("ORIGINAL_CASE_VERIFIED_CLEAN"),
                result_schema: "pocket4-final-original-system-case-result-v1",
            },
            CalendarReminder => Definition {
                source: 1,
                package: "com.android.calendar",
                request_schema: None,
                plan_schema: Some("pocket4-final-system-case-plan-v1"),
                kind: Some("calendar_reminder"),
                seconds: 690,
                state: Some("OWNED_NATURAL_CALENDAR_REMINDER_AND_UI_DELETE_VERIFIED"),
                result_schema: "pocket4-final-calendar-reminder22-current-result-v1",
            },
            SettingsSupportedPages => Definition {
                source: 13,
                package: "com.android.settings",
                request_schema: None,
                plan_schema: Some("pocket4-settings-pages-plan-v2"),
                kind: Some("settings_supported_pages"),
                seconds: 900,
                state: Some("SETTINGS_FONT_SCALE_RESTORED_WITH_PAGES"),
                result_schema: "pocket4-settings-pages-case-result-v3",
            },
            CameraPhoto => Definition {
                source: 3,
                package: "com.android.camera2",
                request_schema: Some("pocket4-camera-photo-display-input-v1"),
                plan_schema: Some("pocket4-final-camera-photo-plan-v1"),
                kind: Some("camera_photo"),
                seconds: 500,
                state: Some("PHOTO_AND_DISPLAY_VERIFIED_VISUAL_AND_OTHER_APP_GATES_PENDING"),
                result_schema: "pocket4-final-camera-photo-display-result-v1",
            },
            ClockTimer => Definition {
                source: 5,
                package: "com.android.deskclock",
                request_schema: None,
                plan_schema: Some("pocket4-final-app-case-plan-v1"),
                kind: Some("clock_timer"),
                seconds: 460,
                state: None,
                result_schema: "pocket4-final-app-case-coordinator-result-v1",
            },
            ClockTimerPair => Definition {
                source: 4,
                package: "com.android.deskclock",
                request_schema: Some("droidloom.clock-timer-pair-request.v1"),
                plan_schema: None,
                kind: None,
                seconds: 0,
                state: None,
                result_schema: "droidloom.clock-timer-pair-observation.v1",
            },
            ClockTimerRemaining | ClockExpiry | ClockAlarm => Definition {
                source: 4,
                package: "com.android.deskclock",
                request_schema: None,
                plan_schema: Some("pocket4-clock-current-execution-plan-v1"),
                kind: Some(match self {
                    ClockTimerRemaining => "timer15",
                    ClockExpiry => "expiry06",
                    _ => "alarm04",
                }),
                seconds: if self == ClockAlarm { 810 } else { 510 },
                state: Some("ORIGINAL_CLOCK_SCOPE_VERIFIED_CLEAN"),
                result_schema: "pocket4-current-clock-original-case-result-v1",
            },
            IhgLondon => Definition {
                source: 5,
                package: "com.ihg.apps.android",
                request_schema: None,
                plan_schema: Some("pocket4-final-app-case-plan-v1"),
                kind: Some("ihg_london"),
                seconds: 680,
                state: None,
                result_schema: "pocket4-final-app-case-coordinator-result-v1",
            },
            DocumentsSaf => Definition {
                source: 6,
                package: "com.android.documentsui",
                request_schema: None,
                plan_schema: Some("pocket4-documents-saf-current-execution-plan-v1"),
                kind: None,
                seconds: 1200,
                state: Some("ORIGINAL_SAF11_VERIFIED_CLEAN"),
                result_schema: "pocket4-final-documents-saf-original-case-result-v1",
            },
            DocumentsSearchSort => Definition {
                source: 7,
                package: "com.android.documentsui",
                request_schema: None,
                plan_schema: Some("pocket4-documents-current-execution-plan-v1"),
                kind: None,
                seconds: 1200,
                state: Some("ORIGINAL_FEATURES_SEARCH_SORT_VERIFIED_CLEAN"),
                result_schema: "pocket4-final-documents-original-case-result-v1",
            },
            GalleryRotation | GalleryVideo | GallerySeek | GalleryAlbum => Definition {
                source: match self {
                    GalleryRotation => 9,
                    GalleryVideo => 10,
                    GallerySeek => 11,
                    _ => 12,
                },
                package: "com.android.gallery3d",
                request_schema: Some("pocket4-gallery-image-request-v1"),
                plan_schema: None,
                kind: None,
                seconds: 1530,
                state: Some("CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED"),
                result_schema: "pocket4-gallery-image-scope-v1",
            },
        }
    }

    fn current_gallery(self) -> bool {
        matches!(
            self,
            Self::GalleryRotation | Self::GalleryVideo | Self::GallerySeek | Self::GalleryAlbum
        )
    }

    pub(super) fn package(self) -> &'static str {
        self.definition().package
    }
}

pub(super) fn original_window_seconds(route: Route) -> u64 {
    route.definition().seconds + 2 * 70 + 250 + 120
}

/// Bind the one canonical source/actual executable owner before a complete
/// qualification run. This grants no Main or application gate.
pub(super) fn qualification_release(
    selection: &FilePin, custody: &Arc<WorkingNativeSourceCustody>,
) -> Result<NativeRelease, String> {
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let source = &sources[0];
    NativeRelease::bind_working(custody, selection, SOURCE_CATALOG,
        &source.preparation, &source.entry)
}

fn require(ok: bool, message: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(message.into()) }
}

fn value(reference: &FilePin) -> Result<Value, String> {
    serde_json::from_slice(&pinned(reference)?).map_err(|e| e.to_string())
}

fn reference(value: &Value) -> Result<FilePin, String> {
    serde_json::from_value(value.clone()).map_err(|e| format!("leaf file reference invalid: {e}"))
}

fn ref_field(value: &Value, key: &str) -> Result<FilePin, String> {
    reference(
        value
            .get(key)
            .ok_or_else(|| format!("leaf input lacks {key}"))?,
    )
}

fn fixed_sources() -> Result<Vec<SelectedSource>, String> {
    let rows: Vec<SelectedSource> =
        serde_json::from_str(SOURCE_CATALOG).map_err(|e| e.to_string())?;
    require(
        rows.len() == 14 && rows.iter().enumerate().all(|(n, r)| r.index == n),
        "compiled leaf source catalog must retain the exact 14 preparations",
    )?;
    Ok(rows)
}

fn validate_selection_pin(selection: &FilePin) -> Result<(), String> {
    require(
        selection.path == Path::new(SELECTION_PATH)
            && selection.bytes == SELECTION_BYTES
            && selection.sha256 == SELECTION_SHA,
        "leaf dispatch requires the independently adopted complete 14-preparation selection",
    )
}

fn validate_selection_document(
    selection: &Value,
    sources: &[SelectedSource],
) -> Result<(), String> {
    exact_keys(
        selection,
        &[
            "schema",
            "selection_only",
            "source_controlled_cohort",
            "current_fixed_r1_bytes_recovered",
            "Android_actions",
            "Main_actions",
            "CURRENT_writes",
            "new_runtime_acceptance_count",
            "full_Main_execute_or_full_runtime_seed_executed",
            "historical_runtime_credit_transferred",
            "runtime_qualified",
            "production_ready",
            "selected_preparations",
            "source_selection_update",
        ],
    )?;
    require(
        selection["schema"] == "current-application-preparation-selection-v1"
            && selection["selection_only"] == true
            && selection["source_controlled_cohort"] == "cp3a-20261126-apps-r2"
            && selection["current_fixed_r1_bytes_recovered"] == false
            && selection["Android_actions"] == 0
            && selection["Main_actions"] == 0
            && selection["CURRENT_writes"] == 0
            && selection["new_runtime_acceptance_count"] == 0
            && selection["full_Main_execute_or_full_runtime_seed_executed"] == false
            && selection["historical_runtime_credit_transferred"] == false,
        "preparation selection must retain its source-only scope without runtime credit",
    )?;
    let preparations: Vec<FilePin> = serde_json::from_value(
        selection
            .get("selected_preparations")
            .ok_or("selection lacks its complete preparation roster")?
            .clone(),
    )
    .map_err(|e| format!("selection preparation roster invalid: {e}"))?;
    require(
        sources.len() == 14
            && preparations.len() == sources.len()
            && sources.iter().enumerate().all(|(index, source)| {
                source.index == index && source.preparation == preparations[index]
            }),
        "compiled leaf sources differ from the externally selected 14 preparations",
    )?;
    let update = &selection["source_selection_update"];
    exact_keys(
        update,
        &[
            "state",
            "changed_indices",
            "unchanged_indices",
            "added_indices",
            "catalog",
            "Android_actions",
            "CURRENT_writes",
            "current_Main_required",
            "native_release_adopted",
            "native_release_adoption_required",
            "runtime_enabled",
            "runtime_qualified",
            "production_ready",
        ],
    )?;
    require(
        update["state"] == "STAGED_CANONICAL_MAPPED_MAIN_AND_FOURTEEN_APP_SOURCES_NOT_ADOPTED"
            && update["changed_indices"] == json!([0,1,2,3,4,5,6,7,8,9,10,11,12])
            && update["unchanged_indices"] == json!([])
            && update["added_indices"] == json!([13])
            && update["Android_actions"] == 0
            && update["CURRENT_writes"] == 0
            && update["current_Main_required"] == true
            && update["native_release_adopted"] == false
            && update["native_release_adoption_required"] == true
            && update["runtime_enabled"] == false
            && update["runtime_qualified"] == false
            && update["production_ready"] == false
            && selection["runtime_qualified"] == false
            && selection["production_ready"] == false
            && ref_field(update,"catalog")? == (FilePin {
                path: "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/selection/leaf_sources.json".into(),
                bytes: SOURCE_CATALOG.len() as u64,
                sha256: hex::encode(Sha256::digest(SOURCE_CATALOG)),
            }),
        "canonical fourteen-source update must preserve mapped Main and native release prerequisites without runtime credit",
    )
}

pub(super) fn validate_selection(selection: &FilePin) -> Result<(), String> {
    // Check the exact external pin before reading anything, then check the
    // compiled dispatch catalog against those selected preparation bytes.
    // A newer selector must never silently dispatch an older source packet.
    validate_selection_pin(selection)?;
    validate_selection_document(&value(selection)?, &fixed_sources()?)
}

fn exact_keys(value: &Value, keys: &[&str]) -> Result<(), String> {
    let got: BTreeSet<_> = value
        .as_object()
        .ok_or("leaf request is not an object")?
        .keys()
        .map(String::as_str)
        .collect();
    require(
        got == keys.iter().copied().collect(),
        "leaf request has unexpected or missing fields",
    )
}

fn validate_case(
    plan: &LeafPlan,
    request: &Value,
    case: &Value,
    source: &SelectedSource,
    sources: &[SelectedSource],
) -> Result<(), String> {
    let d = plan.route.definition();
    if let Some(schema) = d.request_schema {
        require(
            request["schema"] == schema,
            "leaf request schema differs from its finite route",
        )?;
    }
    if let Some(schema) = d.plan_schema {
        require(
            case["schema"] == schema,
            "leaf plan schema differs from its finite route",
        )?;
        if let Some(kind) = d.kind {
            require(
                case["kind"] == kind,
                "leaf case kind differs from the selected application route",
            )?;
        }
        let expected = if plan.route == Route::CameraPhoto {
            &sources[2].preparation
        } else {
            &source.preparation
        };
        require(
            ref_field(case, "source_preparation")? == *expected,
            "leaf plan is not from its selected frozen preparation",
        )?;
        require(
            case["automatic_retry"] == false && case["whole_app_business_accepted"] == false,
            "leaf input changes the original no-retry or scoped acceptance contract",
        )?;
    }
    match plan.route {
        Route::ContactsSearch
        | Route::CalendarCore
        | Route::CalendarReminder
        | Route::SettingsSupportedPages => exact_keys(request, &["base_plan"])?,
        Route::CameraPhoto => {
            exact_keys(
                request,
                &[
                    "schema",
                    "plan",
                    "source_preparation",
                    "automatic_retry",
                    "whole_app_business_accepted",
                ],
            )?;
            require(
                ref_field(request, "source_preparation")? == sources[2].preparation
                    && request["automatic_retry"] == false
                    && request["whole_app_business_accepted"] == false,
                "camera display input no longer binds the original photo preparation",
            )?;
        }
        Route::GalleryRotation | Route::GalleryVideo | Route::GallerySeek | Route::GalleryAlbum => {
            exact_keys(
                request,
                &[
                    "schema",
                    "baseline",
                    "qualification",
                    "native_release",
                    "output",
                ],
            )?
        }
        _ => exact_keys(request, &["plan"])?,
    }
    require(
        (plan.route == Route::CameraPhoto) == plan.output.is_some(),
        "only the camera display wrapper accepts an explicit output argument",
    )?;
    Ok(())
}

fn case_document(plan: &LeafPlan, request: &Value) -> Result<(Option<FilePin>, Value), String> {
    if plan.route.definition().plan_schema.is_none() {
        return Ok((None, request.clone()));
    }
    let name = if matches!(
        plan.route,
        Route::ContactsSearch
            | Route::CalendarCore
            | Route::CalendarReminder
            | Route::SettingsSupportedPages
    ) {
        "base_plan"
    } else {
        "plan"
    };
    let pin = ref_field(request, name)?;
    let case = value(&pin)?;
    Ok((Some(pin), case))
}

// These documents compare the current normal factory's opaque facts. They
// cannot construct Main, a package observation, a data handle, or a business gate.
const NATIVE_BASELINE_SCHEMA: &str = "droidloom.native-leaf-business-baseline.v1";
const NATIVE_QUALIFICATION_SCHEMA: &str = "droidloom.native-leaf-business-qualification.v1";
const NORMAL_SOURCE_RECIPE_BYTES: u64 = 815042;
const NORMAL_SOURCE_RECIPE_SHA: &str =
    "16777fe0bede8ac8524a28a84e908303fc13d3696d0d468401082affc916e1d2";

fn canonical_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let ordered: std::collections::BTreeMap<_, _> =
                map.iter().map(|(key, value)| (key, canonical_value(value))).collect();
            serde_json::to_value(ordered).expect("JSON values are serializable")
        }
        Value::Array(values) => Value::Array(values.iter().map(canonical_value).collect()),
        _ => value.clone(),
    }
}

fn canonical_sha(value: &Value) -> Result<String, String> {
    serde_json::to_vec(&canonical_value(value))
        .map(|raw| hex::encode(Sha256::digest(raw)))
        .map_err(|error| error.to_string())
}

// Saved pre-install IHG inventory remains a comparison document. Its exact
// relationship to the installed helper is checked by the fixed canonical IHG
// source/build/install/thirteen-command chain during the actual owned leaf.
// The ordinary invocation's fresh before/after inventories are separately
// opaque observations and must have identical complete tables.
fn compare_saved_inventory(
    actual: &ApplicationInspection,
    inventory: &Value,
) -> Result<(), String> {
    if actual.package != "com.ihg.apps.android" {
        return require(inventory.is_null(),
            "non-IHG baseline must not carry a user-0 inventory");
    }
    let facts: droidloom_supervisor::package_inventory_observation::UserZeroPackageInventoryFacts =
        serde_json::from_value(inventory.clone()).map_err(|error| error.to_string())?;
    facts.validate_comparison(&actual.epoch)?;
    require(facts.records().get(actual.package.as_str()) == Some(&actual.uid),
        "saved complete inventory differs from the actual target package UID")
}

// This is deliberately a private comparison helper, including in its tests.
// Only main_binding below supplies core from a live, held normal factory.
fn compare_native_main_documents(
    case: &Value,
    actual: &ApplicationInspection,
    core: &Value,
    baseline_ref: &FilePin,
    baseline: &Value,
    qualification: &Value,
) -> Result<(), String> {
    exact_keys(baseline, &[
        "schema", "native_owner", "runtime_observation", "framework_epoch",
        "observation", "classpath", "artifacts", "data_continuity", "sampling",
        "observation_fds", "captured_unix_ns", "comparison_only",
        "account_contents_read", "whole_app_business_accepted", "production_ready",
        "user_zero_package_inventory",
    ])?;
    compare_saved_inventory(actual, &baseline["user_zero_package_inventory"])?;
    require(
        baseline["schema"] == NATIVE_BASELINE_SCHEMA
            && core["schema"] == "droidloom.native-leaf-baseline.v1"
            && core["application"] == serde_json::to_value(actual).map_err(|e| e.to_string())?
            && core["main"]["epoch"] == serde_json::to_value(&actual.epoch).map_err(|e| e.to_string())?
            && baseline["native_owner"] == *core
            && core["comparison_only"] == true
            && core["account_contents_read"] == false
            && core["business_acceptance_evaluated"] == false
            && baseline["comparison_only"] == true
            && baseline["account_contents_read"] == false
            && baseline["whole_app_business_accepted"] == false
            && baseline["production_ready"] == false,
        "native leaf baseline differs from the actual Main/package/target-only comparison",
    )?;
    let runtime = &baseline["runtime_observation"];
    let epoch = &baseline["framework_epoch"];
    let binding = &epoch["binding"];
    require(
        runtime["schema"] == "droidloom.native-leaf-runtime-comparison.v1"
            && runtime["native_owner"] == *core
            && runtime["normal_host_release"] == core["main"]["normal_host_release"]
            && runtime["main_epoch"] == *epoch
            && runtime["saved_document_can_create_authority"] == false
            && runtime["business_acceptance_evaluated"] == false
            && ["observation", "classpath", "artifacts", "data_continuity"]
                .iter().all(|key| runtime[key] == baseline[key])
            && epoch["schema"] == "pocket4-framework-epoch-v1"
            && binding["boot_id"] == core["main"]["epoch"]["boot_id"]
            && epoch["sha256"].as_str() == Some(canonical_sha(binding)?.as_str()),
        "native leaf runtime components or complete framework epoch binding differ",
    )?;
    for (role, field) in [("init", "init"), ("zygote64", "zygote"), ("system_server", "framework")] {
        require(
            binding["processes"][role]["host_pid"] == core["main"][field]["host_pid"]
                && binding["processes"][role]["start_ticks"] == core["main"][field]["start_ticks"],
            "native leaf framework process differs from the actual held Main",
        )?;
    }
    let rows = core["data"]["directories"].as_array()
        .ok_or("native leaf actual target directory array absent")?;
    require(rows.len() == 4, "native leaf actual target directory set differs")?;
    let mut directories = serde_json::Map::new();
    for (row, prefix) in rows[2..].iter().zip(["user/0", "user_de/0"]) {
        let name = format!("{prefix}/{}", actual.package);
        require(row["path"].as_str() == Some(format!("/data/{name}").as_str()),
            "native leaf target directory does not belong to this package")?;
        directories.insert(name, json!({
            "device":row["device"], "inode":row["inode"], "mount_id":row["mount_id"],
            "mode":row["mode"], "uid":row["host_uid"], "gid":row["host_gid"],
        }));
    }
    let mut package_uids = serde_json::Map::new();
    package_uids.insert(actual.package.clone(), json!(actual.uid));
    require(
        baseline["data_continuity"] == json!({
            "schema":"droidloom.native-leaf-target-working-data.v1",
            "scope":"actual_inspected_user_0_package_only",
            "package_uids":package_uids, "directories":directories,
            "working_data_root":core["data"]["data_root"],
            "original_copy_origin":core["main"]["persistent_data"]["original_copy_origin"],
            "original_directory_identity_compared":false, "account_contents_read":false,
        }),
        "native leaf document broadened or changed actual target data metadata",
    )?;
    let sampling = &baseline["sampling"];
    let span = sampling["finished_monotonic_ns"].as_u64().and_then(|end| {
        sampling["started_monotonic_ns"].as_u64().and_then(|start| end.checked_sub(start))
    });
    let closed = &baseline["observation_fds"];
    require(
        sampling["double_observation_pairs"] == 3 && sampling["pairs_equal"] == true
            && span.is_some_and(|n| (10_000_000_000..=120_000_000_000).contains(&n))
            && closed["acquired"].as_u64().is_some_and(|n| n > 0)
            && closed["acquired"] == closed["closed"]
            && closed["acquired"] == closed["close_attempts"]
            && closed["remaining"] == 0 && closed["errors"] == json!([]),
        "native leaf comparison lacks complete sampling or descriptor retirement",
    )?;
    exact_keys(qualification, &[
        "schema", "baseline", "normal_source_recipe", "core_sha256", "main_epoch_sha256",
        "actual_main_and_target_metadata_observed", "working_copy_lineage_bound",
        "working_target_directory_identity_preserved", "fixed_main_readonly_entry_observed",
        "comparison_only", "account_contents_read", "business_actions_admitted",
        "whole_app_business_accepted", "production_ready", "observation_fds",
        "user_zero_package_inventory_sha256",
    ])?;
    require(
        qualification["schema"] == NATIVE_QUALIFICATION_SCHEMA
            && ref_field(qualification, "baseline")? == *baseline_ref
            && qualification["normal_source_recipe"] == json!({
                "bytes":NORMAL_SOURCE_RECIPE_BYTES, "sha256":NORMAL_SOURCE_RECIPE_SHA,
            })
            && qualification["core_sha256"].as_str() == Some(canonical_sha(core)?.as_str())
            && qualification["user_zero_package_inventory_sha256"].as_str()
                == Some(canonical_sha(&baseline["user_zero_package_inventory"])?.as_str())
            && qualification["main_epoch_sha256"] == epoch["sha256"]
            && qualification["observation_fds"] == *closed
            && qualification["actual_main_and_target_metadata_observed"] == true
            && qualification["working_copy_lineage_bound"] == true
            && qualification["working_target_directory_identity_preserved"] == true
            && qualification["fixed_main_readonly_entry_observed"] == true
            && qualification["comparison_only"] == true
            && qualification["account_contents_read"] == false
            && qualification["business_actions_admitted"] == false
            && qualification["whole_app_business_accepted"] == false
            && qualification["production_ready"] == false,
        "native leaf qualification differs in source, actual comparison, or scope",
    )?;
    if let Some(profile) = case.get("target_profile") {
        require(
            profile["package"].as_str() == Some(actual.package.as_str())
                && profile["uid"].as_u64() == Some(u64::from(actual.uid))
                && profile["version_code"].as_u64() == Some(actual.version_code),
            "leaf target profile differs from current PM identity",
        )?;
        let declared: BTreeSet<_> = profile["apks"].as_array()
            .ok_or("leaf target APK set missing")?.iter()
            .map(|row| (row["bytes"].as_u64(), row["sha256"].as_str())).collect();
        let installed: BTreeSet<_> = actual.apks.iter()
            .map(|row| (Some(row.bytes), Some(row.sha256.as_str()))).collect();
        require(declared == installed && declared.len() == actual.apks.len(),
            "leaf target APK bytes differ from the current complete selected official set")?;
    }
    Ok(())
}

fn main_binding(
    case: &Value,
    actual: &ApplicationInspection,
    main: &HeldMainCustody,
    held: &NativeLeafBaselineObservation<'_>,
) -> Result<(FilePin, FilePin), String> {
    main.require_application(actual)?;
    require(held.application() == actual, "native leaf context belongs to another package")?;
    require(held.inventory_facts().is_some() == (actual.package == "com.ihg.apps.android"),
        "IHG requires the actual complete pre-invocation inventory; other routes do not")?;
    let baseline_ref = ref_field(case, "baseline")?;
    let qualification_ref = ref_field(case, "qualification")?;
    require((1..=16 * 1024 * 1024).contains(&baseline_ref.bytes)
        && (1..=262144).contains(&qualification_ref.bytes),
        "native leaf baseline or qualification exceeds the normal producer's bound")?;
    let baseline = value(&baseline_ref)?;
    let qualification = value(&qualification_ref)?;
    held.compare(&baseline["native_owner"]).map_err(|error| error.to_string())?;
    let core = serde_json::to_value(held.facts()).map_err(|error| error.to_string())?;
    compare_native_main_documents(case, actual, &core, &baseline_ref, &baseline, &qualification)?;
    Ok((baseline_ref, qualification_ref))
}

fn output_path(plan: &LeafPlan, request: &Value, case: &Value) -> Result<PathBuf, String> {
    let root = if plan.route == Route::CameraPhoto {
        plan.output.clone().ok_or("camera wrapper output missing")?
    } else if plan.route.definition().plan_schema.is_none() {
        PathBuf::from(request["output"].as_str().ok_or("gallery output missing")?)
    } else {
        PathBuf::from(case["case_root"].as_str().ok_or("case root missing")?)
    };
    require(
        root.is_absolute()
            && root.parent() == Some(Path::new(QUALIFICATION))
            && root
                .parent()
                .ok_or("output parent absent")?
                .canonicalize()
                .map_err(|e| e.to_string())?
                == Path::new(QUALIFICATION),
        "leaf result must remain under the original private qualification directory",
    )?;
    require(
        !root.components().any(|x| {
            matches!(
                x,
                std::path::Component::ParentDir | std::path::Component::CurDir
            )
        }),
        "leaf result path is not canonical",
    )?;
    let result = if matches!(plan.route, Route::ClockTimer | Route::IhgLondon) {
        root.join("coordinator/result.json")
    } else {
        root.join("result.json")
    };
    require(
        !result.try_exists().map_err(|e| e.to_string())?,
        "a prior result exists; explicit reconciliation is required before a new plan",
    )?;
    Ok(result)
}

fn command(plan: &LeafPlan, source: &SelectedSource) -> Result<Command, String> {
    let mut command = Command::new("/usr/bin/python3");
    command
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("HOME", "/root")
        .env("LANG", "C.UTF-8")
        .args(["-I", "-B"])
        .arg(&source.entry.path);
    if plan.route == Route::CameraPhoto {
        command
            .arg("execute")
            .arg("--input")
            .arg(&plan.request.path)
            .arg("--expect-input-sha256")
            .arg(&plan.request.sha256)
            .arg("--output")
            .arg(plan.output.as_ref().ok_or("camera output missing")?);
    } else {
        command
            .arg("--preparation")
            .arg(&source.preparation.path)
            .arg("--expect-preparation-sha256")
            .arg(&source.preparation.sha256)
            .arg("execute")
            .arg("--request")
            .arg(&plan.request.path)
            .arg("--expect-request-sha256")
            .arg(&plan.request.sha256);
    }
    Ok(command)
}

fn claim(
    plan: &LeafPlan,
    actual: &ApplicationInspection,
    source: &SelectedSource,
) -> Result<(), String> {
    let path =
        Path::new(QUALIFICATION).join(format!("native-app-dispatch-{}.json", plan.request.sha256));
    let bytes = serde_json::to_vec_pretty(&json!({
        "schema": "droidloom-native-application-leaf-claim-v1",
        "route": plan.route, "request": plan.request, "preparation": source.preparation,
        "entry_source": source.entry, "observed_identity": actual,
        "automatic_retry": false, "whole_app_business_accepted": false,
        "production_ready": false
    }))
    .map_err(|e| e.to_string())?;
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(&path)
        .map_err(|e| format!("leaf invocation claim not new; do not replay: {e}"))?;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| e.to_string())?;
    fs::File::open(QUALIFICATION)
        .and_then(|f| f.sync_all())
        .map_err(|e| e.to_string())?;
    Ok(())
}

// These comparisons consume only the result returned by the actually executed,
// source-admitted entry. They cannot construct HeldLeafCustody or grant Main.
fn settings_pin(value: &Value) -> Result<FilePin, String> {
    let pin = reference(value)?;
    require(pin.path.is_absolute()
        && !pin.path.components().any(|part| matches!(part,
            std::path::Component::ParentDir | std::path::Component::CurDir))
        && crate::release::valid_sha(&pin.sha256),
        "Settings observation has an invalid bounded evidence reference")?;
    Ok(pin)
}

fn settings_provider(value: &Value) -> Result<f64, String> {
    exact_keys(value, &["present", "text", "effective"])?;
    let number = value["effective"].as_f64().ok_or("Settings provider scale is not numeric")?;
    require(number.is_finite() && (0.5..=2.0).contains(&number),
        "Settings provider scale is outside the source-owned range")?;
    match value["present"].as_bool() {
        Some(false) => require(value["text"].is_null() && number == 1.0,
            "Absent font_scale must retain its actual default effect")?,
        Some(true) => {
            let text = value["text"].as_str().ok_or("Present font_scale lacks its original text")?;
            let parts: Vec<_> = text.split('.').collect();
            let canonical = (1..=2).contains(&parts.len())
                && !parts[0].is_empty()
                && parts[0].bytes().all(|byte| byte.is_ascii_digit())
                && (parts[0] == "0" || !parts[0].starts_with('0'))
                && (parts.len() == 1 || ((1..=8).contains(&parts[1].len())
                    && parts[1].bytes().all(|byte| byte.is_ascii_digit())));
            require(canonical && text.parse::<f64>().ok() == Some(number),
                "Settings original provider text and numeric value differ")?;
        }
        _ => return Err("Settings provider presence must be a real boolean".into()),
    }
    Ok(number)
}

fn settings_configuration(value: &Value) -> Result<f64, String> {
    exact_keys(value, &["font_scale", "other_configuration_fields", "resource_fields", "raw_sha256"])?;
    let number = value["font_scale"].as_f64().ok_or("Settings configuration lacks font_scale")?;
    require(number.is_finite() && (0.5..=2.0).contains(&number)
        && value["raw_sha256"].as_str().is_some_and(crate::release::valid_sha),
        "Settings actual configuration has invalid scale or full digest")?;
    for key in ["other_configuration_fields", "resource_fields"] {
        let rows = value[key].as_array().ok_or("Settings configuration complement missing")?;
        require(rows.len() <= 128 && rows.iter().all(|row| row.as_str().is_some_and(|text|
            !text.is_empty() && text.len() <= 131072 && text.len() % 2 == 0
                && text.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))),
            "Settings configuration complement is not bounded encoded source data")?;
    }
    Ok(number)
}

fn settings_command(value: &Value, operation: &str, argv: &[&str], mutation: bool)
    -> Result<(), String>
{
    exact_keys(value, &["operation", "argv", "mutation", "result", "stdout", "stderr"])?;
    require(value["operation"] == operation && value["argv"] == json!(argv)
        && value["mutation"] == mutation,
        "Settings command differs from the fixed actual font_scale operation")?;
    require(settings_pin(&value["result"])?.bytes > 0,
        "Settings command lacks its completed recorder result")?;
    settings_pin(&value["stdout"])?;
    settings_pin(&value["stderr"])?;
    Ok(())
}

fn settings_snapshot<'a>(value: &'a Value, phase: &str, expected: &Value,
    scope: &Value, complement: &Value) -> Result<(&'a Value, &'a Value, f64), String>
{
    exact_keys(value, &["phase", "provider", "configuration", "provider_command",
        "configuration_command", "scope"])?;
    settings_provider(&value["provider"])?;
    let scale = settings_configuration(&value["configuration"])?;
    require(value["phase"] == phase && value["provider"] == *expected
        && value["scope"] == *scope
        && value["configuration"]["other_configuration_fields"] == complement["other_configuration_fields"]
        && value["configuration"]["resource_fields"] == complement["resource_fields"],
        "Settings snapshot changed phase, original owner, value or unrelated configuration")?;
    let provider = &value["provider_command"];
    let config = &value["configuration_command"];
    settings_command(provider, &format!("{phase}-value"),
        &["/system/bin/settings", "--user", "0", "get", "system", "font_scale"], false)?;
    settings_command(config, &format!("{phase}-config"),
        &["/system/bin/am", "get-config", "--proto"], false)?;
    let raw = format!("{}\n", if expected["present"] == true {
        expected["text"].as_str().ok_or("Settings expected text missing")?
    } else { "null" });
    let stdout = settings_pin(&provider["stdout"])?;
    let config_stdout = settings_pin(&config["stdout"])?;
    require(stdout.bytes == raw.len() as u64
        && stdout.sha256 == hex::encode(Sha256::digest(raw.as_bytes()))
        && (1..=65536).contains(&config_stdout.bytes)
        && config_stdout.sha256 == value["configuration"]["raw_sha256"],
        "Settings snapshot differs from its actual provider/configuration stdout pins")?;
    Ok((provider, config, scale))
}

fn settings_settle<'a>(snapshots: &'a [Value], cursor: &mut usize, prefix: &str,
    expected: &Value, scope: &Value, complement: &Value,
    commands: &mut Vec<&'a Value>) -> Result<(), String>
{
    let mut count = 0;
    let mut last = None;
    while *cursor < snapshots.len() && snapshots[*cursor]["phase"].as_str()
        .is_some_and(|phase| phase.starts_with(&format!("{prefix}-"))) {
        require(count < 12, "Settings effect sampling exceeded its fixed source bound")?;
        let (provider, config, scale) = settings_snapshot(&snapshots[*cursor],
            &format!("{prefix}-{count:02}"), expected, scope, complement)?;
        commands.extend([provider, config]);
        last = Some(scale);
        count += 1;
        *cursor += 1;
    }
    let expected_scale = settings_provider(expected)?;
    require(count > 0 && last.is_some_and(|scale| (scale - expected_scale).abs() <= 0.00001),
        "Settings apply/reopen/restore lacks the actual final framework effect")
}

fn settings_font_scale_facts(result: &Value) -> Result<(), String> {
    let value = &result["setting_roundtrip"];
    exact_keys(value, &["schema", "namespace", "key", "user", "original", "selected",
        "state", "apply_observed", "reopen_observed", "restore_observed", "apply_claim",
        "reopen_claim", "provider_writes", "readonly_commands", "commands", "snapshots",
        "pending_command", "automatic_write_retry", "compare_and_swap_claimed",
        "permission_or_account_write_authorized", "whole_app_business_accepted"])?;
    let original_scale = settings_provider(&value["original"])?;
    let selected = if (original_scale - 1.15).abs() <= 0.00001 { "1.0" } else { "1.15" };
    require(value["schema"] == "pocket4-settings-font-scale-facts-v1"
        && value["namespace"] == "system" && value["key"] == "font_scale" && value["user"] == 0
        && value["selected"] == selected && value["state"] == "restored_verified"
        && value["apply_observed"] == true && value["reopen_observed"] == true
        && value["restore_observed"] == true && value["provider_writes"] == 2
        && value["pending_command"].is_null() && value["automatic_write_retry"] == false
        && value["compare_and_swap_claimed"] == false
        && value["permission_or_account_write_authorized"] == false
        && value["whole_app_business_accepted"] == false,
        "Settings requires its one actual changed, reopened and restored font_scale transaction")?;
    let claims = result["native_claims"].as_array().ok_or("Settings owned claims missing")?;
    let scopes = result["recorder_scopes"].as_array().ok_or("Settings original recorder scopes missing")?;
    require(claims.len() == 2 && scopes.len() == 2 && claims[0] != claims[1] && scopes[0] != scopes[1]
        && value["apply_claim"] == claims[0] && value["reopen_claim"] == claims[1]
        && result["normally_closed_claims"] == result["native_claims"]
        && result["host_flow_contexts_closed"] == result["recorder_scopes"],
        "Settings persistence must use two distinct normally closed owned launches")?;
    for row in claims.iter().chain(scopes.iter()) { settings_pin(row)?; }
    let snapshots = value["snapshots"].as_array().ok_or("Settings actual snapshots missing")?;
    let commands = value["commands"].as_array().ok_or("Settings actual command chain missing")?;
    require((6..=39).contains(&snapshots.len()) && commands.len() == snapshots.len() * 2 + 2
        && value["readonly_commands"].as_u64() == Some((snapshots.len() * 2) as u64),
        "Settings bounded read/write counts differ from the complete actual trace")?;
    let original = &value["original"];
    let complement = &snapshots[0]["configuration"];
    let selected_value = json!({"present":true, "text":selected,
        "effective":selected.parse::<f64>().map_err(|e| e.to_string())?});
    let mut expected_commands = Vec::new();
    for (index, phase) in ["original", "before-apply"].iter().enumerate() {
        let (provider, config, scale) = settings_snapshot(&snapshots[index], phase,
            original, &scopes[0], complement)?;
        require((scale - original_scale).abs() <= 0.00001,
            "Settings original provider and framework effect disagree before mutation")?;
        expected_commands.extend([provider, config]);
    }
    let apply = &commands[expected_commands.len()];
    settings_command(apply, "apply",
        &["/system/bin/settings", "--user", "0", "put", "system", "font_scale", selected], true)?;
    require(settings_pin(&apply["stdout"])?.bytes == 0,
        "Settings normal apply returned unexpected output")?;
    expected_commands.push(apply);
    let mut cursor = 2;
    settings_settle(snapshots, &mut cursor, "applied", &selected_value, &scopes[0],
        complement, &mut expected_commands)?;
    settings_settle(snapshots, &mut cursor, "reopened", &selected_value, &scopes[1],
        complement, &mut expected_commands)?;
    let snapshot = snapshots.get(cursor).ok_or("Settings before-restore snapshot missing")?;
    let (provider, config, _) = settings_snapshot(snapshot, "before-restore",
        &selected_value, &scopes[1], complement)?;
    expected_commands.extend([provider, config]);
    cursor += 1;
    let restore = commands.get(expected_commands.len()).ok_or("Settings normal restore command missing")?;
    let mut restore_argv = vec!["/system/bin/settings", "--user", "0"];
    let restore_stdout: &[u8] = if original["present"] == true {
        restore_argv.extend(["put", "system", "font_scale",
            original["text"].as_str().ok_or("Settings original string missing")?]);
        b""
    } else {
        restore_argv.extend(["delete", "system", "font_scale"]);
        b"Deleted 1 rows\n"
    };
    settings_command(restore, "restore", &restore_argv, true)?;
    let restore_pin = settings_pin(&restore["stdout"])?;
    require(restore_pin.bytes == restore_stdout.len() as u64
        && restore_pin.sha256 == hex::encode(Sha256::digest(restore_stdout)),
        "Settings restore must preserve the exact original string or absence")?;
    expected_commands.push(restore);
    settings_settle(snapshots, &mut cursor, "restored", original, &scopes[1],
        complement, &mut expected_commands)?;
    require(cursor == snapshots.len() && expected_commands.len() == commands.len()
        && expected_commands.iter().zip(commands).all(|(expected, actual)| **expected == *actual)
        && commands.iter().map(|row| row["result"].clone()).collect::<Vec<_>>()
            .iter().enumerate().all(|(index, pin)| !commands[..index].iter().any(|row| row["result"] == *pin)),
        "Settings complete command chain was reordered, repeated or extended")?;
    Ok(())
}

fn settings_v3_terminal(printed: &Value, result: &Value, case_ref: Option<&FilePin>)
    -> Result<(), String>
{
    exact_keys(printed, &["result", "state", "case_business_success_verified", "scope",
        "whole_app_business_accepted"])?;
    let empty = |key: &str| result["cancellation_commit"][key].as_array().is_some_and(Vec::is_empty);
    let two = |key: &str| result[key].as_array().is_some_and(|rows| rows.len() == 2);
    require(result["case_business_success_verified"] == true
        && printed["case_business_success_verified"] == true && printed["state"] == result["state"]
        && result["scope"] == json!(["settings.pages", "settings.roundtrip"])
        && printed["scope"] == result["scope"] && result["accepted_gates"] == result["scope"]
        && result["remaining_gates"] == json!(["settings.permissions", "identity", "lifecycle",
            "stability", "data_permissions", "release_scope", "ui_observation"])
        && Some(ref_field(result, "base_plan")?).as_ref() == case_ref
        && result["all_five_pages_observed"] == true
        && result["identity_permissions_directories_preserved"] == true
        && result["permission_interfaces"] == json!({"settings_permissions_gate_accepted":false,
            "readonly_input_error_verified":false, "account_state_observed":false})
        && result["complete_task_baseline_restored"] == true
        && result["final_source_identity_chain_unchanged"] == true && result["evidence_witness_closed"] == true
        && result["native_launch_count"] == 2 && result["page_route_count"] == 5
        && result["observation_count"] == 9 && two("launches") && two("normal_closes")
        && ["pending_route", "pending_UI"].iter().all(|key| result.get(*key).is_some_and(Value::is_null))
        && result.get("unknown_retained_without_further_mutation").is_none_or(|v| v == false)
        && result.get("unknown_or_conflicting_setting_retained_without_replay").is_none_or(|v| v == false)
        && result["setting_writes"] == 2 && result["provider_writes"] == 2
        && ["permission_writes", "account_writes", "package_writes", "other_provider_writes"]
            .iter().all(|key| result[*key] == 0)
        && result["Android_runtime_qualification_inferred_from_source"] == false
        && result["Binder_UID_cleanup_verified"] == false
        && result["Main_before"].is_object() && result["Main_before"] == result["Main_after"]
        && empty("observed_before_commit") && empty("pending_at_commit")
        && result["cancellation_commit"]["decision_frozen_after_host_context_close"] == true,
        "Settings v3 requires exact pages/restore, original retirement and no other business credit")?;
    let pages = result["pages"].as_array().ok_or("Settings five actual pages missing")?;
    require(pages.len() == 5, "Settings requires all five source-owned page classes")?;
    let profile = [
        ("system", "com.android.settings.Settings$SystemDashboardActivity"),
        ("network", "com.android.settings.Settings$NetworkDashboardActivity"),
        ("display", "com.android.settings.Settings$DisplaySettingsActivity"),
        ("storage", "com.android.settings.Settings$StorageDashboardActivity"),
        ("applications", "com.android.settings.Settings$ManageApplicationsActivity"),
    ];
    let home = "com.android.settings.homepage.SettingsHomepageActivity";
    let mut observations = vec![(&result["initial_home"], "home", home)];
    observations.extend(pages.iter().zip(profile).map(|(row, (name, activity))| (row, name, activity)));
    observations.push((&result["applied_page"], profile[4].0, profile[4].1));
    observations.push((&result["reopened_home"], "home", home));
    observations.push((&result["restored_home"], "home", home));
    let mut init = None;
    let mut receipts = BTreeSet::new();
    for (row, name, activity) in observations {
        exact_keys(row, &["summary", "recorder_result", "observation", "PNG"])?;
        let summary = &row["summary"];
        let pid = summary["android_init_host_pid"].as_u64().filter(|pid| *pid > 0 && *pid <= i32::MAX as u64)
            .ok_or("Settings actual Main pid is missing")?;
        require(summary["page"] == name && summary["package"] == "com.android.settings"
            && summary["activity"] == activity && init.is_none_or(|old| old == pid)
            && summary["expected_title_observed"] == true
            && summary["source"] == "actual-native-tree-and-scoped-PNG"
            && summary["whole_app_business_accepted"] == false
            && summary["visible_control_count"].as_u64().is_some_and(|n| (2..=8192).contains(&n))
            && summary["visible_label_count"].as_u64().is_some_and(|n| (3..=8192).contains(&n))
            && summary["scoped_pixel_sha256"].as_str().is_some_and(crate::release::valid_sha)
            && summary["window_token"].as_str().is_some_and(|s| (1..=32).contains(&s.len())
                && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))),
            "Settings page lacks its exact actual window, native controls or scoped pixels")?;
        init = Some(pid);
        let recorder = settings_pin(&row["recorder_result"])?;
        require(recorder.bytes > 0 && receipts.insert(recorder.path),
            "Settings repeated or omitted an actual UI recorder result")?;
        require(settings_pin(&row["observation"])?.bytes > 0
            && (1..=32 * 1024 * 1024).contains(&settings_pin(&row["PNG"])?.bytes),
            "Settings actual observation or bounded PNG missing")?;
    }
    settings_font_scale_facts(result)
}

fn terminal_result(
    route: Route,
    printed: &Value,
    result: &Value,
    case_ref: Option<&FilePin>,
    baseline: &FilePin,
    qualification: &FilePin,
    source: &SelectedSource,
) -> Result<(), String> {
    let d = route.definition();
    require(
        result["schema"] == d.result_schema
            && result["whole_app_business_accepted"] == false
            && result["automatic_retry"] == false
            && printed["whole_app_business_accepted"] == false,
        "leaf result schema or original scoped/no-retry claims differ",
    )?;
    require(
        result.get("outcome_unknown").is_none_or(|x| x == false)
            && printed.get("outcome_unknown").is_none_or(|x| x == false)
            && result.get("entry_error").is_none()
            && result.get("error").is_none_or(Value::is_null)
            && result
                .get("secondary_errors")
                .is_none_or(|x| x.as_array().is_some_and(Vec::is_empty)),
        "leaf retained an error, cancellation, unknown outcome or secondary failure",
    )?;
    if let Some(expected) = d.state {
        require(
            result["state"] == expected,
            "leaf did not report its exact original successful state",
        )?;
    }
    if matches!(
        route,
        Route::GalleryRotation | Route::GalleryVideo | Route::GallerySeek | Route::GalleryAlbum
    ) {
        require(
            result["business_scope_completed"] == true
                && result["outcome_unknown"] == false
                && result["entry_cancellation_signals"]
                    .as_array()
                    .is_some_and(Vec::is_empty)
                && ref_field(result, "baseline")? == *baseline
                && ref_field(result, "qualification")? == *qualification
                && ref_field(result, "source_preparation")? == source.preparation
                && printed["state"] == result["state"],
            "gallery result lacks completed business/cleanup scope for this Main and preparation",
        )?;
    } else if route == Route::SettingsSupportedPages {
        settings_v3_terminal(printed, result, case_ref)?;
    } else if route == Route::CameraPhoto {
        require(
            printed["success"] == true
                && printed["photo_capture_persistence_verified"] == true
                && printed["exit_code"] == 0
                && result["success"] == true
                && result["photo_capture_persistence_verified"] == true
                && result["display_lease_qualified"] == true
                && Some(ref_field(result, "plan")?).as_ref() == case_ref,
            "camera wrapper did not complete its original photo/display contract",
        )?;
    } else {
        let field = if matches!(route, Route::ClockTimer | Route::IhgLondon) {
            "base_plan"
        } else {
            "plan"
        };
        require(
            Some(ref_field(result, field)?).as_ref() == case_ref,
            "leaf terminal receipt is for a different actual case plan",
        )?;
        let key = if matches!(route, Route::ClockTimer | Route::IhgLondon) {
            "ok"
        } else {
            "case_business_success_verified"
        };
        require(
            result[key] == true && printed[key] == true,
            "leaf lacks actual business success in both saved result and process output",
        )?;
        if key != "ok" {
            require(
                printed["state"] == result["state"],
                "printed and saved leaf states differ",
            )?;
        }
    }
    if matches!(route, Route::ClockTimer | Route::IhgLondon) {
        let child_ref = ref_field(result, "worker_result")?;
        let child = value(&child_ref)?;
        let host_ref = ref_field(result, "worker_host_result")?;
        pinned(&host_ref)?;
        require(
            child["ok"] == true
                && child["error"].is_null()
                && child["secondary_errors"]
                    .as_array()
                    .is_some_and(Vec::is_empty)
                && child["automatic_retry"] == false
                && child["whole_app_business_accepted"] == false
                && Some(ref_field(&child, "base_plan")?).as_ref() == case_ref,
            "coordinator result lacks the actual original worker result for this case",
        )?;
        if route == Route::IhgLondon {
            require(
                child["schema"] == "pocket4-final-ihg-public-london-result-v1"
                    && child["public_london_input_and_readback_completed"] == true
                    && child["business_success_verified"] == false
                    && child["business_outcome_unknown"] == true,
                "IHG route must retain its actual input/readback-only scope and unresolved business outcome",
            )?;
        } else {
            require(
                child["schema"] == "pocket4-final-clock-timer-core-result-v1"
                    && child["state"] == "ORIGINAL_TIMER_CORE_VERIFIED_CLEAN"
                    && child["case_business_success_verified"] == true,
                "Clock coordinator did not carry the actual timer business/cleanup result",
            )?;
        }
    }
    Ok(())
}

/// Bind the compiled Clock source and the original adopted owner once for
/// both cases. This is source/lease custody, not Main or business acceptance.
pub(super) fn clock_pair_release(
    selection: &FilePin,
    context: SourceContext<'_>,
) -> Result<(NativeRelease, FilePin, FilePin), String> {
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let source = &sources[4];
    let lease = match context {
        SourceContext::Legacy => NativeRelease::bind_current(
            selection, SOURCE_CATALOG, &source.preparation, &source.entry,
        )?,
        SourceContext::Working(custody) => NativeRelease::bind_working(
            custody, selection, SOURCE_CATALOG, &source.preparation, &source.entry,
        )?,
    };
    Ok((lease, source.preparation.clone(), source.entry.clone()))
}

/// An unforgeable-in-the-consumer handoff from this actual execute/retire path.
/// It deliberately has no Clone, Deserialize or receipt-file constructor.
pub(super) struct ExecutedClockCase {
    observation: LeafObservation,
    result_custody: super::clock_timer::ClockResultCustody,
}
impl ExecutedClockCase {
    pub(super) fn into_parts(self) -> (LeafObservation, super::clock_timer::ClockResultCustody) {
        (self.observation, self.result_custody)
    }
}

pub(super) fn execute_clock_case(
    plan: &LeafPlan,
    selection: &FilePin,
    actual: &ApplicationInspection,
    main: &HeldMainCustody,
    release: &NativeRelease,
    inspector: &mut control::NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    end: Instant,
) -> Result<ExecutedClockCase, String> {
    require(matches!(plan.route, Route::ClockTimerRemaining | Route::ClockExpiry),
        "Clock fact production only accepts original timer15 and expiry06")?;
    let (observation, _, result_custody) =
        execute_observed(plan, selection, actual, main, release, inspector, baseline, end)?;
    Ok(ExecutedClockCase { observation, result_custody })
}


fn normal_route_release(
    plan: &LeafPlan, selection: &FilePin, context: SourceContext<'_>,
) -> Result<NativeRelease, String> {
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let source = &sources[plan.route.definition().source];
    if let SourceContext::Working(custody) = context {
        return NativeRelease::bind_working(custody, selection, SOURCE_CATALOG,
            &source.preparation, &source.entry);
    }
    if plan.route.current_gallery() {
        let request = value(&plan.request)?;
        NativeRelease::bind(&ref_field(&request, "native_release")?, selection, SOURCE_CATALOG,
            &source.preparation, &source.entry)
    } else {
        NativeRelease::bind_current(selection, SOURCE_CATALOG, &source.preparation, &source.entry)
    }
}

fn leaf_window(end: Instant, remaining: u64) -> Result<(), String> {
    require(end.checked_duration_since(Instant::now())
        .is_some_and(|left| left >= Duration::from_secs(remaining)),
        "normal leaf's fixed work/retirement window is exhausted")
}

/// Every ordinary admitted leaf gets the same real Main/copy-origin path.
/// Saved qualification JSON remains a protocol comparison, never authority.
pub(super) fn execute_admitted(
    inspector: &mut control::NativeApplicationInspector,
    materials: &VerifiedMaterialBatch,
    runtime: &RuntimePlan,
    requested: &ApplicationPlan,
    plan: &LeafPlan,
    selection: &FilePin,
    actual_token: control::ActualApplicationObservation,
) -> Result<(ApplicationInspection, LeafObservation), String> {
    execute_admitted_with_limit(inspector,materials,runtime,requested,plan,selection,actual_token,None,SourceContext::Legacy)
}

pub(super) fn execute_admitted_until(
    inspector: &mut control::NativeApplicationInspector,
    materials: &VerifiedMaterialBatch,
    runtime: &RuntimePlan,
    requested: &ApplicationPlan,
    plan: &LeafPlan,
    selection: &FilePin,
    actual_token: control::ActualApplicationObservation,
    end: Instant,
    source: &Arc<WorkingNativeSourceCustody>,
) -> Result<(ApplicationInspection, LeafObservation), String> {
    execute_admitted_with_limit(inspector,materials,runtime,requested,plan,selection,actual_token,
        Some(end),SourceContext::Working(source))
}

fn execute_admitted_with_limit(
    inspector: &mut control::NativeApplicationInspector,
    materials: &VerifiedMaterialBatch,
    runtime: &RuntimePlan,
    requested: &ApplicationPlan,
    plan: &LeafPlan,
    selection: &FilePin,
    actual_token: control::ActualApplicationObservation,
    inherited_end: Option<Instant>,
    context: SourceContext<'_>,
) -> Result<(ApplicationInspection, LeafObservation), String> {
    require(plan.route != Route::ClockTimerPair,
        "Clock pair requires its one shared two-case Main and owner factory")?;
    let actual = actual_token.facts().clone();
    let seconds = plan.route.definition().seconds;
    // One unchanged leaf limit, two fixed Main transport allowances, one
    // normal package inspection, and finite source/retirement bookends.
    // The original pre-leaf PM token comes from MaterialClient, with no RPC
    // added by baseline capture, each G, or finish_from_observed.
    let window = original_window_seconds(plan.route);
    let release = normal_route_release(plan, selection, context)?;
    release.cover_window(window)?;
    let normal_end = Instant::now() + Duration::from_secs(window);
    let end = inherited_end.map_or(normal_end, |limit| limit.min(normal_end));
    leaf_window(end, seconds + 2 * 70 + 250 + 30)?;
    materials.revalidate()?;
    materials.observe(requested, runtime.android_user, &runtime.expected_epoch, &actual, &actual)?;
    let mut main = HeldMainCustody::observe(inspector, actual_token, end)?;
    let mut baseline = main.baseline(inspector, end)?;
    release.attach_to_baseline(&mut baseline)?;
    let inventory_window = if actual.package == "com.ihg.apps.android" { 70 } else { 0 };
    if inventory_window != 0 {
        leaf_window(end, 70 + 250 + 70 + 70 + 30)?;
        let before = inspector.observe_user_zero_package_inventory_until(
            &main.observation, &main.application, end,
        ).map_err(|error| error.to_string())?;
        baseline.attach_user_zero_inventory(inspector, before)
            .map_err(|error| error.to_string())?;
    }
    release.guard()?;
    if inventory_window == 0 {
        leaf_window(end, seconds + 70 + 250 + 30)?;
    } else {
        // The two necessary inventory requests consume the existing lease.
        // The owned runner caps its original route work at the remaining
        // window after reserving PM/Main/inventory and retirement; no renewal.
        leaf_window(end, 250 + 70 + inventory_window + 30)?;
    }
    let (mut observation, _, result) = execute_observed(
        plan, selection, &actual, &main, &release, inspector, &mut baseline, end,
    )?;
    result.guard()?;
    release.guard()?;
    leaf_window(end, 250 + 70 + inventory_window + 30)?;
    let after_token = inspector.inspect_observed_until(&actual.package, actual.user, end)
        .map_err(|error| error.to_string())?;
    let after = after_token.facts().clone();
    main.require_application(&after)?;
    leaf_window(end, 70 + inventory_window + 30)?;
    let after_main = main.refresh(inspector, &after_token, end)?;
    if inventory_window != 0 {
        leaf_window(end, inventory_window + 30)?;
        let after_inventory = inspector.observe_user_zero_package_inventory_until(
            &after_main, &after_token, end,
        ).map_err(|error| error.to_string())?;
        baseline.record_inventory_bookend(inspector, after_inventory, end)
            .map_err(|error| error.to_string())?;
    }
    baseline.finish_from_observed(inspector, &after_main, &after_token, end)
        .map_err(|error| error.to_string())?;
    materials.revalidate()?;
    let mut final_identity = materials.observe(requested, runtime.android_user,
        &runtime.expected_epoch, &actual, &after)?;
    if let Some(engine) = &observation.engine_observations {
        final_identity.bind_native_execution(&after, &after_main, &[engine])?;
    }
    release.guard()?;
    result.guard()?;
    baseline.verify_local(inspector, end).map_err(|error| error.to_string())?;
    leaf_window(end, 0)?;
    // The actual data handles span the execution and final bookends. Retiring
    // them here does not claim continuous data custody after this window.
    drop(baseline);
    main.retain_completed(after_main, after_token)?;
    observation.custody = Some(HeldLeafCustody {
        main, release, result, final_identity: Some(final_identity), end,
    });
    observation.retained_bookends()?;
    Ok((after, observation))
}

fn execute_observed(
    plan: &LeafPlan,
    selection: &FilePin,
    actual: &ApplicationInspection,
    main: &HeldMainCustody,
    release: &NativeRelease,
    inspector: &mut control::NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    end: Instant,
) -> Result<(LeafObservation, Value, super::clock_timer::ClockResultCustody), String> {
    require(
        plan.route.package() == actual.package,
        "leaf route belongs to a different application",
    )?;
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let d = plan.route.definition();
    let source = &sources[d.source];
    pinned(&source.preparation)?;
    pinned(&source.entry)?;
    let request = value(&plan.request)?;
    let (case_ref, case) = case_document(plan, &request)?;
    validate_case(plan, &request, &case, source, &sources)?;
    release.guard()?;
    require(baseline.deadline() == end && baseline.application() == actual,
        "leaf execution context differs from the original identity or deadline")?;
    baseline.verify_local(inspector, end).map_err(|error| error.to_string())?;
    let (baseline_ref, qualification) = main_binding(&case, actual, main, baseline)?;
    let expected_result = output_path(plan, &request, &case)?;
    let cmd = command(plan, source)?;
    // The trusted selected entry still validates the complete transitive source
    // graph and every original business/support/provider gate before its actions.
    claim(plan, actual, source)?;
    let kind = if plan.route.current_gallery() {
        control::NativeLeafCommandKind::GalleryImage
    } else if plan.route == Route::CalendarReminder {
        control::NativeLeafCommandKind::CalendarReminder
    } else if plan.route == Route::SettingsSupportedPages {
        control::NativeLeafCommandKind::SettingsPages
    } else {
        control::NativeLeafCommandKind::Standard { budget:Duration::from_secs(d.seconds) }
    };
    let executed = control::run_prepared_native_leaf_observed_until(
        cmd, &actual.epoch, kind, inspector, baseline, end,
    )?;
    let (output, engine_observations) = executed.into_parts();
    require(
        output.status.success(),
        "actual leaf process failed; preserve its claim and original logs without replay",
    )?;
    let printed: Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("leaf output is not one complete JSON result: {e}"))?;
    // Capture every result at its first actual executor body read. The same
    // descriptor and full F9/SHA travel through Main/package revalidation.
    let (result_custody, result) = if plan.route == Route::CameraPhoto {
        require(printed["result"].as_str() == expected_result.to_str(),
            "camera wrapper output points outside its exact fresh result path")?;
        super::clock_timer::ClockResultCustody::capture_path(&expected_result)?
    } else {
        let reference = ref_field(&printed, "result")?;
        require(reference.path == expected_result,
            "leaf returned a receipt outside its exact new case result")?;
        super::clock_timer::ClockResultCustody::capture(&reference)?
    };
    let result_ref = result_custody.reference().clone();
    terminal_result(
        plan.route,
        &printed,
        &result,
        case_ref.as_ref(),
        &baseline_ref,
        &qualification,
        source,
    )?;
    // These three source-owned workflows each establish exactly two launch
    // claims. A saved result or an old no-E entry cannot supply their history.
    if matches!(plan.route, Route::ClockTimerRemaining | Route::ClockExpiry
        | Route::SettingsSupportedPages)
    {
        require(engine_observations.as_ref().is_some_and(|history| history.observation_count() == 2),
            "both actual normal launch claims require their running-engine checkpoints")?;
    }
    if let Some(engine) = &engine_observations { main.require_engine(engine)?; }
    // Re-read the externally selected inputs after completed child retirement.
    for pin in [
        selection,
        &source.preparation,
        &source.entry,
        &plan.request,
        &baseline_ref,
        &qualification,
    ] {
        pinned(pin)?;
    }
    if let Some(pin) = case_ref {
        pinned(&pin)?;
    }
    if plan.route.current_gallery() {
        require(ref_field(&result, "native_release")? == ref_field(&request, "native_release")?,
            "Gallery result is not bound to this adopted native release")?;
    }
    release.guard()?;
    main.require_application(actual)?;
    let observation = LeafObservation {
        route: plan.route,
        request: plan.request.clone(),
        preparation: source.preparation.clone(),
        entry_source: source.entry.clone(),
        result: result_ref,
        state: result["state"]
            .as_str()
            .unwrap_or("original_leaf_ok")
            .into(),
        custody: None,
        engine_observations,
        original_entry_result_verified: true,
        original_business_success_reported: plan.route != Route::IhgLondon,
        business_outcome_unknown: plan.route == Route::IhgLondon,
        main_epoch_unchanged: true,
        owned_host_tree_retired: true,
        automatic_retry: false,
        whole_app_business_accepted: false,
        production_ready: false,
        remaining_scope: if plan.route == Route::IhgLondon {
            "Only public London destination input and readback completed. The original producer explicitly retains business_outcome_unknown=true and business_success_verified=false; hotel availability/detail, visual foreground and all release gates remain pending."
        } else {
            "Only this original bounded case completed. Visual review, untested feature paths, all common release gates and whole-app acceptance remain separately required."
        },
    };
    result_custody.guard()?;
    baseline.verify_local(inspector, end).map_err(|error| error.to_string())?;
    Ok((observation, result, result_custody))
}

#[cfg(test)]
mod tests {
    use super::*;
    const CURRENT_SELECTION: &str = include_str!("../tests/fixtures/selection-14-20261126.json");
    const RETIRED_R1_SELECTION: &str = include_str!("../tests/fixtures/selection-14-20261120.json");
    const OLD_SELECTION: &str = include_str!("../tests/fixtures/selection-13-20261120.json");

    fn current_selection() -> Value {
        serde_json::from_str(CURRENT_SELECTION).unwrap()
    }

    fn pin(name: &str) -> FilePin {
        FilePin {
            path: PathBuf::from(format!("/fixture/{name}")),
            bytes: 1,
            sha256: "1".repeat(64),
        }
    }

    #[test]
    fn main_copy_projection_requires_the_actual_ordered_working_pair_but_grants_no_authority() {
        use droidloom_supervisor::main_custody::MainOriginalCopyOrigin;
        let actual = [[1, 2, 0o100600, 0, 0, 1, 4096], [1, 3, 0o100600, 0, 0, 1, 2048]];
        let comparison = MainOriginalCopyOrigin {
            schema: "synthetic-comparison-only".into(),
            working_copy_sha256: "a".repeat(64), cold_clone_sha256: "b".repeat(64),
            original: [[0; 7]; 2], working: actual,
        };
        // This helper only compares values; it cannot create HeldMainCustody.
        assert!(require_working_origin(Some(&comparison), actual).is_ok());
        assert!(require_working_origin(None, actual).is_err());
        assert!(require_working_origin(Some(&comparison), [actual[1], actual[0]]).is_err());
        for role in 0..2 {
            for field in 0..7 {
                let mut changed = actual;
                changed[role][field] ^= 1;
                assert!(require_working_origin(Some(&comparison), changed).is_err());
            }
        }
    }

    // Structural fixtures only: none can construct opaque Main, retained result
    // custody, a normal launch, or an application business acceptance.
    fn settings_v3_shape(present: bool, text: &str) -> (Value, Value, FilePin) {
        fn raw_pin(name: &str, raw: &[u8]) -> Value {
            json!({"path":format!("/fixture/{name}"),"bytes":raw.len(),
                "sha256":hex::encode(Sha256::digest(raw))})
        }
        fn command(operation: &str, argv: Vec<&str>, mutation: bool, raw: &[u8]) -> Value {
            json!({"operation":operation,"argv":argv,"mutation":mutation,
                "result":pin(&format!("{operation}.result")),
                "stdout":raw_pin(&format!("{operation}.stdout"),raw),
                "stderr":raw_pin(&format!("{operation}.stderr"),b"")})
        }
        fn observation(index: usize, page: &str, activity: &str) -> Value {
            let summary = json!({"page":page,"package":"com.android.settings","activity":activity,
                "android_init_host_pid":17,"window_token":"12ab","expected_title_observed":true,
                "source":"actual-native-tree-and-scoped-PNG","whole_app_business_accepted":false,
                "visible_control_count":3,"visible_label_count":4,"scoped_pixel_sha256":"c".repeat(64)});
            json!({"summary":summary,"recorder_result":pin(&format!("ui-{index}.recorder")),
                "observation":pin(&format!("ui-{index}.json")),"PNG":pin(&format!("ui-{index}.png"))})
        }
        let original = if present {
            json!({"present":true,"text":text,"effective":text.parse::<f64>().unwrap()})
        } else { json!({"present":false,"text":null,"effective":1.0}) };
        let selected = if (original["effective"].as_f64().unwrap() - 1.15).abs() <= 0.00001 {
            "1.0"
        } else { "1.15" };
        let changed = json!({"present":true,"text":selected,"effective":selected.parse::<f64>().unwrap()});
        let claims = json!([pin("first-claim"),pin("second-claim")]);
        let scopes = json!([pin("first-scope"),pin("second-scope")]);
        let mut commands = Vec::new();
        let mut snapshots = Vec::new();
        for (phase, provider, scope) in [
            ("original", &original, &scopes[0]),
            ("before-apply", &original, &scopes[0]),
            ("applied-00", &changed, &scopes[0]),
            ("reopened-00", &changed, &scopes[1]),
            ("before-restore", &changed, &scopes[1]),
            ("restored-00", &original, &scopes[1]),
        ] {
            if phase == "applied-00" {
                commands.push(command("apply",
                    vec!["/system/bin/settings","--user","0","put","system","font_scale",selected],
                    true,b""));
            }
            if phase == "restored-00" {
                let mut argv = vec!["/system/bin/settings","--user","0"];
                if present { argv.extend(["put","system","font_scale",text]); }
                else { argv.extend(["delete","system","font_scale"]); }
                commands.push(command("restore",argv,true,if present { b"" } else { b"Deleted 1 rows\n" }));
            }
            let raw = format!("{}\n",if provider["present"]==true {
                provider["text"].as_str().unwrap()
            } else { "null" });
            // Synthetic config bytes model consistency only; the real producer
            // validates actual am get-config protobuf inside its held source path.
            let config_raw = format!("synthetic-{phase}").into_bytes();
            let provider_command = command(&format!("{phase}-value"),
                vec!["/system/bin/settings","--user","0","get","system","font_scale"],false,raw.as_bytes());
            let configuration_command = command(&format!("{phase}-config"),
                vec!["/system/bin/am","get-config","--proto"],false,&config_raw);
            let configuration = json!({"font_scale":provider["effective"],
                "other_configuration_fields":["1001"],"resource_fields":["2001"],
                "raw_sha256":hex::encode(Sha256::digest(&config_raw))});
            snapshots.push(json!({"phase":phase,"provider":provider,"configuration":configuration,
                "scope":scope,"provider_command":provider_command,"configuration_command":configuration_command}));
            commands.extend([provider_command,configuration_command]);
        }
        let font = json!({"schema":"pocket4-settings-font-scale-facts-v1","namespace":"system",
            "key":"font_scale","user":0,"original":original,"selected":selected,"state":"restored_verified",
            "apply_observed":true,"reopen_observed":true,"restore_observed":true,
            "apply_claim":claims[0],"reopen_claim":claims[1],"provider_writes":2,
            "readonly_commands":12,"commands":commands,"snapshots":snapshots,"pending_command":null,
            "automatic_write_retry":false,"compare_and_swap_claimed":false,
            "permission_or_account_write_authorized":false,"whole_app_business_accepted":false});
        let profile = [
            ("system","com.android.settings.Settings$SystemDashboardActivity"),
            ("network","com.android.settings.Settings$NetworkDashboardActivity"),
            ("display","com.android.settings.Settings$DisplaySettingsActivity"),
            ("storage","com.android.settings.Settings$StorageDashboardActivity"),
            ("applications","com.android.settings.Settings$ManageApplicationsActivity"),
        ];
        let home = "com.android.settings.homepage.SettingsHomepageActivity";
        let pages: Vec<Value> = profile.iter().enumerate()
            .map(|(n,(name,activity))|observation(n+1,name,activity)).collect();
        let plan = pin("settings-plan");
        let mut result = json!({"schema":"pocket4-settings-pages-case-result-v3",
            "state":"SETTINGS_FONT_SCALE_RESTORED_WITH_PAGES","whole_app_business_accepted":false,
            "automatic_retry":false,"case_business_success_verified":true,
            "scope":["settings.pages","settings.roundtrip"],"accepted_gates":["settings.pages","settings.roundtrip"],
            "base_plan":plan,"remaining_gates":["settings.permissions","identity","lifecycle",
                "stability","data_permissions","release_scope","ui_observation"]});
        for part in [
            json!({"all_five_pages_observed":true,"pages":pages,
                "initial_home":observation(0,"home",home),
                "applied_page":observation(6,profile[4].0,profile[4].1),
                "reopened_home":observation(7,"home",home),"restored_home":observation(8,"home",home),
                "identity_permissions_directories_preserved":true,
                "permission_interfaces":{"settings_permissions_gate_accepted":false,
                    "readonly_input_error_verified":false,"account_state_observed":false}}),
            json!({"complete_task_baseline_restored":true,"final_source_identity_chain_unchanged":true,
                "evidence_witness_closed":true,"native_launch_count":2,"page_route_count":5,
                "observation_count":9,"native_claims":claims,"normally_closed_claims":claims,
                "recorder_scopes":scopes,"host_flow_contexts_closed":scopes,
                "launches":[0,1],"normal_closes":[0,1],"pending_route":null,"pending_UI":null}),
            json!({"setting_writes":2,"provider_writes":2,"other_provider_writes":0,
                "permission_writes":0,"account_writes":0,"package_writes":0,"setting_roundtrip":font,
                "Android_runtime_qualification_inferred_from_source":false,"Binder_UID_cleanup_verified":false,
                "Main_before":{"comparison_only":true},"Main_after":{"comparison_only":true},
                "cancellation_commit":{"observed_before_commit":[],"pending_at_commit":[],
                    "decision_frozen_after_host_context_close":true}}),
        ] { result.as_object_mut().unwrap().extend(part.as_object().unwrap().clone()); }
        let printed = json!({"result":pin("settings-result"),"state":result["state"],
            "case_business_success_verified":true,"scope":result["scope"],"whole_app_business_accepted":false});
        (printed,result,plan)
    }

    fn check_settings_v3(printed: &Value, result: &Value, plan: &FilePin) -> Result<(), String> {
        let source = SelectedSource { index:13, preparation:pin("settings-prep"), entry:pin("settings-entry") };
        terminal_result(Route::SettingsSupportedPages,printed,result,Some(plan),
            &pin("baseline"),&pin("qualification"),&source)
    }

    #[test]
    fn settings_v3_consumes_actual_source_shape_with_original_string_or_absence() {
        for (present,text) in [(true,"1.0"),(true,"1.15"),(false,"")] {
            let (printed,result,plan)=settings_v3_shape(present,text);
            check_settings_v3(&printed,&result,&plan).unwrap();
            // Passing these comparisons is not a normal-execution token.
            assert_eq!(Route::SettingsSupportedPages.definition().seconds,900);
            assert_eq!(Route::SettingsSupportedPages.definition().source,13);
        }
    }

    #[test]
    fn settings_v3_rejects_old_counts_unknown_cleanup_and_expanded_scope() {
        let (printed,result,plan)=settings_v3_shape(true,"1.0");
        for (key,value) in [
            ("schema",json!("pocket4-settings-pages-case-result-v2")),
            ("state",json!("SETTINGS_PAGES_ROUNDTRIP_VERIFIED_RESTORED")),
            ("accepted_gates",json!(["settings.pages","settings.roundtrip","settings.permissions"])),
            ("page_route_count",json!(11)),("observation_count",json!(13)),
            ("provider_writes",json!(0)),("setting_writes",json!(1)),
            ("permission_writes",json!(1)),("account_writes",json!(1)),
            ("remaining_gates",json!([])),("whole_app_business_accepted",json!(true)),
            ("unknown_retained_without_further_mutation",json!(true)),
            ("normal_closes",json!([0])),("base_plan",json!(pin("other-plan"))),
            ("Main_after",json!({"changed":true})),
            ("permission_interfaces",json!({"settings_permissions_gate_accepted":false,
                "readonly_input_error_verified":true,"account_state_observed":false})),
        ] {
            let mut bad=result.clone();bad[key]=value;
            assert!(check_settings_v3(&printed,&bad,&plan).is_err(),"{key}");
        }
        for key in ["pending_route","pending_UI"] {
            let mut bad=result.clone();bad.as_object_mut().unwrap().remove(key);
            assert!(check_settings_v3(&printed,&bad,&plan).is_err(),"missing {key}");
        }
        let mut bad=result.clone();bad["cancellation_commit"]["pending_at_commit"]=json!([15]);
        assert!(check_settings_v3(&printed,&bad,&plan).is_err());
        let mut old_stdout=printed.clone();old_stdout["accepted_gates"]=result["scope"].clone();
        assert!(check_settings_v3(&old_stdout,&result,&plan).is_err());
        let mut bad=result;bad["pages"][1]=bad["pages"][0].clone();
        assert!(check_settings_v3(&printed,&bad,&plan).is_err());
    }

    #[test]
    fn settings_v3_rejects_missing_reopen_wrong_restore_and_unowned_command_chain() {
        let (printed,result,plan)=settings_v3_shape(false,"");
        for change in 0..14 {
            let mut bad=result.clone();
            let fact=&mut bad["setting_roundtrip"];
            match change {
                0=>fact["selected"]=json!("2.0"),
                1=>fact["reopen_observed"]=json!(false),
                2=>fact["restore_observed"]=json!(false),
                3=>fact["reopen_claim"]=fact["apply_claim"].clone(),
                4=>fact["pending_command"]=json!({"sent":true}),
                5=>fact["commands"][4]["argv"][5]=json!("screen_brightness"),
                6=>fact["commands"][11]["argv"]=json!(["/system/bin/settings","--user","0","put","system","font_scale","1.0"]),
                7=>fact["commands"][4]["mutation"]=json!(false),
                8=>fact["snapshots"][3]["phase"]=json!("applied-01"),
                9=>fact["snapshots"][5]["configuration"]["font_scale"]=json!(1.15),
                10=>fact["snapshots"][4]["configuration"]["other_configuration_fields"]=json!(["1002"]),
                11=>fact["snapshots"][5]["scope"]=fact["snapshots"][0]["scope"].clone(),
                12=>fact["readonly_commands"]=json!(13),
                _=>fact["commands"][0]["stdout"]["sha256"]=json!("0".repeat(64)),
            }
            assert!(check_settings_v3(&printed,&bad,&plan).is_err(),"change {change}");
        }
    }

    #[test]
    fn r2_selector_rejects_retired_r1_pins_and_mixed_source_documents() {
        let old:Value=serde_json::from_str(RETIRED_R1_SELECTION).unwrap();
        let old_pin=FilePin{
            path:"/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/selection/selection-14.json".into(),
            bytes:RETIRED_R1_SELECTION.len() as u64,
            sha256:hex::encode(Sha256::digest(RETIRED_R1_SELECTION)),
        };
        assert!(validate_selection_pin(&old_pin).is_err());
        assert!(validate_selection_document(&old,&fixed_sources().unwrap()).is_err());
        let current=current_selection();
        validate_selection_document(&current,&fixed_sources().unwrap()).unwrap();
        assert!(fixed_sources().unwrap().iter().all(|source|
            source.preparation.path.starts_with("/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2")
            && source.entry.path.starts_with("/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2")));
    }

    #[test]
    fn finite_routes_cover_seven_packages_without_install_or_raw_camera_bypass() {
        let routes = [
            Route::ContactsSearch,
            Route::CalendarCore,
            Route::CalendarReminder,
            Route::CameraPhoto,
            Route::ClockTimer,
            Route::ClockTimerRemaining,
            Route::ClockExpiry,
            Route::ClockAlarm,
            Route::IhgLondon,
            Route::DocumentsSaf,
            Route::DocumentsSearchSort,
            Route::GalleryRotation,
            Route::GalleryVideo,
            Route::GallerySeek,
            Route::GalleryAlbum,
        ];
        assert_eq!(
            routes
                .iter()
                .map(|r| r.package())
                .collect::<BTreeSet<_>>()
                .len(),
            7
        );
        let sources = fixed_sources().unwrap();
        for route in routes {
            let d = route.definition();
            assert!(![2, 8].contains(&d.source));
            let p = LeafPlan {
                route,
                request: pin("request"),
                output: (route == Route::CameraPhoto).then(|| PathBuf::from("/fresh-camera")),
            };
            let cmd = command(&p, &sources[d.source]).unwrap();
            assert_eq!(cmd.get_program(), "/usr/bin/python3");
            let args: Vec<_> = cmd.get_args().map(|a| a.to_str().unwrap()).collect();
            assert_eq!(&args[..2], ["-I", "-B"]);
            assert!(args.contains(&"execute"));
            assert!(!args.contains(&"install") && !args.contains(&"verify"));
            assert!(args.contains(&p.request.sha256.as_str()));
            assert!(if route.current_gallery() {
                d.seconds == 1530
            } else {
                (420..=1200).contains(&d.seconds)
            });
        }
    }
    #[test]
    fn arbitrary_or_old_preparation_selection_is_rejected_before_a_child() {
        assert!(validate_selection(&pin("arbitrary-selection")).is_err());
    }

    #[test]
    fn published_current_selector_binds_the_real_ihg_and_clock_entry() {
        assert_eq!(CURRENT_SELECTION.len() as u64, SELECTION_BYTES);
        assert_eq!(
            hex::encode(Sha256::digest(CURRENT_SELECTION)),
            SELECTION_SHA
        );
        let selection = current_selection();
        let sources = fixed_sources().unwrap();
        validate_selection_document(&selection, &sources).unwrap();
        validate_selection_pin(&FilePin {
            path: SELECTION_PATH.into(),
            bytes: SELECTION_BYTES,
            sha256: SELECTION_SHA.into(),
        })
        .unwrap();
        let source = &sources[5];
        assert_eq!(
            source.entry.path,
            Path::new(
                "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/ihg/app_entry.py"
            )
        );
        assert_eq!(source.entry.bytes, 14093);
        assert_eq!(
            source.entry.sha256,
            "2e3259dbc6f73e9baf7c86075ffb398a5f33e279756046c789941e43303d9c82"
        );
        for route in [Route::ClockTimer, Route::IhgLondon] {
            assert_eq!(route.definition().source, 5);
            let plan = LeafPlan {
                route,
                request: pin("request"),
                output: None,
            };
            let command = command(&plan, source).unwrap();
            let args: Vec<_> = command.get_args().map(|a| a.to_str().unwrap()).collect();
            assert!(args.contains(&source.entry.path.to_str().unwrap()));
            assert!(args.contains(&source.preparation.path.to_str().unwrap()));
            assert!(args.contains(&source.preparation.sha256.as_str()));
        }
    }

    #[test]
    fn november_fourteen_and_mixed_selector_pins_are_rejected_before_reading() {
        let old = ref_field(
            &serde_json::from_str::<Value>(OLD_SELECTION).unwrap(),
            "previous_selection",
        )
        .unwrap();
        assert!(validate_selection_pin(&old).is_err());
        assert!(validate_selection(&old).is_err());
        let current = FilePin {
            path: SELECTION_PATH.into(),
            bytes: SELECTION_BYTES,
            sha256: SELECTION_SHA.into(),
        };
        for mixed in [
            FilePin {
                path: old.path,
                ..current.clone()
            },
            FilePin {
                bytes: old.bytes,
                ..current.clone()
            },
            FilePin {
                sha256: old.sha256,
                ..current
            },
        ] {
            assert!(validate_selection_pin(&mixed).is_err());
        }
    }

    #[test]
    fn current_selector_cannot_dispatch_a_stale_or_reordered_compiled_catalog() {
        let selection = current_selection();
        let mut sources = fixed_sources().unwrap();
        let old: Value = serde_json::from_str(OLD_SELECTION).unwrap();
        sources[5].preparation =
            ref_field(&old["previous_identity_source_update"], "old_preparation").unwrap();
        assert!(validate_selection_document(&selection, &sources).is_err());
        sources = fixed_sources().unwrap();
        sources.swap(4, 5);
        assert!(validate_selection_document(&selection, &sources).is_err());
        sources = fixed_sources().unwrap();
        sources[5].index = 4;
        assert!(validate_selection_document(&selection, &sources).is_err());
        sources.pop();
        assert!(validate_selection_document(&selection, &sources).is_err());
    }

    #[test]
    fn current_selector_requires_every_preparation_once_in_selected_order() {
        let sources = fixed_sources().unwrap();
        let selected = current_selection();
        let original = selected["selected_preparations"].as_array().unwrap();
        for change in 0..4 {
            let mut selection = selected.clone();
            let rows = selection["selected_preparations"].as_array_mut().unwrap();
            match change {
                0 => {
                    rows.pop();
                }
                1 => rows.push(original[0].clone()),
                2 => rows[5] = original[4].clone(),
                _ => rows.swap(4, 5),
            }
            assert!(validate_selection_document(&selection, &sources).is_err());
        }
    }

    #[test]
    fn selection_source_refresh_cannot_promote_runtime_or_expand_its_update() {
        let selected = current_selection();
        let sources = fixed_sources().unwrap();
        for (key, value) in [
            ("selection_only", json!(false)),
            ("source_controlled_cohort", json!("cp3a-20261120-apps-r1")),
            ("current_fixed_r1_bytes_recovered", json!(true)),
            ("Android_actions", json!(1)),
            ("Main_actions", json!(1)),
            ("CURRENT_writes", json!(1)),
            ("new_runtime_acceptance_count", json!(1)),
            (
                "full_Main_execute_or_full_runtime_seed_executed",
                json!(true),
            ),
            ("historical_runtime_credit_transferred", json!(true)),
            ("runtime_qualified", json!(true)),
            ("production_ready", json!(true)),
            ("unknown_field", json!(false)),
        ] {
            let mut changed = selected.clone();
            changed[key] = value;
            assert!(
                validate_selection_document(&changed, &sources).is_err(),
                "{key}"
            );
        }
        for (key, value) in [
            ("changed_indices", json!([0, 8, 9, 10, 11, 12])),
            ("unchanged_indices", json!([1, 2, 3, 4, 5, 6, 7])),
            ("added_indices", json!([])),
            ("state", json!("ADOPTED")),
            ("Android_actions", json!(false)),
            ("CURRENT_writes", json!(1)),
            ("current_Main_required", json!(false)),
            ("native_release_adopted", json!(true)),
            ("native_release_adoption_required", json!(false)),
            ("runtime_enabled", json!(true)),
            ("runtime_qualified", json!(true)),
            ("production_ready", json!(true)),
            ("unknown_field", json!(false)),
            ("catalog", json!(pin("arbitrary-catalog"))),
        ] {
            let mut changed = selected.clone();
            changed["source_selection_update"][key] = value;
            assert!(
                validate_selection_document(&changed, &sources).is_err(),
                "{key}"
            );
        }
    }

    #[test]
    fn wrong_case_kind_and_unwrapped_camera_never_dispatch() {
        let sources = fixed_sources().unwrap();
        let mut p = LeafPlan {
            route: Route::ContactsSearch,
            request: pin("request"),
            output: None,
        };
        let req = json!({"base_plan": pin("plan")});
        let mut case = json!({"schema":"pocket4-final-system-case-plan-v1", "kind":"calendar_core",
            "source_preparation":sources[0].preparation,"automatic_retry":false,"whole_app_business_accepted":false});
        assert!(validate_case(&p, &req, &case, &sources[0], &sources).is_err());
        case["kind"] = json!("contacts_search");
        assert!(validate_case(&p, &req, &case, &sources[0], &sources).is_ok());
        p.output = Some(PathBuf::from("/arbitrary"));
        assert!(validate_case(&p, &req, &case, &sources[0], &sources).is_err());
        assert!(serde_json::from_value::<Route>(json!("camera_raw")).is_err());
        assert!(serde_json::from_value::<Route>(json!("gallery_install")).is_err());
    }

    #[test]
    fn current_gallery_request_requires_detached_release_and_rejects_legacy_installation() {
        let sources = fixed_sources().unwrap();
        let plan = LeafPlan {
            route: Route::GalleryRotation,
            request: pin("request"),
            output: None,
        };
        let request = json!({"schema":"pocket4-gallery-image-request-v1","baseline":pin("baseline"),
            "qualification":pin("qualification"),"output":"/fresh-gallery","native_release":pin("release")});
        validate_case(&plan, &request, &request, &sources[9], &sources).unwrap();
        let mut legacy = request.clone();
        legacy["installation"] = json!(pin("legacy-install"));
        assert!(validate_case(&plan, &legacy, &legacy, &sources[9], &sources).is_err());
        legacy = request.clone();
        legacy.as_object_mut().unwrap().remove("native_release");
        assert!(validate_case(&plan, &legacy, &legacy, &sources[9], &sources).is_err());
        legacy = request;
        legacy["schema"] = json!("pocket4-gallery-current-rotation-request-v1");
        assert!(validate_case(&plan, &legacy, &legacy, &sources[9], &sources).is_err());
    }
    #[test]
    fn zero_exit_equivalent_empty_or_stale_output_is_not_success() {
        let sources = fixed_sources().unwrap();
        let p = pin("plan");
        let b = pin("baseline");
        let q = pin("qualification");
        assert!(
            terminal_result(
                Route::ContactsSearch,
                &json!({}),
                &json!({}),
                Some(&p),
                &b,
                &q,
                &sources[0]
            )
            .is_err()
        );
        let printed = json!({"whole_app_business_accepted":false,"case_business_success_verified":true,"state":"ORIGINAL_CASE_VERIFIED_CLEAN"});
        let mut result = json!({"schema":"pocket4-final-original-system-case-result-v1","whole_app_business_accepted":false,
            "automatic_retry":false,"case_business_success_verified":true,"state":"ORIGINAL_CASE_VERIFIED_CLEAN","plan":p,"secondary_errors":[]});
        assert!(
            terminal_result(
                Route::ContactsSearch,
                &printed,
                &result,
                Some(&p),
                &b,
                &q,
                &sources[0]
            )
            .is_ok()
        );
        result["plan"] = json!(pin("other-plan"));
        assert!(
            terminal_result(
                Route::ContactsSearch,
                &printed,
                &result,
                Some(&p),
                &b,
                &q,
                &sources[0]
            )
            .is_err()
        );
        result["plan"] = json!(p);
        result["secondary_errors"] = json!(["cleanup unresolved"]);
        assert!(
            terminal_result(
                Route::ContactsSearch,
                &printed,
                &result,
                Some(&p),
                &b,
                &q,
                &sources[0]
            )
            .is_err()
        );
    }
    #[test]
    fn gallery_cancelled_or_wrong_epoch_receipt_is_rejected() {
        let sources = fixed_sources().unwrap();
        let b = pin("baseline");
        let q = pin("qualification");
        let state = Route::GalleryRotation.definition().state.unwrap();
        let printed =
            json!({"whole_app_business_accepted":false,"state":state,"outcome_unknown":false});
        let mut result = json!({"schema":"pocket4-gallery-image-scope-v1","state":state,
            "whole_app_business_accepted":false,"automatic_retry":false,"business_scope_completed":true,
            "outcome_unknown":false,"entry_cancellation_signals":[],"baseline":b,"qualification":q,
            "source_preparation":sources[9].preparation});
        assert!(
            terminal_result(
                Route::GalleryRotation,
                &printed,
                &result,
                None,
                &b,
                &q,
                &sources[9]
            )
            .is_ok()
        );
        result["entry_cancellation_signals"] = json!([15]);
        assert!(
            terminal_result(
                Route::GalleryRotation,
                &printed,
                &result,
                None,
                &b,
                &q,
                &sources[9]
            )
            .is_err()
        );
        result["entry_cancellation_signals"] = json!([]);
        result["qualification"] = json!(pin("old-main"));
        assert!(
            terminal_result(
                Route::GalleryRotation,
                &printed,
                &result,
                None,
                &b,
                &q,
                &sources[9]
            )
            .is_err()
        );
    }
    fn saved(root: &Path, name: &str, value: &Value) -> FilePin {
        let raw = serde_json::to_vec(value).unwrap();
        let path = root.join(name);
        fs::write(&path, &raw).unwrap();
        FilePin {
            path,
            bytes: raw.len() as u64,
            sha256: hex::encode(Sha256::digest(&raw)),
        }
    }

    fn native_document_model() -> (ApplicationInspection, Value, Value, FilePin, Value, Value) {
        use droidloom_supervisor::control::application_probe::{InstalledApk, RuntimeEpoch};
        // Parser/comparison fixtures only: no opaque Main/PM/data token is minted.
        let actual = ApplicationInspection {
            package:"com.android.contacts".into(), user:0, uid:10055, version_code:2,
            epoch:RuntimeEpoch { boot_id:"97d9600f-e081-465c-9e6e-62651e09806b".into(),
                cell_host_pid:10, framework_host_pid:20, framework_start_ticks:30 },
            apks:vec![InstalledApk { name:"base.apk".into(), path:"/system/app/Contacts.apk".into(),
                bytes:12, sha256:"a".repeat(64) }],
        };
        let process = |pid:u32, start:u64| json!({"host_pid":pid,"start_ticks":start});
        let init = process(10,11); let zygote = process(15,16); let framework = process(20,30);
        let main = json!({
            "epoch":actual.epoch, "init":init, "zygote":zygote, "framework":framework,
            "persistent_data":{"original_copy_origin":{"comparison_fixture_only":true}},
            "normal_host_release":{"comparison_fixture_only":true},
        });
        let directory = |path:&str, inode:u64| json!({
            "path":path,"device":9,"inode":inode,"mount_id":71,"mode":16832,
            "host_uid":110055,"host_gid":110055,
        });
        let data = json!({"data_root":{"device":9,"inode":2},
            "directories":[directory("/data/user/0",90),directory("/data/user_de/0",91),
                directory("/data/user/0/com.android.contacts",100),
                directory("/data/user_de/0/com.android.contacts",101)]});
        let mut core = json!({"schema":"droidloom.native-leaf-baseline.v1",
            "application":actual,"main":main,"data":data,"peer":{"comparison_fixture_only":true}});
        core["comparison_only"] = json!(true);
        core["account_contents_read"] = json!(false);
        core["business_acceptance_evaluated"] = json!(false);
        let binding = json!({"boot_id":actual.epoch.boot_id,
            "processes":{"init":init,"zygote64":zygote,"system_server":framework}});
        let epoch = json!({"schema":"pocket4-framework-epoch-v1",
            "sha256":canonical_sha(&binding).unwrap(),"binding":binding});
        let mut directories = serde_json::Map::new();
        for (name,inode) in [("user/0/com.android.contacts",100),("user_de/0/com.android.contacts",101)] {
            directories.insert(name.into(), json!({
                "device":9,"inode":inode,"mount_id":71,"mode":16832,"uid":110055,"gid":110055}));
        }
        let continuity = json!({"schema":"droidloom.native-leaf-target-working-data.v1",
            "scope":"actual_inspected_user_0_package_only",
            "package_uids":{"com.android.contacts":10055},"directories":directories,
            "working_data_root":core["data"]["data_root"],
            "original_copy_origin":core["main"]["persistent_data"]["original_copy_origin"],
            "original_directory_identity_compared":false,"account_contents_read":false});
        let observation = json!({"fixture":1});
        let classpath = json!({"fixture":2});
        let artifacts = json!({"fixture":3});
        let mut runtime = json!({"schema":"droidloom.native-leaf-runtime-comparison.v1",
            "native_owner":core,"normal_host_release":core["main"]["normal_host_release"],
            "main_epoch":epoch,"observation":observation,"classpath":classpath,"artifacts":artifacts});
        runtime["data_continuity"] = continuity.clone();
        runtime["saved_document_can_create_authority"] = json!(false);
        runtime["business_acceptance_evaluated"] = json!(false);
        let mut baseline = json!({"schema":NATIVE_BASELINE_SCHEMA,"native_owner":core,
            "runtime_observation":runtime,"framework_epoch":epoch,"observation":observation,
            "classpath":classpath,"artifacts":artifacts,"data_continuity":continuity});
        baseline["sampling"] = json!({"double_observation_pairs":3,"pairs_equal":true,
            "started_monotonic_ns":10,"finished_monotonic_ns":10_000_000_010_u64});
        baseline["observation_fds"] = json!({"acquired":12,"closed":12,"close_attempts":12,
            "remaining":0,"errors":[]});
        baseline["captured_unix_ns"] = json!(42);
        baseline["user_zero_package_inventory"] = Value::Null;
        baseline["comparison_only"] = json!(true);
        for key in ["account_contents_read","whole_app_business_accepted","production_ready"] {
            baseline[key] = json!(false);
        }
        let baseline_ref = pin("normal-baseline");
        let mut qualification = json!({"schema":NATIVE_QUALIFICATION_SCHEMA,"baseline":baseline_ref,
            "normal_source_recipe":{"bytes":NORMAL_SOURCE_RECIPE_BYTES,"sha256":NORMAL_SOURCE_RECIPE_SHA},
            "core_sha256":canonical_sha(&core).unwrap(),"main_epoch_sha256":epoch["sha256"],
            "observation_fds":baseline["observation_fds"],
            "user_zero_package_inventory_sha256":canonical_sha(&Value::Null).unwrap()});
        for key in ["actual_main_and_target_metadata_observed","working_copy_lineage_bound",
            "working_target_directory_identity_preserved","fixed_main_readonly_entry_observed",
            "comparison_only"] { qualification[key] = json!(true); }
        for key in ["account_contents_read","business_actions_admitted","whole_app_business_accepted",
            "production_ready"] { qualification[key] = json!(false); }
        let case = json!({"baseline":baseline_ref,"qualification":pin("normal-qualification"),
            "target_profile":{"package":actual.package,"uid":actual.uid,"version_code":2,
                "apks":[{"bytes":12,"sha256":"a".repeat(64)}]}});
        (actual,core,case,baseline_ref,baseline,qualification)
    }

    #[test]
    fn native_main_documents_bind_complete_actual_identity_epoch_and_source() {
        let (actual,core,case,reference,baseline,qualification) = native_document_model();
        let check = |a:&ApplicationInspection,c:&Value,b:&Value,q:&Value|
            compare_native_main_documents(&case,a,c,&reference,b,q);
        check(&actual,&core,&baseline,&qualification).unwrap();
        let mut wrong = actual.clone(); wrong.uid += 1;
        assert!(check(&wrong,&core,&baseline,&qualification).is_err());
        let mut wrong = actual.clone(); wrong.apks[0].sha256 = "b".repeat(64);
        assert!(check(&wrong,&core,&baseline,&qualification).is_err());
        let mut wrong = core.clone(); wrong["main"]["init"]["start_ticks"] = json!(12);
        assert!(check(&actual,&wrong,&baseline,&qualification).is_err());
        let mut wrong = qualification.clone(); wrong["normal_source_recipe"]["sha256"] = json!("b".repeat(64));
        assert!(check(&actual,&core,&baseline,&wrong).is_err());
        let mut wrong = qualification.clone(); wrong["core_sha256"] = json!("b".repeat(64));
        assert!(check(&actual,&core,&baseline,&wrong).is_err());
        let mut wrong = baseline.clone(); wrong["framework_epoch"]["sha256"] = json!("b".repeat(64));
        assert!(check(&actual,&core,&wrong,&qualification).is_err());
        let mut wrong = qualification.clone(); wrong["baseline"] = json!(pin("another-baseline"));
        assert!(check(&actual,&core,&baseline,&wrong).is_err());
    }

    #[test]
    fn native_main_documents_reject_legacy_credit_and_broadened_data() {
        let (actual,core,case,reference,baseline,qualification) = native_document_model();
        let check = |b:&Value,q:&Value|
            compare_native_main_documents(&case,&actual,&core,&reference,b,q);
        let mut wrong = baseline.clone(); wrong["schema"] = json!("pocket4-final-business-baseline-v2");
        assert!(check(&wrong,&qualification).is_err());
        let mut wrong = qualification.clone(); wrong["main_identity_qualified"] = json!(true);
        assert!(check(&baseline,&wrong).is_err());
        for key in ["account_contents_read","whole_app_business_accepted","production_ready"] {
            let mut wrong = baseline.clone(); wrong[key] = json!(true);
            assert!(check(&wrong,&qualification).is_err());
        }
        let mut wrong = qualification.clone(); wrong["business_actions_admitted"] = json!(true);
        assert!(check(&baseline,&wrong).is_err());
        let mut wrong = baseline.clone();
        wrong["data_continuity"]["package_uids"]["com.unobserved.app"] = json!(10056);
        wrong["runtime_observation"]["data_continuity"] = wrong["data_continuity"].clone();
        assert!(check(&wrong,&qualification).is_err());
        let mut wrong = baseline.clone();
        wrong["data_continuity"]["original_directory_identity_compared"] = json!(true);
        wrong["runtime_observation"]["data_continuity"] = wrong["data_continuity"].clone();
        assert!(check(&wrong,&qualification).is_err());
    }

    #[test]
    fn native_inventory_documents_are_comparisons_not_installation_authority() {
        let (actual,core,case,reference,baseline,qualification) = native_document_model();
        compare_native_main_documents(&case,&actual,&core,&reference,&baseline,&qualification).unwrap();
        let mut changed = baseline.clone();
        changed["user_zero_package_inventory"] = json!({});
        assert!(compare_native_main_documents(&case,&actual,&core,&reference,&changed,&qualification).is_err());
        let mut changed = qualification.clone();
        changed["user_zero_package_inventory_sha256"] = json!("a".repeat(64));
        assert!(compare_native_main_documents(&case,&actual,&core,&reference,&baseline,&changed).is_err());
        let mut target = actual.clone();
        target.package = "com.ihg.apps.android".into();
        assert!(compare_saved_inventory(&target, &Value::Null).is_err());
        let records = json!([{"package":"android","uid":1000},
            {"package":target.package,"uid":target.uid}]);
        let raw = format!("package:android uid:1000\\npackage:{} uid:{}\\n", target.package, target.uid)
            .replace("\\n", "\n");
        let raw_sha = hex::encode(Sha256::digest(raw.as_bytes()));
        let mut inventory = json!({
            "schema":"droidloom.user-zero-package-inventory.v1",
            "epoch":target.epoch, "records":records,
            "records_sha256":hex::encode(Sha256::digest(serde_json::to_vec(&records).unwrap())),
            "stdout_bytes":raw.len(),"stdout_sha256":raw_sha,"comparison_only":true
        });
        // Pure comparison fixture: no actual token or live inventory is minted.
        inventory["query_receipt"] = json!({"schema":2,"query_pid":300,
            "query_waitid_code":1,"query_waitid_status":0,"exec":{},
            "output_bytes":raw.len(),"output_sha256":raw_sha,"elapsed_millis":1,
            "cgroup_removed":true});
        inventory["query_receipt"]["lifecycle"] = json!({
            "owner":"instance_factory","factory_pid":200,"factory_tid":200,
            "factory_pidfd_device":1,"factory_pidfd_inode":2,
            "query_pidfd_device":1,"query_pidfd_inode":3,"release_acknowledged":true,
            "stdio_creator":{"pid":400,"waitid_code":1,"waitid_status":0}
        });
        compare_saved_inventory(&target,&inventory).unwrap();
        let mut changed = inventory.clone();
        changed["query_receipt"]["query_pid"] = json!(301);
        changed["query_receipt"]["elapsed_millis"] = json!(2);
        compare_saved_inventory(&target,&changed).unwrap();
        changed["query_receipt"]["cgroup_removed"] = json!(false);
        assert!(compare_saved_inventory(&target,&changed).is_err());
        let mut changed = target.clone(); changed.uid += 1;
        assert!(compare_saved_inventory(&changed,&inventory).is_err());
        let mut changed = target.clone(); changed.epoch.framework_start_ticks += 1;
        assert!(compare_saved_inventory(&changed,&inventory).is_err());
        let mut changed = inventory.clone(); changed["passed"] = json!(true);
        assert!(compare_saved_inventory(&target,&changed).is_err());
    }

    #[test]
    fn native_main_documents_require_sample_and_descriptor_retirement() {
        let (actual,core,case,reference,baseline,qualification) = native_document_model();
        let check = |b:&Value,q:&Value|
            compare_native_main_documents(&case,&actual,&core,&reference,b,q);
        for key in ["acquired","closed","close_attempts"] {
            let mut wrong = baseline.clone(); wrong["observation_fds"][key] = json!(11);
            let mut q = qualification.clone(); q["observation_fds"] = wrong["observation_fds"].clone();
            assert!(check(&wrong,&q).is_err());
        }
        let mut wrong = baseline.clone(); wrong["observation_fds"]["remaining"] = json!(1);
        let mut q = qualification.clone(); q["observation_fds"] = wrong["observation_fds"].clone();
        assert!(check(&wrong,&q).is_err());
        let mut wrong = baseline.clone(); wrong["sampling"]["finished_monotonic_ns"] = json!(11);
        assert!(check(&wrong,&qualification).is_err());
    }

    #[test]
    fn ihg_ok_only_verifies_input_readback_and_preserves_unknown_business_outcome() {
        let dir = tempfile::tempdir().unwrap();
        let sources = fixed_sources().unwrap();
        let p = pin("plan");
        let b = pin("baseline");
        let q = pin("qualification");
        let mut child = json!({"schema":"pocket4-final-ihg-public-london-result-v1",
            "base_plan":p,"ok":true,"error":null,"secondary_errors":[],"automatic_retry":false,
            "whole_app_business_accepted":false,"public_london_input_and_readback_completed":true,
            "business_success_verified":false,"business_outcome_unknown":true});
        let worker = saved(dir.path(), "worker.json", &child);
        let host = saved(
            dir.path(),
            "host.json",
            &json!({"fixture":"saved host record, not Android evidence"}),
        );
        let printed = json!({"ok":true,"whole_app_business_accepted":false});
        let mut result = json!({"schema":"pocket4-final-app-case-coordinator-result-v1",
            "base_plan":p,"ok":true,"error":null,"automatic_retry":false,"whole_app_business_accepted":false,
            "worker_result":worker,"worker_host_result":host});
        assert!(
            terminal_result(
                Route::IhgLondon,
                &printed,
                &result,
                Some(&p),
                &b,
                &q,
                &sources[5]
            )
            .is_ok()
        );
        child["public_london_input_and_readback_completed"] = json!(false);
        result["worker_result"] = json!(saved(dir.path(), "worker.json", &child));
        assert!(
            terminal_result(
                Route::IhgLondon,
                &printed,
                &result,
                Some(&p),
                &b,
                &q,
                &sources[5]
            )
            .is_err()
        );
    }
}
