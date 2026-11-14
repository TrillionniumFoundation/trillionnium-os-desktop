//! Synthetic protocol controls only. No test below launches or qualifies Android.
use super::*;
use application_probe::InstalledApk;
use std::collections::VecDeque;
use std::sync::Mutex;

const BEFORE: &str = "RootTask id=1 bounds=[0,0][800,600] displayId=0 userId=0\n configuration={mWindowingMode=fullscreen}\n taskId=1: com.android.launcher3/.Launcher userId=0 visible=true topActivity=ComponentInfo{com.android.launcher3/.Launcher}\n";
const NEW: &str = "RootTask id=42 bounds=[10,20][610,520] displayId=0 userId=0\n configuration={mWindowingMode=freeform}\n taskId=42: com.android.settings/.Settings userId=0 visible=true topActivity=ComponentInfo{com.android.settings/.homepage.SettingsHomepageActivity}\n";
const FOCUS: &str =
    "mCurrentFocus=Window{ab12 u0 com.android.settings/.homepage.SettingsHomepageActivity}";

struct Step {
    args: Vec<String>,
    result: Result<String, String>,
}
struct Fake {
    epoch: RuntimeEpoch,
    steps: VecDeque<Step>,
    calls: Vec<Vec<String>>,
}
impl AndroidProbe for Fake {
    fn epoch(&mut self) -> Result<RuntimeEpoch, String> {
        Ok(self.epoch.clone())
    }
    fn command(&mut self, argv: &[String]) -> Result<String, String> {
        self.calls.push(argv.to_vec());
        let step = self
            .steps
            .pop_front()
            .expect("unexpected extra command or retry");
        assert_eq!(argv, step.args, "command routing differs");
        step.result
    }
}
impl SettingsProbe for Fake {
    fn command_until(&mut self, argv: &[String], deadline: Instant) -> Result<String, String> {
        within(deadline)?;
        self.command(argv)
    }
}
fn push(steps: &mut VecDeque<Step>, argv: &[&str], result: impl Into<String>) {
    steps.push_back(Step {
        args: args(argv),
        result: Ok(result.into()),
    });
}
fn inspection(
    package: &str,
    uid: u32,
    helper: bool,
    epoch: &RuntimeEpoch,
) -> ApplicationInspection {
    ApplicationInspection {
        package: package.into(),
        user: 0,
        uid,
        version_code: if helper { 2 } else { 35 },
        epoch: epoch.clone(),
        apks: vec![InstalledApk {
            name: "base.apk".into(),
            path: if helper {
                "/data/app/unit-helper/base.apk"
            } else {
                "/system/priv-app/Settings/Settings.apk"
            }
            .into(),
            bytes: if helper { HELPER_BYTES } else { 3000 },
            sha256: if helper {
                HELPER_SHA.into()
            } else {
                "a".repeat(64)
            },
        }],
    }
}
fn push_inspection(steps: &mut VecDeque<Step>, identity: &ApplicationInspection) {
    let package = format!(
        "package:{} versionCode:{} uid:{}",
        identity.package, identity.version_code, identity.uid
    );
    let paths = format!("package:{}", identity.apks[0].path);
    let apk = &identity.apks[0];
    let metadata = format!("1:2:{}:unit-time:unit-ctime", apk.bytes);
    let p = &identity.package;
    let path = &apk.path;
    push(
        steps,
        &[
            "/system/bin/cmd",
            "package",
            "list",
            "packages",
            "--user",
            "0",
            "-U",
            "--show-versioncode",
            p,
        ],
        &package,
    );
    push(
        steps,
        &["/system/bin/cmd", "package", "path", "--user", "0", p],
        &paths,
    );
    push(
        steps,
        &["/system/bin/toybox", "stat", "-c", "%d:%i:%s:%y:%z", path],
        &metadata,
    );
    push(
        steps,
        &["/system/bin/toybox", "sha256sum", path],
        format!("{}  {path}", apk.sha256),
    );
    push(
        steps,
        &["/system/bin/toybox", "stat", "-c", "%d:%i:%s:%y:%z", path],
        &metadata,
    );
    push(
        steps,
        &[
            "/system/bin/cmd",
            "package",
            "list",
            "packages",
            "--user",
            "0",
            "-U",
            "--show-versioncode",
            p,
        ],
        &package,
    );
    push(
        steps,
        &["/system/bin/cmd", "package", "path", "--user", "0", p],
        &paths,
    );
}
fn encode(raw: &[u8]) -> String {
    const ALPHABET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    let mut bits = 0u32;
    let mut n = 0;
    for byte in raw {
        bits = (bits << 8) | u32::from(*byte);
        n += 8;
        while n >= 6 {
            n -= 6;
            out.push(char::from(ALPHABET[((bits >> n) & 63) as usize]));
        }
    }
    if n > 0 {
        out.push(char::from(ALPHABET[((bits << (6 - n)) & 63) as usize]));
    }
    while out.len() % 4 != 0 {
        out.push('=');
    }
    out
}
fn tree() -> serde_json::Value {
    let root = serde_json::json!({"present":true,"package":SETTINGS,"window_id":7,"bounds":[10,20,610,520],"visible":true});
    serde_json::json!({"ok":true,"accessibility_mode_restoration_verified":true,
        "window_context":{"selected_window":{"display_id":0,"focused":true,"type":1,"window_id":7,
            "bounds":[10,20,610,520],"root":root},"root":root,
            "snapshot_complete":true,"semantic_controls_available":true,"truncated":false,
            "null_child_count":0,"visited_count":1,"visible_count":1,"tree_status":"available"},
        "nodes":[{"package":SETTINGS,"window_id":7,"visible":true,"source":"native_accessibility","bounds_array":[10,20,610,520]}]})
}
fn instrument(value: &serde_json::Value) -> String {
    format!(
        "INSTRUMENTATION_RESULT: sidecar_result_base64={}\nINSTRUMENTATION_CODE: -1",
        encode(&serde_json::to_vec(value).unwrap())
    )
}
fn after() -> String {
    format!("{BEFORE}{NEW}")
}
fn cleanup(steps: &mut VecDeque<Step>) {
    push(
        steps,
        &["/system/bin/cmd", "activity", "stack", "list"],
        after(),
    );
    push(
        steps,
        &["/system/bin/cmd", "activity", "stack", "remove", "42"],
        "",
    );
    push(
        steps,
        &["/system/bin/cmd", "activity", "stack", "list"],
        BEFORE,
    );
}
fn fixture(helper_uid: u32) -> (Fake, ApplicationInspection) {
    let epoch = RuntimeEpoch {
        boot_id: "unit-test-only".into(),
        cell_host_pid: 10,
        framework_host_pid: 20,
        framework_start_ticks: 30,
    };
    let settings = inspection(SETTINGS, 1000, false, &epoch);
    let helper = inspection(HELPER, helper_uid, true, &epoch);
    let mut q = VecDeque::new();
    push_inspection(&mut q, &settings);
    push_inspection(&mut q, &helper);
    push(
        &mut q,
        &[LAUNCHER, "--settings-observation-protocol"],
        "droidloom-settings-observation-v1",
    );
    push(
        &mut q,
        &[
            "/system/bin/cmd",
            "package",
            "resolve-activity",
            "--brief",
            "--user",
            "0",
            "-a",
            "android.settings.SETTINGS",
        ],
        "com.android.settings/.Settings",
    );
    push(
        &mut q,
        &["/system/bin/cmd", "activity", "stack", "list"],
        BEFORE,
    );
    push(
        &mut q,
        &[
            LAUNCHER,
            "--observe-settings-page",
            "android.settings.SETTINGS",
            "--user",
            "0",
            "--component",
            "com.android.settings/com.android.settings.Settings",
            SETTINGS,
        ],
        "object=50 composer_display=60 android_display=0 task=42",
    );
    push(
        &mut q,
        &["/system/bin/cmd", "activity", "stack", "list"],
        after(),
    );
    push_inspection(&mut q, &helper);
    push(
        &mut q,
        &["/system/bin/dumpsys", "window", "displays"],
        FOCUS,
    );
    push(
        &mut q,
        &[
            "/system/bin/am",
            "instrument",
            "-w",
            "-r",
            "-e",
            "request",
            DUMP_REQUEST,
            "local.pocket4.actions.v2/.ActionRunner",
        ],
        instrument(&tree()),
    );
    push(
        &mut q,
        &["/system/bin/dumpsys", "window", "displays"],
        FOCUS,
    );
    push(
        &mut q,
        &["/system/bin/cmd", "activity", "stack", "list"],
        after(),
    );
    push_inspection(&mut q, &settings);
    push_inspection(&mut q, &helper);
    cleanup(&mut q);
    (
        Fake {
            epoch,
            steps: q,
            calls: Vec::new(),
        },
        settings,
    )
}
fn launch_index(fake: &Fake) -> usize {
    fake.steps
        .iter()
        .position(|s| {
            s.args
                .get(1)
                .is_some_and(|s| s == "--observe-settings-page")
        })
        .unwrap()
}
fn native_index(fake: &Fake) -> usize {
    fake.steps
        .iter()
        .position(|s| s.args.first().is_some_and(|s| s == "/system/bin/am"))
        .unwrap()
}
fn count_launches(fake: &Fake) -> usize {
    fake.calls
        .iter()
        .filter(|a| a.get(1).is_some_and(|s| s == "--observe-settings-page"))
        .count()
}
fn count_removes(fake: &Fake) -> usize {
    fake.calls
        .iter()
        .filter(|a| a.get(3).is_some_and(|s| s == "remove"))
        .count()
}
fn perform(fake: &mut Fake, expected: &ApplicationInspection) -> (SettingsObservation, bool) {
    let directory = tempfile::tempdir().unwrap();
    let retained = Mutex::new(None);
    let scope = ActionScope::acquire_in(directory.path(), &retained).unwrap();
    let report = observe_with_scope(
        fake,
        expected,
        SettingsPage::System,
        Instant::now() + Duration::from_secs(90),
        scope,
    )
    .unwrap();
    let held = retained.lock().unwrap().is_some();
    assert_eq!(report.action_scope_retained, held);
    (report, held)
}

