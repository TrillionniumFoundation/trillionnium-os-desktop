//! Qualification-only destination probe with a newly spawned owned Notes app.
//! No production authority, signer, model provider or effect ledger is created.
//! Run only under a task-owned isolated display; this is not the Hepta closure.

#[cfg(target_os = "linux")]
fn main() -> Result<(), Box<dyn std::error::Error>> {
    use std::io::{BufRead, BufReader, Read};
    use std::os::fd::OwnedFd;
    use std::os::unix::net::{UnixDatagram, UnixStream};
    use std::process::{Child, Command, Stdio};
    use std::sync::mpsc;
    use std::time::Duration;
    use trill_ui_broker::notes::{
        NotesDispatchBinding, NotesDispatchOutcome, NotesObservation, NotesTarget,
    };
    use trill_ui_core::notes::{
        sha256_hex, NotesReplace, NotesReplaceAction, NotesResult, NotesTargetIdentity,
    };

    if std::env::var("TRILL_NOTES_PROBE_ISOLATED").as_deref() != Ok("1") {
        return Err(
            "run under a task-owned Xvfb/Weston and set TRILL_NOTES_PROBE_ISOLATED=1".into(),
        );
    }
    let mut args = std::env::args_os().skip(1);
    let app = args
        .next()
        .ok_or("expected absolute path to trill-app-window")?;
    if args.next().is_some() || !std::path::Path::new(&app).is_absolute() {
        return Err("expected one absolute path to the built trill-app-window".into());
    }
    let mut random = [0u8; 32];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut random)?;
    let hex = |bytes: &[u8]| -> String { bytes.iter().map(|b| format!("{b:02x}")).collect() };
    let identity = NotesTargetIdentity {
        session_instance: hex(&random[..16]),
        task_id: 1,
        incarnation: hex(&random[16..]),
    };
    let (owner, app_channel) = UnixStream::pair()?;
    let (recovery, recovery_app) = UnixDatagram::pair()?;
    let (bootstrap, bootstrap_app) = UnixDatagram::pair()?;
    trill_ui_core::notes_private_unix::send_channels(
        &bootstrap,
        &serde_json::to_vec(&identity)?,
        &app_channel,
        &recovery_app,
        Duration::from_secs(1),
    )?;
    drop(app_channel);
    drop(recovery_app);
    drop(bootstrap);
    let target = NotesTarget::from_private_channels(owner, recovery, identity.clone())?;
    struct OwnedChild(Child);
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    let mut child = OwnedChild(
        Command::new(app)
            .args([
                "--kind",
                "notes",
                "--workspace",
                "build",
                "--task-id",
                "1",
                "--notes-session",
            ])
            .arg(&identity.session_instance)
            .arg("--notes-incarnation")
            .arg(&identity.incarnation)
            .env_remove("TRILL_HEPTA_AGENTD_SOCKET")
            .env_remove("TRILL_HEPTA_AGENT_ID")
            .env_remove("TRILL_HEPTA_SPAWN_GENERATION")
            .env_remove("TRILL_HEPTA_PEER_UID")
            .env_remove("TRILL_HEPTA_RUN_ID")
            .stdin(Stdio::from(OwnedFd::from(bootstrap_app)))
            .stdout(Stdio::piped())
            .spawn()?,
    );
    let stdout = child.0.stdout.take().ok_or("missing owned app stdout")?;
    let (sender, markers) = mpsc::sync_channel(8);
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        for _ in 0..8 {
            let mut bytes = Vec::new();
            if (&mut reader)
                .take(257)
                .read_until(b'\n', &mut bytes)
                .is_err()
                || bytes.len() > 256
                || bytes.last() != Some(&b'\n')
            {
                return;
            }
            bytes.pop();
            let Ok(line) = String::from_utf8(bytes) else {
                return;
            };
            if sender.try_send(line).is_err() {
                return;
            }
        }
    });
    if markers.recv_timeout(Duration::from_secs(15))? != "TRILL_UI_FIRST_FRAME_V1" {
        return Err("first application layout not observed".into());
    }
    let text = "Hepta Notes destination probe — 中文\nOwned isolated Linux window; target transport evidence.";
    let request = NotesReplace {
        schema_version: 1,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: "qualification-notes-target-only".into(),
        destination_id: target.destination_id(),
        target: identity,
        expected_revision: 0,
        text: text.into(),
    };
    let raw = serde_json::to_vec(&request)?;
    let digest = sha256_hex(&raw);
    let binding = NotesDispatchBinding {
        operation_id: request.operation_id.clone(),
        destination_id: request.destination_id,
        target: request.target.clone(),
        payload_sha256: digest.clone(),
    };
    let NotesDispatchOutcome::Applied(receipt) = target.enter_exact(&raw, &binding) else {
        return Err("Notes target did not acknowledge application mutation".into());
    };
    let NotesResult::Applied { revision, .. } = &receipt.result else {
        unreachable!()
    };
    let expected = format!(
        "TRILL_NOTES_LAYOUT_V1:{revision}:{}",
        sha256_hex(text.as_bytes())
    );
    if markers.recv_timeout(Duration::from_secs(3))? != expected {
        return Err("changed Notes layout did not match expected revision/content digest".into());
    }
    if target.observe(&request.operation_id, &digest) != NotesObservation::Applied(receipt.clone())
    {
        return Err("independent app receipt query did not match the applied result".into());
    }
    // An optional bounded pause leaves the owned window available to an
    // independent screenshot tool. It does not add pixel claims to this probe.
    let pause: u64 = std::env::var("TRILL_NOTES_PROBE_CAPTURE_MS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0)
        .min(10_000);
    println!(
        "{}",
        serde_json::json!({
            "profile": "isolated_linux_notes_target_transport",
            "app_pid": child.0.id(), "request_sha256": digest, "app_receipt": receipt,
            "independent_application_receipt_query": true,
            "changed_egui_layout_marker": true, "compositor_pixels_verified": false,
            "hepta_production_owner_run": false, "final_use_authority_run": false,
            "asterinas_run": false
        })
    );
    std::thread::sleep(Duration::from_millis(pause));
    Ok(())
}

#[cfg(not(target_os = "linux"))]
fn main() {
    eprintln!("Notes destination probe requires Linux");
    std::process::exit(77);
}
