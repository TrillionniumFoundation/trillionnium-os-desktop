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
const PATCH_SHA: &str = "972500d13d451ce5d07a23fbfbd8cd9e113726029e59b81fd715ad64b4353d0c";
const PINS: &[Pin] = &[
    Pin { path: "runtime/droidloom-supervisor/src/control.rs", before: Some("62821422867785c6b78eb2fa447857ed214c1b44f3ac47111d37da5057e7a652"), after: "22cfe98ff60bb9ef5cf977cecf5867bdfc955ef39d86030a0d358d5a06820700" },
    Pin { path: "runtime/droidloom-supervisor/src/application_settings.rs", before: None, after: "3381d1c6a635899d77b34794d838996d6eb18fffeeece71c57dbbe75b1a3be11" },
    Pin { path: "runtime/droidloom-supervisor/src/application_settings_protocol.rs", before: None, after: "d9462c9df927f0d4928276f4a4880aa8d39dbca60fb9f20fef8f808c0d25635d" },
    Pin { path: "runtime/droidloom-supervisor/src/application_action_scope.rs", before: None, after: "4984cdebfc3dd0bdd3b1101ca40430bd6f9239b218a1d03680829f5fab5b0c0c" },
    Pin { path: "runtime/droidloom-supervisor/src/application_settings_tests.rs", before: None, after: "7153ca66acc6622fbe949495ff218aba396688a49a1438537fd52ad27ae29c39" },
    Pin { path: "android/framework/droidloom-task-launcher/src/lib.rs", before: Some("8c2bd767a62d6d16a3e02daf7fc992d6c4f79adf6d61efd7c6c199b6650f08d0"), after: "5ba1b119f5898fb9d562f8ffdfc6092736d432b29a13a587d6a7b7616a4c3010" },
    Pin { path: "android/framework/droidloom-task-launcher/src/main.rs", before: Some("23bb117afd8aa81e23f23b20ce8b4ca9901e7e17a20315d29b3d922b77c789ba"), after: "d875eaf699c5716abb986912c66fc918df9adf60730afaeff3acf8ed99bb6325" },
    Pin { path: "runtime/droidloom-applications/src/runtime_plan.rs", before: Some("2f5a815833e299d022a3680014167e7418bf6b39488849fb5150b5bcef861032"), after: "8ceaa206dd0bd80fde538c6f483cf1565981354e6467394531298317dc8a6b8b" },
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
    let patch = regular(capsule, "settings-failclosed.patch", false)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if hash(&patch)? != PATCH_SHA {
        return Err("settings-failclosed.patch digest mismatch".into());
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
        "{{\"scope\":\"8 declared source files\",\"mode\":\"{}\",\"verified_files\":8,\"patch_sha256\":\"{}\",\"runtime_qualified\":false}}",
        mode, PATCH_SHA
    );
    Ok(())
}
