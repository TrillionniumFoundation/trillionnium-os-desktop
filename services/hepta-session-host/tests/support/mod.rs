//! Test-only original-owner host. These fixtures do not authenticate a signature
//! or provide a production authority/current-cut publication service.

use codex_hepta_contracts::{AgentId, Sha256Digest};
use codex_hepta_memory::{
    CognitiveRecoveryAnchor, CognitiveStore, ObjectiveSenderCheckpoint,
    ObjectiveSenderCheckpointError, ObjectiveSenderOrigin, ObjectiveSenderRequest,
    ObjectiveSenderRetainedPosition, ObjectiveSenderSnapshot, ObjectiveSenderWriterFence,
    ProductionAuthorityLease, ProductionAuthorityToken, ProductionAuthorityVerifier,
    ProductionDurableWriter, ProductionObjectiveSender,
};
use codex_hepta_paths::HeptaFleetRoot;
use hepta_os_observer::objective::history::{HistoricalPublication, PublicationOutcome};
use hepta_session_host::{HeptaSessionSubmission, HostError};
use serde_json::{Value, json};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU8, AtomicUsize, Ordering};
use std::thread;
use std::time::{Duration, Instant};
use tempfile::TempDir;
use tokio::runtime::{Builder, Runtime};

pub const ACCEPT: u8 = 0;
pub const REFUSE: u8 = 1;
pub const HOLD: u8 = 2;

pub struct TestOnlyVerifier {
    pub revoked: AtomicBool,
}

impl ProductionAuthorityVerifier for TestOnlyVerifier {
    fn verify(
        &self,
        authority: &ProductionAuthorityLease,
        expected: &AgentId,
    ) -> Result<(), String> {
        if self.revoked.load(Ordering::SeqCst) || authority.agent_id != *expected {
            Err("test-only original owner authority refused".to_owned())
        } else {
            Ok(())
        }
    }
}

pub struct TestOnlyCheckpoint {
    pub mode: AtomicU8,
    pub calls: AtomicUsize,
}

impl ObjectiveSenderCheckpoint for TestOnlyCheckpoint {
    async fn acknowledge_current(
        &self,
        current: &CognitiveRecoveryAnchor,
        writer: &ObjectiveSenderWriterFence,
    ) -> Result<CognitiveRecoveryAnchor, ObjectiveSenderCheckpointError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        assert_eq!(writer.generation, 1);
        assert_eq!(writer.authority_epoch, 71);
        match self.mode.load(Ordering::SeqCst) {
            ACCEPT => Ok(current.clone()),
            REFUSE => Err(ObjectiveSenderCheckpointError::Refused),
            HOLD => std::future::pending().await,
            _ => panic!("unknown test-only checkpoint mode"),
        }
    }
}

pub type Submission = HeptaSessionSubmission<TestOnlyCheckpoint>;

pub struct Fixture {
    pub runtime: Runtime,
    pub writer: Arc<ProductionDurableWriter>,
    pub checkpoint: Arc<TestOnlyCheckpoint>,
    pub verifier: Arc<TestOnlyVerifier>,
    pub origin: ObjectiveSenderOrigin,
    pub original: String,
    pub listener: UnixListener,
    _root: TempDir,
}

