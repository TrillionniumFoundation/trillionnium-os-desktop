//! Two actually created QSB/Firefox tasks under one live normal UI owner.
//!
//! This private child of native_application_ui_entry consumes its live session.
//! It cannot adopt a task, recreate an owner from a report, release the global
//! action lock between subjects, or supply a business/whole-application gate.
//! Only source-owned focus and one known cleanup for each created task exist.
//! A failed/uncertain operation poisons the shared session; Drop does no action.
use super::super::{NativeUiOutput, run_owned_native_ui};
use super::*;
use crate::control::EngineMappingObservation;
use crate::control::application_probe::ApplicationInspection;

const SOURCE: &str = "com.android.quicksearchbox";
const RECEIVER: &str = "org.mozilla.firefox";
const STACK_CAP: Duration = Duration::from_secs(15);
const FOCUS_CAP: Duration = Duration::from_secs(15);
const RESOLVE_CAP: Duration = Duration::from_secs(15);
const REMOVE_CAP: Duration = Duration::from_secs(20);
const REMOVE_POLL: Duration = Duration::from_secs(8);
const ENGINE_CAP: Duration = Duration::from_secs(70);
const PM_CAP: Duration = Duration::from_secs(250);
const CATALOG_CAP: Duration = Duration::from_secs(250);
const LAUNCH_CAP: Duration = Duration::from_secs(250);
const MAX_PAIR_COMMANDS: u32 = 91;
const MAX_SESSION_COMMANDS: u32 = 512;

