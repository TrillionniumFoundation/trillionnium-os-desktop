//! Source-owned repeat/soak observations inside one actual native UI session.
//!
//! Three fresh normal Engine checks and complete native dumps, at least fifteen
//! seconds apart, share the original Main, PM token, App PIDFD and deadline.
//! Closing the owned task and the original final bookends are prerequisites;
//! saved JSON, a duration, or a caller-selected sample can never mint this type.
use super::*;
use crate::application_exit_state::ApplicationExitRecord;
use crate::control::{ActualApplicationExitObservation, application_probe::ApplicationInspection};
#[path = "native_application_ui_common_resources.rs"]
mod resources;
use resources::{ResourceFence, ResourceSample};

const SAMPLES: usize = 3;
const GAP: Duration = Duration::from_secs(15);
const EXIT_CAP: Duration = Duration::from_secs(70);
const ENGINE_CAP: Duration = Duration::from_secs(70);
const STACK_CAP: Duration = Duration::from_secs(15);
const MAX_JOURNAL_BYTES: u64 = 128 * 1024 * 1024;
const MAX_JOURNAL_FILES: usize = 4096;
// These three binary name forms are emitted only by the fixed source-owned
// image producers. Retention does not decode pixels or mint media authority.
const MAX_FIXED_IMAGE_BYTES: u64 = 32 * 1024 * 1024;
fn retained_member_limit(name: &str) -> u64 {
    let numbered_image = name.as_bytes().get(..4).is_some_and(|prefix| {
        prefix.iter().all(u8::is_ascii_digit)
            && matches!(name.get(4..), Some("-stdout.bin" | "-scoped-source.png"))
    });
    if name == "CAMERA-OWNED-PHOTO.jpg" || numbered_image {
        MAX_FIXED_IMAGE_BYTES
    } else {
        wire::WIRE_REPLY_BYTES as u64
    }
}

/// Additional source-owned allowance when a caller budgets a shared session.
/// It never creates a deadline or extends an existing case/lease. The two exit
/// queries, three Engine+dump+task checks and two minimum gaps are explicit.
pub fn stability_additional_window_seconds() -> u64 {
    2 * EXIT_CAP.as_secs()
        + SAMPLES as u64 * (ENGINE_CAP + COMMAND_CAP + 2 * STACK_CAP).as_secs()
        + (SAMPLES as u64 - 1) * GAP.as_secs()
}
#[derive(Debug, Serialize)]
pub struct NativeUiStabilitySummary {
    schema: &'static str,
    package: String,
    actual_uid: u32,
    task: u32,
    application_host_pid: u32,
    application_start_ticks: u64,
    sample_count: usize,
    minimum_gap_milliseconds: u64,
    actual_elapsed_milliseconds: u64,
    sample_offsets_milliseconds: Vec<u64>,
    native_dump_sha256: Vec<String>,
    before_exit_records_sha256: String,
    after_exit_records_sha256: String,
    before_resource: ResourceSample,
    samples_resource: Vec<ResourceSample>,
    after_resource: ResourceSample,
    complete_exact_uid_exit_records_unchanged: bool,
    original_process_pidfd_held_through_reviewed_window: bool,
    normal_owned_task_close_and_final_bookends: bool,
    other_tasks_preserved: bool,
    all_actual_queries_retired: bool,
    original_deadline_extended: bool,
    independent_reopen_inferred: bool,
    data_permissions_or_accounts_inferred: bool,
    whole_application_accepted: bool,
}
struct Sample {
    at: Instant,
    dump_sha256: String,
    resources: ResourceSample,
}
/// Live single-session recorder. Construction and each sample require the real
/// session; neither public fields nor a deserializer expose its state.
pub struct NativeUiStabilityWindow {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    journal: PathBuf,
    journal_identity: [u64; 5],
    task: u32,
    end: Instant,
    work_end: Instant,
    before: ActualApplicationExitObservation,
    resources: ResourceFence,
    initial_resources: ResourceSample,
    samples: Vec<Sample>,
    failed: bool,
}
struct JournalFile {
    name: String,
    file: File,
    identity: Identity,
    sha256: String,
}
pub(super) struct RetainedJournal {
    files: Vec<JournalFile>,
    directory_identity: [u64; 5],
    names: BTreeSet<String>,
}
fn full_hash(file: &File, count: u64) -> Result<String, String> {
    let mut hash = Sha256::new();
    let mut offset = 0;
    while offset < count {
        let mut buffer = [0_u8; 65536];
        let wanted = usize::try_from((count - offset).min(buffer.len() as u64))
            .map_err(|_| "native common journal length overflow")?;
        let n = file
            .read_at(&mut buffer[..wanted], offset)
            .map_err(|e| e.to_string())?;
        need(n > 0, "native common retained journal was truncated")?;
        hash.update(&buffer[..n]);
        offset += n as u64;
    }
    let mut extra = [0_u8; 1];
    need(
        file.read_at(&mut extra, count).map_err(|e| e.to_string())? == 0,
        "native common retained journal grew",
    )?;
    Ok(format!("{:x}", hash.finalize()))
}
fn names(journal: &Journal) -> Result<BTreeSet<String>, String> {
    journal.verify()?;
    let mut result = BTreeSet::new();
    for row in fs::read_dir(&journal.path).map_err(|e| e.to_string())? {
        let row = row.map_err(|e| e.to_string())?;
        let name = row
            .file_name()
            .into_string()
            .map_err(|_| "native journal name is not UTF-8")?;
        need(
            !name.is_empty()
                && name.len() <= 128
                && name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
                && result.len() < MAX_JOURNAL_FILES
                && result.insert(name),
            "native common journal has a duplicate, malformed or excessive member",
        )?;
    }
    journal.verify()?;
    Ok(result)
}

