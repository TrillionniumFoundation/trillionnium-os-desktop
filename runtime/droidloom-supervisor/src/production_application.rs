//! Fixed package inspection, owned Firefox entry and fixed Contacts provider reads.
//!
//! The public worker entry has no command-line parameters. The normal broker
//! lends a ReadyTreeWitness; neither a saved receipt nor a process number can
//! select an execution target. The explicit Firefox adapter adds two closed
//! commands; Contacts has a separate read-only Java role and no UI acceptance.
//! The original four-read API remains unchanged.
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io;
use std::os::unix::fs::MetadataExt;

use crate::control::application_probe::{AndroidProbe, ApplicationInspection, RuntimeEpoch};
use crate::production_namespace::{ApplicationAuthority, FrameworkObservation, ReadyTreeWitness};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[path = "production_application_custody.rs"]
mod custody;
pub(crate) use custody::{ProductionInspection, inspect_with_custody};

#[path = "production_application_business.rs"]
mod business;
#[path = "production_application_launch.rs"]
mod launch;
pub(crate) use launch::LaunchObservation;
#[path = "production_application_task_control.rs"]
mod task_control;
pub(crate) use task_control::ApplicationTaskControl;
#[path = "production_application_contacts.rs"]
mod contacts;
pub(crate) use contacts::{ContactsBaselineObservation, ContactsQuery};
#[path = "production_application_launch_command.rs"]
mod launch_command;
#[path = "production_application_operation.rs"]
mod operation;
pub(crate) use launch_command::LaunchCommand;
use operation::ApplicationOperation;
pub(crate) use operation::{BrowserCommand, OperationDomain};

#[path = "production_application_process.rs"]
mod process;
#[path = "production_application_protocol.rs"]
mod protocol;
#[path = "production_application_worker.rs"]
mod worker;
pub(crate) use worker::{CloneArgs as FrontendCloneArgs, SignalMask as FrontendSignalMask};

/// Borrowed execution authority. Implementations retain their actual original
/// owner; no request, PID, receipt, or serialized Ready state implements this.
/// The same closed worker and actual waitid/cgroup retirement path serve both
/// the legacy namespace owner and the boot-created early owner.
/// Only two source-owned fixed locations exist. This is sent on the private
/// parent-authenticated worker channel, never accepted as a public path.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryProjection {
    LegacyRoot,
    EarlyDev,
}
impl QueryProjection {
    fn content_classpath(self) -> &'static CStr {
        match self {
            Self::LegacyRoot => c"CLASSPATH=/.droidloom-query/content.jar",
            Self::EarlyDev => c"CLASSPATH=/dev/droidloom-query/content.jar",
        }
    }
}

pub(crate) trait ApplicationWorkerAuthority {
    fn query_projection(&self) -> QueryProjection;
    fn revalidate(&self) -> std::result::Result<(), crate::production_namespace::NamespaceError>;
    fn descriptors(&self, binary: &CStr) -> std::result::Result<Vec<File>, crate::production_namespace::NamespaceError>;
    fn contacts_content_descriptors(&self) -> std::result::Result<[File; 2], crate::production_namespace::NamespaceError>;
    fn mapped_root(&self) -> std::result::Result<(u32, u32), crate::production_namespace::NamespaceError>;
    fn leaf(&self) -> std::result::Result<crate::production_cgroup::ApplicationLeaf<'_>, crate::production_namespace::NamespaceError>;
    fn bind_created_process(&self, pidfd: &std::os::fd::OwnedFd, query: bool) -> std::result::Result<(File, u32), crate::production_namespace::NamespaceError>;
    fn progress_inherited_native(&self, deadline: std::time::Instant) -> std::result::Result<(), crate::production_namespace::NamespaceError>;
}

pub(crate) const WORKER_ARGUMENT: &str = "__production-application-read";
const OUTPUT_LIMIT: usize = 65536;
const QUERY_LIMIT: std::time::Duration = std::time::Duration::from_secs(30);
const RETIRE_LIMIT: std::time::Duration = std::time::Duration::from_secs(3);

