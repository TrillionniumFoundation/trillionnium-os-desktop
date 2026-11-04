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
    require_absent(&fresh.prefix.join("seed.sock"))?;
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
            "authority_state_absent": true,
            "no_session_or_turn_submitted_by_fixture": true,
            "fresh_mount_detached": true,
            "production_qualified": false,
        }),
    )?;
    Ok(())
}

fn require_absent(path: &Path) -> Result<()> {
    match std::fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(_) => Err(format!("unexpected lifecycle test entry: {}", path.display()).into()),
    }
}
