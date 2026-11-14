//! Finite execution routes for the selected, already qualified application leaves.
//!
//! These routes call the original entry, including its source closure, Main,
//! package identity, display lease, limits and cleanup checks. A verified leaf
//! result is scoped progress; it cannot satisfy a whole application release.
use std::collections::BTreeSet;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use droidloom_supervisor::control::{self, application_probe::ApplicationInspection};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use super::{FilePin, pinned};

const QUALIFICATION: &str = "/home/alex/work/pocket4-android-final/qualification";
const SELECTION_SHA: &str = "bdef16ba95bc222a037e78a6849d582083c9706d7cd6f3e7b72cfdf722e900a7";
const SOURCE_CATALOG: &str = include_str!("leaf_sources.json");

#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub(super) enum Route {
    ContactsSearch,
    CalendarCore,
    CalendarReminder,
    CameraPhoto,
    ClockTimer,
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
            GalleryRotation => Definition {
                source: 9,
                package: "com.android.gallery3d",
                request_schema: Some("pocket4-gallery-current-rotation-request-v1"),
                plan_schema: None,
                kind: None,
                seconds: 840,
                state: Some("OWNED_GALLERY_JPEG_ROTATION_REOPEN_AND_CLEANUP_VERIFIED"),
                result_schema: "pocket4-current-owned-gallery-jpeg-rotation-v1",
            },
            GalleryVideo | GallerySeek | GalleryAlbum => Definition {
                source: match self {
                    GalleryVideo => 10,
                    GallerySeek => 11,
                    _ => 12,
                },
                package: "com.android.gallery3d",
                request_schema: Some(match self {
                    GalleryVideo => "pocket4-gallery-current-video-request-v1",
                    GallerySeek => "pocket4-gallery-current-seek-request-v1",
                    _ => "pocket4-gallery-current-album-request-v1",
                }),
                plan_schema: None,
                kind: None,
                seconds: 840,
                state: Some(match self {
                    GalleryVideo => "CURRENT_MAIN_VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED",
                    GallerySeek => {
                        "CURRENT_MAIN_VIDEO_PLAY_PAUSE_RESUME_REOPEN_SEEK_CLEANUP_VERIFIED"
                    }
                    _ => {
                        "CURRENT_MAIN_VIDEO_ALBUM_THUMBNAIL_PLAY_PAUSE_RESUME_REOPEN_SEEK_CLEANUP_VERIFIED"
                    }
                }),
                result_schema: match self {
                    GalleryVideo => "pocket4-gallery-current-owned-video-v1",
                    GallerySeek => "pocket4-gallery-current-owned-video-seek-v1",
                    _ => "pocket4-gallery-current-owned-video-album-v1",
                },
            },
        }
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
        rows.len() == 13 && rows.iter().enumerate().all(|(n, r)| r.index == n),
        "compiled leaf source catalog must retain the exact 13 preparations",
    )?;
    Ok(rows)
}

pub(super) fn validate_selection(selection: &FilePin) -> Result<(), String> {
    require(
        selection.path
            == Path::new(
                "/home/alex/work/p4-app-current-ihg-identity-20261114-e6ac-r1/selection-13.json",
            )
            && selection.bytes == 13160
            && selection.sha256 == SELECTION_SHA,
        "leaf dispatch requires the independently adopted complete 13-preparation selection",
    )?;
    pinned(selection)?;
    Ok(())
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
        Route::ContactsSearch | Route::CalendarCore | Route::CalendarReminder => {
            exact_keys(request, &["base_plan"])?
        }
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
                    "installation",
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
        Route::ContactsSearch | Route::CalendarCore | Route::CalendarReminder
    ) {
        "base_plan"
    } else {
        "plan"
    };
    let pin = ref_field(request, name)?;
    let case = value(&pin)?;
    Ok((Some(pin), case))
}

