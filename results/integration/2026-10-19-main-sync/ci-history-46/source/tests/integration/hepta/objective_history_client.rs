//! Qualification-only CLI invocations and deliberate response loss.

use codex_hepta_agent_protocol::{AgentdRequest, AuthBusObjectiveIngress, ObjectiveJournalAnchor};
use serde_json::{Value, json};
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::Duration;
use tokio::io::AsyncWriteExt;

use crate::original_objective_fixture::{Fixture, claims};
use crate::original_objective_owner::{Owner, write_private};
use crate::{AGENT, Result, require};

pub fn query(
    owner: &Owner,
    binary: &Path,
    spawn: u64,
    request: &AuthBusObjectiveIngress,
    anchor: Option<&ObjectiveJournalAnchor>,
    label: &str,
    request_id: u64,
) -> Result<Value> {
    let pid = owner
        .snapshot()?
        .process_system_id
        .ok_or("owner PID missing")?;
    let before = owner.journal_hash()?;
    let input = serde_json::to_vec(request)?;
    write_private(
        &owner.evidence.join(format!("{label}-query-input.json")),
        &input,
    )?;
    let mut command = Command::new(binary);
    command
        .arg(&owner.socket)
        .arg(AGENT)
        .arg(spawn.to_string())
        .arg(owner.uid.to_string())
        .arg(pid.to_string())
        .arg(request_id.to_string());
    if let Some(anchor) = anchor {
        command
            .arg(anchor.sequence.to_string())
            .arg(&anchor.chain_digest);
    }
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    child
        .stdin
        .take()
        .ok_or("history stdin missing")?
        .write_all(&input)?;
    let output = child.wait_with_output()?;
    require(
        output.stdout.len() <= 16_384 && output.stderr.len() <= 1_024,
        "history output bound exceeded",
    )?;
    write_private(
        &owner.evidence.join(format!("{label}-query-output.json")),
        &output.stdout,
    )?;
    write_private(
        &owner.evidence.join(format!("{label}-query-stderr.log")),
        &output.stderr,
    )?;
    let result: Value = serde_json::from_slice(&output.stdout)?;
    let identity = json!({
        "request_id":request_id,"agent_id":AGENT,"spawn_generation":spawn,
        "peer_uid":owner.uid,"peer_pid":pid,
        "original_spawn_generation":request.body.spawn_generation,
        "issuer_id":request.issuer_id,"key_epoch":request.key_epoch,
        "message_id":request.message_id,"message_sequence":request.sequence,
        "expires_at_ms":request.expires_at_ms,"run_id":request.body.run_id,
    });
    require(
        result["schema_version"] == 1
            && result["identity"] == identity
            && result["anchor"] == serde_json::to_value(anchor)?,
        "history identity/anchor drift",
    )?;
    let code = match result["status"].as_str() {
        Some("historical_publication") => 0,
        Some("query_not_sent") => 10,
        Some("unknown") => 12,
        _ => return Err("unknown history CLI status".into()),
    };
    require(
        output.status.code() == Some(code),
        "history CLI status/exit mismatch",
    )?;
    require(
        owner.journal_hash()? == before,
        "history read changed original journal",
    )?;
    println!(
        "{}",
        json!({"event":"history_query_observed","label":label,
        "exit_code":code,"result":result,"journal_sha256":before,"journal_unchanged":true})
    );
    Ok(result)
}

