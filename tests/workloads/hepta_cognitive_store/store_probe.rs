//! No-authority process-crash compatibility probe linked to the original store.
//! No SQL, replacement store, production lease, or owner test hooks live here.
use std::io::{Read, Write};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use codex_hepta_contracts::AgentId;
use codex_hepta_memory::{
    CognitiveAccess, CognitiveRecoveryAnchor, CognitiveScope, CognitiveStore, CognitiveStoreError,
    KgEntityFactDraft, KgFactSetDraft, KgRelationFactDraft, LedgerSourceKind, MemoryDraft,
    MemoryLifecycleState, MemoryRevisionDraft, MemoryVerification, SourceDraft, StableMemoryId,
};
use codex_hepta_paths::{HeptaAgentLayout, HeptaFleetRoot};
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdout, Command};
use tokio::time::timeout;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
const AGENT: &str = "33333333-3333-4333-8333-333333333333";
const LINE_LIMIT: u64 = 64 * 1024;
const STEP_DEADLINE: Duration = Duration::from_secs(90);
const CHECKS: [&str; 10] = [
    "original_source_memory_kg_commit",
    "live_wal_before_sigkill",
    "sigkill_exit_observed",
    "legacy_reopen_exact_anchor_and_memory",
    "source_retry_idempotent_after_sigkill",
    "two_processes_ready_before_cas",
    "one_cas_commit_one_conflict",
    "losing_source_transaction_rolled_back",
    "winning_memory_and_projection_persisted",
    "graceful_close_reopen_exact_anchor",
];

fn require(condition: bool, message: &'static str) -> Result<()> {
    if !condition {
        return Err(message.into());
    }
    Ok(())
}

fn agent() -> Result<AgentId> {
    Ok(AgentId::parse(AGENT)?)
}

fn layout(root: &Path) -> Result<HeptaAgentLayout> {
    Ok(HeptaFleetRoot::parse(root.join("fleet"))?
        .layout()
        .agent(&agent()?))
}

fn access() -> Result<CognitiveAccess> {
    Ok(CognitiveAccess::agent_private(agent()?))
}

fn content(variant: &str) -> String {
    format!("Inert store compatibility fixture revision {variant}.")
}

fn source(variant: &str) -> SourceDraft {
    SourceDraft {
        scope: CognitiveScope::AgentPrivate,
        kind: LedgerSourceKind::ExplicitMemoryDirective,
        event_key: format!("native-store-fixture-{variant}"),
        content: content(variant).into_bytes(),
        observed_at_unix_seconds: 100,
    }
}

fn revision(variant: &str) -> MemoryRevisionDraft {
    MemoryRevisionDraft {
        scope: CognitiveScope::AgentPrivate,
        content: content(variant),
        verification: MemoryVerification::Verified,
        lifecycle: MemoryLifecycleState::Active,
        valid_from_unix_seconds: 100,
        valid_to_unix_seconds: None,
        citations: Vec::new(),
    }
}

fn facts(variant: &str) -> KgFactSetDraft {
    KgFactSetDraft {
        entities: vec![
            KgEntityFactDraft {
                key: "fixture".into(),
                entity_type: "test_fixture".into(),
                label: "Store fixture".into(),
            },
            KgEntityFactDraft {
                key: "revision".into(),
                entity_type: "test_revision".into(),
                label: variant.into(),
            },
        ],
        relations: vec![KgRelationFactDraft {
            key: "contains".into(),
            from_entity_key: "fixture".into(),
            to_entity_key: "revision".into(),
            relation: "contains".into(),
        }],
    }
}

fn emit(value: Value) -> Result<()> {
    let mut out = std::io::stdout().lock();
    serde_json::to_writer(&mut out, &value)?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(())
}

fn release_barrier() -> Result<()> {
    let mut byte = [0];
    std::io::stdin().read_exact(&mut byte)?;
    require(byte == [b'!'], "invalid child release barrier")
}

async fn seed(root: &Path) -> Result<()> {
    let store = CognitiveStore::open(&layout(root)?).await?;
    let receipt = store
        .remember_with_kg(
            &access()?,
            &source("seed"),
            &MemoryDraft {
                stable_key: "native-store-fixture".into(),
                revision: revision("seed"),
            },
            &facts("seed"),
        )
        .await?;
    let anchor = store.recovery_anchor().await?;
    let wal_bytes = std::fs::metadata(store.path().with_extension("sqlite3-wal"))?.len();
    require(wal_bytes > 0, "original store has no live WAL")?;
    require(
        receipt.projection.entity_count == 2 && receipt.projection.relation_count == 1,
        "original atomic KG write missing",
    )?;
    emit(json!({"event":"seed_ready", "receipt":receipt, "anchor":anchor, "wal_bytes":wal_bytes}))?;
    // Keep the pool, fence, and live WAL open until our actual parent kills us.
    // A normal release is an error; this path must never fake a crash receipt.
    release_barrier()?;
    store.close().await;
    Err("seed child was released instead of SIGKILL".into())
}

