//! Closed comparison wire for the three original preparation diagnostics.
//! These serializable records cannot construct Main custody, an execution owner,
//! or a successful observation. Only the authenticated normal client does that.
use crate::control::application_probe::ApplicationInspection;
use crate::main_custody::RuntimeMainCustody;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::os::unix::process::ExitStatusExt;
use std::process::{ExitStatus, Output};
use std::time::{Duration, Instant};

const REQUEST_SCHEMA: &str = "droidloom.preparation-read-request.v1";
const REPLY_SCHEMA: &str = "droidloom.preparation-read-reply.v1";
pub(crate) const COMMAND_LIMIT: Duration = Duration::from_secs(15);
pub(crate) const OUTPUT_LIMIT: usize = 4096;
pub(crate) const MAX_RESPONSE_BYTES: usize = 131072;

fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn digest(v: &str) -> bool {
    v.len() == 64
        && v.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// No PID, UID, argv, property name or filesystem path is a request input.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PreparationReadKind {
    GuestUid,
    GuestGid,
    BootCompleted,
}
impl PreparationReadKind {
    pub(crate) fn literal_arguments(self) -> &'static [&'static str] {
        match self {
            Self::GuestUid => &["/system/bin/toybox", "id", "-u"],
            Self::GuestGid => &["/system/bin/toybox", "id", "-g"],
            Self::BootCompleted => &["/system/bin/toolbox", "getprop", "sys.boot_completed"],
        }
    }
    pub(crate) fn expected_stdout(self) -> &'static [u8] {
        match self {
            Self::GuestUid | Self::GuestGid => b"0\n",
            Self::BootCompleted => b"1\n",
        }
    }
    pub(crate) fn filename(self) -> &'static str {
        match self {
            Self::GuestUid => "guest-uid",
            Self::GuestGid => "guest-gid",
            Self::BootCompleted => "boot-completed",
        }
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PreparationReadRequest {
    schema: String,
    #[serde(deserialize_with = "closed_value")]
    main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed_value")]
    application: ApplicationInspection,
    kind: PreparationReadKind,
    deadline_monotonic_ns: u64,
}
impl PreparationReadRequest {
    pub(crate) fn from_owned(
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
        kind: PreparationReadKind,
        end: Instant,
    ) -> Result<Self, String> {
        let clock = monotonic_ns()?;
        let now = Instant::now();
        let remaining = end
            .checked_duration_since(now)
            .filter(|v| !v.is_zero())
            .ok_or("preparation read original end elapsed")?
            .min(COMMAND_LIMIT);
        let deadline_monotonic_ns = clock
            .checked_add(
                u64::try_from(remaining.as_nanos())
                    .map_err(|_| "preparation read deadline overflow")?,
            )
            .ok_or("preparation clock overflow")?;
        let result = Self {
            schema: REQUEST_SCHEMA.into(),
            main: main.clone(),
            application: application.clone(),
            kind,
            deadline_monotonic_ns,
        };
        result.validate()?;
        Ok(result)
    }
    pub(crate) fn main(&self) -> &RuntimeMainCustody {
        &self.main
    }
    pub(crate) fn application(&self) -> &ApplicationInspection {
        &self.application
    }
    pub(crate) fn kind(&self) -> PreparationReadKind {
        self.kind
    }
    pub(crate) fn deadline(&self) -> Result<Instant, String> {
        // Restoring the absolute clock can only shorten the original caller end.
        let now = Instant::now();
        let clock = monotonic_ns()?;
        let remaining = self
            .deadline_monotonic_ns
            .checked_sub(clock)
            .filter(|v| *v != 0)
            .ok_or("preparation read original absolute end elapsed")?;
        need(
            u128::from(remaining) <= COMMAND_LIMIT.as_nanos(),
            "preparation read cap exceeded",
        )?;
        now.checked_add(Duration::from_nanos(remaining))
            .ok_or("preparation Instant overflow".into())
    }
    pub(crate) fn validate(&self) -> Result<(), String> {
        need(
            self.schema == REQUEST_SCHEMA
                && self.application.user == 0
                && self.application.uid < 100000
                && self.application.version_code > 0
                && self.main.epoch == self.application.epoch
                && crate::engine_custody::selected_package(&self.application.package),
            "preparation read requires the same actual selected user-0 Main/PM comparison",
        )?;
        self.main.validate(&self.application.epoch)?;
        let apks = &self.application.apks;
        let names: BTreeSet<_> = apks.iter().map(|v| &v.name).collect();
        let paths: BTreeSet<_> = apks.iter().map(|v| &v.path).collect();
        need(
            !apks.is_empty()
                && apks.len() <= 64
                && names.len() == apks.len()
                && paths.len() == apks.len()
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
                            .all(|v| !v.is_empty() && v != "." && v != "..")
                }),
            "preparation read complete APK comparison differs",
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
        "invalid preparation clock",
    )?;
    (value.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64))
        .ok_or("preparation monotonic overflow".into())
}
fn closed_value<'de, D, T>(deserializer: D) -> Result<T, D::Error>
where
    D: serde::Deserializer<'de>,
    T: serde::de::DeserializeOwned + Serialize,
{
    let raw = crate::native_preparation_json::unique_json_value(deserializer)?;
    let value: T = serde_json::from_value(raw.clone()).map_err(serde::de::Error::custom)?;
    if serde_json::to_value(&value).map_err(serde::de::Error::custom)? != raw {
        return Err(serde::de::Error::custom(
            "preparation comparison has unrecognized fields",
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
            _ => return Err("preparation read actual query wait status is not terminal".into()),
        };
        Ok(ExitStatus::from_raw(raw))
    }
    fn validate(&self, command: &PreparationReadKind, stdout: &[u8]) -> Result<(), String> {
        self.status()?;
        need(
            self.schema == 2
                && self.cgroup_removed
                && self.query_pid > 1
                && self.query_pid <= i32::MAX as u32
                && self.output_bytes == stdout.len()
                && self.output_sha256 == hash(stdout)
                && u128::from(self.elapsed_millis) <= COMMAND_LIMIT.as_millis(),
            "preparation read real query retirement, complete output or fixed duration differs",
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
            "preparation read factory/PIDFD/stdio-creator release or retirement differs",
        )?;
        let profile = crate::production_application::preparation_read_execution_profile(command)?;
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
                && profile.guest_uid == 0
                && n.uid.checked_add(profile.guest_uid) == Some(e.uid)
                && n.gid.checked_add(profile.guest_uid) == Some(e.gid)
                && e.no_new_privileges
                && e.seccomp_filter_mode == 2,
            "preparation read actual TRACEEXEC/source ELF/role or mapped credentials differ",
        )
    }
}

