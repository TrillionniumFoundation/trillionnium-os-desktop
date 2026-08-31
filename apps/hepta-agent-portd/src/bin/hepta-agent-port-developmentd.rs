//! Explicit development-profile AgentPort activation for D3 local fixtures.
//!
//! This binary is deliberately separate from `hepta-agent-portd` (the product
//! binary) and from the `fixture`/qualification binaries.  It can only serve
//! an already-connected systemd AF_UNIX stream when both the development
//! profile argument and the administrator-created marker are present.  The
//! handler is the typed `BrowserActor<DeterministicLocalRuntime>` and every
//! admitted request is wrapped by the durable D0C-06 receipt observer.
//!
//! No listener is created here.  No public endpoint or external effect
//! authority is available; the actor runtime accepts loopback HTTP fixtures
//! and ephemeral profiles only.

#![deny(unsafe_op_in_unsafe_fn)]

use hepta_agent_port::{
    AgentPortError, BrowserRequestHandler, DispatchContext, HandlerOutcome, ServiceEvidence,
    serve_one_with_observer,
};
use hepta_agent_transport::{PeerIdentity, PeerPolicy};
use hepta_browser_actor::{
    BrowserActor, D3_BROWSERD_VERSION, D3_PLAN_REVISION, D3_SERVO_COMMIT,
    DeterministicLocalRuntime, PrincipalBinding, PrincipalBindingError, TaskFlowPrincipal,
};
use hepta_browser_codec::BrowserRequest;
use hepta_peer_attestation::{
    AttestationError, AttestedPeer, PeerRuntimePolicy, ProcfsPeerAttestor, hash_trusted_executable,
    resolve_group_id, resolve_user_id,
};
use hepta_session_core::{JournalError, JournalId, JournalOpenPolicy, ReceiptJournal};
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::FromRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::UnixStream;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const DEVELOPMENT_MARKER_PATH: &str = "/etc/hepta/enable-agent-port-development";
const DEVELOPMENT_SOCKET_PATH: &str = "/run/hepta/browserd/agent-development.sock";
const DEFAULT_JOURNAL_PATH: &str = "/var/lib/hepta-browserd/development/receipts.journal";
const DEVELOPMENT_JOURNAL_ROOT: &str = "/var/lib/hepta-browserd/development";
const EXPECTED_PEER_USER: &str = "hepta-agent";
const EXPECTED_PEER_GROUP: &str = "hepta-agent";
const EXPECTED_PEER_UNIT: &str = "hepta-agent.service";
const DEVELOPMENT_PEER_EXECUTABLE: &str = "/usr/libexec/hepta-agent";
const EXPECTED_EXECUTABLE_ENV: &str = "HEPTA_D3_EXPECTED_EXECUTABLE_SHA256";
const PRINCIPAL_ID_ENV: &str = "HEPTA_D3_PRINCIPAL_ID";
const IMAGE_ID_ENV: &str = "HEPTA_D3_IMAGE_ID";
const JOURNAL_PATH_ENV: &str = "HEPTA_D3_RECEIPT_JOURNAL";
const CONNECTION_CEILING: Duration = Duration::from_secs(20);
const DEVELOPMENT_PROFILE: &str = "development";
const JOURNAL_ID: JournalId = JournalId([0xd3; 16]);

/// Keep the marker descriptor open through the one-request admission path.
/// Opening with O_NOFOLLOW and validating metadata through this descriptor
/// prevents a symlink swap between a pathname preflight and the security
/// decision.  The descriptor is intentionally not used for marker contents;
/// the marker's existence/ownership is the only activation fact.
#[derive(Debug)]
struct MarkerGuard {
    _file: File,
}

/// Adapter used by the one-request development service to refresh peer
/// identity immediately before each actor dispatch.  Keeping this wrapper at
/// the service boundary preserves the generic AgentPort API while ensuring a
/// stale PID, changed start time, cgroup, unit, or executable is rejected
/// before runtime work starts.
struct AttestedActorHandler<'a> {
    actor: &'a mut BrowserActor<DeterministicLocalRuntime>,
    attestor: ProcfsPeerAttestor,
    attested: &'a AttestedPeer,
}

impl BrowserRequestHandler for AttestedActorHandler<'_> {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.actor
            .handle_attested(context, request, &self.attestor, self.attested)
    }
}

fn main() {
    let arguments = std::env::args().skip(1).collect::<Vec<_>>();
    let outcome = if arguments.iter().any(|argument| argument == "--self-check") {
        self_check(&arguments).map(|report| println!("{report}"))
    } else {
        serve_inherited_connection(&arguments)
            .map(|evidence| println!("{}", evidence_json(&evidence)))
    };
    if let Err(error) = outcome {
        eprintln!("hepta-agent-port-developmentd: {error}");
        std::process::exit(1);
    }
}

