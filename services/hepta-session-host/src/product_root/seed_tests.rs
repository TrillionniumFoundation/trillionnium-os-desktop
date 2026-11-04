//! Explicit installed-binary lifecycle check; no authority or turn is created.
use super::super::{Result, config::Inputs, fs, geometry::Product};
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::time::Instant;

#[test]
#[ignore = "requires explicit Root config, actual App Server ELF, and a private mount namespace"]
fn actual_seed_start_resume_closes_client_and_reaps_first_signal_child() -> Result<()> {
    // Invoke alone via unshare --mount --propagation private. This fixture
    // never takes ownership of an existing or partial deployment.
    // SAFETY: reads only this process's actual credentials and parent identity.
    let (uid, euid, parent) = unsafe { (libc::getuid(), libc::geteuid(), libc::getppid()) };
    if uid != 0 || euid != 0 {
        return Err("actual Root is required for the original seed lifecycle test".into());
    }
    let namespace = std::fs::read_link("/proc/self/ns/mnt")?;
    if namespace == std::fs::read_link(format!("/proc/{parent}/ns/mnt"))? {
        return Err("run this fixture in its own private mount namespace".into());
    }
    let input_path = std::env::var_os("TRILL_ROOT_SEED_TEST_CONFIG")
        .ok_or("an explicit Root0600 seed test configuration is required")?;
    let inputs = Inputs::read(Path::new(&input_path))?;
    if inputs.is_desktop() {
        return Err("the original Notes seed fixture requires the Notes-only profile".into());
    }
    let app_server_sha256 = fs::digest(&inputs.programs.app_server)?;
    let fresh = Product::create(&inputs)?;
    fs::json_new(&fresh.admin.join("original-inputs.json"), &inputs)?;
    assert!(fresh.mounted());
    let prefix_before = std::fs::symlink_metadata(&fresh.prefix)?;
    assert_eq!(prefix_before.mode() & 0o7777, 0o750);
    assert_eq!(prefix_before.uid(), 0);
    assert_eq!(prefix_before.gid(), inputs.gid);
    assert_eq!(
        std::fs::symlink_metadata(&fresh.admin)?.mode() & 0o7777,
        0o700
    );
    require_absent(&fresh.authority)?;
    require_absent(&fresh.prefix.join("a/state"))?;

    // Run the original Notes branch on the same current-thread runtime
    // as initialize: real RemoteAppServerClient, original Start/Resume and
    // client.shutdown, then the original ChildOwner's one SIGTERM and 10s wait.
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    let started = Instant::now();
    let super::ThreadSeed::Notes(receipt) = runtime.block_on(super::create(&inputs, &fresh))?
    else {
        return Err("the Notes-only seed fixture received a different profile receipt".into());
    };
    let elapsed_ms = started.elapsed().as_millis();
    receipt.verify_persisted()?;
    let receipt_path = fresh.admin.join("original-thread-seed.json");
    let stored: serde_json::Value = fs::read_root_json(&receipt_path)?;
    assert_eq!(stored, serde_json::to_value(&receipt)?);
    require_absent(&fresh.admin.join("seed.sock"))?;
    // The old socket placement let App Server's private-directory setup chmod
    // the product prefix to 0700, so the real Session could not reach Notes.
    // Both custody and actual dropped-owner access must survive Start/Resume.
    require_absent(&fresh.prefix.join("seed.sock"))?;
    let prefix_after = std::fs::symlink_metadata(&fresh.prefix)?;
    assert_eq!(
        (
            prefix_after.dev(),
            prefix_after.ino(),
            prefix_after.uid(),
            prefix_after.gid(),
            prefix_after.mode(),
        ),
        (
            prefix_before.dev(),
            prefix_before.ino(),
            prefix_before.uid(),
            prefix_before.gid(),
            prefix_before.mode(),
        )
    );
    require_seed_owner_access(&inputs, &fresh)?;
    require_absent(&fresh.authority)?;
    require_absent(&fresh.prefix.join("a/state"))?;
    for name in [
        "session.stdout",
        "session.stderr",
        "composition.json",
        "native-human-registration.json",
    ] {
        require_absent(&fresh.admin.join(name))?;
    }

    // Preserve all Core metadata and original logs. Check only the mount that
    // this Product actually created; do not force or lazily detach a mount.
    let observation_path = fresh.admin.join("seed-lifecycle-observation.json");
    let mountpoint = fresh.bind.mountpoint.clone();
    let mounted_identity = (fresh.bind.device, fresh.bind.inode);
    drop(runtime);
    drop(fresh);
    let retired = std::fs::metadata(&mountpoint)?;
    assert_ne!((retired.dev(), retired.ino()), mounted_identity);
    fs::json_new(
        &observation_path,
        &serde_json::json!({
            "schema": "trill.original-root.seed-lifecycle-test.v1",
            "scope": "original_seed_component_only",
            "app_server": inputs.programs.app_server,
            "app_server_sha256": app_server_sha256,
            "original_seed_receipt": receipt_path,
            "original_seed_create_returned": true,
            "create_elapsed_ms": elapsed_ms,
            "original_child_termination_deadline_ms": 10_000,
            "seed_socket_retired": true,
            "product_prefix_custody_preserved": true,
            "actual_owner_notes_access": true,
            "actual_owner_admin_access_refused": true,
            "authority_state_absent": true,
            "no_session_or_turn_submitted_by_fixture": true,
            "fresh_mount_detached": true,
            "production_qualified": false,
        }),
    )?;
    Ok(())
}

fn require_seed_owner_access(inputs: &Inputs, fresh: &Product) -> Result<()> {
    // Use the same configured, Root-custodied interpreter with the original
    // credential-drop helper. No authority, UI, or model request is submitted.
    let probe = r#"import os, sys
uid, gid = int(sys.argv[1]), int(sys.argv[2])
if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (uid, uid, gid, gid):
    raise RuntimeError("actual owner credentials differ")
for path in sys.argv[3:5]:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    os.close(descriptor)
try:
    descriptor = os.open(sys.argv[5], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
except PermissionError:
    pass
else:
    os.close(descriptor)
    raise RuntimeError("private Root administration became owner-accessible")
print("seed-owner-custody-ok")
"#;
    let mut command = std::process::Command::new(&inputs.programs.python);
    command
        .args(["-I", "-B", "-c", probe])
        .arg(inputs.uid.to_string())
        .arg(inputs.gid.to_string())
        .arg(&fresh.prefix)
        .arg(fresh.user.join("notes"))
        .arg(&fresh.admin)
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .stdin(std::process::Stdio::null());
    super::super::process::drop_to_owner(&mut command, inputs.uid, inputs.gid);
    let output = command.output()?;
    if !output.status.success() || output.stdout != b"seed-owner-custody-ok\n" {
        return Err(format!(
            "actual owner cannot traverse the seeded product with private administration: {}",
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(())
}

fn require_absent(path: &Path) -> Result<()> {
    match std::fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(_) => Err(format!("unexpected lifecycle test entry: {}", path.display()).into()),
    }
}
