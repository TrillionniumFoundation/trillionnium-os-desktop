use std::os::unix::fs::DirBuilderExt;
use std::{
    env, fs,
    path::{Path, PathBuf},
    process::{Command, ExitCode},
};
struct Pin {
    path: &'static str,
    before: Option<&'static str>,
    after: &'static str,
}
const PATCH_SHA: &str = "868078f9fbc3b1e595d9e3d83bef03390d346926809678663ce2ae35d47d215b";
const PINS: &[Pin] = &[
    Pin {
        path: "tools/droidloom-update/src/main.rs",
        before: Some("6e0c5526ad4f6497a25abda84c137e0dfbedefd7ae45d6ccf279352ba4d234cc"),
        after: "938cb260731c960e59c98dee740ba10f427bc0d68513d6e37d20eb2fb9677b0a",
    },
];
fn hash(path: &Path) -> Result<String, String> {
    let out = Command::new("/usr/bin/sha256sum")
        .arg("--")
        .arg(path)
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(format!("sha256sum failed for {}", path.display()));
    }
    let text = String::from_utf8(out.stdout).map_err(|e| e.to_string())?;
    let value = text.split_whitespace().next().ok_or("empty checksum")?;
    if value.len() != 64 || !value.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err("invalid checksum output".into());
    }
    Ok(value.to_string())
}
fn regular(root: &Path, relative: &str, absent: bool) -> Result<PathBuf, String> {
    if !fs::symlink_metadata(root)
        .map_err(|e| e.to_string())?
        .is_dir()
    {
        return Err("tree root must be a real directory".into());
    }
    let mut p = root.to_path_buf();
    let parts: Vec<_> = relative.split('/').collect();
    for (i, part) in parts.iter().enumerate() {
        if *part == "." || *part == ".." || part.is_empty() {
            return Err("unsafe manifest path".into());
        }
        p.push(part);
        match fs::symlink_metadata(&p) {
            Ok(meta) => {
                if i + 1 == parts.len() {
                    if absent {
                        return Err(format!("expected absent preimage: {relative}"));
                    }
                    if !meta.is_file() {
                        return Err(format!("not a regular file: {relative}"));
                    }
                } else if !meta.is_dir() {
                    return Err(format!("non-directory parent: {relative}"));
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound && absent => {
                return Ok(root.join(relative));
            }
            Err(e) => return Err(format!("{relative}: {e}")),
        }
    }
    Ok(p)
}
fn check(root: &Path, after: bool) -> Result<(), String> {
    for pin in PINS {
        let expected = if after { Some(pin.after) } else { pin.before };
        let p = regular(root, pin.path, expected.is_none())?;
        if let Some(wanted) = expected {
            if hash(&p)? != wanted {
                return Err(format!("source hash mismatch: {}", pin.path));
            }
        }
    }
    Ok(())
}
fn git_apply(root: &Path, patch: &Path, check_only: bool) -> Result<(), String> {
    let mut cmd = Command::new("/usr/bin/git");
    cmd.arg("-C").arg(root).arg("apply");
    if check_only {
        cmd.arg("--check");
    }
    let result = cmd
        .arg("--whitespace=nowarn")
        .arg("--")
        .arg(patch)
        .output()
        .map_err(|e| e.to_string())?;
    if !result.status.success() {
        return Err(String::from_utf8_lossy(&result.stderr).into_owned());
    }
    Ok(())
}
fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("source verification failed: {e}");
            ExitCode::FAILURE
        }
    }
}
fn run() -> Result<(), String> {
    let a: Vec<_> = env::args().collect();
    if a.len() < 4 {
        return Err("usage: verify-source CAPSULE_DIR check-before|check-after TREE; or verify-source CAPSULE_DIR replay BASE_TREE NEW_OUTPUT".into());
    }
    let capsule = Path::new(&a[1]);
    let patch = regular(capsule, "recovery-lock-test-isolation.patch", false)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if hash(&patch)? != PATCH_SHA {
        return Err("recovery-lock-test-isolation.patch digest mismatch".into());
    }
    let mode = a[2].as_str();
    let tree = Path::new(&a[3]);
    match mode {
        "check-before" | "check-after" => {
            if a.len() != 4 {
                return Err("unexpected extra argument".into());
            }
            check(tree, mode == "check-after")?;
        }
        "replay" => {
            if a.len() != 5 {
                return Err("replay requires BASE_TREE and NEW_OUTPUT".into());
            }
            check(tree, false)?;
            let out = Path::new(&a[4]);
            fs::DirBuilder::new()
                .mode(0o700)
                .create(out)
                .map_err(|e| format!("output must be new and have an existing parent: {e}"))?;
            for pin in PINS {
                if pin.before.is_some() {
                    let target = out.join(pin.path);
                    let parent = target.parent().ok_or("missing parent")?;
                    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
                    fs::copy(tree.join(pin.path), target).map_err(|e| e.to_string())?;
                }
            }
            check(out, false)?;
            git_apply(out, &patch, true)?;
            git_apply(out, &patch, false)?;
            check(out, true)?;
        }
        _ => return Err("unknown verification mode".into()),
    }
    println!(
        "{{\"scope\":\"1 declared source file\",\"mode\":\"{}\",\"verified_files\":1,\"patch_sha256\":\"{}\",\"runtime_qualified\":false}}",
        mode, PATCH_SHA
    );
    Ok(())
}