fn serve_inherited_connection(arguments: &[String]) -> Result<ServiceEvidence, ServiceError> {
    require_development_profile(arguments)?;
    let _marker = require_marker(Path::new(DEVELOPMENT_MARKER_PATH))?;

    let stream = inherited_stream_from_stdin()?;
    verify_local_socket_path(&stream, Path::new(DEVELOPMENT_SOCKET_PATH))?;

    let expected_uid = resolve_user_id(EXPECTED_PEER_USER)?;
    let expected_gid = resolve_group_id(EXPECTED_PEER_GROUP)?;
    let peer = PeerIdentity::from_stream(&stream)?;
    let runtime_policy =
        PeerRuntimePolicy::for_system_service(expected_uid, expected_gid, EXPECTED_PEER_UNIT)?;
    let attestor = ProcfsPeerAttestor::default();
    // Cross-UID `/proc/<pid>/exe` reads are intentionally unavailable to this
    // service.  Bind the reviewed TaskFlow service mechanism to one compiled,
    // root-owned executable path instead; the attestor retains this exact
    // source and reopens/re-hashes it at every BrowserActor dispatch.
    let executable = hash_trusted_executable(DEVELOPMENT_PEER_EXECUTABLE)?;
    let attested =
        attestor.attest_with_static_executable_digest(peer, &runtime_policy, &executable)?;

    // The administrator-provided digest is an additional image/configuration
    // pin.  It must equal the independently opened trusted path before the
    // semantic principal is constructed.  `bind_attested` then copies the
    // digest/unit/cgroup only from the immutable, pidfd-backed snapshot.
    let principal = principal_from_environment(
        expected_uid,
        expected_gid,
        &attested.snapshot().executable_sha256,
    )?;
    let binding = PrincipalBinding::bind_attested(principal, peer, attested.snapshot())?;

    let journal_path = journal_path_from_environment()?;
    let journal = open_or_create_journal(&journal_path)?;
    let image_id =
        std::env::var(IMAGE_ID_ENV).unwrap_or_else(|_| "trillionnium-development-local".to_owned());
    let mut actor = BrowserActor::new(binding, DeterministicLocalRuntime::default());
    let mut observer = actor.receipt_observer(journal, image_id);
    let transport_policy = PeerPolicy {
        expected_pid: peer.pid,
        expected_uid,
        expected_gid: Some(expected_gid),
    };

    // Keep the pidfd-backed attestation alive until the one response has been
    // committed.  The wrapper refreshes procfs identity immediately before
    // actor dispatch; the observer commits requested/dispatched/terminal
    // records before `serve_one_with_observer` writes the response frame.
    let mut guarded_actor = AttestedActorHandler {
        actor: &mut actor,
        attestor,
        attested: &attested,
    };
    serve_one_with_observer(
        stream,
        transport_policy,
        CONNECTION_CEILING,
        &mut guarded_actor,
        &mut observer,
    )
    .map_err(ServiceError::AgentPort)
}

fn self_check(arguments: &[String]) -> Result<String, ServiceError> {
    require_profile_argument(arguments)?;
    hepta_browser_actor::self_check().map_err(ServiceError::ActorSelfCheck)?;
    Ok(format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.agent-port-development-self-check.v1\",",
            "\"ok\":true,\"profile\":\"{}\",\"development_only\":true,",
            "\"product_agent_port_connected\":false,\"integrated_image_qualified\":false,",
            "\"marker_required\":true,\"marker_shipped\":false,",
            "\"listener_created\":false,",
            "\"browser_actor_wired\":true,\"browser_actor_dispatch_exercised\":true,",
            "\"browser_actor_connected\":false,",
            "\"receipt_observer_wired\":true,\"receipt_observer_connected\":false,",
            "\"attestation_exercised\":false,\"journal_exercised\":false,",
            "\"static_attestation_wired\":true,",
            "\"cross_uid_procfs_required\":false,",
            "\"trusted_executable_path\":\"{}\",",
            "\"scope\":\"source_wiring_only\",",
            "\"external_effect_authority\":false,",
            "\"socket\":\"{}\",\"plan_revision\":\"{}\",",
            "\"servo_commit\":\"{}\",\"browserd_version\":\"{}\"}}"
        ),
        DEVELOPMENT_PROFILE,
        DEVELOPMENT_PEER_EXECUTABLE,
        DEVELOPMENT_SOCKET_PATH,
        D3_PLAN_REVISION,
        D3_SERVO_COMMIT,
        D3_BROWSERD_VERSION,
    ))
}

fn require_development_profile(arguments: &[String]) -> Result<(), ServiceError> {
    require_profile_argument(arguments)
}

fn require_profile_argument(arguments: &[String]) -> Result<(), ServiceError> {
    let mut profile_count = 0_u8;
    let mut index = 0_usize;
    while index < arguments.len() {
        match arguments[index].as_str() {
            "--self-check" => index += 1,
            "--profile" => {
                profile_count = profile_count.saturating_add(1);
                let value = arguments
                    .get(index + 1)
                    .ok_or(ServiceError::ProfileNotSelected)?;
                if value != DEVELOPMENT_PROFILE {
                    return Err(ServiceError::ProfileNotSelected);
                }
                index += 2;
            }
            argument => return Err(ServiceError::UnknownArgument(argument.to_owned())),
        }
    }
    if profile_count == 1 {
        Ok(())
    } else {
        Err(ServiceError::ProfileNotSelected)
    }
}