/// A rejected query, changed capability, or actual process lifecycle failure.
#[derive(Debug, Error)]
pub enum ApplicationError {
    /// Inputs or current kernel observations did not satisfy the fixed contract.
    #[error("production application read rejected: {0}")]
    Rejected(String),
    /// Actual owned children were not all reaped; the original lease is retained.
    #[error("production application retirement unproven; original ownership quarantined")]
    RetirementUnproven,
    /// A required syscall failed. No numeric process fallback is used.
    #[error(transparent)]
    Io(#[from] io::Error),
}
type Result<T> = std::result::Result<T, ApplicationError>;
fn reject(text: impl Into<String>) -> ApplicationError {
    ApplicationError::Rejected(text.into())
}
fn require(value: bool, message: &'static str) -> Result<()> {
    if value { Ok(()) } else { Err(reject(message)) }
}
fn external(error: impl std::fmt::Display) -> ApplicationError {
    reject(error.to_string())
}

/// Deliberately finite. There is no shell, general argv, user-selected binary,
/// arbitrary file read, activity launch, account operation, or install command.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "query", deny_unknown_fields)]
pub(crate) enum ApplicationRead {
    PackageIdentity { package: String, user: u32 },
    PackagePaths { package: String, user: u32 },
    ApkStat { path: String },
    ApkSha256 { path: String },
}

fn package_valid(package: &str) -> bool {
    package.len() <= 255
        && package.contains('.')
        && package.split('.').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
        })
}
fn apk_valid(path: &str) -> bool {
    path.len() <= 512
        && path.is_ascii()
        && path.ends_with(".apk")
        && [
            "/data/app/",
            "/system/",
            "/system_ext/",
            "/product/",
            "/vendor/",
            "/odm/",
            "/oem/",
            "/apex/",
        ]
        .iter()
        .any(|prefix| path.starts_with(prefix))
        && !path
            .split('/')
            .skip(1)
            .any(|part| part.is_empty() || part == "." || part == "..")
        && !path
            .bytes()
            .any(|byte| byte.is_ascii_control() || byte.is_ascii_whitespace())
}

impl ApplicationRead {
    fn validate(&self) -> Result<()> {
        match self {
            Self::PackageIdentity { package, user } | Self::PackagePaths { package, user } => {
                require(
                    package_valid(package) && *user <= 21_474,
                    "invalid package or Android user",
                )
            }
            Self::ApkStat { path } | Self::ApkSha256 { path } => {
                require(apk_valid(path), "not a bounded public installed APK path")
            }
        }
    }

    fn from_command(args: &[String]) -> Result<Self> {
        let text: Vec<&str> = args.iter().map(String::as_str).collect();
        let result = match text.as_slice() {
            [
                "/system/bin/cmd",
                "package",
                "list",
                "packages",
                "--user",
                user,
                "-U",
                "--show-versioncode",
                package,
            ] => Self::PackageIdentity {
                package: (*package).into(),
                user: canonical_user(user)?,
            },
            [
                "/system/bin/cmd",
                "package",
                "path",
                "--user",
                user,
                package,
            ] => Self::PackagePaths {
                package: (*package).into(),
                user: canonical_user(user)?,
            },
            ["/system/bin/toybox", "stat", "-c", "%d:%i:%s:%y:%z", path] => Self::ApkStat {
                path: (*path).into(),
            },
            ["/system/bin/toybox", "sha256sum", path] => Self::ApkSha256 {
                path: (*path).into(),
            },
            _ => return Err(reject("command is outside the fixed production read set")),
        };
        result.validate()?;
        Ok(result)
    }

    pub(crate) fn binary(&self) -> &'static CStr {
        match self {
            Self::PackageIdentity { .. } | Self::PackagePaths { .. } => c"cmd",
            _ => c"toybox",
        }
    }

    fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let values: Vec<String> = match self {
            Self::PackageIdentity { package, user } => vec![
                "/system/bin/cmd".into(),
                "package".into(),
                "list".into(),
                "packages".into(),
                "--user".into(),
                user.to_string(),
                "-U".into(),
                "--show-versioncode".into(),
                package.clone(),
            ],
            Self::PackagePaths { package, user } => vec![
                "/system/bin/cmd".into(),
                "package".into(),
                "path".into(),
                "--user".into(),
                user.to_string(),
                package.clone(),
            ],
            Self::ApkStat { path } => vec![
                "/system/bin/toybox".into(),
                "stat".into(),
                "-c".into(),
                "%d:%i:%s:%y:%z".into(),
                path.clone(),
            ],
            Self::ApkSha256 { path } => vec![
                "/system/bin/toybox".into(),
                "sha256sum".into(),
                path.clone(),
            ],
        };
        values
            .into_iter()
            .map(|value| CString::new(value).map_err(|_| reject("NUL in fixed query")))
            .collect()
    }
}
fn canonical_user(text: &str) -> Result<u32> {
    let user: u32 = text.parse().map_err(|_| reject("invalid Android user"))?;
    require(text == user.to_string(), "Android user is not canonical")?;
    Ok(user)
}

