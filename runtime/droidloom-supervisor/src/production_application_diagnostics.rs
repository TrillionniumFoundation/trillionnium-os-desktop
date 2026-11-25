//! Closed, bounded diagnostics borrowed from the original kernel-first owner.
//! Output availability and Android readiness are separate observations. Neither
//! a formatter failure nor a partial report may hide unproven child retirement.
use super::*;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use std::time::Instant;

pub(super) const TAIL_BYTES: usize = 128 * 1024;
pub(super) const ERROR_TAIL_BYTES: usize = 16 * 1024;
pub(super) const TRAFFIC_LIMIT: usize = 32 * 1024 * 1024;

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(super) enum DiagnosticBuffer {
    MainSystemCrash,
    Crash,
    Events,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "diagnostic", deny_unknown_fields)]
pub(super) enum DiagnosticCommand {
    PackageUid {
        package: String,
        user: u32,
    },
    Log {
        buffer: DiagnosticBuffer,
        lines: Option<u32>,
        uid: Option<u32>,
    },
    ExitHistory {
        package: Option<String>,
    },
}
impl DiagnosticCommand {
    pub(super) fn validate(&self) -> Result<()> {
        match self {
            Self::PackageUid { package, user } => require(
                package_valid(package) && *user <= 21_474,
                "invalid diagnostic package or user",
            ),
            Self::ExitHistory { package } => require(
                package.as_deref().is_none_or(package_valid),
                "invalid exit-history package",
            ),
            Self::Log { buffer, lines, uid } => {
                let valid = match (buffer, lines, uid) {
                    (DiagnosticBuffer::MainSystemCrash, Some(n), None)
                    | (DiagnosticBuffer::Crash, Some(n), None) => (1..=2000).contains(n),
                    (DiagnosticBuffer::Events, Some(2000), None) => true,
                    (DiagnosticBuffer::MainSystemCrash, None, Some(n)) => *n <= i32::MAX as u32,
                    _ => false,
                };
                require(
                    valid,
                    "log buffer, line bound or UID filter is outside the fixed diagnostic set",
                )
            }
        }
    }
    pub(super) const fn binary(&self) -> &'static CStr {
        match self {
            Self::PackageUid { .. } => c"cmd",
            Self::Log { .. } => c"logcat",
            Self::ExitHistory { .. } => c"dumpsys",
        }
    }
    pub(super) const fn binary_events(&self) -> bool {
        matches!(
            self,
            Self::Log {
                buffer: DiagnosticBuffer::Events,
                ..
            }
        )
    }
    pub(super) const fn stdout_limit(&self) -> usize {
        if self.binary_events() {
            super::event_log::OUTPUT_BYTES
        } else {
            TAIL_BYTES
        }
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        if self.binary_events() {
            // Stock binary output bypasses liblog's optional dynamic-tag-map
            // probe. The request still permits only the fixed 2000-event dump.
            return [
                "/system/bin/logcat",
                "-d",
                "-b",
                "events",
                "-B",
                "-t",
                "2000",
            ]
            .into_iter()
            .map(|v| CString::new(v).map_err(external))
            .collect();
        }
        self.formatter_arguments()
    }
    fn formatter_arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let args: Vec<String> = match self {
            Self::PackageUid { package, user } => vec![
                "/system/bin/cmd".into(),
                "package".into(),
                "list".into(),
                "packages".into(),
                "-U".into(),
                "--user".into(),
                user.to_string(),
                package.clone(),
            ],
            Self::Log { buffer, lines, uid } => {
                let selected = match buffer {
                    DiagnosticBuffer::MainSystemCrash => "main,system,crash",
                    DiagnosticBuffer::Crash => "crash",
                    DiagnosticBuffer::Events => "events",
                };
                let mut args = [
                    "/system/bin/logcat",
                    "-d",
                    "-b",
                    selected,
                    "-v",
                    "threadtime",
                    "-v",
                    "printable",
                ]
                .into_iter()
                .map(str::to_owned)
                .collect::<Vec<_>>();
                if let Some(lines) = lines {
                    args.extend(["-t".into(), lines.to_string()]);
                }
                if let Some(uid) = uid {
                    args.push(format!("--uid={uid}"));
                }
                args.push("*:V".into());
                args
            }
            Self::ExitHistory { package } => {
                let mut args = ["/system/bin/dumpsys", "-t", "5", "activity", "exit-info"]
                    .into_iter()
                    .map(str::to_owned)
                    .collect::<Vec<_>>();
                if let Some(package) = package {
                    args.push(package.clone());
                }
                args
            }
        };
        args.into_iter()
            .map(|value| CString::new(value).map_err(external))
            .collect()
    }
}