/// This is a transport comparison. Only a real accepted same-peer response may
/// be wrapped by the client's opaque PreparationReadObservation.
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PreparationReadReply {
    schema: String,
    #[serde(deserialize_with = "closed_value")]
    request: PreparationReadRequest,
    #[serde(deserialize_with = "closed_value")]
    before_main: RuntimeMainCustody,
    #[serde(deserialize_with = "closed_value")]
    after_main: RuntimeMainCustody,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    stderr_bytes: usize,
    stderr_sha256: String,
    #[serde(deserialize_with = "closed_value")]
    receipt: ReadComparison,
}
impl PreparationReadReply {
    pub(crate) fn from_observation(
        observed: &crate::production_application::PreparationReadObservation,
    ) -> Result<Self, String> {
        let output = observed.output();
        let value = Self {
            schema: REPLY_SCHEMA.into(),
            request: observed.request().clone(),
            before_main: observed.before_main().clone(),
            after_main: observed.after_main().clone(),
            stdout: output.stdout.clone(),
            stderr: output.stderr.clone(),
            stderr_bytes: observed.stderr_bytes(),
            stderr_sha256: observed.stderr_sha256().into(),
            receipt: serde_json::from_value(
                serde_json::to_value(observed.receipt()).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?,
        };
        let actual = value.output_for(observed.request())?;
        need(
            actual.status == output.status
                && actual.stdout == output.stdout
                && actual.stderr == output.stderr,
            "preparation transport changed actual retired output",
        )?;
        need(
            serde_json::to_vec(&value).map_err(|e| e.to_string())?.len() <= MAX_RESPONSE_BYTES,
            "preparation reply exceeds its complete framing bound",
        )?;
        Ok(value)
    }
    pub(crate) fn output_for(&self, expected: &PreparationReadRequest) -> Result<Output, String> {
        expected.validate()?;
        need(
            self.schema == REPLY_SCHEMA
                && self.request == *expected
                && self.before_main == expected.main
                && self.after_main == expected.main,
            "preparation reply belongs to another original request/Main/end",
        )?;
        need(
            self.stdout.len() <= OUTPUT_LIMIT
                && self.stderr.len() <= OUTPUT_LIMIT
                && self.stderr_bytes == self.stderr.len()
                && self.stderr_sha256 == hash(&self.stderr),
            "preparation complete output differs",
        )?;
        self.receipt.validate(&expected.kind, &self.stdout)?;
        expected.deadline()?;
        Ok(Output {
            status: self.receipt.status()?,
            stdout: self.stdout.clone(),
            stderr: self.stderr.clone(),
        })
    }
    pub(crate) fn matches_original(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
        kind: PreparationReadKind,
    ) -> bool {
        self.request.main == *main
            && self.request.application == *application
            && self.request.kind == kind
            && self.before_main == *main
            && self.after_main == *main
    }
    pub(crate) fn comparison(&self) -> Result<serde_json::Value, String> {
        serde_json::to_value(self).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use crate::control::application_probe::InstalledApk;

    pub(crate) fn comparison(kind: PreparationReadKind) -> PreparationReadRequest {
        let main = crate::main_custody::tests::sample();
        let application = ApplicationInspection {
            package: "com.ihg.apps.android".into(),
            user: 0,
            uid: 10137,
            version_code: 1,
            epoch: main.epoch.clone(),
            apks: vec![InstalledApk {
                name: "base.apk".into(),
                path: "/data/app/ihg/base.apk".into(),
                bytes: 1,
                sha256: "a".repeat(64),
            }],
        };
        PreparationReadRequest::from_owned(
            &main,
            &application,
            kind,
            Instant::now() + Duration::from_secs(10),
        )
        .unwrap()
    }
    #[test]
    fn preparation_read_has_only_three_literal_commands_and_guest_zero() {
        let cases = [
            (
                PreparationReadKind::GuestUid,
                "guest_uid",
                &["/system/bin/toybox", "id", "-u"][..],
                b"0\n".as_slice(),
            ),
            (
                PreparationReadKind::GuestGid,
                "guest_gid",
                &["/system/bin/toybox", "id", "-g"][..],
                b"0\n".as_slice(),
            ),
            (
                PreparationReadKind::BootCompleted,
                "boot_completed",
                &["/system/bin/toolbox", "getprop", "sys.boot_completed"][..],
                b"1\n".as_slice(),
            ),
        ];
        for (kind, name, argv, expected) in cases {
            assert_eq!(serde_json::to_string(&kind).unwrap(), format!("\"{name}\""));
            assert_eq!(kind.literal_arguments(), argv);
            assert_eq!(kind.expected_stdout(), expected);
            let profile =
                crate::production_application::preparation_read_execution_profile(&kind).unwrap();
            assert_eq!(profile.guest_uid, 0);
            assert_eq!(profile.process_selinux, "u:r:droidloom_preparation_read:s0");
        }
        for raw in [
            r#""shell""#,
            r#"{"guest_uid":{}}"#,
            r#""setprop""#,
            r#"["guest_uid"]"#,
        ] {
            assert!(serde_json::from_str::<PreparationReadKind>(raw).is_err());
        }
    }
    #[test]
    fn preparation_request_rejects_changed_main_apks_unknown_fields_and_new_deadlines() {
        let original = comparison(PreparationReadKind::BootCompleted);
        let value = serde_json::to_value(&original).unwrap();
        let mut extra = value.clone();
        extra["application"]["unexpected"] = true.into();
        assert!(serde_json::from_value::<PreparationReadRequest>(extra).is_err());
        let mut duplicate = serde_json::to_string(&value).unwrap();
        let prefix = r#""package":"com.ihg.apps.android""#;
        duplicate = duplicate.replacen(
            prefix,
            &format!(r#"{prefix},"package":"com.ihg.apps.android""#),
            1,
        );
        assert!(serde_json::from_str::<PreparationReadRequest>(&duplicate).is_err());
        for case in 0..6 {
            let mut changed = original.clone();
            match case {
                0 => changed.application.epoch.framework_start_ticks += 1,
                1 => changed
                    .application
                    .apks
                    .push(changed.application.apks[0].clone()),
                2 => changed.application.user = 1,
                3 => changed.application.package = "not.source.selected".into(),
                4 => changed.deadline_monotonic_ns = 1,
                _ => changed.deadline_monotonic_ns = monotonic_ns().unwrap() + 30_000_000_000,
            }
            assert!(changed.validate().is_err(), "mutation {case}");
        }
    }
    fn receipt() -> ReadComparison {
        let p = crate::production_application::preparation_read_execution_profile(
            &PreparationReadKind::GuestUid,
        )
        .unwrap();
        ReadComparison {
            schema: 2,
            lifecycle: LifecycleComparison::InstanceFactory {
                factory_pid: 100,
                factory_tid: 100,
                factory_pidfd_device: 5,
                factory_pidfd_inode: 10,
                query_pidfd_device: 5,
                query_pidfd_inode: 11,
                stdio_creator: CreatorComparison {
                    pid: 101,
                    waitid_code: libc::CLD_EXITED,
                    waitid_status: 0,
                },
                release_acknowledged: true,
            },
            query_pid: 102,
            query_waitid_code: libc::CLD_EXITED,
            query_waitid_status: 0,
            exec: ExecComparison {
                query_start_ticks: 200,
                original_parent_pid: 100,
                tracer_tid: 100,
                waitid_code: libc::CLD_TRAPPED,
                waitid_status: libc::SIGTRAP | (libc::PTRACE_EVENT_EXEC << 8),
                event_previous_tid: 102,
                executable: ExecutableNode {
                    dev: 4,
                    ino: 11,
                    mode: libc::S_IFREG | 0o555,
                    uid: 2000000,
                    gid: 2000000,
                    nlink: 1,
                    bytes: p.executable_bytes,
                    mtime: 1,
                    mtime_nsec: 0,
                    ctime: 1,
                    ctime_nsec: 0,
                },
                executable_mount_id: 4,
                executable_sha256: p.executable_sha256.into(),
                executable_selinux: p.executable_selinux.into(),
                process_selinux: p.process_selinux.into(),
                process_apparmor: p.process_apparmor.into(),
                uid: 2000000,
                gid: 2000000,
                no_new_privileges: true,
                seccomp_filter_mode: 2,
            },
            output_bytes: 2,
            output_sha256: hash(b"0\n"),
            elapsed_millis: 1,
            cgroup_removed: true,
        }
    }
    #[test]
    fn preparation_receipt_comparison_requires_traceexec_and_actual_retirement_shape() {
        // These are wire comparisons only: this does not construct an opaque
        // observation, a Ready owner or a real-execution result.
        receipt()
            .validate(&PreparationReadKind::GuestUid, b"0\n")
            .unwrap();
        for case in 0..8 {
            let mut altered = receipt();
            match case {
                0 => altered.cgroup_removed = false,
                1 => {
                    let LifecycleComparison::InstanceFactory {
                        release_acknowledged,
                        ..
                    } = &mut altered.lifecycle;
                    *release_acknowledged = false;
                }
                2 => altered.exec.process_selinux = "u:r:droidloom_query:s0".into(),
                3 => altered.exec.uid += 2000,
                4 => altered.exec.event_previous_tid += 1,
                5 => altered.exec.executable.bytes += 1,
                6 => altered.output_sha256 = "b".repeat(64),
                _ => altered.query_waitid_code = libc::CLD_STOPPED,
            }
            assert!(
                altered
                    .validate(&PreparationReadKind::GuestUid, b"0\n")
                    .is_err(),
                "mutation {case}"
            );
        }
        let mut nonzero = receipt();
        nonzero.query_waitid_status = 9;
        nonzero
            .validate(&PreparationReadKind::GuestUid, b"0\n")
            .unwrap();
        assert_eq!(nonzero.status().unwrap().code(), Some(9));
    }
}
