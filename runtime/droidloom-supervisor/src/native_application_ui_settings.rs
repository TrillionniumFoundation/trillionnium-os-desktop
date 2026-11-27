//! Fixed Settings permission/account/negative-lookup flow on an actual owned task.
//!
//! Only run_settings_permission_case can construct the completed observation.
//! It borrows real Main/PM/data custody, uses the original seven-FD UI runner,
//! and follows Settings' own permission preference into PermissionController.
//! The companion's selected APK, actual PM UID, window token and original task
//! must all agree. No permission/account mutation or caller intent is exposed.
use super::*;
use crate::control::{
    ActualApplicationPermissionObservation, application_probe::ApplicationInspection,
};

const SETTINGS: &str = "com.android.settings";
const COMPANION: &str = "com.android.permissioncontroller";
const SETTINGS_BYTES: u64 = 91_609_273;
const SETTINGS_SHA: &str = "c2d4c45348dd45483f0893c6236ffb29322a52d2db61f83936be1508bd03a090";
const COMPANION_BYTES: u64 = 27_340_349;
const COMPANION_SHA: &str = "b0186fc4a5b89f8e5aa4ee5d938a82e5222c7ebaf57e94ff27f9da81ceb63673";
const SEARCH: &str = "droidloom_no_matching_application_4b91";
const APPS_LIST: &str = "com.android.settings:id/apps_list";
const SEARCH_MENU: &str = "com.android.settings:id/search_app_list_menu";
const MAX_WINDOW_BYTES: usize = 2 * 1024 * 1024;
const PAGE_COUNT: usize = 7;
const PAGE_READS: usize = 3;
const OPEN_SECONDS: u64 = 250 + 3 * 15 + 250 + 250 + 2 * 15 + 70;
const FINISH_SECONDS: u64 = 250 + 70 + 250 + 70 + 60;
const POST_SECONDS: u64 = 250 + 70;
const POLL_GAP: Duration = Duration::from_secs(1);

/// An allowance, never a new deadline. The caller supplies the one original end.
/// Seven pages have at most three complete read-only snapshots. Each snapshot
/// uses two task lists, two bounded WM reads and one actual helper dump.
/// Four fixed in-task Settings navigations, one exact Back, two clicks and two
/// find+set-text operations are counted separately. Initial target PM is owned
/// by the dispatcher and is not hidden in this function.
pub fn settings_permission_case_window_seconds() -> u64 {
    OPEN_SECONDS
        + FINISH_SECONDS
        + 2 * 250
        + 2 * 70
        + PAGE_COUNT as u64 * PAGE_READS as u64 * (2 * 15 + 2 * 15 + 70)
        + 4 * (2 * 15 + 30)
        + (2 * 15 + 4 * 15 + 15)
        + 2 * (2 * 15 + 70)
        + 2 * 2 * (2 * 15 + 70)
        + 20
        + 120
}

fn require_window(now: Instant, end: Instant, baseline_end: Instant) -> Result<Instant, String> {
    need(
        now < end
            && end <= baseline_end
            && end.duration_since(now)
                <= Duration::from_secs(settings_permission_case_window_seconds()),
        "Settings requires its existing source-bounded case deadline",
    )?;
    end.checked_sub(Duration::from_secs(POST_SECONDS))
        .filter(|e| *e > now)
        .ok_or_else(|| {
            "Settings original deadline cannot cover companion/permission post observations".into()
        })
}