// Only the source-owned constructors select the required member set.
// No caller can supply a schema, list of names, passed map or copied transcript.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum JournalKind { Finished, Stability, Permissions }
fn required_members(kind: JournalKind) -> &'static [&'static str] {
    match kind {
        JournalKind::Finished => &[
            "BASELINE.json","LAUNCH-INTENT.json","LAUNCH-RESULT.json","OWNED-TASK.json",
            "CLEANUP-INTENT.json","CLEANUP-COMPLETE.json","FINISHED.json",
        ],
        JournalKind::Stability => &[
            "BASELINE.json","OWNED-TASK.json","FINISHED.json","STABILITY-BEGIN.json",
            "STABILITY-SAMPLE-1.json","STABILITY-SAMPLE-2.json","STABILITY-SAMPLE-3.json",
            "STABILITY-AFTER-CLOSE.json",
        ],
        JournalKind::Permissions => &[
            "PERMISSION-BEGIN.json", "PERMISSION-BEFORE.json",
            "PERMISSION-AFTER.json", "PERMISSION-COMPLETE.json",
        ],
    }
}
fn require_members(kind: JournalKind, names: &BTreeSet<String>) -> Result<(), String> {
    need(required_members(kind).iter().all(|name| names.contains(*name))
        && (kind != JournalKind::Permissions || names.len() == required_members(kind).len()),
        "actual native finished/stability/permission journal is incomplete or differs")
}

