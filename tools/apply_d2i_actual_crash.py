#!/usr/bin/env python3
"""Upgrade the D2I product runtime from simulated WebView replacement to an exact content-process crash proof."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


runtime = "runtime/servo/hepta_workspace_runtime.rs"

replace_once(
    runtime,
    "use std::error::Error;\nuse std::fs;\nuse std::path::{Path, PathBuf};\nuse std::rc::Rc;\nuse std::time::{Duration, Instant};\n",
    "use std::env;\nuse std::error::Error;\nuse std::fs;\nuse std::io::ErrorKind;\nuse std::path::{Path, PathBuf};\nuse std::process::Command;\nuse std::rc::Rc;\nuse std::thread;\nuse std::time::{Duration, Instant};\n",
)
replace_once(
    runtime,
    "    MouseButtonAction, MouseButtonEvent, MouseMoveEvent, RenderingContext, Servo, ServoBuilder,\n    WebView, WebViewBuilder, WheelDelta, WheelEvent, WheelMode, WindowRenderingContext,\n",
    "    MouseButtonAction, MouseButtonEvent, MouseMoveEvent, Opts, RenderingContext, Servo,\n    ServoBuilder, WebView, WebViewBuilder, WheelDelta, WheelEvent, WheelMode,\n    WindowRenderingContext, run_content_process,\n",
)
replace_once(
    runtime,
    "fn main() -> Result<(), Box<dyn Error>> {\n    rustls::crypto::aws_lc_rs::default_provider()\n",
    "fn main() -> Result<(), Box<dyn Error>> {\n    if let Some(token) = content_process_token() {\n        run_content_process(token);\n        return Ok(());\n    }\n\n    rustls::crypto::aws_lc_rs::default_provider()\n",
)
replace_once(
    runtime,
    "struct RuntimeState {\n",
    "fn content_process_token() -> Option<String> {\n    let mut arguments = env::args();\n    while let Some(argument) = arguments.next() {\n        if argument == \"--content-process\" {\n            return arguments.next();\n        }\n    }\n    None\n}\n\nstruct RuntimeState {\n",
)
replace_once(
    runtime,
    "    popup_requests_denied: Cell<u64>,\n    actual_crash_callbacks: Cell<u64>,\n    generation: Cell<u64>,\n",
    "    popup_requests_denied: Cell<u64>,\n    actual_crash_callbacks: Cell<u64>,\n    crash_triggered: Cell<bool>,\n    content_process_termination_observed: Cell<bool>,\n    content_process_pid: Cell<u32>,\n    content_process_start_time: Cell<u64>,\n    generation: Cell<u64>,\n",
)
replace_once(
    runtime,
    "    fn begin_recovery(self: &Rc<Self>) {\n",
    '''    fn trigger_content_crash(self: &Rc<Self>) {
        if self.crash_triggered.replace(true) {
            return;
        }
        let content_pid = match exact_content_process_pid() {
            Ok(pid) => pid,
            Err(error) => {
                self.write_evidence(&format!("FAIL_CONTENT_PROCESS_DISCOVERY:{error}"));
                return;
            }
        };
        let start_time = match exact_content_process_start_time(content_pid) {
            Ok(start_time) => start_time,
            Err(error) => {
                self.write_evidence(&format!("FAIL_CONTENT_PROCESS_IDENTITY:{error}"));
                return;
            }
        };
        self.content_process_pid.set(content_pid);
        self.content_process_start_time.set(start_time);
        let _ = fs::write(
            self.output.join("content-process-identity.json"),
            format!(
                "{{\\n  \\\"pid\\\": {content_pid},\\n  \\\"start_time_ticks\\\": {start_time}\\n}}\\n"
            ),
        );

        let status = match Command::new("/bin/kill")
            .args(["-KILL", &content_pid.to_string()])
            .status()
        {
            Ok(status) => status,
            Err(error) => {
                self.write_evidence(&format!("FAIL_CONTENT_PROCESS_KILL_EXEC:{error}"));
                return;
            }
        };
        if !status.success() {
            self.write_evidence(&format!("FAIL_CONTENT_PROCESS_KILL_STATUS:{status}"));
            return;
        }

        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let stat_path = format!("/proc/{content_pid}/stat");
            let deadline = Instant::now() + Duration::from_secs(10);
            loop {
                match fs::read_to_string(&stat_path) {
                    Err(error) if error.kind() == ErrorKind::NotFound => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                            pid: content_pid,
                            start_time,
                        });
                        break;
                    }
                    Err(error) => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                            format!("could not observe exact content-process termination: {error}"),
                        ));
                        break;
                    }
                    Ok(stat) => {
                        let Some(observed_start_time) = proc_start_time(&stat) else {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                "could not parse exact content-process start time".to_owned(),
                            ));
                            break;
                        };
                        if observed_start_time != start_time {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                format!(
                                    "content-process identity changed: pid={content_pid}, expected={start_time}, observed={observed_start_time}"
                                ),
                            ));
                            break;
                        }
                        if proc_state(&stat) == Some('Z') {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                                pid: content_pid,
                                start_time,
                            });
                            break;
                        }
                        if Instant::now() >= deadline {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                format!(
                                    "content process remained executable after SIGKILL: pid={content_pid}, start_time={start_time}"
                                ),
                            ));
                            break;
                        }
                        thread::sleep(Duration::from_millis(10));
                    }
                }
            }
        });
    }

    fn begin_recovery(self: &Rc<Self>) {
''',
)
replace_once(
    runtime,
    '                "  \\\"actual_crash_callbacks\\\": {},\\n",\n                "  \\\"simulated_content_process_recovery\\\": {},\\n",\n                "  \\\"external_network_used\\\": false,\\n",\n',
    '                "  \\\"actual_crash_callbacks\\\": {},\\n",\n                "  \\\"actual_content_process_crash_proven\\\": {},\\n",\n                "  \\\"content_process_pid\\\": {},\\n",\n                "  \\\"content_process_start_time_ticks\\\": {},\\n",\n                "  \\\"content_process_termination_observed\\\": {},\\n",\n                "  \\\"simulated_content_process_recovery\\\": false,\\n",\n                "  \\\"external_network_used\\\": false,\\n",\n',
)
replace_once(
    runtime,
    "            self.popup_requests_denied.get(),\n            self.actual_crash_callbacks.get(),\n            self.recovery_started.get(),\n            elapsed_ms,\n",
    "            self.popup_requests_denied.get(),\n            self.actual_crash_callbacks.get(),\n            self.actual_crash_callbacks.get() > 0\n                && self.content_process_termination_observed.get(),\n            self.content_process_pid.get(),\n            self.content_process_start_time.get(),\n            self.content_process_termination_observed.get(),\n            elapsed_ms,\n",
)
replace_once(
    runtime,
    "        if self.page_input_verified.get()\n            && self.popup_requests_denied.get() >= 1\n            && self.generation.get() == 1\n            && self.ime_composition_events_sent.get() == 3\n        {\n            self.begin_recovery();\n        }\n",
    "        if self.page_input_verified.get()\n            && self.popup_requests_denied.get() >= 1\n            && self.generation.get() == 1\n            && self.ime_composition_events_sent.get() == 3\n            && !self.crash_triggered.get()\n        {\n            self.trigger_content_crash();\n            return;\n        }\n        if self.generation.get() == 1\n            && self.crash_triggered.get()\n            && self.content_process_termination_observed.get()\n            && self.actual_crash_callbacks.get() >= 1\n        {\n            self.begin_recovery();\n        }\n",
)
replace_once(
    runtime,
    "        self.actual_crash_callbacks\n            .set(self.actual_crash_callbacks.get().saturating_add(1));\n        self.window.set_title(TRUSTED_TITLE);\n        self.window.request_redraw();\n",
    "        self.actual_crash_callbacks\n            .set(self.actual_crash_callbacks.get().saturating_add(1));\n        self.window.set_title(TRUSTED_TITLE);\n        self.window.request_redraw();\n        let _ = self.proxy.send_event(AppEvent::Wake);\n",
)
replace_once(
    runtime,
    "        let servo = ServoBuilder::default()\n            .event_loop_waker(Box::new(waker.clone()))\n            .build();\n",
    "        let profile = output.join(\"servo-profile\");\n        fs::create_dir_all(&profile).expect(\"failed to create Servo profile\");\n        let mut opts = Opts::default();\n        opts.multiprocess = true;\n        opts.hard_fail = false;\n        opts.sandbox = false;\n        opts.temporary_storage = true;\n        opts.config_dir = Some(profile);\n        let servo = ServoBuilder::default()\n            .opts(opts)\n            .event_loop_waker(Box::new(waker.clone()))\n            .build();\n",
)
replace_once(
    runtime,
    "            popup_requests_denied: Cell::new(0),\n            actual_crash_callbacks: Cell::new(0),\n            generation: Cell::new(1),\n",
    "            popup_requests_denied: Cell::new(0),\n            actual_crash_callbacks: Cell::new(0),\n            crash_triggered: Cell::new(false),\n            content_process_termination_observed: Cell::new(false),\n            content_process_pid: Cell::new(0),\n            content_process_start_time: Cell::new(0),\n            generation: Cell::new(1),\n",
)
replace_once(
    runtime,
    "    fn user_event(&mut self, _event_loop: &ActiveEventLoop, _event: AppEvent) {\n        if let Self::Running(state) = self {\n            state.drive();\n        }\n    }\n",
    '''    fn user_event(&mut self, _event_loop: &ActiveEventLoop, event: AppEvent) {
        if let Self::Running(state) = self {
            match event {
                AppEvent::ContentProcessTerminated { pid, start_time } => {
                    if pid != state.content_process_pid.get()
                        || start_time != state.content_process_start_time.get()
                    {
                        state.write_evidence("FAIL_CONTENT_PROCESS_IDENTITY_DRIFT");
                        return;
                    }
                    state.content_process_termination_observed.set(true);
                }
                AppEvent::ContentProcessTerminationFailed(reason) => {
                    state.write_evidence(&format!("FAIL_CONTENT_PROCESS_TERMINATION:{reason}"));
                    return;
                }
                AppEvent::Wake => {}
            }
            state.drive();
        }
    }
''',
)
replace_once(
    runtime,
    "enum AppEvent {\n    Wake,\n}\n",
    "enum AppEvent {\n    Wake,\n    ContentProcessTerminated { pid: u32, start_time: u64 },\n    ContentProcessTerminationFailed(String),\n}\n",
)
replace_once(
    runtime,
    "fn _assert_evidence_path_is_bounded(path: &Path) -> bool {\n",
    '''fn exact_content_process_pid() -> Result<u32, String> {
    let parent_pid = std::process::id();
    let current_executable = fs::canonicalize(
        env::current_exe().map_err(|error| format!("could not resolve runtime executable: {error}"))?,
    )
    .map_err(|error| format!("could not canonicalize runtime executable: {error}"))?;
    let mut candidates = Vec::new();
    for entry in fs::read_dir("/proc")
        .map_err(|error| format!("could not enumerate /proc: {error}"))?
    {
        let Ok(entry) = entry else { continue };
        let name = entry.file_name();
        let Some(name) = name.to_str() else { continue };
        let Ok(pid) = name.parse::<u32>() else { continue };
        if pid == parent_pid {
            continue;
        }
        let Ok(stat) = fs::read_to_string(format!("/proc/{pid}/stat")) else {
            continue;
        };
        if proc_parent_pid(&stat) != Some(parent_pid) {
            continue;
        }
        let Ok(executable) = fs::canonicalize(format!("/proc/{pid}/exe")) else {
            continue;
        };
        if executable != current_executable {
            continue;
        }
        let Ok(command_line) = fs::read(format!("/proc/{pid}/cmdline")) else {
            continue;
        };
        if command_line
            .split(|byte| *byte == 0)
            .any(|argument| argument == b"--content-process")
        {
            candidates.push(pid);
        }
    }
    match candidates.as_slice() {
        [pid] => Ok(*pid),
        [] => Err("no exact direct --content-process child was found".to_owned()),
        _ => Err(format!(
            "multiple exact direct --content-process children were found: {candidates:?}"
        )),
    }
}

fn exact_content_process_start_time(pid: u32) -> Result<u64, String> {
    let stat = fs::read_to_string(format!("/proc/{pid}/stat"))
        .map_err(|error| format!("could not read content-process identity: {error}"))?;
    proc_start_time(&stat)
        .ok_or_else(|| "could not parse content-process start time".to_owned())
}

fn proc_state(stat: &str) -> Option<char> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .next()?
        .chars()
        .next()
}

fn proc_start_time(stat: &str) -> Option<u64> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .nth(19)?
        .parse()
        .ok()
}

fn proc_parent_pid(stat: &str) -> Option<u32> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .nth(1)?
        .parse()
        .ok()
}

fn _assert_evidence_path_is_bounded(path: &Path) -> bool {
''',
)

acceptance = "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance"
replace_once(
    acceptance,
    "actual_crash_callbacks=${actual_crash_callbacks:-0}\n\ncat > \"$result\" <<EOF\n",
    "actual_crash_callbacks=${actual_crash_callbacks:-0}\n(( actual_crash_callbacks >= 1 )) || fail actual_crash_callback_missing\ngrep -Eq '\"actual_content_process_crash_proven\"[[:space:]]*:[[:space:]]*true' \"$runtime\" \\\n  || fail actual_content_process_crash_not_proven\ngrep -Eq '\"content_process_termination_observed\"[[:space:]]*:[[:space:]]*true' \"$runtime\" \\\n  || fail content_process_termination_not_observed\n\ncat > \"$result\" <<EOF\n",
)
replace_once(
    acceptance,
    '  "actual_content_process_crash_proven": false,\n',
    '  "actual_content_process_crash_proven": true,\n',
)

boot = "tests/qemu/run-d2i-boot-test.sh"
replace_once(
    boot,
    'assert acceptance["actual_content_process_crash_proven"] is False, acceptance\n',
    'assert acceptance["actual_content_process_crash_proven"] is True, acceptance\nassert acceptance["actual_crash_callbacks"] >= 1, acceptance\nassert runtime["actual_content_process_crash_proven"] is True, runtime\nassert runtime["actual_crash_callbacks"] >= 1, runtime\nassert runtime["content_process_termination_observed"] is True, runtime\n',
)
replace_once(
    boot,
    '    "actual_content_process_crash_proven": False,\n',
    '    "actual_content_process_crash_proven": True,\n',
)