async fn contender(root: &Path, memory: &str, variant: &str) -> Result<()> {
    require(matches!(variant, "a" | "b"), "unknown contender")?;
    let store = CognitiveStore::open(&layout(root)?).await?;
    let id = StableMemoryId::parse(memory)?;
    emit(json!({"event":"cas_ready", "variant":variant}))?;
    release_barrier()?;
    let result = store
        .correct_with_kg(
            &access()?,
            &id,
            1,
            &source(variant),
            &revision(variant),
            &facts(variant),
        )
        .await;
    let record = match result {
        Ok(receipt) => {
            require(
                receipt.memory.id.revision == 2 && receipt.memory.supersedes_revision == Some(1),
                "CAS winner did not append exact next revision",
            )?;
            json!({"event":"cas_result", "variant":variant, "outcome":"committed", "receipt":receipt})
        }
        Err(CognitiveStoreError::Conflict(_)) => {
            json!({"event":"cas_result", "variant":variant, "outcome":"conflict"})
        }
        Err(error) => return Err(error.into()),
    };
    // Returning before SQLx workers close is not a shutdown barrier.
    store.close().await;
    emit(record)
}

struct Worker {
    child: Child,
    output: BufReader<ChildStdout>,
}

impl Worker {
    fn start(root: &Path, mode: &str, arguments: &[&str]) -> Result<Self> {
        let mut child = Command::new(std::env::current_exe()?)
            .arg(mode)
            .arg(root)
            .args(arguments)
            .env_clear()
            .env("PATH", "/bin:/sbin")
            .env("HOME", root)
            .env("TMPDIR", root)
            .env("LANG", "C")
            .env("LC_ALL", "C")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true)
            .spawn()?;
        let output = BufReader::new(child.stdout.take().ok_or("missing child stdout")?);
        Ok(Self { child, output })
    }

    async fn record(&mut self) -> Result<Value> {
        let mut line = Vec::new();
        timeout(
            STEP_DEADLINE,
            (&mut self.output)
                .take(LINE_LIMIT)
                .read_until(b'\n', &mut line),
        )
        .await??;
        require(
            !line.is_empty() && line.last() == Some(&b'\n'),
            "incomplete or excessive child record",
        )?;
        Ok(serde_json::from_slice(&line)?)
    }

    async fn release(&mut self) -> Result<()> {
        let input = self.child.stdin.as_mut().ok_or("missing child stdin")?;
        timeout(STEP_DEADLINE, input.write_all(b"!")).await??;
        Ok(())
    }

    async fn finish(&mut self) -> Result<()> {
        require(
            timeout(STEP_DEADLINE, self.child.wait()).await??.success(),
            "store child failed",
        )?;
        let mut extra = Vec::new();
        timeout(
            STEP_DEADLINE,
            (&mut self.output).take(LINE_LIMIT).read_to_end(&mut extra),
        )
        .await??;
        require(extra.is_empty(), "unexpected extra child stdout")
    }
}

