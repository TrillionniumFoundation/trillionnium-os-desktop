//! Complete common assertions derived from live source-owned case factories.
//! Parsing a saved result is insufficient: the callers below require the
//! non-deserializable normal execution object and its original held result FD.
use super::clock_timer::ClockTimerEvidence;
use super::leaf_routes::{LeafObservation, Route};
use super::runtime_identity::IdentityObservation;
use super::*;
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use serde_json::{Value, json};

#[derive(Debug, Serialize)]
pub(super) struct CommonGateFact {
    id: &'static str,
    package: String,
    epoch: RuntimeEpoch,
    basis: Value,
}

impl CommonGateFact {
    pub(super) fn id(&self) -> &'static str {
        self.id
    }
    pub(super) fn require_subject(
        &self,
        package: &str,
        epoch: &RuntimeEpoch,
    ) -> Result<(), String> {
        require(
            self.package == package && &self.epoch == epoch,
            "common fact belongs to a different actual application or Main epoch",
        )
    }
}

fn require(value: bool, reason: &str) -> Result<(), String> {
    if value { Ok(()) } else { Err(reason.into()) }
}

fn fact(
    id: &'static str,
    package: &str,
    main: &RuntimeMainCustody,
    basis: Value,
) -> CommonGateFact {
    CommonGateFact {
        id,
        package: package.into(),
        epoch: main.epoch.clone(),
        basis,
    }
}

fn identity_fact(
    identity: &IdentityObservation,
    package: &str,
    main: &RuntimeMainCustody,
) -> Option<CommonGateFact> {
    identity.complete_identity_gate_passed().then(|| {
        fact(
            "identity",
            package,
            main,
            json!({"factory":"normal_materials_with_opaque_main_and_running_engine",
            "sample_kind":"actual_case_history","freshness_or_data_migration_inferred":false}),
        )
    })
}


/// These two complete common assertions consume an actual finished stability
/// object and a material identity joined to its opaque running Engine. Pixels,
/// account state, independent reopen and business success are separate facts.
pub(super) fn from_stability(
    evidence: &control::NativeUiStabilityEvidence,
    identity: &IdentityObservation,
    main: &RuntimeMainCustody,
    actual: &ApplicationInspection,
) -> Result<Vec<CommonGateFact>, String> {
    identity.require_application(actual)?;
    evidence.require_subject(main, actual)?;
    let identity = identity_fact(identity, &actual.package, main)
        .ok_or("finished family history lacks its complete actual material/Engine identity")?;
    Ok(vec![
        identity,
        fact(
            "stability",
            &actual.package,
            main,
            json!({
                "factory":"normal_native_ui_stability",
                "sample_kind":"actual_case_history",
                "source_owned_window":evidence.summary(),
                "journal":evidence.transcript().journal(),
                "task":evidence.transcript().task(),
                "independent_reopen_inferred":false,
                "data_permissions_or_accounts_inferred":false,
                "whole_application_accepted":false
            }),
        ),
    ])
}

fn distinct_pair(value: &Value) -> bool {
    value
        .as_array()
        .is_some_and(|rows| rows.len() == 2 && rows[0] != rows[1])
}

