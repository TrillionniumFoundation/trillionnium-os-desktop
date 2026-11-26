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
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::leaf_release::NativeRelease;
use super::{ApplicationPlan, FilePin, RuntimePlan, pinned};
use super::runtime_identity::{IdentityObservation, VerifiedMaterialBatch};

const QUALIFICATION: &str = "/var/lib/droidloom/qualification/pocket4";
const SELECTION_PATH: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/selection/selection-14.json";
const SELECTION_BYTES: u64 = 4669;
const SELECTION_SHA: &str = "40ec943537a140b11a055587e9b7bd4bb39f944429e6d509df6241842e9be1c9";
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
    application: ApplicationInspection,
}

impl fmt::Debug for HeldMainCustody {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("HeldMainCustody")
            .field("application", &self.application)
            .field("facts", self.observation.facts())
            .field("peer", self.observation.peer()).finish()
    }
}

impl Serialize for HeldMainCustody {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeStruct;
        let mut out = serializer.serialize_struct("HeldMainCustody", 4)?;
        out.serialize_field("schema", "droidloom.application-main-custody.v1")?;
        out.serialize_field("application", &self.application)?;
        out.serialize_field("facts", self.observation.facts())?;
        out.serialize_field("peer", self.observation.peer())?;
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
    pub(super) fn observe(
        inspector: &mut control::NativeApplicationInspector,
        application: &ApplicationInspection,
    ) -> Result<Self, String> {
        let observation = inspector.observe_main(&application.epoch)
            .map_err(|error| error.to_string())?;
        let held = Self { observation, application: application.clone() };
        held.require_application(application)?;
        Ok(held)
    }

    pub(super) fn require_application(&self, actual: &ApplicationInspection) -> Result<(), String> {
        use droidloom_supervisor::main_custody::MainDataRole;
        let facts = self.observation.facts();
        let data = &facts.persistent_data;
        require(&self.application == actual && facts.epoch == actual.epoch
            && actual.user == 0
            && data.backings[0].role == MainDataRole::Data
            && data.backings[1].role == MainDataRole::Metadata,
            "leaf Main differs in package/user/UID/version/full APKs, epoch or backing roles")?;
        require_working_origin(data.original_copy_origin.as_ref(),
            [data.backings[0].backing.stable7(), data.backings[1].backing.stable7()])
    }

    pub(super) fn revalidate(
        &self,
        inspector: &mut control::NativeApplicationInspector,
        actual: &ApplicationInspection,
    ) -> Result<(), String> {
        self.require_application(actual)?;
        inspector.revalidate_main(&self.observation).map_err(|error| error.to_string())?;
        self.require_application(actual)
    }

    pub(super) fn guard_projection(&self) -> Result<(), String> {
        self.require_application(&self.application)
    }

