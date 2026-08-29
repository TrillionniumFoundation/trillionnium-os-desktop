#!/usr/bin/env python3
"""Apply the bounded D0A-02 runtime-exit observation repair exactly once."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/servo-headed-runtime/src/main.rs"
SIMPLE = ROOT / "runtime/servo/hepta_workspace_runtime.rs"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one source anchor, found {count}")
    return text.replace(old, new, 1)


def patch_experiment() -> bool:
    text = EXPERIMENT.read_text(encoding="utf-8")
    if "ContentProcessTerminated { pid, start_time }" in text:
        return False

    text = replace_once(
        text,
        "use std::time::Duration;",
        "use std::time::{Duration, Instant};",
        "time import",
    )
    text = replace_once(
        text,
        """#[derive(Debug)]
enum AppEvent {
    Wake,
    Drive,
    Settled,
    Timeout,
    Exit(i32),
}
""",
        """#[derive(Debug)]
enum AppEvent {
    Wake,
    Drive,
    Settled,
    Timeout,
    ContentProcessTerminated { pid: u32, start_time: u64 },
    ContentProcessTerminationFailed(String),
    Exit(i32),
}
""",
        "AppEvent variants",
    )
    text = replace_once(
        text,
        """            AppEvent::Timeout => {
                if let Some(state) = &self.state {
                    if !state.completed.get() {
                        state.fail("runtime watchdog expired");
                    }
                }
            }
            AppEvent::Settled => {
""",
        """            AppEvent::Timeout => {
                if let Some(state) = &self.state {
                    if !state.completed.get() {
                        state.fail("runtime watchdog expired");
                    }
                }
            }
            AppEvent::ContentProcessTerminated { pid, start_time } => {
                if let Some(state) = &self.state {
                    state.crash_observed.set(true);
                    *state.crash_reason.borrow_mut() = Some(format!(
                        "exact content process terminated after SIGKILL: pid={pid}, start_time={start_time}"
                    ));
                    state.window.request_redraw();
                    state.drive();
                }
            }
            AppEvent::ContentProcessTerminationFailed(message) => {
                if let Some(state) = &self.state {
                    state.fail(&message);
                }
            }
            AppEvent::Settled => {
""",
        "event-loop termination handling",
    )
    text = replace_once(
        text,
        """        let content_pid = match exact_content_process_pid() {
            Ok(pid) => pid,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        if let Err(error) = fs::write(
""",
        """        let content_pid = match exact_content_process_pid() {
            Ok(pid) => pid,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        let content_start_time = match exact_content_process_start_time(content_pid) {
            Ok(start_time) => start_time,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        if let Err(error) = fs::write(
""",
        "content process identity capture",
    )
    text = replace_once(
        text,
        """        if !status.success() {
            self.fail(&format!(
                "exact content-process kill exited with status {status}"
            ));
            return;
        }
        let _ = self.proxy.send_event(AppEvent::Drive);
""",
        """        if !status.success() {
            self.fail(&format!(
                "exact content-process kill exited with status {status}"
            ));
            return;
        }

        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let stat_path = format!("/proc/{content_pid}/stat");
            let deadline = Instant::now() + Duration::from_secs(5);
            loop {
                match fs::read_to_string(&stat_path) {
                    Err(error) if error.kind() == ErrorKind::NotFound => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                            pid: content_pid,
                            start_time: content_start_time,
                        });
                        break;
                    }
                    Err(error) => {
                        let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                            format!(
                                "could not observe exact content-process termination: {error}"
                            ),
                        ));
                        break;
                    }
                    Ok(stat) => {
                        let observed_start_time = match proc_start_time(&stat) {
                            Some(start_time) => start_time,
                            None => {
                                let _ = proxy.send_event(
                                    AppEvent::ContentProcessTerminationFailed(
                                        "could not parse exact content-process start time while observing termination"
                                            .to_owned(),
                                    ),
                                );
                                break;
                            }
                        };
                        if observed_start_time != content_start_time {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                format!(
                                    "content-process pid identity changed before an unambiguous exit observation: pid={content_pid}, expected_start_time={content_start_time}, observed_start_time={observed_start_time}"
                                ),
                            ));
                            break;
                        }
                        if proc_state(&stat) == Some('Z') {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminated {
                                pid: content_pid,
                                start_time: content_start_time,
                            });
                            break;
                        }
                        if Instant::now() >= deadline {
                            let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(
                                format!(
                                    "exact content process remained executable after SIGKILL timeout: pid={content_pid}, start_time={content_start_time}"
                                ),
                            ));
                            break;
                        }
                        thread::sleep(Duration::from_millis(10));
                    }
                }
            }
        });
""",
        "bounded process-exit observer",
    )
    text = replace_once(
        text,
        """fn proc_parent_pid(stat: &str) -> Option<u32> {
""",
        """fn exact_content_process_start_time(pid: u32) -> Result<u64, String> {
    let stat = fs::read_to_string(format!("/proc/{pid}/stat"))
        .map_err(|error| format!("could not read exact content-process identity: {error}"))?;
    proc_start_time(&stat)
        .ok_or_else(|| "could not parse exact content-process start time".to_owned())
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
""",
        "proc identity helpers",
    )
    EXPERIMENT.write_text(text, encoding="utf-8")
    return True


def patch_simple_runtime() -> bool:
    text = SIMPLE.read_text(encoding="utf-8")
    if "self.input_events_sent.set(13);" in text:
        return False
    text = replace_once(
        text,
        """        for event in events {
            webview.notify_input_event(event);
        }
        self.input_events_sent.set(7);
""",
        """        for event in events {
            webview.notify_input_event(event);
        }
        // Servo reports handled callbacks only for events that enter its input
        // dispatch path. Repeat pointer/button input so the qualification gate
        // cannot stall merely because keyboard or dismissed-IME events have no
        // handled callback on the exact pinned Servo revision.
        for _ in 0..2 {
            webview.notify_input_event(InputEvent::MouseMove(MouseMoveEvent::new(point)));
            webview.notify_input_event(InputEvent::MouseButton(MouseButtonEvent::new(
                MouseButtonAction::Down,
                MouseButton::Primary,
                point,
            )));
            webview.notify_input_event(InputEvent::MouseButton(MouseButtonEvent::new(
                MouseButtonAction::Up,
                MouseButton::Primary,
                point,
            )));
        }
        self.input_events_sent.set(13);
""",
        "simple runtime input corpus",
    )
    SIMPLE.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    changed = patch_experiment() | patch_simple_runtime()
    print("D0A-02 runtime exit observation patch applied" if changed else "D0A-02 patch already applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