fn require_marker(path: &Path) -> Result<MarkerGuard, ServiceError> {
    let parent = path
        .parent()
        .ok_or_else(|| ServiceError::MarkerParentUnsafe(path.to_owned()))?;
    let parent_metadata = fs::symlink_metadata(parent).map_err(|source| {
        if source.kind() == io::ErrorKind::NotFound {
            ServiceError::MarkerParentUnsafe(parent.to_owned())
        } else {
            ServiceError::Io(source)
        }
    })?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(ServiceError::MarkerParentUnsafe(parent.to_owned()));
    }
    if parent_metadata.uid() != 0 {
        return Err(ServiceError::MarkerParentNotRootOwned(parent.to_owned()));
    }
    if parent_metadata.permissions().mode() & 0o022 != 0 {
        return Err(ServiceError::MarkerParentWritable(parent.to_owned()));
    }

    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|source| {
            if source.kind() == io::ErrorKind::NotFound {
                ServiceError::MarkerMissing(path.to_owned())
            } else if source.raw_os_error() == Some(libc::ELOOP) {
                ServiceError::MarkerNotRegular(path.to_owned())
            } else {
                ServiceError::Io(source)
            }
        })?;
    // Inspect the opened descriptor rather than the pathname.  This closes
    // the metadata/open race and makes the owner/mode decision refer to the
    // exact inode that remains held for the admission lifetime.
    let metadata = file.metadata().map_err(ServiceError::Io)?;
    if !metadata.is_file() {
        return Err(ServiceError::MarkerNotRegular(path.to_owned()));
    }
    if metadata.uid() != 0 {
        return Err(ServiceError::MarkerNotRootOwned(path.to_owned()));
    }
    if metadata.permissions().mode() & 0o022 != 0 {
        return Err(ServiceError::MarkerWritable(path.to_owned()));
    }
    Ok(MarkerGuard { _file: file })
}

fn principal_from_environment(
    expected_uid: u32,
    expected_gid: u32,
    attested_digest: &str,
) -> Result<TaskFlowPrincipal, ServiceError> {
    let configured = std::env::var(EXPECTED_EXECUTABLE_ENV)
        .map_err(|_| ServiceError::MissingConfiguration(EXPECTED_EXECUTABLE_ENV))?;
    if configured != attested_digest {
        return Err(ServiceError::ConfiguredExecutableDigestMismatch {
            configured,
            observed: attested_digest.to_owned(),
        });
    }
    let principal_id =
        std::env::var(PRINCIPAL_ID_ENV).unwrap_or_else(|_| "taskflow-development-local".to_owned());
    Ok(TaskFlowPrincipal {
        principal_id,
        expected_uid,
        expected_gid,
        expected_systemd_unit: EXPECTED_PEER_UNIT.to_owned(),
        expected_cgroup_v2_path: format!("/system.slice/{EXPECTED_PEER_UNIT}"),
        expected_executable_sha256: attested_digest.to_owned(),
    })
}

fn journal_path_from_environment() -> Result<PathBuf, ServiceError> {
    let path = std::env::var_os(JOURNAL_PATH_ENV)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_JOURNAL_PATH));
    validate_journal_path(&path)
}

fn validate_journal_path(path: &Path) -> Result<PathBuf, ServiceError> {
    let invalid = |reason| {
        Err(ServiceError::JournalPathInvalid {
            path: path.to_owned(),
            reason,
        })
    };
    if !path.is_absolute() {
        return invalid("path must be absolute");
    }
    if path
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return invalid("path must not contain '..'");
    }
    let root = Path::new(DEVELOPMENT_JOURNAL_ROOT);
    if !path.starts_with(root) || path == root {
        return invalid("path must remain below the development journal root");
    }
    if path.file_name().is_none() {
        return invalid("path must name a journal file");
    }
    Ok(path.to_owned())
}

fn open_or_create_journal(path: &Path) -> Result<ReceiptJournal, ServiceError> {
    // Validate and materialize the parent one component at a time before
    // probing or creating the journal leaf.  `create_dir_all` follows an
    // ancestor symlink; doing this preflight first prevents a mutable path
    // component from causing directory creation outside the configured
    // journal root.  ReceiptJournal repeats the checks at the final open.
    ensure_journal_parent(path)?;
    if path.exists() {
        return open_existing_journal(path);
    }
    let created_wall_clock_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| ServiceError::ClockBeforeUnixEpoch)?
        .as_millis();
    let created_wall_clock_unix_ms = u64::try_from(created_wall_clock_unix_ms)
        .map_err(|_| ServiceError::ClockBeforeUnixEpoch)?;
    match ReceiptJournal::create(path, JOURNAL_ID, created_wall_clock_unix_ms) {
        Ok(journal) => Ok(journal),
        Err(JournalError::Io(error)) if error.kind() == io::ErrorKind::AlreadyExists => {
            open_existing_journal(path)
        }
        Err(error) => Err(ServiceError::Journal(error)),
    }
}