fn selected_settings(actual: &ApplicationInspection) -> Result<(), String> {
    need(
        actual.package == SETTINGS
            && actual.user == 0
            && actual.uid == 1000
            && actual.version_code == 37
            && actual.apks.len() == 1
            && actual.apks[0].name == "base.apk"
            && actual.apks[0].bytes == SETTINGS_BYTES
            && actual.apks[0].sha256 == SETTINGS_SHA,
        "Settings actual complete APK differs from the selected interface source",
    )
}
fn selected_companion(
    actual: &ApplicationInspection,
    target: &ApplicationInspection,
) -> Result<(), String> {
    need(
        actual.package == COMPANION
            && actual.user == 0
            && actual.uid >= 1000
            && actual.uid < 100_000
            && actual.epoch == target.epoch
            && actual.version_code == 330_000_000
            && actual.apks.len() == 1
            && actual.apks[0].name == "base.apk"
            && actual.apks[0].bytes == COMPANION_BYTES
            && actual.apks[0].sha256 == COMPANION_SHA,
        "PermissionController is not the actual selected complete same-epoch companion",
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum Page {
    AppInfo,
    Permissions,
    Accounts,
    AppsBefore,
    EmptyLookup,
    AppsRestored,
    Home,
}
const PAGES: [Page; PAGE_COUNT] = [
    Page::AppInfo,
    Page::Permissions,
    Page::Accounts,
    Page::AppsBefore,
    Page::EmptyLookup,
    Page::AppsRestored,
    Page::Home,
];
impl Page {
    fn package(self) -> &'static str {
        if self == Self::Permissions {
            COMPANION
        } else {
            SETTINGS
        }
    }
    fn accepts_component(self, component: &str) -> bool {
        match self {
            Self::AppInfo => matches!(
                component,
                "com.android.settings/com.android.settings.applications.InstalledAppDetailsTop"
                    | "com.android.settings/com.android.settings.spa.SpaActivity"
            ),
            Self::Permissions => {
                component
                    == "com.android.permissioncontroller/com.android.permissioncontroller.permission.ui.ManagePermissionsActivity"
            }
            Self::Accounts => {
                component
                    == "com.android.settings/com.android.settings.Settings$AccountDashboardActivity"
            }
            Self::AppsBefore | Self::EmptyLookup | Self::AppsRestored => {
                component
                    == "com.android.settings/com.android.settings.Settings$ManageApplicationsActivity"
            }
            Self::Home => matches!(
                component,
                "com.android.settings/com.android.settings.homepage.SettingsHomepageActivity"
                    | "com.android.settings/com.android.settings.Settings"
            ),
        }
    }
}

#[derive(Debug, Eq, PartialEq, Serialize)]
struct Window {
    token: String,
    component: String,
    uid: u32,
    task: u32,
    display: u32,
}
fn number(value: &str) -> Result<u32, String> {
    let n = value
        .parse::<u32>()
        .map_err(|_| "Settings window integer malformed")?;
    need(
        n.to_string() == value && n <= i32::MAX as u32,
        "Settings window integer noncanonical",
    )?;
    Ok(n)
}
fn component(value: &str) -> Result<String, String> {
    crate::control::validate_component(value).map_err(|e| e.to_string())?;
    let (p, a) = value
        .split_once('/')
        .ok_or("Settings window component absent")?;
    Ok(format!(
        "{p}/{}",
        if a.starts_with('.') {
            format!("{p}{a}")
        } else {
            a.into()
        }
    ))
}
fn window_identity(value: &str) -> Result<(String, String), String> {
    let body = value
        .strip_prefix("Window{")
        .and_then(|v| v.strip_suffix('}'))
        .ok_or("Settings actual WM window delimiters differ")?;
    let fields = body.split_ascii_whitespace().collect::<Vec<_>>();
    need(
        fields.len() == 3
            && fields[1] == "u0"
            && !fields[0].is_empty()
            && fields[0].len() <= 32
            && fields[0]
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "Settings actual WM focus has foreign user or malformed identity",
    )?;
    Ok((fields[0].into(), component(fields[2])?))
}
fn one_field<'a>(lines: &[&'a str], name: &str) -> Result<&'a str, String> {
    let values = lines
        .iter()
        .flat_map(|l| l.split_ascii_whitespace())
        .filter_map(|s| s.strip_prefix(name))
        .collect::<Vec<_>>();
    need(
        values.len() == 1,
        "Settings actual WM field is missing or duplicated",
    )?;
    Ok(values[0])
}

/// Selected WindowState.dump prints mDisplayId/taskId on one line and
/// mOwnerUid/package on another. Neither a package name nor a focus token alone
/// authorizes a companion window. Unknown or incomplete actual output fails.
fn parse_window(raw: &[u8], page: Page, uid: u32, task: u32) -> Result<Window, String> {
    need(
        !raw.is_empty()
            && raw.len() <= MAX_WINDOW_BYTES
            && raw.ends_with(b"\n")
            && !raw
                .iter()
                .any(|b| b.is_ascii_control() && !b"\n\r\t".contains(b)),
        "Settings complete WM output bound differs",
    )?;
    let text = std::str::from_utf8(raw).map_err(|_| "Settings WM is not UTF-8")?;
    let lines = text.lines().collect::<Vec<_>>();
    need(lines.len() <= 32_768, "Settings WM line count exceeded")?;
    let mut focuses = BTreeSet::new();
    for line in &lines {
        if let Some(rest) = line.trim().strip_prefix("mCurrentFocus=") {
            // The selected product has only display zero. Null or a foreign
            // display focus is not silently dropped to obtain one target.
            focuses.insert(window_identity(rest)?);
        }
    }
    need(
        focuses.len() == 1,
        "Settings actual current focus is absent or ambiguous",
    )?;
    let (token, actual_component) = focuses.into_iter().next().unwrap();
    need(
        page.accepts_component(&actual_component),
        "Settings actual focus is not the fixed page or selected companion",
    )?;
    let mut block = None;
    for (i, line) in lines.iter().enumerate() {
        let Some(rest) = line.trim().strip_prefix("Window #") else {
            continue;
        };
        let Some((index, value)) = rest.split_once(' ') else {
            continue;
        };
        number(index)?;
        let Some(value) = value.strip_suffix(':') else {
            continue;
        };
        let found = window_identity(value)?;
        if found.0 != token {
            continue;
        }
        need(
            found.1 == actual_component && block.is_none(),
            "Settings focused window block is duplicated or mismatched",
        )?;
        let indent = line.len() - line.trim_start().len();
        let stop = (i + 1..lines.len())
            .find(|j| {
                !lines[*j].trim().is_empty()
                    && lines[*j].len() - lines[*j].trim_start().len() <= indent
            })
            .unwrap_or(lines.len());
        block = Some(&lines[i + 1..stop]);
    }
    let block = block.ok_or("Settings focused window's full owner/task block is absent")?;
    need(
        number(one_field(block, "mDisplayId=")?)? == 0
            && number(one_field(block, "taskId=")?)? == task
            && number(one_field(block, "mOwnerUid=")?)? == uid
            && one_field(block, "package=")? == page.package()
            && one_field(block, "mViewVisibility=")? == "0x0"
            && one_field(block, "mHasSurface=")? == "true"
            && one_field(block, "isReadyForDisplay()=")? == "true",
        "Settings focused window is not visible in the actual UID and original owned task",
    )?;
    Ok(Window {
        token,
        component: actual_component,
        uid,
        task,
        display: 0,
    })
}

