//! Explicit original ObjectiveStart/ObjectiveAdmission host client. Public UI
//! requests select only trusted startup entries; no raw envelope, endpoint,
//! issuer, arbitrary path, signature or effect request comes from the renderer.
use super::objective_store::{read_private, Retention};
use hepta_os_observer::objective::history::{HistoryStatus, ObjectiveHistoryClient};
use hepta_os_observer::{
    objective::{ObjectiveTransport, PrePublicationRefusal, ProvidedObjective, SubmissionStatus},
    EndpointConfig,
};
use serde::Deserialize;
use std::collections::BTreeSet;
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::FromRawFd;
use std::os::unix::fs::MetadataExt;
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, SyncSender};
use trill_ui_core::notes::sha256_hex;
use trill_ui_core::objective::*;
use trill_ui_core::Response;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Owner {
    socket_path: PathBuf,
    agent_id: String,
    spawn_generation: u64,
    peer_uid: u32,
    peer_pid: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Selection {
    id: String,
    envelope_path: PathBuf,
    submit_request_id: u64,
    history_request_id: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Config {
    schema_version: u16,
    owner: Owner,
    retention_dir: PathBuf,
    entries: Vec<Selection>,
}
struct Entry {
    raw: String,
    attempt_identity: String,
    submit_request_id: u64,
    history_request_id: u64,
    detail: ObjectiveDetail,
}
struct Engine {
    endpoint: EndpointConfig,
    peer_pid: u32,
    owner: String,
    entries: Vec<Entry>,
    retention: Retention,
}
enum Command {
    Submit(String),
    Query(String),
}
#[derive(Default)]
pub struct ObjectiveMonitor {
    commands: Option<SyncSender<Command>>,
    replies: Option<Receiver<ObjectiveSummary>>,
    owner: Option<(String, u64)>,
    entries: Vec<ObjectiveDetail>,
}
impl ObjectiveMonitor {
    pub fn from_inherited_fd(fd: i32) -> io::Result<Self> {
        if fd < 3 {
            return Err(io::Error::other(
                "objective config needs an explicit inherited descriptor",
            ));
        }
        if unsafe { libc::fcntl(fd, libc::F_GETFD) } < 0 {
            return Err(io::Error::last_os_error());
        }
        let file = unsafe { File::from_raw_fd(fd) };
        if unsafe { libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
            return Err(io::Error::last_os_error());
        }
        let m = file.metadata()?;
        if !m.is_file()
            || m.len() > 16 * 1024
            || m.uid() != trill_ui_core::host_peer::current_effective_uid()
            || m.mode() & 0o777 != 0o600
        {
            return Err(io::Error::other("invalid private objective config"));
        }
        let mut bytes = Vec::new();
        file.take(16 * 1024 + 1).read_to_end(&mut bytes)?;
        let config: Config = serde_json::from_slice(&bytes)
            .map_err(|_| io::Error::other("invalid objective config schema"))?;
        Self::from_config(config)
    }
    fn from_config(config: Config) -> io::Result<Self> {
        if config.schema_version != 1
            || config.entries.is_empty()
            || config.entries.len() > MAX_ENTRIES
            || config.owner.peer_pid == 0
            || config.owner.peer_pid > i32::MAX as u32
        {
            return Err(io::Error::other("invalid objective startup bounds"));
        }
        let endpoint = EndpointConfig::new(
            config.owner.socket_path,
            config.owner.agent_id.clone(),
            config.owner.spawn_generation,
            config.owner.peer_uid,
        )
        .map_err(|e| io::Error::other(e.code()))?;
        let retention = Retention::open(&config.retention_dir)?;
        let mut entries = Vec::new();
        let mut ids = BTreeSet::new();
        let mut requests = BTreeSet::new();
        let mut hashes = BTreeSet::new();
        let mut attempts = BTreeSet::new();
        for selected in config.entries {
            if !valid_entry_id(&selected.id)
                || !ids.insert(selected.id.clone())
                || selected.submit_request_id == 0
                || selected.history_request_id == 0
                || !requests.insert(selected.submit_request_id)
                || !requests.insert(selected.history_request_id)
            {
                return Err(io::Error::other("invalid objective entry identity"));
            }
            let raw = read_private(&selected.envelope_path)?;
            let original = ProvidedObjective::parse_json(raw.clone())
                .map_err(|e| io::Error::other(e.code()))?;
            let identity = original.identity();
            let hash = sha256_hex(raw.as_bytes());
            if !hashes.insert(hash.clone()) {
                return Err(io::Error::other("duplicate original objective payload"));
            }
            let value: serde_json::Value = serde_json::from_str(&raw).map_err(io::Error::other)?;
            let source = value["body"]["source_envelope_json"]
                .as_str()
                .ok_or_else(|| io::Error::other("objective claimed source missing"))?
                .to_owned();
            let attempt_identity = attempt_identity(&config.owner.agent_id, identity);
            if !attempts.insert(attempt_identity.clone()) {
                return Err(io::Error::other("duplicate original objective identity"));
            }
            let attempted =
                retention.was_attempted(&config.owner.agent_id, &attempt_identity, &raw)?;
            let old_generation = identity.spawn_generation != config.owner.spawn_generation;
            let summary = ObjectiveSummary {
                id: selected.id,
                envelope_sha256: hash,
                claimed_issuer_id: identity.issuer_id.clone(),
                run_id: identity.run_id.clone(),
                original_spawn_generation: identity.spawn_generation,
                delivery: if attempted || old_generation {
                    ObjectiveDelivery::Unknown
                } else {
                    ObjectiveDelivery::Ready
                },
                diagnostic: if attempted {
                    Some("retained_prior_attempt_query_only".into())
                } else if old_generation {
                    Some("historical_generation_query_only".into())
                } else {
                    None
                },
                publication_digest: None,
                history: ObjectiveHistory::NotQueried,
                history_diagnostic: None,
                history_publication_digest: None,
            };
            entries.push(Entry {
                raw,
                attempt_identity,
                submit_request_id: selected.submit_request_id,
                history_request_id: selected.history_request_id,
                detail: ObjectiveDetail {
                    summary,
                    claimed_source_envelope_json: source,
                },
            });
        }
        for entry in &entries {
            let mut frame = Vec::new();
            trill_ui_core::write_frame(
                &mut frame,
                &Response::ObjectiveDetail {
                    detail: Box::new(entry.detail.clone()),
                    session_instance: "0".repeat(32),
                },
            )?;
        }
        let views = entries.iter().map(|e| e.detail.clone()).collect();
        let owner = Some((config.owner.agent_id.clone(), config.owner.spawn_generation));
        let mut engine = Engine {
            endpoint,
            peer_pid: config.owner.peer_pid,
            owner: config.owner.agent_id,
            entries,
            retention,
        };
        let (commands, incoming) = mpsc::sync_channel(1);
        let (results, replies) = mpsc::sync_channel(8);
        std::thread::Builder::new()
            .name("objective-client".into())
            .spawn(move || {
                while let Ok(command) = incoming.recv() {
                    let updated = match command {
                        Command::Submit(id) => engine.submit(&id),
                        Command::Query(id) => engine.query(&id),
                    };
                    if let Some(updated) = updated {
                        if results.send(updated).is_err() {
                            break;
                        }
                    }
                }
            })?;
        Ok(Self {
            commands: Some(commands),
            replies: Some(replies),
            owner,
            entries: views,
        })
    }
    pub fn refresh(&mut self) {
        let mut closed = false;
        if let Some(replies) = &self.replies {
            loop {
                match replies.try_recv() {
                    Ok(updated) => {
                        if let Some(entry) = self.entries.iter_mut().find(|e| {
                            e.summary.id == updated.id
                                && e.summary.envelope_sha256 == updated.envelope_sha256
                        }) {
                            entry.summary = updated;
                        }
                    }
                    Err(mpsc::TryRecvError::Empty) => break,
                    Err(mpsc::TryRecvError::Disconnected) => {
                        closed = true;
                        break;
                    }
                }
            }
        }
        if closed {
            self.commands = None;
            self.replies = None;
            for entry in &mut self.entries {
                if entry.summary.delivery == ObjectiveDelivery::Submitting {
                    entry.summary.delivery = ObjectiveDelivery::Unknown;
                    entry.summary.diagnostic = Some("objective_worker_closed_query_only".into());
                }
                if entry.summary.history == ObjectiveHistory::Querying {
                    entry.summary.history = ObjectiveHistory::Unknown;
                    entry.summary.history_diagnostic = Some("objective_worker_closed".into());
                }
            }
        }
    }
    pub fn list(&mut self, instance: &str) -> Response {
        self.refresh();
        Response::Objectives {
            configured: self.owner.is_some(),
            owner_agent_id: self.owner.as_ref().map(|o| o.0.clone()),
            owner_spawn_generation: self.owner.as_ref().map(|o| o.1),
            entries: self.entries.iter().map(|e| e.summary.clone()).collect(),
            session_instance: instance.into(),
        }
    }
    pub fn inspect(&mut self, id: &str, instance: &str) -> Response {
        self.refresh();
        match self.entries.iter().find(|e| e.summary.id == id) {
            Some(detail) => Response::ObjectiveDetail {
                detail: Box::new(detail.clone()),
                session_instance: instance.into(),
            },
            None => Self::error(instance, "No trusted signed-envelope entry selected"),
        }
    }
    pub fn enqueue(&mut self, id: String, submit: bool, instance: &str) -> Response {
        self.refresh();
        let Some(entry) = self.entries.iter_mut().find(|e| e.summary.id == id) else {
            return Self::error(instance, "No trusted signed-envelope entry selected");
        };
        if entry.summary.delivery == ObjectiveDelivery::Submitting
            || entry.summary.history == ObjectiveHistory::Querying
            || submit
                && (entry.summary.delivery != ObjectiveDelivery::Ready
                    || entry.summary.history == ObjectiveHistory::HistoricalPublication)
        {
            return Self::error(
                instance,
                "Objective client is busy or query-only; no submission queued",
            );
        }
        let Some(commands) = &self.commands else {
            return Self::error(instance, "Original Objective client not configured");
        };
        let command = if submit {
            Command::Submit(id)
        } else {
            Command::Query(id)
        };
        if commands.try_send(command).is_err() {
            return Self::error(instance, "Objective client busy; no command queued");
        }
        if submit {
            entry.summary.delivery = ObjectiveDelivery::Submitting;
        } else {
            entry.summary.history = ObjectiveHistory::Querying;
        }
        self.list(instance)
    }
    fn error(instance: &str, message: &str) -> Response {
        Response::Error {
            message: message.into(),
            session_instance: instance.into(),
        }
    }
}
fn attempt_identity(
    owner: &str,
    identity: &hepta_os_observer::objective::ObjectiveIdentity,
) -> String {
    // Stable original claims, never raw JSON serialization. This digest is a
    // client anti-resend index, not a signature, grant or owner journal key.
    let fields = [
        owner.to_owned(),
        identity.issuer_id.clone(),
        identity.key_epoch.to_string(),
        identity.message_id.clone(),
        identity.sequence.to_string(),
        identity.run_id.clone(),
        identity.spawn_generation.to_string(),
    ];
    let mut bytes = b"trill.objective.client-attempt.v1\0".to_vec();
    for field in fields {
        bytes.extend_from_slice(field.as_bytes());
        bytes.push(0);
    }
    sha256_hex(&bytes)
}

impl Engine {
    fn submit(&mut self, id: &str) -> Option<ObjectiveSummary> {
        let entry = self
            .entries
            .iter_mut()
            .find(|e| e.detail.summary.id == id)?;
        if entry.detail.summary.delivery != ObjectiveDelivery::Ready
            || entry.detail.summary.history == ObjectiveHistory::HistoricalPublication
        {
            return Some(entry.detail.summary.clone());
        }
        entry.detail.summary.delivery = ObjectiveDelivery::Unknown;
        entry.detail.summary.diagnostic = Some("retained_attempt_outcome_unknown".into());
        if self
            .retention
            .begin_once(&self.owner, &entry.attempt_identity, &entry.raw)
            .is_err()
        {
            entry.detail.summary.delivery = ObjectiveDelivery::NotSent;
            entry.detail.summary.diagnostic = Some("client_retention_failed_no_transport".into());
            return Some(entry.detail.summary.clone());
        }
        let original = match ProvidedObjective::parse_json(entry.raw.clone()) {
            Ok(v) => v,
            Err(_) => return Some(entry.detail.summary.clone()),
        };
        let transport = match ObjectiveTransport::new(
            self.endpoint.clone(),
            self.peer_pid,
            entry.submit_request_id,
        ) {
            Ok(v) => v,
            Err(e) => {
                entry.detail.summary.delivery = ObjectiveDelivery::NotSent;
                entry.detail.summary.diagnostic = Some(e.code().into());
                return Some(entry.detail.summary.clone());
            }
        };
        let attempt = transport.submit_once(original);
        let summary = &mut entry.detail.summary;
        match attempt.status() {
            SubmissionStatus::NotSent(issue) => {
                summary.delivery = ObjectiveDelivery::NotSent;
                summary.diagnostic = Some(issue.code().into());
            }
            SubmissionStatus::SubmitUnknown(issue) => {
                summary.delivery = ObjectiveDelivery::Unknown;
                summary.diagnostic = Some(issue.code().into());
            }
            SubmissionStatus::RefusedBeforePublication { reason, .. } => {
                summary.delivery = ObjectiveDelivery::Refused;
                summary.diagnostic = Some(
                    match reason {
                        PrePublicationRefusal::ObjectiveUnavailable => "objective_unavailable",
                        PrePublicationRefusal::UnsupportedSchema => "unsupported_schema",
                    }
                    .into(),
                );
            }
            SubmissionStatus::Admitted(receipt) => {
                summary.delivery = ObjectiveDelivery::Admitted;
                summary.diagnostic = None;
                summary.publication_digest = Some(receipt.publication_digest.clone());
            }
            SubmissionStatus::Conflict(_) => {
                summary.delivery = ObjectiveDelivery::Conflict;
                summary.diagnostic = Some("objective_conflict".into());
            }
        }
        Some(summary.clone())
    }
    fn query(&mut self, id: &str) -> Option<ObjectiveSummary> {
        let entry = self
            .entries
            .iter_mut()
            .find(|e| e.detail.summary.id == id)?;
        entry.detail.summary.history = ObjectiveHistory::Unknown;
        let original = match ProvidedObjective::parse_json(entry.raw.clone()) {
            Ok(v) => v,
            Err(_) => return Some(entry.detail.summary.clone()),
        };
        let client = match ObjectiveHistoryClient::new(
            self.endpoint.clone(),
            self.peer_pid,
            entry.history_request_id,
        ) {
            Ok(v) => v,
            Err(e) => {
                entry.detail.summary.history_diagnostic = Some(e.code().into());
                return Some(entry.detail.summary.clone());
            }
        };
        let attempt = client.query_once(original, None);
        match attempt.status() {
            HistoryStatus::HistoricalPublication { publication, .. } => {
                entry.detail.summary.history = ObjectiveHistory::HistoricalPublication;
                entry.detail.summary.history_diagnostic = None;
                entry.detail.summary.history_publication_digest =
                    Some(publication.publication_digest.clone());
            }
            HistoryStatus::Unknown(issue) => {
                entry.detail.summary.history_diagnostic = Some(issue.code().into());
            }
            HistoryStatus::QueryNotSent(issue) => {
                entry.detail.summary.history_diagnostic = Some(issue.code().into());
            }
        }
        Some(entry.detail.summary.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::super::objective_store::tests::{write, Root};
    use super::*;
    use std::fs;
    use std::io::{BufRead, BufReader};
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::UnixListener;
    use std::time::{Duration, Instant};
    const RAW: &str = include_str!(
        "../../../services/hepta-os/tests/fixtures/objective_ingress_original_wire_only.json"
    );
    fn config(root: &Root) -> Config {
        Config {
            schema_version: 1,
            owner: Owner {
                socket_path: root.0.join("owner.sock"),
                agent_id: "11111111-1111-4111-8111-111111111111".into(),
                spawn_generation: 3,
                peer_uid: trill_ui_core::host_peer::current_effective_uid(),
                peer_pid: std::process::id(),
            },
            retention_dir: root.0.clone(),
            entries: vec![Selection {
                id: "provided".into(),
                envelope_path: root.0.join("envelope"),
                submit_request_id: 91,
                history_request_id: 92,
            }],
        }
    }
    fn summary(m: &mut ObjectiveMonitor) -> ObjectiveSummary {
        m.refresh();
        m.entries[0].summary.clone()
    }
    fn finish(m: &mut ObjectiveMonitor) -> ObjectiveSummary {
        let deadline = Instant::now() + Duration::from_secs(4);
        loop {
            let value = summary(m);
            if value.delivery != ObjectiveDelivery::Submitting {
                return value;
            }
            assert!(Instant::now() < deadline);
            std::thread::sleep(Duration::from_millis(5));
        }
    }
    #[test]
    fn default_has_no_owner_or_submit_route() {
        let mut m = ObjectiveMonitor::default();
        assert!(
            matches!(m.list("i"),Response::Objectives{configured:false,entries,..}if entries.is_empty())
        );
        assert!(matches!(
            m.enqueue("provided".into(), true, "i"),
            Response::Error { .. }
        ));
    }
    #[test]
    fn lost_reply_is_retained_before_socket_send_and_reopen_is_query_only() {
        let root = Root::new();
        let raw = RAW.trim_end_matches('\n');
        write(&root.0.join("envelope"), raw.as_bytes());
        let listener = UnixListener::bind(root.0.join("owner.sock")).unwrap();
        fs::set_permissions(root.0.join("owner.sock"), fs::Permissions::from_mode(0o600)).unwrap();
        let marker = root.0.join(format!(
            "{}.attempt",
            attempt_identity(
                "11111111-1111-4111-8111-111111111111",
                ProvidedObjective::parse_json(raw.to_owned())
                    .unwrap()
                    .identity()
            )
        ));
        let peer = std::thread::spawn(move || {
            let (stream, _) = listener.accept().unwrap();
            let mut frame = String::new();
            BufReader::new(stream).read_line(&mut frame).unwrap();
            assert!(marker.exists());
            assert!(frame.contains("objective_start"));
            frame
        });
        let mut m = ObjectiveMonitor::from_config(config(&root)).unwrap();
        m.enqueue("provided".into(), true, "i");
        assert_eq!(finish(&mut m).delivery, ObjectiveDelivery::Unknown);
        assert!(matches!(
            m.enqueue("provided".into(), true, "i"),
            Response::Error { .. }
        ));
        peer.join().unwrap();
        drop(m);
        let deadline = Instant::now() + Duration::from_secs(2);
        let mut reopened = loop {
            match ObjectiveMonitor::from_config(config(&root)) {
                Ok(m) => break m,
                Err(_) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(5)),
                Err(e) => panic!("{e}"),
            }
        };
        assert_eq!(summary(&mut reopened).delivery, ObjectiveDelivery::Unknown);
        assert!(matches!(
            reopened.enqueue("provided".into(), true, "i"),
            Response::Error { .. }
        ));
    }
    #[test]
    fn old_signed_generation_is_query_only_before_any_send() {
        let root = Root::new();
        write(
            &root.0.join("envelope"),
            RAW.trim_end_matches('\n').as_bytes(),
        );
        let mut cfg = config(&root);
        cfg.owner.spawn_generation = 4;
        let mut m = ObjectiveMonitor::from_config(cfg).unwrap();
        assert_eq!(summary(&mut m).delivery, ObjectiveDelivery::Unknown);
        assert!(matches!(
            m.enqueue("provided".into(), true, "i"),
            Response::Error { .. }
        ));
    }
    #[test]
    fn historical_publication_prevents_submit_even_without_local_attempt() {
        let root = Root::new();
        write(
            &root.0.join("envelope"),
            RAW.trim_end_matches('\n').as_bytes(),
        );
        let mut m = ObjectiveMonitor::from_config(config(&root)).unwrap();
        m.entries[0].summary.history = ObjectiveHistory::HistoricalPublication;
        assert!(matches!(
            m.enqueue("provided".into(), true, "i"),
            Response::Error { .. }
        ));
    }
    #[test]
    fn dead_worker_projects_unknown_instead_of_forever_submitting() {
        let root = Root::new();
        write(
            &root.0.join("envelope"),
            RAW.trim_end_matches('\n').as_bytes(),
        );
        let mut m = ObjectiveMonitor::from_config(config(&root)).unwrap();
        let (tx, rx) = mpsc::sync_channel(1);
        drop(tx);
        m.replies = Some(rx);
        m.entries[0].summary.delivery = ObjectiveDelivery::Submitting;
        m.entries[0].summary.history = ObjectiveHistory::Querying;
        m.refresh();
        assert_eq!(m.entries[0].summary.delivery, ObjectiveDelivery::Unknown);
        assert_eq!(m.entries[0].summary.history, ObjectiveHistory::Unknown);
        assert!(m.commands.is_none());
    }
    fn reopen_after_parallel_execs(root: &Root) -> io::Result<ObjectiveMonitor> {
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            match ObjectiveMonitor::from_config(config(root)) {
                Err(error)
                    if error.kind() == io::ErrorKind::WouldBlock && Instant::now() < deadline =>
                {
                    std::thread::sleep(Duration::from_millis(5))
                }
                result => return result,
            }
        }
    }
    #[test]
    fn same_original_claims_cannot_rearm_by_json_order_spaces_or_signature_hex_case() {
        let root = Root::new();
        let raw = RAW.trim_end_matches('\n').to_owned();
        // Use hex letters so changing their presentation is meaningful; this
        // fixture is structurally valid but does not claim issuer trust.
        let mut value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        value["signature_hex"] = "ab".repeat(64).into();
        let raw = serde_json::to_string(&value).unwrap();
        write(&root.0.join("envelope"), raw.as_bytes());
        let original = ProvidedObjective::parse_json(raw.clone()).unwrap();
        let identity =
            attempt_identity("11111111-1111-4111-8111-111111111111", original.identity());
        let mut retention = Retention::open(&root.0).unwrap();
        retention
            .begin_once("11111111-1111-4111-8111-111111111111", &identity, &raw)
            .unwrap();
        drop(retention);
        let mut reordered = value
            .as_object()
            .unwrap()
            .iter()
            .rev()
            .map(|(k, v)| format!("{}:{}", serde_json::to_string(k).unwrap(), v))
            .collect::<Vec<_>>()
            .join(",");
        reordered = format!("{{{reordered}}}");
        let variants = [
            raw.replacen("{", "{ ", 1),
            reordered,
            raw.replace(&"ab".repeat(64), &"AB".repeat(64)),
        ];
        for changed in variants {
            assert_ne!(raw, changed);
            let supplied = ProvidedObjective::parse_json(changed.clone()).unwrap();
            assert_eq!(
                identity,
                attempt_identity("11111111-1111-4111-8111-111111111111", supplied.identity())
            );
            fs::write(root.0.join("envelope"), changed).unwrap();
            let error = reopen_after_parallel_execs(&root)
                .err()
                .expect("same identity must reject changed bytes");
            assert_eq!(error.kind(), io::ErrorKind::Other);
            assert_eq!(
                error.to_string(),
                "objective private client retention invalid"
            );
        }
        fs::write(root.0.join("envelope"), raw).unwrap();
        let mut reopened = reopen_after_parallel_execs(&root).unwrap();
        assert_eq!(summary(&mut reopened).delivery, ObjectiveDelivery::Unknown);
    }
}