impl Fixture {
    pub fn new() -> Self {
        let runtime = Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .unwrap();
        let root = TempDir::new().unwrap();
        fs::set_permissions(root.path(), fs::Permissions::from_mode(0o700)).unwrap();
        let owner = AgentId::parse("00000000-0000-4000-8000-000000000231").unwrap();
        let fleet = root.path().join("fleet");
        fs::create_dir(&fleet).unwrap();
        let layout = HeptaFleetRoot::parse(fleet).unwrap().layout().agent(&owner);
        let verifier = Arc::new(TestOnlyVerifier {
            revoked: AtomicBool::new(false),
        });
        let writer = runtime.block_on(async {
            // Explicit test genesis only. This is not a production recovery fallback.
            let store = CognitiveStore::open(&layout).await.unwrap();
            let authority = ProductionAuthorityLease::from_verified_parts(
                owner.clone(),
                Sha256Digest::for_bytes(b"host-test-only-grant"),
                71,
                87,
                4_000_000_000,
                ProductionAuthorityToken::from_verified_bytes(
                    b"host-test-only-opaque-token".to_vec(),
                )
                .unwrap(),
            )
            .unwrap();
            Arc::new(
                ProductionDurableWriter::open_with_live_verifier(
                    store,
                    authority,
                    verifier.clone(),
                    "host-test-only-owner",
                    1,
                )
                .await
                .unwrap(),
            )
        });
        let checkpoint = Arc::new(TestOnlyCheckpoint {
            mode: AtomicU8::new(ACCEPT),
            calls: AtomicUsize::new(0),
        });
        let path = root.path().join("control.sock");
        let listener = UnixListener::bind(&path).unwrap();
        listener.set_nonblocking(true).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        let origin = ObjectiveSenderOrigin {
            agent_id: owner,
            spawn_generation: 1,
            request_id: 19,
            expected_peer_uid: fs::metadata(root.path()).unwrap().uid(),
            expected_peer_pid: std::process::id(),
            endpoint_identity: path.to_str().unwrap().to_owned(),
            original_notes_thread: None,
        };
        let original = serde_json::to_string(&json!({
            "issuer_id": "test-only-original-issuer", "key_epoch": 3,
            "message_id": "test-only-original-message", "sequence": 7,
            "expires_at_ms": 4_000_000_000_000_u64, "signature_hex": "ab".repeat(64),
            "body": {
                "spawn_generation": 1, "run_id": "test-only-original-run", "objective_revision": 5,
                "source_envelope_json": "{\"original\":\"你好\"}",
                "runtime_body_digest": "11".repeat(32), "preference_state_digest": "22".repeat(32),
                "model_tuple_digest": "33".repeat(32), "prompt_registry_digest": "44".repeat(32),
                "artifact_set_digest": "55".repeat(32), "authority_epoch": 71,
            },
        }))
        .unwrap();
        Self {
            runtime,
            writer,
            checkpoint,
            verifier,
            origin,
            original,
            listener,
            _root: root,
        }
    }

    pub fn sender(&self) -> ProductionObjectiveSender<TestOnlyCheckpoint> {
        self.writer
            .objective_sender(self.checkpoint.clone(), Duration::from_millis(250))
            .unwrap()
    }

    pub fn prepare(&self) -> Result<Submission, HostError> {
        HeptaSessionSubmission::prepare(
            self.sender(),
            self.runtime.handle().clone(),
            self.origin.clone(),
            self.original.clone(),
            Duration::from_secs(2),
        )
    }

    pub fn retained(&self) -> Vec<ObjectiveSenderRequest> {
        self.runtime
            .block_on(
                self.sender()
                    .retained_page(ObjectiveSenderRetainedPosition::Beginning),
            )
            .unwrap()
            .requests
    }

    pub fn snapshot(&self, request: ObjectiveSenderRequest) -> ObjectiveSenderSnapshot {
        let sender = self.sender();
        self.runtime.block_on(async {
            let ticket = sender.recover_pending(request).await.unwrap();
            sender.snapshot(&ticket).await.unwrap()
        })
    }

    pub fn recover(&self, request: ObjectiveSenderRequest) -> Submission {
        HeptaSessionSubmission::recover_unknown(
            self.sender(),
            self.runtime.handle().clone(),
            request,
            Duration::from_secs(2),
        )
        .unwrap()
    }

    pub fn assert_no_connection(&self) {
        assert!(
            matches!(self.listener.accept(), Err(error)
            if error.kind() == std::io::ErrorKind::WouldBlock),
            "unexpected repeated socket connection"
        );
    }

    pub fn serve(&self, reply: Option<Value>) -> thread::JoinHandle<Vec<u8>> {
        self.serve_with(reply, || {})
    }

