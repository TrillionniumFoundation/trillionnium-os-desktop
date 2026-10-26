//! Linux application persistence, not the Hepta operation ledger or authority.
//! A single directory-anchored writer commits text/revision/application receipts
//! together: write temporary file, fsync file, rename, fsync directory. Replies
//! are published only after that sequence. A failure poisons this writer.
use super::*;
use std::ffi::CString;
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path};

const MAX_STATE_BYTES: u64 = 512 * 1024;
const MAX_RECEIPTS: usize = 1;
const MAX_INCARNATIONS: usize = 1024;
const STATE: &str = "state.json";
const PENDING: &str = ".state.pending";
const LOCK: &str = "writer.lock";

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct State {
    schema_version: u16,
    document_id: String,
    text: String,
    revision: u64,
    active_target: NotesTargetIdentity,
    incarnations: Vec<NotesTargetIdentity>,
    receipts: Vec<StoredReceipt>,
    retired: Option<RetiredReceipt>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredReceipt {
    response: NotesResponse,
    exact_utf8: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RetiredReceipt {
    target: NotesTargetIdentity,
    operation_id: String,
    payload_sha256: String,
    receipt_sha256: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Acknowledge {
    schema_version: u16,
    action: AcknowledgeAction,
    target: NotesTargetIdentity,
    operation_id: String,
    payload_sha256: String,
    receipt_sha256: String,
}
#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum AcknowledgeAction {
    AcknowledgeTerminal,
}
#[derive(Serialize)]
struct Acknowledgement<'a> {
    schema_version: u16,
    target: &'a NotesTargetIdentity,
    operation_id: &'a str,
    payload_sha256: &'a str,
    receipt_sha256: &'a str,
    status: &'static str,
}

impl State {
    fn validate(&self) -> io::Result<()> {
        if self.schema_version != 1
            || !lower_hex(&self.document_id, 32)
            || self.text.len() > MAX_NOTES_TEXT_BYTES
            || self.receipts.len() > MAX_RECEIPTS
            || self.incarnations.is_empty()
            || self.incarnations.len() > MAX_INCARNATIONS
            || self.incarnations.last() != Some(&self.active_target)
        {
            return Err(invalid("Notes persisted state bounds or identity"));
        }
        for (index, target) in self.incarnations.iter().enumerate() {
            target.validate().map_err(protocol)?;
            if self.incarnations[..index].contains(target) {
                return Err(invalid("Notes incarnation was reused"));
            }
        }
        if let Some(retired) = &self.retired {
            if !self.incarnations.contains(&retired.target)
                || !valid_operation_id(&retired.operation_id)
                || !lower_hex(&retired.payload_sha256, 64)
                || !lower_hex(&retired.receipt_sha256, 64)
            {
                return Err(invalid("Notes retired receipt binding"));
            }
        }
        for (index, receipt) in self.receipts.iter().enumerate() {
            let stored = receipt;
            let receipt = &stored.response;
            if NotesResponse::parse_exact(stored.exact_utf8.as_bytes()).map_err(protocol)?
                != *receipt
            {
                return Err(invalid("Notes exact receipt differs from metadata"));
            }
            let NotesResult::Applied {
                revision,
                text_sha256,
                ..
            } = &receipt.result
            else {
                return Err(invalid("only applied application receipts may be retained"));
            };
            if *revision > self.revision
                || !self.incarnations.contains(&receipt.target)
                || (*revision == self.revision && *text_sha256 != sha256_hex(self.text.as_bytes()))
                || self.receipts[..index].iter().any(|old| {
                    old.response.target == receipt.target
                        && old.response.operation_id == receipt.operation_id
                })
            {
                return Err(invalid("Notes receipt/state consistency"));
            }
        }
        Ok(())
    }
}

pub struct DurableNotes {
    directory: File,
    lock: File,
    state: State,
    poisoned: bool,
}

impl DurableNotes {
    /// Creates a brand-new private directory; an existing directory is refused.
    /// A trusted launcher supplies the path, never an effect payload/renderer.
    pub fn create(path: &Path, target: NotesTargetIdentity) -> io::Result<Self> {
        target.validate().map_err(protocol)?;
        let parent = open_directory(path.parent().ok_or_else(|| invalid("Notes parent"))?, false)?;
        let name = path
            .file_name()
            .ok_or_else(|| invalid("Notes directory name"))?;
        let name = CString::new(name.as_bytes()).map_err(|_| invalid("Notes path NUL"))?;
        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let directory = openat(
            parent.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_DIRECTORY,
            0,
        )?;
        check_private_dir(&directory)?;
        parent.sync_all()?;
        let lock = open_lock(&directory, true)?;
        let mut random = [0u8; 16];
        File::open("/dev/urandom")?.read_exact(&mut random)?;
        let state = State {
            schema_version: 1,
            document_id: random.iter().map(|b| format!("{b:02x}")).collect(),
            text: String::new(),
            revision: 0,
            active_target: target.clone(),
            incarnations: vec![target],
            receipts: Vec::new(),
            retired: None,
        };
        let mut store = Self {
            directory,
            lock,
            state: state.clone(),
            poisoned: false,
        };
        store.commit(state, true)?;
        Ok(store)
    }

    /// Opens the same document under a NEW process incarnation. Old effects
    /// remain fenced; the private recovery API can only observe old receipts.
    pub fn reopen(path: &Path, target: NotesTargetIdentity) -> io::Result<Self> {
        target.validate().map_err(protocol)?;
        let directory = open_directory(path, false)?;
        check_private_dir(&directory)?;
        let lock = open_lock(&directory, false)?;
        let state_file = open_named(&directory, STATE, libc::O_RDONLY, 0)?;
        check_private_file(&state_file)?;
        let mut raw = Vec::new();
        state_file.take(MAX_STATE_BYTES + 1).read_to_end(&mut raw)?;
        if raw.len() as u64 > MAX_STATE_BYTES {
            return Err(invalid("Notes state too large"));
        }
        let mut state: State = serde_json::from_slice(&raw).map_err(io::Error::other)?;
        state.validate()?;
        if state.incarnations.contains(&target) || state.incarnations.len() >= MAX_INCARNATIONS {
            return Err(invalid("Notes reopen requires a fresh bounded incarnation"));
        }
        // An interrupted pre-rename file is never promoted to committed state.
        match open_named(&directory, PENDING, libc::O_RDONLY, 0) {
            Ok(file) => {
                check_private_file(&file)?;
                unlink(&directory, PENDING)?;
                directory.sync_all()?;
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
        state.active_target = target.clone();
        state.incarnations.push(target);
        let mut store = Self {
            directory,
            lock,
            state: state.clone(),
            poisoned: false,
        };
        store.commit(state, false)?;
        Ok(store)
    }

    pub fn text(&self) -> &str {
        &self.state.text
    }
    pub fn revision(&self) -> u64 {
        self.state.revision
    }
    pub fn document_id(&self) -> &str {
        &self.state.document_id
    }
    pub fn target(&self) -> &NotesTargetIdentity {
        &self.state.active_target
    }
    pub fn is_poisoned(&self) -> bool {
        self.poisoned
    }

    pub fn apply_exact(&mut self, raw: &[u8]) -> io::Result<NotesResponse> {
        self.healthy()?;
        let request = NotesReplace::parse_exact(raw).map_err(protocol)?;
        let digest = sha256_hex(raw);
        let response = |result| NotesResponse {
            schema_version: NOTES_SCHEMA_VERSION,
            target: self.state.active_target.clone(),
            operation_id: request.operation_id.clone(),
            payload_sha256: digest.clone(),
            result,
        };
        let refusal = |reason| {
            response(NotesResult::NotApplied {
                reason,
                current_revision: self.state.revision,
            })
        };
        if request.target != self.state.active_target {
            return Ok(refusal(NotesNotAppliedReason::TargetMismatch));
        }
        if let Some(old) = self.state.receipts.iter().find(|receipt| {
            receipt.response.target == request.target
                && receipt.response.operation_id == request.operation_id
        }) {
            return Ok(if old.response.payload_sha256 == digest {
                old.response.clone()
            } else {
                refusal(NotesNotAppliedReason::OperationConflict)
            });
        }
        if request.expected_revision != self.state.revision {
            return Ok(refusal(NotesNotAppliedReason::RevisionConflict));
        }
        let Some(revision) = self.state.revision.checked_add(1) else {
            return Ok(refusal(NotesNotAppliedReason::RevisionExhausted));
        };
        if self.state.receipts.len() >= MAX_RECEIPTS {
            return Ok(refusal(NotesNotAppliedReason::ReceiptPending));
        }
        let applied = response(NotesResult::Applied {
            previous_revision: self.state.revision,
            revision,
            text_sha256: sha256_hex(request.text.as_bytes()),
        });
        let mut next = self.state.clone();
        next.text = request.text;
        next.revision = revision;
        next.receipts.push(StoredReceipt {
            response: applied.clone(),
            exact_utf8: serde_json::to_string(&applied).map_err(io::Error::other)?,
        });
        self.commit(next, false)?;
        Ok(applied)
    }

    pub fn local_edit(&mut self, text: String) -> io::Result<()> {
        self.healthy()?;
        if text.len() > MAX_NOTES_TEXT_BYTES {
            return Err(protocol(NotesProtocolError::TextBound));
        }
        if text != self.state.text {
            let mut next = self.state.clone();
            next.revision = next
                .revision
                .checked_add(1)
                .ok_or_else(|| invalid("Notes revision exhausted"))?;
            next.text = text;
            self.commit(next, false)?;
        }
        Ok(())
    }

    /// Recovery never executes effects and returns the exact original target.
    /// A missing receipt is Unknown, including after application retirement.
    pub fn observe(&self, query: &NotesObserve) -> io::Result<NotesResponse> {
        self.healthy()?;
        query.validate().map_err(protocol)?;
        if let Some(receipt) = self.state.receipts.iter().find(|receipt| {
            receipt
                .response
                .matches(&query.target, &query.operation_id, &query.payload_sha256)
        }) {
            return Ok(receipt.response.clone());
        }
        Ok(NotesResponse {
            schema_version: 1,
            target: query.target.clone(),
            operation_id: query.operation_id.clone(),
            payload_sha256: query.payload_sha256.clone(),
            result: NotesResult::Unknown {
                current_revision: self.state.revision,
            },
        })
    }

    pub fn apply_exact_bytes(&mut self, raw: &[u8]) -> io::Result<Vec<u8>> {
        let response = self.apply_exact(raw)?;
        self.exact_response(response)
    }

    pub fn observe_exact_bytes(&self, raw: &[u8]) -> io::Result<Vec<u8>> {
        let query = NotesObserve::parse_exact(raw).map_err(protocol)?;
        let response = self.observe(&query)?;
        self.exact_response(response)
    }

    fn exact_response(&self, response: NotesResponse) -> io::Result<Vec<u8>> {
        if let Some(stored) = self
            .state
            .receipts
            .iter()
            .find(|stored| stored.response == response)
        {
            Ok(stored.exact_utf8.as_bytes().to_vec())
        } else {
            serde_json::to_vec(&response).map_err(io::Error::other)
        }
    }

    /// This private acknowledgement only releases the application's retained
    /// receipt. The caller is the existing Hepta owner after its durable terminal.
    /// It does not authorise a mutation or assert Hepta's journal durability.
    pub fn acknowledge_exact_bytes(&mut self, raw: &[u8]) -> io::Result<Vec<u8>> {
        self.healthy()?;
        if raw.is_empty() || raw.len() > MAX_NOTES_REQUEST_BYTES {
            return Err(invalid("Notes ACK bound"));
        }
        let ack: Acknowledge = serde_json::from_slice(raw).map_err(io::Error::other)?;
        let _ = ack.action;
        ack.target.validate().map_err(protocol)?;
        if ack.schema_version != 1
            || !valid_operation_id(&ack.operation_id)
            || !lower_hex(&ack.payload_sha256, 64)
            || !lower_hex(&ack.receipt_sha256, 64)
        {
            return Err(invalid("Notes terminal acknowledgement binding"));
        }
        let matches = |old: &RetiredReceipt| {
            old.target == ack.target
                && old.operation_id == ack.operation_id
                && old.payload_sha256 == ack.payload_sha256
                && old.receipt_sha256 == ack.receipt_sha256
        };
        let status = if self.state.retired.as_ref().is_some_and(matches) {
            "already_released"
        } else if self.state.receipts.iter().any(|stored| {
            stored
                .response
                .matches(&ack.target, &ack.operation_id, &ack.payload_sha256)
                && sha256_hex(stored.exact_utf8.as_bytes()) == ack.receipt_sha256
        }) {
            let mut next = self.state.clone();
            next.receipts.clear();
            next.retired = Some(RetiredReceipt {
                target: ack.target.clone(),
                operation_id: ack.operation_id.clone(),
                payload_sha256: ack.payload_sha256.clone(),
                receipt_sha256: ack.receipt_sha256.clone(),
            });
            self.commit(next, false)?;
            "released"
        } else {
            "unknown"
        };
        serde_json::to_vec(&Acknowledgement {
            schema_version: 1,
            target: &ack.target,
            operation_id: &ack.operation_id,
            payload_sha256: &ack.payload_sha256,
            receipt_sha256: &ack.receipt_sha256,
            status,
        })
        .map_err(io::Error::other)
    }

    pub fn read_document_state(&self, raw: &[u8]) -> io::Result<Vec<u8>> {
        self.healthy()?;
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct Query {
            schema_version: u16,
            action: Action,
            target: NotesTargetIdentity,
            request_id: String,
        }
        #[derive(Deserialize)]
        #[serde(rename_all = "snake_case")]
        enum Action {
            ReadDocumentState,
        }
        if raw.is_empty() || raw.len() > MAX_NOTES_REQUEST_BYTES {
            return Err(invalid("document query bound"));
        }
        let query: Query = serde_json::from_slice(raw).map_err(io::Error::other)?;
        let _ = query.action;
        if query.schema_version != 1
            || query.target != self.state.active_target
            || !lower_hex(&query.request_id, 32)
        {
            return Err(invalid("document state query identity"));
        }
        serde_json::to_vec(
            &serde_json::json!({ "schema_version": 1, "action": "document_state",
            "target": query.target, "request_id": query.request_id, "revision": self.state.revision,
            "text_sha256": sha256_hex(self.state.text.as_bytes()) }),
        )
        .map_err(io::Error::other)
    }

    fn healthy(&self) -> io::Result<()> {
        if self.poisoned {
            Err(io::Error::other(
                "Notes persistence outcome unknown; reopen required",
            ))
        } else {
            Ok(())
        }
    }

    fn commit(&mut self, next: State, initial: bool) -> io::Result<()> {
        self.healthy()?;
        let result = self.commit_inner(&next, initial);
        match result {
            Ok(()) => {
                self.state = next;
                Ok(())
            }
            Err(error) => {
                self.poisoned = true;
                Err(error)
            }
        }
    }

    fn commit_inner(&self, next: &State, initial: bool) -> io::Result<()> {
        next.validate()?;
        check_private_dir(&self.directory)?;
        check_private_file(&self.lock)?;
        let current_lock = open_named(&self.directory, LOCK, libc::O_RDONLY, 0)?;
        let a = self.lock.metadata()?;
        let b = current_lock.metadata()?;
        if a.dev() != b.dev() || a.ino() != b.ino() {
            return Err(invalid("Notes writer lock replaced"));
        }
        if !initial {
            check_private_file(&open_named(&self.directory, STATE, libc::O_RDONLY, 0)?)?;
        }
        let raw = serde_json::to_vec(next).map_err(io::Error::other)?;
        if raw.len() as u64 > MAX_STATE_BYTES {
            return Err(invalid("Notes persisted state too large"));
        }
        let mut pending = open_named(
            &self.directory,
            PENDING,
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,
            0o600,
        )?;
        pending.write_all(&raw)?;
        pending.sync_all()?;
        checkpoint("file_synced");
        let from = CString::new(PENDING).unwrap();
        let to = CString::new(STATE).unwrap();
        if unsafe {
            libc::renameat(
                self.directory.as_raw_fd(),
                from.as_ptr(),
                self.directory.as_raw_fd(),
                to.as_ptr(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error());
        }
        checkpoint("renamed");
        self.directory.sync_all()?;
        checkpoint("directory_synced");
        Ok(())
    }
}

/// Creates missing private ancestors with descriptor-relative operations.
/// Existing symlinks and dot/dotdot components are rejected at every level.
/// The final directory must be 0700 and owned by the effective user.
pub fn ensure_private_directory(path: &Path) -> io::Result<()> {
    let directory = open_directory(path, true)?;
    check_private_dir(&directory)
}

fn open_directory(path: &Path, create: bool) -> io::Result<File> {
    if !path.is_absolute() {
        return Err(invalid("Notes storage path must be absolute"));
    }
    let mut directory = File::open("/")?;
    for component in path.components() {
        let Component::Normal(name) = component else {
            if component == Component::RootDir {
                continue;
            }
            return Err(invalid("Notes path components"));
        };
        let name = CString::new(name.as_bytes()).map_err(|_| invalid("Notes path NUL"))?;
        let next = match openat(
            directory.as_raw_fd(),
            &name,
            libc::O_RDONLY | libc::O_DIRECTORY,
            0,
        ) {
            Ok(next) => next,
            Err(error) if create && error.kind() == io::ErrorKind::NotFound => {
                if unsafe { libc::mkdirat(directory.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
                    return Err(io::Error::last_os_error());
                }
                directory.sync_all()?;
                openat(
                    directory.as_raw_fd(),
                    &name,
                    libc::O_RDONLY | libc::O_DIRECTORY,
                    0,
                )?
            }
            Err(error) => return Err(error),
        };
        directory = next;
    }
    Ok(directory)
}

fn openat(dir: i32, name: &CString, flags: i32, mode: u32) -> io::Result<File> {
    let fd = unsafe {
        libc::openat(
            dir,
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            mode,
        )
    };
    if fd < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
fn open_named(dir: &File, name: &str, flags: i32, mode: u32) -> io::Result<File> {
    openat(dir.as_raw_fd(), &CString::new(name).unwrap(), flags, mode)
}
fn open_lock(directory: &File, create: bool) -> io::Result<File> {
    let flags = libc::O_RDWR
        | if create {
            libc::O_CREAT | libc::O_EXCL
        } else {
            0
        };
    let lock = open_named(directory, LOCK, flags, 0o600)?;
    check_private_file(&lock)?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(lock)
}
fn check_private_dir(file: &File) -> io::Result<()> {
    let m = file.metadata()?;
    if !m.is_dir() || m.mode() & 0o777 != 0o700 || m.uid() != unsafe { libc::geteuid() } {
        return Err(invalid("Notes directory must be owned private 0700"));
    }
    Ok(())
}
fn check_private_file(file: &File) -> io::Result<()> {
    let m = file.metadata()?;
    if !m.is_file()
        || m.mode() & 0o777 != 0o600
        || m.nlink() != 1
        || m.uid() != unsafe { libc::geteuid() }
    {
        return Err(invalid(
            "Notes state/lock must be private owned regular single-link 0600",
        ));
    }
    Ok(())
}
fn unlink(directory: &File, name: &str) -> io::Result<()> {
    if unsafe {
        libc::unlinkat(
            directory.as_raw_fd(),
            CString::new(name).unwrap().as_ptr(),
            0,
        )
    } != 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}
fn protocol(error: NotesProtocolError) -> io::Error {
    invalid(&format!("Notes protocol: {error:?}"))
}
fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.to_owned())
}

#[cfg(not(test))]
fn checkpoint(_: &str) {}
#[cfg(test)]
fn checkpoint(stage: &str) {
    if std::env::var("TRILL_TEST_NOTES_CRASH_STAGE")
        .ok()
        .as_deref()
        == Some(stage)
    {
        println!("NOTES_CHECKPOINT:{stage}");
        io::stdout().flush().unwrap();
        loop {
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{symlink, PermissionsExt};
    use std::path::PathBuf;
    use std::process::{Command, Stdio};
    use std::time::Duration;

    fn target(seed: char) -> NotesTargetIdentity {
        NotesTargetIdentity {
            session_instance: seed.to_string().repeat(32),
            task_id: 1,
            incarnation: seed.to_string().repeat(32),
        }
    }
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let mut random = [0u8; 8];
            File::open("/dev/urandom")
                .unwrap()
                .read_exact(&mut random)
                .unwrap();
            let root =
                std::env::temp_dir().join(format!("notes-store-{}", u64::from_ne_bytes(random)));
            std::fs::create_dir(&root).unwrap();
            std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700)).unwrap();
            Self(root)
        }
        fn doc(&self) -> PathBuf {
            self.0.join("document")
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    fn request(target: NotesTargetIdentity, op: &str, revision: u64, text: &str) -> Vec<u8> {
        serde_json::to_vec(&NotesReplace {
            schema_version: 1,
            action: NotesReplaceAction::ReplaceNote,
            operation_id: op.into(),
            destination_id: target.destination_id(),
            target,
            expected_revision: revision,
            text: text.into(),
        })
        .unwrap()
    }
    fn query(target: NotesTargetIdentity, op: &str, payload: &[u8]) -> Vec<u8> {
        serde_json::to_vec(&NotesObserve {
            schema_version: 1,
            action: NotesObserveAction::Observe,
            target,
            operation_id: op.into(),
            payload_sha256: sha256_hex(payload),
        })
        .unwrap()
    }
    fn ack(target: NotesTargetIdentity, op: &str, payload: &[u8], receipt: &[u8]) -> Vec<u8> {
        serde_json::to_vec(
            &serde_json::json!({"schema_version":1,"action":"acknowledge_terminal",
            "target":target,"operation_id":op,"payload_sha256":sha256_hex(payload),
            "receipt_sha256":sha256_hex(receipt)}),
        )
        .unwrap()
    }

    #[test]
    fn fixed_recovery_golden_drives_real_store_and_exact_receipt_retirement() {
        let wire: serde_json::Value =
            serde_json::from_str(include_str!("../../../../tests/ui/notes-recovery-v1.json"))
                .unwrap();
        let bytes = |key: &str| wire[key].as_str().unwrap().as_bytes();
        let request = NotesReplace::parse_exact(bytes("request_utf8")).unwrap();
        let observe = NotesObserve::parse_exact(bytes("observe_utf8")).unwrap();
        assert_eq!(serde_json::to_vec(&observe).unwrap(), bytes("observe_utf8"));
        assert_eq!(observe.target, request.target);
        assert_eq!(observe.operation_id, request.operation_id);
        assert_eq!(sha256_hex(bytes("request_utf8")), wire["payload_sha256"]);

        let fixture = Fixture::new();
        let mut store = DurableNotes::create(&fixture.doc(), request.target.clone()).unwrap();
        let receipt = store.apply_exact_bytes(bytes("request_utf8")).unwrap();
        assert_eq!(receipt, bytes("application_response_utf8"));
        assert_eq!(sha256_hex(&receipt), wire["receipt_sha256"]);
        assert_eq!(
            store.apply_exact_bytes(bytes("request_utf8")).unwrap(),
            receipt
        );
        assert_eq!(
            store.observe_exact_bytes(bytes("observe_utf8")).unwrap(),
            receipt
        );
        assert_eq!(
            store
                .read_document_state(bytes("read_document_state_utf8"))
                .unwrap(),
            bytes("document_state_utf8")
        );

        let reformatted = bytes("reformatted_application_response_utf8");
        assert_eq!(
            NotesResponse::parse_exact(reformatted).unwrap(),
            NotesResponse::parse_exact(&receipt).unwrap()
        );
        assert_eq!(sha256_hex(reformatted), wire["reformatted_receipt_sha256"]);
        assert_ne!(sha256_hex(reformatted), sha256_hex(&receipt));
        let mut wrong_ack: serde_json::Value =
            serde_json::from_slice(bytes("acknowledge_utf8")).unwrap();
        wrong_ack["receipt_sha256"] = wire["reformatted_receipt_sha256"].clone();
        let wrong_reply: serde_json::Value = serde_json::from_slice(
            &store
                .acknowledge_exact_bytes(&serde_json::to_vec(&wrong_ack).unwrap())
                .unwrap(),
        )
        .unwrap();
        assert_eq!(wrong_reply["status"], "unknown");
        assert_eq!(
            store.observe_exact_bytes(bytes("observe_utf8")).unwrap(),
            receipt
        );
        assert_eq!(
            store
                .acknowledge_exact_bytes(bytes("acknowledge_utf8"))
                .unwrap(),
            bytes("released_utf8")
        );
        assert_eq!(
            store
                .acknowledge_exact_bytes(bytes("acknowledge_utf8"))
                .unwrap(),
            bytes("already_released_utf8")
        );
        assert_eq!(
            store.observe_exact_bytes(bytes("observe_utf8")).unwrap(),
            bytes("unknown_observation_utf8")
        );
        assert_eq!(
            store
                .read_document_state(bytes("read_document_state_utf8"))
                .unwrap(),
            bytes("document_state_utf8")
        );

        let query = wire["read_document_state_utf8"].as_str().unwrap();
        for invalid in [
            query.replacen('{', "{\"schema_version\":1,", 1),
            query.replacen('{', "{\"text\":\"forbidden\",", 1),
            query.replace(&"3".repeat(32), &"G".repeat(32)),
            query.replace(&"2".repeat(32), &"4".repeat(32)),
        ] {
            assert!(store.read_document_state(invalid.as_bytes()).is_err());
        }
        assert!(store
            .acknowledge_exact_bytes(bytes("request_utf8"))
            .is_err());
        assert!(store.observe_exact_bytes(bytes("request_utf8")).is_err());
    }

    #[test]
    fn persistence_reopen_retains_text_revision_exact_receipt_and_fences_old_effect() {
        const TEST: &str = "notes::persistence::tests::persistence_reopen_retains_text_revision_exact_receipt_and_fences_old_effect";
        const CHILD_PARENT: &str = "TRILL_TEST_NOTES_REOPEN_PARENT_PID";
        if let Some(parent) = std::env::var_os(CHILD_PARENT) {
            let parent = parent.to_str().unwrap().parse::<u32>().unwrap();
            assert_eq!(
                parent,
                unsafe { libc::getppid() } as u32,
                "the isolated body must be executed by its waiting test parent"
            );
            assert_ne!(parent, std::process::id());
            eprintln!(
                "NOTES_REOPEN_ISOLATED parent={parent} child={}",
                std::process::id()
            );
        } else {
            // A concurrently spawned crash-test child can temporarily inherit
            // another test's CLOEXEC lock before exec. This parent owns no
            // writer: only its exec-complete exact-test child opens this fixture.
            // Keep every original reopen/fencing assertion in that child rather
            // than serializing unrelated tests or retrying a refused lock.
            let child = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", TEST, "--nocapture", "--test-threads=1"])
                .env(CHILD_PARENT, std::process::id().to_string())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .unwrap();
            let child_id = child.id();
            let output = child.wait_with_output().unwrap();
            let stdout = String::from_utf8_lossy(&output.stdout);
            let stderr = String::from_utf8_lossy(&output.stderr);
            assert!(output.status.success(), "{stdout}\n{stderr}");
            assert_eq!(
                stdout.matches(&format!("test {TEST} ... ok")).count(),
                1,
                "{stdout}"
            );
            assert_eq!(
                stdout
                    .matches("test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured;")
                    .count(),
                1,
                "{stdout}"
            );
            let identity = format!(
                "NOTES_REOPEN_ISOLATED parent={} child={child_id}",
                std::process::id()
            );
            assert_eq!(
                stderr.lines().filter(|line| *line == identity).count(),
                1,
                "{stderr}"
            );
            eprintln!("{identity}");
            return;
        }
        let fixture = Fixture::new();
        let payload = request(target('a'), "first", 0, "persistent 中文");
        let mut store = DurableNotes::create(&fixture.doc(), target('a')).unwrap();
        let document_id = store.document_id().to_owned();
        let receipt = store.apply_exact_bytes(&payload).unwrap();
        assert_eq!(store.apply_exact_bytes(&payload).unwrap(), receipt);
        assert_eq!(store.revision(), 1);
        drop(store);
        assert!(DurableNotes::reopen(&fixture.doc(), target('a')).is_err());
        let mut store = DurableNotes::reopen(&fixture.doc(), target('b')).unwrap();
        assert_eq!(store.document_id(), document_id);
        assert_eq!(store.text(), "persistent 中文");
        assert_eq!(store.revision(), 1);
        assert_eq!(
            store
                .observe_exact_bytes(&query(target('a'), "first", &payload))
                .unwrap(),
            receipt
        );
        let refused = store.apply_exact(&payload).unwrap();
        assert!(matches!(
            refused.result,
            NotesResult::NotApplied {
                reason: NotesNotAppliedReason::TargetMismatch,
                ..
            }
        ));
        let next = request(target('b'), "next", 1, "second");
        assert!(matches!(
            store.apply_exact(&next).unwrap().result,
            NotesResult::NotApplied {
                reason: NotesNotAppliedReason::ReceiptPending,
                ..
            }
        ));
        let ack = ack(target('a'), "first", &payload, &receipt);
        assert!(
            String::from_utf8(store.acknowledge_exact_bytes(&ack).unwrap())
                .unwrap()
                .contains("released")
        );
        drop(store);
        let mut store = DurableNotes::reopen(&fixture.doc(), target('c')).unwrap();
        assert!(
            String::from_utf8(store.acknowledge_exact_bytes(&ack).unwrap())
                .unwrap()
                .contains("already_released")
        );
        let next = request(target('c'), "next", 1, "second");
        assert!(matches!(
            store.apply_exact(&next).unwrap().result,
            NotesResult::Applied { revision: 2, .. }
        ));
    }

    #[test]
    fn local_edits_persist_and_cas_and_wrong_ack_cannot_discard_receipt() {
        let fixture = Fixture::new();
        let mut store = DurableNotes::create(&fixture.doc(), target('a')).unwrap();
        store.local_edit("local user".into()).unwrap();
        let stale = request(target('a'), "stale", 0, "overwrite");
        assert!(matches!(
            store.apply_exact(&stale).unwrap().result,
            NotesResult::NotApplied {
                reason: NotesNotAppliedReason::RevisionConflict,
                ..
            }
        ));
        let raw = request(target('a'), "first", 1, "authorised");
        let receipt = store.apply_exact_bytes(&raw).unwrap();
        store.local_edit("later user".into()).unwrap();
        let wrong = ack(target('a'), "first", &raw, b"wrong bytes");
        assert!(
            String::from_utf8(store.acknowledge_exact_bytes(&wrong).unwrap())
                .unwrap()
                .contains("unknown")
        );
        drop(store);
        let store = DurableNotes::reopen(&fixture.doc(), target('b')).unwrap();
        assert_eq!(store.text(), "later user");
        assert_eq!(store.revision(), 3);
        assert_eq!(
            store
                .observe_exact_bytes(&query(target('a'), "first", &raw))
                .unwrap(),
            receipt
        );
    }

    #[test]
    fn filesystem_aliases_unsafe_modes_second_writer_and_corruption_are_refused() {
        let fixture = Fixture::new();
        let store = DurableNotes::create(&fixture.doc(), target('a')).unwrap();
        assert!(DurableNotes::create(&fixture.doc(), target('b')).is_err());
        assert!(DurableNotes::reopen(&fixture.doc(), target('b')).is_err());
        let alias = fixture.0.join("alias");
        symlink(fixture.doc(), &alias).unwrap();
        assert!(DurableNotes::reopen(&alias, target('b')).is_err());
        drop(store);
        std::fs::set_permissions(
            fixture.doc().join(STATE),
            std::fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        assert!(DurableNotes::reopen(&fixture.doc(), target('b')).is_err());
        std::fs::set_permissions(
            fixture.doc().join(STATE),
            std::fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        std::fs::hard_link(fixture.doc().join(STATE), fixture.0.join("hard")).unwrap();
        assert!(DurableNotes::reopen(&fixture.doc(), target('b')).is_err());
        std::fs::remove_file(fixture.0.join("hard")).unwrap();
        std::fs::write(fixture.doc().join(STATE), b"{truncated").unwrap();
        assert!(DurableNotes::reopen(&fixture.doc(), target('b')).is_err());
    }

    #[test]
    fn lock_replacement_poisoned_writer_cannot_ack_an_effect() {
        let fixture = Fixture::new();
        let mut store = DurableNotes::create(&fixture.doc(), target('a')).unwrap();
        std::fs::remove_file(fixture.doc().join(LOCK)).unwrap();
        let raw = request(target('a'), "first", 0, "must not apply");
        assert!(store.apply_exact_bytes(&raw).is_err());
        assert!(store.is_poisoned());
        assert_eq!(store.revision(), 0);
        assert!(store
            .observe_exact_bytes(&query(target('a'), "first", &raw))
            .is_err());
    }

    #[test]
    fn kill_between_atomic_write_stages_never_separates_receipt_from_document() {
        use std::io::BufRead;
        if let Some(path) = std::env::var_os("TRILL_TEST_NOTES_CRASH_PATH") {
            let mut store = DurableNotes::reopen(Path::new(&path), target('b')).unwrap();
            let stage = std::env::var("TRILL_TEST_NOTES_ARM_STAGE").unwrap();
            std::env::set_var("TRILL_TEST_NOTES_CRASH_STAGE", stage);
            store
                .apply_exact_bytes(&request(target('b'), "crash", 0, "durable after kill"))
                .unwrap();
            panic!("checkpoint must wait for parent kill");
        }
        for stage in ["file_synced", "renamed", "directory_synced"] {
            let fixture = Fixture::new();
            drop(DurableNotes::create(&fixture.doc(), target('a')).unwrap());
            let mut child = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "notes::persistence::tests::kill_between_atomic_write_stages_never_separates_receipt_from_document", "--nocapture"])
                .env("TRILL_TEST_NOTES_CRASH_PATH", fixture.doc())
                .env("TRILL_TEST_NOTES_ARM_STAGE", stage)
                .stdout(Stdio::piped()).stderr(Stdio::inherit()).spawn().unwrap();
            let stdout = child.stdout.take().unwrap();
            let (tx, rx) = std::sync::mpsc::channel();
            let reader = std::thread::spawn(move || {
                for line in io::BufReader::new(stdout).lines().map_while(Result::ok) {
                    if line.starts_with("NOTES_CHECKPOINT:") {
                        let _ = tx.send(line);
                        break;
                    }
                }
            });
            let observed = rx.recv_timeout(Duration::from_secs(5));
            let _ = child.kill();
            let status = child.wait().unwrap();
            reader.join().unwrap();
            assert!(!status.success());
            assert!(observed.unwrap().ends_with(stage));
            let store = DurableNotes::reopen(&fixture.doc(), target('c')).unwrap();
            let raw = request(target('b'), "crash", 0, "durable after kill");
            let response = store
                .observe_exact_bytes(&query(target('b'), "crash", &raw))
                .unwrap();
            let response = NotesResponse::parse_exact(&response).unwrap();
            if stage == "file_synced" {
                assert_eq!(store.text(), "");
                assert_eq!(store.revision(), 0);
                assert!(matches!(response.result, NotesResult::Unknown { .. }));
            } else {
                assert_eq!(store.text(), "durable after kill");
                assert_eq!(store.revision(), 1);
                assert!(matches!(
                    response.result,
                    NotesResult::Applied { revision: 1, .. }
                ));
            }
        }
    }
}