#[test]
fn synthetic_page_candidate_fixture_never_grants_framework_creation_authority() {
    for helper_uid in [10125, 10987] {
        let (mut fake, expected) = fixture(helper_uid);
        let (report, held) = perform(&mut fake, &expected);
        assert!(!report.completed_partial());
        assert!(!held);
        assert!(fake.steps.is_empty());
        assert_eq!(count_launches(&fake), 1);
        assert_eq!(count_removes(&fake), 1);
        assert_eq!(report.helper_inspection.uid, helper_uid);
        assert_eq!(report.task_candidate.unwrap().id, 42);
        let window = report.window.unwrap();
        assert_eq!(window.focus.token, "ab12");
        assert_eq!(window.visible_nodes, 1);
        assert!(
            !window.pixel_observation_verified
                && !report.production_ready
                && !report.runtime_qualified
        );
        assert_eq!(report.accepted_gates, 0);
    }
}

#[test]
fn old_vendor_or_preexisting_settings_fails_before_start_and_leaves_no_intent() {
    for old_vendor in [true, false] {
        let (mut fake, expected) = fixture(10237);
        let i = launch_index(&fake);
        if old_vendor {
            fake.steps[14].result = Err("unknown option".into());
        } else {
            fake.steps[i - 1].result = Ok(after());
        }
        let directory = tempfile::tempdir().unwrap();
        let retained = Mutex::new(None);
        let scope = ActionScope::acquire_in(directory.path(), &retained).unwrap();
        assert!(
            observe_with_scope(
                &mut fake,
                &expected,
                SettingsPage::System,
                Instant::now() + Duration::from_secs(90),
                scope
            )
            .is_err()
        );
        assert_eq!(count_launches(&fake), 0);
        assert!(retained.lock().unwrap().is_none());
        assert!(ActionScope::acquire_in(directory.path(), &retained).is_ok());
    }
}

