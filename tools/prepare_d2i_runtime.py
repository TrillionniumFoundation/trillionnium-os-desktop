#!/usr/bin/env python3
"""Deterministically harden the tracked D2I Servo qualification source."""
from __future__ import annotations

import argparse, hashlib, json, re
from pathlib import Path


def sub(text: str, pattern: str, replacement: str, label: str, *, regex: bool = False) -> str:
    if regex:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    else:
        count = text.count(pattern)
        if count == 1:
            text = text.replace(pattern, replacement, 1)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    a = ap.parse_args()
    original = a.source.read_text(encoding="utf-8")
    t = original

    t = sub(t, "KeyboardEvent, MouseButton,\n", "KeyboardEvent, MouseButton, NavigationRequest,\n", "navigation import")
    t = sub(
        t,
        "    \"setTimeout(()=>%7Bwindow.__hepta_popup=window.open('data:text/html,popup')%7D,0);\",\n",
        "    \"setTimeout(()=>%7Bwindow.__hepta_popup=window.open('data:text/html,popup')%7D,0);\",\n"
        "    \"setTimeout(()=>%7Blocation.href='https://example.invalid/d2i-denied'%7D,50);\",\n",
        "external navigation fixture",
    )
    t = sub(
        t,
        "fn content_process_token() -> Option<String> {",
        "#[derive(Clone, Copy, Debug, PartialEq, Eq)]\n"
        "struct ProcessIdentity { pid: u32, start_time: u64 }\n\n"
        "fn content_process_token() -> Option<String> {",
        "process identity",
    )
    t = sub(
        t,
        "    popup_requests_denied: Cell<u64>,\n"
        "    actual_crash_callbacks: Cell<u64>,\n"
        "    crash_triggered: Cell<bool>,\n"
        "    content_process_termination_observed: Cell<bool>,\n"
        "    content_process_pid: Cell<u32>,\n"
        "    content_process_start_time: Cell<u64>,\n",
        "    popup_requests_denied: Cell<u64>,\n"
        "    external_navigation_requests_denied: Cell<u64>,\n"
        "    actual_crash_callbacks: Cell<u64>,\n"
        "    crash_triggered: Cell<bool>,\n"
        "    signal_sent: Cell<bool>,\n"
        "    content_process_termination_observed: Cell<bool>,\n"
        "    zero_content_processes_after_termination: Cell<bool>,\n"
        "    content_process_pid: Cell<u32>,\n"
        "    content_process_start_time: Cell<u64>,\n"
        "    replacement_process_pid: Cell<u32>,\n"
        "    replacement_process_start_time: Cell<u64>,\n",
        "state fields",
    )
    t = sub(
        t,
        'format!("{{\\n  \\\"pid\\\": {content_pid},\\n  \\\"start_time_ticks\\\": {start_time}\\n}}\\n"),',
        'format!("{{\\n  \\\"generation\\\": 1,\\n  \\\"pid\\\": {content_pid},\\n  \\\"start_time_ticks\\\": {start_time}\\n}}\\n"),',
        "selected identity generation",
    )
    t = sub(
        t,
        "        );\n\n        let status = match Command::new(\"/bin/kill\")",
        "        );\n"
        "        let _ = fs::write(self.output.join(\"process-topology-pre-fault.json\"), format!(\n"
        "            \"{{\\n  \\\"active_process_count\\\": 1,\\n  \\\"embedder_pid\\\": {},\\n  \\\"processes\\\": [{{\\\"pid\\\": {content_pid}, \\\"start_time_ticks\\\": {start_time}}}]\\n}}\\n\",\n"
        "            std::process::id()));\n\n"
        "        let status = match Command::new(\"/bin/kill\")",
        "pre-fault topology",
    )
    t = sub(
        t,
        "        if !status.success() {\n"
        "            self.write_evidence(&format!(\"FAIL_CONTENT_PROCESS_KILL_STATUS:{status}\"));\n"
        "            return;\n"
        "        }\n\n        let proxy = self.proxy.clone();",
        "        if !status.success() {\n"
        "            self.write_evidence(&format!(\"FAIL_CONTENT_PROCESS_KILL_STATUS:{status}\"));\n"
        "            return;\n"
        "        }\n"
        "        self.signal_sent.set(true);\n"
        "        let _ = fs::write(self.output.join(\"content-sigkill-sent.json\"), format!(\n"
        "            \"{{\\n  \\\"generation\\\": 1,\\n  \\\"pid\\\": {content_pid},\\n  \\\"signal\\\": \\\"SIGKILL\\\",\\n  \\\"start_time_ticks\\\": {start_time}\\n}}\\n\"));\n\n"
        "        let proxy = self.proxy.clone();\n"
        "        let output = self.output.clone();",
        "SIGKILL receipt",
    )
    t = sub(
        t,
        r"Err\(error\) if error\.kind\(\) == ErrorKind::NotFound => \{.*?break;\n                    \}",
        "Err(error) if error.kind() == ErrorKind::NotFound => {\n"
        "                        match exact_content_process_identities() {\n"
        "                            Ok(processes) if processes.is_empty() => {\n"
        "                                let _ = fs::write(output.join(\"process-topology-post-termination.json\"), format!(\n"
        "                                    \"{{\\n  \\\"active_process_count\\\": 0,\\n  \\\"embedder_pid\\\": {},\\n  \\\"processes\\\": []\\n}}\\n\", std::process::id()));\n"
        "                                let _ = proxy.send_event(AppEvent::ContentProcessTerminated { pid: content_pid, start_time });\n"
        "                            }\n"
        "                            Ok(processes) => { let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(format!(\n"
        "                                \"content-process set not empty after termination: {processes:?}\"))); }\n"
        "                            Err(reason) => { let _ = proxy.send_event(AppEvent::ContentProcessTerminationFailed(reason)); }\n"
        "                        }\n"
        "                        break;\n"
        "                    }",
        "zero-process intermediate",
        regex=True,
    )
    t = sub(
        t,
        r"if proc_state\(&stat\) == Some\('Z'\) \{.*?break;\n                        \}",
        "if proc_state(&stat) == Some('Z') {\n"
        "                            thread::sleep(Duration::from_millis(10));\n"
        "                            continue;\n"
        "                        }",
        "wait past zombie",
        regex=True,
    )
    t = sub(
        t,
        "        self.webview.borrow_mut().take();\n"
        "        self.generation.set(2);\n"
        "        self.recovery_frame_baseline.set(self.frame_count.get());\n",
        "        self.webview.borrow_mut().take();\n"
        "        self.generation.set(2);\n"
        "        self.recovery_frame_baseline.set(self.frame_count.get());\n"
        "        self.input_events_sent.set(0);\n"
        "        self.input_events_handled.set(0);\n"
        "        self.page_input_evidence_requested.set(false);\n"
        "        self.page_input_verified.set(false);\n"
        "        self.ime_composition_events_sent.set(0);\n"
        "        self.popup_requests_denied.set(0);\n"
        "        self.external_navigation_requests_denied.set(0);\n"
        "        self.screenshot_requested.set(false);\n",
        "generation-two reset",
    )
    t = sub(t, "        let elapsed_ms = self.started_at.elapsed().as_millis();\n", "        let elapsed_ms = self.started_at.elapsed().as_millis();\n        let replacement_distinct = self.replacement_process_pid.get() > 0 && (self.replacement_process_pid.get() != self.content_process_pid.get() || self.replacement_process_start_time.get() != self.content_process_start_time.get());\n        let crash_proven = self.signal_sent.get() && self.content_process_termination_observed.get() && self.zero_content_processes_after_termination.get() && replacement_distinct;\n", "derived proof")
    t = sub(
        t,
        '                "  \\\"popup_requests_denied\\\": {},\\n",\n'
        '                "  \\\"actual_crash_callbacks\\\": {},\\n",\n'
        '                "  \\\"actual_content_process_crash_proven\\\": {},\\n",\n'
        '                "  \\\"content_process_pid\\\": {},\\n",\n'
        '                "  \\\"content_process_start_time_ticks\\\": {},\\n",\n'
        '                "  \\\"content_process_termination_observed\\\": {},\\n",\n',
        '                "  \\\"popup_requests_denied\\\": {},\\n",\n'
        '                "  \\\"external_navigation_requests_denied\\\": {},\\n",\n'
        '                "  \\\"actual_crash_callbacks\\\": {},\\n",\n'
        '                "  \\\"crash_callback_required\\\": false,\\n",\n'
        '                "  \\\"signal_sent\\\": {},\\n",\n'
        '                "  \\\"actual_content_process_crash_proven\\\": {},\\n",\n'
        '                "  \\\"content_process_pid\\\": {},\\n",\n'
        '                "  \\\"content_process_start_time_ticks\\\": {},\\n",\n'
        '                "  \\\"content_process_termination_observed\\\": {},\\n",\n'
        '                "  \\\"zero_content_processes_after_termination\\\": {},\\n",\n'
        '                "  \\\"replacement_content_process_pid\\\": {},\\n",\n'
        '                "  \\\"replacement_content_process_start_time_ticks\\\": {},\\n",\n'
        '                "  \\\"replacement_process_distinct\\\": {},\\n",\n',
        "proof JSON fields",
    )
    t = sub(
        t,
        "            self.popup_requests_denied.get(),\n"
        "            self.actual_crash_callbacks.get(),\n"
        "            self.actual_crash_callbacks.get() > 0\n"
        "                && self.content_process_termination_observed.get(),\n"
        "            self.content_process_pid.get(),\n"
        "            self.content_process_start_time.get(),\n"
        "            self.content_process_termination_observed.get(),\n",
        "            self.popup_requests_denied.get(),\n"
        "            self.external_navigation_requests_denied.get(),\n"
        "            self.actual_crash_callbacks.get(),\n"
        "            self.signal_sent.get(),\n"
        "            crash_proven,\n"
        "            self.content_process_pid.get(),\n"
        "            self.content_process_start_time.get(),\n"
        "            self.content_process_termination_observed.get(),\n"
        "            self.zero_content_processes_after_termination.get(),\n"
        "            self.replacement_process_pid.get(),\n"
        "            self.replacement_process_start_time.get(),\n"
        "            replacement_distinct,\n",
        "proof JSON arguments",
    )
    t = sub(t, "        if self.generation.get() == 1\n            && self.input_events_handled.get() >= 3\n", "        if self.input_events_handled.get() >= 3\n", "input evidence both generations")
    t = sub(t, "            && self.popup_requests_denied.get() >= 1\n            && self.generation.get() == 1\n            && self.ime_composition_events_sent.get() == 0\n", "            && self.popup_requests_denied.get() >= 1\n            && self.ime_composition_events_sent.get() == 0\n", "IME both generations")
    t = sub(
        t,
        r"        if self\.generation\.get\(\) == 1\n            && self\.crash_triggered\.get\(\).*?        if self\.output\.join\(\"screenshot\.ready\"\)\.is_file\(\)",
        "        if self.generation.get() == 1\n"
        "            && self.crash_triggered.get()\n"
        "            && self.signal_sent.get()\n"
        "            && self.content_process_termination_observed.get()\n"
        "            && self.zero_content_processes_after_termination.get()\n"
        "        { self.begin_recovery(); }\n"
        "        if self.generation.get() == 2 && self.frame_count.get() > self.recovery_frame_baseline.get() {\n"
        "            if self.replacement_process_pid.get() == 0 {\n"
        "                match exact_content_process_identity() {\n"
        "                    Ok(identity) if identity.pid != self.content_process_pid.get() || identity.start_time != self.content_process_start_time.get() => {\n"
        "                        self.replacement_process_pid.set(identity.pid);\n"
        "                        self.replacement_process_start_time.set(identity.start_time);\n"
        "                        let _ = fs::write(self.output.join(\"process-topology-post-recovery.json\"), format!(\n"
        "                            \"{{\\n  \\\"active_process_count\\\": 1,\\n  \\\"embedder_pid\\\": {},\\n  \\\"processes\\\": [{{\\\"pid\\\": {}, \\\"start_time_ticks\\\": {}}}]\\n}}\\n\", std::process::id(), identity.pid, identity.start_time));\n"
        "                    }\n"
        "                    Ok(_) => { self.write_evidence(\"FAIL_REPLACEMENT_PROCESS_IDENTITY_REUSED\"); return; }\n"
        "                    Err(_) => return,\n"
        "                }\n"
        "            }\n"
        "            self.request_recovery_screenshot();\n"
        "        }\n"
        "        if self.output.join(\"screenshot.ready\").is_file()",
        "callback-independent recovery",
        regex=True,
    )
    t = sub(t, "            && self.popup_requests_denied.get() >= 1\n            && self.input_events_handled.get() >= 3\n", "            && self.popup_requests_denied.get() >= 1\n            && self.external_navigation_requests_denied.get() >= 1\n            && self.replacement_process_pid.get() > 0\n            && self.input_events_handled.get() >= 3\n", "final proof threshold")
    t = sub(
        t,
        "    fn notify_crashed(&self, _webview: WebView, _reason: String, _backtrace: Option<String>) {",
        "    fn request_navigation(&self, _webview: WebView, request: NavigationRequest) {\n"
        "        if request.url.scheme() == \"data\" { request.allow(); } else {\n"
        "            self.external_navigation_requests_denied.set(self.external_navigation_requests_denied.get().saturating_add(1));\n"
        "            request.deny();\n"
        "        }\n"
        "    }\n\n"
        "    fn notify_crashed(&self, _webview: WebView, _reason: String, _backtrace: Option<String>) {",
        "navigation delegate",
    )
    t = sub(
        t,
        "            popup_requests_denied: Cell::new(0),\n"
        "            actual_crash_callbacks: Cell::new(0),\n"
        "            crash_triggered: Cell::new(false),\n"
        "            content_process_termination_observed: Cell::new(false),\n"
        "            content_process_pid: Cell::new(0),\n"
        "            content_process_start_time: Cell::new(0),\n",
        "            popup_requests_denied: Cell::new(0),\n"
        "            external_navigation_requests_denied: Cell::new(0),\n"
        "            actual_crash_callbacks: Cell::new(0),\n"
        "            crash_triggered: Cell::new(false),\n"
        "            signal_sent: Cell::new(false),\n"
        "            content_process_termination_observed: Cell::new(false),\n"
        "            zero_content_processes_after_termination: Cell::new(false),\n"
        "            content_process_pid: Cell::new(0),\n"
        "            content_process_start_time: Cell::new(0),\n"
        "            replacement_process_pid: Cell::new(0),\n"
        "            replacement_process_start_time: Cell::new(0),\n",
        "state initialization",
    )
    t = sub(t, "                    state.content_process_termination_observed.set(true);", "                    state.zero_content_processes_after_termination.set(true);\n                    state.content_process_termination_observed.set(true);", "termination state")
    t = sub(
        t,
        r"fn exact_content_process_pid\(\) -> Result<u32, String> \{.*?\n\}\n\nfn exact_content_process_start_time",
        '''fn exact_content_process_identities() -> Result<Vec<ProcessIdentity>, String> {
    let parent_pid = std::process::id();
    let current_executable = fs::canonicalize(env::current_exe().map_err(|e| format!("runtime executable: {e}"))?)
        .map_err(|e| format!("canonical runtime executable: {e}"))?;
    let mut out = Vec::new();
    for entry in fs::read_dir("/proc").map_err(|e| format!("enumerate /proc: {e}"))? {
        let Ok(entry) = entry else { continue };
        let Some(name) = entry.file_name().to_str().map(str::to_owned) else { continue };
        let Ok(pid) = name.parse::<u32>() else { continue };
        if pid == parent_pid { continue; }
        let Ok(stat) = fs::read_to_string(format!("/proc/{pid}/stat")) else { continue };
        if proc_parent_pid(&stat) != Some(parent_pid) { continue; }
        let Ok(exe) = fs::canonicalize(format!("/proc/{pid}/exe")) else { continue };
        if exe != current_executable { continue; }
        let Ok(cmdline) = fs::read(format!("/proc/{pid}/cmdline")) else { continue };
        if cmdline.split(|b| *b == 0).any(|arg| arg == b"--content-process") {
            let start_time = proc_start_time(&stat).ok_or_else(|| format!("content start time: {pid}"))?;
            out.push(ProcessIdentity { pid, start_time });
        }
    }
    out.sort_by_key(|item| item.pid);
    Ok(out)
}

fn exact_content_process_identity() -> Result<ProcessIdentity, String> {
    let items = exact_content_process_identities()?;
    match items.as_slice() {
        [identity] => Ok(*identity),
        [] => Err("no exact direct --content-process child was found".to_owned()),
        _ => Err(format!("multiple exact direct --content-process children were found: {items:?}")),
    }
}

fn exact_content_process_pid() -> Result<u32, String> {
    exact_content_process_identity().map(|item| item.pid)
}

fn exact_content_process_start_time''',
        "process enumeration",
        regex=True,
    )

    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(t, encoding="utf-8")
    record = {
        "schema": "trillionnium.desktop.d2i-runtime-transformation.v1",
        "status": "PASS_DETERMINISTIC_REVIEWED_TRANSFORMATION",
        "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "output_sha256": hashlib.sha256(t.encode()).hexdigest(),
        "callback_required": False,
        "zero_process_intermediate_required": True,
        "distinct_replacement_required": True,
        "external_navigation_denied": True,
        "repository_mutated": False,
    }
    a.evidence.parent.mkdir(parents=True, exist_ok=True)
    a.evidence.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