/// Real output plus exact syscall retirement evidence. No deserializer or
/// caller-supplied success boolean can create this value.
pub(crate) struct ApplicationReadResult {
    output: String,
    receipt: ReadReceipt,
}
pub(crate) struct BrowserCommandResult {
    output: String,
    receipt: ReadReceipt,
}
pub(crate) struct ContactsReadResult {
    output: String,
    receipt: ReadReceipt,
}
pub(crate) struct LaunchCommandResult {
    output: std::process::Output,
    receipt: ReadReceipt,
    stderr_bytes: usize,
    stderr_sha256: String,
    operation_deadline: std::time::Instant,
}
#[derive(Debug, Serialize)]
pub(crate) struct BridgeReceipt {
    worker_pid: u32,
    worker_waitid_code: i32,
    worker_waitid_status: i32,
    elapsed_millis: u64,
    cgroup_removed: bool,
}
pub(crate) struct BridgeConnection {
    socket: File,
    receipt: BridgeReceipt,
}
struct OperationResult {
    output: String,
    receipt: ReadReceipt,
}
#[derive(Debug, Serialize)]
pub(crate) struct ReadReceipt {
    worker_pid: u32,
    worker_waitid_code: i32,
    worker_waitid_status: i32,
    query_pid: u32,
    query_waitid_code: i32,
    query_waitid_status: i32,
    exec: process::ExecReceipt,
    output_bytes: usize,
    output_sha256: String,
    elapsed_millis: u64,
    cgroup_removed: bool,
}

pub(crate) struct ApplicationRetired<'a> {
    children: &'a process::Children,
}
impl ApplicationRetired<'_> {
    pub(crate) fn verify_cgroup(&self, file: &File) -> Result<()> {
        self.children.verify_retirement()?;
        let m = file.metadata()?;
        require(
            (m.dev(), m.ino()) == self.children.cgroup_identity,
            "retirement proof belongs to a different leaf",
        )
    }
}

pub(crate) fn run(
    authority: &dyn ApplicationWorkerAuthority,
    query: &ApplicationRead,
) -> Result<ApplicationReadResult> {
    run_read_before(authority, query, std::time::Instant::now() + QUERY_LIMIT)
}

pub(crate) fn run_read_before(
    authority: &dyn ApplicationWorkerAuthority,
    query: &ApplicationRead,
    deadline: std::time::Instant,
) -> Result<ApplicationReadResult> {
    query.validate()?;
    let result = process::run(
        authority,
        &ApplicationOperation::Read {
            value: query.clone(),
        },
        deadline,
    )?;
    Ok(ApplicationReadResult {
        output: result.output,
        receipt: result.receipt,
    })
}

pub(crate) fn run_launch_command(
    authority: &dyn ApplicationWorkerAuthority,
    command: &LaunchCommand,
    deadline: std::time::Instant,
) -> Result<LaunchCommandResult> {
    command.validate()?;
    process::run_launch(authority, command, deadline)
}

pub(crate) fn run_browser_command(
    authority: &dyn ApplicationWorkerAuthority,
    command: &BrowserCommand,
    deadline: std::time::Instant,
) -> Result<BrowserCommandResult> {
    command.validate()?;
    let result = process::run(
        authority,
        &ApplicationOperation::Browser {
            value: command.clone(),
        },
        deadline,
    )?;
    Ok(BrowserCommandResult {
        output: result.output,
        receipt: result.receipt,
    })
}

pub(crate) fn run_contacts_read(
    authority: &dyn ApplicationWorkerAuthority,
    query: &ContactsQuery,
    deadline: std::time::Instant,
) -> Result<ContactsReadResult> {
    query.validate()?;
    let result = process::run(
        authority,
        &ApplicationOperation::ContactsRead {
            value: query.clone(),
        },
        deadline,
    )?;
    Ok(ContactsReadResult {
        output: result.output,
        receipt: result.receipt,
    })
}

pub(crate) fn inspect_contacts_baseline(
    ready: ReadyTreeWitness<'_>,
    contacts: &ApplicationInspection,
    provider: &ApplicationInspection,
) -> Result<ContactsBaselineObservation> {
    contacts::baseline(ready, contacts, provider)
}

pub(crate) fn launch_application(
    ready: ReadyTreeWitness<'_>,
    request: &droidloom_task_launcher::LaunchRequest,
    deadline: std::time::Instant,
) -> Result<LaunchObservation> {
    launch::launch(ready, request, deadline)
}

pub(crate) fn connect_task_control(
    authority: &ApplicationAuthority<'_>,
    package: &str,
    deadline: std::time::Instant,
) -> Result<ApplicationTaskControl> {
    task_control::connect(authority, package, deadline)
}

