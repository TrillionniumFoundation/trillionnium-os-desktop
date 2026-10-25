//! Signed, isolated ObjectiveStart through the unchanged original Agentd process.
//! Fleet/Supervisor, AuthBus claims, compiler and durable journal are original
//! crates. Only the explicit test producer has a signing key. No model turn,
//! Operations dispatch, external device action or UI completion is asserted.

use codex_hepta_learning_ledger::{
    DurableRunStartJournal, RunStartAdmissionBindingV1, RunStartAnchor, RunStartAppendDisposition,
    RunStartAppendReceipt, RunStartObjectiveDispositionV1, RunStartRecovery,
};
use codex_hepta_objective::decode_admission_profile_json_v1;
use codex_hepta_types::{Digest32, StableId};
use ed25519_dalek::SigningKey;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::Instant;

mod original_objective_fixture;
mod original_objective_export;
mod original_objective_owner;
mod original_objective_session;
use original_objective_fixture::{ActionSet, Fixture, PROFILE, claims, hex, signed_fixture, trust};
use original_objective_owner::{Owner, write_private};
use original_objective_session::{Options as SessionOptions, SessionProbe};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const AGENT: &str = "33333333-3333-4333-8333-333333333333";

fn require(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(std::io::Error::other(message).into())
    }
}

fn check(name: &str, evidence: Value) {
    println!(
        "{}",
        json!({"event":"objective_check","check":name,"evidence":evidence})
    );
}

fn verify_admission(
    value: &Value,
    fixture: &Fixture,
    generation: u64,
    disposition: &str,
) -> Result<()> {
    require(
        value["status"] == "admitted" && value["bytes_written"] == value["request_frame_bytes"],
        "actual transport did not return complete admission",
    )?;
    let receipt = &value["receipt"];
    require(
        receipt["run_id"] == fixture.request.body.run_id
            && receipt["objective_digest"] == fixture.objective_digest.to_string()
            && receipt["hard_constraint_digest"] == fixture.hard_constraint_digest.to_string()
            && receipt["disposition"] == disposition
            && receipt["response_generation"] == generation,
        "original admission disagrees with original compiler",
    )
}

fn verify_publication_receipt(value: &Value, original: &RunStartAppendReceipt) -> Result<()> {
    require(
        value["receipt"]["publication_digest"] == original.record_digest.to_string()
            && value["receipt"]["chain_digest"] == original.chain_digest.to_string(),
        "admission publication receipt differs from original durable record",
    )
}