#[test]
fn wrong_native_helper_bytes_never_execute_instrumentation_or_start_a_page() {
    let (mut fake, expected) = fixture(10237);
    fake.steps[10].result = Ok(format!(
        "{}  /data/app/unit-helper/base.apk",
        "b".repeat(64)
    ));
    let d = tempfile::tempdir().unwrap();
    let r = Mutex::new(None);
    let scope = ActionScope::acquire_in(d.path(), &r).unwrap();
    assert!(
        observe_with_scope(
            &mut fake,
            &expected,
            SettingsPage::System,
            Instant::now() + Duration::from_secs(90),
            scope
        )
        .is_err()
    );
    assert_eq!(count_launches(&fake), 0);
    assert_eq!(fake.calls.len(), 14);
    assert!(r.lock().unwrap().is_none());
}

#[test]
fn uncertain_single_launch_retains_scope_and_sends_no_followup_or_removal() {
    let (mut fake, expected) = fixture(10237);
    let i = launch_index(&fake);
    fake.steps[i].result = Err("fixture transport deadline: outcome unknown".into());
    let (report, held) = perform(&mut fake, &expected);
    assert!(held);
    assert!(report.failure.unwrap().contains("outcome unknown"));
    assert_eq!(fake.calls.len(), i + 1);
    assert_eq!(count_launches(&fake), 1);
    assert_eq!(count_removes(&fake), 0);
}