fn ensure_journal_parent(path: &Path) -> Result<(), ServiceError> {
    let parent = path.parent().ok_or(ServiceError::JournalPathHasNoParent)?;
    if parent.as_os_str().is_empty() {
        return Err(ServiceError::JournalPathInvalid {
            path: path.to_owned(),
            reason: "path must have a parent directory",
        });
    }
    if path
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(ServiceError::JournalPathInvalid {
            path: path.to_owned(),
            reason: "path must not contain '..'",
        });
    }

    // Walk from the filesystem root (or the relative-path base) so a missing
    // suffix can be created without ever asking create_dir_all to resolve a
    // symlink in an unchecked component.
    let mut current = PathBuf::new();
    for component in parent.components() {
        match component {
            Component::RootDir => current.push(component.as_os_str()),
            Component::CurDir => {}
            Component::Normal(name) => {
                current.push(name);
                match fs::symlink_metadata(&current) {
                    Ok(metadata) => validate_journal_directory(&current, &metadata)?,
                    Err(error) if error.kind() == io::ErrorKind::NotFound => {
                        fs::create_dir(&current).map_err(ServiceError::Io)?;
                        let metadata = fs::symlink_metadata(&current).map_err(ServiceError::Io)?;
                        validate_journal_directory(&current, &metadata)?;
                    }
                    Err(error) => return Err(ServiceError::Io(error)),
                }
            }
            Component::ParentDir => unreachable!("parent traversal rejected above"),
            Component::Prefix(_) => {
                return Err(ServiceError::JournalPathInvalid {
                    path: path.to_owned(),
                    reason: "unsupported path prefix",
                });
            }
        }
    }
    Ok(())
}

fn validate_journal_directory(
    path: &Path,
    metadata: &std::fs::Metadata,
) -> Result<(), ServiceError> {
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ServiceError::JournalPathInvalid {
            path: path.to_owned(),
            reason: "journal parent must be a real directory",
        });
    }
    let mode = metadata.permissions().mode();
    let root_owned_sticky = metadata.uid() == 0 && mode & 0o1000 != 0;
    if mode & 0o022 != 0 && !root_owned_sticky {
        return Err(ServiceError::JournalPathInvalid {
            path: path.to_owned(),
            reason: "journal parent must not be group/other writable",
        });
    }
    Ok(())
}

fn open_existing_journal(path: &Path) -> Result<ReceiptJournal, ServiceError> {
    let mut journal = ReceiptJournal::open(path, JournalOpenPolicy::RECOVER_CRASH)
        .map_err(ServiceError::Journal)?;
    let report = journal.inspect().map_err(ServiceError::Journal)?;
    if report.header.journal_id != JOURNAL_ID {
        return Err(ServiceError::JournalIdentityMismatch);
    }
    // A rotated segment cannot be safely reopened in isolation: the
    // ReceiptJournal in-memory progress map would not contain predecessor
    // receipt IDs, allowing a fresh Requested record to replay an operation.
    // Until this development service is given an ordered chain-open API that
    // imports predecessor progress, fail closed rather than silently serving
    // a partial journal namespace.
    if report.header.segment_number > 1 {
        return Err(ServiceError::JournalRotationRequiresCompleteChain(
            report.header.segment_number,
        ));
    }
    if !report.unresolved.is_empty() {
        return Err(ServiceError::JournalHasUnresolvedReceipts(
            report.unresolved.len(),
        ));
    }
    Ok(journal)
}

fn inherited_stream_from_stdin() -> Result<UnixStream, ServiceError> {
    verify_stream_socket(0)?;
    // SAFETY: F_DUPFD_CLOEXEC creates a new descriptor referring to fd 0. The
    // returned descriptor is owned by this function and transferred exactly
    // once to UnixStream. Standard input remains owned by the process runtime.
    let duplicated = unsafe { libc::fcntl(0, libc::F_DUPFD_CLOEXEC, 3) };
    if duplicated < 0 {
        return Err(ServiceError::Io(io::Error::last_os_error()));
    }
    // SAFETY: `duplicated` is a fresh descriptor returned by fcntl and is now
    // transferred exactly once to UnixStream ownership.
    Ok(unsafe { UnixStream::from_raw_fd(duplicated) })
}

fn verify_stream_socket(fd: libc::c_int) -> Result<(), ServiceError> {
    let mut socket_domain: libc::c_int = 0;
    let mut domain_length = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    // SAFETY: the output pointers refer to initialized writable storage for
    // the call and getsockopt retains neither pointer.
    let domain_status = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_DOMAIN,
            std::ptr::addr_of_mut!(socket_domain).cast(),
            std::ptr::addr_of_mut!(domain_length),
        )
    };
    if domain_status != 0 {
        return Err(ServiceError::Io(io::Error::last_os_error()));
    }
    if usize::try_from(domain_length).ok() != Some(std::mem::size_of::<libc::c_int>())
        || socket_domain != libc::AF_UNIX
    {
        return Err(ServiceError::WrongInheritedDescriptor);
    }

    let mut socket_type: libc::c_int = 0;
    let mut length = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    // SAFETY: the output pointers refer to initialized writable storage for
    // the call and getsockopt retains neither pointer.
    let status = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_TYPE,
            std::ptr::addr_of_mut!(socket_type).cast(),
            std::ptr::addr_of_mut!(length),
        )
    };
    if status != 0 {
        return Err(ServiceError::Io(io::Error::last_os_error()));
    }
    if usize::try_from(length).ok() != Some(std::mem::size_of::<libc::c_int>())
        || socket_type != libc::SOCK_STREAM
    {
        return Err(ServiceError::WrongInheritedDescriptor);
    }
    Ok(())
}

