//! Real signed ObjectiveStart history through its separately pinned owner.
//! Recovery uses the retained request/run identities, not Operations K/D.
//! The response-loss fault belongs to this harness; it is not a hepta-submit
//! CLI lost-reply execution. All storage faults happen after the owner stops.

use codex_hepta_types::Digest32;
use ed25519_dalek::SigningKey;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

mod objective_history_client;
mod original_objective_fixture;
mod original_objective_owner;

use objective_history_client::{anchor, lose_submission_response, publication, query, unknown};
use original_objective_fixture::{ActionSet, Fixture, sign, signed_fixture, trust};
use original_objective_owner::{Owner, write_private};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const AGENT: &str = "33333333-3333-4333-8333-333333333333";
const CHECKS: &[&str] = &[
    "live_compiled_publication",
    "live_abstain_publication",
    "retained_anchor_covers_publication",
    "harness_lost_response_then_history",
    "postpublication_submit_unknown_history_published",
    "wrong_anchor_unknown",
    "earlier_anchor_unknown",
    "changed_signed_request_unknown",
    "restart_projection_missing_history_published",
    "expired_request_history_still_published",
    "rollback_retained_anchor_unknown",
    "truncated_tail_retained_anchor_unknown",
    "revoked_issuer_history_still_published",
    "revoked_new_submission_rejected",
    "controlled_stop",
];

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
        json!({"event":"objective_history_check","check":name,"evidence":evidence})
    );
}

fn generation(observation: &Value) -> Result<u64> {
    observation["current_generation"]
        .as_u64()
        .ok_or_else(|| "owner generation missing".into())
}

fn wall_clock_ms() -> Result<u64> {
    Ok(u64::try_from(
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis(),
    )?)
}

fn verify_admission(receipt: &Value, fixture: &Fixture, disposition: &str) -> Result<()> {
    require(
        receipt["status"] == "admitted"
            && receipt["bytes_written"] == receipt["request_frame_bytes"]
            && receipt["receipt"]["run_id"] == fixture.request.body.run_id
            && receipt["receipt"]["objective_digest"] == fixture.objective_digest.to_string()
            && receipt["receipt"]["hard_constraint_digest"]
                == fixture.hard_constraint_digest.to_string()
            && receipt["receipt"]["disposition"] == disposition
            && receipt["receipt"]["idempotent"] == false
            && !fixture.admission.authority.grants_any()
            && Digest32::of_bytes(&fixture.protocol_bytes) == fixture.protocol_digest,
        "real admission did not match isolated original compiler",
    )
}

fn receipt_matches(result: &Value, submitted: &Value, disposition: &str) -> Result<()> {
    require(
        result["publication"]["publication_digest"] == submitted["receipt"]["publication_digest"]
            && result["publication"]["chain_digest"] == submitted["receipt"]["chain_digest"]
            && result["response_generation"] == submitted["receipt"]["response_generation"]
            && result["publication"]["outcome"]["type"] == disposition,
        "history publication disagrees with original submission receipt",
    )
}

fn stopped_fault_restart(
    owner: &mut Owner,
    previous_spawn: u64,
    label: &str,
    bytes: &[u8],
) -> Result<(u64, Value, Value)> {
    owner.stop()?;
    require(
        !owner.snapshot()?.active && owner.read(previous_spawn, None).is_err(),
        "storage fault requires original owner confirmed stopped",
    )?;
    let before = fs::read(owner.journal_path())?;
    write_private(
        &owner.evidence.join(format!("{label}-before-journal.bin")),
        &before,
    )?;
    write_private(
        &owner.evidence.join(format!("{label}-injected-journal.bin")),
        bytes,
    )?;
    write_private(&owner.journal_path(), bytes)?;
    let injected_hash = Digest32::of_bytes(bytes).to_string();
    require(
        owner.journal_hash()? == injected_hash,
        "fault file write mismatch",
    )?;
    owner.supervisor.restart(&owner.agent, Instant::now())?;
    let (spawn, observation) = owner.wait_running(Some(previous_spawn))?;
    let after = fs::read(owner.journal_path())?;
    write_private(
        &owner
            .evidence
            .join(format!("{label}-recovered-journal.bin")),
        &after,
    )?;
    let evidence = json!({"fault":label,"owner_confirmed_stopped_before_fault":true,
        "before_sha256":Digest32::of_bytes(&before).to_string(),
        "injected_sha256":injected_hash,"injected_bytes":bytes.len(),
        "recovered_sha256":Digest32::of_bytes(&after).to_string(),"recovered_bytes":after.len(),
        "old_spawn":previous_spawn,"new_spawn":spawn,
        "new_pid":observation["health"]["process_id"],"recovery_owner":"original_agentd"});
    Ok((spawn, observation, evidence))
}