fn verify_journal(
    owner: &Owner,
    fixtures: &[(&Fixture, &Value)],
    generation: u64,
    original_hash: &str,
) -> Result<Value> {
    require(
        !owner.snapshot()?.active,
        "cannot inspect the live owner's journal with recovery API",
    )?;
    let profile = decode_admission_profile_json_v1(PROFILE.as_bytes())?;
    let mut binding = b"hepta:agentd:objective-run-start-owner:v1\0".to_vec();
    binding.extend_from_slice(AGENT.as_bytes());
    binding.extend_from_slice(profile.digest()?.as_array());
    let binding = Digest32::of_bytes(&binding);
    let first = fixtures.first().ok_or("no expected journal records")?.1;
    let first_anchor = RunStartAnchor {
        sequence: 1,
        chain_digest: first["receipt"]["chain_digest"]
            .as_str()
            .ok_or("first receipt chain missing")?
            .parse()?,
    };
    let prefix = DurableRunStartJournal::recover(
        File::open(owner.evidence.join("compiled-journal.bin"))?,
        binding,
        4096,
        RunStartRecovery::Acknowledged(first_anchor),
    )?;
    require(
        prefix.records()?.len() == 1
            && prefix.conflicts()?.is_empty()
            && prefix.head_digest() == first_anchor.chain_digest,
        "first publication prefix does not match the first original receipt",
    )?;
    drop(prefix);
    let last = fixtures.last().ok_or("no expected journal records")?.1;
    let anchor = RunStartAnchor {
        sequence: fixtures.len() as u64,
        chain_digest: last["receipt"]["chain_digest"]
            .as_str()
            .ok_or("chain digest missing")?
            .parse()?,
    };
    // Read-only File prevents recovery from repairing/truncating evidence. An
    // incomplete file is a failure, never an opportunity to manufacture a pass.
    let mut journal = DurableRunStartJournal::recover(
        File::open(owner.journal_path())?,
        binding,
        4096,
        RunStartRecovery::Acknowledged(anchor),
    )?;
    require(
        journal.records()?.len() == fixtures.len() && journal.conflicts()?.is_empty(),
        "journal record count drift",
    )?;
    require(
        journal.head_digest() == anchor.chain_digest,
        "journal head differs from last actual receipt",
    )?;
    let mut records = Vec::new();
    for (index, (fixture, response)) in fixtures.iter().enumerate() {
        let record = journal
            .get(&StableId::new(&fixture.request.body.run_id)?)?
            .cloned()
            .ok_or("published run missing from journal")?;
        let request = &fixture.request;
        let body = &request.body;
        let signed = claims(request)?;
        let expected_admission = RunStartAdmissionBindingV1 {
            profile_id: fixture.admission.profile_id.clone(),
            profile_revision: fixture.admission.profile_revision.get(),
            profile_digest: fixture.admission.profile_digest,
            supplied_source_digest: fixture.admission.supplied_source_digest,
            intent_digest: fixture.admission.intent_digest,
            admitted_source_digest: fixture.admission.admitted_source_digest,
            observed_at_unix_micros: fixture.admission.observed_at_unix_micros,
            deadline_unix_micros: fixture
                .admission
                .deadline_unix_micros
                .ok_or("fixture deadline absent")?,
            authority: fixture.admission.authority,
        };
        let disposition = match record.disposition {
            RunStartObjectiveDispositionV1::Compiled => "compiled",
            RunStartObjectiveDispositionV1::ExplicitAbstain => "explicit_abstain",
        };
        require(
            record.snapshot.objective_digest == fixture.objective_digest
                && record.snapshot.hard_constraint_digest == fixture.hard_constraint_digest
                && record.snapshot.run_id.as_str() == body.run_id
                && record.snapshot.preference_state_digest.to_string()
                    == body.preference_state_digest
                && record.snapshot.model_tuple_digest.to_string() == body.model_tuple_digest
                && record.snapshot.prompt_registry_digest.to_string()
                    == body.prompt_registry_digest
                && record.snapshot.artifact_set_digest.to_string() == body.artifact_set_digest
                && record.snapshot.authority_epoch == body.authority_epoch
                && record.runtime_body_digest.to_string() == body.runtime_body_digest
                && record.objective_function_v1_digest == fixture.protocol_digest
                && record.objective_function_v1_bytes == fixture.protocol_bytes
                && record.snapshot.generation == generation
                && record.authentication.issuer_id == signed.issuer_id
                && record.authentication.key_epoch == signed.key_epoch.get()
                && record.authentication.message_id == signed.message_id
                && record.authentication.sequence == signed.sequence
                && record.authentication.expires_at_ms == signed.expires_at_ms
                && record.authentication.scope_digest == signed.scope_digest
                && record.authentication.signed_body_digest == signed.payload_digest
                && hex(&record.authentication.signature) == request.signature_hex
                && record.admission == expected_admission
                && response["receipt"]["disposition"] == disposition
                && !record.admission.authority.grants_any(),
            "durable original record identity/authority drift",
        )?;
        // The original public API returns the existing record's exact receipt
        // before its write path for an identical record. The recovered File is
        // read-only, so an unexpected append cannot manufacture new evidence.
        // This is local journal inspection, not another ObjectiveStart request.
        let head = journal.head_digest();
        let publication = journal.append(head, record.clone())?;
        require(
            publication.disposition == RunStartAppendDisposition::IdempotentReplay
                && publication.sequence == index as u64 + 1
                && journal.head_digest() == head,
            "read-only original record replay changed publication identity",
        )?;
        verify_publication_receipt(response, &publication)?;
        // Only one valid hex character changes. Correct run/body/chain fields
        // must not hide a wrong publication digest in an otherwise valid reply.
        let mut changed_digest = publication.record_digest.to_string();
        let replacement = if changed_digest.starts_with('1') {
            "2"
        } else {
            "1"
        };
        changed_digest.replace_range(..1, replacement);
        let mut changed = (**response).clone();
        changed["receipt"]["publication_digest"] = changed_digest.into();
        require(
            verify_publication_receipt(&changed, &publication).is_err(),
            "changed publication digest passed original journal binding",
        )?;
        records.push(json!({"run_id":record.snapshot.run_id.as_str(),
            "generation":record.snapshot.generation,"objective_digest":record.snapshot.objective_digest.to_string(),
            "hard_constraint_digest":record.snapshot.hard_constraint_digest.to_string(),
            "protocol_digest":record.objective_function_v1_digest.to_string(),
            "sequence":record.authentication.sequence,"disposition":disposition,
            "signed_body_digest":record.authentication.signed_body_digest.to_string(),
            "profile_digest":record.admission.profile_digest.to_string(),
            "publication_digest":publication.record_digest.to_string(),
            "chain_digest":publication.chain_digest.to_string(),"journal_sequence":publication.sequence,
            "publication_binding_checked":true,"changed_publication_digest_rejected":true,
            "authority_grants_any":record.admission.authority.grants_any()}));
    }
    drop(journal);
    require(
        owner.journal_hash()? == original_hash,
        "read-only original journal inspection changed bytes",
    )?;
    Ok(
        json!({"journal_sha256":original_hash,"acknowledged_sequence":anchor.sequence,
        "first_acknowledged_chain_digest":first_anchor.chain_digest.to_string(),
        "acknowledged_chain_digest":anchor.chain_digest.to_string(),"records":records}),
    )
}

