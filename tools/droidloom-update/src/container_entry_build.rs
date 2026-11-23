//! Build the cell entry without a host ELF interpreter. CP3A supplies Bionic;
//! its root must not need an injected host loader to execute the host facade.
use std::{path::Path, process::Command};

pub fn command(source: &Path, target: &Path, jobs: usize) -> Command {
    let mut command = Command::new("cargo");
    command
        .current_dir(source)
        .env("CARGO_TARGET_DIR", target)
        .args(["rustc", "--locked", "--release", "--jobs"])
        .arg(jobs.to_string())
        .args([
            "-p",
            "droidloom-supervisor",
            "--bin",
            "droidloom-container-entry",
            "--",
            "-C",
            "target-feature=+crt-static",
        ]);
    command
}
