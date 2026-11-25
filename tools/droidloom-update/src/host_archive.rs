//! Export the normal host stage, including the protected empty StateDirectory.
use crate::{package, util::*};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    os::unix::fs::{DirBuilderExt, MetadataExt},
    path::Path,
    process::{Command, Stdio},
};

const STATE: &str = "var/lib/droidloom-mac-calibration";
const PUBLIC_APKS: &str = "var/lib/droidloom-public-apks";
const ARCHIVE: &str = "HOST-STAGE.tar.xz";
const MANIFEST: &str = "HOST-STAGE.json";
// This installed template drop-in is the only host member outside the existing
// /usr and SELinux trees. Do not admit arbitrary systemd configuration or @ paths.
const NATIVE_RUNTIME_DROPIN: &str =
    "etc/systemd/system/user-runtime-dir@.service.d/50-droidloom-native-session.conf";

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
struct Member {
    path: String,
    size: u64,
    sha256: String,
    mode: u32,
}
#[derive(Debug, PartialEq, Eq)]
struct Node(u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64);
fn node(m: &fs::Metadata) -> Node {
    Node(
        m.dev(),
        m.ino(),
        m.mode(),
        m.uid(),
        m.gid(),
        m.nlink(),
        m.len(),
        m.mtime(),
        m.mtime_nsec(),
        m.ctime(),
        m.ctime_nsec(),
    )
}
fn state_directory(stage: &Path) -> Result<Node> {
    empty_directory(stage, STATE, 0o700)
}
fn empty_directory(stage: &Path, relative: &str, mode: u32) -> Result<Node> {
    let path = stage.join(relative);
    let m = fs::symlink_metadata(&path)?;
    if !m.is_dir() || m.mode() & 0o7777 != mode || fs::read_dir(&path)?.next().is_some() {
        return fail(
            "normal host fixed directory must be ordinary, empty and have its exact declared mode",
        );
    }
    Ok(node(&m))
}
fn snapshot(stage: &Path) -> Result<(Vec<Member>, Vec<Node>)> {
    if !stage.is_absolute() || stage.canonicalize()? != stage {
        return fail("host stage must have a canonical absolute path");
    }
    let mut rows = Vec::new();
    let mut nodes = vec![
        state_directory(stage)?,
        empty_directory(stage, PUBLIC_APKS, 0o755)?,
    ];
    for path in files(stage)? {
        let relative = path
            .strip_prefix(stage)?
            .to_str()
            .ok_or("non-UTF8 host member")?;
        if relative != NATIVE_RUNTIME_DROPIN
            && (!(relative.starts_with("usr/") || relative.starts_with("etc/selinux/"))
                || !relative
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"/_.-".contains(&b))
                || relative
                    .split('/')
                    .any(|p| p == "." || p == ".." || p.is_empty()))
        {
            return fail(format!("unexpected host release member path: {relative}"));
        }
        let m = fs::symlink_metadata(&path)?;
        if !m.is_file() || m.nlink() != 1 || m.len() >= 32 * 1024 * 1024 || m.mode() & 0o7022 != 0 {
            return fail("host release contains a linked, special, oversized or writable member");
        }
        let before = node(&m);
        let sha256 = hash(&path)?;
        if node(&fs::symlink_metadata(&path)?) != before {
            return fail("host member changed while hashing");
        }
        nodes.push(before);
        rows.push(Member {
            path: relative.into(),
            size: m.len(),
            sha256,
            mode: m.mode() & 0o777,
        });
    }
    if rows.is_empty() || rows.len() > 128 {
        return fail("host release member count outside bound");
    }
    Ok((rows, nodes))
}
fn source_identity(repo: &Path) -> Result<(String, String)> {
    let read = |args: &[&str]| output(Command::new("git").arg("-C").arg(repo).args(args));
    if !read(&["status", "--porcelain", "--untracked-files=all"])?.is_empty() {
        return fail("host release requires a clean source checkout");
    }
    let head = read(&["rev-parse", "HEAD"])?;
    let tree = read(&["rev-parse", "HEAD^{tree}"])?;
    if ![&head, &tree].iter().all(|s| {
        s.len() == 40
            && s.bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    }) {
        return fail("host release source identity is not a Git SHA-1");
    }
    Ok((head, tree))
}
fn tar() -> Command {
    let mut command = Command::new("tar");
    command
        .env_remove("TAR_OPTIONS")
        .env_remove("XZ_DEFAULTS")
        .env("XZ_OPT", "-T1")
        .env("LC_ALL", "C");
    command
}
fn create_file(path: &Path, body: &[u8]) -> Result<()> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(body)?;
    file.sync_all()?;
    Ok(())
}
fn export(stage: &Path, output_root: &Path, source: &(String, String)) -> Result<Value> {
    let parent = output_root.parent().ok_or("host export lacks parent")?;
    if !output_root.is_absolute() || parent.canonicalize()? != parent {
        return fail("host export parent must be a canonical absolute directory");
    }
    let (members, nodes) = snapshot(stage)?;
    fs::DirBuilder::new().mode(0o700).create(output_root)?;
    let partial = output_root.join("HOST-STAGE.tar.xz.partial");
    let mut names = members.iter().map(|m| m.path.as_str()).collect::<Vec<_>>();
    names.push(STATE);
    names.push(PUBLIC_APKS);
    names.sort_unstable();
    let mut list = Vec::new();
    for name in names {
        list.extend_from_slice(name.as_bytes());
        list.push(0);
    }
    let mut command = tar();
    command
        .args([
            "--create",
            "--xz",
            "--format=ustar",
            "--mtime=@0",
            "--owner=0",
            "--group=0",
            "--numeric-owner",
            "--no-recursion",
            "--null",
            "--verbatim-files-from",
            "--directory",
        ])
        .arg(stage)
        .arg("--file")
        .arg(&partial)
        .arg("--files-from=-")
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    let mut child = command.spawn()?;
    child
        .stdin
        .take()
        .ok_or("tar input missing")?
        .write_all(&list)?;
    let result = child.wait_with_output()?;
    if !result.status.success() {
        return fail(format!(
            "normal host archive failed: {}",
            String::from_utf8_lossy(&result.stderr)
        ));
    }
    if snapshot(stage)? != (members.clone(), nodes) {
        return fail("normal host stage changed during export");
    }
    let readback = tempfile::Builder::new()
        .prefix(".host-readback-")
        .tempdir_in(output_root)?;
    run(tar()
        .args([
            "--extract",
            "--xz",
            "--same-permissions",
            "--no-same-owner",
            "--file",
        ])
        .arg(&partial)
        .arg("--directory")
        .arg(readback.path()))?;
    if snapshot(readback.path())?.0 != members {
        return fail(
            "host archive readback differs from normal staged files or empty state directory",
        );
    }
    readback.close()?;
    fs::File::open(&partial)?.sync_all()?;
    let archive = output_root.join(ARCHIVE);
    fs::rename(&partial, &archive)?;
    let manifest = json!({
        "commit":source.0,"tree":source.1,"stage":stage,
        "files":members,
        "directories":[{"path":STATE,"uid":0,"gid":0,"mode":0o700,"empty":true},
                       {"path":PUBLIC_APKS,"uid":0,"gid":0,"mode":0o755,"empty":true}]
    });
    let manifest_path = output_root.join(MANIFEST);
    let mut body = serde_json::to_vec_pretty(&manifest)?;
    body.push(b'\n');
    create_file(&manifest_path, &body)?;
    let result = json!({
        "schema":"droidloom-normal-container-host-release-v1",
        "commit":source.0,"tree":source.1,"stage":stage,
        "archive":{"path":archive,"size":fs::metadata(&archive)?.len(),"sha256":hash(&archive)?},
        "manifest":{"path":manifest_path,"size":body.len(),"sha256":hash(&manifest_path)?},
        "files_verified":members.len(),"protected_empty_directories_verified":1,
        "public_apk_input_roots_verified":1,
        "runtime_qualified":false,"production_activated":false
    });
    let mut result_bytes = serde_json::to_vec_pretty(&result)?;
    result_bytes.push(b'\n');
    create_file(&output_root.join("RELEASE.json"), &result_bytes)?;
    fs::File::open(output_root)?.sync_all()?;
    Ok(result)
}