/// The Android domain defaults include logging writes. This extra inherited
/// filter admits only the stock read transport's AF_UNIX/SOCK_SEQPACKET socket;
/// AppArmor path mediation independently fixes /dev/socket/logdr. No listener,
/// datagram, Internet endpoint or socketpair can be manufactured by this role.
pub(super) fn filter() -> Vec<libc::sock_filter> {
    let mut f = super::worker::query_filter();
    assert_eq!(f.pop().map(|v| v.k), Some(0x7fff_0000));
    let ins = |code, jt, jf, k| libc::sock_filter { code, jt, jf, k };
    let deny = 0x0005_0000 | libc::EPERM as u32;
    f.extend([
        ins(0x15, 0, 11, libc::SYS_socket as u32),
        ins(0x20, 0, 0, 16),
        ins(0x15, 1, 0, libc::AF_UNIX as u32),
        ins(0x06, 0, 0, deny),
        ins(0x20, 0, 0, 24),
        ins(
            0x54,
            0,
            0,
            !((libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK) as u32),
        ),
        ins(0x15, 1, 0, libc::SOCK_SEQPACKET as u32),
        ins(0x06, 0, 0, deny),
        ins(0x20, 0, 0, 32),
        ins(0x15, 1, 0, 0),
        ins(0x06, 0, 0, deny),
        ins(0x06, 0, 0, 0x7fff_0000),
    ]);
    for nr in [
        libc::SYS_socketpair,
        libc::SYS_bind,
        libc::SYS_listen,
        libc::SYS_accept,
        libc::SYS_accept4,
    ] {
        f.extend([ins(0x15, 0, 1, nr as u32), ins(0x06, 0, 0, deny)]);
    }
    f.push(ins(0x06, 0, 0, 0x7fff_0000));
    f
}

