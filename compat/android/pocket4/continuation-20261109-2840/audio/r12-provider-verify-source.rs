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
const PATCH_SHA: &str = "424d7f0c70adc13d9059c727c25abf323d020234c8db20459e0617d11d3f4160";
const PINS: &[Pin] = &[
    Pin { path: "android/manifest/audio-bridge-source-lock.json", before: Some("db5187942e23ef535cfc53ebe47e98ef3e258a9f79d225a621f8fd20cded9a91"), after: "22ae84b8d0747e371096035f46e636a00990d2a7b4cae8c5727f56fa946d1ee3" },
    Pin { path: "tools/droidloom-source/src/lib.rs", before: Some("a7ed63338cf2d997df829e8f8a5f2fb0c322b4ff071a40c84caa880654ff0722"), after: "3cef5ac4c844b1b2ba66d2cc3f4e536349b58d88e43a4365316734dadd560750" },
    Pin { path: "tools/droidloom-update/src/android.rs", before: Some("25ede448bfe8bb622361f128ec9a57a264104abe5462e106934530e6c9c9bf35"), after: "4044c83e0ebe5d95ce23d57f0ee5f4cc99160c1155f2887eff10d4deca2d9b18" },
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
    let patch = regular(capsule, "r12-original-provider-closure.patch", false)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if hash(&patch)? != PATCH_SHA {
        return Err("r12-original-provider-closure.patch digest mismatch".into());
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
