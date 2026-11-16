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
const PATCH_SHA: &str = "c45a3e749fdb91c4835cc91b5ae15c99cb09f890faf80287d7d74582dbb45c67";
const PINS: &[Pin] = &[
    Pin { path: "runtime/droidloom-supervisor/src/production_namespace_binder_child.rs", before: Some("61e239e17deeb9fbfff346055510cc8ece7181d0c0ec36065c890d5a34df08b1"), after: "963907d9c0d0351d2d786ec86863f67483b17475b9cc1d6132d308a31f0bd3bc" },
    Pin { path: "runtime/droidloom-supervisor/src/production_namespace_binder_ipc_child.rs", before: Some("abfcd730ff90b070f3db936daf29bfa901cdcd2fc8ed766e4e6e8b7be31152d3"), after: "b2e91a38012c533da580e0506ae7fd088c8eeca8552308df4e159ca0bb1ecf99" },
    Pin { path: "runtime/droidloom-supervisor/src/production_namespace_binder_parent.rs", before: Some("dff11205d6d6752a4b8f08d947745dcefa74d42d54cc64645a5de5ea206d047a"), after: "ad7b9aa3b7a2ba81c35dd0a4cd66ca80e3e4a4f202a0b5584f9eb6b7607aef71" },
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
    let patch = regular(capsule, "c11-review-combined.patch", false)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if hash(&patch)? != PATCH_SHA {
        return Err("c11-review-combined.patch digest mismatch".into());
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
        "{{\"scope\":\"3 declared source files\",\"mode\":\"{}\",\"verified_files\":3,\"patch_sha256\":\"{}\",\"runtime_qualified\":false}}",
        mode, PATCH_SHA
    );
    Ok(())
}