    pub fn serve_with(
        &self,
        reply: Option<Value>,
        before_reply: impl FnOnce() + Send + 'static,
    ) -> thread::JoinHandle<Vec<u8>> {
        let listener = self.listener.try_clone().unwrap();
        let sender = self.sender();
        let runtime = self.runtime.handle().clone();
        let original = self.original.clone();
        thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(5);
            let (mut stream, _) = loop {
                match listener.accept() {
                    Ok(stream) => break stream,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(
                            Instant::now() < deadline,
                            "expected bounded test connection"
                        );
                        thread::sleep(Duration::from_millis(1));
                    }
                    Err(error) => panic!("test listener: {error}"),
                }
            };
            let page = runtime
                .block_on(sender.retained_page(ObjectiveSenderRetainedPosition::Beginning))
                .unwrap();
            assert_eq!(
                page.requests.len(),
                1,
                "original durable retain must precede connect"
            );
            assert_eq!(page.requests[0].exact_original(), original.as_bytes());
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut reader = BufReader::new(stream.try_clone().unwrap().take(65_537));
            let mut frame = Vec::new();
            reader.read_until(b'\n', &mut frame).unwrap();
            assert!(frame.ends_with(b"\n") && frame.len() <= 65_536);
            let parsed: Value = serde_json::from_slice(&frame).unwrap();
            assert!(
                parsed["method"]["request"].is_object()
                    || parsed["method"]["query"]["request"].is_object()
            );
            assert!(
                String::from_utf8(frame.clone())
                    .unwrap()
                    .contains(&original),
                "exact original bytes must survive wire composition"
            );
            before_reply();
            if let Some(reply) = reply {
                let mut bytes = serde_json::to_vec(&reply).unwrap();
                bytes.push(b'\n');
                stream.write_all(&bytes).unwrap();
            }
            frame
        })
    }

    pub fn admitted(&self) -> Value {
        json!({"schema_version":2,"request_id":self.origin.request_id,
            "agent_id":self.origin.agent_id.as_str(),"spawn_generation":1,"current_generation":2,
            "payload":{"type":"objective_run","run_id":"test-only-original-run",
                "objective_digest":"1".repeat(64),"hard_constraint_digest":"2".repeat(64),
                "publication_digest":"3".repeat(64),"chain_digest":"4".repeat(64),
                "disposition":"compiled","idempotent":false}})
    }

    pub fn history_origin(&self) -> ObjectiveSenderOrigin {
        let mut current = self.origin.clone();
        current.spawn_generation = 2;
        current.request_id = 20;
        current
    }

    pub fn publication(&self) -> HistoricalPublication {
        let request =
            ObjectiveSenderRequest::from_original(self.original.clone(), self.origin.clone())
                .unwrap();
        let identity = request.identity();
        HistoricalPublication {
            run_id: identity.run_id.clone(),
            original_spawn_generation: identity.body_spawn_generation,
            issuer_id: identity.issuer_id.clone(),
            key_epoch: identity.key_epoch,
            message_id: identity.message_id.clone(),
            message_sequence: identity.sequence,
            expires_at_ms: identity.expires_at_ms,
            signed_body_digest: identity.signed_body_sha256.as_str().to_owned(),
            profile_digest: "6".repeat(64),
            publication_sequence: 1,
            publication_digest: "3".repeat(64),
            chain_digest: "4".repeat(64),
            outcome: PublicationOutcome::Compiled {
                objective_digest: "1".repeat(64),
                hard_constraint_digest: "2".repeat(64),
            },
        }
    }

    pub fn history_reply(
        &self,
        publication: Option<HistoricalPublication>,
        response_generation: u64,
    ) -> Value {
        let outcome = match publication {
            Some(publication) => json!({"type":"published","publication":publication}),
            None => json!({"type":"unknown","reason":"no_matching_publication"}),
        };
        json!({"schema_version":2,"request_id":20,"agent_id":self.origin.agent_id.as_str(),
            "spawn_generation":2,"current_generation":response_generation,
            "payload":{"type":"objective_admission","outcome":outcome}})
    }
}