    /// Borrow the actual opaque fact for a future normal engine observation.
    /// Serializing facts()/peer() does not recreate this object.
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
        self.main.require_application(&self.main.application)?;
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
        self.custody.as_ref().ok_or("leaf has no actual normal Main/result custody")?.guard()
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
            && self.state == "SETTINGS_PAGES_ROUNDTRIP_VERIFIED_RESTORED"
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
                state: Some("SETTINGS_PAGES_ROUNDTRIP_VERIFIED_RESTORED"),
                result_schema: "pocket4-settings-pages-case-result-v2",
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
                path: "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/selection/leaf_sources.json".into(),
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

// Original leaf protocol comparisons only; no JSON field grants Main authority.
fn legacy_main_documents(
    case: &Value,
    actual: &ApplicationInspection,
) -> Result<(FilePin, FilePin), String> {
    let baseline_ref = ref_field(case, "baseline")?;
    let qualification_ref = ref_field(case, "qualification")?;
    let baseline = value(&baseline_ref)?;
    let qualification = value(&qualification_ref)?;
    let epoch = &baseline["framework_epoch"];
    let binding = &epoch["binding"];
    require(
        baseline["schema"] == "pocket4-final-business-baseline-v2"
            && epoch["schema"] == "pocket4-framework-epoch-v1"
            && binding["boot_id"].as_str() == Some(actual.epoch.boot_id.as_str())
            && binding["processes"]["init"]["host_pid"].as_u64()
                == Some(u64::from(actual.epoch.cell_host_pid))
            && binding["processes"]["system_server"]["host_pid"].as_u64()
                == Some(u64::from(actual.epoch.framework_host_pid))
            && binding["processes"]["system_server"]["start_ticks"].as_u64()
                == Some(actual.epoch.framework_start_ticks),
        "leaf baseline and current daemon observation do not identify the same physical Main",
    )?;
    require(
        qualification["schema"] == "pocket4-final-business-qualification-v2"
            && ref_field(&qualification, "baseline")? == baseline_ref
            && qualification["main_identity_qualified"] == true
            && qualification["predeployment_data_directory_identity_preserved"] == true
            && qualification["business_actions_admitted"] == false
            && qualification["whole_app_business_accepted"] == false
            && qualification["main_epoch_sha256"] == epoch["sha256"]
            && qualification["observation_fds"] == baseline["observation_fds"],
        "leaf needs its actual identity/data-preservation qualification for the same baseline",
    )?;
    require(
        epoch["sha256"]
            .as_str()
            .is_some_and(crate::release::valid_sha),
        "leaf baseline has no valid complete framework epoch digest",
    )?;
    if let Some(profile) = case.get("target_profile") {
        require(
            profile["package"].as_str() == Some(actual.package.as_str())
                && profile["uid"].as_u64() == Some(u64::from(actual.uid))
                && profile["version_code"].as_u64() == Some(actual.version_code),
            "leaf target profile differs from current PM identity",
        )?;
        let declared: BTreeSet<_> = profile["apks"]
            .as_array()
            .ok_or("leaf target APK set missing")?
            .iter()
            .map(|x| (x["bytes"].as_u64(), x["sha256"].as_str()))
            .collect();
        let installed: BTreeSet<_> = actual
            .apks
            .iter()
            .map(|x| (Some(x.bytes), Some(x.sha256.as_str())))
            .collect();
        require(
            declared == installed && declared.len() == actual.apks.len(),
            "leaf target APK bytes differ from the current complete selected official set",
        )?;
    }
    Ok((baseline_ref, qualification_ref))
}

fn main_binding(
    case: &Value,
    actual: &ApplicationInspection,
    main: &HeldMainCustody,
) -> Result<(FilePin, FilePin), String> {
    main.require_application(actual)?;
    legacy_main_documents(case, actual)
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
        exact_keys(
            printed,
            &[
                "result",
                "state",
                "case_business_success_verified",
                "scope",
                "accepted_gates",
                "whole_app_business_accepted",
            ],
        )?;
        let empty = |key: &str| {
            result["cancellation_commit"][key]
                .as_array()
                .is_some_and(Vec::is_empty)
        };
        let two = |key: &str| result[key].as_array().is_some_and(|rows| rows.len() == 2);
        require(
            result["case_business_success_verified"] == true
                && printed["case_business_success_verified"] == true
                && printed["state"] == result["state"]
                && result["scope"] == json!(["settings.pages", "settings.roundtrip"])
                && printed["scope"] == result["scope"]
                && result["accepted_gates"] == result["scope"]
                && printed["accepted_gates"] == result["accepted_gates"]
                && result["remaining_gates"]
                    == json!([
                        "settings.permissions",
                        "identity",
                        "lifecycle",
                        "stability",
                        "data_permissions",
                        "release_scope",
                        "ui_observation"
                    ])
                && Some(ref_field(result, "base_plan")?).as_ref() == case_ref
                && result["all_five_pages_observed"] == true
                && result["pages"].as_array().is_some_and(|v| v.len() == 5)
                && result["identity_permissions_directories_preserved"] == true
                && result["permission_account_state_preserved"] == true
                && result["permission_interfaces"]["settings_permissions_gate_accepted"] == false
                && result["permission_interfaces"]["readonly_input_error_verified"] == true
                && result["complete_task_baseline_restored"] == true
                && result["final_source_identity_chain_unchanged"] == true
                && result["evidence_witness_closed"] == true
                && result["native_launch_count"] == 2
                && result["page_route_count"] == 11
                && result["observation_count"] == 13
                && two("native_claims")
                && result["normally_closed_claims"] == result["native_claims"]
                && two("launches")
                && two("normal_closes")
                && two("host_flow_contexts_closed")
                && [
                    "pending_route",
                    "pending_UI",
                    "pending_setting",
                    "pending_native",
                ]
                .iter()
                .all(|key| result.get(*key).is_some_and(Value::is_null))
                && result
                    .get("unknown_retained_without_further_mutation")
                    .is_none_or(|v| v == false)
                && result
                    .get("unknown_or_conflicting_setting_retained_without_replay")
                    .is_none_or(|v| v == false)
                && result["setting_writes"] == 2
                && result["provider_writes"] == 2
                && [
                    "permission_writes",
                    "account_writes",
                    "package_writes",
                    "other_provider_writes",
                ]
                .iter()
                .all(|key| result[*key] == 0)
                && [
                    "apply_readback_verified",
                    "effect_verified",
                    "reopen_persistence_verified",
                    "restore_readback_verified",
                    "restored_effect_verified",
                ]
                .iter()
                .all(|key| result["setting_roundtrip"][*key] == true)
                && result["Android_runtime_qualification_inferred_from_source"] == false
                && empty("observed_before_commit")
                && empty("pending_at_commit")
                && result["cancellation_commit"]["decision_frozen_after_host_context_close"]
                    == true,
            "Settings result must prove pages and exact restored roundtrip with two owned launches/closes; permissions remain pending and unknown effects forbid credit",
        )?;
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
) -> Result<(NativeRelease, FilePin, FilePin), String> {
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let source = &sources[4];
    let lease = NativeRelease::bind_current(
        selection, SOURCE_CATALOG, &source.preparation, &source.entry,
    )?;
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
) -> Result<ExecutedClockCase, String> {
    require(matches!(plan.route, Route::ClockTimerRemaining | Route::ClockExpiry),
        "Clock fact production only accepts original timer15 and expiry06")?;
    let (observation, _, result_custody) =
        execute_observed(plan, selection, actual, main, release)?;
    Ok(ExecutedClockCase { observation, result_custody })
}


fn normal_route_release(plan: &LeafPlan, selection: &FilePin) -> Result<NativeRelease, String> {
    validate_selection(selection)?;
    let sources = fixed_sources()?;
    let source = &sources[plan.route.definition().source];
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
    actual: &ApplicationInspection,
) -> Result<(ApplicationInspection, LeafObservation), String> {
    require(plan.route != Route::ClockTimerPair,
        "Clock pair requires its one shared two-case Main and owner factory")?;
    let seconds = plan.route.definition().seconds;
    // One unchanged leaf limit, two fixed Main transport allowances, one
    // normal package inspection, and finite source/retirement bookends.
    let window = seconds + 2 * 70 + 250 + 120;
    let release = normal_route_release(plan, selection)?;
    release.cover_window(window)?;
    let end = Instant::now() + Duration::from_secs(window);
    leaf_window(end, seconds + 2 * 70 + 250 + 30)?;
    materials.revalidate()?;
    materials.observe(requested, runtime.android_user, &runtime.expected_epoch, actual, actual)?;
    let main = HeldMainCustody::observe(inspector, actual)?;
    release.guard()?;
    leaf_window(end, seconds + 70 + 250 + 30)?;
    let (mut observation, _, result) = execute_observed(plan, selection, actual, &main, &release)?;
    result.guard()?;
    release.guard()?;
    leaf_window(end, 250 + 70 + 30)?;
    let reply = inspector.inspect(&actual.package, actual.user).map_err(|error| error.to_string())?;
    let (after, _) = super::consume_inspection(reply, &actual.package, actual.user)?;
    main.require_application(&after)?;
    leaf_window(end, 70 + 30)?;
    main.revalidate(inspector, &after)?;
    materials.revalidate()?;
    let final_identity = materials.observe(requested, runtime.android_user,
        &runtime.expected_epoch, actual, &after)?;
    release.guard()?;
    result.guard()?;
    leaf_window(end, 0)?;
    observation.custody = Some(HeldLeafCustody {
        main, release, result, final_identity: Some(final_identity),
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
    let (baseline, qualification) = main_binding(&case, actual, main)?;
    let expected_result = output_path(plan, &request, &case)?;
    let cmd = command(plan, source)?;
    // The trusted selected entry still validates the complete transitive source
    // graph and every original business/support/provider gate before its actions.
    claim(plan, actual, source)?;
    let output = if plan.route.current_gallery() {
        control::run_prepared_gallery_image_leaf(cmd, &actual.epoch)?
    } else if plan.route == Route::CalendarReminder {
        control::run_prepared_calendar_reminder_leaf(cmd, &actual.epoch)?
    } else if plan.route == Route::SettingsSupportedPages {
        control::run_prepared_settings_pages_leaf(cmd, &actual.epoch)?
    } else {
        control::run_prepared_application_leaf(cmd, &actual.epoch, Duration::from_secs(d.seconds))?
    };
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
        &baseline,
        &qualification,
        source,
    )?;
    // Re-read the externally selected inputs after completed child retirement.
    for pin in [
        selection,
        &source.preparation,
        &source.entry,
        &plan.request,
        &baseline,
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
    Ok((observation, result, result_custody))
}

#[cfg(test)]
mod tests {
    use super::*;
    const CURRENT_SELECTION: &str = include_str!("../tests/fixtures/selection-14-20261120.json");
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

    #[test]
    fn settings_pages_terminal_keeps_partial_scope_and_rejects_unknown_or_extra_credit() {
        let source = SelectedSource {
            index: 13,
            preparation: pin("settings-prep"),
            entry: pin("settings-entry"),
        };
        let plan = pin("settings-plan");
        let baseline = pin("baseline");
        let qualification = pin("qualification");
        let result_pin = pin("settings-result");
        let printed = json!({"result":result_pin,"state":"SETTINGS_PAGES_ROUNDTRIP_VERIFIED_RESTORED",
            "case_business_success_verified":true,"scope":["settings.pages","settings.roundtrip"],
            "accepted_gates":["settings.pages","settings.roundtrip"],"whole_app_business_accepted":false});
        let result = json!({"schema":"pocket4-settings-pages-case-result-v2","state":"SETTINGS_PAGES_ROUNDTRIP_VERIFIED_RESTORED",
            "whole_app_business_accepted":false,"automatic_retry":false,"case_business_success_verified":true,
            "scope":["settings.pages","settings.roundtrip"],"accepted_gates":["settings.pages","settings.roundtrip"],"base_plan":plan,
            "remaining_gates":["settings.permissions","identity","lifecycle","stability","data_permissions","release_scope","ui_observation"],
            "all_five_pages_observed":true,"pages":[0,1,2,3,4],"identity_permissions_directories_preserved":true,
            "complete_task_baseline_restored":true,"final_source_identity_chain_unchanged":true,"evidence_witness_closed":true,
            "permission_account_state_preserved":true,"permission_interfaces":{"settings_permissions_gate_accepted":false,"readonly_input_error_verified":true},
            "native_launch_count":2,"page_route_count":11,"observation_count":13,
            "native_claims":["one","two"],"normally_closed_claims":["one","two"],"launches":[0,1],"normal_closes":[0,1],
            "host_flow_contexts_closed":[0,1],"pending_route":null,"pending_UI":null,"pending_setting":null,"pending_native":null,
            "setting_writes":2,"provider_writes":2,"other_provider_writes":0,"permission_writes":0,"account_writes":0,"package_writes":0,
            "setting_roundtrip":{"apply_readback_verified":true,"effect_verified":true,"reopen_persistence_verified":true,"restore_readback_verified":true,"restored_effect_verified":true},
            "Android_runtime_qualification_inferred_from_source":false,
            "cancellation_commit":{"observed_before_commit":[],"pending_at_commit":[],"decision_frozen_after_host_context_close":true}});
        let check = |value: &Value| {
            terminal_result(
                Route::SettingsSupportedPages,
                &printed,
                value,
                Some(&plan),
                &baseline,
                &qualification,
                &source,
            )
        };
        check(&result).unwrap();
        for (key, value) in [
            (
                "accepted_gates",
                json!([
                    "settings.pages",
                    "settings.roundtrip",
                    "settings.permissions"
                ]),
            ),
            ("schema", json!("pocket4-settings-pages-case-result-v1")),
            (
                "setting_roundtrip",
                json!({"restore_readback_verified":false}),
            ),
            (
                "permission_interfaces",
                json!({"settings_permissions_gate_accepted":false,"readonly_input_error_verified":false}),
            ),
            ("pending_setting", json!({"sent":true})),
            ("pending_native", json!({"scope":"unknown"})),
            ("provider_writes", json!(0)),
            ("permission_writes", json!(1)),
            ("remaining_gates", json!([])),
            ("whole_app_business_accepted", json!(true)),
            ("setting_writes", json!(1)),
            ("unknown_retained_without_further_mutation", json!(true)),
            ("normal_closes", json!([0])),
            ("base_plan", json!(pin("another-plan"))),
        ] {
            let mut changed = result.clone();
            changed[key] = value;
            assert!(check(&changed).is_err(), "{key}");
        }
        for key in [
            "pending_route",
            "pending_UI",
            "pending_setting",
            "pending_native",
        ] {
            let mut missing = result.clone();
            missing.as_object_mut().unwrap().remove(key);
            assert!(check(&missing).is_err(), "missing {key}");
        }
        let mut missing_input_error = result.clone();
        missing_input_error["permission_interfaces"]
            .as_object_mut()
            .unwrap()
            .remove("readonly_input_error_verified");
        assert!(check(&missing_input_error).is_err());
        let mut cancelled = result;
        cancelled["cancellation_commit"]["pending_at_commit"] = json!([15]);
        assert!(check(&cancelled).is_err());
        assert_eq!(Route::SettingsSupportedPages.definition().source, 13);
        assert_eq!(Route::SettingsSupportedPages.definition().seconds, 900);
        assert_eq!(
            Route::SettingsSupportedPages.package(),
            "com.android.settings"
        );
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
                "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/ihg/app_entry.py"
            )
        );
        assert_eq!(source.entry.bytes, 13828);
        assert_eq!(
            source.entry.sha256,
            "c7c42c574b9f72b6880991bedd670ffce5a97146748315c249b9fa116bc79b4d"
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

    #[test]
    fn legacy_main_documents_only_compare_epoch_and_current_apk_without_minting_authority() {
        use droidloom_supervisor::control::application_probe::{InstalledApk, RuntimeEpoch};
        let dir = tempfile::tempdir().unwrap();
        let mut observed = ApplicationInspection {
            package: "com.android.contacts".into(),
            user: 0,
            uid: 10055,
            version_code: 2,
            epoch: RuntimeEpoch {
                boot_id: "97d9600f-e081-465c-9e6e-62651e09806b".into(),
                cell_host_pid: 10,
                framework_host_pid: 20,
                framework_start_ticks: 30,
            },
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: "/system/app/Contacts.apk".into(),
                bytes: 12,
                sha256: "a".repeat(64),
            }],
        };
        let baseline = saved(
            dir.path(),
            "baseline.json",
            &json!({
                "schema":"pocket4-final-business-baseline-v2", "observation_fds":{"closed":true},
                "framework_epoch":{"schema":"pocket4-framework-epoch-v1","sha256":"b".repeat(64),
                    "binding":{"boot_id":observed.epoch.boot_id,"processes":{
                        "init":{"host_pid":10},"system_server":{"host_pid":20,"start_ticks":30}}}}
            }),
        );
        let qualification = saved(
            dir.path(),
            "qualification.json",
            &json!({
                "schema":"pocket4-final-business-qualification-v2","baseline":baseline,
                "main_identity_qualified":true,"predeployment_data_directory_identity_preserved":true,
                "business_actions_admitted":false,"whole_app_business_accepted":false,
                "main_epoch_sha256":"b".repeat(64),"observation_fds":{"closed":true}
            }),
        );
        let case = json!({"baseline":baseline,"qualification":qualification,
            "target_profile":{"package":observed.package,"uid":observed.uid,"version_code":2,
                "apks":[{"bytes":12,"sha256":"a".repeat(64)}]}});
        assert!(legacy_main_documents(&case, &observed).is_ok());
        observed.epoch.framework_start_ticks = 31;
        assert!(legacy_main_documents(&case, &observed).is_err());
        observed.epoch.framework_start_ticks = 30;
        observed.apks[0].sha256 = "c".repeat(64);
        assert!(legacy_main_documents(&case, &observed).is_err());
        observed.apks[0].sha256 = "a".repeat(64);
        fs::write(&qualification.path, b"{}").unwrap();
        assert!(legacy_main_documents(&case, &observed).is_err());
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
