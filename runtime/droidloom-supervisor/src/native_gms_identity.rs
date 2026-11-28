//! GMS implementation/configuration identity from already-retained normal owners.
//! No command, file open, deadline extension, account mutation or API test occurs
//! here. The common SelfCheck pair and its PM window remain the sole FD owners.
//! A serialized comparison, manifest, UI label or account count is not authority.
use super::{NativeFamilyUiEvidence, NativeUiPermissionPreservation};
use crate::application_permission_state::{GmsComponentEnablement, PackagePermissionState};
use crate::control::application_probe::ApplicationInspection;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::sync::OnceLock;

const PACKAGE: &str = "com.google.android.gms";
const VERSION: u64 = 252432036;
const APK_BYTES: u64 = 108_520_063;
const APK_SHA256: &str = "1094fa60ace2367ac52bd08d1bd4f33fa8144ba930e355121b28234b8ebbf382";
const MANIFEST: &[u8] = include_bytes!("native_gms_identity_manifest.json");
const MANIFEST_SHA256: &str = "dc2db8a8e380e2a3e569a772c8f8db4bf22abf2617ea60b39103ce341c84b862";
const PANEL_ID: &str = "com.google.android.gms:id/self_check_name";
const CORE_COMPONENTS: [&str; 5] = [
    "org.microg.gms.auth.loginservice.GoogleLoginService",
    "com.google.android.gms.auth.GetToken",
    "org.microg.gms.gcm.PushRegisterService",
    "org.microg.gms.gcm.McsService",
    "org.microg.gms.location.manager.GoogleLocationManagerService",
];
fn need(value: bool, reason: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}
fn digest<T: serde::Serialize + ?Sized>(value: &T) -> Result<String, String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(value).map_err(|e| e.to_string())?)
    ))
}
fn source() -> Result<&'static Value, String> {
    static SOURCE: OnceLock<Result<Value, String>> = OnceLock::new();
    SOURCE
        .get_or_init(|| {
            need(
                MANIFEST.len() == 50_103
                    && format!("{:x}", Sha256::digest(MANIFEST)) == MANIFEST_SHA256,
                "original GMS manifest source bytes differ",
            )?;
            let value: Value = serde_json::from_slice(MANIFEST).map_err(|e| e.to_string())?;
            need(
                value["schema"] == "droidloom.selected-microg-identity-manifest.v1"
                    && value["package"] == PACKAGE
                    && value["version_code"] == VERSION
                    && value["apk_bytes"] == APK_BYTES
                    && value["apk_sha256"] == APK_SHA256
                    && value["selected_android_api"] == 37
                    && value["application"]["enabled_default"] == true,
                "original GMS implementation/default configuration identity differs",
            )?;
            let rows = value["services"]
                .as_array()
                .ok_or("GMS service manifest is not an array")?;
            need(
                rows.len() == 122,
                "original complete GMS service roster differs",
            )?;
            let mut names = std::collections::BTreeSet::new();
            let mut action_count = 0;
            for row in rows {
                let name = row["name"].as_str().ok_or("GMS service name is absent")?;
                need(
                    names.insert(name),
                    "original GMS service declaration is repeated",
                )?;
                row["enabled_default"]
                    .as_bool()
                    .ok_or("GMS service default is unresolved")?;
                let actions = row["intent_actions"]
                    .as_array()
                    .ok_or("GMS service actions are absent")?;
                need(
                    actions.iter().all(Value::is_string),
                    "GMS declared service action is malformed",
                )?;
                action_count += actions.len();
            }
            need(
                action_count == 241 && CORE_COMPONENTS.iter().all(|name| names.contains(name)),
                "GMS declared compatibility/core service scope differs",
            )?;
            Ok(value)
        })
        .as_ref()
        .map_err(Clone::clone)
}
fn require_application(app: &ApplicationInspection) -> Result<(), String> {
    need(
        app.package == PACKAGE
            && app.user == 0
            && app.uid != 0
            && app.uid < 100_000
            && app.version_code == VERSION
            && app.apks.len() == 1
            && app.apks[0].name == "base.apk"
            && app.apks[0].bytes == APK_BYTES
            && app.apks[0].sha256 == APK_SHA256,
        "GMS identity requires the exact original selected APK and current complete PM subject",
    )
}
fn panel_pair(first: &Value, reopened: &Value) -> Result<(), String> {
    let rows = first
        .as_array()
        .ok_or("GMS actual SelfCheck is not a panel")?;
    need(
        first == reopened
            && !rows.is_empty()
            && rows.len() <= 128
            && rows.iter().all(|row| {
                row["resource_id"] == PANEL_ID
                    && row["text"].as_str().is_some_and(|s| !s.trim().is_empty())
                    && row["class"].is_string()
                    && row["enabled"].is_boolean()
            }),
        "GMS identity needs the same source-fixed actual SelfCheck readback in both retained tasks",
    )
}
fn component_configuration(
    state: &GmsComponentEnablement,
) -> Result<BTreeMap<String, bool>, String> {
    let manifest = source()?;
    state.require_unrestricted()?;
    need(
        state.application_enabled(
            manifest["application"]["enabled_default"]
                .as_bool()
                .unwrap(),
        ),
        "GMS actual PM application is disabled",
    )?;
    let mut services = BTreeMap::new();
    for row in manifest["services"].as_array().unwrap() {
        let name = row["name"].as_str().unwrap();
        let enabled = state.service_enabled(name, row["enabled_default"].as_bool().unwrap());
        services.insert(name.into(), enabled);
    }
    need(
        CORE_COMPONENTS
            .iter()
            .all(|name| services.get(*name) == Some(&true)),
        "GMS core account/token/push/location component configuration is disabled",
    )?;
    Ok(services)
}
fn configured_services(state: &PackagePermissionState) -> Result<BTreeMap<String, bool>, String> {
    need(
        state.package() == PACKAGE && state.version_code() == VERSION,
        "GMS component configuration belongs to another PM package/version",
    )?;
    component_configuration(
        state
            .gms_component_enablement()
            .ok_or("actual GMS PM component configuration is missing")?,
    )
}
fn basis(
    ui: &NativeFamilyUiEvidence,
    permissions: &NativeUiPermissionPreservation,
) -> Result<Value, String> {
    ui.guard_immutable()?;
    let first = ui.stability().transcript();
    let reopened = ui.reopened().transcript();
    let app = first.engine().application();
    let main = &first.engine().facts().main;
    require_application(app)?;
    ui.require_subject(main, app)?;
    permissions.require_subject(main, app)?;
    permissions.require_pair(first, reopened)?;
    let (panel, reopened_panel) = ui.gms_selfcheck_panels()?;
    panel_pair(panel, reopened_panel)?;
    let (before, after) = permissions.gms_permission_observations()?;
    before.require_application(app)?;
    after.require_application(app)?;
    let services = configured_services(before.state())?;
    need(
        services == configured_services(after.state())?,
        "GMS component enablement changed across its actual SelfCheck pair",
    )?;
    let manifest = source()?;
    let enabled = services
        .iter()
        .filter_map(|(name, on)| on.then_some(name))
        .collect::<Vec<_>>();
    let disabled = services
        .iter()
        .filter_map(|(name, on)| (!on).then_some(name))
        .collect::<Vec<_>>();
    // These are hashes of genuine live-owner comparisons, not input receipts.
    // Their actual UI/permission journals stay held by the common case.
    let ui_comparison_sha256 = digest(&ui.comparison()?)?;
    let permission_comparison_sha256 = digest(&permissions.comparison()?)?;
    let result = json!({
        "schema":"droidloom.native-gms-implementation-identity.v1",
        "completed_gates":["gms.identity"],
        "package":app.package,"uid":app.uid,"epoch":app.epoch,
        "actual_application_sha256":digest(app)?,"actual_main_sha256":digest(main)?,
        "implementation":manifest["implementation"],"version_name":manifest["version_name"],
        "version_code":app.version_code,"actual_installed_apk_sha256":app.apks[0].sha256,
        "original_apk_signer_source":manifest["original_signer_certificates_sha256"],
        "signer_binding_basis":"same complete installed APK bytes as the original verified source",
        "manifest_source_sha256":MANIFEST_SHA256,"binary_manifest":manifest["manifest_member"],
        "declared_compatibility_scope":manifest["scope"],
        "declared_service_count":services.len(),"declared_service_intent_action_count":241,
        "enabled_service_components":enabled,"disabled_service_components":disabled,
        "component_enablement_basis":"same selected manifest/resource defaults plus actual user-zero PM overrides",
        "pm_component_before":before.state().gms_component_enablement(),
        "pm_component_after":after.state().gms_component_enablement(),
        "pm_before_stdout_sha256":before.stdout_sha256(),"pm_after_stdout_sha256":after.stdout_sha256(),
        "selfcheck_panel_sha256":digest(panel)?,"selfcheck_row_count":panel.as_array().unwrap().len(),
        "actual_ui_comparison_sha256":ui_comparison_sha256,
        "actual_permission_comparison_sha256":permission_comparison_sha256,
        "normal_owned_two_task_closes_and_same_main_pm_bookends":true,
        "additional_queries":0,"additional_retained_descriptors":0,"additional_window_seconds":0,
        "running_service_process_or_api_success_observed":false,
        "account_count_used_for_acceptance":false,"account_token_push_location_api_accepted":false,
        "integrity_bypass_or_proprietary_google_certification_inferred":false,
        "gms_consumer_and_failure_gates_accepted":false,"comparison_only":true,"production_ready":false
    });
    need(
        serde_json::to_vec(&result)
            .map_err(|e| e.to_string())?
            .len()
            <= 32_768,
        "GMS identity comparison exceeded its fixed existing frame allowance",
    )?;
    Ok(result)
}

