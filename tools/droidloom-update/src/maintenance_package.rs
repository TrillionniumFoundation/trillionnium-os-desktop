//! Compile the fixed production maintenance entry from the same normal source.
use crate::util::*;
use std::{fs, path::Path, process::Command};

const SOURCE: &[u8] = include_bytes!("../../../packaging/ubuntu/production/maintenance.c");
const SCRIPT: &[u8] = include_bytes!("../../../packaging/ubuntu/production/release.py");
// Admitted original Ubuntu python3.14-minimal ELF. A distribution upgrade must
// update this source pin and produce a new normally built host, not retarget
// the running privileged interpreter through an environment variable.
const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA256: &str =
    "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";

pub(super) fn stage(destination: &Path) -> Result<()> {
    let work = tempfile::tempdir()?;
    let source = work.path().join("maintenance.c");
    let script = work.path().join("release.py");
    fs::write(&source, SOURCE)?;
    fs::write(&script, SCRIPT)?;
    let header = format!(
        concat!(
            "/* Generated only from the normal source inputs. */\n",
            "#define DROIDLOOM_MAINTENANCE_SCRIPT_BYTES {}ULL\n",
            "#define DROIDLOOM_MAINTENANCE_SCRIPT_SHA256 \"{}\"\n",
            "#define DROIDLOOM_MAINTENANCE_PYTHON_BYTES {}ULL\n",
            "#define DROIDLOOM_MAINTENANCE_PYTHON_SHA256 \"{}\"\n"
        ),
        SCRIPT.len(), hash(&script)?, PYTHON_BYTES, PYTHON_SHA256
    );
    fs::write(work.path().join("maintenance_inputs.h"), header)?;
    let binary = work.path().join("droidloom-maintenance");
    let status = Command::new("cc")
        .current_dir(work.path())
        .args([
            "-std=c11", "-O2", "-fPIE", "-fstack-protector-strong",
            "-D_FORTIFY_SOURCE=3", "-Wall", "-Wextra", "-Werror",
            "-Wl,-z,relro,-z,now", "-pie", "maintenance.c", "-lcrypto", "-o",
        ])
        .arg(&binary)
        .status()?;
    if !status.success() {
        return fail("cannot compile the fixed normal maintenance entry");
    }
    let prefix = destination.join("usr/lib/droidloom/production/current");
    let target = prefix.join("droidloom-maintenance");
    copy(&binary, &target)?;
    mode(&target, 0o755)?;
    let target = prefix.join("droidloom-maintenance.py");
    write(&target, SCRIPT)?;
    mode(&target, 0o444)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normal_maintenance_entry_rejects_free_programs_before_authority() {
        let directory = tempfile::tempdir().unwrap();
        stage(directory.path()).unwrap();
        let binary = directory.path().join(
            "usr/lib/droidloom/production/current/droidloom-maintenance"
        );
        for args in [vec!["/bin/sh"], vec!["verify", "../escape"], vec!["status", "/tmp/path"]] {
            let result = Command::new(&binary).args(args).output().unwrap();
            assert_eq!(result.status.code(), Some(64));
        }
        let result = Command::new(&binary).arg("status").output().unwrap();
        assert_eq!(result.status.code(), Some(77));
        assert!(String::from_utf8_lossy(&result.stderr).contains("authenticated native maintenance"));
    }
}