pub fn publication(
    result: &Value,
    fixture: &Fixture,
    original_spawn: u64,
    publication_sequence: u64,
    current_generation: u64,
) -> Result<()> {
    let expected_claims = claims(&fixture.request)?;
    let record = &result["publication"];
    require(
        result["status"] == "historical_publication"
            && result["bytes_written"]
                .as_u64()
                .is_some_and(|bytes| bytes > 0)
            && result["bytes_written"] == result["request_frame_bytes"]
            && result["response_generation"] == current_generation,
        "original history publication transport invalid",
    )?;
    require(
        record["run_id"] == fixture.request.body.run_id
            && record["original_spawn_generation"] == original_spawn
            && record["issuer_id"] == fixture.request.issuer_id
            && record["key_epoch"] == fixture.request.key_epoch
            && record["message_id"] == fixture.request.message_id
            && record["message_sequence"] == fixture.request.sequence
            && record["expires_at_ms"] == fixture.request.expires_at_ms
            && record["signed_body_digest"] == expected_claims.payload_digest.to_string()
            && record["profile_digest"] == fixture.admission.profile_digest.to_string()
            && record["publication_sequence"] == publication_sequence
            && record["outcome"]["objective_digest"] == fixture.objective_digest.to_string()
            && record["outcome"]["hard_constraint_digest"]
                == fixture.hard_constraint_digest.to_string(),
        "history publication differs from retained signed original",
    )?;
    let coverage = if result["anchor"].is_null() {
        "current_owner_journal"
    } else {
        "retained_anchor"
    };
    require(
        result["anchor_coverage"] == coverage,
        "history coverage drift",
    )
}

pub fn anchor(result: &Value) -> Result<ObjectiveJournalAnchor> {
    Ok(ObjectiveJournalAnchor {
        sequence: result["publication"]["publication_sequence"]
            .as_u64()
            .ok_or("sequence missing")?,
        chain_digest: result["publication"]["chain_digest"]
            .as_str()
            .ok_or("chain missing")?
            .into(),
    })
}

pub fn unknown(result: &Value, reason: &str) -> Result<()> {
    require(
        result["status"] == "unknown"
            && result["issue"] == reason
            && result["bytes_written"]
                .as_u64()
                .is_some_and(|bytes| bytes > 0)
            && result["bytes_written"] == result["request_frame_bytes"]
            && result.get("publication").is_none(),
        "history must remain sent unknown",
    )
}

pub fn lose_submission_response(
    owner: &Owner,
    request: &AuthBusObjectiveIngress,
    spawn: u64,
) -> Result<Value> {
    let pid = owner
        .snapshot()?
        .process_system_id
        .ok_or("owner PID missing")?;
    let input = serde_json::to_vec(request)?;
    write_private(
        &owner.evidence.join("03-lost-response-request.json"),
        &input,
    )?;
    let mut frame =
        serde_json::to_vec(&AgentdRequest::objective_start(103, spawn, request.clone()))?;
    frame.push(b'\n');
    require(
        frame.len() <= 65_536,
        "lost response frame exceeds original bound",
    )?;
    write_private(&owner.evidence.join("03-lost-response-frame.jsonl"), &frame)?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    runtime.block_on(async {
        tokio::time::timeout(Duration::from_secs(5), async {
            let mut stream = tokio::net::UnixStream::connect(&owner.socket).await?;
            let peer = stream.peer_cred()?;
            require(
                peer.uid() == owner.uid
                    && peer.pid().and_then(|value| u64::try_from(value).ok()) == Some(pid),
                "lost response sender connected to wrong owner peer",
            )?;
            stream.write_all(&frame).await?;
            stream.shutdown().await?;
            // Intentionally drop the connection without a read. The sender cannot
            // conclude admission; a separate original-owner history query must do so.
            drop(stream);
            Ok::<_, Box<dyn std::error::Error>>(())
        })
        .await
    })??;
    let evidence = json!({"sender":"qualification_harness_original_protocol",
        "run_id":request.body.run_id,"message_id":request.message_id,
        "spawn_generation":spawn,"peer_uid":owner.uid,"peer_pid":pid,
        "bytes_written":frame.len(),"request_frame_bytes":frame.len(),
        "response_bytes_read":0,"response_discarded_by_harness":true,
        "hepta_submit_cli_loss_case":false,"submission_outcome":"unknown"});
    println!(
        "{}",
        json!({"event":"objective_response_discarded","evidence":evidence})
    );
    Ok(evidence)
}