#[test]
fn ack_cannot_authorize_an_old_task_or_a_task_missing_from_the_actual_snapshot() {
    for id in [1, 43] {
        let (mut fake, expected) = fixture(10237);
        let i = launch_index(&fake);
        fake.steps[i].result = Ok(format!(
            "object=50 composer_display=60 android_display=0 task={id}"
        ));
        let (report, held) = perform(&mut fake, &expected);
        assert!(held);
        assert!(report.task_candidate.is_none());
        assert_eq!(count_removes(&fake), 0);
        assert_eq!(fake.calls.len(), i + 2);
    }
}

#[test]
fn a_settled_foreign_native_node_is_rejected_and_only_the_owned_leaf_is_cleaned() {
    let (mut fake, expected) = fixture(10237);
    let i = native_index(&fake);
    let mut value = tree();
    value["nodes"][0]["package"] = "org.example.foreign".into();
    fake.steps[i].result = Ok(instrument(&value));
    fake.steps.truncate(i + 1);
    cleanup(&mut fake.steps);
    let (report, held) = perform(&mut fake, &expected);
    assert!(!held);
    assert!(report.cleanup_confirmed);
    assert!(report.failure.unwrap().contains("outside"));
    assert!(report.window.is_none());
    assert_eq!(count_removes(&fake), 1);
    assert!(fake.steps.is_empty());
}

#[test]
fn missing_restoration_or_unknown_instrumentation_keeps_the_action_scope() {
    for timeout in [true, false] {
        let (mut fake, expected) = fixture(10237);
        let i = native_index(&fake);
        let mut value = tree();
        value["accessibility_mode_restoration_verified"] = false.into();
        fake.steps[i].result = if timeout {
            Err("native invocation timeout".into())
        } else {
            Ok(instrument(&value))
        };
        let (report, held) = perform(&mut fake, &expected);
        assert!(held);
        assert!(!report.cleanup_confirmed);
        assert_eq!(fake.calls.len(), i + 1);
        assert_eq!(count_removes(&fake), 0);
    }
}

#[test]
fn duplicate_restoration_claim_is_not_accepted_as_a_settled_result() {
    let (mut fake, expected) = fixture(10237);
    let i = native_index(&fake);
    let json = "{\"ok\":true,\"accessibility_mode_restoration_verified\":false,\"accessibility_mode_restoration_verified\":true}";
    fake.steps[i].result = Ok(format!(
        "INSTRUMENTATION_RESULT: sidecar_result_base64={}",
        encode(json.as_bytes())
    ));
    let (report, held) = perform(&mut fake, &expected);
    assert!(held);
    assert!(report.failure.is_some());
    assert_eq!(count_removes(&fake), 0);
    assert_eq!(fake.calls.len(), i + 1);
}