fn settings_lifecycle(result: &Value) -> Result<Value, String> {
    let scale = &result["setting_roundtrip"];
    require(
        distinct_pair(&result["native_claims"])
            && distinct_pair(&result["recorder_scopes"])
            && result["normally_closed_claims"] == result["native_claims"]
            && result["host_flow_contexts_closed"] == result["recorder_scopes"]
            && result["native_launch_count"] == 2
            && result["normal_closes"]
                .as_array()
                .is_some_and(|rows| rows.len() == 2)
            && result["complete_task_baseline_restored"] == true
            && result["pending_route"].is_null()
            && result["pending_UI"].is_null(),
        "Settings common lifecycle lacks two distinct retired owned tasks or the restored pre-existing task set",
    )?;
    require(
        scale["state"] == "restored_verified"
            && scale["apply_observed"] == true
            && scale["reopen_observed"] == true
            && scale["restore_observed"] == true
            && scale["apply_claim"] == result["native_claims"][0]
            && scale["reopen_claim"] == result["native_claims"][1]
            && scale["provider_writes"] == 2
            && scale["pending_command"].is_null()
            && scale["automatic_write_retry"] == false
            && scale["permission_or_account_write_authorized"] == false,
        "Settings common lifecycle lacks the actual preserved effect across normal close/reopen and exact restore",
    )?;
    Ok(json!({"factory":"settings_v3_actual_font_scale_lifecycle",
        "native_launches":2,"normal_closes":2,
        "same_changed_value_after_separate_reopen":true,
        "original_value_or_absence_restored":true,
        "pre_existing_task_set_restored":true,
        "whole_data_or_account_acceptance_inferred":false}))
}

fn settings_ui(result: &Value, actual_init: u32) -> Result<Value, String> {
    let pages = result["pages"]
        .as_array()
        .ok_or("Settings UI page array missing")?;
    require(
        pages.len() == 5 && result["observation_count"] == 9,
        "Settings common UI lacks the complete fixed page and observation set",
    )?;
    let mut rows = vec![&result["initial_home"]];
    rows.extend(pages);
    rows.extend([
        &result["applied_page"],
        &result["reopened_home"],
        &result["restored_home"],
    ]);
    let mut receipts = BTreeSet::new();
    for row in rows {
        let summary = &row["summary"];
        require(
            summary["android_init_host_pid"].as_u64() == Some(u64::from(actual_init))
                && summary["package"] == "com.android.settings"
                && summary["source"] == "actual-native-tree-and-scoped-PNG"
                && summary["expected_title_observed"] == true
                && summary["visible_control_count"]
                    .as_u64()
                    .is_some_and(|n| (2..=8192).contains(&n))
                && summary["visible_label_count"]
                    .as_u64()
                    .is_some_and(|n| (3..=8192).contains(&n))
                && summary["scoped_pixel_sha256"]
                    .as_str()
                    .is_some_and(crate::release::valid_sha)
                && summary["window_token"]
                    .as_str()
                    .is_some_and(|s| !s.is_empty() && s.len() <= 32),
            "Settings common UI differs from this actual Main, owned window, native controls or scoped pixels",
        )?;
        let recorder = row["recorder_result"]["path"]
            .as_str()
            .ok_or("Settings UI recorder path missing")?;
        require(
            receipts.insert(recorder),
            "Settings common UI repeats an observation receipt",
        )?;
    }
    // The original Settings terminal factory has already checked exact page
    // classes/activities, every full receipt/PNG pin, complete provider/config
    // stdout values and the one reversible input trace. This extra comparison
    // joins its actual window's init PID to this opaque Main, not a saved PID.
    Ok(
        json!({"factory":"settings_v3_actual_native_pages_and_font_scale_readback",
        "fixed_pages":5,"native_tree_and_scoped_png_observations":9,
        "actual_main_init_host_pid":actual_init,
        "provider_and_framework_effect_readback_verified":true,
        "unobserved_permission_or_account_pages_inferred":false}),
    )
}

