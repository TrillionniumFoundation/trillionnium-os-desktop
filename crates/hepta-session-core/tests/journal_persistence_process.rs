//! Isolated process-cut matrix over the exact journal source. A custom test
//! harness avoids fork/exec inheriting locks from unrelated parallel unit tests.
//! No generated or copied journal implementation is used. Normal product builds
//! do not compile this entrypoint or its private cfg(test) cutpoints.
#![allow(dead_code, unused_imports)] // The source module also contains non-tested public APIs.
#[path = "../src/receipt_journal.rs"]
mod receipt_journal;
use receipt_journal::persistence_tests::*;
use receipt_journal::*;
use std::fs::{self, File};
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

fn perform_case(root: &Path, case: &str, target: &str, checkpoint: PathBuf) {
    // Preparation occurs before arming the one-shot, thread-local injection.
    // There is exactly one tested operation in each fresh exec'd child.
    let mut writer = match case {
        "rotate" | "append" => Some(prepared(root)),
        "reopen" => {
            prepared_unresolved(root);
            None
        }
        "pending" => {
            recovered_pending(root);
            None
        }
        "repair" => {
            with_torn_tail(root);
            None
        }
        "initialize" => None,
        _ => panic!("unknown persistence test case"),
    };
    let _armed = Armed::new(target, Action::Pause(checkpoint));
    match case {
        "rotate" => {
            let _ = writer.take().unwrap().rotate_managed(2);
        }
        "append" => {
            let _ = writer
                .as_mut()
                .unwrap()
                .append(event("new", LifecycleState::Requested));
        }
        "reopen" | "pending" | "repair" => {
            let _ = ReceiptJournal::open_managed(root, ID, ManagedOpenPolicy::RECOVER_CRASH);
        }
        "initialize" => {
            let _ = ReceiptJournal::create_managed(root, ID, 1);
        }
        _ => unreachable!(),
    }
    panic!("target {target} was not reached by case {case}");
}
struct ChildGuard(Child);
impl Drop for ChildGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn killed_at(case: &str, target: &str) -> Temp {
    let temp = Temp::new();
    let output = File::create(temp.0.join("child.log")).unwrap();
    let mut child = ChildGuard(
        Command::new(std::env::current_exe().unwrap())
            .arg("--persistence-child")
            .arg(&temp.0)
            .args([case, target])
            .stdout(Stdio::from(output.try_clone().unwrap()))
            .stderr(Stdio::from(output))
            .spawn()
            .unwrap(),
    );
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if fs::read_to_string(temp.0.join("checkpoint"))
            .ok()
            .as_deref()
            == Some(target)
        {
            break;
        }
        assert!(
            child.0.try_wait().unwrap().is_none(),
            "child exited {case}/{target}: {}",
            fs::read_to_string(temp.0.join("child.log")).unwrap()
        );
        assert!(
            Instant::now() < deadline,
            "bounded child checkpoint timeout {case}/{target}"
        );
        std::thread::sleep(Duration::from_millis(3));
    }
    child.0.kill().unwrap();
    assert_eq!(child.0.wait().unwrap().signal(), Some(9), "{case}/{target}");
    temp
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--persistence-child") {
        assert_eq!(args.len(), 4, "bounded private test child arguments");
        let parent = PathBuf::from(&args[1]);
        assert!(
            parent
                .file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("hepta-persistence-cuts-")
        );
        assert!(parent.is_dir());
        let case = &args[2];
        let target = &args[3];
        assert!(matrix().iter().any(|(c, t, _)| *c == case && *t == target));
        perform_case(
            &parent.join("store"),
            case,
            target,
            parent.join("checkpoint"),
        );
        unreachable!();
    }
    if args == ["--list"] {
        for (case, target, _) in matrix() {
            println!("{case}/{target}: process-cut");
        }
        return;
    }
    assert!(
        args.iter()
            .all(|a| a == "--nocapture" || a.starts_with("--test-threads=")),
        "unsupported custom-harness arguments; matrix must not be silently filtered"
    );
    let cases = matrix();
    assert_eq!(
        cases.len(),
        64,
        "independent process scenario count drifted"
    );
    for (case, target, state) in &cases {
        let temp = killed_at(case, target);
        match *case {
            "rotate" | "pending" => assert_publication(&temp.store(), *state, true),
            "initialize" => assert_publication(&temp.store(), *state, false),
            "reopen" => assert_unresolved_preserved(&temp.store()),
            "append" => assert_append_cut(&temp.store(), target),
            "repair" => assert_repaired(&temp.store()),
            _ => unreachable!(),
        }
        println!("persistence-cut case={case} point={target} signal=9 recovered=PASS");
    }
    println!(
        "persistence-process-matrix: {} passed; 0 failed; no physical-powerloss claim",
        cases.len()
    );
}
fn matrix() -> Vec<(&'static str, &'static str, DiskState)> {
    let mut cases = Vec::new();
    for &(point, state) in ROTATION_CUTS {
        cases.push(("rotate", point, state));
    }
    for &(point, state) in INITIALIZATION_CUTS {
        cases.push(("initialize", point, state));
    }
    for &point in REOPEN_CUTS {
        cases.push(("reopen", point, DiskState::Published));
    }
    for &(point, state) in ROTATION_CUTS
        .iter()
        .filter(|(p, _)| p.starts_with("publish."))
    {
        cases.push(("pending", point, state));
    }
    for &point in APPEND_CUTS {
        cases.push(("append", point, DiskState::Published));
    }
    for &point in REPAIR_CUTS {
        cases.push(("repair", point, DiskState::Published));
    }
    cases
}