fn run() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    require(
        args.len() == 5,
        "usage: objective-history-probe AGENTD OBSERVER SUBMITTER HISTORY FRESH-PRIVATE-ROOT",
    )?;
    let binding: Value =
        serde_json::from_str(include_str!("objective_history_source_binding.json"))?;
    let mut seed = [0_u8; 32];
    File::open("/dev/urandom")?.read_exact(&mut seed)?;
    let key = SigningKey::from_bytes(&seed);
    seed.fill(0);
    let mut owner = Owner::new(
        Path::new(&args[4]),
        PathBuf::from(&args[0]),
        PathBuf::from(&args[1]),
        PathBuf::from(&args[2]),
        &key,
    )?;
    let history = Path::new(&args[3]);
    let (initial_spawn, initial) = owner.wait_running(None)?;
    let initial_generation = generation(&initial)?;

    let compiled = signed_fixture(
        &key,
        initial_spawn,
        1,
        "run.history-compiled",
        ActionSet::Read,
    )?;
    let submitted = owner.submit(&compiled.request, initial_spawn, 101, "01-compiled")?;
    verify_admission(&submitted, &compiled, "compiled")?;
    let first = query(
        &owner,
        history,
        initial_spawn,
        &compiled.request,
        None,
        "01-compiled",
        201,
    )?;
    publication(&first, &compiled, initial_spawn, 1, initial_generation)?;
    receipt_matches(&first, &submitted, "compiled")?;
    let first_anchor = anchor(&first)?;
    let first_journal = fs::read(owner.journal_path())?;
    write_private(
        &owner.evidence.join("01-compiled-journal.bin"),
        &first_journal,
    )?;
    check(CHECKS[0], json!({"submission":submitted,"history":first}));

    let mut abstain = signed_fixture(
        &key,
        initial_spawn,
        2,
        "run.history-abstain",
        ActionSet::Abstain,
    )?;
    abstain.request.expires_at_ms = wall_clock_ms()?
        .checked_add(25_000)
        .ok_or("expiry overflow")?;
    sign(&key, &mut abstain.request)?;
    require(
        wall_clock_ms()? < abstain.request.expires_at_ms,
        "short-lived abstain request expired before its only submission",
    )?;
    let submitted_abstain = owner.submit(&abstain.request, initial_spawn, 102, "02-abstain")?;
    verify_admission(&submitted_abstain, &abstain, "explicit_abstain")?;
    let second = query(
        &owner,
        history,
        initial_spawn,
        &abstain.request,
        None,
        "02-abstain",
        202,
    )?;
    publication(&second, &abstain, initial_spawn, 2, initial_generation)?;
    receipt_matches(&second, &submitted_abstain, "explicit_abstain")?;
    require(
        owner
            .read(initial_spawn, Some(&abstain.request.body.run_id))?
            .is_null(),
        "abstain created current run",
    )?;
    let second_anchor = anchor(&second)?;
    let second_journal = fs::read(owner.journal_path())?;
    write_private(
        &owner.evidence.join("02-abstain-journal.bin"),
        &second_journal,
    )?;
    check(
        CHECKS[1],
        json!({"submission":submitted_abstain,"history":second,"run_status":null}),
    );

    let covered = query(
        &owner,
        history,
        initial_spawn,
        &compiled.request,
        Some(&second_anchor),
        "03-covered-by-second",
        203,
    )?;
    publication(&covered, &compiled, initial_spawn, 1, initial_generation)?;
    require(
        covered["publication"] == first["publication"],
        "anchor changed original publication",
    )?;
    check(CHECKS[2], json!({"history":covered}));

    let lost = signed_fixture(
        &key,
        initial_spawn,
        3,
        "run.history-lost-response",
        ActionSet::Read,
    )?;
    let loss = lose_submission_response(&owner, &lost.request, initial_spawn)?;
    let deadline = Instant::now() + Duration::from_secs(20);
    let mut projection_reads = 0_u64;
    loop {
        projection_reads += 1;
        let run = owner.read(initial_spawn, Some(&lost.request.body.run_id))?;
        if run["phase"] == "admitted" && run["terminal_observed"] == false {
            break;
        }
        require(
            run.is_null() && Instant::now() < deadline && projection_reads < 40,
            "lost-response request did not reach original admitted state",
        )?;
        thread::sleep(Duration::from_millis(25));
    }
    // Wait for the prior submit to finish before measuring a read-only query's
    // journal stability. A concurrently finishing submit is not a query write.
    let recovered = query(
        &owner,
        history,
        initial_spawn,
        &lost.request,
        None,
        "04-lost-response",
        204,
    )?;
    publication(&recovered, &lost, initial_spawn, 3, initial_generation)?;
    require(
        recovered["publication"]["outcome"]["type"] == "compiled",
        "lost-response disposition drift",
    )?;
    let third_journal = fs::read(owner.journal_path())?;
    write_private(
        &owner.evidence.join("03-lost-response-journal.bin"),
        &third_journal,
    )?;
    check(
        CHECKS[3],
        json!({"loss":loss,"history":recovered,"history_query_attempts":1,
        "read_only_run_projection_waits":projection_reads,
        "resubmission_count":0,"journal_sha256":Digest32::of_bytes(&third_journal).to_string()}),
    );

    let active_runs = [
        owner.read(initial_spawn, Some(&compiled.request.body.run_id))?,
        owner.read(initial_spawn, Some(&lost.request.body.run_id))?,
    ];
    require(
        active_runs
            .iter()
            .all(|run| run["phase"] == "admitted" && run["terminal_observed"] == false),
        "capacity qualification requires two existing active compiled runs",
    )?;
    // The unchanged original ResourceBudget::local_default supplies two slots.
    // The CLI deliberately exposes only the generic owner rejection code; the
    // capacity cause is a source-backed inference, not observed error bytes.
    let capacity = signed_fixture(
        &key,
        initial_spawn,
        4,
        "run.history-postpublication-capacity",
        ActionSet::Read,
    )?;
    let capacity_submission = owner.submit(
        &capacity.request,
        initial_spawn,
        104,
        "05-postpublication-capacity",
    )?;
    require(
        capacity_submission["status"] == "submit_unknown"
            && capacity_submission["issue"] == "objective_owner_request_rejected"
            && capacity_submission["bytes_written"]
                .as_u64()
                .is_some_and(|value| value > 0)
            && capacity_submission["bytes_written"] == capacity_submission["request_frame_bytes"]
            && owner
                .read(initial_spawn, Some(&capacity.request.body.run_id))?
                .is_null(),
        "third active compiled request must return generic rejection and no current run",
    )?;
    let postpublication = query(
        &owner,
        history,
        initial_spawn,
        &capacity.request,
        None,
        "05-postpublication-capacity",
        205,
    )?;
    publication(
        &postpublication,
        &capacity,
        initial_spawn,
        4,
        initial_generation,
    )?;
    require(
        postpublication["publication"]["outcome"]["type"] == "compiled",
        "postpublication rejection has no original compiled publication",
    )?;
    let retained_anchor = anchor(&postpublication)?;
    let full_journal = fs::read(owner.journal_path())?;
    let full_hash = Digest32::of_bytes(&full_journal).to_string();
    write_private(&owner.evidence.join("04-full-journal.bin"), &full_journal)?;
    write_private(
        &owner.evidence.join("retained-anchor.json"),
        &serde_json::to_vec(&retained_anchor)?,
    )?;
    check(
        CHECKS[4],
        json!({"submission":capacity_submission,"history":postpublication,
        "active_run_ids":[compiled.request.body.run_id,lost.request.body.run_id],
        "active_runs_before_submission":active_runs,"run_status":null,
        "source_inference":"original_default_run_capacity_exhausted",
        "specific_original_error_bytes_observed":false,"resubmission_count":0}),
    );

    let mut wrong_anchor = retained_anchor.clone();
    wrong_anchor.chain_digest.replace_range(
        ..1,
        if retained_anchor.chain_digest.starts_with('1') {
            "2"
        } else {
            "1"
        },
    );
    let wrong = query(
        &owner,
        history,
        initial_spawn,
        &compiled.request,
        Some(&wrong_anchor),
        "06-wrong-anchor",
        301,
    )?;
    unknown(&wrong, "anchor_mismatch")?;
    check(CHECKS[5], json!({"history":wrong}));
    let earlier = query(
        &owner,
        history,
        initial_spawn,
        &abstain.request,
        Some(&first_anchor),
        "07-earlier-anchor",
        302,
    )?;
    unknown(&earlier, "publication_outside_anchor")?;
    check(CHECKS[6], json!({"history":earlier}));
    let mut changed = compiled.request.clone();
    changed.signature_hex.replace_range(
        ..1,
        if compiled.request.signature_hex.starts_with('1') {
            "2"
        } else {
            "1"
        },
    );
    let mismatched = query(
        &owner,
        history,
        initial_spawn,
        &changed,
        Some(&retained_anchor),
        "08-changed-signature",
        303,
    )?;
    unknown(&mismatched, "no_matching_publication")?;
    check(CHECKS[7], json!({"history":mismatched}));

    owner.supervisor.restart(&owner.agent, Instant::now())?;
    let (restarted_spawn, restarted) = owner.wait_running(Some(initial_spawn))?;
    require(
        restarted["health"]["process_id"] != initial["health"]["process_id"]
            && owner.journal_hash()? == full_hash
            && owner
                .read(restarted_spawn, Some(&compiled.request.body.run_id))?
                .is_null()
            && owner
                .read(restarted_spawn, Some(&lost.request.body.run_id))?
                .is_null()
            && owner
                .read(restarted_spawn, Some(&capacity.request.body.run_id))?
                .is_null(),
        "restart must retain history without resuming old run",
    )?;
    let historical = query(
        &owner,
        history,
        restarted_spawn,
        &lost.request,
        Some(&retained_anchor),
        "09-after-restart",
        304,
    )?;
    publication(
        &historical,
        &lost,
        initial_spawn,
        3,
        generation(&restarted)?,
    )?;
    require(
        historical["publication"] == recovered["publication"],
        "restart changed publication",
    )?;
    check(
        CHECKS[8],
        json!({"old_spawn":initial_spawn,"new_spawn":restarted_spawn,
        "old_pid":initial["health"]["process_id"],"new_pid":restarted["health"]["process_id"],
        "run_status":null,"history":historical,"resubmission_count":0}),
    );

    let expiry_wait_started = Instant::now();
    let observed_after_expiry = loop {
        require(
            expiry_wait_started.elapsed() <= Duration::from_secs(30),
            "real expiry wait exceeded 30-second qualification bound",
        )?;
        let now = wall_clock_ms()?;
        if now > abstain.request.expires_at_ms {
            break now;
        }
        thread::sleep(Duration::from_millis(25));
    };
    let expiry_wait_ms = u64::try_from(expiry_wait_started.elapsed().as_millis())?;
    let expired_history = query(
        &owner,
        history,
        restarted_spawn,
        &abstain.request,
        Some(&retained_anchor),
        "10-expired-history",
        308,
    )?;
    publication(
        &expired_history,
        &abstain,
        initial_spawn,
        2,
        generation(&restarted)?,
    )?;
    require(
        expired_history["publication"] == second["publication"],
        "real expiry changed original publication",
    )?;
    check(
        CHECKS[9],
        json!({"history":expired_history,
        "expires_at_ms":abstain.request.expires_at_ms,"observed_at_ms":observed_after_expiry,
        "wait_elapsed_ms":expiry_wait_ms,"wait_bound_ms":30_000,"resubmission_count":0}),
    );

    let (rollback_spawn, _, rollback_fault) = stopped_fault_restart(
        &mut owner,
        restarted_spawn,
        "11-rollback-prefix",
        &first_journal,
    )?;
    require(
        owner.journal_hash()? == Digest32::of_bytes(&first_journal).to_string(),
        "rollback recovery changed valid prefix",
    )?;
    let rollback = query(
        &owner,
        history,
        rollback_spawn,
        &compiled.request,
        Some(&retained_anchor),
        "11-rollback-anchor",
        305,
    )?;
    unknown(&rollback, "anchor_missing")?;
    check(
        CHECKS[10],
        json!({"fault":rollback_fault,"history":rollback,"resubmission_count":0}),
    );

    require(
        full_journal.len() > third_journal.len() + 1,
        "fourth frame missing from fault input",
    )?;
    let (truncated_spawn, truncated_owner, truncated_fault) = stopped_fault_restart(
        &mut owner,
        rollback_spawn,
        "12-truncated-tail",
        &full_journal[..full_journal.len() - 1],
    )?;
    require(
        owner.journal_hash()? == Digest32::of_bytes(&third_journal).to_string(),
        "original recovery did not retain exactly the three complete frames",
    )?;
    let truncated = query(
        &owner,
        history,
        truncated_spawn,
        &capacity.request,
        Some(&retained_anchor),
        "12-truncated-anchor",
        306,
    )?;
    unknown(&truncated, "anchor_missing")?;
    check(
        CHECKS[11],
        json!({"fault":truncated_fault,"history":truncated,"resubmission_count":0}),
    );

    let revoked = serde_json::to_vec(&trust(&key, true))?;
    write_private(&owner.evidence.join("revoked-public-trust.json"), &revoked)?;
    write_private(&owner.trust_file, &revoked)?;
    let after_revoke = query(
        &owner,
        history,
        truncated_spawn,
        &compiled.request,
        Some(&first_anchor),
        "13-revoked-history",
        307,
    )?;
    publication(
        &after_revoke,
        &compiled,
        initial_spawn,
        1,
        generation(&truncated_owner)?,
    )?;
    require(
        after_revoke["publication"] == first["publication"],
        "revocation erased original publication",
    )?;
    check(
        CHECKS[12],
        json!({"history":after_revoke,"issuer_revoked":true,"issuer_restored":false}),
    );

    let negative = signed_fixture(
        &key,
        truncated_spawn,
        5,
        "run.history-revoked-negative",
        ActionSet::Read,
    )?;
    let before_rejection = owner.journal_hash()?;
    let rejection = owner.submit(
        &negative.request,
        truncated_spawn,
        105,
        "14-revoked-negative",
    )?;
    require(
        rejection["status"] == "submit_unknown"
            && rejection["issue"] == "objective_owner_request_rejected"
            && rejection["bytes_written"] == rejection["request_frame_bytes"]
            && owner.journal_hash()? == before_rejection,
        "revoked new submission did not fail without publication",
    )?;
    check(
        CHECKS[13],
        json!({"submission":rejection,"journal_unchanged":true,
        "purpose":"distinct_revoked_negative_not_recovery_retry"}),
    );
    owner.stop()?;
    require(
        !owner.snapshot()?.active && owner.read(truncated_spawn, None).is_err(),
        "final owner still active",
    )?;
    check(CHECKS[14], json!({"active":false}));
    println!(
        "{}",
        json!({"event":"acceptance_pass","checks":CHECKS,
        "evidence_class":"original_owner_objective_admission_history",
        "source_binding":binding,"isolated_test_issuer":true,
        "objective_request_attempts":5,"published_objective_requests":4,
        "recovery_resubmissions":0,"operations_dispatch":false,"device_effect":false,
        "model_turn":false,"production_issuer":false,"canonical_intelligence":false,
        "historical_run_resumed":false,"operations_k_or_d_created":false,
        "hepta_submit_cli_lost_reply_executed":false,
        "not_executed":["caller_anchor_co_rollback",
            "production_issuer","effect_reconciliation","kernel_g1","kernel_g2"]})
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("objective-history-probe failed: {error}");
        std::process::exit(1);
    }
}