fn verify_local_socket_path(stream: &UnixStream, expected: &Path) -> Result<(), ServiceError> {
    let address = stream.local_addr().map_err(ServiceError::Io)?;
    let actual = address
        .as_pathname()
        .ok_or(ServiceError::UnnamedInheritedSocket)?;
    if actual != expected {
        return Err(ServiceError::SocketPathMismatch {
            expected: expected.to_owned(),
            actual: actual.to_owned(),
        });
    }
    Ok(())
}

fn evidence_json(evidence: &ServiceEvidence) -> String {
    format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.agent-port-development-result.v1\",",
            "\"profile\":\"{}\",\"peer_pid\":{},\"peer_uid\":{},\"peer_gid\":{},",
            "\"transport_sequence\":{},\"request_id\":\"{}\",",
            "\"request_sha256\":\"{}\",\"response_sha256\":\"{}\",",
            "\"response_ok\":{},\"response_committed\":true}}"
        ),
        DEVELOPMENT_PROFILE,
        evidence.peer.pid.unwrap_or_default(),
        evidence.peer.uid,
        evidence.peer.gid,
        evidence.transport_sequence,
        escape_json(&evidence.request_id),
        evidence.request_sha256,
        evidence.response_sha256,
        evidence.response_ok,
    )
}

fn escape_json(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character.is_control() => {
                use std::fmt::Write;
                let _ = write!(output, "\\u{:04x}", character as u32);
            }
            character => output.push(character),
        }
    }
    output
}

#[derive(Debug)]
enum ServiceError {
    Io(io::Error),
    Transport(hepta_agent_transport::TransportError),
    Attestation(AttestationError),
    AgentPort(AgentPortError),
    Binding(PrincipalBindingError),
    Journal(JournalError),
    ActorSelfCheck(String),
    ProfileNotSelected,
    MarkerMissing(PathBuf),
    MarkerNotRegular(PathBuf),
    MarkerNotRootOwned(PathBuf),
    MarkerWritable(PathBuf),
    MarkerParentUnsafe(PathBuf),
    MarkerParentNotRootOwned(PathBuf),
    MarkerParentWritable(PathBuf),
    MissingConfiguration(&'static str),
    ConfiguredExecutableDigestMismatch {
        configured: String,
        observed: String,
    },
    UnknownArgument(String),
    JournalPathHasNoParent,
    JournalPathInvalid {
        path: PathBuf,
        reason: &'static str,
    },
    JournalIdentityMismatch,
    JournalRotationRequiresCompleteChain(u64),
    JournalHasUnresolvedReceipts(usize),
    ClockBeforeUnixEpoch,
    WrongInheritedDescriptor,
    UnnamedInheritedSocket,
    SocketPathMismatch {
        expected: PathBuf,
        actual: PathBuf,
    },
}

impl fmt::Display for ServiceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "I/O failed: {error}"),
            Self::Transport(error) => write!(formatter, "transport failed: {error}"),
            Self::Attestation(error) => write!(formatter, "peer attestation failed: {error}"),
            Self::AgentPort(error) => write!(formatter, "AgentPort failed: {error}"),
            Self::Binding(error) => write!(formatter, "principal binding failed: {error}"),
            Self::Journal(error) => write!(formatter, "receipt journal failed: {error}"),
            Self::ActorSelfCheck(error) => {
                write!(formatter, "BrowserActor self-check failed: {error}")
            }
            Self::ProfileNotSelected => formatter.write_str(
                "development activation requires the explicit '--profile development' argument",
            ),
            Self::MarkerMissing(path) => {
                write!(formatter, "development marker {} is absent", path.display())
            }
            Self::MarkerNotRegular(path) => write!(
                formatter,
                "development marker {} must be a regular non-symlink file",
                path.display()
            ),
            Self::MarkerNotRootOwned(path) => write!(
                formatter,
                "development marker {} must be owned by root",
                path.display()
            ),
            Self::MarkerWritable(path) => write!(
                formatter,
                "development marker {} must not be writable by group or other users",
                path.display()
            ),
            Self::MarkerParentUnsafe(path) => write!(
                formatter,
                "development marker parent {} must be a real directory",
                path.display()
            ),
            Self::MarkerParentNotRootOwned(path) => write!(
                formatter,
                "development marker parent {} must be owned by root",
                path.display()
            ),
            Self::MarkerParentWritable(path) => write!(
                formatter,
                "development marker parent {} must not be writable by group or other users",
                path.display()
            ),
            Self::MissingConfiguration(name) => {
                write!(
                    formatter,
                    "required development configuration {name} is absent"
                )
            }
            Self::ConfiguredExecutableDigestMismatch {
                configured,
                observed,
            } => write!(
                formatter,
                "configured development executable digest {configured} does not match trusted path digest {observed}"
            ),
            Self::UnknownArgument(argument) => {
                write!(formatter, "unknown development-profile argument {argument}")
            }
            Self::JournalPathHasNoParent => {
                formatter.write_str("receipt journal path has no parent directory")
            }
            Self::JournalPathInvalid { path, reason } => write!(
                formatter,
                "invalid development receipt journal path {}: {reason}",
                path.display()
            ),
            Self::JournalIdentityMismatch => {
                formatter.write_str("development receipt journal identity does not match profile")
            }
            Self::JournalRotationRequiresCompleteChain(segment) => write!(
                formatter,
                "development receipt journal segment {segment} requires complete ordered chain inspection before reopen"
            ),
            Self::JournalHasUnresolvedReceipts(count) => write!(
                formatter,
                "development receipt journal has {count} unresolved in-flight receipt(s)"
            ),
            Self::ClockBeforeUnixEpoch => formatter.write_str("system clock precedes Unix epoch"),
            Self::WrongInheritedDescriptor => {
                formatter.write_str("standard input is not an AF_UNIX stream socket")
            }
            Self::UnnamedInheritedSocket => {
                formatter.write_str("inherited stream has no filesystem pathname")
            }
            Self::SocketPathMismatch { expected, actual } => write!(
                formatter,
                "inherited socket path {} does not equal {}",
                actual.display(),
                expected.display()
            ),
        }
    }
}