/// Additional allowance above an ordinary already-budgeted source session.
/// Three new 250-second normal requests and one 70-second running Engine request
/// prepare the receiver. Fixed helper work is 175 seconds, one handoff is 345.
/// The retained receiver adds Engine 70 + close 60 + source dump 100 + PM 250.
/// It only supplies a source budget; no existing absolute deadline is extended.
pub const fn pair_additional_window_seconds() -> u64 {
    PM_CAP.as_secs()
        + CATALOG_CAP.as_secs()
        + LAUNCH_CAP.as_secs()
        + ENGINE_CAP.as_secs()
        + 175
        + 345
        + receiver_post_seconds()
}
const fn receiver_post_seconds() -> u64 {
    ENGINE_CAP.as_secs()
        + CLEANUP_RESERVE.as_secs()
        + COMMAND_CAP.as_secs()
        + 2 * STACK_CAP.as_secs()
        + PM_CAP.as_secs()
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Side {
    Source,
    Receiver,
}
impl Side {
    fn package(self) -> &'static str {
        match self {
            Self::Source => SOURCE,
            Self::Receiver => RECEIVER,
        }
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Preparing,
    SourceVisible,
    ReceiverVisible,
    Returned,
    Closed,
}
enum Command<'a> {
    Tasks,
    FocusSource,
    Resolve(&'a str),
    Remove(Side),
    Ui(&'a wire::Request),
}

/// Closed two-subject live owner. No Clone, Deserialize, task-ID constructor,
/// generic command, caller-selected package, or replaceable deadline is exposed.
pub struct NativeUiPairSession<'a, 'b> {
    session: NativeUiSession<'a, 'b>,
    receiver: ActualApplicationObservation,
    receiver_engine: Option<EngineMappingObservation>,
    receiver_task: Option<u32>,
    receiver_closed: bool,
    phase: Phase,
    receiver_end: Instant,
    first_sequence: u32,
    first_actions: u32,
    source_before: Option<wire::Reply>,
    handoff: Option<Handoff>,
    source_returned: Option<wire::Reply>,
}
struct Handoff {
    expected_url: String,
    component: String,
    found: wire::Reply,
    clicked: wire::Reply,
    receiver_dump: wire::Reply,
}

/// Historical immutable custody for the two normal owned task lifetimes.
/// The full original journal, including every pair command and reply, is held.
/// It deliberately has no completed_gates / accepted / production-ready API.
pub struct RetainedNativeUiPairTranscript {
    original: RetainedNativeUiTranscript,
    receiver: ActualApplicationObservation,
    receiver_after: ActualApplicationObservation,
    receiver_engine: EngineMappingObservation,
    receiver_task: u32,
    before_tasks: tasks::Tasks,
    source_before: wire::Reply,
    handoff: Option<Handoff>,
    source_returned: wire::Reply,
    first_sequence: u32,
    first_actions: u32,
}

/// Comparison only. Task IDs in these values can never construct a pair owner.
/// Unlike the old single-task comparison, every complete original root and
/// child row is retained, as well as the exact set of root and leaf IDs.
fn require_tasks(
    actual: &tasks::Tasks,
    before: &tasks::Tasks,
    active: &[(u32, &str)],
    retiring: Option<(u32, &str)>,
) -> Result<(), String> {
    let mut permitted = BTreeSet::new();
    for &(id, package) in active.iter().chain(retiring.iter()) {
        need(
            id != 0
                && !before.ids.contains(&id)
                && !before.roots.contains_key(&id)
                && permitted.insert(id)
                && matches!(package, SOURCE | RECEIVER),
            "native pair owned task aliases an original task or another subject",
        )?;
    }
    for (id, root) in &before.roots {
        need(
            actual.roots.get(id) == Some(root),
            "native pair original complete background root/child changed",
        )?;
    }
    need(
        before.ids.is_subset(&actual.ids)
            && actual
                .roots
                .keys()
                .all(|id| before.roots.contains_key(id) || permitted.contains(id))
            && actual
                .ids
                .iter()
                .all(|id| before.ids.contains(id) || permitted.contains(id)),
        "native pair has a foreign, moved, or missing task",
    )?;
    for &(id, package) in active {
        need(
            actual.exact_leaf(id, package),
            "native pair active task is not its exact owned leaf",
        )?;
    }
    if let Some((id, package)) = retiring {
        need(
            actual.exact_leaf(id, package) || actual.shrinking_leaf(id) || actual.absent(id),
            "native pair removing task changed identity",
        )?;
    }
    Ok(())
}

fn tasks_comparison(value: &tasks::Tasks) -> Value {
    serde_json::json!({"leaf_ids":value.ids,"complete_roots":format!("{:?}",value.roots)})
}

fn resolved_firefox(bytes: &[u8]) -> Result<String, String> {
    need(
        !bytes.is_empty()
            && bytes.len() <= 4096
            && bytes.ends_with(b"\n")
            && bytes
                .iter()
                .all(|v| v.is_ascii() && (!v.is_ascii_control() || *v == b'\n')),
        "native pair resolver output is missing or outside its fixed ASCII bound",
    )?;
    let text = std::str::from_utf8(bytes).map_err(|_| "native pair resolver is not UTF-8")?;
    let rows = text.lines().collect::<Vec<_>>();
    // Exact CP3A PackageManagerShellCommand --brief output. Metadata is parsed,
    // not ignored as an arbitrary banner before a caller-provided component.
    let [metadata, component] = rows.as_slice() else {
        return Err(
            "native pair resolver must contain one brief metadata row and one component".into(),
        );
    };
    let fields = metadata.split(' ').collect::<Vec<_>>();
    let keys = [
        "priority=",
        "preferredOrder=",
        "match=0x",
        "specificIndex=",
        "isDefault=",
    ];
    need(
        fields.len() == keys.len(),
        "native pair resolver metadata field count differs",
    )?;
    for (index, (field, prefix)) in fields.iter().zip(keys).enumerate() {
        let value = field
            .strip_prefix(prefix)
            .ok_or("native pair resolver metadata key/order differs")?;
        let valid = match index {
            2 => {
                !value.is_empty()
                    && value.len() <= 8
                    && value
                        .bytes()
                        .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
            }
            4 => matches!(value, "true" | "false"),
            _ => value.parse::<i32>().is_ok_and(|n| n.to_string() == value),
        };
        need(valid, "native pair resolver metadata value is malformed")?;
    }
    crate::control::validate_component(component).map_err(|e| e.to_string())?;
    need(
        component
            .split_once('/')
            .is_some_and(|(package, activity)| package == RECEIVER && !activity.is_empty()),
        "native pair actual implicit HTTPS receiver is not the selected Firefox",
    )?;
    Ok((*component).into())
}

// Read from the actual selected CP3A services.jar, 25,716,529 bytes,
// SHA256 bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86.
// runTask routes the literal "focus" to runTaskFocus: parse one task ID,
// println this exact line, then IActivityTaskManager.setFocusedTask(taskId).
// A successful command alone is insufficient: the live owner requires the
// exact two-task tree and a fresh QSB active-window dump immediately afterwards.
fn focus_result(bytes: &[u8], actual_source_task: u32) -> Result<(), String> {
    need(
        actual_source_task > 0
            && actual_source_task <= i32::MAX as u32
            && bytes == format!("Setting focus to task {actual_source_task}\n").as_bytes(),
        "native pair focus response does not name its actual owned source task",
    )
}

impl<'a, 'b> NativeUiPairSession<'a, 'b> {
    pub fn from_quick_search(
        mut source: NativeUiSession<'a, 'b>,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<Self, String> {
        need(
            !source.poisoned
                && !source.cleanup_started
                && !source.stability_started
                && source.baseline.application().package == SOURCE
                && source.baseline.application().user == 0
                && source.task.is_some()
                && source.engine.is_some()
                && source.sequence <= MAX_SESSION_COMMANDS - MAX_PAIR_COMMANDS,
            "native pair requires a live unused selected QSB task with the original command reserve",
        )?;
        let original_tree = source.before_task_tree.as_ref().ok_or(
            "native pair first normal Launch did not retain the complete actual prelaunch tree",
        )?;
        need(
            original_tree.ids == source.before_tasks
                && !original_tree.contains_package(SOURCE)
                && !original_tree.contains_package(RECEIVER),
            "native pair cannot adopt a preexisting QSB or Firefox task",
        )?;
        source.guard(inspector, source.work_end)?;
        let receiver_end = source.work_end;
        source.work_end = receiver_end.checked_sub(Duration::from_secs(receiver_post_seconds()))
            .filter(|v| *v > Instant::now())
            .ok_or("native pair original lease cannot retain both actual normal cleanup/bookend reserves")?;
        let receiver = inspector
            .inspect_observed_until(RECEIVER, 0, source.work_end)
            .map_err(|e| e.to_string())?;
        inspector
            .require_observations_local(source.baseline.main(), &receiver, source.work_end)
            .map_err(|e| e.to_string())?;
        need(
            receiver.facts().package == RECEIVER
                && receiver.facts().user == 0
                && receiver.facts().epoch == source.baseline.application().epoch,
            "native pair receiver complete PM observation has another subject",
        )?;
        let first_sequence = source.sequence;
        let first_actions = source.android_actions;
        let mut result = Self {
            session: source,
            receiver,
            receiver_engine: None,
            receiver_task: None,
            receiver_closed: false,
            phase: Phase::Preparing,
            receiver_end,
            first_sequence,
            first_actions,
            source_before: None,
            handoff: None,
            source_returned: None,
        };
        result.session.journal.json(
            "PAIR-BEGIN.json",
            &serde_json::json!({
                "schema":"droidloom.native-ui-pair-live.v1",
                "main":result.session.baseline.main().facts(),
                "source":result.session.baseline.application(),"receiver":result.receiver.facts(),
                "original_task_tree":tasks_comparison(result.original_tree()?),
                "source_task":result.session.task,"automatic_retry":false,
                "preexisting_task_adoption":false,"business_gate_supplied":false,
            }),
        )?;
        let prepared = (|| {
            result.launch_receiver(inspector)?;
            result.require_active(inspector, result.session.work_end)?;
            let output = result.run(inspector, Command::FocusSource, result.session.work_end)?;
            focus_result(&output.stdout, result.task(Side::Source)?)?;
            result.require_active(inspector, result.session.work_end)?;
            result.source_before = Some(result.ui(
                inspector,
                Side::Source,
                wire::Operation::Dump,
                result.session.work_end,
            )?);
            result.phase = Phase::SourceVisible;
            result.session.journal.json(
                "PAIR-SOURCE-READY.json",
                &serde_json::json!({
                    "source_task":result.session.task,"receiver_task":result.receiver_task,
                    "source_dump":result.source_before.as_ref().unwrap().body(),
                    "both_normal_launches_and_running_engines_observed":true,
                    "original_background_roots_unchanged":true,"business_gate_supplied":false,
                }),
            )?;
            result.guard(inspector, result.session.work_end)
        })();
        if let Err(error) = prepared {
            return Err(result.fail("prepare", error));
        }
        Ok(result)
    }
    fn original_tree(&self) -> Result<&tasks::Tasks, String> {
        self.session
            .before_task_tree
            .as_ref()
            .ok_or_else(|| "native pair original task tree absent".into())
    }
    fn task(&self, side: Side) -> Result<u32, String> {
        match side {
            Side::Source => self.session.task,
            Side::Receiver => self.receiver_task,
        }
        .ok_or_else(|| "native pair actual owned task absent".into())
    }
    fn guard(&self, inspector: &NativeApplicationInspector, until: Instant) -> Result<(), String> {
        self.session.guard(inspector, until)?;
        inspector
            .require_observations_local(
                self.session.baseline.main(),
                &self.receiver,
                until.min(self.session.end),
            )
            .map_err(|e| e.to_string())?;
        let source = self
            .session
            .engine
            .as_ref()
            .ok_or("native pair original Engine absent")?;
        need(
            source.application() == self.session.baseline.application()
                && source.facts().main == *self.session.baseline.main().facts(),
            "native pair original Engine belongs to another full subject",
        )?;
        if let Some(receiver) = &self.receiver_engine {
            need(
                receiver.application() == self.receiver.facts()
                    && receiver.facts().main == source.facts().main
                    && receiver.peer() == source.peer(),
                "native pair receiver Engine belongs to another full subject or peer",
            )?;
        }
        before(until.min(self.session.end))
    }
    fn fail(&mut self, phase: &'static str, first: String) -> String {
        self.session.poisoned = true;
        let recorded = self.session.journal.json(
            &format!("PAIR-FAILED-{phase}.json"),
            &serde_json::json!({
                "first_error":first,"phase":format!("{:?}",self.phase),
                "automatic_retry":false,"follow_up_forbidden":true,"business_gate_supplied":false,
            }),
        );
        format!(
            "{first}; native pair poisoned; history={}; failure_record={}",
            self.session.journal.path.display(),
            recorded.is_ok()
        )
    }
    fn run(
        &mut self,
        inspector: &NativeApplicationInspector,
        command: Command<'_>,
        until: Instant,
    ) -> Result<Output, String> {
        need(
            !self.session.poisoned
                && self.session.sequence < MAX_SESSION_COMMANDS
                && until <= self.session.end,
            "native pair is poisoned, exhausted, or offered a different deadline",
        )?;
        let (label, literal, mutation, cap, limit) = match command {
            Command::Tasks => (
                "pair-tasks",
                vec![
                    "/system/bin/cmd".into(),
                    "activity".into(),
                    "stack".into(),
                    "list".into(),
                ],
                false,
                STACK_CAP,
                NativeUiOutput::Small,
            ),
            Command::FocusSource => (
                "pair-focus-owned-source",
                vec![
                    "/system/bin/cmd".into(),
                    "activity".into(),
                    "task".into(),
                    "focus".into(),
                    self.task(Side::Source)?.to_string(),
                ],
                true,
                FOCUS_CAP,
                NativeUiOutput::Small,
            ),
            Command::Resolve(url) => {
                crate::control::application_probe::validate_https_url(url)?;
                (
                    "pair-resolve-implicit-https",
                    vec![
                        "/system/bin/cmd".into(),
                        "package".into(),
                        "resolve-activity".into(),
                        "--brief".into(),
                        "--user".into(),
                        "0".into(),
                        "-a".into(),
                        "android.intent.action.VIEW".into(),
                        "-c".into(),
                        "android.intent.category.BROWSABLE".into(),
                        "-d".into(),
                        url.into(),
                    ],
                    false,
                    RESOLVE_CAP,
                    NativeUiOutput::Small,
                )
            }
            Command::Remove(side) => (
                "pair-remove-owned-task",
                vec![
                    "/system/bin/cmd".into(),
                    "activity".into(),
                    "stack".into(),
                    "remove".into(),
                    self.task(side)?.to_string(),
                ],
                true,
                REMOVE_CAP,
                NativeUiOutput::Small,
            ),
            Command::Ui(request) => (
                "pair-fixed-native-ui",
                request.arguments().map_err(|e| e.to_string())?,
                request.mutation(),
                COMMAND_CAP,
                NativeUiOutput::Helper,
            ),
        };
        self.guard(inspector, until)?;
        self.session.sequence += 1;
        self.session.poisoned = true;
        let index = self.session.sequence;
        self.session.journal.json(&format!("{index:04}-INTENT.json"), &serde_json::json!({
            "label":label,"literal_sha256":format!("{:x}",Sha256::digest(serde_json::to_vec(&literal).map_err(|e|e.to_string())?)),
            "mutation":mutation,"actual_source_task":self.session.task,"actual_receiver_task":self.receiver_task,
            "automatic_retry":false,"comparison_only":true,
        }))?;
        let result: Result<Output, String> = (|| {
            let command_end = (Instant::now() + cap).min(until);
            before(command_end)?;
            let (command, inherit) = self.session.target.command(
                &self.session.helper,
                &literal,
                true,
                cap.min(command_end.saturating_duration_since(Instant::now())),
            )?;
            if mutation {
                self.session.android_actions += 1;
            }
            let mut guard = || self.guard(inspector, command_end);
            let output = run_owned_native_ui(
                command,
                &inherit,
                &[
                    self.session.target.init.pidfd.as_raw_fd(),
                    self.session.target.framework.pidfd.as_raw_fd(),
                ],
                command_end,
                limit,
                &mut guard,
            )?;
            self.session
                .journal
                .write(&format!("{index:04}-stdout.bin"), &output.stdout)?;
            self.session
                .journal
                .write(&format!("{index:04}-stderr.bin"), &output.stderr)?;
            self.session.journal.json(&format!("{index:04}-RESULT.json"), &serde_json::json!({
                "exit_code":output.status.code(),"host_invocation_retired":true,
                "android_mutation_attempted":mutation,"automatic_retry":false,"business_gate_supplied":false,
            }))?;
            self.guard(inspector, command_end)?;
            need(
                output.status.code() == Some(0) && output.stderr.is_empty(),
                "native pair fixed command failed; actual raw output retained",
            )?;
            Ok(output)
        })();
        match result {
            Ok(output) => {
                self.session.poisoned = false;
                Ok(output)
            }
            Err(error) => {
                let recorded = self.session.journal.json(
                    &format!("{index:04}-FAILED.json"),
                    &serde_json::json!({
                        "error":error,"outcome_unknown":mutation,"automatic_retry":false,
                    }),
                );
                Err(format!(
                    "{error}; pair command poisoned; history={}; failure_record={}",
                    self.session.journal.path.display(),
                    recorded.is_ok()
                ))
            }
        }
    }
    fn stacks(
        &mut self,
        inspector: &NativeApplicationInspector,
        until: Instant,
    ) -> Result<tasks::Tasks, String> {
        let out = self.run(inspector, Command::Tasks, until)?;
        tasks::Tasks::parse(&out.stdout).inspect_err(|_| self.session.poisoned = true)
    }
    fn active(&self) -> Result<Vec<(u32, &'static str)>, String> {
        let mut active = Vec::new();
        if !self.session.cleanup_started {
            active.push((self.task(Side::Source)?, SOURCE));
        }
        if let Some(id) = self.receiver_task {
            if !self.receiver_closed {
                active.push((id, RECEIVER));
            }
        }
        Ok(active)
    }
    fn require_active(
        &mut self,
        inspector: &NativeApplicationInspector,
        until: Instant,
    ) -> Result<(), String> {
        let actual = self.stacks(inspector, until)?;
        let result = require_tasks(&actual, self.original_tree()?, &self.active()?, None);
        if result.is_err() {
            self.session.poisoned = true;
        }
        result
    }
    fn launch_receiver(
        &mut self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<(), String> {
        self.guard(inspector, self.session.work_end)?;
        let reply = inspector
            .request_fixed_until(
                &ControlRequest::ListApplications { user: 0 },
                Some(self.session.work_end),
            )
            .map_err(|e| e.to_string())?;
        self.session.owner_reply(&reply)?;
        self.session.journal.json("PAIR-CATALOG.json", &reply)?;
        let candidates = reply
            .applications
            .ok_or("native pair actual launcher catalog absent")?
            .into_iter()
            .filter(|c| c.package == RECEIVER)
            .map(|c| c.component)
            .collect::<BTreeSet<_>>();
        need(
            candidates.len() == 1,
            "native pair receiver has no unique actual MAIN/LAUNCHER component",
        )?;
        let component = candidates.into_iter().next().unwrap();
        crate::control::validate_component(&component).map_err(|e| e.to_string())?;
        let before = self.stacks(inspector, self.session.work_end)?;
        require_tasks(
            &before,
            self.original_tree()?,
            &[(self.task(Side::Source)?, SOURCE)],
            None,
        )?;
        need(
            !before.contains_package(RECEIVER),
            "native pair refuses a preexisting Firefox task",
        )?;
        self.session.journal.json("PAIR-LAUNCH-INTENT.json",&serde_json::json!({
            "package":RECEIVER,"component":component,"actual_before":tasks_comparison(&before),"automatic_retry":false,
        }))?;
        self.session.poisoned = true;
        let reply = inspector
            .request_fixed_until(
                &ControlRequest::Launch {
                    spec: PathBuf::from(crate::control::DEFAULT_CELL_SPEC),
                    package: RECEIVER.into(),
                    component: Some(component),
                    resolution: None,
                    user: 0,
                },
                Some(self.session.work_end),
            )
            .map_err(|e| e.to_string())?;
        self.session
            .journal
            .json("PAIR-LAUNCH-RESULT.json", &reply)?;
        self.session.owner_reply(&reply)?;
        need(
            reply.inspection.as_ref() == Some(self.receiver.facts()),
            "native pair normal receiver Launch changed complete PM identity",
        )?;
        let task = tasks::launch_task(
            reply
                .launch
                .as_deref()
                .ok_or("native pair normal native binding absent")?,
        )?;
        need(
            !before.ids.contains(&task) && !before.roots.contains_key(&task),
            "native pair normal receiver Launch reused an existing task",
        )?;
        self.receiver_task = Some(task);
        self.session.poisoned = false;
        self.require_active(inspector, self.session.work_end)?;
        self.receiver_engine = Some(
            inspector
                .observe_running_engine_until(
                    self.session.baseline.main(),
                    &self.receiver,
                    self.session.work_end,
                )
                .map_err(|e| e.to_string())?,
        );
        self.guard(inspector, self.session.work_end)?;
        self.session.journal.json(
            "PAIR-OWNED-RECEIVER.json",
            &serde_json::json!({
                "task":task,"application":self.receiver.facts(),
                "engine":self.receiver_engine.as_ref().unwrap().facts(),
                "actual_prelaunch_absence":true,"business_gate_supplied":false,
            }),
        )
    }
    fn ui(
        &mut self,
        inspector: &NativeApplicationInspector,
        side: Side,
        operation: wire::Operation,
        until: Instant,
    ) -> Result<wire::Reply, String> {
        self.require_active(inspector, until)?;
        let request = wire::Request::new(side.package(), operation).map_err(|e| e.to_string())?;
        let output = self.run(inspector, Command::Ui(&request), until)?;
        let reply = wire::Reply::parse(&request, &output)
            .inspect_err(|_| self.session.poisoned = true)
            .map_err(|e| e.to_string())?;
        self.require_active(inspector, until)?;
        Ok(reply)
    }
    pub fn source_before_handoff(&self) -> Result<&wire::Reply, String> {
        need(
            !self.session.poisoned && self.phase == Phase::SourceVisible,
            "native pair source is not a known live ready task",
        )?;
        self.source_before
            .as_ref()
            .ok_or_else(|| "native pair actual source dump absent".into())
    }
    /// One actual QSB-owned click after a fresh implicit HTTPS resolver selected
    /// the separately observed Firefox. The URL is a comparison expectation:
    /// neither resolution nor this history proves the loaded document/URL.
    pub fn handoff_https_result(
        &mut self,
        inspector: &NativeApplicationInspector,
        selector: wire::Selector,
        expected_https_url: &str,
    ) -> Result<(), String> {
        need(
            self.phase == Phase::SourceVisible && self.handoff.is_none() && !self.session.poisoned,
            "native pair permits only one known source-to-receiver handoff",
        )?;
        crate::control::application_probe::validate_https_url(expected_https_url)?;
        let result =
            (|| {
                let found = self.ui(
                    inspector,
                    Side::Source,
                    wire::Operation::Find(selector.clone()),
                    self.session.work_end,
                )?;
                let nodes = found
                    .body()
                    .get("matches")
                    .and_then(Value::as_array)
                    .ok_or("native pair actual selector nodes absent")?;
                need(
                    found.body().get("count").and_then(Value::as_u64) == Some(1)
                        && nodes.len() == 1
                        && nodes[0].get("enabled").and_then(Value::as_bool) == Some(true)
                        && nodes[0].get("clickable").and_then(Value::as_bool) == Some(true),
                    "native pair handoff must target one actually enabled clickable QSB node",
                )?;
                self.require_active(inspector, self.session.work_end)?;
                let output = self.run(
                    inspector,
                    Command::Resolve(expected_https_url),
                    self.session.work_end,
                )?;
                let component = resolved_firefox(&output.stdout)?;
                self.require_active(inspector, self.session.work_end)?;
                self.session.journal.json("PAIR-HANDOFF-INTENT.json",&serde_json::json!({
                "expected_https_url":expected_https_url,"actual_resolved_component":component,
                "actual_selected_node":nodes[0],"source_task":self.session.task,
                "receiver_task":self.receiver_task,"url_or_document_verified":false,
                "explicit_firefox_launch_for_handoff":false,"automatic_retry":false,
            }))?;
                let clicked = self.ui(
                    inspector,
                    Side::Source,
                    wire::Operation::Click(selector),
                    self.session.work_end,
                )?;
                let receiver_dump = self.ui(
                    inspector,
                    Side::Receiver,
                    wire::Operation::Dump,
                    self.session.work_end,
                )?;
                self.handoff = Some(Handoff {
                    expected_url: expected_https_url.into(),
                    component,
                    found,
                    clicked,
                    receiver_dump,
                });
                self.phase = Phase::ReceiverVisible;
                self.session.journal.json(
                    "PAIR-HANDOFF-COMPLETE.json",
                    &serde_json::json!({
                        "actual_receiver_dump":self.handoff.as_ref().unwrap().receiver_dump.body(),
                        "exact_two_owned_tasks_and_original_background_roots":true,
                        "expected_url_loaded":false,"business_gate_supplied":false,
                    }),
                )?;
                self.guard(inspector, self.session.work_end)
            })();
        result.map_err(|e| self.fail("handoff", e))
    }
    pub fn receiver_after_handoff(&self) -> Result<&wire::Reply, String> {
        need(
            !self.session.poisoned && self.phase == Phase::ReceiverVisible,
            "native pair receiver is not known live after handoff",
        )?;
        self.handoff
            .as_ref()
            .map(|h| &h.receiver_dump)
            .ok_or_else(|| "native pair actual handoff absent".into())
    }
    fn close_side(
        &mut self,
        inspector: &NativeApplicationInspector,
        side: Side,
        until: Instant,
    ) -> Result<(), String> {
        need(
            !self.session.poisoned,
            "native pair unknown outcome forbids cleanup",
        )?;
        let id = self.task(side)?;
        need(
            match side {
                Side::Source => !self.session.cleanup_started,
                Side::Receiver => !self.receiver_closed,
            },
            "native pair cleanup has already been attempted",
        )?;
        self.require_active(inspector, until)?;
        let (intent, complete) = match side {
            Side::Source => ("CLEANUP-INTENT.json", "CLEANUP-COMPLETE.json"),
            Side::Receiver => (
                "PAIR-RECEIVER-CLEANUP-INTENT.json",
                "PAIR-RECEIVER-CLEANUP-COMPLETE.json",
            ),
        };
        self.session.journal.json(
            intent,
            &serde_json::json!({"task":id,"package":side.package(),"automatic_retry":false}),
        )?;
        // Mark the original-once cleanup before executing the one mutation.
        match side {
            Side::Source => self.session.cleanup_started = true,
            Side::Receiver => self.receiver_closed = true,
        };
        let active = self.active()?;
        let output = self.run(inspector, Command::Remove(side), until)?;
        need(
            output.stdout.is_empty(),
            "native pair task removal returned unexpected output",
        )?;
        let poll_end = (Instant::now() + REMOVE_POLL).min(until);
        let mut removed = false;
        for _ in 0..32 {
            before(poll_end)?;
            std::thread::sleep(Duration::from_millis(100));
            let actual = self.stacks(inspector, poll_end)?;
            require_tasks(
                &actual,
                self.original_tree()?,
                &active,
                Some((id, side.package())),
            )?;
            if actual.absent(id) {
                removed = true;
                break;
            }
        }
        need(
            removed,
            "native pair task removal remains unknown; no repeat/follow-up is permitted",
        )?;
        self.guard(inspector, until)?;
        self.session.journal.json(
            complete,
            &serde_json::json!({
                "task":id,"package":side.package(),"actual_owned_task_absent":true,
                "complete_original_background_roots_preserved":true,
                "automatic_retry":false,"business_gate_supplied":false,
            }),
        )
    }
    /// Close this pair's new Firefox task once, then observe actual QSB UI.
    /// This is task custody return; it is deliberately not browser Back evidence.
    pub fn close_receiver_and_return(
        &mut self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<(), String> {
        need(
            matches!(self.phase, Phase::SourceVisible | Phase::ReceiverVisible)
                && !self.session.poisoned,
            "native pair receiver return is unavailable or already attempted",
        )?;
        let result = (|| {
            inspector
                .revalidate_engine_until(
                    self.session.baseline.main(),
                    &self.receiver,
                    self.receiver_engine
                        .as_ref()
                        .ok_or("native pair original receiver Engine absent")?,
                    self.receiver_end,
                )
                .map_err(|e| e.to_string())?;
            self.close_side(inspector, Side::Receiver, self.receiver_end)?;
            self.source_returned = Some(self.ui(
                inspector,
                Side::Source,
                wire::Operation::Dump,
                self.receiver_end,
            )?);
            self.phase = Phase::Returned;
            self.session.journal.json(
                "PAIR-RETURN.json",
                &serde_json::json!({
                    "source_task":self.session.task,"closed_receiver_task":self.receiver_task,
                    "actual_source_dump":self.source_returned.as_ref().unwrap().body(),
                    "browser_back_action_performed":false,"query_persistence_inferred":false,
                    "business_gate_supplied":false,"automatic_retry":false,
                }),
            )
        })();
        result.map_err(|e| self.fail("return", e))
    }
    pub fn source_after_return(&self) -> Result<&wire::Reply, String> {
        need(
            !self.session.poisoned && self.phase == Phase::Returned,
            "native pair actual task return absent",
        )?;
        self.source_returned
            .as_ref()
            .ok_or_else(|| "native pair actual returned QSB dump absent".into())
    }
    pub fn counts(&self) -> (u32, u32) {
        (
            self.session.sequence - self.first_sequence,
            self.session.android_actions - self.first_actions,
        )
    }
    pub fn finish(
        mut self,
        inspector: &mut NativeApplicationInspector,
    ) -> Result<RetainedNativeUiPairTranscript, String> {
        need(
            !self.session.poisoned,
            "native pair uncertain mutation forbids all follow-up",
        )?;
        if self.phase != Phase::Returned {
            self.close_receiver_and_return(inspector)?;
        }
        let result = (|| {
            inspector
                .revalidate_engine_until(
                    self.session.baseline.main(),
                    self.session.baseline.actual_application(),
                    self.session
                        .engine
                        .as_ref()
                        .ok_or("native pair original source Engine absent")?,
                    self.session.end,
                )
                .map_err(|e| e.to_string())?;
            self.close_side(inspector, Side::Source, self.session.end)?;
            let after = inspector
                .inspect_observed_until(RECEIVER, 0, self.session.end)
                .map_err(|e| e.to_string())?;
            inspector
                .require_observations_local(self.session.baseline.main(), &after, self.session.end)
                .map_err(|e| e.to_string())?;
            need(
                after.facts() == self.receiver.facts(),
                "native pair receiver full PM identity changed at final bookend",
            )?;
            self.guard(inspector, self.session.end)?;
            self.phase = Phase::Closed;
            self.session.journal.json("PAIR-FINISHED.json",&serde_json::json!({
                "schema":"droidloom.native-ui-pair-finished.v1","source_task":self.session.task,
                "receiver_task":self.receiver_task,"receiver_before":self.receiver.facts(),"receiver_after":after.facts(),
                "pair_helper_commands":self.counts().0,"pair_helper_mutations":self.counts().1,
                "normal_receiver_launches":1,"both_created_tasks_absent":true,
                "complete_original_background_roots_preserved":true,
                "actual_handoff_completed":self.handoff.is_some(),"browser_back_performed":false,
                "business_gate_supplied":false,"automatic_retry":false,
            }))?;
            Ok(after)
        })();
        let receiver_after = match result {
            Ok(v) => v,
            Err(e) => return Err(self.fail("finish", e)),
        };
        let before_tasks = self
            .session
            .before_task_tree
            .take()
            .ok_or("native pair retained first prelaunch tree absent")?;
        let original = self.session.finish_bookends(inspector)?.into_retained()?;
        let result = RetainedNativeUiPairTranscript {
            original,
            receiver: self.receiver,
            receiver_after,
            receiver_engine: self
                .receiver_engine
                .take()
                .ok_or("native pair retained receiver Engine absent")?,
            receiver_task: self
                .receiver_task
                .ok_or("native pair retained actual receiver task absent")?,
            before_tasks,
            source_before: self
                .source_before
                .take()
                .ok_or("native pair source-before dump absent")?,
            handoff: self.handoff.take(),
            source_returned: self
                .source_returned
                .take()
                .ok_or("native pair source-return dump absent")?,
            first_sequence: self.first_sequence,
            first_actions: self.first_actions,
        };
        result.guard_immutable()?;
        Ok(result)
    }
}
impl RetainedNativeUiPairTranscript {
    pub fn guard_immutable(&self) -> Result<(), String> {
        self.original.guard_immutable()?;
        let original = self.original.transcript();
        need(
            original.engine().application().package == SOURCE
                && self.receiver.facts().package == RECEIVER
                && self.receiver.facts().user == 0
                && self.receiver.facts() == self.receiver_after.facts()
                && self.receiver_engine.application() == self.receiver.facts()
                && self.receiver_engine.facts().main == original.engine().facts().main
                && self.receiver_engine.peer() == original.engine().peer()
                && self.receiver_task != original.task()
                && !self.before_tasks.ids.contains(&original.task())
                && !self.before_tasks.ids.contains(&self.receiver_task)
                && !self.before_tasks.roots.contains_key(&original.task())
                && !self.before_tasks.roots.contains_key(&self.receiver_task)
                && original.operations() >= self.first_sequence
                && original.actions() >= self.first_actions,
            "native pair retained subjects or original task provenance changed",
        )
    }
    pub fn require_subjects(
        &self,
        main: &RuntimeMainCustody,
        source: &ApplicationInspection,
        receiver: &ApplicationInspection,
    ) -> Result<(), String> {
        self.original.require_subject(main, source)?;
        need(
            receiver == self.receiver.facts() && self.receiver_engine.facts().main == *main,
            "native pair retained second complete subject differs",
        )?;
        self.guard_immutable()
    }
    pub fn source_transcript(&self) -> &NativeUiTranscript {
        self.original.transcript()
    }
    pub fn receiver_application(&self) -> &ApplicationInspection {
        self.receiver.facts()
    }
    pub fn source_before_handoff(&self) -> &wire::Reply {
        &self.source_before
    }
    pub fn receiver_after_handoff(&self) -> Option<&wire::Reply> {
        self.handoff.as_ref().map(|h| &h.receiver_dump)
    }
    pub fn source_after_return(&self) -> &wire::Reply {
        &self.source_returned
    }
    pub fn counts(&self) -> (u32, u32) {
        (
            self.original.transcript().operations() - self.first_sequence,
            self.original.transcript().actions() - self.first_actions,
        )
    }
    pub fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        Ok(serde_json::json!({
            "schema":"droidloom.native-ui-pair-retained.v1",
            "source":self.original.comparison()?,"receiver_application":self.receiver.facts(),
            "receiver_after":self.receiver_after.facts(),"receiver_engine":self.receiver_engine.facts(),
            "receiver_task":self.receiver_task,"original_task_tree":tasks_comparison(&self.before_tasks),
            "source_before_handoff":self.source_before.body(),"source_after_return":self.source_returned.body(),
            "handoff":self.handoff.as_ref().map(|h|serde_json::json!({
                "expected_https_url":h.expected_url,"actual_resolved_component":h.component,
                "actual_find":h.found.body(),"actual_click":h.clicked.body(),"actual_receiver_dump":h.receiver_dump.body(),
                "expected_url_loaded":false,"business_gate_supplied":false,
            })),
            "pair_helper_commands":self.counts().0,"pair_helper_mutations":self.counts().1,
            "normal_receiver_launches":1,"both_owned_tasks_closed":true,"original_background_roots_preserved":true,
            "browser_back_performed":false,"live_execution_authority_retained":false,"business_gate_supplied":false,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn listing(id: u32, package: &str) -> String {
        format!(
            "RootTask id={id} displayId=0 userId=0\n configuration={{ mWindowingMode=freeform }}\n taskId={id}: {package}/.Main userId=0 visible=true\n"
        )
    }
    fn parse(text: &str) -> tasks::Tasks {
        tasks::Tasks::parse(text.as_bytes()).unwrap()
    }
    #[test]
    fn native_ui_pair_preserves_complete_background_roots_and_exact_two_new_subjects() {
        let original = listing(3, "com.android.launcher3") + &listing(4, "com.android.settings");
        let before = parse(&original);
        let owned = [(7, SOURCE), (9, RECEIVER)];
        let both = original.clone() + &listing(7, SOURCE) + &listing(9, RECEIVER);
        assert!(require_tasks(&parse(&both), &before, &owned, None).is_ok());
        for changed in [
            both.replace("RootTask id=3 displayId=0", "RootTask id=3 displayId=1"),
            both.replace("3: com.android.launcher3", "3: com.android.contacts"),
            both.replace(
                "RootTask id=4 displayId=0 userId=0",
                "RootTask id=4 displayId=0 userId=10",
            ),
            both.replace(
                "taskId=4: com.android.settings/.Main userId=0",
                "taskId=4: com.android.settings/.Main userId=10",
            ),
            original.clone()
                + &listing(7, SOURCE)
                + &listing(9, RECEIVER)
                + &listing(10, "com.android.camera2"),
            original.clone() + &listing(7, SOURCE),
            original.clone() + &listing(7, RECEIVER) + &listing(9, SOURCE),
        ] {
            assert!(require_tasks(&parse(&changed), &before, &owned, None).is_err());
        }
        assert!(
            require_tasks(&parse(&both), &before, &[(7, SOURCE), (7, RECEIVER)], None).is_err()
        );
        assert!(
            require_tasks(&parse(&both), &before, &[(3, SOURCE), (9, RECEIVER)], None).is_err()
        );
    }
    #[test]
    fn native_ui_pair_cleanup_allows_only_the_one_owned_shrinking_or_absent_root() {
        let original = listing(3, "com.android.launcher3");
        let before = parse(&original);
        let live = original.clone() + &listing(7, SOURCE);
        for tail in [
            listing(9, RECEIVER),
            "RootTask id=9 displayId=0 userId=0\n configuration={ mWindowingMode=freeform }\n"
                .into(),
            String::new(),
        ] {
            assert!(
                require_tasks(
                    &parse(&(live.clone() + &tail)),
                    &before,
                    &[(7, SOURCE)],
                    Some((9, RECEIVER))
                )
                .is_ok()
            );
        }
        assert!(
            require_tasks(
                &parse(&(live.clone() + &listing(9, "com.android.settings"))),
                &before,
                &[(7, SOURCE)],
                Some((9, RECEIVER))
            )
            .is_err()
        );
        assert!(require_tasks(&parse(&original), &before, &[], None).is_ok());
        assert!(require_tasks(&parse(&live), &before, &[], None).is_err());
    }
    #[test]
    fn native_ui_pair_resolver_rejects_foreign_ambiguous_or_banner_injected_results() {
        let good = "priority=0 preferredOrder=0 match=0x208000 specificIndex=-1 isDefault=true\norg.mozilla.firefox/.App\n";
        assert_eq!(
            resolved_firefox(good.as_bytes()).unwrap(),
            "org.mozilla.firefox/.App"
        );
        for bad in [
            good.replace("org.mozilla.firefox", "com.android.intentresolver"),
            format!("Warning: malformed input\n{good}"),
            format!("{good}org.mozilla.firefox/.Other\n"),
            good.replace("specificIndex=-1", "specificIndex=-01"),
            good.replace("priority=0 preferredOrder=0", "preferredOrder=0 priority=0"),
            good.replace("match=0x208000", "match=0xZZ"),
            good.replace("isDefault=true", "isDefault=maybe"),
            good.replace(".App", ".App extra"),
            "org.mozilla.firefox/.App\n".into(),
        ] {
            assert!(resolved_firefox(bad.as_bytes()).is_err());
        }
    }
    #[test]
    fn native_ui_pair_budget_keeps_existing_lease_and_reserves_every_fixed_step() {
        assert_eq!(pair_additional_window_seconds(), 1820);
        assert_eq!(receiver_post_seconds(), 480);
        assert_eq!(MAX_PAIR_COMMANDS, 8 + 12 + 3 + 2 * (2 + 32));
        assert!(MAX_PAIR_COMMANDS < MAX_SESSION_COMMANDS);
        assert!(focus_result(b"Setting focus to task 7\n", 7).is_ok());
        assert!(focus_result(b"Setting focus to task 9\n", 7).is_err());
        assert!(focus_result(b"Setting focus to task 0\n", 0).is_err());
        assert!(focus_result(b"Setting focus to task 7", 7).is_err());
    }
}
