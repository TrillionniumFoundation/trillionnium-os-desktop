from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one replacement target, found {count}: {old!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


source = Path("experiments/servo-headed-runtime/src/main.rs")
replace_once(
    source,
    "use std::path::{Path, PathBuf};\n",
    "use std::path::{Path, PathBuf};\nuse std::process::Command;\n",
)
replace_once(
    source,
    """    fn trigger_content_crash(self: &Rc<Self>) {
        self.crash_triggered.set(true);
        if let Err(error) = fs::write(self.output_dir.join("content-crash-ready"), "ready\\n") {
            self.fail(&format!(
                "could not publish exact content-process crash marker: {error}"
            ));
        }
    }
""",
    """    fn trigger_content_crash(self: &Rc<Self>) {
        self.crash_triggered.set(true);
        let content_pid = match exact_content_process_pid() {
            Ok(pid) => pid,
            Err(error) => {
                self.fail(&error);
                return;
            }
        };
        if let Err(error) = fs::write(
            self.output_dir.join("content-process-pid.txt"),
            format!("{content_pid}\\n"),
        ) {
            self.fail(&format!("could not record exact content-process pid: {error}"));
            return;
        }
        if let Err(error) = fs::write(self.output_dir.join("content-crash-ready"), "ready\\n") {
            self.fail(&format!(
                "could not publish exact content-process crash marker: {error}"
            ));
            return;
        }
        let status = match Command::new("/bin/kill")
            .args(["-KILL", &content_pid.to_string()])
            .status()
        {
            Ok(status) => status,
            Err(error) => {
                self.fail(&format!("could not execute exact content-process kill: {error}"));
                return;
            }
        };
        if !status.success() {
            self.fail(&format!(
                "exact content-process kill exited with status {status}"
            ));
            return;
        }
        let _ = self.proxy.send_event(AppEvent::Drive);
    }
""",
)
insert_before = """fn clear_rect(gl: &glow::Context, x: i32, y: i32, width: i32, height: i32, color: [f32; 4]) {
"""
helpers = """fn exact_content_process_pid() -> Result<u32, String> {
    let parent_pid = std::process::id();
    let current_exe = fs::canonicalize(
        env::current_exe().map_err(|error| format!("could not resolve parent executable: {error}"))?,
    )
    .map_err(|error| format!("could not canonicalize parent executable: {error}"))?;
    let mut candidates = Vec::new();
    let entries = fs::read_dir("/proc")
        .map_err(|error| format!("could not enumerate /proc for content process: {error}"))?;
    for entry in entries {
        let entry = match entry {
            Ok(entry) => entry,
            Err(_) => continue,
        };
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Ok(pid) = name.parse::<u32>() else {
            continue;
        };
        if pid == parent_pid {
            continue;
        }
        let stat = match fs::read_to_string(format!("/proc/{pid}/stat")) {
            Ok(stat) => stat,
            Err(_) => continue,
        };
        if proc_parent_pid(&stat) != Some(parent_pid) {
            continue;
        }
        let executable = match fs::canonicalize(format!("/proc/{pid}/exe")) {
            Ok(executable) => executable,
            Err(_) => continue,
        };
        if executable != current_exe {
            continue;
        }
        let cmdline = match fs::read(format!("/proc/{pid}/cmdline")) {
            Ok(cmdline) => cmdline,
            Err(_) => continue,
        };
        let has_content_process_flag = cmdline
            .split(|byte| *byte == 0)
            .any(|argument| argument == b"--content-process");
        if has_content_process_flag {
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

fn proc_parent_pid(stat: &str) -> Option<u32> {
    let command_end = stat.rfind(')')?;
    stat.get(command_end + 2..)?
        .split_whitespace()
        .nth(1)?
        .parse()
        .ok()
}

"""
replace_once(source, insert_before, helpers + insert_before)