/// A request-local sequence accepts only the formatter's exact fixed calls.
/// A package log UID is supplied by the actual PackageManager result, never
/// by the public client, a process number, or an unrelated listing row.
struct Plan<'a> {
    package: Option<&'a str>,
    user: u32,
    lines: u32,
    crashes: bool,
    step: usize,
    uid: Option<u32>,
}
impl<'a> Plan<'a> {
    fn new(package: Option<&'a str>, user: u32, lines: u32, crashes: bool) -> Result<Self> {
        require(
            package.is_none_or(package_valid) && user <= 21_474 && (1..=2000).contains(&lines),
            "invalid fixed diagnostic request",
        )?;
        Ok(Self {
            package,
            user,
            lines,
            crashes,
            step: 0,
            uid: None,
        })
    }
    fn count(&self) -> usize {
        if self.crashes {
            2 + usize::from(self.package.is_some())
        } else {
            1 + usize::from(self.package.is_some())
        }
    }
    fn next(&mut self, args: &[String]) -> Result<DiagnosticCommand> {
        let command = if self.crashes {
            match self.step {
                0 => DiagnosticCommand::Log {
                    buffer: DiagnosticBuffer::Crash,
                    lines: Some(self.lines),
                    uid: None,
                },
                1 => DiagnosticCommand::ExitHistory {
                    package: self.package.map(str::to_owned),
                },
                2 if self.package.is_some() => DiagnosticCommand::Log {
                    buffer: DiagnosticBuffer::Events,
                    lines: Some(2000),
                    uid: None,
                },
                _ => return Err(reject("diagnostic request repeated or added a command")),
            }
        } else if let Some(package) = self.package {
            match self.step {
                0 => DiagnosticCommand::PackageUid {
                    package: package.into(),
                    user: self.user,
                },
                1 => DiagnosticCommand::Log {
                    buffer: DiagnosticBuffer::MainSystemCrash,
                    lines: None,
                    uid: Some(
                        self.uid
                            .ok_or_else(|| reject("diagnostic package UID was not observed"))?,
                    ),
                },
                _ => return Err(reject("diagnostic request repeated or added a command")),
            }
        } else if self.step == 0 {
            DiagnosticCommand::Log {
                buffer: DiagnosticBuffer::MainSystemCrash,
                lines: Some(self.lines),
                uid: None,
            }
        } else {
            return Err(reject("diagnostic request repeated or added a command"));
        };
        let expected = command.formatter_arguments()?;
        require(
            expected.len() == args.len()
                && expected
                    .iter()
                    .zip(args)
                    .all(|(left, right)| left.to_bytes() == right.as_bytes()),
            "diagnostic formatter command differs from its bound public request",
        )?;
        self.step += 1;
        Ok(command)
    }
    fn observed(&mut self, command: &DiagnosticCommand, output: &str) -> Result<()> {
        if let DiagnosticCommand::PackageUid { package, user } = command {
            let mut actual = None;
            for line in output.lines() {
                let fields: Vec<_> = line.split_ascii_whitespace().collect();
                if fields.first().copied() != Some(format!("package:{package}").as_str()) {
                    continue;
                }
                require(
                    fields.len() == 2 && actual.is_none(),
                    "ambiguous diagnostic package UID listing",
                )?;
                let text = fields[1]
                    .strip_prefix("uid:")
                    .ok_or_else(|| reject("diagnostic package listing lacks UID"))?;
                let uid: u32 = text.parse().map_err(external)?;
                require(
                    uid.to_string() == text && uid <= i32::MAX as u32 && uid / 100_000 == *user,
                    "diagnostic package UID belongs to another Android user",
                )?;
                actual = Some(uid);
            }
            self.uid = Some(actual.ok_or_else(|| {
                reject("requested diagnostic package is not installed for this user")
            })?);
        }
        Ok(())
    }
}
fn namespace_error(error: crate::production_namespace::NamespaceError) -> ApplicationError {
    match error {
        crate::production_namespace::NamespaceError::RetirementUnproven => {
            ApplicationError::RetirementUnproven
        }
        value => external(value),
    }
}
pub(super) fn tail_text(bytes: &[u8], limit: usize) -> String {
    if bytes.len() > limit {
        format!(
            "[Older output omitted: showing the last {limit} bytes]\n{}",
            String::from_utf8_lossy(&bytes[bytes.len() - limit..])
        )
    } else {
        String::from_utf8_lossy(bytes).into_owned()
    }
}
fn collect_with(
    package: Option<&str>,
    user: u32,
    lines: u32,
    crashes: bool,
    mut execute: impl FnMut(&DiagnosticCommand) -> Result<String>,
) -> Result<String> {
    let mut plan = Plan::new(package, user, lines, crashes)?;
    let mut quarantined = false;
    let mut sequence_failed = false;
    let output = crate::control::render_diagnostics(package, user, lines, crashes, |args| {
        let attempt = (|| {
            require(
                !quarantined && !sequence_failed,
                "diagnostic owner or sequence is no longer usable",
            )?;
            let command = plan.next(args).inspect_err(|_| sequence_failed = true)?;
            let text = execute(&command)?;
            plan.observed(&command, &text)
                .inspect_err(|_| sequence_failed = true)?;
            Ok(text)
        })();
        if matches!(attempt, Err(ApplicationError::RetirementUnproven)) {
            quarantined = true;
        }
        attempt.map_err(|error: ApplicationError| {
            crate::control::ControlError::Invalid(error.to_string())
        })
    });
    if quarantined {
        return Err(ApplicationError::RetirementUnproven);
    }
    require(
        !sequence_failed,
        "diagnostic fixed command sequence was rejected",
    )?;
    let text = output.map_err(external)?;
    require(
        plan.step == plan.count(),
        "diagnostic report has an incomplete fixed command sequence",
    )?;
    Ok(text)
}

