//! Closed comparison protocol for native UI execution by the original broker.
//!
//! These serde values are never live authority. Only the authenticated client
//! borrows opaque Main/PM observations, and only the normal backend can create
//! the observation accepted by GatewayReply::from_observation.
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use crate::native_application_ui_protocol as wire;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::os::unix::process::ExitStatusExt;
use std::process::{ExitStatus, Output};
use std::time::{Duration, Instant};

const SETTINGS: &str = "com.android.settings";
const CAMERA: &str = "com.android.camera2";
const COMPANION: &str = "com.android.permissioncontroller";
const IMAGES: &str = "content://media/external/images/media";
const IMAGE_COLUMNS: &str = "_id:_data:_display_name:mime_type:_size:width:height:orientation:date_added:is_pending:owner_package_name";
const REQUEST_SCHEMA: &str = "droidloom.native-ui-gateway-request.v1";
const REPLY_SCHEMA: &str = "droidloom.native-ui-gateway-reply.v1";
const SMALL: usize = 65_536;
const PNG: usize = 33_554_432;
// This is used only by RunNativeUi response framing. Ordinary control replies
// keep their original bound. PNG Base64, stderr and complete comparisons fit.
pub(crate) const MAX_RESPONSE_BYTES: usize = 45 * 1024 * 1024;

fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn positive(text: &str, maximum: u64) -> Result<u64, String> {
    let value: u64 = text
        .parse()
        .map_err(|_| "native UI positive integer is malformed")?;
    need(
        value != 0 && value <= maximum && value.to_string() == text,
        "native UI integer is not canonical or exceeds the fixed bound",
    )?;
    Ok(value)
}
fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).into()).collect()
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum EntryCheck {
    GuestUid,
    GuestGid,
    BootCompleted,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum SettingsDestination {
    AppInfo,
    Accounts,
    Apps,
    Home,
}
impl SettingsDestination {
    fn arguments(&self, task: u32) -> Vec<String> {
        let (activity, action, data) = match self {
            Self::AppInfo => (
                "com.android.settings.applications.InstalledAppDetails",
                "android.settings.APPLICATION_DETAILS_SETTINGS",
                true,
            ),
            Self::Accounts => (
                "com.android.settings.Settings$AccountDashboardActivity",
                "android.intent.action.MAIN",
                false,
            ),
            Self::Apps => (
                "com.android.settings.Settings$ManageApplicationsActivity",
                "android.settings.MANAGE_APPLICATIONS_SETTINGS",
                false,
            ),
            Self::Home => (
                "com.android.settings.Settings",
                "android.intent.action.MAIN",
                false,
            ),
        };
        let mut args = strings(&[
            "/system/bin/cmd",
            "activity",
            "start-activity",
            "-W",
            "--user",
            "0",
            "--display",
            "0",
            "--task",
        ]);
        args.extend([
            task.to_string(),
            "-a".into(),
            action.into(),
            "-n".into(),
            format!("{SETTINGS}/{activity}"),
        ]);
        if data {
            args.extend(strings(&["-d", "package:com.android.settings"]));
        }
        args
    }
}

// Comparison DTO only. Converting it uses exactly the original Selector
// builders; it does not add a Deserialize constructor to the original type.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct HelperSelector {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    text: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    desc: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    editable: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    focused: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    enabled: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    scrollable: Option<bool>,
}
impl HelperSelector {
    fn selector(&self) -> Result<wire::Selector, String> {
        need(
            ([
                self.id.is_some(),
                self.text.is_some(),
                self.desc.is_some(),
                self.editable.is_some(),
            ]
            .into_iter()
            .filter(|v| *v)
            .count()
                == 1 || (self.id.is_none() && self.text.is_none() && self.desc.is_none()
                    && self.editable.is_none() && self.scrollable == Some(true)))
                && !(self.editable.is_some() && self.scrollable.is_some())
                && [self.editable, self.focused, self.enabled, self.scrollable]
                    .into_iter()
                    .all(|v| v.is_none_or(|value| value)),
            "native UI selector is outside the existing builder vocabulary",
        )?;
        let mut result = if let Some(value) = &self.id {
            wire::Selector::resource_id(value).map_err(|e| e.to_string())?
        } else if let Some(value) = &self.text {
            wire::Selector::exact_text(value).map_err(|e| e.to_string())?
        } else if let Some(value) = &self.desc {
            wire::Selector::description(value).map_err(|e| e.to_string())?
        } else if self.editable == Some(true) {
            wire::Selector::editable()
        } else {
            wire::Selector::scrollable()
        };
        if self.scrollable == Some(true) { result = result.requiring_scrollable(); }
        if self.focused == Some(true) {
            result = result.focused();
        }
        if self.enabled == Some(true) {
            result = result.enabled();
        }
        Ok(result)
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum HelperOperation {
    Meta {},
    Dump {},
    Find {
        selector: HelperSelector,
    },
    Click {
        selector: HelperSelector,
    },
    ScrollForward { selector: HelperSelector },
    ScrollBackward { selector: HelperSelector },
    SetText {
        selector: HelperSelector,
        value: String,
    },
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct HelperCommand {
    package: String,
    operation: HelperOperation,
}
impl HelperCommand {
    fn request(&self) -> Result<wire::Request, String> {
        let operation = match &self.operation {
            HelperOperation::Meta {} => wire::Operation::Meta,
            HelperOperation::Dump {} => wire::Operation::Dump,
            HelperOperation::Find { selector } => wire::Operation::Find(selector.selector()?),
            HelperOperation::Click { selector } => wire::Operation::Click(selector.selector()?),
            HelperOperation::ScrollForward { selector } => wire::Operation::ScrollForward(selector.selector()?),
            HelperOperation::ScrollBackward { selector } => wire::Operation::ScrollBackward(selector.selector()?),
            HelperOperation::SetText { selector, value } => wire::Operation::SetText {
                selector: selector.selector()?,
                value: value.clone(),
            },
        };
        if self.package == COMPANION {
            need(
                matches!(self.operation, HelperOperation::Dump {}),
                "native UI companion accepts only the fixed read-only Dump",
            )?;
            Ok(wire::Request::permission_controller_dump())
        } else {
            wire::Request::new(&self.package, operation).map_err(|e| e.to_string())
        }
    }
    fn parse(encoded: &str) -> Result<Self, String> {
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct Payload {
            op: String,
            expected_package: String,
            display: u32,
            accessibility_mode: String,
            selector: Option<HelperSelector>,
            value: Option<String>,
        }
        let raw =
            wire::decode64_bounded(encoded, SMALL, false, false).map_err(|e| e.to_string())?;
        let unique = wire::strict_json(&raw, false).map_err(|e| e.to_string())?;
        let body: Payload = serde_json::from_value(unique).map_err(|e| e.to_string())?;
        need(
            body.display == 0 && body.accessibility_mode == "none",
            "native UI helper display or accessibility mode differs",
        )?;
        let operation = match (body.op.as_str(), body.selector, body.value) {
            ("meta", None, None) => HelperOperation::Meta {},
            ("dump", None, None) => HelperOperation::Dump {},
            ("find", Some(selector), None) => HelperOperation::Find { selector },
            ("click", Some(selector), None) => HelperOperation::Click { selector },
            ("scroll-forward", Some(selector), None) => HelperOperation::ScrollForward { selector },
            ("scroll-backward", Some(selector), None) => HelperOperation::ScrollBackward { selector },
            ("set-text", Some(selector), Some(value)) => {
                HelperOperation::SetText { selector, value }
            }
            _ => return Err("native UI helper operation or exact fields differ".into()),
        };
        let result = Self {
            package: body.expected_package,
            operation,
        };
        // Re-encode with the actual original builder. This rejects null/extra
        // fields, alternate JSON spelling/order, duplicate keys and Base64 aliases.
        let arguments = result.request()?.arguments().map_err(|e| e.to_string())?;
        need(
            arguments[6] == encoded,
            "native UI helper payload is not source-canonical",
        )?;
        Ok(result)
    }
    fn require_subject(&self, package: &str) -> Result<(), String> {
        self.request()?;
        need(
            self.package == package
                || (package == SETTINGS
                    && self.package == COMPANION
                    && matches!(self.operation, HelperOperation::Dump {})),
            "native UI helper is for another package or non-read-only companion",
        )
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum GatewayCommand {
    EntryCheck {
        check: EntryCheck,
    },
    TaskList {},
    TaskRemove {
        task: u32,
    },
    Helper {
        request: HelperCommand,
    },
    WindowDisplays {},
    ScreenCapture {},
    CameraImageIds {},
    CameraImageRow {
        row: u64,
    },
    CameraClock {},
    CalendarCounts {},
    SettingsWindow {},
    SettingsStart {
        destination: SettingsDestination,
        task: u32,
    },
    SettingsBack {},
    CameraMenu {},
    PackageIdentity { package: String },
    PackagePaths { package: String },
    PackageLauncher { package: String },
}
impl GatewayCommand {
    fn parse(literal: &[String], shell: bool, package: &str) -> Result<Self, String> {
        let args = literal.iter().map(String::as_str).collect::<Vec<_>>();
        let value = match args.as_slice() {
            ["/system/bin/toybox", "id", "-u"] => Self::EntryCheck {
                check: EntryCheck::GuestUid,
            },
            ["/system/bin/toybox", "id", "-g"] => Self::EntryCheck {
                check: EntryCheck::GuestGid,
            },
            ["/system/bin/getprop", "sys.boot_completed"] => Self::EntryCheck {
                check: EntryCheck::BootCompleted,
            },
            ["/system/bin/cmd", "activity", "stack", "list"] => Self::TaskList {},
            ["/system/bin/cmd", "activity", "stack", "remove", task] => Self::TaskRemove {
                task: positive(task, i32::MAX as u64)? as u32,
            },
            [
                "/system/bin/am",
                "instrument",
                "-w",
                "-r",
                "-e",
                "request",
                encoded,
                component,
            ] if *component == wire::HELPER_COMPONENT => Self::Helper {
                request: HelperCommand::parse(encoded)?,
            },
            ["/system/bin/dumpsys", "window", "displays"] => Self::WindowDisplays {},
            ["/system/bin/screencap", "-p"] => Self::ScreenCapture {},
            [
                "/system/bin/content",
                "query",
                "--user",
                "0",
                "--uri",
                uri,
                "--projection",
                "_id",
            ] if *uri == IMAGES => Self::CameraImageIds {},
            [
                "/system/bin/content",
                "query",
                "--user",
                "0",
                "--uri",
                uri,
                "--projection",
                columns,
            ] if *columns == IMAGE_COLUMNS => Self::CameraImageRow {
                row: positive(
                    uri.strip_prefix(&format!("{IMAGES}/"))
                        .ok_or("native UI fixed image URI differs")?,
                    i64::MAX as u64,
                )?,
            },
            ["/system/bin/date", "+%s"] => Self::CameraClock {},
            ["/system/bin/app_process64", "-Xint", "-Xusejit:false", "/system/bin", class]
                if *class == crate::native_calendar_counts::CLASS => Self::CalendarCounts {},
            ["/system/bin/dumpsys", "window"] => Self::SettingsWindow {},
            ["/system/bin/input", "keyevent", "4"] => Self::SettingsBack {},
            ["/system/bin/input", "keyevent", "82"] => Self::CameraMenu {},
            ["/system/bin/cmd", "package", "list", "packages", "-U",
                "--show-versioncode", "--user", "0", selected]
                if *selected == package => Self::PackageIdentity { package: (*selected).into() },
            ["/system/bin/cmd", "package", "path", "--user", "0", selected]
                if *selected == package => Self::PackagePaths { package: (*selected).into() },
            ["/system/bin/cmd", "package", "resolve-activity", "--brief", "--user", "0",
                "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                selected] if *selected == package => Self::PackageLauncher { package: (*selected).into() },
            [
                "/system/bin/cmd",
                "activity",
                "start-activity",
                "-W",
                "--user",
                "0",
                "--display",
                "0",
                "--task",
                task,
                "-a",
                _,
                "-n",
                _,
                ..,
            ] => {
                let task = positive(task, i32::MAX as u64)? as u32;
                let destination = [
                    SettingsDestination::AppInfo,
                    SettingsDestination::Accounts,
                    SettingsDestination::Apps,
                    SettingsDestination::Home,
                ]
                .into_iter()
                .find(|value| value.arguments(task).as_slice() == literal)
                .ok_or("native UI fixed Settings destination differs")?;
                Self::SettingsStart { destination, task }
            }
            _ => return Err("native UI literal is outside the fixed command set".into()),
        };
        need(
            (value.guest_uid() == 2000) == shell,
            "native UI fixed guest identity differs",
        )?;
        value.validate_subject(package)?;
        need(
            value.literal_arguments()?.as_slice() == literal,
            "native UI literal is not canonical",
        )?;
        Ok(value)
    }
    fn validate_subject(&self, package: &str) -> Result<(), String> {
        need(
            crate::engine_custody::selected_package(package),
            "native UI subject is outside the selected 39 packages",
        )?;
        match self {
            Self::Helper { request } => request.require_subject(package)?,
            Self::CalendarCounts {} => need(
                package == crate::native_calendar_counts::SUBJECT,
                "Calendar counts require the actual fixed Calendar application",
            )?,
            Self::PackageIdentity { package: selected }
            | Self::PackagePaths { package: selected }
            | Self::PackageLauncher { package: selected } => need(
                selected == package,
                "native leaf PM query differs from the actual selected application",
            )?,
            Self::TaskRemove { task } | Self::SettingsStart { task, .. } => need(
                *task > 0 && *task <= i32::MAX as u32,
                "native UI task bound differs",
            )?,
            Self::CameraImageRow { row } => need(
                *row > 0 && *row <= i64::MAX as u64,
                "native UI image row bound differs",
            )?,
            _ => {}
        }
        if matches!(
            self,
            Self::CameraImageIds {} | Self::CameraImageRow { .. } | Self::CameraClock {}
                | Self::CameraMenu {}
        ) {
            need(
                package == CAMERA,
                "native UI media query requires the actual Camera subject",
            )?;
        }
        if matches!(
            self,
            Self::SettingsWindow {} | Self::SettingsStart { .. } | Self::SettingsBack {}
        ) {
            need(
                package == SETTINGS,
                "native UI Settings operation requires the actual Settings subject",
            )?;
        }
        Ok(())
    }
    pub(crate) fn literal_arguments(&self) -> Result<Vec<String>, String> {
        Ok(match self {
            Self::EntryCheck {
                check: EntryCheck::GuestUid,
            } => strings(&["/system/bin/toybox", "id", "-u"]),
            Self::EntryCheck {
                check: EntryCheck::GuestGid,
            } => strings(&["/system/bin/toybox", "id", "-g"]),
            Self::EntryCheck {
                check: EntryCheck::BootCompleted,
            } => strings(&["/system/bin/getprop", "sys.boot_completed"]),
            Self::TaskList {} => strings(&["/system/bin/cmd", "activity", "stack", "list"]),
            Self::TaskRemove { task } => {
                need(
                    *task > 0 && *task <= i32::MAX as u32,
                    "native UI task bound differs",
                )?;
                let mut result = strings(&["/system/bin/cmd", "activity", "stack", "remove"]);
                result.push(task.to_string());
                result
            }
            Self::Helper { request } => {
                request.request()?.arguments().map_err(|e| e.to_string())?
            }
            Self::WindowDisplays {} => strings(&["/system/bin/dumpsys", "window", "displays"]),
            Self::ScreenCapture {} => strings(&["/system/bin/screencap", "-p"]),
            Self::CameraImageIds {} => strings(&[
                "/system/bin/content",
                "query",
                "--user",
                "0",
                "--uri",
                IMAGES,
                "--projection",
                "_id",
            ]),
            Self::CameraImageRow { row } => {
                need(
                    *row > 0 && *row <= i64::MAX as u64,
                    "native UI image row bound differs",
                )?;
                strings(&[
                    "/system/bin/content",
                    "query",
                    "--user",
                    "0",
                    "--uri",
                    &format!("{IMAGES}/{row}"),
                    "--projection",
                    IMAGE_COLUMNS,
                ])
            }
            Self::CameraClock {} => strings(&["/system/bin/date", "+%s"]),
            Self::CalendarCounts {} => strings(&[
                "/system/bin/app_process64", "-Xint", "-Xusejit:false", "/system/bin",
                crate::native_calendar_counts::CLASS,
            ]),
            Self::SettingsWindow {} => strings(&["/system/bin/dumpsys", "window"]),
            Self::SettingsStart { destination, task } => {
                need(
                    *task > 0 && *task <= i32::MAX as u32,
                    "native UI task bound differs",
                )?;
                destination.arguments(*task)
            }
            Self::SettingsBack {} => strings(&["/system/bin/input", "keyevent", "4"]),
            Self::CameraMenu {} => strings(&["/system/bin/input", "keyevent", "82"]),
            Self::PackageIdentity { package } => {
                self.validate_subject(package)?;
                strings(&["/system/bin/cmd", "package", "list", "packages", "-U",
                    "--show-versioncode", "--user", "0", package])
            }
            Self::PackagePaths { package } => {
                self.validate_subject(package)?;
                strings(&["/system/bin/cmd", "package", "path", "--user", "0", package])
            }
            Self::PackageLauncher { package } => {
                self.validate_subject(package)?;
                strings(&["/system/bin/cmd", "package", "resolve-activity", "--brief",
                    "--user", "0", "-a", "android.intent.action.MAIN", "-c",
                    "android.intent.category.LAUNCHER", package])
            }
        })
    }
    pub(crate) fn guest_uid(&self) -> u32 {
        match self {
            Self::CalendarCounts {} => crate::native_calendar_counts::OBSERVER_UID,
            Self::TaskList {}
            | Self::TaskRemove { .. }
            | Self::Helper { .. }
            | Self::SettingsStart { .. }
            | Self::SettingsBack {}
            | Self::CameraMenu {}
            | Self::PackageIdentity { .. }
            | Self::PackagePaths { .. }
            | Self::PackageLauncher { .. } => 2000,
            _ => 0,
        }
    }
    pub(crate) fn maximum_duration(&self) -> Duration {
        Duration::from_secs(match self {
            Self::Helper { .. } => 70,
            Self::SettingsStart { .. } => 30,
            Self::TaskRemove { .. } | Self::ScreenCapture {} => 20,
            Self::CameraClock {} => 10,
            Self::CalendarCounts {} => 14,
            _ => 15,
        })
    }
    pub(crate) fn stdout_limit(&self) -> usize {
        match self {
            Self::CalendarCounts {} => crate::native_calendar_counts::OUTPUT_BYTES,
            Self::ScreenCapture {} => PNG,
            Self::Helper { .. } | Self::SettingsWindow {} => wire::WIRE_REPLY_BYTES,
            _ => SMALL,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatewayRequest {
    schema: String,
    #[serde(deserialize_with = "closed_value")]
    main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed_value")]
    application: ApplicationInspection,
    #[serde(deserialize_with = "closed_value")]
    command: GatewayCommand,
    deadline_monotonic_ns: u64,
}
impl GatewayRequest {
    pub(crate) fn from_owned(
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
        literal: &[String],
        shell: bool,
        end: Instant,
    ) -> Result<Self, String> {
        let command = GatewayCommand::parse(literal, shell, &application.package)?;
        // CLOCK first, Instant second: conversion can only shorten the caller's
        // original end. It never samples a fresh duration on the server.
        let clock = monotonic_ns()?;
        let now = Instant::now();
        let remaining = end
            .checked_duration_since(now)
            .filter(|v| !v.is_zero())
            .ok_or("native UI original command deadline elapsed")?
            .min(command.maximum_duration());
        let deadline_monotonic_ns = clock
            .checked_add(
                u64::try_from(remaining.as_nanos()).map_err(|_| "native UI deadline overflow")?,
            )
            .ok_or("native UI monotonic deadline overflow")?;
        let result = Self {
            schema: REQUEST_SCHEMA.into(),
            main: main.clone(),
            application: application.clone(),
            command,
            deadline_monotonic_ns,
        };
        result.validate()?;
        Ok(result)
    }
    pub(crate) fn command(&self) -> &GatewayCommand {
        &self.command
    }
    pub(crate) fn main(&self) -> &RuntimeMainCustody {
        &self.main
    }
    pub(crate) fn application(&self) -> &ApplicationInspection {
        &self.application
    }
    pub(crate) fn deadline(&self) -> Result<Instant, String> {
        // Instant first, CLOCK second: restoring an absolute end likewise never
        // extends it, including after queueing, parsing, or earlier bookends.
        let now = Instant::now();
        let clock = monotonic_ns()?;
        let remaining = self
            .deadline_monotonic_ns
            .checked_sub(clock)
            .filter(|v| *v != 0)
            .ok_or("native UI original absolute deadline elapsed")?;
        need(
            u128::from(remaining) <= self.command.maximum_duration().as_nanos(),
            "native UI deadline exceeds the fixed command cap",
        )?;
        now.checked_add(Duration::from_nanos(remaining))
            .ok_or("native UI Instant overflow".into())
    }
    pub(crate) fn validate(&self) -> Result<(), String> {
        need(
            self.schema == REQUEST_SCHEMA
                && self.application.user == 0
                && self.application.uid < 100_000
                && self.application.version_code > 0
                && self.main.epoch == self.application.epoch,
            "native UI request schema, actual user, version or Main/PM epoch differs",
        )?;
        self.main.validate(&self.application.epoch)?;
        self.command.validate_subject(&self.application.package)?;
        let apks = &self.application.apks;
        let paths: BTreeSet<_> = apks.iter().map(|v| &v.path).collect();
        let names: BTreeSet<_> = apks.iter().map(|v| &v.name).collect();
        need(
            !apks.is_empty()
                && apks.len() <= 64
                && paths.len() == apks.len()
                && names.len() == apks.len()
                && apks.iter().filter(|v| v.name == "base.apk").count() == 1
                && apks.iter().all(|v| {
                    v.bytes > 0
                        && digest(&v.sha256)
                        && !v.name.is_empty()
                        && v.name.len() <= 255
                        && !v.name.contains('/')
                        && v.path.starts_with('/')
                        && v.path.ends_with(".apk")
                        && v.path.len() <= 4096
                        && !v.path.chars().any(char::is_control)
                        && v.path
                            .split('/')
                            .skip(1)
                            .all(|s| !s.is_empty() && s != "." && s != "..")
                }),
            "native UI complete installed APK comparison differs",
        )?;
        self.deadline()?;
        Ok(())
    }
}
fn monotonic_ns() -> Result<u64, String> {
    let mut value: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    need(
        value.tv_sec >= 0 && (0..1_000_000_000).contains(&value.tv_nsec),
        "native UI monotonic clock is malformed",
    )?;
    (value.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64))
        .ok_or("native UI monotonic clock overflow".into())
}

// Preserve duplicate-key and exact-field rejection through nested comparison
// structs even if a future nested type adds serde defaults or skips a field.
fn closed_value<'de, D, T>(deserializer: D) -> Result<T, D::Error>
where
    D: serde::Deserializer<'de>,
    T: serde::de::DeserializeOwned + Serialize,
{
    let raw = wire::unique_json_value(deserializer)?;
    let value: T = serde_json::from_value(raw.clone()).map_err(serde::de::Error::custom)?;
    let encoded = serde_json::to_value(&value).map_err(serde::de::Error::custom)?;
    if encoded != raw {
        return Err(serde::de::Error::custom(
            "native UI comparison has unknown or noncanonical fields",
        ));
    }
    Ok(value)
}

#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExecutableNode {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    bytes: u64,
    mtime: i64,
    mtime_nsec: i64,
    ctime: i64,
    ctime_nsec: i64,
}
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ExecComparison {
    query_start_ticks: u64,
    original_parent_pid: u32,
    tracer_tid: u32,
    waitid_code: i32,
    waitid_status: i32,
    event_previous_tid: u64,
    executable: ExecutableNode,
    executable_mount_id: u64,
    executable_sha256: String,
    executable_selinux: String,
    process_selinux: String,
    process_apparmor: String,
    uid: u32,
    gid: u32,
    no_new_privileges: bool,
    seccomp_filter_mode: u32,
}
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct CreatorComparison {
    pid: u32,
    waitid_code: i32,
    waitid_status: i32,
}
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "owner", rename_all = "snake_case", deny_unknown_fields)]
enum LifecycleComparison {
    InstanceFactory {
        factory_pid: u32,
        factory_tid: u32,
        factory_pidfd_device: u64,
        factory_pidfd_inode: u64,
        query_pidfd_device: u64,
        query_pidfd_inode: u64,
        stdio_creator: CreatorComparison,
        release_acknowledged: bool,
    },
}
#[derive(Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadComparison {
    schema: u32,
    lifecycle: LifecycleComparison,
    query_pid: u32,
    query_waitid_code: i32,
    query_waitid_status: i32,
    exec: ExecComparison,
    output_bytes: usize,
    output_sha256: String,
    elapsed_millis: u64,
    cgroup_removed: bool,
}
impl ReadComparison {
    fn status(&self) -> Result<ExitStatus, String> {
        let raw = match (self.query_waitid_code, self.query_waitid_status) {
            (libc::CLD_EXITED, code) if (0..=255).contains(&code) => code << 8,
            (libc::CLD_KILLED, signal) if (1..=64).contains(&signal) => signal,
            (libc::CLD_DUMPED, signal) if (1..=64).contains(&signal) => signal | 0x80,
            _ => return Err("native UI actual query wait status is not terminal".into()),
        };
        Ok(ExitStatus::from_raw(raw))
    }
    fn validate(&self, command: &GatewayCommand, stdout: &[u8]) -> Result<(), String> {
        self.validate_with_limit(command,stdout,command.maximum_duration())
    }
    fn validate_with_limit(&self, command:&GatewayCommand, stdout:&[u8], duration:Duration) -> Result<(),String> {
        let profile=crate::production_application::native_ui_execution_profile(command)?;
        self.validate_profile(stdout,duration,command.guest_uid(),&profile)
    }
    fn validate_profile(&self,stdout:&[u8],duration:Duration,expected_guest_uid:u32,
        profile:&crate::production_application::NativeUiExecutionProfile)->Result<(),String>{
        self.status()?;
        need(
            self.schema == 2
                && self.cgroup_removed
                && self.query_pid > 1
                && self.query_pid <= i32::MAX as u32
                && self.output_bytes == stdout.len()
                && self.output_sha256 == hash(stdout)
                && u128::from(self.elapsed_millis) <= duration.as_millis(),
            "native UI real query retirement, complete output or fixed duration differs",
        )?;
        let LifecycleComparison::InstanceFactory {
            factory_pid,
            factory_tid,
            factory_pidfd_device,
            factory_pidfd_inode,
            query_pidfd_device,
            query_pidfd_inode,
            stdio_creator,
            release_acknowledged,
        } = &self.lifecycle;
        need(
            *factory_pid > 1
                && *factory_pid <= i32::MAX as u32
                && factory_pid == factory_tid
                && *factory_pid != self.query_pid
                && *factory_pidfd_device > 0
                && *factory_pidfd_inode > 0
                && *query_pidfd_device > 0
                && *query_pidfd_inode > 0
                && (*factory_pidfd_device, *factory_pidfd_inode)
                    != (*query_pidfd_device, *query_pidfd_inode)
                && stdio_creator.pid > 1
                && stdio_creator.pid <= i32::MAX as u32
                && stdio_creator.pid != self.query_pid
                && stdio_creator.pid != *factory_pid
                && stdio_creator.waitid_code == libc::CLD_EXITED
                && stdio_creator.waitid_status == 0
                && *release_acknowledged,
            "native UI factory/PIDFD/stdio-creator release or retirement differs",
        )?;
        let e = &self.exec;
        let n = &e.executable;
        need(
            e.query_start_ticks > 0
                && e.original_parent_pid == *factory_pid
                && e.tracer_tid == *factory_pid
                && e.waitid_code == libc::CLD_TRAPPED
                && e.waitid_status == (libc::SIGTRAP | (libc::PTRACE_EVENT_EXEC << 8))
                && e.event_previous_tid == u64::from(self.query_pid)
                && n.dev > 0
                && n.ino > 0
                && n.mode == libc::S_IFREG | 0o555
                && n.nlink == 1
                && n.bytes == profile.executable_bytes
                && (0..1_000_000_000).contains(&n.mtime_nsec)
                && (0..1_000_000_000).contains(&n.ctime_nsec)
                && e.executable_mount_id > 0
                && e.executable_sha256 == profile.executable_sha256
                && digest(&e.executable_sha256)
                && e.executable_selinux == profile.executable_selinux
                && e.process_selinux == profile.process_selinux
                && e.process_apparmor == profile.process_apparmor
                && profile.guest_uid == expected_guest_uid
                && n.uid.checked_add(profile.guest_uid) == Some(e.uid)
                && n.gid.checked_add(profile.guest_uid) == Some(e.gid)
                && e.no_new_privileges
                && e.seccomp_filter_mode == 2,
            "native UI actual TRACEEXEC/source ELF/role or mapped credentials differ",
        )
    }
}

/// Comparison transport only. Parsing this cannot create the original broker
/// observation, a live client, a UI session, or a business/acceptance fact.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatewayReply {
    schema: String,
    #[serde(deserialize_with = "closed_value")]
    request: GatewayRequest,
    #[serde(deserialize_with = "closed_value")]
    before_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed_value")]
    after_main: RuntimeMainCustody,
    stdout_base64: String,
    stderr_base64: String,
    stderr_bytes: usize,
    stderr_sha256: String,
    #[serde(deserialize_with = "closed_value")]
    receipt: ReadComparison,
}
impl GatewayReply {
    #[cfg(target_os = "linux")]
    pub(crate) fn from_observation(
        observation: &crate::production_application::NativeUiObservation,
    ) -> Result<Self, String> {
        let output = observation.output();
        let result = Self {
            schema: REPLY_SCHEMA.into(),
            request: observation.request().clone(),
            before_main: observation.before_main().clone(),
            after_main: observation.after_main().clone(),
            stdout_base64: wire::encode64(&output.stdout),
            stderr_base64: wire::encode64(&output.stderr),
            stderr_bytes: observation.stderr_bytes(),
            stderr_sha256: observation.stderr_sha256().into(),
            receipt: serde_json::from_value(
                serde_json::to_value(observation.receipt()).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?,
        };
        let reconstructed = result.output_for(observation.request())?;
        need(
            reconstructed.status == output.status
                && reconstructed.stdout == output.stdout
                && reconstructed.stderr == output.stderr,
            "native UI comparison differs from its actual retired output",
        )?;
        need(
            serde_json::to_vec(&result)
                .map_err(|e| e.to_string())?
                .len()
                <= MAX_RESPONSE_BYTES,
            "native UI bounded response exceeds its framing contract",
        )?;
        Ok(result)
    }
    pub(crate) fn output_for(&self, expected: &GatewayRequest) -> Result<Output, String> {
        expected.validate()?;
        need(
            self.schema == REPLY_SCHEMA
                && self.request == *expected
                && self.before_main == expected.main
                && self.after_main == expected.main,
            "native UI reply is for another request, complete Main, application or original end",
        )?;
        let stdout = wire::decode64_bounded(
            &self.stdout_base64,
            expected.command.stdout_limit(),
            true,
            false,
        )
        .map_err(|e| e.to_string())?;
        let stderr = wire::decode64_bounded(&self.stderr_base64, SMALL, true, false)
            .map_err(|e| e.to_string())?;
        need(
            self.stderr_bytes == stderr.len() && self.stderr_sha256 == hash(&stderr),
            "native UI complete actual stderr differs",
        )?;
        self.receipt.validate(&expected.command, &stdout)?;
        expected.deadline()?;
        Ok(Output {
            status: self.receipt.status()?,
            stdout,
            stderr,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn calendar_counts_gateway_keeps_fixed_subject_class_role_and_original_bounds() {
        let command = GatewayCommand::CalendarCounts {};
        let literal = command.literal_arguments().unwrap();
        let subject = crate::native_calendar_counts::SUBJECT;
        assert_eq!(GatewayCommand::parse(&literal, false, subject).unwrap(), command);
        assert!(GatewayCommand::parse(&literal, true, subject).is_err());
        for other in ["com.android.contacts", "com.android.providers.calendar", "com.android.settings"] {
            assert!(GatewayCommand::parse(&literal, false, other).is_err());
        }
        assert_eq!(command.guest_uid(), 10017);
        assert_eq!(command.maximum_duration(), Duration::from_secs(14));
        assert_eq!(command.stdout_limit(), 8192);
        let mut with_sql = literal.clone();
        with_sql.push("SELECT count(*) FROM Events".into());
        assert!(GatewayCommand::parse(&with_sql, false, subject).is_err());
        let mut other_class = literal;
        *other_class.last_mut().unwrap() = "com.android.commands.content.Content".into();
        assert!(GatewayCommand::parse(&other_class, false, subject).is_err());
        for input in [
            r#"{"kind":"calendar_counts","uid":0}"#,
            r#"{"kind":"calendar_counts","sql":"SELECT 1"}"#,
            r#"{"kind":"calendar_counts","database":"/data/other.db"}"#,
        ] {
            assert!(serde_json::from_str::<GatewayCommand>(input).is_err());
        }
    }

    use crate::control::application_probe::InstalledApk;

    fn subject(package: &str) -> (RuntimeMainCustody, ApplicationInspection) {
        let main = crate::main_custody::tests::sample();
        let app = ApplicationInspection {
            package: package.into(),
            user: 0,
            uid: 10_001,
            version_code: 1,
            epoch: main.epoch.clone(),
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: "/system/app/Fixture/base.apk".into(),
                bytes: 512,
                sha256: "a".repeat(64),
            }],
        };
        (main, app)
    }
    fn request(command: GatewayCommand, package: &str) -> GatewayRequest {
        let (main, app) = subject(package);
        GatewayRequest::from_owned(
            &main,
            &app,
            &command.literal_arguments().unwrap(),
            command.guest_uid() == 2000,
            Instant::now() + Duration::from_secs(5),
        )
        .unwrap()
    }
    fn helper(operation: wire::Operation) -> Vec<String> {
        wire::Request::new(SETTINGS, operation)
            .unwrap()
            .arguments()
            .unwrap()
    }

    #[test]
    fn native_ui_gateway_fixed_commands_roundtrip_with_original_roles_and_limits() {
        let mut commands = vec![
            (
                GatewayCommand::EntryCheck {
                    check: EntryCheck::GuestUid,
                },
                SETTINGS,
            ),
            (
                GatewayCommand::EntryCheck {
                    check: EntryCheck::GuestGid,
                },
                SETTINGS,
            ),
            (
                GatewayCommand::EntryCheck {
                    check: EntryCheck::BootCompleted,
                },
                SETTINGS,
            ),
            (GatewayCommand::TaskList {}, SETTINGS),
            (GatewayCommand::TaskRemove { task: 7 }, SETTINGS),
            (GatewayCommand::WindowDisplays {}, SETTINGS),
            (GatewayCommand::ScreenCapture {}, SETTINGS),
            (GatewayCommand::CameraImageIds {}, CAMERA),
            (GatewayCommand::CameraImageRow { row: 19 }, CAMERA),
            (GatewayCommand::CameraClock {}, CAMERA),
            (GatewayCommand::SettingsWindow {}, SETTINGS),
            (GatewayCommand::SettingsBack {}, SETTINGS),
        ];
        for destination in [
            SettingsDestination::AppInfo,
            SettingsDestination::Accounts,
            SettingsDestination::Apps,
            SettingsDestination::Home,
        ] {
            commands.push((
                GatewayCommand::SettingsStart {
                    destination,
                    task: 7,
                },
                SETTINGS,
            ));
        }
        for (command, package) in commands {
            let args = command.literal_arguments().unwrap();
            assert_eq!(
                GatewayCommand::parse(&args, command.guest_uid() == 2000, package).unwrap(),
                command
            );
            assert!(GatewayCommand::parse(&args, command.guest_uid() != 2000, package).is_err());
            let wire = serde_json::to_vec(&request(command.clone(), package)).unwrap();
            let decoded: GatewayRequest = serde_json::from_slice(&wire).unwrap();
            assert_eq!(decoded.command(), &command);
            decoded.validate().unwrap();
        }
        assert_eq!(GatewayCommand::ScreenCapture {}.stdout_limit(), PNG);
        assert_eq!(
            GatewayCommand::SettingsWindow {}.stdout_limit(),
            wire::WIRE_REPLY_BYTES
        );
        assert_eq!(GatewayCommand::TaskList {}.stdout_limit(), SMALL);
    }

    #[test]
    fn native_leaf_package_gateway_is_fixed_user_zero_same_application_only() {
        for command in [
            GatewayCommand::PackageIdentity { package: SETTINGS.into() },
            GatewayCommand::PackagePaths { package: SETTINGS.into() },
            GatewayCommand::PackageLauncher { package: SETTINGS.into() },
        ] {
            let literal = command.literal_arguments().unwrap();
            assert_eq!(GatewayCommand::parse(&literal, true, SETTINGS).unwrap(), command);
            assert!(GatewayCommand::parse(&literal, true, CAMERA).is_err());
            assert!(GatewayCommand::parse(&literal, false, SETTINGS).is_err());
            assert_eq!(command.guest_uid(), 2000);
            assert_eq!(command.stdout_limit(), SMALL);
            assert_eq!(command.maximum_duration(), Duration::from_secs(15));
            let mut other_user = literal.clone();
            let user = other_user.iter().position(|v| v == "--user").unwrap();
            other_user[user + 1] = "1".into();
            assert!(GatewayCommand::parse(&other_user, true, SETTINGS).is_err());
            let mut extra = literal.clone();
            extra.push("--uid".into());
            assert!(GatewayCommand::parse(&extra, true, SETTINGS).is_err());
            let mut cross = literal.clone();
            *cross.last_mut().unwrap() = CAMERA.into();
            assert!(GatewayCommand::parse(&cross, true, SETTINGS).is_err());
        }
        assert!(GatewayCommand::PackageIdentity { package: "invalid.not.selected".into() }
            .literal_arguments().is_err());
    }

    #[test]
    fn native_ui_gateway_camera_menu_is_only_fixed_camera_shell_key() {
        let literal = strings(&["/system/bin/input", "keyevent", "82"]);
        let command = GatewayCommand::parse(&literal, true, CAMERA).unwrap();
        assert_eq!(command, GatewayCommand::CameraMenu {});
        assert_eq!(command.literal_arguments().unwrap(), literal);
        assert_eq!(command.guest_uid(), 2000);
        assert_eq!(command.maximum_duration(), Duration::from_secs(15));
        assert_eq!(command.stdout_limit(), SMALL);
        assert!(GatewayCommand::parse(&literal, false, CAMERA).is_err());
        for package in [SETTINGS, "com.android.deskclock", COMPANION, "example.foreign"] {
            assert!(GatewayCommand::parse(&literal, true, package).is_err());
        }
        for key in ["082", "+82", "KEYCODE_MENU", "4", "26", "82;id"] {
            assert!(GatewayCommand::parse(&strings(&["/system/bin/input", "keyevent", key]), true, CAMERA).is_err());
        }
        let mut extra = literal;
        extra.push("extra".into());
        assert!(GatewayCommand::parse(&extra, true, CAMERA).is_err());
        let encoded = serde_json::to_value(GatewayCommand::CameraMenu {}).unwrap();
        assert_eq!(serde_json::from_value::<GatewayCommand>(encoded.clone()).unwrap(), command);
        let mut unknown = encoded;
        unknown["key"] = serde_json::Value::from(82);
        assert!(serde_json::from_value::<GatewayCommand>(unknown).is_err());
    }

    #[test]
    fn native_ui_gateway_rejects_extra_argv_foreign_scope_and_noncanonical_numbers() {
        let settings = strings(&["/system/bin/input", "keyevent", "4"]);
        assert!(GatewayCommand::parse(&settings, true, CAMERA).is_err());
        for value in ["0", "01", "+1", "-1", "2147483648", "1;id"] {
            let args = strings(&["/system/bin/cmd", "activity", "stack", "remove", value]);
            assert!(GatewayCommand::parse(&args, true, SETTINGS).is_err());
        }
        for value in ["0", "01", "9223372036854775808", "1/../../images"] {
            let args = strings(&[
                "/system/bin/content",
                "query",
                "--user",
                "0",
                "--uri",
                &format!("{IMAGES}/{value}"),
                "--projection",
                IMAGE_COLUMNS,
            ]);
            assert!(GatewayCommand::parse(&args, false, CAMERA).is_err());
        }
        for mut args in [
            strings(&["/system/bin/screencap", "-p"]),
            strings(&["/system/bin/cmd", "activity", "stack", "list"]),
            SettingsDestination::Home.arguments(7),
        ] {
            args.push("extra".into());
            assert!(GatewayCommand::parse(&args, false, SETTINGS).is_err());
            assert!(GatewayCommand::parse(&args, true, SETTINGS).is_err());
        }
        assert!(
            GatewayCommand::parse(
                &GatewayCommand::CameraImageIds {}
                    .literal_arguments()
                    .unwrap(),
                false,
                SETTINGS
            )
            .is_err()
        );
        assert!(
            GatewayCommand::parse(
                &GatewayCommand::TaskList {}.literal_arguments().unwrap(),
                true,
                "example.foreign"
            )
            .is_err()
        );
    }

    #[test]
    fn native_ui_gateway_helper_requires_exact_existing_builder_and_companion_scope() {
        for operation in [
            wire::Operation::Meta,
            wire::Operation::Dump,
            wire::Operation::Find(wire::Selector::resource_id("id").unwrap().enabled()),
            wire::Operation::Click(wire::Selector::exact_text("read only").unwrap()),
            wire::Operation::ScrollForward(wire::Selector::scrollable().enabled()),
            wire::Operation::ScrollBackward(wire::Selector::resource_id("list").unwrap().requiring_scrollable().enabled()),
            wire::Operation::SetText {
                selector: wire::Selector::editable().focused(),
                value: "旧值 🛰️ café".into(),
            },
            wire::Operation::SetText {
                selector: wire::Selector::editable(),
                value: String::new(),
            },
        ] {
            let args = helper(operation);
            let parsed = GatewayCommand::parse(&args, true, SETTINGS).unwrap();
            assert_eq!(parsed.literal_arguments().unwrap(), args);
            assert!(GatewayCommand::parse(&args, true, CAMERA).is_err());
        }
        let companion = wire::Request::permission_controller_dump()
            .arguments()
            .unwrap();
        assert!(GatewayCommand::parse(&companion, true, SETTINGS).is_ok());
        assert!(GatewayCommand::parse(&companion, true, CAMERA).is_err());
        let mut args = helper(wire::Operation::Dump);
        args[7] = "local.pocket4.other/.ActionRunner".into();
        assert!(GatewayCommand::parse(&args, true, SETTINGS).is_err());
        for raw in [
            r#"{"op":"dump","op":"dump","expected_package":"com.android.settings","display":0,"accessibility_mode":"none"}"#,
            r#"{"op":"dump","expected_package":"com.android.settings","display":0,"accessibility_mode":"none","extra":true}"#,
            r#"{"op":"dump","expected_package":"com.android.settings","display":1,"accessibility_mode":"none"}"#,
            r#"{"op":"find","expected_package":"com.android.settings","display":0,"accessibility_mode":"none","selector":{"regex":".*"}}"#,
            r#"{"op":"find","expected_package":"com.android.settings","display":0,"accessibility_mode":"none","selector":{"editable":false}}"#,
            r#"{"op":"click","expected_package":"com.android.permissioncontroller","display":0,"accessibility_mode":"none","selector":{"text":"Allow"}}"#,
        ] {
            let mut args = helper(wire::Operation::Dump);
            args[6] = wire::encode64(raw.as_bytes());
            assert!(GatewayCommand::parse(&args, true, SETTINGS).is_err());
        }
        let mut args = helper(wire::Operation::Meta);
        args[6].push('\n');
        assert!(GatewayCommand::parse(&args, true, SETTINGS).is_err());
    }

    #[test]
    fn native_ui_gateway_original_deadline_is_not_renewed_or_nested_fields_ignored() {
        let (main, app) = subject(SETTINGS);
        let end = Instant::now() + Duration::from_secs(2);
        let args = helper(wire::Operation::Meta);
        let request = GatewayRequest::from_owned(&main, &app, &args, true, end).unwrap();
        assert!(request.deadline().unwrap() <= end);
        assert!(request.deadline().unwrap() <= end);
        assert!(GatewayRequest::from_owned(&main, &app, &args, true, Instant::now()).is_err());
        let mut far = request.clone();
        far.deadline_monotonic_ns = monotonic_ns().unwrap() + 71_000_000_000;
        assert!(far.validate().is_err());
        let mut expired = request.clone();
        expired.deadline_monotonic_ns = 1;
        assert!(expired.validate().is_err());
        let mut different = request.clone();
        different.application.epoch.cell_host_pid += 1;
        assert!(different.validate().is_err());
        let original = serde_json::to_value(&request).unwrap();
        for key in ["main", "application", "command"] {
            let mut changed = original.clone();
            changed[key]
                .as_object_mut()
                .unwrap()
                .insert("unknown".into(), true.into());
            assert!(serde_json::from_value::<GatewayRequest>(changed).is_err());
        }
        let mut changed = original.clone();
        changed
            .as_object_mut()
            .unwrap()
            .insert("role".into(), 10.into());
        assert!(serde_json::from_value::<GatewayRequest>(changed).is_err());
        let raw = serde_json::to_string(&original).unwrap();
        let duplicate = raw.replacen("\"schema\":", "\"schema\":\"duplicate\",\"schema\":", 1);
        assert!(serde_json::from_str::<GatewayRequest>(&duplicate).is_err());
    }

    fn comparison_reply(request: GatewayRequest) -> GatewayReply {
        // Synthetic comparison data only, deliberately no NativeUiObservation
        // or actual Main/PM/Inspector token constructor.
        let profile =
            crate::production_application::native_ui_execution_profile(request.command()).unwrap();
        let root_uid = 100_000;
        let stdout = b"actual bytes \0\xff";
        let stderr = b"child diagnostic\n";
        GatewayReply {
            schema: REPLY_SCHEMA.into(),
            before_main: request.main.clone(),
            after_main: request.main.clone(),
            request,
            stdout_base64: wire::encode64(stdout),
            stderr_base64: wire::encode64(stderr),
            stderr_bytes: stderr.len(),
            stderr_sha256: hash(stderr),
            receipt: ReadComparison {
                schema: 2,
                lifecycle: LifecycleComparison::InstanceFactory {
                    factory_pid: 501,
                    factory_tid: 501,
                    factory_pidfd_device: 5,
                    factory_pidfd_inode: 501,
                    query_pidfd_device: 5,
                    query_pidfd_inode: 502,
                    stdio_creator: CreatorComparison {
                        pid: 503,
                        waitid_code: libc::CLD_EXITED,
                        waitid_status: 0,
                    },
                    release_acknowledged: true,
                },
                query_pid: 502,
                query_waitid_code: libc::CLD_EXITED,
                query_waitid_status: 7,
                exec: ExecComparison {
                    query_start_ticks: 99,
                    original_parent_pid: 501,
                    tracer_tid: 501,
                    waitid_code: libc::CLD_TRAPPED,
                    waitid_status: libc::SIGTRAP | (libc::PTRACE_EVENT_EXEC << 8),
                    event_previous_tid: 502,
                    executable: ExecutableNode {
                        dev: 8,
                        ino: 10,
                        mode: libc::S_IFREG | 0o555,
                        uid: root_uid,
                        gid: root_uid,
                        nlink: 1,
                        bytes: profile.executable_bytes,
                        mtime: 1,
                        mtime_nsec: 0,
                        ctime: 1,
                        ctime_nsec: 0,
                    },
                    executable_mount_id: 12,
                    executable_sha256: profile.executable_sha256.into(),
                    executable_selinux: profile.executable_selinux.into(),
                    process_selinux: profile.process_selinux.into(),
                    process_apparmor: profile.process_apparmor.into(),
                    uid: root_uid + profile.guest_uid,
                    gid: root_uid + profile.guest_uid,
                    no_new_privileges: true,
                    seccomp_filter_mode: 2,
                },
                output_bytes: stdout.len(),
                output_sha256: hash(stdout),
                elapsed_millis: 1,
                cgroup_removed: true,
            },
        }
    }
    #[test]
    fn native_ui_gateway_reply_preserves_nonzero_binary_output_and_requires_real_lifecycle_shape() {
        let request = request(
            GatewayCommand::EntryCheck {
                check: EntryCheck::GuestUid,
            },
            SETTINGS,
        );
        let reply = comparison_reply(request.clone());
        let output = reply.output_for(&request).unwrap();
        assert_eq!(output.status.code(), Some(7));
        assert_eq!(output.stdout, b"actual bytes \0\xff");
        assert_eq!(output.stderr, b"child diagnostic\n");
        let original = serde_json::to_value(&reply).unwrap();
        for (pointer, value) in [
            ("/receipt/schema", 1.into()),
            ("/receipt/cgroup_removed", false.into()),
            ("/receipt/output_sha256", "0".repeat(64).into()),
            ("/receipt/query_waitid_code", libc::CLD_STOPPED.into()),
            ("/receipt/lifecycle/release_acknowledged", false.into()),
            ("/receipt/lifecycle/stdio_creator/waitid_status", 1.into()),
            ("/receipt/lifecycle/factory_tid", 777.into()),
            ("/receipt/exec/original_parent_pid", 999.into()),
            ("/receipt/exec/tracer_tid", 999.into()),
            ("/receipt/exec/uid", 0.into()),
            ("/receipt/exec/executable_sha256", "b".repeat(64).into()),
            ("/receipt/exec/no_new_privileges", false.into()),
            ("/stderr_sha256", "c".repeat(64).into()),
            ("/after_main/epoch/cell_host_pid", 999.into()),
        ] {
            let mut value_json = original.clone();
            *value_json.pointer_mut(pointer).unwrap() = value;
            let changed: GatewayReply = serde_json::from_value(value_json).unwrap();
            assert!(changed.output_for(&request).is_err(), "{pointer}");
        }
        let mut foreign = request.clone();
        foreign.command = GatewayCommand::EntryCheck {
            check: EntryCheck::GuestGid,
        };
        assert!(reply.output_for(&foreign).is_err());
        let mut unknown = original.clone();
        unknown["receipt"]["lifecycle"]
            .as_object_mut()
            .unwrap()
            .insert("passed".into(), true.into());
        assert!(serde_json::from_value::<GatewayReply>(unknown).is_err());
        let mut legacy = original;
        legacy["receipt"]["lifecycle"]["owner"] = "legacy_broker".into();
        assert!(serde_json::from_value::<GatewayReply>(legacy).is_err());
    }

    #[test]
    fn native_ui_gateway_codec_keeps_exact_binary_empty_and_canonical_bounds() {
        assert_eq!(wire::decode64_bounded("", SMALL, true, false).unwrap(), b"");
        assert!(wire::decode64_bounded("", SMALL, false, false).is_err());
        assert_eq!(
            wire::decode64_bounded("/wA=", 2, false, false).unwrap(),
            [255, 0]
        );
        assert!(wire::decode64_bounded("/wA=", 1, false, false).is_err());
        for raw in ["Zh==", "Zg=\n", "Zg== ", "Zg=", "====", "AA=A", "Zg==Zg=="] {
            assert!(
                wire::decode64_bounded(raw, SMALL, true, false).is_err(),
                "{raw}"
            );
        }
        assert!(wire::decode64_bounded("", PNG + 1, true, false).is_err());
    }
}

/// The original APK owner uses the existing normal Query factory (30 s), not
/// the separate legacy I/P/L command's shorter 15 s cap. Both are fixed source
/// profiles; this comparison function accepts neither an argv nor a duration.
pub(crate) fn validate_apk_metadata_read(
    value:&serde_json::Value,stdout:&[u8],package:&str,paths:bool,
)->Result<(),String>{
    let receipt:ReadComparison=serde_json::from_value(value.clone()).map_err(|e|e.to_string())?;
    need(serde_json::to_value(&receipt).map_err(|e|e.to_string())?==*value,
        "APK metadata receipt has unknown fields")?;
    let kind=if paths {crate::production_application::apk_protocol::PackageReadKind::Paths}
        else {crate::production_application::apk_protocol::PackageReadKind::Identity};
    // Comparison of already source-fixed reader metadata, not UI admission.
    // Ordinary GatewayRequest::validate_subject still enforces selected39.
    need(crate::production_application::apk_scope::known_package(package),
        "APK metadata comparison is outside the fixed original role set")?;
    need(!stdout.is_empty() && stdout.len()<=SMALL && receipt.status()?.success(),
        "APK metadata output or actual query status differs")?;
    let profile=crate::production_application::apk_session_owner::package_execution_profile(kind);
    receipt.validate_profile(stdout,Duration::from_secs(30),2000,&profile)
}


/// The fixed role ordinal is resolved by the authenticated original APK slot.
/// This is a comparison decoder, not a second GatewayRequest admission path.
pub(crate) fn fixed_apk_package_output(
    value:&serde_json::Value,stdout:Vec<u8>,stderr:Vec<u8>,package:&str,
    kind:crate::production_application::apk_protocol::PackageReadKind,
)->Result<Output,String>{
    need(crate::production_application::apk_scope::known_package(package)
        && stdout.len()<=SMALL && stderr.len()<=SMALL,
        "APK PM comparison exceeds its source role or complete output bound")?;
    let receipt:ReadComparison=serde_json::from_value(value.clone()).map_err(|e|e.to_string())?;
    need(serde_json::to_value(&receipt).map_err(|e|e.to_string())?==*value,
        "APK PM real receipt has unknown fields")?;
    kind.literal_arguments(package)?;
    let profile=crate::production_application::apk_session_owner::package_execution_profile(kind);
    receipt.validate_profile(&stdout,Duration::from_secs(15),2000,&profile)?;
    Ok(Output{status:receipt.status()?,stdout,stderr})
}