fn nodes(body: &Value) -> Result<&[Value], String> {
    body["nodes"]
        .as_array()
        .filter(|v| !v.is_empty() && v.len() <= 2000)
        .map(Vec::as_slice)
        .ok_or_else(|| "Settings complete native node list absent".into())
}
fn text_count(nodes: &[Value], text: &str) -> usize {
    nodes
        .iter()
        .filter(|n| n["visible"] == true && n["text"] == text)
        .count()
}
fn bounds(node: &Value) -> Option<[i64; 4]> {
    let v = node["bounds_array"].as_array().filter(|v| v.len() == 4)?;
    let out = [
        v[0].as_i64()?,
        v[1].as_i64()?,
        v[2].as_i64()?,
        v[3].as_i64()?,
    ];
    (out[2] > out[0] && out[3] > out[1]).then_some(out)
}
fn apps_rows(nodes: &[Value]) -> Result<usize, String> {
    let lists = nodes
        .iter()
        .filter(|n| n["resource-id"] == APPS_LIST && n["visible"] == true)
        .collect::<Vec<_>>();
    need(
        lists.len() == 1,
        "Settings actual mounted applications list is absent or ambiguous",
    )?;
    let rect = bounds(lists[0]).ok_or("Settings actual applications list bounds absent")?;
    Ok(nodes
        .iter()
        .filter(|n| {
            n["visible"] == true
                && n["editable"] == false
                && n["resource-id"] != APPS_LIST
                && n["class"].as_str().is_some_and(|v| v.ends_with("TextView"))
                && n["text"].as_str().is_some_and(|v| !v.is_empty())
                && bounds(n).is_some_and(|b| {
                    b[0] >= rect[0] && b[1] >= rect[1] && b[2] <= rect[2] && b[3] <= rect[3]
                })
        })
        .count())
}
fn query_is(nodes: &[Value], value: &str) -> bool {
    let editable = nodes
        .iter()
        .filter(|n| {
            n["visible"] == true
                && n["editable"] == true
                && n["enabled"] == true
                && n["password"] == false
        })
        .collect::<Vec<_>>();
    editable.len() == 1 && editable[0]["text"] == value
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
enum Feedback {
    Page,
    NoMatchingAppsText,
    CompleteEmptyApplicationsList,
}
fn page_semantics(page: Page, body: &Value) -> Result<Feedback, String> {
    let n = nodes(body)?;
    need(
        n.iter().all(|v| v["package"] == page.package()),
        "Settings complete semantic tree contains a foreign package",
    )?;
    match page {
        Page::AppInfo => need(
            text_count(n, "Settings") > 0 && text_count(n, "Permissions") == 1,
            "Settings own app-info/permission preference is not visible",
        )?,
        Page::Permissions => need(
            text_count(n, "Settings") > 0
                && text_count(n, "App permissions") > 0
                && (text_count(n, "Allowed") > 0 || text_count(n, "Not allowed") > 0),
            "actual selected companion did not show Settings' permission groups",
        )?,
        Page::Accounts => need(
            (text_count(n, "Passwords & accounts") > 0
                || text_count(n, "Passwords, passkeys & accounts") > 0)
                && text_count(n, "Add account") == 1,
            "actual readonly account dashboard and its interface are not visible",
        )?,
        Page::AppsBefore => need(
            apps_rows(n)? > 0
                && text_count(n, "No matching apps") == 0
                && n.iter()
                    .filter(|v| {
                        v["resource-id"] == SEARCH_MENU
                            && v["visible"] == true
                            && v["enabled"] == true
                    })
                    .count()
                    == 1,
            "Settings application list/search affordance is not ready",
        )?,
        Page::EmptyLookup => {
            need(
                query_is(n, SEARCH),
                "Settings actual query readback differs",
            )?;
            if n.iter()
                .filter(|v| {
                    v["visible"] == true
                        && v["resource-id"] == "android:id/empty"
                        && v["text"] == "No matching apps"
                })
                .count()
                == 1
            {
                need(
                    n.iter()
                        .all(|v| v["resource-id"] != APPS_LIST || v["visible"] != true),
                    "Settings empty message conflicts with an actual visible applications list",
                )?;
                return Ok(Feedback::NoMatchingAppsText);
            }
            need(
                text_count(n, "No matching apps") == 0 && apps_rows(n)? == 0,
                "Settings negative lookup lacks a complete visible empty result",
            )?;
            return Ok(Feedback::CompleteEmptyApplicationsList);
        }
        Page::AppsRestored => need(
            query_is(n, "") && apps_rows(n)? > 0 && text_count(n, "No matching apps") == 0,
            "Settings original empty query/nonempty applications view did not return",
        )?,
        Page::Home => need(
            text_count(n, "Settings") > 0,
            "Settings normal home did not return",
        )?,
    }
    Ok(Feedback::Page)
}
#[derive(Debug, Serialize)]
struct PageEvidence {
    page: Page,
    window: Window,
    query_stdout_sha256: String,
    window_before_sha256: String,
    window_after_sha256: String,
    node_count: usize,
    attempts: usize,
    feedback: Feedback,
}
#[derive(Clone, Copy)]
enum Destination {
    AppInfo,
    Accounts,
    Apps,
    Home,
}
fn navigation(task: u32, dest: Destination) -> Vec<String> {
    let (activity, action, data) = match dest {
        Destination::AppInfo => (
            "com.android.settings.applications.InstalledAppDetails",
            "android.settings.APPLICATION_DETAILS_SETTINGS",
            Some("package:com.android.settings"),
        ),
        Destination::Accounts => (
            "com.android.settings.Settings$AccountDashboardActivity",
            "android.intent.action.MAIN",
            None,
        ),
        Destination::Apps => (
            "com.android.settings.Settings$ManageApplicationsActivity",
            "android.settings.MANAGE_APPLICATIONS_SETTINGS",
            None,
        ),
        Destination::Home => (
            "com.android.settings.Settings",
            "android.intent.action.MAIN",
            None,
        ),
    };
    let mut argv = vec![
        "/system/bin/cmd".into(),
        "activity".into(),
        "start-activity".into(),
        "-W".into(),
        "--user".into(),
        "0".into(),
        "--display".into(),
        "0".into(),
        "--task".into(),
        task.to_string(),
        "-a".into(),
        action.into(),
        "-n".into(),
        format!("{SETTINGS}/{activity}"),
    ];
    if let Some(data) = data {
        argv.extend(["-d".into(), data.into()]);
    }
    argv
}
fn started(raw: &[u8]) -> Result<(), String> {
    need(
        raw.len() <= 65_536 && raw.ends_with(b"\n"),
        "Settings activity result bound",
    )?;
    let s = std::str::from_utf8(raw).map_err(|_| "Settings activity result UTF-8")?;
    let lines = s.lines().map(str::trim).collect::<Vec<_>>();
    need(
        lines.iter().filter(|v| **v == "Status: ok").count() == 1
            && lines.iter().filter(|v| **v == "Complete").count() == 1
            && !lines.iter().any(|l| {
                [
                    "Error:",
                    "Exception",
                    "Permission Denial:",
                    "Status: timeout",
                ]
                .iter()
                .any(|p| l.starts_with(p))
            }),
        "Settings fixed activity did not complete normally",
    )
}

// Selected RootWindowContainer root-task names use origActivity/realActivity
// before their top-activity fallback. The original Settings root remains exact;
// the companion is separately bound by actual PM and the WM task/UID/token.
impl NativeUiSession<'_, '_> {
    fn settings_wm(&mut self, inspector: &NativeApplicationInspector) -> Result<Vec<u8>, String> {
        let out = self.run(
            inspector,
            "settings-fixed-window-custody",
            ["/system/bin/dumpsys", "window"]
                .map(str::to_owned)
                .to_vec(),
            false,
            false,
            Duration::from_secs(15),
            super::super::NativeUiOutput::Helper,
            self.work_end,
        )?;
        need(
            out.stdout.len() <= MAX_WINDOW_BYTES,
            "Settings WM complete output exceeds source bound",
        )?;
        Ok(out.stdout)
    }
    fn settings_page(
        &mut self,
        inspector: &NativeApplicationInspector,
        companion: &ActualApplicationObservation,
        page: Page,
    ) -> Result<PageEvidence, String> {
        let task = self.task.ok_or("Settings actual task absent")?;
        let uid = if page == Page::Permissions {
            companion.facts().uid
        } else {
            self.baseline.application().uid
        };
        let mut last = String::new();
        for attempt in 1..=PAGE_READS {
            self.owned_task(inspector, self.work_end)?;
            inspector
                .require_observations_local(self.baseline.main(), companion, self.work_end)
                .map_err(|e| e.to_string())?;
            let first_raw = self.settings_wm(inspector)?;
            let first = match parse_window(&first_raw, page, uid, task) {
                Ok(window) => window,
                Err(error) => {
                    // A successful native click can precede the companion's
                    // first frame. Only the already proven source AppInfo
                    // window in this same task may remain during this wait.
                    if page == Page::Permissions
                        && attempt < PAGE_READS
                        && parse_window(
                            &first_raw,
                            Page::AppInfo,
                            self.baseline.application().uid,
                            task,
                        )
                        .is_ok()
                    {
                        self.owned_task(inspector, self.work_end)?;
                        need(
                            self.work_end.saturating_duration_since(Instant::now()) > POLL_GAP,
                            "Settings companion wait reached its original deadline",
                        )?;
                        std::thread::sleep(POLL_GAP);
                        last = error;
                        continue;
                    }
                    return Err(error);
                }
            };
            let request = if page == Page::Permissions {
                wire::Request::permission_controller_dump()
            } else {
                wire::Request::new(SETTINGS, wire::Operation::Dump).map_err(|e| e.to_string())?
            };
            let out = self.run(
                inspector,
                "settings-fixed-page-dump",
                request.arguments().map_err(|e| e.to_string())?,
                true,
                false,
                COMMAND_CAP,
                super::super::NativeUiOutput::Helper,
                self.work_end,
            )?;
            let reply = wire::Reply::parse(&request, &out).map_err(|e| e.to_string())?;
            let second_raw = self.settings_wm(inspector)?;
            let second = parse_window(&second_raw, page, uid, task)?;
            need(
                first == second,
                "Settings actual focused task/window changed around its semantic read",
            )?;
            self.owned_task(inspector, self.work_end)?;
            inspector
                .require_observations_local(self.baseline.main(), companion, self.work_end)
                .map_err(|e| e.to_string())?;
            match page_semantics(page, reply.body()) {
                Ok(feedback) => {
                    let fact = PageEvidence {
                        page,
                        window: first,
                        query_stdout_sha256: format!("{:x}", Sha256::digest(&out.stdout)),
                        window_before_sha256: format!("{:x}", Sha256::digest(&first_raw)),
                        window_after_sha256: format!("{:x}", Sha256::digest(&second_raw)),
                        node_count: nodes(reply.body())?.len(),
                        attempts: attempt,
                        feedback,
                    };
                    self.journal.json(
                        &format!(
                            "SETTINGS-PAGE-{}.json",
                            PAGES.iter().position(|p| *p == page).unwrap()
                        ),
                        &fact,
                    )?;
                    return Ok(fact);
                }
                Err(error) => last = error,
            }
            if attempt < PAGE_READS {
                before(self.work_end)?;
                need(
                    self.work_end.saturating_duration_since(Instant::now()) > POLL_GAP,
                    "Settings original deadline cannot cover its readonly observation gap",
                )?;
                std::thread::sleep(POLL_GAP);
            }
        }
        Err(format!(
            "Settings fixed visible page was not observed after bounded readonly sampling: {last}"
        ))
    }
    fn settings_navigate(
        &mut self,
        inspector: &NativeApplicationInspector,
        destination: Destination,
    ) -> Result<(), String> {
        self.owned_task(inspector, self.work_end)?;
        let out = self.run(
            inspector,
            "settings-fixed-in-task-navigation",
            navigation(self.task.ok_or("Settings task absent")?, destination),
            true,
            true,
            Duration::from_secs(30),
            super::super::NativeUiOutput::Small,
            self.work_end,
        )?;
        if let Err(e) = started(&out.stdout) {
            self.poisoned = true;
            return Err(e);
        }
        self.owned_task(inspector, self.work_end)
    }
    fn settings_return_from_companion(
        &mut self,
        inspector: &NativeApplicationInspector,
        companion: &ActualApplicationObservation,
        prior: &PageEvidence,
    ) -> Result<(), String> {
        self.owned_task(inspector, self.work_end)?;
        inspector
            .require_observations_local(self.baseline.main(), companion, self.work_end)
            .map_err(|e| e.to_string())?;
        let raw = self.settings_wm(inspector)?;
        need(
            parse_window(
                &raw,
                Page::Permissions,
                companion.facts().uid,
                self.task.ok_or("Settings task absent")?,
            )? == prior.window,
            "Settings companion changed before the one fixed normal return",
        )?;
        self.run(
            inspector,
            "settings-companion-one-back",
            ["/system/bin/input", "keyevent", "4"]
                .map(str::to_owned)
                .to_vec(),
            true,
            true,
            Duration::from_secs(15),
            super::super::NativeUiOutput::Small,
            self.work_end,
        )?;
        self.owned_task(inspector, self.work_end)?;
        for attempt in 1..=PAGE_READS {
            let raw = self.settings_wm(inspector)?;
            let task = self.task.ok_or("Settings task absent")?;
            if parse_window(&raw, Page::AppInfo, self.baseline.application().uid, task).is_ok() {
                return Ok(());
            }
            // No additional Back is sent. Only the exact original companion
            // window may still be finishing during a bounded readonly wait.
            need(
                parse_window(&raw, Page::Permissions, companion.facts().uid, task)? == prior.window
                    && attempt < PAGE_READS,
                "Settings companion did not return normally without another input",
            )?;
            need(
                self.work_end.saturating_duration_since(Instant::now()) > POLL_GAP,
                "Settings return wait reached its original deadline",
            )?;
            std::thread::sleep(POLL_GAP);
        }
        Err("Settings normal companion return remained incomplete".into())
    }
}

/// Completed live case plus immutable finished history. It does not implement
/// Deserialize/Clone and exposes no constructor from saved comparison values.
pub struct SettingsPermissionCaseObservation {
    finished: RetainedNativeUiTranscript,
    companion: [ActualApplicationObservation; 2],
    permissions: [ActualApplicationPermissionObservation; 2],
    pages: Vec<PageEvidence>,
    end: Instant,
}
impl SettingsPermissionCaseObservation {
    pub fn transcript(&self) -> &NativeUiTranscript {
        self.finished.transcript()
    }
    pub fn verify_retained(&self) -> Result<(), String> {
        self.finished.guard_immutable()?;
        let target = self.transcript().engine().application();
        selected_settings(target)?;
        selected_companion(self.companion[0].facts(), target)?;
        selected_companion(self.companion[1].facts(), target)?;
        need(
            self.companion[0].facts() == self.companion[1].facts(),
            "Settings actual companion complete PM identity changed",
        )?;
        self.permissions[0].facts().require_application(target)?;
        self.permissions[1].facts().require_application(target)?;
        self.permissions[0]
            .facts()
            .same_permissions(self.permissions[1].facts())?;
        need(
            self.pages.len() == PAGE_COUNT
                && self.pages.iter().zip(PAGES).all(|(p, expected)| {
                    p.page == expected
                        && p.window.task == self.transcript().task()
                        && p.window.display == 0
                        && expected.accepts_component(&p.window.component)
                        && p.window.uid
                            == if expected == Page::Permissions {
                                self.companion[0].facts().uid
                            } else {
                                target.uid
                            }
                        && (1..=PAGE_READS).contains(&p.attempts)
                        && (1..=2000).contains(&p.node_count)
                }),
            "Settings actual page sequence/task/identity evidence is incomplete",
        )?;
        need(
            self.transcript().actions() == 10,
            "Settings successful history differs from the fixed UI actions and original one close",
        )?;
        Ok(())
    }
    pub fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.finished.require_subject(main, application)?;
        self.verify_retained()
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.verify_retained()?;
        Ok(serde_json::json!({
            "schema":"droidloom.settings-permission-interface-case.v1",
            "application":self.transcript().engine().application(),
            "main":self.transcript().engine().facts().main,
            "task":self.transcript().task(), "journal":self.transcript().journal(),
            "pages":self.pages,
            "companion_application":self.companion[0].facts(),
            "complete_companion_identity_unchanged":true,
            "pm_permissions_before":self.permissions[0].facts(),
            "pm_permissions_after":self.permissions[1].facts(),
            "complete_pm_permissions_unchanged":true,
            "permission_controls_clicked":false,"account_provider_selected":false,
            "account_add_or_remove_requested":false,"search_query_cleared":true,
            "normal_return_and_exact_owned_task_close":true,
            "all_actual_invocations_retired":true,"original_deadline_extended":false,
            "data_permissions_or_stability_inferred":false,"whole_application_accepted":false
        }))
    }
}