fn clock_lifecycle(timer: &Value, expiry: &Value) -> Result<Value, String> {
    for result in [timer, expiry] {
        require(
            distinct_pair(&result["owned_tasks"])
                && result["owned_tasks"] == result["closed_tasks"]
                && result["native_launch_calls"] == 2
                && result["normal_remove_calls"] == 2
                && result["task_set_restored"] == true
                && result["owned_task_remaining"].is_null()
                && result["pending"].as_object().is_some_and(|rows| {
                    rows.keys().map(String::as_str).collect::<BTreeSet<_>>()
                        == BTreeSet::from(["close", "effect", "input"])
                        && rows.values().all(Value::is_null)
                })
                && result["alarms_before"].is_object()
                && result["alarms_before"] == result["alarms_after"],
            "Clock common lifecycle lacks its exact closed owned tasks and unchanged pre-existing state",
        )?;
    }
    let phases = &timer["phases"];
    require(
        phases["paused"].is_object()
            && phases["paused"] == phases["paused-stable"]
            && phases["paused"] == phases["after-normal-close"]
            && phases["paused"] == phases["after-reopen"],
        "Clock common lifecycle did not preserve the exact timer through separate normal close/reopen",
    )?;
    Ok(
        json!({"factory":"clock_timer15_and_expiry06_actual_lifecycle",
        "source_owned_cases":2,"native_launches":4,"normal_closes":4,
        "same_paused_timer_after_separate_reopen":true,
        "pre_existing_tasks_and_alarms_restored":true,
        "timezone_audio_soak_or_whole_data_acceptance_inferred":false}),
    )
}

pub(super) fn from_leaf(
    observation: &LeafObservation,
    identity: &IdentityObservation,
) -> Result<Vec<CommonGateFact>, String> {
    observation.retained_bookends()?;
    let main = observation
        .main_observation()
        .ok_or("common leaf facts need actual normal Main custody")?;
    let package = observation.route.package();
    identity.require_application(observation.actual_application()?)?;
    let mut result = identity_fact(identity, package, main.facts())
        .into_iter()
        .collect::<Vec<_>>();
    if observation.route == Route::SettingsSupportedPages
        && observation.verified_business_gates() == ["settings.pages", "settings.roundtrip"]
    {
        let actual = observation.retained_result_value()?;
        result.push(fact(
            "lifecycle",
            package,
            main.facts(),
            settings_lifecycle(&actual)?,
        ));
        result.push(fact(
            "ui_observation",
            package,
            main.facts(),
            settings_ui(&actual, main.facts().epoch.cell_host_pid)?,
        ));
    }
    observation.retained_bookends()?;
    Ok(result)
}