pub(crate) fn open_browser(
    ready: ReadyTreeWitness<'_>,
    expected: &ApplicationInspection,
    url: &str,
) -> Result<(ApplicationInspection, String)> {
    business::open(ready, expected, url)
}

struct ProductionProbe<'a> {
    ready: ReadyTreeWitness<'a>,
    framework: FrameworkObservation,
    reads: Vec<ReadReceipt>,
    deadline: std::time::Instant,
}
impl AndroidProbe for ProductionProbe<'_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        if std::time::Instant::now() >= self.deadline {
            return Err("production inspection deadline".into());
        }
        self.ready
            .application_epoch(&self.framework)
            .map_err(|error| error.to_string())
    }
    fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
        if std::time::Instant::now() >= self.deadline || self.reads.len() >= 200 {
            return Err("production inspection query bound".into());
        }
        let query = ApplicationRead::from_command(args).map_err(|error| error.to_string())?;
        let result = self
            .ready
            .run_application_read(&query)
            .map_err(|error| error.to_string())?;
        self.reads.push(result.receipt);
        Ok(result.output)
    }
}

pub(crate) fn inspect(
    mut ready: ReadyTreeWitness<'_>,
    package: &str,
    user: u32,
) -> Result<ApplicationInspection> {
    require(
        package_valid(package) && user <= 21_474,
        "invalid package inspection",
    )?;
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(300);
    let framework = ready.observe_application_framework().map_err(external)?;
    let mut probe = ProductionProbe {
        ready,
        framework,
        reads: Vec::new(),
        deadline,
    };
    let inspection =
        crate::control::application_probe::inspect(&mut probe, package, user).map_err(external)?;
    require(
        !probe.reads.is_empty()
            && probe.reads.iter().all(|row| {
                row.cgroup_removed
                    && row.worker_waitid_code == libc::CLD_EXITED
                    && row.worker_waitid_status == 0
                    && row.query_waitid_code == libc::CLD_EXITED
                    && row.query_waitid_status == 0
            }),
        "inspection has incomplete real read retirement",
    )?;
    Ok(inspection)
}

/// Internal fresh-image dispatch. It accepts only authenticated inherited
/// descriptor custody from the original broker, never command-line inputs.
///
/// # Errors
/// Rejects an ordinary caller, missing original descriptors, a changed owner,
/// or any failed namespace, clone, or fixed-query preparation operation.
pub fn run_application_read_worker() -> Result<()> {
    worker::entry()
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).into()).collect()
    }
    #[test]
    fn production_application_read_has_four_exact_real_commands() {
        for query in [
            ApplicationRead::PackageIdentity {
                package: "org.mozilla.firefox".into(),
                user: 0,
            },
            ApplicationRead::PackagePaths {
                package: "org.mozilla.firefox".into(),
                user: 10,
            },
            ApplicationRead::ApkStat {
                path: "/data/app/abc/base.apk".into(),
            },
            ApplicationRead::ApkSha256 {
                path: "/product/app/Clock/Clock.apk".into(),
            },
        ] {
            let roundtrip = query
                .arguments()
                .unwrap()
                .into_iter()
                .map(|value| value.into_string().unwrap())
                .collect::<Vec<_>>();
            assert_eq!(ApplicationRead::from_command(&roundtrip).unwrap(), query);
        }
    }
    #[test]
    fn production_application_read_rejects_mutation_and_non_apk_reads() {
        for command in [
            args(&["/system/bin/cmd", "package", "clear", "org.mozilla.firefox"]),
            args(&["/system/bin/sh", "-c", "id"]),
            args(&[
                "/system/bin/toybox",
                "sha256sum",
                "/data/user/0/org.example/prefs.apk",
            ]),
            args(&[
                "/system/bin/toybox",
                "sha256sum",
                "/data/app/../user/secret.apk",
            ]),
            args(&[
                "/system/bin/cmd",
                "package",
                "path",
                "--user",
                "00",
                "org.example.app",
            ]),
        ] {
            assert!(ApplicationRead::from_command(&command).is_err());
        }
    }
    #[test]
    fn production_application_read_wire_cannot_add_authority() {
        assert!(
            serde_json::from_str::<ApplicationRead>(
                r#"{"query":"PackagePaths","package":"org.example.app","user":0,"pid":123}"#
            )
            .is_err()
        );
        assert!(
            serde_json::from_str::<ApplicationRead>(r#"{"query":"Command","argv":["true"]}"#)
                .is_err()
        );
        assert!(!apk_valid("/data/app/a\nb.apk"));
        assert!(!apk_valid("/data/app/a/./base.apk"));
        assert!(!apk_valid("/data/app//base.apk"));
        assert!(!package_valid("org.example;id"));
    }
}