fn main_binding(
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
        baseline["schema"] == "pocket4-final-business-baseline-v1"
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
        qualification["schema"] == "pocket4-final-business-qualification-v1"
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

pub(super) fn execute(
    plan: &LeafPlan,
    selection: &FilePin,
    actual: &ApplicationInspection,
) -> Result<LeafObservation, String> {
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
    let (baseline, qualification) = main_binding(&case, actual)?;
    let expected_result = output_path(plan, &request, &case)?;
    let cmd = command(plan, source)?;
    // The trusted selected entry still validates the complete transitive source
    // graph and every original business/support/provider gate before its actions.
    claim(plan, actual, source)?;
    let output =
        control::run_prepared_application_leaf(cmd, &actual.epoch, Duration::from_secs(d.seconds))?;
    require(
        output.status.success(),
        "actual leaf process failed; preserve its claim and original logs without replay",
    )?;
    let printed: Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("leaf output is not one complete JSON result: {e}"))?;
    let result_ref = if plan.route == Route::CameraPhoto {
        require(
            printed["result"].as_str() == expected_result.to_str(),
            "camera wrapper output points outside its exact fresh result path",
        )?;
        let raw = crate::release::read_frozen(&expected_result, 8 * 1024 * 1024)
            .map_err(|e| e.to_string())?;
        FilePin {
            path: expected_result.clone(),
            bytes: raw.len() as u64,
            sha256: hex::encode(Sha256::digest(&raw)),
        }
    } else {
        ref_field(&printed, "result")?
    };
    require(
        result_ref.path == expected_result,
        "leaf returned a receipt outside its exact new case result",
    )?;
    let result = value(&result_ref)?;
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
    Ok(LeafObservation {
        route: plan.route,
        request: plan.request.clone(),
        preparation: source.preparation.clone(),
        entry_source: source.entry.clone(),
        result: result_ref,
        state: result["state"]
            .as_str()
            .unwrap_or("original_leaf_ok")
            .into(),
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
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pin(name: &str) -> FilePin {
        FilePin {
            path: PathBuf::from(format!("/fixture/{name}")),
            bytes: 1,
            sha256: "1".repeat(64),
        }
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
            assert!((420..=1200).contains(&d.seconds));
        }
    }
    #[test]
    fn arbitrary_or_old_preparation_selection_is_rejected_before_a_child() {
        assert!(validate_selection(&pin("arbitrary-selection")).is_err());
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
        let mut result = json!({"schema":"pocket4-current-owned-gallery-jpeg-rotation-v1","state":state,
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
    fn physical_main_binding_rejects_changed_epoch_and_current_apk() {
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
                "schema":"pocket4-final-business-baseline-v1", "observation_fds":{"closed":true},
                "framework_epoch":{"schema":"pocket4-framework-epoch-v1","sha256":"b".repeat(64),
                    "binding":{"boot_id":observed.epoch.boot_id,"processes":{
                        "init":{"host_pid":10},"system_server":{"host_pid":20,"start_ticks":30}}}}
            }),
        );
        let qualification = saved(
            dir.path(),
            "qualification.json",
            &json!({
                "schema":"pocket4-final-business-qualification-v1","baseline":baseline,
                "main_identity_qualified":true,"predeployment_data_directory_identity_preserved":true,
                "business_actions_admitted":false,"whole_app_business_accepted":false,
                "main_epoch_sha256":"b".repeat(64),"observation_fds":{"closed":true}
            }),
        );
        let case = json!({"baseline":baseline,"qualification":qualification,
            "target_profile":{"package":observed.package,"uid":observed.uid,"version_code":2,
                "apks":[{"bytes":12,"sha256":"a".repeat(64)}]}});
        assert!(main_binding(&case, &observed).is_ok());
        observed.epoch.framework_start_ticks = 31;
        assert!(main_binding(&case, &observed).is_err());
        observed.epoch.framework_start_ticks = 30;
        observed.apks[0].sha256 = "c".repeat(64);
        assert!(main_binding(&case, &observed).is_err());
        observed.apks[0].sha256 = "a".repeat(64);
        fs::write(&qualification.path, b"{}").unwrap();
        assert!(main_binding(&case, &observed).is_err());
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