pub(super) fn from_clock(
    observation: &ClockTimerEvidence,
    identity: &IdentityObservation,
) -> Result<Vec<CommonGateFact>, String> {
    observation.retained_bookends()?;
    require(
        observation.verified_business_gates() == ["clock.timer"],
        "common Clock facts need the actual complete timer pair factory",
    )?;
    let main = observation.main_observation();
    let package = "com.android.deskclock";
    identity.require_application(observation.actual_application())?;
    let mut result = identity_fact(identity, package, main.facts())
        .into_iter()
        .collect::<Vec<_>>();
    let (timer, expiry) = observation.retained_case_values()?;
    result.push(fact(
        "lifecycle",
        package,
        main.facts(),
        clock_lifecycle(&timer, &expiry)?,
    ));
    observation.retained_bookends()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn lifecycle() -> Value {
        json!({
            "native_claims":[{"path":"/owned/one"},{"path":"/owned/two"}],
            "recorder_scopes":[{"path":"/scope/one"},{"path":"/scope/two"}],
            "normally_closed_claims":[{"path":"/owned/one"},{"path":"/owned/two"}],
            "host_flow_contexts_closed":[{"path":"/scope/one"},{"path":"/scope/two"}],
            "native_launch_count":2,"normal_closes":[{},{}],
            "complete_task_baseline_restored":true,"pending_route":null,"pending_UI":null,
            "setting_roundtrip":{
                "state":"restored_verified","apply_observed":true,"reopen_observed":true,
                "restore_observed":true,"apply_claim":{"path":"/owned/one"},
                "reopen_claim":{"path":"/owned/two"},"provider_writes":2,
                "pending_command":null,"automatic_write_retry":false,
                "permission_or_account_write_authorized":false
            }
        })
    }
    #[test]
    fn physical_common_lifecycle_requires_distinct_normal_close_reopen_and_restore() {
        // Pure comparisons, not execution objects or opaque gate constructors.
        let baseline = lifecycle();
        settings_lifecycle(&baseline).unwrap();
        let mut changed = baseline.clone();
        changed["native_claims"][1] = changed["native_claims"][0].clone();
        assert!(settings_lifecycle(&changed).is_err());
        let mut changed = baseline.clone();
        changed["normally_closed_claims"]
            .as_array_mut()
            .unwrap()
            .pop();
        assert!(settings_lifecycle(&changed).is_err());
        let mut changed = baseline.clone();
        changed["setting_roundtrip"]["reopen_claim"] = changed["native_claims"][0].clone();
        assert!(settings_lifecycle(&changed).is_err());
        let mut changed = baseline.clone();
        changed["setting_roundtrip"]["restore_observed"] = json!(false);
        assert!(settings_lifecycle(&changed).is_err());
        let mut changed = baseline;
        changed["complete_task_baseline_restored"] = json!(false);
        assert!(settings_lifecycle(&changed).is_err());
    }
    fn observation(index: u32) -> Value {
        json!({"summary":{
            "android_init_host_pid":100,"package":"com.android.settings",
            "source":"actual-native-tree-and-scoped-PNG","expected_title_observed":true,
            "visible_control_count":4,"visible_label_count":6,
            "scoped_pixel_sha256":"a".repeat(64),"window_token":"abcd"
        },"recorder_result":{"path":format!("/observations/{index}/result.json")}})
    }
    #[test]
    fn physical_common_ui_binds_every_native_window_to_the_actual_main() {
        let mut result = json!({"observation_count":9,"initial_home":observation(0),
            "pages":(1..=5).map(observation).collect::<Vec<_>>(),
            "applied_page":observation(6),"reopened_home":observation(7),
            "restored_home":observation(8)});
        settings_ui(&result, 100).unwrap();
        assert!(settings_ui(&result, 101).is_err());
        let original = result.clone();
        result["reopened_home"]["summary"]["android_init_host_pid"] = json!(101);
        assert!(settings_ui(&result, 100).is_err());
        let mut result = original.clone();
        result["restored_home"]["recorder_result"] =
            result["initial_home"]["recorder_result"].clone();
        assert!(settings_ui(&result, 100).is_err());
        let mut result = original;
        result["pages"][2]["summary"]["visible_control_count"] = json!(0);
        assert!(settings_ui(&result, 100).is_err());
    }
    fn clock() -> Value {
        let paused = json!({"ids":[7],"timers":[{"id":7,"state":2,"remaining":456}]});
        json!({"owned_tasks":[20,21],"closed_tasks":[20,21],"native_launch_calls":2,
            "normal_remove_calls":2,"task_set_restored":true,"owned_task_remaining":null,
            "pending":{"close":null,"effect":null,"input":null},
            "alarms_before":{"untouched":"alarm"},"alarms_after":{"untouched":"alarm"},
            "phases":{"paused":paused,"paused-stable":paused,
                "after-normal-close":paused,"after-reopen":paused}})
    }
    #[test]
    fn physical_common_clock_rejects_foreign_close_lost_state_and_unfinished_cleanup() {
        let timer = clock();
        let expiry = clock();
        clock_lifecycle(&timer, &expiry).unwrap();
        let mut changed = timer.clone();
        changed["closed_tasks"] = json!([20, 99]);
        assert!(clock_lifecycle(&changed, &expiry).is_err());
        let mut changed = timer.clone();
        changed["phases"]["after-reopen"]["timers"][0]["id"] = json!(8);
        assert!(clock_lifecycle(&changed, &expiry).is_err());
        let mut changed = expiry.clone();
        changed["alarms_after"] = json!({});
        assert!(clock_lifecycle(&timer, &changed).is_err());
        let mut changed = expiry;
        changed["pending"]["close"] = json!({"task":21});
        assert!(clock_lifecycle(&timer, &changed).is_err());
    }
}