/// Historical close/retirement custody. It is deliberately separate from
/// NativeUiStabilityEvidence: no repeat/soak or business gate is supplied.
pub struct RetainedNativeUiTranscript {
    transcript: NativeUiTranscript,
    journal: RetainedJournal,
}
impl NativeUiTranscript {
    pub fn into_retained(self) -> Result<RetainedNativeUiTranscript, String> {
        before(self.original_end)?;
        let journal = RetainedJournal::capture(
            &self.journal_custody, self.original_end, JournalKind::Finished,
        )?;
        let result = RetainedNativeUiTranscript { transcript: self, journal };
        result.guard_immutable()?;
        before(result.transcript.original_end)?;
        Ok(result)
    }
}
impl RetainedNativeUiTranscript {
    pub fn transcript(&self) -> &NativeUiTranscript { &self.transcript }
    pub fn guard_immutable(&self) -> Result<(), String> {
        self.journal.guard(&self.transcript.journal_custody)
    }
    pub fn require_subject(
        &self, main: &RuntimeMainCustody, application: &ApplicationInspection,
    ) -> Result<(), String> {
        need(
            self.transcript.engine().facts().main == *main
                && self.transcript.engine().application() == application,
            "finished native transcript has another actual Main or complete application identity",
        )?;
        self.guard_immutable()
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        Ok(serde_json::json!({
            "schema":"droidloom.native-ui-retained-finished.v1",
            "main":self.transcript.engine().facts().main,
            "application":self.transcript.engine().application(),
            "task":self.transcript.task(),"journal":self.transcript.journal(),
            "journal_identity":self.journal.directory_identity,
            "operations":self.transcript.operations(),"actions":self.transcript.actions(),
            "retained_members":self.journal.files.len(),
            "normal_owned_close_and_full_bookends_completed":true,
            "source_result_fds_retained":true,"live_execution_authority_retained":false,
            "stability_or_business_gate_supplied":false
        }))
    }
}