/// No file, pidfd, Clone, Deserialize or comparison-input constructor exists.
/// The application case retains and rechecks both original owners whenever
/// this result is used. This object cannot outlive them as proof.
pub struct NativeGmsIdentityEvidence {
    comparison: Value,
}
impl NativeGmsIdentityEvidence {
    pub fn supports(package: &str) -> bool {
        package == PACKAGE
    }
    pub fn completed_gates(&self) -> &'static [&'static str] {
        &["gms.identity"]
    }
    pub fn require_existing_evidence(
        &self,
        ui: &NativeFamilyUiEvidence,
        permissions: &NativeUiPermissionPreservation,
    ) -> Result<(), String> {
        need(
            self.comparison == basis(ui, permissions)?,
            "GMS identity became detached from its actual retained common owners",
        )
    }
    pub fn comparison(
        &self,
        ui: &NativeFamilyUiEvidence,
        permissions: &NativeUiPermissionPreservation,
    ) -> Result<Value, String> {
        self.require_existing_evidence(ui, permissions)?;
        Ok(self.comparison.clone())
    }
}
/// Only genuine common UI/PM owners can enter. No new Android operation runs.
pub fn observe_native_gms_identity(
    ui: &NativeFamilyUiEvidence,
    permissions: &NativeUiPermissionPreservation,
) -> Result<NativeGmsIdentityEvidence, String> {
    Ok(NativeGmsIdentityEvidence {
        comparison: basis(ui, permissions)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn app() -> ApplicationInspection {
        ApplicationInspection {
            package: PACKAGE.into(),
            user: 0,
            uid: 10118,
            version_code: VERSION,
            epoch: crate::control::application_probe::RuntimeEpoch {
                boot_id: "11111111-1111-4111-8111-111111111111".into(),
                cell_host_pid: 11,
                framework_host_pid: 12,
                framework_start_ticks: 13,
            },
            apks: vec![crate::control::application_probe::InstalledApk {
                name: "base.apk".into(),
                path: "/data/app/current-microg/base.apk".into(),
                bytes: APK_BYTES,
                sha256: APK_SHA256.into(),
            }],
        }
    }
    fn config(enabled: &[&str], disabled: &[&str], setting: u8) -> GmsComponentEnablement {
        // Pure parser/comparator fixture. This cannot construct a retained UI,
        // normal permission owner or NativeGmsIdentityEvidence.
        serde_json::from_value(json!({
            "enabled_setting":setting,"hidden":false,"suspended":false,
            "app_lock_enabled":false,"quarantined":false,
            "enabled_components":enabled,"disabled_components":disabled
        }))
        .unwrap()
    }
    #[test]
    fn gms_identity_exact_original_apk_rejects_foreign_user_version_bytes_and_extra_split() {
        let a = app();
        require_application(&a).unwrap();
        for change in 0..7 {
            let mut b = a.clone();
            match change {
                0 => b.package = "org.microg.gms".into(),
                1 => b.user = 10,
                2 => b.version_code -= 1,
                3 => b.apks[0].bytes -= 1,
                4 => b.apks[0].sha256 = "f".repeat(64),
                5 => b.apks[0].name = "split.apk".into(),
                _ => b.apks.push(b.apks[0].clone()),
            }
            assert!(require_application(&b).is_err());
        }
    }
    #[test]
    fn gms_manifest_complete_defaults_keep_literal_and_sdk_resource_disabled_services() {
        let s = source().unwrap();
        let states = component_configuration(&config(&[], &[], 0)).unwrap();
        assert_eq!(states.len(), 122);
        assert_eq!(states.values().filter(|v| **v).count(), 119);
        for name in [
            "org.microg.gms.auth.WorkAccountAuthenticatorService",
            "androidx.camera.core.impl.MetadataHolderService",
            "androidx.work.impl.background.systemalarm.SystemAlarmService",
        ] {
            assert_eq!(states.get(name), Some(&false));
        }
        assert_eq!(
            states["androidx.work.impl.background.systemjob.SystemJobService"],
            true
        );
        assert_eq!(
            s["enabled_resource_resolution"]["@0x7f050003"]["selected_configuration"],
            "v23"
        );
        assert_eq!(
            s["enabled_resource_resolution"]["@0x7f050005"]["resolved_value"],
            true
        );
        assert!(s["scope"].as_str().unwrap().contains("no dependent API"));
    }
    #[test]
    fn gms_identity_requires_enabled_core_but_preserves_explicit_optional_component_choices() {
        let optional = "org.microg.gms.auth.WorkAccountAuthenticatorService";
        let states = component_configuration(&config(&[optional], &[], 0)).unwrap();
        assert_eq!(states[optional], true);
        for name in CORE_COMPONENTS {
            assert!(component_configuration(&config(&[], &[name], 0)).is_err());
        }
        for n in 2..=4 {
            assert!(component_configuration(&config(&[], &[], n)).is_err());
        }
        let conflict = config(&[optional], &[optional], 0);
        assert!(component_configuration(&conflict).is_err());
    }
    #[test]
    fn gms_identity_panel_requires_real_source_id_and_same_nonempty_reopened_rows() {
        let p = json!([{"resource_id":PANEL_ID,"class":"android.widget.TextView",
            "text":"System supports installed implementation","enabled":true}]);
        panel_pair(&p, &p).unwrap();
        for bad in [
            json!([]),
            json!([{"resource_id":PANEL_ID,"text":"","class":"x","enabled":true}]),
            json!([{"resource_id":"org.example:id/self_check_name","text":"passed","class":"x","enabled":true}]),
        ] {
            assert!(panel_pair(&bad, &bad).is_err());
        }
        let mut changed = p.clone();
        changed[0]["text"] = json!("different");
        assert!(panel_pair(&p, &changed).is_err());
        assert!(!NativeGmsIdentityEvidence::supports("org.microg.gms"));
    }
}