#[test]
fn window_token_change_invalidates_observation_but_does_not_adopt_another_task() {
    let (mut fake, expected) = fixture(10237);
    let i = native_index(&fake);
    fake.steps[i + 1].result = Ok(FOCUS.replace("ab12", "ab13"));
    fake.steps.truncate(i + 2);
    cleanup(&mut fake.steps);
    let (report, held) = perform(&mut fake, &expected);
    assert!(!held);
    assert!(report.cleanup_confirmed);
    assert!(report.failure.unwrap().contains("focus token"));
    assert!(report.window.is_none());
    assert_eq!(count_removes(&fake), 1);
}

#[test]
fn changed_task_topology_before_cleanup_prevents_the_removal_command() {
    let (mut fake, expected) = fixture(10237);
    let i = fake.steps.len() - 3;
    fake.steps[i].result = Ok(after().replace("taskId=1:", "taskId=99:"));
    let (report, held) = perform(&mut fake, &expected);
    assert!(held);
    assert!(!report.cleanup_confirmed);
    assert_eq!(count_removes(&fake), 0);
    assert_eq!(fake.calls.len(), i + 1);
}

#[test]
fn an_uncertain_removal_is_sent_exactly_once_and_never_retried() {
    let (mut fake, expected) = fixture(10237);
    let i = fake.steps.len() - 2;
    fake.steps[i].result = Err("remove outcome unknown".into());
    let (report, held) = perform(&mut fake, &expected);
    assert!(held);
    assert!(!report.cleanup_confirmed);
    assert_eq!(count_removes(&fake), 1);
    assert_eq!(fake.calls.len(), i + 1);
}

#[test]
fn expired_lease_sends_no_commands_and_creates_no_pending_intent() {
    let (mut fake, expected) = fixture(10237);
    let d = tempfile::tempdir().unwrap();
    let r = Mutex::new(None);
    let scope = ActionScope::acquire_in(d.path(), &r).unwrap();
    assert!(
        observe_with_scope(
            &mut fake,
            &expected,
            SettingsPage::System,
            Instant::now(),
            scope
        )
        .is_err()
    );
    assert!(fake.calls.is_empty());
    assert!(r.lock().unwrap().is_none());
    assert!(ActionScope::acquire_in(d.path(), &r).is_ok());
}

#[test]
fn native_nodes_require_complete_same_window_visible_in_bounds_original_source() {
    let tasks = Tasks::parse(&after()).unwrap();
    let owned = tasks
        .candidate_after(&Tasks::parse(BEFORE).unwrap(), 42)
        .unwrap();
    let focus = protocol::focus(FOCUS, &owned).unwrap();
    for change in 0..7 {
        let mut value = tree();
        match change {
            0 => value["nodes"][0]["window_id"] = 8.into(),
            1 => value["nodes"][0]["bounds_array"] = serde_json::json!([0, 0, 800, 600]),
            2 => value["nodes"][0]["source"] = "synthetic".into(),
            3 => value["window_context"]["snapshot_complete"] = false.into(),
            4 => value["window_context"]["selected_window"]["focused"] = false.into(),
            5 => value["window_context"]["root"]["window_id"] = 8.into(),
            _ => value["window_context"]["visible_count"] = 2.into(),
        }
        assert!(
            protocol::validate_dump(value.to_string(), &owned, focus.clone()).is_err(),
            "mutation {change}"
        );
    }
    let (_, raw) = protocol::native_dump(&instrument(&tree())).unwrap();
    assert!(protocol::validate_dump(raw, &owned, focus).is_ok());
}

#[test]
fn production_settings_admission_cannot_accept_a_declared_identity() {
    let (_, expected) = fixture(10237);
    // The production daemon calls this admission before constructing a probe;
    // a JSON identity cannot grant Android observation or task-creation power.
    let error = observe(&expected, SettingsPage::System).unwrap_err();
    assert_eq!(error, FRAMEWORK_AUTHORITY_BLOCKER);
}