fn require_generated_permission_records(
    generated: &BTreeMap<String, (u64, String)>,
    actual: &BTreeMap<String, (u64, String)>,
) -> Result<(), String> {
    let names = generated.keys().cloned().collect();
    require_members(JournalKind::Permissions, &names)?;
    need(generated.values().all(|(bytes, sha)| *bytes > 0
        && *bytes <= crate::application_permission_state::MAX_WIRE_BYTES as u64
        && sha.len() == 64
        && sha.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
        && generated == actual,
        "PM permission retained records differ from the actual factory's generated full bytes")
}

impl RetainedJournal {
    pub(super) fn require_generated_permission_records(
        &self, generated: &BTreeMap<String, (u64, String)>,
    ) -> Result<(), String> {
        let actual = self.files.iter().map(|held|
            (held.name.clone(), (held.identity.bytes, held.sha256.clone()))).collect();
        require_generated_permission_records(generated, &actual)
    }
    pub(super) fn capture(journal: &Journal, end: Instant, kind: JournalKind) -> Result<Self, String> {
        before(end)?;
        let wanted = names(journal)?;
        require_members(kind, &wanted)?;
        let mut files = Vec::new();
        let mut total = 0_u64;
        for name in &wanted {
            before(end)?;
            let c = CString::new(name.as_str()).map_err(|_| "invalid native journal name")?;
            let file = open_at(
                journal.directory.as_raw_fd(),
                &c,
                libc::O_RDONLY | libc::O_NOFOLLOW,
            )
            .map_err(|e| e.to_string())?;
            let identity = Identity::of(&file.metadata().map_err(|e| e.to_string())?);
            need(
                identity.mode == libc::S_IFREG | 0o600
                    && identity.uid == 0
                    && identity.gid == 0
                    && identity.links == 1
                    && identity.bytes <= retained_member_limit(name),
                "native common journal has a link, wrong owner/mode or oversized member",
            )?;
            total = total
                .checked_add(identity.bytes)
                .ok_or("native journal total overflow")?;
            need(
                total <= MAX_JOURNAL_BYTES,
                "native common journal exceeds its whole retained bound",
            )?;
            let sha256 = full_hash(&file, identity.bytes)?;
            need(
                Identity::of(&file.metadata().map_err(|e| e.to_string())?) == identity,
                "native common journal changed during the complete read",
            )?;
            files.push(JournalFile {
                name: name.clone(),
                file,
                identity,
                sha256,
            });
        }
        let retained = Self {
            files,
            directory_identity: journal.identity,
            names: wanted,
        };
        retained.guard(journal)?;
        before(end)?;
        Ok(retained)
    }
    pub(super) fn guard(&self, journal: &Journal) -> Result<(), String> {
        journal.verify()?;
        need(
            journal.identity == self.directory_identity && names(journal)? == self.names,
            "native common retained journal directory or member set changed",
        )?;
        for held in &self.files {
            let c =
                CString::new(held.name.as_str()).map_err(|_| "invalid retained journal name")?;
            let named = open_at(
                journal.directory.as_raw_fd(),
                &c,
                libc::O_RDONLY | libc::O_NOFOLLOW,
            )
            .map_err(|e| e.to_string())?;
            need(
                Identity::of(&named.metadata().map_err(|e| e.to_string())?) == held.identity
                    && Identity::of(&held.file.metadata().map_err(|e| e.to_string())?)
                        == held.identity
                    && full_hash(&held.file, held.identity.bytes)? == held.sha256,
                "native common journal full bytes or held/named identity changed",
            )?;
        }
        journal.verify()
    }
}
/// Historical successful source-owned observation. The actual kernel, query
/// and task factories created it while the original session deadline held.
/// Immutable guarding later grants no fresh App liveness or execution lease.
pub struct NativeUiStabilityEvidence {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    transcript: NativeUiTranscript,
    journal: RetainedJournal,
    before: ActualApplicationExitObservation,
    after: ActualApplicationExitObservation,
    _resources: ResourceFence,
    summary: NativeUiStabilitySummary,
}
impl NativeUiStabilityEvidence {
    pub fn transcript(&self) -> &NativeUiTranscript {
        &self.transcript
    }
    pub fn summary(&self) -> &NativeUiStabilitySummary {
        &self.summary
    }
    pub fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        need(
            &self.main == main
                && &self.application == application
                && self.transcript.engine().facts().main == *main
                && self.transcript.engine().application() == application,
            "common stability belongs to another Main, package, UID or complete APK identity",
        )?;
        self.guard_immutable()
    }
    pub fn guard_immutable(&self) -> Result<(), String> {
        self.before.facts().require_application(&self.application)?;
        self.after.facts().require_application(&self.application)?;
        unchanged_exit_records(
            self.before.facts().records(),
            self.after.facts().records(),
            self.application.uid,
        )?;
        self.journal.guard(&self.transcript.journal_custody)
    }
}
fn unchanged_exit_records(
    before: &[ApplicationExitRecord],
    after: &[ApplicationExitRecord],
    uid: u32,
) -> Result<(), String> {
    let collect = |records: &[ApplicationExitRecord]| {
        records
            .iter()
            .filter(|record| record.real_uid() == uid || record.package_uid() == uid)
            .map(|record| record.record_sha256().to_string())
            .collect::<BTreeSet<_>>()
    };
    need(
        collect(before) == collect(after),
        "fresh exact-UID exit evidence changed: crash, ANR, self-exit or lost history is not a pass",
    )
}
fn require_cadence(times: &[Instant]) -> Result<(), String> {
    need(
        times.len() == SAMPLES
            && times.windows(2).all(|pair| {
                pair[1]
                    .checked_duration_since(pair[0])
                    .is_some_and(|elapsed| elapsed >= GAP)
            })
            && times[SAMPLES - 1].duration_since(times[0]) >= 2 * GAP,
        "reviewed stability needs exactly three distinct samples at least fifteen seconds apart",
    )
}
impl<'a, 'b> NativeUiSession<'a, 'b> {
    pub fn begin_stability(
        &mut self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<NativeUiStabilityWindow, String> {
        self.guard(inspector, self.work_end)?;
        need(
            !self.poisoned && !self.cleanup_started && !self.stability_started,
            "common stability requires one unused, certain running UI session",
        )?;
        self.stability_started = true;
        // The after-close query consumes this original time; it never gets a
        // new lease or steals the original finish's PM/Main/retirement reserve.
        self.work_end = self
            .work_end
            .checked_sub(EXIT_CAP)
            .filter(|cutoff| *cutoff > Instant::now())
            .ok_or("original UI window cannot reserve the after-close exit query")?;
        let result = (|| -> Result<NativeUiStabilityWindow, String> {
            let task = self
                .task
                .ok_or("common stability lacks the actual owned task")?;
            let engine = self
                .engine
                .as_ref()
                .ok_or("common stability lacks actual running Engine")?;
            let resources = ResourceFence::capture(&engine.facts().process)?;
            let initial_resources = resources.sample(true)?;
            let observed = inspector
                .observe_application_exit_state_until(
                    self.baseline.main(),
                    self.baseline.actual_application(),
                    self.work_end,
                )
                .map_err(|e| e.to_string())?;
            inspector
                .require_exit_state_local(
                    self.baseline.main(),
                    self.baseline.actual_application(),
                    &observed,
                    self.work_end,
                )
                .map_err(|e| e.to_string())?;
            resources.live()?;
            self.guard(inspector, self.work_end)?;
            self.journal.json(
                "STABILITY-BEGIN.json",
                &serde_json::json!({
                    "schema":"droidloom.native-ui-stability-begin.v1",
                    "actual_main":self.baseline.main().facts(),
                    "actual_application":self.baseline.application(),"task":task,
                    "before_exit_state":observed.facts(),"initial_resources":initial_resources,
                    "samples":SAMPLES,"minimum_gap_seconds":GAP.as_secs(),
                    "additional_source_allowance_seconds":stability_additional_window_seconds(),
                    "original_deadline_extended":false,"comparison_only":true
                }),
            )?;
            Ok(NativeUiStabilityWindow {
                main: self.baseline.main().facts().clone(),
                application: self.baseline.application().clone(),
                journal: self.journal.path.clone(),
                journal_identity: self.journal.identity,
                task,
                end: self.end,
                work_end: self.work_end,
                before: observed,
                resources,
                initial_resources,
                samples: Vec::new(),
                failed: false,
            })
        })();
        match result {
            Ok(window) => Ok(window),
            Err(error) => Err(self.observation_failure(inspector, error)),
        }
    }
}
impl NativeUiStabilityWindow {
    fn same_session(&self, session: &NativeUiSession<'_, '_>) -> Result<(), String> {
        need(
            !self.failed
                && session.stability_started
                && !session.poisoned
                && session.end == self.end
                && session.work_end == self.work_end
                && session.journal.path == self.journal
                && session.journal.identity == self.journal_identity
                && session.task == Some(self.task)
                && session.baseline.application() == &self.application
                && session.baseline.main().facts() == &self.main,
            "common stability changed session, owner, task, source application or original deadline",
        )
    }
    pub fn sample(
        &mut self,
        session: &mut NativeUiSession<'_, '_>,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<(), String> {
        let result = (|| -> Result<(), String> {
            self.same_session(session)?;
            need(
                !session.cleanup_started && self.samples.len() < SAMPLES,
                "common stability cannot repeat a sample after completion or cleanup",
            )?;
            if let Some(last) = self.samples.last() {
                let target = last
                    .at
                    .checked_add(GAP)
                    .ok_or("stability sample clock overflow")?;
                need(
                    target < self.work_end,
                    "original work window cannot fit the next stability sample",
                )?;
                while Instant::now() < target {
                    session.guard(inspector, self.work_end)?;
                    self.resources.live()?;
                    std::thread::sleep(
                        Duration::from_millis(50)
                            .min(target.saturating_duration_since(Instant::now())),
                    );
                }
            }
            session.guard(inspector, self.work_end)?;
            self.resources.live()?;
            inspector
                .revalidate_engine_until(
                    session.baseline.main(),
                    session.baseline.actual_application(),
                    session
                        .engine
                        .as_ref()
                        .ok_or("common stability original Engine missing")?,
                    self.work_end,
                )
                .map_err(|e| e.to_string())?;
            let dump = session.dump(inspector)?;
            self.resources.live()?;
            let snapshot = self.resources.sample(true)?;
            resources::same_window(&self.initial_resources, &snapshot)?;
            let at = Instant::now();
            before(self.work_end)?;
            let digest = format!(
                "{:x}",
                Sha256::digest(serde_json::to_vec(dump.body()).map_err(|e| e.to_string())?)
            );
            let first = self.samples.first().map_or(at, |sample| sample.at);
            let ordinal = self.samples.len() + 1;
            session.journal.json(
                &format!("STABILITY-SAMPLE-{ordinal}.json"),
                &serde_json::json!({"schema":"droidloom.native-ui-stability-sample.v1",
                    "ordinal":ordinal,"task":self.task,
                    "elapsed_from_first_ms":at.saturating_duration_since(first).as_millis(),
                    "native_dump_sha256":digest,"resources":snapshot,
                    "same_original_app_pidfd":true,"fresh_normal_engine_revalidated":true,
                    "comparison_only":true,"automatic_retry":false}),
            )?;
            self.samples.push(Sample {
                at,
                dump_sha256: digest,
                resources: snapshot,
            });
            Ok(())
        })();
        if let Err(error) = result {
            self.failed = true;
            return Err(session.observation_failure(inspector, error));
        }
        Ok(())
    }
    pub fn finish(
        mut self,
        session: NativeUiSession<'_, '_>,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<NativeUiStabilityEvidence, String> {
        let mut session = session;
        let prepared = (|| -> Result<(), String> {
            self.same_session(&session)?;
            require_cadence(
                &self
                    .samples
                    .iter()
                    .map(|sample| sample.at)
                    .collect::<Vec<_>>(),
            )?;
            session.guard(inspector, self.work_end)?;
            self.resources.live()?;
            inspector
                .require_exit_state_local(
                    session.baseline.main(),
                    session.baseline.actual_application(),
                    &self.before,
                    self.work_end,
                )
                .map_err(|e| e.to_string())?;
            Ok(())
        })();
        if let Err(error) = prepared {
            self.failed = true;
            return Err(session.observation_failure(inspector, error));
        }
        // Same existing close path, including its actual final running Engine
        // check and a single removal of only the retained new task.
        session = session.close_before_bookends(inspector)?;
        let completed =
            (|| -> Result<(ActualApplicationExitObservation, ResourceSample), String> {
                let after = inspector
                    .observe_application_exit_state_until(
                        session.baseline.main(),
                        session.baseline.actual_application(),
                        self.end,
                    )
                    .map_err(|e| e.to_string())?;
                inspector
                    .require_exit_state_local(
                        session.baseline.main(),
                        session.baseline.actual_application(),
                        &after,
                        self.end,
                    )
                    .map_err(|e| e.to_string())?;
                need(
                    after.observed_at() > self.samples.last().expect("three checked").at
                        && self.before.observed_at() < self.samples[0].at,
                    "fresh exit queries do not bracket the actual stability samples",
                )?;
                unchanged_exit_records(
                    self.before.facts().records(),
                    after.facts().records(),
                    self.application.uid,
                )?;
                let resource_after = self.resources.sample(false)?;
                resources::same_window(&self.initial_resources, &resource_after)?;
                session.journal.json(
                    "STABILITY-AFTER-CLOSE.json",
                    &serde_json::json!({
                        "schema":"droidloom.native-ui-stability-after-close.v1",
                        "actual_exit_state":after.facts(),"resources":resource_after,
                        "exact_uid_records_unchanged":true,"original_owned_close_completed":true,
                        "comparison_only":true,"automatic_retry":false
                    }),
                )?;
                Ok((after, resource_after))
            })();
        let (after, after_resource) = match completed {
            Ok(value) => value,
            Err(error) => return Err(session.observation_failure(inspector, error)),
        };
        let transcript = session.finish_bookends(inspector)?;
        let journal = RetainedJournal::capture(&transcript.journal_custody, self.end, JournalKind::Stability)?;
        let first = self.samples[0].at;
        let last = self.samples[SAMPLES - 1].at;
        let summary = NativeUiStabilitySummary {
            schema: "droidloom.native-ui-stability.v1",
            package: self.application.package.clone(),
            actual_uid: self.application.uid,
            task: self.task,
            application_host_pid: transcript.engine().facts().process.host_pid,
            application_start_ticks: transcript.engine().facts().process.start_ticks,
            sample_count: SAMPLES,
            minimum_gap_milliseconds: GAP.as_millis() as u64,
            actual_elapsed_milliseconds: last.duration_since(first).as_millis() as u64,
            sample_offsets_milliseconds: self
                .samples
                .iter()
                .map(|sample| sample.at.duration_since(first).as_millis() as u64)
                .collect(),
            native_dump_sha256: self
                .samples
                .iter()
                .map(|sample| sample.dump_sha256.clone())
                .collect(),
            before_exit_records_sha256: self.before.facts().records_sha256().into(),
            after_exit_records_sha256: after.facts().records_sha256().into(),
            before_resource: self.initial_resources,
            samples_resource: self
                .samples
                .into_iter()
                .map(|sample| sample.resources)
                .collect(),
            after_resource,
            complete_exact_uid_exit_records_unchanged: true,
            original_process_pidfd_held_through_reviewed_window: true,
            normal_owned_task_close_and_final_bookends: true,
            other_tasks_preserved: true,
            all_actual_queries_retired: true,
            original_deadline_extended: false,
            independent_reopen_inferred: false,
            data_permissions_or_accounts_inferred: false,
            whole_application_accepted: false,
        };
        let evidence = NativeUiStabilityEvidence {
            main: self.main,
            application: self.application,
            transcript,
            journal,
            before: self.before,
            after,
            _resources: self.resources,
            summary,
        };
        evidence.guard_immutable()?;
        before(self.end)?;
        Ok(evidence)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn record(uid: u32, digest: &str) -> ApplicationExitRecord {
        serde_json::from_value(serde_json::json!({
            "container_uid":uid,"timestamp":"2026-11-27 01:02:03.004","pid":23,
            "real_uid":uid,"package_uid":uid,"defining_uid":-1,"user":0,
            "process":"com.android.settings","reason":4,"subreason":0,"status":0,
            "record_sha256":digest.repeat(64)
        }))
        .unwrap()
    }
    #[test]
    fn common_retention_fixed_image_names_do_not_expand_other_members_or_total_bounds() {
        for name in [
            "0000-stdout.bin",
            "0512-stdout.bin",
            "0007-scoped-source.png",
            "CAMERA-OWNED-PHOTO.jpg",
        ] {
            assert_eq!(retained_member_limit(name), 32 * 1024 * 1024);
        }
        for name in [
            "BASELINE.json",
            "FINISHED.json",
            "STABILITY-BEGIN.json",
            "0001-stderr.bin",
            "1-stdout.bin",
            "00000-stdout.bin",
            "0001-source.png",
            "0001-scoped-source.png.extra",
            "camera-owned-photo.jpg",
            "CAMERA-OWNED-PHOTO.jpg/child",
            "０００１-stdout.bin",
            "image.png",
        ] {
            assert_eq!(
                retained_member_limit(name),
                wire::WIRE_REPLY_BYTES as u64,
                "{name}"
            );
        }
        assert_eq!(MAX_JOURNAL_BYTES, 128 * 1024 * 1024);
        assert_eq!(MAX_JOURNAL_FILES, 4096);
    }
    #[test]
    fn common_stability_journal_full_read_rejects_truncation_and_growth_on_the_held_fd() {
        let path = std::env::temp_dir().join(format!(
            "droidloom-common-held-{}-{}",
            std::process::id(),
            NEXT_JOURNAL.fetch_add(1, Ordering::Relaxed)
        ));
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        file.write_all(b"abc").unwrap();
        file.sync_all().unwrap();
        assert_eq!(
            full_hash(&file, 3).unwrap(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert!(full_hash(&file, 2).is_err());
        file.set_len(2).unwrap();
        assert!(full_hash(&file, 3).is_err());
        drop(file);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn common_stability_exact_uid_rejects_new_crash_self_exit_and_lost_history() {
        let a = record(10123, "a");
        let b = record(10123, "b");
        let other = record(110123, "c");
        unchanged_exit_records(&[a.clone()], &[other.clone(), a.clone()], 10123).unwrap();
        assert!(unchanged_exit_records(&[a.clone()], &[a.clone(), b], 10123).is_err());
        assert!(unchanged_exit_records(&[a.clone()], &[], 10123).is_err());
        unchanged_exit_records(&[], &[other], 10123).unwrap();
    }
    #[test]
    fn common_stability_cadence_requires_actual_three_samples_and_the_complete_interval() {
        let start = Instant::now();
        require_cadence(&[start, start + GAP, start + 2 * GAP]).unwrap();
        for times in [
            vec![],
            vec![start, start + GAP],
            vec![start, start, start + 2 * GAP],
            vec![
                start,
                start + GAP - Duration::from_millis(1),
                start + 2 * GAP,
            ],
            vec![start, start + GAP, start + GAP + Duration::from_secs(14)],
            vec![start, start + GAP, start + 2 * GAP, start + 3 * GAP],
            vec![start + GAP, start, start + 2 * GAP],
        ] {
            assert!(require_cadence(&times).is_err());
        }
        assert_eq!(stability_additional_window_seconds(), 680);
    }
    #[test]
    fn native_camera_case_finished_journal_cannot_substitute_stability_or_omit_close() {
        let full=required_members(JournalKind::Finished).iter().map(|x|x.to_string())
            .collect::<BTreeSet<_>>();
        assert_eq!(full.len(),7);
        assert!(require_members(JournalKind::Finished,&full).is_ok());
        for name in required_members(JournalKind::Finished) {
            let mut missing=full.clone();missing.remove(*name);
            assert!(require_members(JournalKind::Finished,&missing).is_err(),"{name}");
        }
        let stability=required_members(JournalKind::Stability).iter().map(|x|x.to_string())
            .collect::<BTreeSet<_>>();
        assert_eq!(stability.len(),8);
        assert!(require_members(JournalKind::Stability,&stability).is_ok());
        assert!(require_members(JournalKind::Finished,&stability).is_err());
        assert!(require_members(JournalKind::Stability,&full).is_err());
    }

    #[test]
    fn pm_permission_window_retention_rejects_missing_extra_failed_or_substituted_records() {
        let expected: BTreeMap<String, (u64, String)> = required_members(JournalKind::Permissions)
            .iter().map(|name| (name.to_string(), (17, "ab".repeat(32)))).collect();
        require_generated_permission_records(&expected, &expected).unwrap();
        let mut missing = expected.clone();
        missing.remove("PERMISSION-AFTER.json");
        assert!(require_generated_permission_records(&expected, &missing).is_err());
        let mut extra = expected.clone();
        extra.insert("PERMISSION-FAILED.json".into(), (17, "ab".repeat(32)));
        assert!(require_generated_permission_records(&expected, &extra).is_err());
        assert!(require_generated_permission_records(&extra, &extra).is_err());
        let mut changed = expected.clone();
        changed.get_mut("PERMISSION-BEFORE.json").unwrap().1 = "cd".repeat(32);
        assert!(require_generated_permission_records(&expected, &changed).is_err());
        changed = expected.clone();
        changed.get_mut("PERMISSION-AFTER.json").unwrap().0 += 1;
        assert!(require_generated_permission_records(&expected, &changed).is_err());
        let mut malformed = expected.clone();
        malformed.get_mut("PERMISSION-COMPLETE.json").unwrap().0 = 0;
        assert!(require_generated_permission_records(&malformed, &malformed).is_err());
        for kind in [JournalKind::Finished, JournalKind::Stability] {
            let mut names: BTreeSet<String> = required_members(kind).iter().map(|n| n.to_string()).collect();
            require_members(kind, &names).unwrap();
            assert!(require_members(JournalKind::Permissions, &names).is_err());
            names.remove(required_members(kind)[0]);
            assert!(require_members(kind, &names).is_err());
        }
    }

}
