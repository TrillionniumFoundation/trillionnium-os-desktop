//! Fixed single-application entry for installed resource-bounded root units.
use super::leaf_release::{Inputs, ROOT};
use super::leaf_routes::Route;
use super::{FilePin, RuntimePlan, leaf_release, leaf_routes, run_files};
use droidloom_supervisor::control::{
    DEFAULT_CONTROL_SOCKET, NativeApplicationSourceLocks, NativeOwnedLeafUnit, OwnedLeafProfile,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};

const CALENDAR_UNIT: &str =
    include_str!("../../../packaging/systemd/system/droidloom-native-calendar@.service");
const GALLERY_UNIT: &str =
    include_str!("../../../packaging/systemd/system/droidloom-native-gallery@.service");
const SETTINGS_UNIT: &str =
    include_str!("../../../packaging/systemd/system/droidloom-native-settings@.service");

fn selected_route(
    profile: OwnedLeafProfile,
    plan: &RuntimePlan,
) -> Result<&leaf_routes::LeafPlan, String> {
    if plan.schema != 2
        || plan.android_user != 0
        || plan.applications.len() != 1
        || plan.execute_public_browser
        || plan.browser_fixture.is_some()
        || plan.preparation_selection.is_none()
    {
        return Err(
            "owned qualification unit requires one exact user-0 leaf plan and no browser operation"
                .into(),
        );
    }
    let app = &plan.applications[0];
    let leaf = app
        .leaf
        .as_ref()
        .ok_or("owned qualification unit requires an explicit current leaf")?;
    let expected = match profile {
        OwnedLeafProfile::CalendarReminder => {
            app.package == "com.android.calendar" && leaf.route == Route::CalendarReminder
        }
        OwnedLeafProfile::SettingsPages => {
            app.package == "com.android.settings" && leaf.route == Route::SettingsSupportedPages
        }
        OwnedLeafProfile::Gallery => {
            app.package == "com.android.gallery3d"
                && matches!(
                    leaf.route,
                    Route::GalleryRotation
                        | Route::GalleryVideo
                        | Route::GallerySeek
                        | Route::GalleryAlbum
                )
        }
    };
    if !expected || app.expected_input.is_none() || leaf.output.is_some() {
        return Err("single owned unit plan differs from its fixed package, route or complete source requirement".into());
    }
    Ok(leaf)
}