async fn probe(root: &Path) -> Result<()> {
    require(root.is_absolute(), "absolute new state root required")?;
    std::fs::DirBuilder::new().mode(0o700).create(root)?;
    std::fs::DirBuilder::new()
        .mode(0o700)
        .create(root.join("fleet"))?;
    let mut seed = Worker::start(root, "seed", &[])?;
    let first = seed.record().await?;
    require(
        first["event"] == "seed_ready" && first["wal_bytes"].as_u64().is_some_and(|v| v > 0),
        "missing original seed/WAL receipt",
    )?;
    let anchor: CognitiveRecoveryAnchor = serde_json::from_value(first["anchor"].clone())?;
    let memory = first["receipt"]["memory"]["id"]["memory_id"]
        .as_str()
        .ok_or("seed memory ID missing")?;
    let id = StableMemoryId::parse(memory)?;
    seed.child.start_kill()?;
    let killed = timeout(STEP_DEADLINE, seed.child.wait()).await??;
    require(
        killed.signal() == Some(9),
        "seed did not actually die by SIGKILL",
    )?;
    drop(seed);

    let store = CognitiveStore::open(&layout(root)?).await?;
    require(
        store.recovery_anchor().await? == anchor,
        "legacy crash reopen changed logical cut",
    )?;
    let actual = store.latest_memory(&access()?, &id).await?;
    require(
        serde_json::to_value(actual)? == first["receipt"]["memory"],
        "seed memory changed after kill",
    )?;
    let retried = store.append_source(&access()?, &source("seed")).await?;
    require(
        serde_json::to_value(retried)? == first["receipt"]["source"],
        "source replay changed identity",
    )?;
    require(
        store.recovery_anchor().await? == anchor,
        "idempotent source replay mutated logical cut",
    )?;
    store.close().await;

    let mut a = Worker::start(root, "cas", &[memory, "a"])?;
    let mut b = Worker::start(root, "cas", &[memory, "b"])?;
    require(
        a.record().await? == json!({"event":"cas_ready", "variant":"a"})
            && b.record().await? == json!({"event":"cas_ready", "variant":"b"}),
        "CAS readiness barrier missing",
    )?;
    // Both independent original pools are open before either CAS can start.
    a.release().await?;
    b.release().await?;
    let left = a.record().await?;
    let right = b.record().await?;
    a.finish().await?;
    b.finish().await?;
    require(
        left["event"] == "cas_result"
            && left["variant"] == "a"
            && right["event"] == "cas_result"
            && right["variant"] == "b",
        "CAS result identity mismatch",
    )?;
    let (winner, loser) = match (left["outcome"].as_str(), right["outcome"].as_str()) {
        (Some("committed"), Some("conflict")) => (&left, "b"),
        (Some("conflict"), Some("committed")) => (&right, "a"),
        _ => {
            return Err(
                "expected exactly one original CAS commit and one original conflict".into(),
            );
        }
    };
    let store = CognitiveStore::open(&layout(root)?).await?;
    let actual = store.latest_memory(&access()?, &id).await?;
    require(
        serde_json::to_value(actual)? == winner["receipt"]["memory"],
        "winning memory differs after process exit",
    )?;
    require(
        winner["receipt"]["projection"]["entity_count"] == 2
            && winner["receipt"]["projection"]["relation_count"] == 1,
        "winning KG receipt missing",
    )?;
    let mut losing_source = source(loser);
    losing_source.content = b"inert rollback verification; distinct from rejected source".to_vec();
    // This only succeeds if the failed CAS rolled back its source INSERT too.
    store.append_source(&access()?, &losing_source).await?;
    let final_anchor = store.recovery_anchor().await?;
    require(
        final_anchor != anchor,
        "CAS did not advance original logical cut",
    )?;
    store.close().await;
    let reopened = CognitiveStore::open(&layout(root)?).await?;
    require(
        reopened.recovery_anchor().await? == final_anchor,
        "graceful reopen changed logical cut",
    )?;
    let actual = reopened.latest_memory(&access()?, &id).await?;
    require(
        serde_json::to_value(actual)? == winner["receipt"]["memory"],
        "final winner changed",
    )?;
    reopened.close().await;
    emit(json!({
        "event":"acceptance_pass", "schema":"hepta.original-cognitive-store-process-crash.v1",
        "evidence_class":"legacy_original_store_wal_process_crash_reopen", "checks":CHECKS,
        "agent_id":AGENT, "wal_bytes_before_kill":first["wal_bytes"], "killed_signal":9,
        "seed_receipt":first["receipt"], "seed_anchor":anchor, "cas_results":[left,right],
        "final_anchor":final_anchor, "production_authority":false, "production_writer_lock":false,
        "authenticated_recovery":false, "power_loss_durability":false, "f1_completed":false,
        "model_turn":false, "device_effect":false,
    }))
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() {
    let args: Vec<_> = std::env::args().collect();
    let result = match args.get(1).map(String::as_str) {
        Some("probe") if args.len() == 3 => probe(&PathBuf::from(&args[2])).await,
        Some("seed") if args.len() == 3 => seed(&PathBuf::from(&args[2])).await,
        Some("cas") if args.len() == 5 => {
            contender(&PathBuf::from(&args[2]), &args[3], &args[4]).await
        }
        _ => Err("usage: store-probe probe <absolute-new-root>".into()),
    };
    if let Err(error) = result {
        eprintln!("original cognitive store probe failed: {error}");
        std::process::exit(1);
    }
}
