//! Fixed read-only package inspection in the actually owned production tree.
//!
//! The public worker entry has no command-line parameters. The normal broker
//! lends a ReadyTreeWitness; neither a saved receipt nor a process number can
//! select an execution target. Business/UI actions require separate adapters.
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io;
use std::os::unix::fs::MetadataExt;

use crate::control::application_probe::{AndroidProbe, ApplicationInspection, RuntimeEpoch};
use crate::production_namespace::{ApplicationAuthority, FrameworkObservation, ReadyTreeWitness};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[path = "production_application_process.rs"]
mod process;
#[path = "production_application_protocol.rs"]
mod protocol;
#[path = "production_application_worker.rs"]
mod worker;

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
    authority: &ApplicationAuthority<'_>,
    query: &ApplicationRead,
) -> Result<ApplicationReadResult> {
    query.validate()?;
    process::run(authority, query)
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