fn run() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    require(
        args.len() >= 4,
        "usage: original-objective-probe AGENTD OBSERVER SUBMITTER FRESH-PRIVATE-ROOT [--session-bin PATH --ctl-bin PATH [--session-phase-dir PATH --session-ack-seconds N]]",
    )?;
    if args.get(4).is_some_and(|v| v == "--export-ready") { return original_objective_export::run(&args); }
    let session_options = SessionOptions::read(&args[4..])?;
    let session_enabled = session_options.is_some();
    let mut seed = [0_u8; 32];
    File::open("/dev/urandom")?.read_exact(&mut seed)?;
    let key = SigningKey::from_bytes(&seed);
    seed.fill(0);
    let mut owner = Owner::new(
        Path::new(&args[3]),
        PathBuf::from(&args[0]),
        PathBuf::from(&args[1]),
        PathBuf::from(&args[2]),
        &key,
    )?;
    let (spawn, observation) = owner.wait_running(None)?;
    let generation = observation["current_generation"]
        .as_u64()
        .ok_or("current owner generation missing")?;
    require(
        owner.read(spawn, Some("run.desktop-compiled"))?.is_null(),
        "fresh original owner already has test run",
    )?;
    let compiled = signed_fixture(&key, spawn, 1, "run.desktop-compiled", ActionSet::Read)?;
    let admitted = owner.submit(&compiled.request, spawn, 101, "01-compiled")?;
    verify_admission(&admitted, &compiled, generation, "compiled")?;
    require(
        admitted["receipt"]["idempotent"] == false,
        "fresh objective was marked replay",
    )?;
    let run = owner.read(spawn, Some(&compiled.request.body.run_id))?;
    require(
        run["phase"] == "admitted"
            && run["generation"] == generation
            && run["terminal_observed"] == false,
        "compiled objective did not enter original admitted state",
    )?;
    check(
        "compiled_original_admission",
        json!({"receipt":admitted["receipt"],"run":run}),
    );
    let compiled_hash = owner.journal_hash()?;
    fs::copy(
        owner.journal_path(),
        owner.evidence.join("compiled-journal.bin"),
    )?;
    let mut session = session_options
        .map(|options| {
            SessionProbe::start(
                options,
                Path::new(&args[3]),
                &owner,
                spawn,
                &compiled.request.body.run_id,
            )
        })
        .transpose()?;

    let duplicate = owner.submit(&compiled.request, spawn, 102, "02-exact-replay")?;
    verify_admission(&duplicate, &compiled, generation, "compiled")?;
    let mut expected = admitted["receipt"].clone();
    expected["idempotent"] = true.into();
    require(
        duplicate["receipt"] == expected && owner.journal_hash()? == compiled_hash,
        "exact signed replay appended or changed original publication",
    )?;
    check(
        "exact_replay_same_publication",
        json!({"receipt":duplicate["receipt"],"journal_sha256":compiled_hash}),
    );

    let abstain = signed_fixture(&key, spawn, 2, "run.desktop-abstain", ActionSet::Abstain)?;
    let abstained = owner.submit(&abstain.request, spawn, 103, "03-explicit-abstain")?;
    verify_admission(&abstained, &abstain, generation, "explicit_abstain")?;
    require(
        abstained["receipt"]["idempotent"] == false
            && owner
                .read(spawn, Some(&abstain.request.body.run_id))?
                .is_null(),
        "explicit abstain created a runtime run",
    )?;
    let published_hash = owner.journal_hash()?;
    require(
        published_hash != compiled_hash,
        "explicit abstain did not persist a publication",
    )?;
    check(
        "explicit_abstain_durable_without_run",
        json!({"receipt":abstained["receipt"],"journal_sha256":published_hash}),
    );

    let mut invalid = signed_fixture(
        &key,
        spawn,
        3,
        "run.desktop-invalid-signature",
        ActionSet::Read,
    )?;
    invalid.request.signature_hex = "00".repeat(64);
    let rejected = owner.submit(&invalid.request, spawn, 104, "04-invalid-signature")?;
    require(
        rejected["status"] == "submit_unknown"
            && rejected["issue"] == "objective_owner_request_rejected"
            && rejected["bytes_written"] == rejected["request_frame_bytes"]
            && owner.journal_hash()? == published_hash,
        "invalid signature did not produce bounded owner rejection without append",
    )?;
    check(
        "invalid_signature_owner_rejected",
        json!({"transport_status":"submit_unknown","journal_unchanged":true}),
    );

    let wrong_generation = signed_fixture(
        &key,
        spawn + 1,
        4,
        "run.desktop-wrong-generation",
        ActionSet::Read,
    )?;
    let fenced = owner.submit(
        &wrong_generation.request,
        spawn,
        105,
        "05-body-generation-mismatch",
    )?;
    require(
        fenced["status"] == "not_sent"
            && fenced["bytes_written"] == 0
            && owner.journal_hash()? == published_hash,
        "body generation mismatch was sent",
    )?;
    check(
        "body_generation_fenced_before_send",
        json!({"bytes_written":0,"journal_unchanged":true}),
    );

    let revoked_trust = serde_json::to_vec(&trust(&key, true))?;
    write_private(&owner.trust_file, &revoked_trust)?;
    write_private(
        &owner.evidence.join("revoked-public-trust.json"),
        &revoked_trust,
    )?;
    let revoked = signed_fixture(&key, spawn, 5, "run.desktop-revoked", ActionSet::Read)?;
    let rejected = owner.submit(&revoked.request, spawn, 106, "06-revoked-issuer")?;
    require(
        rejected["status"] == "submit_unknown"
            && rejected["issue"] == "objective_owner_request_rejected"
            && rejected["bytes_written"] == rejected["request_frame_bytes"]
            && owner.journal_hash()? == published_hash,
        "revoked isolated issuer did not remain rejected",
    )?;
    check(
        "revoked_issuer_owner_rejected",
        json!({"transport_status":"submit_unknown","journal_unchanged":true}),
    );
    // Restore only this disposable test registration for the generation test.
    write_private(&owner.trust_file, &serde_json::to_vec(&trust(&key, false))?)?;

    // Capture waits begin only after exact replay and time-sensitive fixture
    // admissions. A slow renderer never changes their authentication outcome.
    if let Some(session) = session.as_mut() {
        session.observed(&owner, spawn)?;
    }

    let old_pid = observation["health"]["process_id"].clone();
    owner.supervisor.restart(&owner.agent, Instant::now())?;
    let (new_spawn, restarted) = owner.wait_running(Some(spawn))?;
    require(
        restarted["health"]["process_id"] != old_pid
            && owner.journal_hash()? == published_hash
            && owner
                .read(new_spawn, Some(&compiled.request.body.run_id))?
                .is_null()
            && owner
                .read(new_spawn, Some(&abstain.request.body.run_id))?
                .is_null(),
        "restart changed publication or promoted historical run into new generation",
    )?;
    check(
        "owner_restart_retains_historical_journal",
        json!({"old_spawn":spawn,"new_spawn":new_spawn,
        "old_pid":old_pid,"new_pid":restarted["health"]["process_id"],"journal_sha256":published_hash,"historical_run_absent":true}),
    );
    let stale = owner.submit(&compiled.request, spawn, 107, "07-old-spawn-after-restart")?;
    let post_request_owner = owner.read(new_spawn, None)?;
    let post_request_run = owner.read(new_spawn, Some(&compiled.request.body.run_id))?;
    // The fixed original server identifies the new spawn in its rejection.
    // Our old endpoint must retain that mismatch as an unknown sent attempt;
    // transport loss alone cannot qualify the owner's generation boundary.
    // Missing current projection does not erase the historical publication.
    require(
        stale["status"] == "submit_unknown"
            && stale["issue"] == "objective_protocol_mismatch"
            && stale["bytes_written"]
                .as_u64()
                .is_some_and(|bytes| bytes > 0)
            && stale["bytes_written"] == stale["request_frame_bytes"]
            && post_request_owner["spawn_generation"] == new_spawn
            && post_request_owner["health"]["process_id"] == restarted["health"]["process_id"]
            && post_request_owner["health"]["ready"] == true
            && post_request_owner["health"]["lifecycle"] == "running"
            && post_request_run.is_null()
            && owner.journal_hash()? == published_hash,
        "old spawn did not retain sent-unknown semantics with the same live replacement owner",
    )?;
    check(
        "old_spawn_not_accepted",
        json!({"transport_status":stale["status"],"issue":stale["issue"],
            "bytes_written":stale["bytes_written"],"request_frame_bytes":stale["request_frame_bytes"],
            "post_request_owner":post_request_owner,"post_request_run":post_request_run,
            "journal_unchanged":true}),
    );
    if let Some(session) = session.as_mut() {
        session.stale(&owner)?;
        session.replace_missing(&owner, new_spawn)?;
    }

    owner.stop()?;
    require(
        owner.read(new_spawn, None).is_err(),
        "stopped owner still responds",
    )?;
    let decoded = verify_journal(
        &owner,
        &[(&compiled, &admitted), (&abstain, &abstained)],
        generation,
        &published_hash,
    )?;
    write_private(
        &owner.evidence.join("journal-inspection.json"),
        &serde_json::to_vec_pretty(&decoded)?,
    )?;
    fs::copy(
        owner.journal_path(),
        owner.evidence.join("final-journal.bin"),
    )?;
    check("original_journal_matches_receipts", decoded);
    check(
        "controlled_stop",
        json!({"active":owner.snapshot()?.active}),
    );
    println!(
        "{}",
        json!({"event":"acceptance_pass","evidence_class":"original_agentd_signed_objective_admission",
        "checks":["compiled_original_admission","exact_replay_same_publication","explicit_abstain_durable_without_run",
            "invalid_signature_owner_rejected","body_generation_fenced_before_send","revoked_issuer_owner_rejected",
            "owner_restart_retains_historical_journal","old_spawn_not_accepted","original_journal_matches_receipts","controlled_stop"],
        "original_commit":"f8c9419df6ddeb36ff8b522a50219981fb8d9345","isolated_test_issuer":true,
        "session_projection":session_enabled,
        "production_issuer":false,"model_turn":false,"operations_dispatch":false,"device_effect":false,
        "canonical_intelligence":false,"historical_run_resumed":false})
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("original-objective-probe failed: {error}");
        std::process::exit(1);
    }
}