pub(crate) fn diagnostics_early(
    authority: &EarlyApplicationAuthority<'_>,
    package: Option<&str>,
    user: u32,
    lines: u32,
    crashes: bool,
    overall_deadline: Instant,
) -> Result<String> {
    let borrowed = authority.diagnostic_authority().map_err(namespace_error)?;
    let deadline = (Instant::now() + QUERY_LIMIT).min(overall_deadline);
    let output = collect_with(package, user, lines, crashes, |command| {
        borrowed
            .progress_inherited_native(deadline)
            .map_err(namespace_error)?;
        let request = ApplicationOperation::Diagnostics {
            value: command.clone(),
        };
        let result = workflow::finish_effect(
            factory_query::run(&borrowed, &request, deadline),
            || borrowed.revalidate().map_err(namespace_error),
            deadline,
        )?;
        eprintln!(
            "droidloom-diagnostics-read {}",
            serde_json::to_string(&serde_json::json!({"command":command,"receipt":result.receipt, "output_scope":if command.binary_events() { "bounded_binary_events" } else { "retained_tail" }, "stdout_truncated":result.output.stdout.len()>command.stdout_limit(), "stderr_truncated":result.output.stderr.len()>ERROR_TAIL_BYTES, "traffic_limit_bytes":TRAFFIC_LIMIT}))
                .map_err(external)?
        );
        if !result.output.status.success() {
            return Err(reject(format!(
                "fixed diagnostic command exited {}: {}",
                result.output.status,
                tail_text(&result.output.stderr, ERROR_TAIL_BYTES)
            )));
        }
        require(
            result.receipt.successful_retirement(),
            "diagnostic process has no normal complete retirement",
        )?;
        require(
            result.output.stderr.is_empty(),
            "fixed diagnostic command reported an error",
        )?;
        if command.binary_events() {
            super::event_log::decode(&result.output.stdout)
        } else if matches!(command, DiagnosticCommand::PackageUid { .. }) {
            require(
                result.output.stdout.len() <= TAIL_BYTES,
                "package UID listing exceeded its complete-output bound",
            )?;
            String::from_utf8(result.output.stdout).map_err(external)
        } else {
            Ok(tail_text(&result.output.stdout, TAIL_BYTES))
        }
    });
    workflow::finish_effect(
        output,
        || borrowed.revalidate().map_err(namespace_error),
        deadline,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(command: &DiagnosticCommand) -> Vec<String> {
        command
            .arguments()
            .unwrap()
            .into_iter()
            .map(|v| v.into_string().unwrap())
            .collect()
    }
    #[test]
    fn diagnostics_uid_is_bound_to_actual_exact_package_and_user_before_log_read() {
        let mut plan = Plan::new(Some("org.example.app"), 10, 80, false).unwrap();
        let uid = DiagnosticCommand::PackageUid {
            package: "org.example.app".into(),
            user: 10,
        };
        assert_eq!(plan.next(&args(&uid)).unwrap(), uid);
        for output in [
            "package:org.example.app uid:10000\n",
            "package:org.example.app2 uid:1010000\n",
            "package:org.example.app uid:1010000\npackage:org.example.app uid:1010000\n",
        ] {
            assert!(plan.observed(&uid, output).is_err());
        }
        plan.observed(
            &uid,
            "package:org.example.app2 uid:1010001\npackage:org.example.app uid:1010000\n",
        )
        .unwrap();
        let log = DiagnosticCommand::Log {
            buffer: DiagnosticBuffer::MainSystemCrash,
            lines: None,
            uid: Some(1010000),
        };
        let mut bad = args(&log);
        bad.push("-c".into());
        assert!(plan.next(&bad).is_err());
        let wrong = DiagnosticCommand::Log {
            buffer: DiagnosticBuffer::MainSystemCrash,
            lines: None,
            uid: Some(1010001),
        };
        assert!(plan.next(&args(&wrong)).is_err());
        assert_eq!(plan.next(&args(&log)).unwrap(), log);
        assert!(plan.next(&args(&log)).is_err());
    }
    #[test]
    fn diagnostics_quarantine_overrides_optional_sections_and_stops_further_execution() {
        let mut count = 0;
        let result = collect_with(Some("org.example.app"), 0, 30, true, |_| {
            count += 1;
            Err(ApplicationError::RetirementUnproven)
        });
        assert!(matches!(result, Err(ApplicationError::RetirementUnproven)));
        assert_eq!(count, 1);
        let mut count = 0;
        let result = collect_with(Some("org.example.app"), 0, 30, true, |command| {
            count += 1;
            match command {
                DiagnosticCommand::Log {
                    buffer: DiagnosticBuffer::Crash,
                    ..
                } => Err(reject("logd absent")),
                DiagnosticCommand::ExitHistory { .. } => {
                    Ok("ApplicationExitInfo #0: observed\n".into())
                }
                _ => Ok(String::new()),
            }
        })
        .unwrap();
        assert_eq!(count, 3);
        assert!(result.contains("Unavailable:"));
        assert!(result.contains("ApplicationExitInfo #0"));
    }
    #[test]
    fn diagnostics_has_only_fixed_read_commands_and_explicit_bounded_tail() {
        for message in [
            r#"{"diagnostic":"Log","buffer":"security","lines":20,"uid":null}"#,
            r#"{"diagnostic":"ExitHistory","package":null,"service":"account"}"#,
            r#"{"diagnostic":"PackageUid","package":"org.example.app","user":0,"pid":123}"#,
        ] {
            assert!(serde_json::from_str::<DiagnosticCommand>(message).is_err());
        }
        for command in [
            DiagnosticCommand::Log {
                buffer: DiagnosticBuffer::Events,
                lines: Some(1),
                uid: None,
            },
            DiagnosticCommand::Log {
                buffer: DiagnosticBuffer::Crash,
                lines: None,
                uid: Some(10000),
            },
            DiagnosticCommand::Log {
                buffer: DiagnosticBuffer::MainSystemCrash,
                lines: Some(10),
                uid: Some(10000),
            },
            DiagnosticCommand::PackageUid {
                package: "org.example.app;id".into(),
                user: 0,
            },
        ] {
            assert!(command.validate().is_err());
        }
        assert_eq!(
            tail_text(b"abcdef", 4),
            "[Older output omitted: showing the last 4 bytes]\ncdef"
        );
        let operation = ApplicationOperation::Diagnostics {
            value: DiagnosticCommand::ExitHistory { package: None },
        };
        assert_eq!(operation.domain(), OperationDomain::DiagnosticsRead);
        assert_eq!(operation.binary(), c"dumpsys");
        assert_eq!(operation.domain().gid(), 1007);
        assert_eq!(OperationDomain::Query.gid(), 2000);
        assert!(!operation.uses_app_process());
        assert_eq!(operation.descriptor_count(), 15);
    }

    #[test]
    fn diagnostics_seccomp_allows_only_the_real_read_socket_kind() {
        let program = filter();
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            unsafe {
                if libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
                    libc::_exit(81);
                }
            }
            if super::super::query_io::install_filter(&program).is_err() {
                unsafe {
                    libc::_exit(82);
                }
            }
            for flags in [0, libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK] {
                let fd = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_SEQPACKET | flags, 0) };
                if fd < 0 {
                    unsafe {
                        libc::_exit(83);
                    }
                }
                unsafe {
                    libc::close(fd);
                }
            }
            for (domain, kind, protocol) in [
                (libc::AF_UNIX, libc::SOCK_STREAM, 0),
                (libc::AF_UNIX, libc::SOCK_DGRAM | libc::SOCK_CLOEXEC, 0),
                (libc::AF_INET, libc::SOCK_SEQPACKET, 0),
                (libc::AF_UNIX, libc::SOCK_SEQPACKET, 1),
            ] {
                let fd = unsafe { libc::socket(domain, kind, protocol) };
                if fd != -1 || std::io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe {
                        libc::_exit(84);
                    }
                }
            }
            for nr in [
                libc::SYS_socketpair,
                libc::SYS_bind,
                libc::SYS_listen,
                libc::SYS_accept,
                libc::SYS_accept4,
                libc::SYS_setns,
                libc::SYS_ptrace,
            ] {
                let rc = unsafe { libc::syscall(nr, -1_i64, 0_i64, 0_i64, 0_i64, 0_i64, 0_i64) };
                if rc != -1 || std::io::Error::last_os_error().raw_os_error() != Some(libc::EPERM) {
                    unsafe {
                        libc::_exit(85);
                    }
                }
            }
            unsafe {
                libc::_exit(0);
            }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert!(libc::WIFEXITED(status));
        assert_eq!(libc::WEXITSTATUS(status), 0);
    }
}