impl std::error::Error for ServiceError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            Self::Transport(error) => Some(error),
            Self::Attestation(error) => Some(error),
            Self::AgentPort(error) => Some(error),
            Self::Binding(error) => Some(error),
            Self::Journal(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for ServiceError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<hepta_agent_transport::TransportError> for ServiceError {
    fn from(error: hepta_agent_transport::TransportError) -> Self {
        Self::Transport(error)
    }
}

impl From<AttestationError> for ServiceError {
    fn from(error: AttestationError) -> Self {
        Self::Attestation(error)
    }
}

impl From<PrincipalBindingError> for ServiceError {
    fn from(error: PrincipalBindingError) -> Self {
        Self::Binding(error)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn profile_argument_is_required_and_exact() {
        assert!(
            require_profile_argument(&["--profile".to_owned(), "development".to_owned(),]).is_ok()
        );
        assert!(require_profile_argument(&["--profile=development".to_owned()]).is_err());
        assert!(
            require_profile_argument(&["--profile".to_owned(), "production".to_owned(),]).is_err()
        );
        assert!(
            require_profile_argument(&[
                "--profile".to_owned(),
                "development".to_owned(),
                "--profile".to_owned(),
                "development".to_owned(),
            ])
            .is_err()
        );
        assert!(
            require_profile_argument(&[
                "--profile".to_owned(),
                "development".to_owned(),
                "--unknown".to_owned(),
            ])
            .is_err()
        );
    }

    #[test]
    fn marker_requires_regular_non_symlink_file() {
        let unique = format!(
            "hepta-d3-marker-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        fs::create_dir_all(&root).expect("root");
        let marker = root.join("marker");
        fs::write(&marker, b"development\n").expect("marker");
        let root_owned = fs::symlink_metadata(&root).expect("root metadata").uid() == 0;
        if root_owned {
            require_marker(&marker).expect("regular marker");
            fs::set_permissions(&marker, fs::Permissions::from_mode(0o664)).expect("permissions");
            assert!(matches!(
                require_marker(&marker),
                Err(ServiceError::MarkerWritable(_))
            ));
            fs::set_permissions(&marker, fs::Permissions::from_mode(0o644)).expect("permissions");
            let link = root.join("link");
            std::os::unix::fs::symlink(&marker, &link).expect("symlink");
            assert!(matches!(
                require_marker(&link),
                Err(ServiceError::MarkerNotRegular(_))
            ));
        } else {
            // Non-root CI cannot create a root-owned marker.  It must still
            // exercise the fail-closed path without turning the unit test
            // red merely because the test process lacks CAP_CHOWN.
            assert!(matches!(
                require_marker(&marker),
                Err(ServiceError::MarkerParentNotRootOwned(_))
            ));
        }
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn marker_parent_must_be_root_owned_and_not_group_writable() {
        let unique = format!(
            "hepta-d3-marker-parent-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        fs::create_dir_all(&root).expect("root");
        let marker = root.join("marker");
        fs::write(&marker, b"development\n").expect("marker");
        let metadata = fs::symlink_metadata(&root).expect("root metadata");
        if metadata.uid() == 0 {
            fs::set_permissions(&root, fs::Permissions::from_mode(0o777))
                .expect("parent permissions");
            assert!(matches!(
                require_marker(&marker),
                Err(ServiceError::MarkerParentWritable(_))
            ));
            fs::set_permissions(&root, fs::Permissions::from_mode(0o755))
                .expect("parent permissions");
        } else {
            assert!(matches!(
                require_marker(&marker),
                Err(ServiceError::MarkerParentNotRootOwned(_))
            ));
        }
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn journal_environment_path_is_absolute_and_confined() {
        let accepted = Path::new("/var/lib/hepta-browserd/development/custom/receipts.journal");
        assert_eq!(
            validate_journal_path(accepted).expect("confined path"),
            accepted
        );
        assert!(matches!(
            validate_journal_path(Path::new("receipts.journal")),
            Err(ServiceError::JournalPathInvalid { .. })
        ));
        assert!(matches!(
            validate_journal_path(Path::new(
                "/var/lib/hepta-browserd/development/../outside.journal"
            )),
            Err(ServiceError::JournalPathInvalid { .. })
        ));
        assert!(matches!(
            validate_journal_path(Path::new("/var/lib/hepta-browserd/other.journal")),
            Err(ServiceError::JournalPathInvalid { .. })
        ));
        assert!(matches!(
            validate_journal_path(Path::new(DEVELOPMENT_JOURNAL_ROOT)),
            Err(ServiceError::JournalPathInvalid { .. })
        ));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn inherited_descriptor_requires_unix_stream_family() {
        // An AF_UNIX stream is accepted; a same-type AF_INET socket is not.
        // Use raw libc sockets so this regression test does not introduce a
        // TCP listener/authority into the development binary source.
        let unix_fd = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_STREAM, 0) };
        if unix_fd < 0 {
            // Some hermetic CI sandboxes deny socket creation altogether.  A
            // denied syscall is an environment limitation, not a validator
            // failure; normal Linux runners execute the assertions below.
            assert!(
                matches!(
                    io::Error::last_os_error().raw_os_error(),
                    Some(libc::EPERM) | Some(libc::EAFNOSUPPORT)
                ),
                "AF_UNIX socket creation failed: {}",
                io::Error::last_os_error()
            );
            return;
        }
        assert!(verify_stream_socket(unix_fd).is_ok());
        unsafe { libc::close(unix_fd) };

        let inet_fd = unsafe { libc::socket(libc::AF_INET, libc::SOCK_STREAM, 0) };
        assert!(inet_fd >= 0, "AF_INET socket creation failed");
        assert!(matches!(
            verify_stream_socket(inet_fd),
            Err(ServiceError::WrongInheritedDescriptor)
        ));
        unsafe { libc::close(inet_fd) };
    }

    #[test]
    fn development_self_check_reports_source_wiring_without_live_claims() {
        let report = self_check(&[
            "--profile".to_owned(),
            "development".to_owned(),
            "--self-check".to_owned(),
        ])
        .expect("self-check");
        assert!(report.contains("\"development_only\":true"));
        assert!(report.contains("\"browser_actor_wired\":true"));
        assert!(report.contains("\"browser_actor_dispatch_exercised\":true"));
        assert!(report.contains("\"browser_actor_connected\":false"));
        assert!(report.contains("\"receipt_observer_wired\":true"));
        assert!(report.contains("\"receipt_observer_connected\":false"));
        assert!(report.contains("\"product_agent_port_connected\":false"));
        assert!(report.contains("\"integrated_image_qualified\":false"));
        assert!(report.contains("\"attestation_exercised\":false"));
        assert!(report.contains("\"journal_exercised\":false"));
        assert!(report.contains("\"static_attestation_wired\":true"));
        assert!(report.contains("\"cross_uid_procfs_required\":false"));
        assert!(report.contains(&format!(
            "\"trusted_executable_path\":\"{DEVELOPMENT_PEER_EXECUTABLE}\""
        )));
        assert!(report.contains("\"scope\":\"source_wiring_only\""));
        assert!(report.contains("\"listener_created\":false"));
        assert!(report.contains("\"marker_shipped\":false"));
    }

    #[test]
    fn configured_digest_must_match_the_trusted_path_observation() {
        let observed = "a".repeat(64);
        let error = ServiceError::ConfiguredExecutableDigestMismatch {
            configured: "b".repeat(64),
            observed: observed.clone(),
        };
        let rendered = error.to_string();
        assert!(rendered.contains(&"b".repeat(64)));
        assert!(rendered.contains(&observed));
    }

    #[test]
    fn journal_factory_creates_and_reopens_a_private_receipt_store() {
        let unique = format!(
            "hepta-d3-journal-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        fs::create_dir_all(&root).expect("root");
        let path = root.join("receipts.journal");
        let journal = open_or_create_journal(&path).expect("create journal");
        assert_eq!(journal.path(), path.as_path());
        drop(journal);
        let reopened = open_or_create_journal(&path).expect("reopen journal");
        assert_eq!(reopened.path(), path.as_path());
        drop(reopened);
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn journal_factory_rejects_symlinked_ancestor_before_creation() {
        let unique = format!(
            "hepta-d3-journal-preflight-symlink-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        let real = root.join("real");
        let link = root.join("link");
        fs::create_dir_all(&real).expect("real parent");
        std::os::unix::fs::symlink(&real, &link).expect("ancestor symlink");
        let path = link.join("new").join("receipts.journal");

        assert!(matches!(
            open_or_create_journal(&path),
            Err(ServiceError::JournalPathInvalid { reason, .. })
                if reason == "journal parent must be a real directory"
        ));
        assert!(!real.join("new").exists());
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn journal_factory_rejects_writable_ancestor_before_creation() {
        let unique = format!(
            "hepta-d3-journal-preflight-permissions-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        let outer = root.join("outer");
        fs::create_dir_all(&outer).expect("writable parent");
        fs::set_permissions(&outer, fs::Permissions::from_mode(0o775))
            .expect("make ancestor group writable");
        let path = outer.join("new").join("receipts.journal");

        assert!(matches!(
            open_or_create_journal(&path),
            Err(ServiceError::JournalPathInvalid { reason, .. })
                if reason == "journal parent must not be group/other writable"
        ));
        assert!(!outer.join("new").exists());
        fs::set_permissions(&outer, fs::Permissions::from_mode(0o755))
            .expect("restore parent permissions");
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn journal_factory_rejects_a_different_journal_identity() {
        let unique = format!(
            "hepta-d3-journal-id-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        fs::create_dir_all(&root).expect("root");
        let path = root.join("receipts.journal");
        let journal = ReceiptJournal::create(&path, JournalId([0x42; 16]), 1)
            .expect("create foreign journal");
        drop(journal);
        assert!(matches!(
            open_or_create_journal(&path),
            Err(ServiceError::JournalIdentityMismatch)
        ));
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn journal_factory_rejects_unresolved_inflight_receipts() {
        use hepta_session_core::{
            PrivacyClass, ReceiptEffectClass as EffectClass, ReceiptEvent,
            ReceiptLifecycleState as LifecycleState, ReceiptSource,
        };

        let unique = format!(
            "hepta-d3-journal-unresolved-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        fs::create_dir_all(&root).expect("root");
        let path = root.join("receipts.journal");
        let mut journal = ReceiptJournal::create(&path, JOURNAL_ID, 1).expect("create journal");
        let event = |receipt_id: &str, lifecycle: LifecycleState| ReceiptEvent {
            receipt_id: receipt_id.to_owned(),
            plan_revision: "2026-08-28-d5".to_owned(),
            image_id: "image-fixture".to_owned(),
            servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
            browserd_version: "0.1.0".to_owned(),
            session_id: "session-1".to_owned(),
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 1,
            mutation_epoch: 0,
            source: ReceiptSource::Agent,
            operation: "page.observe".to_owned(),
            lifecycle,
            outcome: None,
            effect_class: EffectClass::PotentialExternalEffect,
            privacy_class: PrivacyClass::Internal,
            request_sha256: [1; 32],
            response_sha256: None,
            error_code: None,
            detail: Some("fixture".to_owned()),
            monotonic_ms: 10,
            wall_clock_unix_ms: 20,
        };
        journal
            .append(event("receipt-requested", LifecycleState::Requested))
            .expect("requested");
        journal
            .append(event("receipt-dispatched", LifecycleState::Requested))
            .expect("requested");
        journal
            .append(event("receipt-dispatched", LifecycleState::Dispatched))
            .expect("dispatched");
        drop(journal);
        assert!(matches!(
            open_or_create_journal(&path),
            Err(ServiceError::JournalHasUnresolvedReceipts(2))
        ));
        fs::remove_dir_all(root).expect("remove test root");
    }

    #[test]
    fn journal_factory_rejects_isolated_rotated_segment() {
        use hepta_session_core::{
            PrivacyClass, ReceiptEffectClass as EffectClass, ReceiptEvent,
            ReceiptLifecycleState as LifecycleState, ReceiptOutcome, ReceiptSource,
        };

        let unique = format!(
            "hepta-d3-journal-rotated-reopen-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        fs::create_dir_all(&root).expect("root");
        let first_dir = root.join("predecessor");
        let second_dir = root.join("successor");
        fs::create_dir_all(&first_dir).expect("predecessor root");
        fs::create_dir_all(&second_dir).expect("successor root");
        let first = first_dir.join("segment-1.journal");
        let second = second_dir.join("segment-2.journal");

        // Rotation requires a non-empty predecessor.  A terminal lifecycle is
        // enough to make the segment quiescent while keeping the fixture
        // small.  The successor carries a predecessor digest in its header;
        // opening that file alone would nevertheless reconstruct an empty
        // progress map and could admit replayed receipt IDs.  The development
        // service must reject this partial chain until an ordered chain-open
        // API is available.
        let mut journal = ReceiptJournal::create(&first, JOURNAL_ID, 1).expect("create journal");
        let event = |lifecycle: LifecycleState| ReceiptEvent {
            receipt_id: "rotated-replay".to_owned(),
            plan_revision: "2026-08-28-d5".to_owned(),
            image_id: "image-fixture".to_owned(),
            servo_commit: "670ae8a70801b162e186f81cbb5bdd2d59c39108".to_owned(),
            browserd_version: "0.1.0".to_owned(),
            session_id: "session-1".to_owned(),
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 1,
            mutation_epoch: 0,
            source: ReceiptSource::Agent,
            operation: "page.observe".to_owned(),
            lifecycle,
            outcome: None,
            effect_class: EffectClass::PotentialExternalEffect,
            privacy_class: PrivacyClass::Internal,
            request_sha256: [1; 32],
            response_sha256: None,
            error_code: None,
            detail: Some("fixture".to_owned()),
            monotonic_ms: 10,
            wall_clock_unix_ms: 20,
        };
        journal
            .append(event(LifecycleState::Requested))
            .expect("append requested");
        journal
            .append(event(LifecycleState::Dispatched))
            .expect("append dispatched");
        let mut completed = event(LifecycleState::Completed);
        completed.outcome = Some(ReceiptOutcome::Succeeded);
        completed.response_sha256 = Some([2; 32]);
        journal.append(completed).expect("append completed");
        let (_seal, next) = journal.rotate(&second, 2).expect("rotate journal");
        drop(next);

        assert!(matches!(
            open_or_create_journal(&second),
            Err(ServiceError::JournalRotationRequiresCompleteChain(2))
        ));
        fs::remove_dir_all(root).expect("remove test root");
    }
}