pub fn run_settings_permission_case(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<SettingsPermissionCaseObservation, String> {
    let session_end = require_window(Instant::now(), original_end, baseline.deadline())?;
    selected_settings(baseline.application())?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|e| e.to_string())?;
    let permissions_before = inspector
        .observe_application_permission_state_until(
            baseline.main(),
            baseline.actual_application(),
            original_end,
        )
        .map_err(|e| e.to_string())?;
    let companion_before = inspector
        .inspect_observed_until(COMPANION, 0, original_end)
        .map_err(|e| e.to_string())?;
    selected_companion(companion_before.facts(), baseline.application())?;
    inspector
        .require_observations_local(baseline.main(), &companion_before, original_end)
        .map_err(|e| e.to_string())?;
    let mut session = NativeUiSession::open(inspector, baseline, session_end)?;
    session.journal.json(
        "SETTINGS-INTERFACE-BEGIN.json",
        &serde_json::json!({
        "companion":companion_before.facts(), "pm_permissions":permissions_before.facts(),
        "fixed_query":SEARCH,"account_mutation":false,"permission_mutation":false,
        "automatic_retry":false,"comparison_only":true}),
    )?;
    let attempted: Result<Vec<PageEvidence>, String> = (|| {
        let mut pages = Vec::with_capacity(PAGE_COUNT);
        session.settings_navigate(inspector, Destination::AppInfo)?;
        pages.push(session.settings_page(inspector, &companion_before, Page::AppInfo)?);
        // This exact native click follows Settings' selected source:
        // MANAGE_APP_PERMISSIONS + own package + hideInfoButton, started for
        // result by Settings. The shell never invokes protected PC activities.
        session.click(
            inspector,
            wire::Selector::exact_text("Permissions")
                .map_err(|e| e.to_string())?
                .enabled(),
        )?;
        let permission = session.settings_page(inspector, &companion_before, Page::Permissions)?;
        session.settings_return_from_companion(inspector, &companion_before, &permission)?;
        pages.push(permission);
        session.settings_navigate(inspector, Destination::Accounts)?;
        pages.push(session.settings_page(inspector, &companion_before, Page::Accounts)?);
        session.settings_navigate(inspector, Destination::Apps)?;
        pages.push(session.settings_page(inspector, &companion_before, Page::AppsBefore)?);
        session.click(
            inspector,
            wire::Selector::resource_id(SEARCH_MENU)
                .map_err(|e| e.to_string())?
                .enabled(),
        )?;
        session.set_text(inspector, wire::Selector::editable().enabled(), SEARCH)?;
        pages.push(session.settings_page(inspector, &companion_before, Page::EmptyLookup)?);
        session.set_text(inspector, wire::Selector::editable().enabled(), "")?;
        pages.push(session.settings_page(inspector, &companion_before, Page::AppsRestored)?);
        session.settings_navigate(inspector, Destination::Home)?;
        pages.push(session.settings_page(inspector, &companion_before, Page::Home)?);
        session.journal.json(
            "SETTINGS-INTERFACE-COMPLETE.json",
            &serde_json::json!({
            "pages":pages,"permission_controls_clicked":false,"account_provider_selected":false,
            "fixed_query_cleared":true,"comparison_only":true}),
        )?;
        Ok(pages)
    })();
    let pages = match attempted {
        Ok(pages) => pages,
        Err(error) => return Err(session.observation_failure(inspector, error)),
    };
    let finished = session.finish(inspector)?.into_retained()?;
    let companion_after = inspector
        .inspect_observed_until(COMPANION, 0, original_end)
        .map_err(|e| e.to_string())?;
    inspector
        .require_observations_local(baseline.main(), &companion_after, original_end)
        .map_err(|e| e.to_string())?;
    let permissions_after = inspector
        .observe_application_permission_state_until(
            baseline.main(),
            baseline.actual_application(),
            original_end,
        )
        .map_err(|e| e.to_string())?;
    inspector
        .require_permission_state_local(
            baseline.main(),
            baseline.actual_application(),
            &permissions_after,
            original_end,
        )
        .map_err(|e| e.to_string())?;
    baseline
        .verify_local(inspector, original_end)
        .map_err(|e| e.to_string())?;
    before(original_end)?;
    let result = SettingsPermissionCaseObservation {
        finished,
        companion: [companion_before, companion_after],
        permissions: [permissions_before, permissions_after],
        pages,
        end: original_end,
    };
    result.verify_retained()?;
    before(result.end)?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn wm(task: u32, uid: u32, package: &str, activity: &str) -> String {
        format!(
            "WINDOW MANAGER\n  mCurrentFocus=Window{{a1 u0 {package}/{activity}}}\n  Window #3 Window{{a1 u0 {package}/{activity}}}:\n    mDisplayId=0 taskId={task} mSession=Session{{1 2:u0a1}}\n    mOwnerUid={uid} showForAllUsers=false package={package} appop=NONE\n    mViewVisibility=0x0 mHaveFrame=true\n    mHasSurface=true isReadyForDisplay()=true\n  globalState=true\n"
        )
    }
    #[test]
    fn settings_permissions_window_requires_actual_task_uid_focus_and_surface() {
        let good = wm(
            77,
            10103,
            COMPANION,
            ".permission.ui.ManagePermissionsActivity",
        );
        let actual = parse_window(good.as_bytes(), Page::Permissions, 10103, 77).unwrap();
        assert_eq!(actual.task, 77);
        for altered in [
            good.replace("taskId=77", "taskId=78"),
            good.replace("mOwnerUid=10103", "mOwnerUid=1000"),
            good.replace("mDisplayId=0", "mDisplayId=1"),
            good.replace("mViewVisibility=0x0", "mViewVisibility=0x4"),
            good.replace("mHasSurface=true", "mHasSurface=false"),
            good.replace("isReadyForDisplay()=true", "isReadyForDisplay()=false"),
            good.replace("a1 u0", "a1 u10"),
            good.replace("Window #3 Window{a1", "Window #3 Window{b2"),
            good.replace(
                "package=com.android.permissioncontroller",
                "package=com.android.settings",
            ),
            good.replace(".permission.ui.ManagePermissionsActivity", ".Different"),
        ] {
            assert!(parse_window(altered.as_bytes(), Page::Permissions, 10103, 77).is_err());
        }
    }
    #[test]
    fn settings_permissions_window_rejects_missing_duplicate_and_cross_block_ownership() {
        let good = wm(
            77,
            10103,
            COMPANION,
            ".permission.ui.ManagePermissionsActivity",
        );
        for altered in [
            good.replace(" taskId=77", ""),
            good.replace(" taskId=77", " taskId=77 taskId=77"),
            good.replace("    mOwnerUid=10103", "  footer=anything\n    mOwnerUid=10103"),
            good.replace("  globalState=true", "  Window #4 Window{a1 u0 com.android.permissioncontroller/.permission.ui.ManagePermissionsActivity}:\n    mOwnerUid=10103"),
            good.clone() + "  mCurrentFocus=Window{b2 u0 com.android.settings/.Settings}\n",
            good.trim_end().into(),
            good.clone() + "\0",
        ] { assert!(parse_window(altered.as_bytes(), Page::Permissions, 10103, 77).is_err()); }
    }
    fn n(id: &str, text: &str, rect: [i64; 4], editable: bool) -> Value {
        serde_json::json!({"resource-id":id,"text":text,"visible":true,"package":SETTINGS,
            "class":if editable {"android.widget.EditText"} else {"android.widget.TextView"},
            "editable":editable,"enabled":true,"password":false,"bounds_array":rect})
    }
    fn empty_nodes() -> Value {
        serde_json::json!({"nodes":[
            n("android:id/search_src_text",SEARCH,[0,0,600,50],true),
            n(APPS_LIST,"",[0,70,600,600],false)
        ]})
    }
    #[test]
    fn settings_permissions_empty_lookup_needs_positive_complete_list_and_query_readback() {
        let good = empty_nodes();
        assert!(matches!(
            page_semantics(Page::EmptyLookup, &good).unwrap(),
            Feedback::CompleteEmptyApplicationsList
        ));
        for alter in 0..6 {
            let mut bad = good.clone();
            match alter {
                0 => bad["nodes"].as_array_mut().unwrap().remove(1),
                1 => {
                    bad["nodes"][0]["text"] = "wrong".into();
                    Value::Null
                }
                2 => {
                    bad["nodes"][1]["visible"] = false.into();
                    Value::Null
                }
                3 => {
                    bad["nodes"][1]["package"] = COMPANION.into();
                    Value::Null
                }
                4 => {
                    bad["nodes"].as_array_mut().unwrap().push(n(
                        "android:id/title",
                        "some app",
                        [5, 80, 500, 100],
                        false,
                    ));
                    Value::Null
                }
                _ => {
                    bad["nodes"].as_array_mut().unwrap().push(n(
                        "android:id/title",
                        "No matching apps",
                        [5, 80, 500, 100],
                        false,
                    ));
                    Value::Null
                }
            };
            assert!(page_semantics(Page::EmptyLookup, &bad).is_err());
        }
        let mut restored = good.clone();
        restored["nodes"][0]["text"] = "".into();
        restored["nodes"].as_array_mut().unwrap().push(n(
            "android:id/title",
            "Calendar",
            [5, 80, 500, 100],
            false,
        ));
        assert!(page_semantics(Page::AppsRestored, &restored).is_ok());
        restored["nodes"][0]["text"] = SEARCH.into();
        assert!(page_semantics(Page::AppsRestored, &restored).is_err());
    }
    #[test]
    fn settings_permissions_pages_require_account_and_permission_interfaces_not_headings_alone() {
        let accounts = serde_json::json!({"nodes":[n("title","Passwords & accounts",[0,0,600,60],false),
            n("add","Add account",[0,100,600,160],false)]});
        assert!(page_semantics(Page::Accounts, &accounts).is_ok());
        let mut missing = accounts.clone();
        missing["nodes"].as_array_mut().unwrap().pop();
        assert!(page_semantics(Page::Accounts, &missing).is_err());
        let mut permission = serde_json::json!({"nodes":[n("title","App permissions",[0,0,600,60],false),
            n("name","Settings",[0,100,600,160],false),n("group","Allowed",[0,200,600,240],false)]});
        for item in permission["nodes"].as_array_mut().unwrap() {
            item["package"] = COMPANION.into();
        }
        assert!(page_semantics(Page::Permissions, &permission).is_ok());
        permission["nodes"].as_array_mut().unwrap().pop();
        assert!(page_semantics(Page::Permissions, &permission).is_err());
        assert_eq!(PAGES.len(), 7);
        assert_eq!(PAGES[5], Page::AppsRestored);
        assert_eq!(PAGES[6], Page::Home);
    }
    #[test]
    fn settings_permissions_navigation_has_no_permission_account_or_arbitrary_target_action() {
        for dest in [
            Destination::AppInfo,
            Destination::Accounts,
            Destination::Apps,
            Destination::Home,
        ] {
            let a = navigation(77, dest);
            assert_eq!(&a[..3], ["/system/bin/cmd", "activity", "start-activity"]);
            assert_eq!(a[a.iter().position(|v| v == "--task").unwrap() + 1], "77");
            assert!(
                a[a.iter().position(|v| v == "-n").unwrap() + 1]
                    .starts_with("com.android.settings/")
            );
            assert!(!a.iter().any(|v| v.contains(COMPANION)
                || v.contains("ADD_ACCOUNT")
                || v.contains("MANAGE_APP_PERMISSIONS")));
        }
        assert!(started(b"Starting: Intent { }\nStatus: ok\nComplete\n").is_ok());
        for bad in [
            b"Status: timeout\nComplete\n".as_slice(),
            b"Status: ok\nError: denied\nComplete\n",
            b"Status: ok\nStatus: ok\nComplete\n",
            b"Status: ok\n",
        ] {
            assert!(started(bad).is_err());
        }
    }
    #[test]
    fn settings_permissions_original_deadline_allows_consumed_time_but_never_renews() {
        let now = Instant::now();
        let end = now + Duration::from_secs(settings_permission_case_window_seconds());
        assert!(require_window(now + Duration::from_millis(1), end, end).is_ok());
        assert!(
            require_window(
                now,
                end + Duration::from_secs(1),
                end + Duration::from_secs(1)
            )
            .is_err()
        );
        assert!(require_window(now, end, end - Duration::from_secs(1)).is_err());
        assert!(require_window(end, end, end).is_err());
        assert_eq!(settings_permission_case_window_seconds(), 6050);
    }
}
