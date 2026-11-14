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
const PATCH_SHA: &str = "01019f05117d998a59243a44f114a00b4aae8b8a1019b8e5bd8f07a74b6dae45";
const PINS: &[Pin] = &[
    Pin {
        path: "docs/contracts/runtime-layout-v1.md",
        before: Some("f737014cf45be70b7a2089f37c189d2540bfcd9f9c19a2086677f8f6b39c5ce9"),
        after: "7f871b73582b43740926e9f66ac068c39c595dcf4df4fc5f484d84a7be951c73",
    },
    Pin {
        path: "docs/threat-model-v1.md",
        before: Some("02f9aa4531344f2d39c59a939b5a469be599e05b3140a95efde3e0524d46016f"),
        after: "f916b4783272a4573b2573040ead999fda07e31a74cf1bdd1c91fd06494e455b",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/control.rs",
        before: Some("50d7bc3abd94f83233ef7d461f93cb714f843cacb3fd5c0e929d06671a95f89b"),
        after: "46279b7c0b382f64d03f73e576e774152f39725aeb240050669db7cea9b2e90f",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/development.rs",
        before: Some("7745991017baaf8bd2e1ba6a5500465a9732c4b8356bd4edd6257a09d3ba2d95"),
        after: "2ef2429a74fa8c66c0f78c11056503c3ed50ce254b0345a9f8a716d6bf136ce2",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/lib.rs",
        before: Some("2ffbdfabad12878deb12f069f509fdd654058ad7deeac60eae77926dee18c5a4"),
        after: "24ee3240d749797424e25fb0f98021fc721a16a5f699b9bde9bd58d8feac3847",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/linux_plan.rs",
        before: Some("51638df0266e5a7e8abc148c08917c62b8de6467bde0dec097a70afd097de92f"),
        after: "d8dc23214b6ac4d229d4f29577ffa0fe233ae06a7d8396e149b214a59990191b",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/main.rs",
        before: Some("9767d6cdacb7fe673c6e95048c7e680995151dc39dad8aaee403114108bf7981"),
        after: "aae7d4d208da37eaa87a5f64c70c6dc510940c8f34543cee4ccfec9b525ecc0e",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/production_identity.rs",
        before: Some("2e9e21cc0c7d4aa60c7c43d310761006642876e33e93d14ec6eb3afad303aabb"),
        after: "44822e3982ae7645c057e3622e8c2c68da64e6c820e569dfd62d5c30f3f07fb8",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/production_namespace.rs",
        before: None,
        after: "32bc2e34986246afda38370795f1c56d567cc6c2646762ef38fd7a601733b6e3",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/production_namespace_child.rs",
        before: None,
        after: "5c3d143be5a58f8986ea0dd4b2c8b4f0f586e8bc65da0069ababcbca2561a2aa",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/production_namespace_tests.rs",
        before: None,
        after: "d3372123a268adb14fef4d3ec29372a029676316f6f9e2b8888c550ffefa09e9",
    },
    Pin {
        path: "runtime/droidloom-supervisor/src/sealed_spec.rs",
        before: None,
        after: "d3b95b594748488c1c3648e9fbae8f945003ca665e257cab86363c852aeaf842",
    },
    Pin {
        path: "runtime/droidloom-supervisor/tests/fixtures/sealed-entry-probe.rs",
        before: None,
        after: "933569f16f7b871436ef57eb8134a335aeb12a0710eb1f4776345698859c879e",
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
    let patch = regular(capsule, "combined.patch", false)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if hash(&patch)? != PATCH_SHA {
        return Err("combined.patch digest mismatch".into());
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
        "{{\"scope\":\"13 declared source files\",\"mode\":\"{}\",\"verified_files\":13,\"patch_sha256\":\"{}\",\"runtime_qualified\":false}}",
        mode, PATCH_SHA
    );
    Ok(())
}