pub(super) fn run(profile: &str, expected_sha: &str) -> Result<(), String> {
    let profile = OwnedLeafProfile::parse(profile)?;
    if !crate::release::valid_sha(expected_sha) {
        return Err("exact owned root plan hash required".into());
    }
    let locks = NativeApplicationSourceLocks::acquire().map_err(|e| e.to_string())?;
    let mut inputs = Inputs::new();
    let path = PathBuf::from(format!(
        "{ROOT}/plans/{}/{expected_sha}.json",
        profile.name()
    ));
    let raw = inputs.read(&path, None, super::INPUT_LIMIT, true, false)?;
    if hex::encode(Sha256::digest(&raw)) != expected_sha {
        return Err("actual complete root plan differs from its independent instance hash".into());
    }
    let plan: RuntimePlan =
        serde_json::from_value(leaf_release::json(&raw)?).map_err(|e| e.to_string())?;
    let leaf = selected_route(profile, &plan)?;
    let selection = plan
        .preparation_selection
        .as_ref()
        .ok_or("compiled selection missing")?;
    let release = leaf_routes::owned_route_release(leaf, selection)?;
    // This does not extend the foreground owner's window. Reject a plan whose
    // existing lease cannot cover its entire controller and stop/cleanup budget.
    release.cover_window(profile.controller_seconds() + 180 + 30)?;
    let template = match profile {
        OwnedLeafProfile::CalendarReminder => CALENDAR_UNIT,
        OwnedLeafProfile::Gallery => GALLERY_UNIT,
        OwnedLeafProfile::SettingsPages => SETTINGS_UNIT,
    };
    let installed = PathBuf::from(format!("/usr/lib/systemd/system/{}", profile.template()));
    let template_pin = FilePin {
        path: installed.clone(),
        bytes: template.len() as u64,
        sha256: hex::encode(Sha256::digest(template)),
    };
    if inputs.read(&installed, Some(&template_pin), 16 * 1024, true, false)? != template.as_bytes()
    {
        return Err("installed normal-package unit differs from the compiled entry".into());
    }
    let unit = NativeOwnedLeafUnit::capture(profile, expected_sha, &locks)?;
    inputs.guard()?;
    release.guard()?;
    let report = run_files(Path::new(DEFAULT_CONTROL_SOCKET), &path, expected_sha, 1)?;
    // The manager query runs only after the original nested invocation has
    // retired, so it cannot reenter that invocation's ownership mutex.
    unit.guard()?;
    inputs.guard()?;
    release.guard()?;
    locks.validate().map_err(|e| e.to_string())?;
    let result = json!({"schema":"droidloom-owned-native-leaf-report-v1",
        "plan":{"path":path,"bytes":raw.len(),"sha256":expected_sha},
        "profile":profile.name(),"unit":unit.observation(),"runtime_report":report,
        "automatic_retry":false,"runtime_qualified":false,"production_ready":false,
        "whole_app_business_accepted":false,
        "unit_retirement_requires_external_readback":true});
    let stdout = std::io::stdout();
    let mut output = stdout.lock();
    serde_json::to_writer(&mut output, &result).map_err(|e| e.to_string())?;
    output
        .write_all(b"\n")
        .and_then(|()| output.flush())
        .map_err(|e| e.to_string())?;
    // Keep the real release, root request, unit and lock OFDs until publication.
    inputs.guard()?;
    release.guard()?;
    locks.validate().map_err(|e| e.to_string())?;
    Err("application acceptance remains incomplete; retain the exact unit report and all pending gates".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn model(route: &str, package: &str) -> RuntimePlan {
        let pin = json!({"path":"/fixture","bytes":1,"sha256":"a".repeat(64)});
        serde_json::from_value(json!({"schema":2,"android_user":0,"main_qualification":pin,
            "expected_epoch":{"boot_id":"fixture","cell_host_pid":1,"framework_host_pid":2,"framework_start_ticks":3},
            "gate_registry":pin,"preparation_selection":pin,"execute_public_browser":false,"browser_fixture":null,
            "applications":[{"package":package,"expected_input":{"version_code":1,
                "apks":[{"name":"base.apk","bytes":1,"sha256":"a".repeat(64)}],"source_receipt":pin},
                "leaf":{"route":route,"request":pin,"output":null}}]})).unwrap()
    }

    #[test]
    fn fixed_unit_plans_preserve_one_exact_route_and_the_full_original_dispatch() {
        let settings = model("settings_supported_pages", "com.android.settings");
        assert!(selected_route(OwnedLeafProfile::SettingsPages, &settings).is_ok());
        assert!(selected_route(OwnedLeafProfile::Gallery, &settings).is_err());
        assert!(selected_route(OwnedLeafProfile::CalendarReminder, &settings).is_err());
        assert!(selected_route(OwnedLeafProfile::SettingsPages, &model("settings_supported_pages", "com.android.gallery3d")).is_err());
        let calendar = model("calendar_reminder", "com.android.calendar");
        assert!(selected_route(OwnedLeafProfile::CalendarReminder, &calendar).is_ok());
        assert!(selected_route(OwnedLeafProfile::Gallery, &calendar).is_err());
        for route in [
            "gallery_rotation",
            "gallery_video",
            "gallery_seek",
            "gallery_album",
        ] {
            let mut p = model(route, "com.android.gallery3d");
            assert!(selected_route(OwnedLeafProfile::Gallery, &p).is_ok());
            p.applications.push(p.applications[0].clone());
            assert!(selected_route(OwnedLeafProfile::Gallery, &p).is_err());
        }
        for route in ["calendar_core", "clock_timer", "contacts_search"] {
            assert!(
                selected_route(
                    OwnedLeafProfile::CalendarReminder,
                    &model(route, "com.android.calendar")
                )
                .is_err()
            );
        }
        let mut browser = calendar.clone();
        browser.execute_public_browser = true;
        assert!(selected_route(OwnedLeafProfile::CalendarReminder, &browser).is_err());
        let mut absent = calendar;
        absent.applications[0].expected_input = None;
        assert!(selected_route(OwnedLeafProfile::CalendarReminder, &absent).is_err());
    }
}