pub fn stage(
    repo: &Path,
    work: &Path,
    jobs: usize,
    policy: &Path,
    output_root: &Path,
) -> Result<Value> {
    fs::create_dir_all(work)?;
    let work = work.canonicalize()?;
    if output_root.parent() != Some(work.as_path()) {
        return fail(
            "host archive output must be a fresh direct child of the normal work directory",
        );
    }
    if fs::symlink_metadata(output_root).is_ok() {
        return fail("host archive output already exists");
    }
    let identity = source_identity(repo)?;
    let stage = package::stage_container_host(repo, &work, jobs, Some(policy))?;
    if source_identity(repo)? != identity {
        return fail("host source changed during normal compilation");
    }
    export(&stage, output_root, &identity)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    fn fixture() -> (tempfile::TempDir, std::path::PathBuf) {
        let temp = tempfile::tempdir().unwrap();
        let stage = temp.path().join("stage");
        fs::create_dir_all(stage.join(STATE)).unwrap();
        fs::set_permissions(stage.join(STATE), fs::Permissions::from_mode(0o700)).unwrap();
        fs::create_dir_all(stage.join(PUBLIC_APKS)).unwrap();
        fs::set_permissions(stage.join(PUBLIC_APKS), fs::Permissions::from_mode(0o755)).unwrap();
        fs::create_dir_all(stage.join("usr/share/droidloom")).unwrap();
        fs::write(
            stage.join("usr/share/droidloom/input"),
            b"original staged bytes\n",
        )
        .unwrap();
        fs::set_permissions(
            stage.join("usr/share/droidloom/input"),
            fs::Permissions::from_mode(0o444),
        )
        .unwrap();
        (temp, stage)
    }
    fn identity() -> (String, String) {
        ("a".repeat(40), "b".repeat(40))
    }
    #[test]
    fn normal_archive_contains_both_fixed_empty_directories_and_is_reproducible() {
        let (temp, stage) = fixture();
        let a = export(&stage, &temp.path().join("a"), &identity()).unwrap();
        let b = export(&stage, &temp.path().join("b"), &identity()).unwrap();
        assert_eq!(a["archive"]["sha256"], b["archive"]["sha256"]);
        let manifest: Value =
            serde_json::from_slice(&fs::read(temp.path().join("a").join(MANIFEST)).unwrap())
                .unwrap();
        assert_eq!(
            manifest["directories"],
            json!([{"path":STATE,"uid":0,"gid":0,"mode":448,"empty":true}, {"path":PUBLIC_APKS,"uid":0,"gid":0,"mode":493,"empty":true}])
        );
        let listing = output(
            tar()
                .arg("--list")
                .arg("--xz")
                .arg("--file")
                .arg(temp.path().join("a").join(ARCHIVE)),
        )
        .unwrap();
        assert_eq!(listing.lines().count(), 3);
        assert!(listing.lines().any(|l| l == format!("{PUBLIC_APKS}/")));
        assert!(listing.lines().any(|l| l == format!("{STATE}/")));
    }
    #[test]
    fn normal_native_configuration_and_hardware_entries_survive_real_archive_roundtrip() {
        let (temp, stage) = fixture();
        crate::package::stage_native_configuration_for_archive_test(&stage).unwrap();
        let output_root = temp.path().join("normal-native");
        export(&stage, &output_root, &identity()).unwrap();
        let manifest: Value =
            serde_json::from_slice(&fs::read(output_root.join(MANIFEST)).unwrap()).unwrap();
        let files = manifest["files"].as_array().unwrap();
        for (relative, expected) in [
            (
                "usr/lib/udev/rules.d/00-droidloom-native-hardware.rules",
                include_bytes!("../../../android/framework/droidloom-readiness/board-policy/00-droidloom-native-hardware.rules").as_slice(),
            ),
            (
                "usr/lib/systemd/system/systemd-udevd.service.d/50-droidloom-hardware-label.conf",
                include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-udev-hardware-label.conf").as_slice(),
            ),
            (
                "usr/lib/systemd/system/systemd-udev-trigger.service.d/50-droidloom-uevent-label.conf",
                include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-udev-trigger-label.conf").as_slice(),
            ),
            (
                "etc/systemd/system/user-runtime-dir@.service.d/50-droidloom-native-session.conf",
                include_bytes!("../../../android/framework/droidloom-readiness/board-policy/ubuntu-user-runtime-dir.conf").as_slice(),
            ),
        ] {
            let member = files.iter().find(|entry| entry["path"] == relative).unwrap();
            assert_eq!(member["mode"], 0o444);
            assert_eq!(member["size"], expected.len());
            assert_eq!(member["sha256"], hash(&stage.join(relative)).unwrap());
            let extracted = tar().arg("--extract").arg("--to-stdout").arg("--xz")
                .arg("--file").arg(output_root.join(ARCHIVE)).arg(relative).output().unwrap();
            assert!(extracted.status.success());
            assert_eq!(extracted.stdout, expected);
        }
        assert_eq!(manifest["directories"].as_array().unwrap().len(), 2);
    }
    #[test]
    fn missing_nonempty_or_wrong_mode_state_is_rejected_before_publication() {
        for case in 0..3 {
            let (temp, stage) = fixture();
            match case {
                0 => fs::remove_dir(stage.join(STATE)).unwrap(),
                1 => {
                    fs::write(stage.join(STATE).join("capture.pending"), b"prior capture").unwrap()
                }
                _ => fs::set_permissions(stage.join(STATE), fs::Permissions::from_mode(0o755))
                    .unwrap(),
            }
            let out = temp.path().join("release");
            assert!(export(&stage, &out, &identity()).is_err());
            assert!(!out.exists());
        }
    }
    #[test]
    fn public_input_root_must_be_empty_fixed_mode_and_ordinary() {
        for case in 0..4 {
            let (temp, stage) = fixture();
            let root = stage.join(PUBLIC_APKS);
            match case {
                0 => fs::remove_dir(&root).unwrap(),
                1 => fs::write(root.join("unexpected.apk"), b"unexpected").unwrap(),
                2 => fs::set_permissions(&root, fs::Permissions::from_mode(0o777)).unwrap(),
                _ => {
                    fs::remove_dir(&root).unwrap();
                    symlink(stage.join(STATE), &root).unwrap();
                }
            }
            let out = temp.path().join("release");
            assert!(export(&stage, &out, &identity()).is_err());
            assert!(!out.exists());
        }
    }
    #[test]
    fn linked_members_and_existing_output_are_refused() {
        for hard in [false, true] {
            let (temp, stage) = fixture();
            let source = stage.join("usr/share/droidloom/input");
            let link = stage.join("usr/share/droidloom/alias");
            if hard {
                fs::hard_link(&source, &link).unwrap()
            } else {
                symlink(&source, &link).unwrap()
            }
            assert!(export(&stage, &temp.path().join("release"), &identity()).is_err());
        }
        let (temp, stage) = fixture();
        let out = temp.path().join("release");
        fs::create_dir(&out).unwrap();
        fs::write(out.join("sentinel"), b"preserve").unwrap();
        assert!(export(&stage, &out, &identity()).is_err());
        assert_eq!(fs::read(out.join("sentinel")).unwrap(), b"preserve");
    }
}
