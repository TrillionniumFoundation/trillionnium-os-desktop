//! Original Supervisor/Agentd kept alive for the actual Shell acceptance test.
//! The signing key is a fresh qualification producer, never a product issuer.
use crate::original_objective_fixture::{signed_fixture, ActionSet, PROFILE};
use crate::original_objective_owner::{write_private, Owner};
use crate::{require, Result, AGENT};
use codex_hepta_learning_ledger::{DurableRunStartJournal, RunStartRecovery};
use codex_hepta_objective::decode_admission_profile_json_v1;
use codex_hepta_types::Digest32;
use ed25519_dalek::SigningKey;
use serde_json::json;
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

pub fn run(args: &[OsString]) -> Result<()> {
    require(args.len() == 5, "export-ready accepts no implicit paths")?;
    let mut seed = [0; 32];
    File::open("/dev/urandom")?.read_exact(&mut seed)?;
    let key = SigningKey::from_bytes(&seed);
    seed.fill(0);
    let root = Path::new(&args[3]);
    let mut owner = Owner::new(root, PathBuf::from(&args[0]), PathBuf::from(&args[1]), PathBuf::from(&args[2]), &key)?;
    let (spawn, observed) = owner.wait_running(None)?;
    let inbox = root.join("shell-inbox");
    fs::create_dir(&inbox)?;
    fs::set_permissions(&inbox, fs::Permissions::from_mode(0o700))?;
    let retained = inbox.join("retained");
    fs::create_dir(&retained)?;
    fs::set_permissions(&retained, fs::Permissions::from_mode(0o700))?;
    let valid = signed_fixture(&key, spawn, 1, "run.shell-valid", ActionSet::Read)?;
    let mut invalid = signed_fixture(&key, spawn, 2, "run.shell-invalid", ActionSet::Read)?;
    invalid.request.signature_hex = "00".repeat(64);
    let mut entries = Vec::new();
    for (index, (id, fixture)) in [("valid", &valid), ("invalid", &invalid)].into_iter().enumerate() {
        let path = inbox.join(format!("{id}.json"));
        let bytes = serde_json::to_vec(&fixture.request)?;
        write_private(&path, &bytes)?;
        entries.push(json!({"id":id,"envelope_path":path,"submit_request_id":101+2*index,"history_request_id":102+2*index}));
    }
    let config = inbox.join("config.json");
    write_private(&config, &serde_json::to_vec(&json!({"schema_version":1,
        "owner":{"socket_path":owner.socket,"agent_id":AGENT,"spawn_generation":spawn,"peer_uid":owner.uid,"peer_pid":observed["health"]["process_id"]},
        "retention_dir":retained,"entries":entries}))?)?;
    let ready = json!({"schema_version":1,"config_path":config,"stop_path":inbox.join("stop"),
        "journal_path":owner.journal_path(),"original_owner":observed,"initial_journal_sha256":owner.journal_hash()?,
        "isolated_test_issuer":true,"production_issuer":false,"model_turn":false,"device_effect":false});
    write_private(&inbox.join("ready.json"), &serde_json::to_vec(&ready)?)?;
    println!("{}", json!({"event":"objective_shell_ready","ready":ready}));
    let deadline = Instant::now() + Duration::from_secs(180);
    while !inbox.join("stop").exists() {
        require(Instant::now() < deadline, "Shell fixture deadline elapsed")?;
        owner.tick()?;
        require(owner.snapshot()?.active, "original owner exited before fixture stop")?;
        std::thread::sleep(Duration::from_millis(25));
    }
    owner.stop()?;
    let before = owner.journal_hash()?;
    let profile = decode_admission_profile_json_v1(PROFILE.as_bytes())?;
    let mut binding = b"hepta:agentd:objective-run-start-owner:v1\0".to_vec();
    binding.extend_from_slice(AGENT.as_bytes());
    binding.extend_from_slice(profile.digest()?.as_array());
    // Read-only recovery after controlled stop. This checks the owner journal,
    // not an external rollback witness and not the UI's local client marker.
    let mut journal = DurableRunStartJournal::recover(File::open(owner.journal_path())?, Digest32::of_bytes(&binding), 4096, RunStartRecovery::Unacknowledged)?;
    let records = journal.records()?.into_iter().cloned().collect::<Vec<_>>();
    let mut publications = Vec::new();
    for record in records {
        let receipt = journal.append(journal.head_digest(), record.clone())?;
        publications.push(json!({"run_id":record.snapshot.run_id.to_string(),"publication_digest":receipt.record_digest.to_string(),"chain_digest":receipt.chain_digest.to_string(),"sequence":receipt.sequence}));
    }
    require(journal.conflicts()?.is_empty(), "unexpected fixture conflicts")?;
    drop(journal);
    require(before == owner.journal_hash()?, "read-only inspection changed original journal")?;
    let final_state = json!({"schema_version":1,"active":owner.snapshot()?.active,"journal_sha256":before,
        "publications":publications,"read_only_original_journal":true,"external_rollback_witness":false,
        "isolated_test_issuer":true,"production_issuer":false,"model_turn":false,"device_effect":false});
    write_private(&inbox.join("final.json"), &serde_json::to_vec(&final_state)?)?;
    println!("{}", json!({"event":"objective_shell_stopped","result":final_state}));
    Ok(())
}
