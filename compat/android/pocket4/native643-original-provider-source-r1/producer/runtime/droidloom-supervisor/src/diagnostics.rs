//! Read-only, bounded Android diagnostics. No caller-selected executable or shell.

use std::collections::VecDeque;
use std::fmt::Write as _;
use std::io::{self, Read};
use std::process::{Command, Stdio};
use std::thread;

use super::{ControlError, io_error};

const MAX_OUTPUT: usize = 128 * 1024;

pub(super) fn collect(
    pid: u32,
    package: Option<&str>,
    user: u32,
    lines: u32,
    crashes: bool,
) -> Result<String, ControlError> {
    collect_with(package, user, lines, crashes, |args| {
        let mut command = droidloom_cpu_placement::command("/usr/bin/timeout");
        command
            .args(["--kill-after=1s", "10s", "/usr/bin/nsenter", "--target"])
            .arg(pid.to_string())
            .args([
                "--mount", "--uts", "--ipc", "--net", "--pid", "--cgroup", "--root", "--wd",
                "--env", "--",
            ])
            .args(args);
        capture(&mut command)
    })
}

fn collect_with(
    package: Option<&str>,
    user: u32,
    lines: u32,
    crashes: bool,
    mut run: impl FnMut(&[String]) -> Result<String, ControlError>,
) -> Result<String, ControlError> {
    let mut args: Vec<String> = [
        "/system/bin/logcat",
        "-d",
        "-b",
        if crashes {
            "crash"
        } else {
            "main,system,crash"
        },
        "-v",
        "threadtime",
        "-v",
        "printable",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    if !(1..=2000).contains(&lines) {
        return Err(ControlError::Invalid(
            "diagnostic line limit must be between 1 and 2000".into(),
        ));
    }
    // logcat applies a numeric -t at the logd reader, BEFORE client-side UID
    // filtering. A noisy unrelated app must not hide retained target logs.
    // Package requests therefore filter the complete retained snapshot first;
    // capture still has its existing 10s deadline and 128-KiB bounded tail.
    if crashes || package.is_none() {
        args.extend(["-t".to_owned(), lines.to_string()]);
    }
    if !crashes && let Some(package) = package {
        let listing = run(&[
            "/system/bin/cmd".into(),
            "package".into(),
            "list".into(),
            "packages".into(),
            "-U".into(),
            "--user".into(),
            user.to_string(),
            package.into(),
        ])?;
        let uid = package_uid(&listing, package)?;
        args.push(format!("--uid={uid}"));
    }
    // Explicit filter avoids inheriting Android's ambient log tag filters.
    args.push("*:V".into());
    let logs = run(&args);
    if !crashes {
        return logs.map(|text| {
            if text.trim().is_empty() {
                "No matching log entries in the retained Android buffers.\n".into()
            } else if package.is_some() {
                matched_tail(&text, lines as usize)
            } else {
                text
            }
        });
    }

    let mut exit_args = vec![
        "/system/bin/dumpsys".into(),
        "-t".into(),
        "5".into(),
        "activity".into(),
        "exit-info".into(),
    ];
    if let Some(package) = package {
        exit_args.push(package.into());
    }
    let exits = run(&exit_args).and_then(checked_exit_history);
    // System_server owns activity lifecycle events, so an app-UID logcat filter
    // cannot see them. Sample the bounded global *events* ring separately and
    // keep only exact process-package matches. This does NOT identify a SIGKILL
    // sender; it describes the resulting ActivityManager actions.
    let lifecycle = package.map(|name| collect_lifecycle_sample(name, &mut run));
    if let (Err(log_error), Err(exit_error)) = (&logs, &exits) {
        return Err(ControlError::Invalid(format!(
            "crash buffer unavailable: {log_error}; exit history unavailable: {exit_error}"
        )));
    }
    // Keep global crash traces: native crash reporters and system_server may
    // write under different UIDs, after the app process has already exited.
    let section = |result: Result<String, ControlError>| match result {
        Ok(text) if text.trim().is_empty() => "No retained entries.\n".into(),
        Ok(text) => text,
        Err(error) => format!("Unavailable: {error}\n"),
    };
    let mut output = format!(
        "=== Recent crash buffer (all apps, including system crash reporters) ===\n{}\n=== Recorded process exits ({}) ===\n{}",
        section(logs),
        package.unwrap_or("all apps"),
        section(exits)
    );
    if let (Some(name), Some(events)) = (package, lifecycle) {
        write!(
            &mut output,
            "\n=== Sampled app lifecycle events ({name}; NOT a SIGKILL sender attribution) ===\n{}",
            section(events)
        )
        .expect("formatting into a String cannot fail");
    }
    Ok(output)
}

fn collect_lifecycle_sample(
    package: &str,
    run: &mut impl FnMut(&[String]) -> Result<String, ControlError>,
) -> Result<String, ControlError> {
    let args: Vec<String> = [
        "/system/bin/logcat",
        "-d",
        "-b",
        "events",
        "-v",
        "threadtime",
        "-v",
        "printable",
        "-t",
        "2000",
        "*:V",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    run(&args).map(|raw| sampled_lifecycle_events(&raw, package))
}

/// Exact Android process name comparison, including :named app subprocesses.
/// Prefix-neighbor applications are never part of the target's events.
fn process_belongs_to_package(process: &str, package: &str) -> bool {
    process == package
        || process
            .strip_prefix(package)
            .is_some_and(|rest| rest.starts_with(':'))
}

/// Android event-log payloads are positional; use the process-name field rather
/// than a broad substring search which could leak unrelated apps' lifecycle.
/// Android event records identify a victim, not necessarily a signal sender.
fn lifecycle_event_belongs_to_package(line: &str, package: &str) -> bool {
    let Some((prefix, body)) = line.split_once(": [") else {
        return false;
    };
    let Some(tag) = prefix.split_whitespace().last() else {
        return false;
    };
    let values: Vec<_> = body.trim_end_matches(']').split(',').collect();
    match tag {
        "am_proc_start" => values
            .get(3)
            .is_some_and(|name| process_belongs_to_package(name.trim(), package)),
        "am_proc_bound" | "am_proc_died" | "am_kill" | "am_crash" | "am_anr" => values
            .get(2)
            .is_some_and(|name| process_belongs_to_package(name.trim(), package)),
        "am_schedule_service_restart" => values
            .get(1)
            .and_then(|service| service.trim().split_once('/'))
            .is_some_and(|(owner, _)| owner == package),
        _ => false,
    }
}

/// Keep a bounded and explicitly incomplete recent event-log sample. Logcat's
/// global '-t' and the transport's 128-KiB byte tail can omit earlier events.
/// Consequently an empty sample is NOT proof that an app never exited.
fn sampled_lifecycle_events(raw: &str, package: &str) -> String {
    const MAX_MATCHED_LINES: usize = 48;
    const MAX_LINE_CHARS: usize = 512;
    let mut lines = VecDeque::with_capacity(MAX_MATCHED_LINES);
    let mut omitted = false;
    for line in raw.lines() {
        if lifecycle_event_belongs_to_package(line, package) {
            if lines.len() == MAX_MATCHED_LINES {
                lines.pop_front();
                omitted = true;
            }
            lines.push_back(line.chars().take(MAX_LINE_CHARS).collect::<String>());
        }
    }
    let mut result =
        "[Recent global logd event sample only; earlier events may be absent.]\n".to_owned();
    if raw.starts_with("[Older output omitted:") {
        result.push_str("[Global event snapshot was byte-truncated before package filtering.]\n");
    }
    if omitted {
        result.push_str("[Older package-matched events omitted from bounded display.]\n");
    }
    if lines.is_empty() {
        result.push_str(
            "No matching app lifecycle events in this recent sample (not proof of no exits).\n",
        );
    } else {
        for line in lines {
            result.push_str(&line);
            result.push('\n');
        }
    }
    result
}

// Return the latest UID-matched rendered lines, preserving truncation notices.
// This never parses text as a new command or broadens access to other UIDs.
fn matched_tail(text: &str, limit: usize) -> String {
    let (notice, body) = if text.starts_with("[Older output omitted:") {
        text.split_once('\n')
            .map_or(("", text), |(first, rest)| (first, rest))
    } else {
        ("", text)
    };
    let mut recent = VecDeque::with_capacity(limit);
    let mut omitted = false;
    for line in body.lines() {
        if recent.len() == limit {
            recent.pop_front();
            omitted = true;
        }
        recent.push_back(line);
    }
    let mut output = String::new();
    if !notice.is_empty() {
        output.push_str(notice);
        output.push('\n');
    }
    if omitted {
        writeln!(
            &mut output,
            "[Older UID-matched lines omitted: showing the last {limit} rendered lines]"
        )
        .expect("formatting into a String cannot fail");
    }
    for line in recent {
        output.push_str(line);
        output.push('\n');
    }
    output
}

fn checked_exit_history(text: String) -> Result<String, ControlError> {
    // dumpsys can return exit status zero while the service is missing or its
    // Binder dump timed out. Do not label that as a successful empty history.
    let first = text
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .unwrap_or("");
    let unavailable = first.starts_with("Can't find service:")
        || first.starts_with("Error dumping service info:")
        || text.lines().any(|line| {
            line.trim()
                .starts_with("*** SERVICE 'activity' DUMP TIMEOUT")
        });
    if unavailable {
        Err(ControlError::Invalid(format!(
            "Android activity exit history unavailable: {}",
            text.trim()
        )))
    } else {
        Ok(text)
    }
}

fn package_uid(listing: &str, package: &str) -> Result<u32, ControlError> {
    let expected = format!("package:{package}");
    for line in listing.lines() {
        let mut fields = line.split_whitespace();
        if fields.next() == Some(expected.as_str()) {
            return fields
                .find_map(|field| field.strip_prefix("uid:"))
                .and_then(|uid| uid.parse().ok())
                .ok_or_else(|| {
                    ControlError::Invalid("Android returned an invalid package UID".into())
                });
        }
    }
    Err(ControlError::Invalid(format!(
        "package {package} is not installed for the selected Android user"
    )))
}

fn read_tail(mut reader: impl Read, limit: usize) -> io::Result<String> {
    let mut tail = VecDeque::with_capacity(limit);
    let mut buffer = [0; 8192];
    let mut truncated = false;
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        for byte in &buffer[..count] {
            if tail.len() == limit {
                tail.pop_front();
                truncated = true;
            }
            tail.push_back(*byte);
        }
    }
    let bytes: Vec<u8> = tail.into_iter().collect();
    let text = String::from_utf8_lossy(&bytes);
    Ok(if truncated {
        format!("[Older output omitted: showing the last {limit} bytes]\n{text}")
    } else {
        text.into_owned()
    })
}

fn capture(command: &mut Command) -> Result<String, ControlError> {
    capture_with_stdin(command, Stdio::null())
}

pub(super) fn capture_with_stdin(
    command: &mut Command,
    stdin: Stdio,
) -> Result<String, ControlError> {
    let mut child = command
        .stdin(stdin)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|source| io_error("start Android command", source))?;
    let stdout = child.stdout.take().expect("piped stdout");
    let stderr = child.stderr.take().expect("piped stderr");
    let (status, stdout, stderr) = thread::scope(|scope| {
        let out = scope.spawn(|| read_tail(stdout, MAX_OUTPUT));
        let err = scope.spawn(|| read_tail(stderr, 16 * 1024));
        (child.wait(), out.join(), err.join())
    });
    let status = status.map_err(|source| io_error("wait for Android command", source))?;
    let read = |result: thread::Result<io::Result<String>>| {
        result
            .map_err(|_| ControlError::Invalid("Android command output reader failed".into()))?
            .map_err(|source| io_error("read Android command output", source))
    };
    let stdout = read(stdout)?;
    let stderr = read(stderr)?;
    if !status.success() {
        if matches!(status.code(), Some(124 | 137)) {
            return Err(super::android_operation_timeout("Android command"));
        }
        return Err(ControlError::Invalid(format!(
            "Android command failed ({status}): {stderr}{stdout}"
        )));
    }
    Ok(if stderr.is_empty() {
        stdout
    } else {
        format!("{stdout}\n{stderr}")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn package_log_filter_precedes_the_rendered_tail() {
        let mut calls = Vec::new();
        let result = collect_with(Some("com.example.app"), 0, 2, false, |args| {
            calls.push(args.to_vec());
            Ok(if args[0] == "/system/bin/cmd" {
                "package:com.example.app uid:10001\n".into()
            } else {
                assert!(!args.iter().any(|arg| arg == "-t" || arg == "-T"));
                assert!(args.iter().any(|arg| arg == "--uid=10001"));
                "old matching line\nretained cause\nlast target line\n".into()
            })
        })
        .unwrap();
        assert!(result.contains("retained cause\nlast target line\n"));
        assert!(!result.contains("old matching line"));
        assert!(result.contains("last 2 rendered lines"));
        assert_eq!(calls.len(), 2);
    }

    #[test]
    fn unrelated_global_tail_cannot_make_package_logs_falsely_empty() {
        let result = collect_with(Some("com.example.app"), 0, 1, false, |args| {
            Ok(if args[0] == "/system/bin/cmd" {
                "package:com.example.app uid:10001\n".into()
            } else if args.iter().any(|arg| arg == "-t") {
                String::new() // logd selected only newer unrelated records
            } else {
                "retained target failure\n".into()
            })
        })
        .unwrap();
        assert_eq!(result, "retained target failure\n");
    }

    #[test]
    fn unfiltered_and_crash_log_reads_retain_the_global_limit() {
        for crashes in [false, true] {
            collect_with(None, 0, 7, crashes, |args| {
                if args[0] == "/system/bin/logcat" {
                    assert!(args.windows(2).any(|pair| pair == ["-t", "7"]));
                    assert!(!args.iter().any(|arg| arg.starts_with("--uid=")));
                }
                Ok(String::new())
            })
            .unwrap();
        }
    }

    #[test]
    fn uid_tail_preserves_byte_truncation_notice_and_unicode() {
        let result = matched_tail(
            "[Older output omitted: showing the last 20 bytes]\n旧记录\n最新故障\n",
            1,
        );
        assert!(result.starts_with("[Older output omitted:"));
        assert!(result.ends_with("最新故障\n"));
        assert!(!result.contains("旧记录"));
    }

    #[test]
    fn missing_service_with_zero_status_is_marked_unavailable() {
        let result = collect_with(Some("com.example.app"), 0, 10, true, |args| {
            Ok(if args[0] == "/system/bin/logcat" {
                "native backtrace\n".into()
            } else {
                "\nCan't find service: activity\n".into()
            })
        })
        .unwrap();
        assert!(result.contains("native backtrace"));
        assert!(result.contains("Unavailable: Android activity exit history unavailable:"));
        assert!(!result.contains("No retained entries."));
    }

    #[test]
    fn two_unavailable_sections_do_not_report_success() {
        let result = collect_with(None, 0, 10, true, |args| {
            if args[0] == "/system/bin/logcat" {
                Err(ControlError::Invalid("logd unavailable".into()))
            } else {
                Ok("Can't find service: activity\n".into())
            }
        });
        assert!(result.is_err());
    }

    #[test]
    fn binder_timeout_is_not_a_valid_exit_history() {
        assert!(checked_exit_history("ACTIVITY MANAGER PROCESS EXIT INFO\n*** SERVICE 'activity' DUMP TIMEOUT (5000ms) EXPIRED ***\n".into()).is_err());
        assert!(
            checked_exit_history("Error dumping service info: (Failure calling service)\n".into())
                .is_err()
        );
    }

    #[test]
    fn quoted_error_in_a_real_description_does_not_hide_history() {
        let data =
            "ACTIVITY MANAGER PROCESS EXIT INFO\n description=Can't find service: activity\n";
        assert_eq!(checked_exit_history(data.into()).unwrap(), data);
        assert_eq!(checked_exit_history(String::new()).unwrap(), "");
    }

    #[test]
    fn invalid_line_bounds_do_not_contact_android() {
        for lines in [0, 2001, u32::MAX] {
            assert!(
                collect_with(Some("com.example.app"), 0, lines, false, |_| panic!(
                    "must reject first"
                ))
                .is_err()
            );
        }
    }

    #[test]
    fn logs_use_installed_uid_even_when_the_process_is_dead() {
        let mut calls = Vec::new();
        let result = collect_with(Some("com.example.app"), 10, 200, false, |args| {
            calls.push(args.to_vec());
            Ok(if calls.len() == 1 {
                "package:com.example.app.extra uid:1010002\npackage:com.example.app uid:1010001\n"
                    .into()
            } else {
                "retained stack trace\n".into()
            })
        })
        .unwrap();
        assert_eq!(result, "retained stack trace\n");
        assert!(calls[0].windows(2).any(|args| args == ["--user", "10"]));
        assert!(calls[1].contains(&"--uid=1010001".into()));
        assert!(!calls[1].iter().any(|arg| arg.starts_with("--pid")));
        assert!(package_uid("package:com.example.app.extra uid:10001", "com.example.app").is_err());
        assert!(package_uid("package:com.example.app uid:oops", "com.example.app").is_err());
    }

    #[test]
    fn crash_report_keeps_native_traces_when_activity_service_is_down() {
        let report = collect_with(Some("com.example.app"), 0, 200, true, |args| {
            assert!(!args.iter().any(|arg| arg.starts_with("--uid")));
            if args[0] == "/system/bin/logcat" {
                Ok("DEBUG: native backtrace from crash_dump64\n".into())
            } else {
                assert_eq!(args.last().unwrap(), "com.example.app");
                Err(ControlError::Invalid("activity service unavailable".into()))
            }
        })
        .unwrap();
        assert!(report.contains("native backtrace"));
        assert!(report.contains("Unavailable: activity service unavailable"));
    }

    #[test]
    fn oversized_output_keeps_bounded_tail_and_announces_truncation() {
        let output = read_tail(&b"old records\nlatest trace\n"[..], 13).unwrap();
        assert!(output.starts_with("[Older output omitted:"));
        assert!(output.ends_with("latest trace\n"));
        assert!(!output.contains("old records"));
    }

    #[test]
    fn lifecycle_events_match_exact_packages_not_prefix_neighbors() {
        let ok = [
            "10-14 08:51:47.408 841 3300 I am_proc_died: [0,4348,tv.danmaku.bili,0,19]",
            "10-14 08:51:47.409 841 3300 I am_kill : [0,2740,tv.danmaku.bili:download,905,depends on provider,463832]",
            "10-14 08:51:54.063 841 874 I am_proc_start: [0,4551,10115,tv.danmaku.bili,content provider,{}]",
            "10-14 08:51:54.207 841 3733 I am_proc_bound: [0,4551,tv.danmaku.bili]",
            "10-14 08:51:54.949 841 874 I am_schedule_service_restart: [0,tv.danmaku.bili/com.bilibili.example.Service,40000]",
        ];
        for line in ok {
            assert!(
                lifecycle_event_belongs_to_package(line, "tv.danmaku.bili"),
                "{line}"
            );
        }
        for line in [
            "10-14 08:51:47.408 841 3300 I am_proc_died: [0,4348,tv.danmaku.bili.evil,0,19]",
            "10-14 08:51:47.408 841 3300 I am_proc_died: [0,4348,tv.danmaku.bilidownload,0,19]",
            "10-14 08:51:47.408 841 3300 I am_proc_died: [0,4348,another.package,tv.danmaku.bili]",
            "10-14 08:51:47.408 841 3300 I am_kill : [0,4348,another.package,reason contains tv.danmaku.bili]",
            "10-14 08:51:47.408 841 3300 I am_wtf : [0,841,system_server,ActivityTaskManager,tv.danmaku.bili]",
            "logcat: buffer unavailable",
            "10-14 08:51:47.408 841 3300 I am_proc_died: malformed",
        ] {
            assert!(
                !lifecycle_event_belongs_to_package(line, "tv.danmaku.bili"),
                "{line}"
            );
        }
    }

    #[test]
    fn sampled_lifecycle_events_are_bounded_and_explicitly_not_exhaustive() {
        let mut raw = String::from("[Older output omitted: showing the last 131072 bytes]\n");
        for idx in 0..55 {
            writeln!(
                &mut raw,
                "10-14 08:51:47.408 841 3300 I am_proc_died: [0,{idx},tv.danmaku.bili,0,19]"
            )
            .unwrap();
            raw.push_str(
                "10-14 08:51:47.408 841 3300 I am_proc_died: [0,9,tv.danmaku.bili.extra,0,19]\n",
            );
        }
        let display = sampled_lifecycle_events(&raw, "tv.danmaku.bili");
        assert!(display.contains("byte-truncated"));
        assert!(display.contains("Older package-matched events omitted"));
        assert!(!display.contains("bili.extra"));
        assert!(!display.contains("[0,0,tv.danmaku.bili,"));
        assert!(display.contains("[0,54,tv.danmaku.bili,"));
        assert_eq!(
            display
                .lines()
                .filter(|line| line.contains("am_proc_died"))
                .count(),
            48
        );
        let empty = sampled_lifecycle_events("", "tv.danmaku.bili");
        assert!(empty.contains("not proof of no exits"));
    }

    #[test]
    fn crash_report_preserves_exits_when_event_buffer_unavailable() {
        let mut calls = Vec::new();
        let report = collect_with(Some("tv.danmaku.bili"), 0, 40, true, |args| {
            calls.push(args.to_vec());
            if args.first().map(String::as_str) == Some("/system/bin/logcat")
                && args.windows(2).any(|a| a == ["-b", "events"])
            {
                Err(ControlError::Invalid("event logd unavailable".into()))
            } else if args.first().map(String::as_str) == Some("/system/bin/logcat") {
                Ok("crash buffer retained\n".into())
            } else {
                Ok("ACTIVITY MANAGER PROCESS EXIT INFO\n".into())
            }
        })
        .unwrap();
        assert!(report.contains("crash buffer retained"));
        assert!(report.contains("ACTIVITY MANAGER PROCESS EXIT INFO"));
        assert!(report.contains("Unavailable: event logd unavailable"));
        assert_eq!(calls.len(), 3);
        assert!(!calls[2].iter().any(|arg| arg.starts_with("--uid=")));
    }

    #[test]
    fn sampled_events_do_not_claim_system_kill_sender_or_change_global_requests() {
        let mut calls = 0;
        let report=collect_with(Some("tv.danmaku.bili"),0,200,true,|args| {
            calls+=1;
            if args.windows(2).any(|w|w==["-b","events"]) {
                Ok("10-14 08:51:47.409 841 3300 I am_kill : [0,2740,tv.danmaku.bili:download,905,depends on provider,463832]\\n".into())
            } else if args[0]=="/system/bin/logcat" {
                Ok("native backtrace\n".into())
            } else { Ok("ACTIVITY MANAGER PROCESS EXIT INFO\n".into()) }
        }).unwrap();
        assert_eq!(calls, 3);
        assert!(report.contains("am_kill"));
        assert!(report.contains("NOT a SIGKILL sender attribution"));
        let mut global_calls = 0;
        collect_with(None, 0, 200, true, |_| {
            global_calls += 1;
            Ok(String::new())
        })
        .unwrap();
        assert_eq!(global_calls, 2);
    }

    #[test]
    fn timed_out_commands_report_failure() {
        let mut command = droidloom_cpu_placement::command("/usr/bin/timeout");
        command.args(["--kill-after=0.1s", "0.1s", "/usr/bin/sleep", "5"]);
        let started = std::time::Instant::now();
        let error = capture(&mut command).unwrap_err().to_string();
        assert!(error.contains("Android looks stuck"));
        assert!(error.contains("journalctl -b -u droidloomd.service"));
        assert!(started.elapsed() < std::time::Duration::from_secs(3));
    }
}
