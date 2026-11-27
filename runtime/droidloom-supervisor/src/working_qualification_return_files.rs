//! Fixed held files for the independent working-return consumer.
//! Protected documents are comparisons after actual PID1 retirement; no
//! deserialization here can mint a live Main, Complete, or inherited source lock.
use super::{BootOwner, MaintenanceOperation, RetiredWorkingParent};
use crate::control::physical_qualification_channel::{BINDING_LIMIT, SUMMARY_LIMIT, layout};
use crate::{native_hardware_label as held, native_working_contract as contract};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    ffi::CString,
    fs::{self, File, OpenOptions},
    io::{self, Write},
    os::{
        fd::AsRawFd,
        unix::{
            ffi::OsStrExt,
            fs::{FileExt, MetadataExt, OpenOptionsExt, PermissionsExt},
        },
    },
    path::{Path, PathBuf},
    time::Instant,
};

fn denied(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, s)
}
fn live(end: Instant) -> io::Result<()> {
    if Instant::now() >= end {
        Err(denied(
            "working return file operation exhausted its original end",
        ))
    } else {
        Ok(())
    }
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn f9(file: &File) -> io::Result<[u64; 9]> {
    let m = file.metadata()?;
    let ns = |sec: i64, nsec: i64| {
        u64::try_from(i128::from(sec) * 1_000_000_000 + i128::from(nsec))
            .map_err(|_| denied("working return input timestamp is outside its source range"))
    };
    Ok([
        m.dev(),
        m.ino(),
        m.mode().into(),
        m.uid().into(),
        m.gid().into(),
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}
struct Directory {
    path: PathBuf,
    chain: Vec<(PathBuf, File, [u64; 9])>,
    label: &'static [u8],
}
impl Directory {
    fn open(path: &Path, label: &'static [u8]) -> io::Result<Self> {
        if !path.is_absolute()
            || path.components().any(|p| {
                !matches!(
                    p,
                    std::path::Component::RootDir | std::path::Component::Normal(_)
                )
            })
        {
            return Err(denied("working return directory is not canonical"));
        }
        let mut current = PathBuf::from("/");
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/")?;
        let pin = f9(&root)?;
        let mut chain = vec![(current.clone(), root, pin)];
        for part in path.components().skip(1) {
            let std::path::Component::Normal(part) = part else {
                return Err(denied("directory component differs"));
            };
            current.push(part);
            let parent = &chain
                .last()
                .ok_or_else(|| denied("held directory chain absent"))?
                .1;
            let name = CString::new(part.as_bytes()).map_err(io::Error::other)?;
            let fd = unsafe {
                libc::openat(
                    parent.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                )
            };
            if fd < 0 {
                return Err(io::Error::last_os_error());
            }
            use std::os::fd::FromRawFd;
            let file = unsafe { File::from_raw_fd(fd) };
            let pin = f9(&file)?;
            if pin[2] & u64::from(libc::S_IFMT) != u64::from(libc::S_IFDIR)
                || pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
            {
                return Err(denied(
                    "working return requires a protected root directory chain",
                ));
            }
            chain.push((current.clone(), file, pin));
        }
        let value = Self {
            path: path.into(),
            chain,
            label,
        };
        value.guard()?;
        Ok(value)
    }
    fn file(&self) -> &File {
        &self.chain.last().expect("constructed directory chain").1
    }
    fn guard(&self) -> io::Result<()> {
        for (path, file, pin) in &self.chain {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)?;
            if f9(file)?[..5] != pin[..5] || f9(&named)?[..5] != pin[..5] {
                return Err(denied("working return held directory identity changed"));
            }
        }
        let pin = f9(self.file())?;
        if pin[2] != u64::from(libc::S_IFDIR | 0o700)
            || pin[3..5] != [0, 0]
            || held::label(self.file())? != self.label
        {
            return Err(denied(
                "working return directory is not its exact normal labelled private inode",
            ));
        }
        Ok(())
    }
    fn create_directory(
        &self,
        name: &'static str,
        label: &'static [u8],
        allow_existing: bool,
    ) -> io::Result<Self> {
        self.guard()?;
        let leaf = CString::new(name).unwrap();
        if unsafe { libc::mkdirat(self.file().as_raw_fd(), leaf.as_ptr(), 0o700) } != 0 {
            let e = io::Error::last_os_error();
            if !allow_existing || e.raw_os_error() != Some(libc::EEXIST) {
                return Err(e);
            }
        }
        let result = Self::open(&self.path.join(name), label)?;
        self.file().sync_all()?;
        self.guard()?;
        Ok(result)
    }
    fn create_file(&self, name: &str, label: &'static [u8]) -> io::Result<File> {
        self.guard()?;
        if name.is_empty()
            || name.len() > 64
            || name
                .bytes()
                .any(|v| !v.is_ascii_alphanumeric() && !b".-_".contains(&v))
        {
            return Err(denied("working return has no such fixed evidence member"));
        }
        let name = CString::new(name).map_err(io::Error::other)?;
        let fd = unsafe {
            libc::openat(
                self.file().as_raw_fd(),
                name.as_ptr(),
                libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        use std::os::fd::FromRawFd;
        let file = unsafe { File::from_raw_fd(fd) };
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o600)
            || pin[3..7] != [0, 0, 1, 0]
            || held::label(&file)? != label
        {
            return Err(denied(
                "working return created file lacks its normal finite MAC transition",
            ));
        }
        self.file().sync_all()?;
        self.guard()?;
        Ok(file)
    }
}
struct Input {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    sha: String,
    label: &'static [u8],
}
impl Input {
    fn open(
        directory: &Directory,
        name: &'static str,
        label: &'static [u8],
        maximum: u64,
        end: Instant,
    ) -> io::Result<Self> {
        live(end)?;
        directory.guard()?;
        let path = directory.path.join(name);
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o400)
            || pin[3..6] != [0, 0, 1]
            || pin[6] > maximum
            || held::label(&file)? != label
        {
            return Err(denied(
                "protected working evidence is not its normal sealed root inode",
            ));
        }
        let mut value = Self {
            path,
            file,
            pin,
            sha: String::new(),
            label,
        };
        let raw = value.read_unhashed(end)?;
        value.sha = sha(&raw);
        value.guard()?;
        directory.guard()?;
        Ok(value)
    }
    fn guard(&self) -> io::Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&self.path)?;
        if f9(&self.file)? != self.pin
            || f9(&named)? != self.pin
            || held::label(&self.file)? != self.label
            || held::label(&named)? != self.label
        {
            return Err(denied(
                "protected working evidence changed held/named inode or normal MAC label",
            ));
        }
        Ok(())
    }
    fn read_unhashed(&self, end: Instant) -> io::Result<Vec<u8>> {
        self.guard()?;
        live(end)?;
        let mut raw = vec![0; self.pin[6] as usize];
        for (index, part) in raw.chunks_mut(65536).enumerate() {
            live(end)?;
            self.file.read_exact_at(part, (index * 65536) as u64)?;
        }
        if self.file.read_at(&mut [0; 1], self.pin[6])? != 0 {
            return Err(denied("protected evidence grew"));
        }
        live(end)?;
        self.guard()?;
        Ok(raw)
    }
    fn bytes(&self, end: Instant) -> io::Result<Vec<u8>> {
        let raw = self.read_unhashed(end)?;
        if sha(&raw) != self.sha {
            return Err(denied("protected evidence changed full contents"));
        }
        Ok(raw)
    }
    fn compare(&self, record: &Value) -> io::Result<()> {
        let pin: [u64; 9] =
            serde_json::from_value(record["f9"].clone()).map_err(io::Error::other)?;
        if record["path"] != json!(self.path)
            || record["bytes"] != self.pin[6]
            || record["sha256"] != self.sha
            || pin != self.pin
        {
            return Err(denied(
                "protected evidence differs from its captured whole-file commitment",
            ));
        }
        self.guard()
    }
    fn compare_payload(&self, record: &Value) -> io::Result<()> {
        if record["path"] != json!(self.path)
            || record["bytes"] != self.pin[6]
            || record["sha256"] != self.sha
        {
            return Err(denied(
                "protected source payload differs from the captured physical plan",
            ));
        }
        self.guard()
    }
    fn observation(&self) -> Value {
        json!({"path":self.path,"bytes":self.pin[6],"sha256":self.sha,"f9":self.pin})
    }
}
struct RetiredSourceLock {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
}
impl RetiredSourceLock {
    fn open(root: &Directory, name: &'static str, record: &Value) -> io::Result<Self> {
        root.guard()?;
        let path = root.path.join(name);
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&path)?;
        let pin = f9(&file)?;
        let captured: [u64; 9] =
            serde_json::from_value(record["f9"].clone()).map_err(io::Error::other)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o600)
            || pin[3..7] != [0, 0, 1, 0]
            || record["name"] != name
            || captured != pin
            || held::label(&file)? != layout::WORKING_SOURCE_LOCK_LABEL
        {
            return Err(denied(
                "working source lock is not the exact fresh captured inode",
            ));
        }
        // A new open description can acquire this only after every inherited
        // exclusive description from the real parent and suite has closed.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let value = Self { path, file, pin };
        value.guard()?;
        root.guard()?;
        Ok(value)
    }
    fn guard(&self) -> io::Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&self.path)?;
        if f9(&self.file)? != self.pin
            || f9(&named)? != self.pin
            || held::label(&self.file)? != layout::WORKING_SOURCE_LOCK_LABEL
            || held::label(&named)? != layout::WORKING_SOURCE_LOCK_LABEL
        {
            return Err(denied("retired source lock changed"));
        }
        // The retained return OFD must still exclude a separate opener.
        if unsafe { libc::flock(named.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0 {
            return Err(denied(
                "return lost its fresh exclusive source-lock retirement observation",
            ));
        }
        if io::Error::last_os_error().raw_os_error() != Some(libc::EWOULDBLOCK) {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
}
pub(super) struct ProtectedRun {
    root: Directory,
    canonical_inputs: Directory,
    inputs: Vec<Input>,
    locks: [RetiredSourceLock; 2],
    observation: Value,
}
impl ProtectedRun {
    pub(super) fn observe(boot: &BootOwner, parent: &RetiredWorkingParent) -> io::Result<Self> {
        parent.guard(boot).map_err(|e| denied(&e))?;
        if !parent.clean() {
            return Err(denied(
                "failed parent cannot authenticate a complete physical run",
            ));
        }
        let end = parent.deadline();
        let root = Directory::open(
            &boot.config().runtime_evidence_directory(),
            layout::WORKING_EVIDENCE_DIRECTORY_LABEL,
        )?;
        let capture = Input::open(
            &root,
            layout::WORKING_CAPTURE_FILE,
            layout::WORKING_CAPTURE_FILE_LABEL,
            1024 * 1024,
            end,
        )?;
        let raw = capture.bytes(end)?;
        let value: Value = serde_json::from_slice(&raw).map_err(io::Error::other)?;
        if value["schema"] != "droidloom.captured-physical-application-run.v1"
            || value["source_factory_complete_captured"] != true
            || value["runtime_qualified"] != false
            || value["production_ready"] != false
            || value["requires_independent_parent_retirement_and_private_copy_return"] != true
        {
            return Err(denied(
                "working capture is not the current source factory's incomplete-return record",
            ));
        }
        parent
            .compare_capture(&value["actual_parent"], boot)
            .map_err(|e| denied(&e))?;
        let child = &value["actual_child"];
        if !child["pid"]
            .as_u64()
            .is_some_and(|n| n > 1 && n != u64::from(parent.parent_pid()))
            || !child["start_ticks"].as_u64().is_some_and(|n| n > 0)
            || child["exit_code"] != 0
            || child["direct_child_reaped"] != true
            || child["all_child_cgroups_absent"] != true
            || child["every_frame_scm_credentials_checked"] != true
        {
            return Err(denied(
                "working capture does not record its actual retired private suite",
            ));
        }
        let plan = Input::open(
            &root,
            layout::WORKING_PLAN_FILE,
            layout::WORKING_PLAN_FILE_LABEL,
            4 * 1024 * 1024,
            end,
        )?;
        let binding = Input::open(
            &root,
            layout::WORKING_MAIN_BINDING_FILE,
            layout::WORKING_MAIN_BINDING_FILE_LABEL,
            BINDING_LIMIT as u64,
            end,
        )?;
        let summary = Input::open(
            &root,
            "applications.stdout",
            layout::WORKING_APPLICATION_OUTPUT_LABEL,
            SUMMARY_LIMIT as u64,
            end,
        )?;
        let stderr = Input::open(
            &root,
            "applications.stderr",
            layout::WORKING_APPLICATION_OUTPUT_LABEL,
            1024 * 1024,
            end,
        )?;
        for (input, key) in [
            (&plan, "plan"),
            (&binding, "main_binding"),
            (&summary, "summary"),
            (&stderr, "stderr"),
        ] {
            input.compare(&value[key])?;
        }
        let main: crate::main_custody::RuntimeMainCustody =
            serde_json::from_slice(&binding.bytes(end)?).map_err(io::Error::other)?;
        boot.compare_protected_main(&main)?;
        let complete = super::super::super::capture::compare_summary(
            &summary.bytes(end)?,
            &plan.path,
            plan.pin[6],
            &plan.sha,
            &main.epoch,
        )?;
        let physical_plan: Value =
            serde_json::from_slice(&plan.bytes(end)?).map_err(io::Error::other)?;
        let runtime_plan = Input::open(
            &root,
            layout::WORKING_RUNTIME_PLAN_FILE,
            layout::WORKING_RUNTIME_PLAN_FILE_LABEL,
            16 * 1024 * 1024,
            end,
        )?;
        runtime_plan.compare_payload(&physical_plan["runtime_plan"])?;
        if physical_plan["schema"] != "droidloom.physical-application-plan.v1" {
            return Err(denied(
                "protected physical plan is not the normal source schema",
            ));
        }
        let candidate = layout::working_candidate_directory(&boot.config().candidate_id)
            .ok_or_else(|| denied("protected material candidate absent"))?;
        let canonical_inputs = Directory::open(
            &candidate.join(layout::WORKING_INPUT_DIRECTORY),
            layout::WORKING_INPUT_DIRECTORY_LABEL,
        )?;
        let admitted = Input::open(
            &canonical_inputs,
            layout::WORKING_ADMITTED_MATERIALS_FILE,
            layout::WORKING_INPUT_FILE_LABEL,
            16 * 1024 * 1024,
            end,
        )?;
        if admitted.sha != boot.config().admitted_materials_sha256 {
            return Err(denied(
                "returned working source materials differ from this actual boot",
            ));
        }
        let admitted_value: Value =
            serde_json::from_slice(&admitted.bytes(end)?).map_err(io::Error::other)?;
        let documents = admitted_value["public_materials"]["documents"]
            .as_array()
            .ok_or_else(|| denied("four protected current material roles absent"))?;
        if admitted_value["schema"] != "droidloom.working-qualification-admitted-materials.v1"
            || admitted_value["candidate_id"] != boot.config().candidate_id
            || documents.len() != 4
        {
            return Err(denied(
                "protected working material roles or candidate differ",
            ));
        }
        let mut material_inputs = Vec::new();
        for (name, record) in layout::WORKING_APPLICATION_INPUT_FILES
            .into_iter()
            .zip(documents)
        {
            let input = Input::open(
                &canonical_inputs,
                name,
                layout::WORKING_INPUT_FILE_LABEL,
                16 * 1024 * 1024,
                end,
            )?;
            if record["source"]["bytes"] != input.pin[6] || record["source"]["sha256"] != input.sha
            {
                return Err(denied(
                    "protected copied material bytes differ from the admitted source role",
                ));
            }
            material_inputs.push(input);
        }
        let gates = Input::open(
            &canonical_inputs,
            layout::WORKING_GATE_REGISTRY_FILE,
            layout::WORKING_INPUT_FILE_LABEL,
            1024 * 1024,
            end,
        )?;
        if complete["gate_registry"]["bytes"] != gates.pin[6]
            || complete["gate_registry"]["sha256"] != gates.sha
        {
            return Err(denied(
                "protected gates differ from the full source-owned 39/377 registry",
            ));
        }
        material_inputs.extend([admitted, gates]);
        let source = &value["working_source"];
        let applications: [u64; 9] = serde_json::from_value(source["applications"]["f9"].clone())
            .map_err(io::Error::other)?;
        if source["schema"] != "droidloom.working-native-source-custody.v1"
            || source["runtime_evidence_directory"] != json!(root.path)
            || source["applications"]["path"] != contract::APPLICATIONS_EXECUTABLE
            || source["applications"]["bytes"] != boot.config().applications.bytes
            || source["applications"]["sha256"] != boot.config().applications.sha256
            || applications != boot.applications_identity()?
            || source["actual_pid"] != parent.parent_pid()
            || source["historical_original_lock_identity_claimed"] != false
        {
            return Err(denied(
                "working capture does not retain the actual installed source generation",
            ));
        }
        let locks = [
            RetiredSourceLock::open(&root, "source.lock", &source["fresh_source_lock"])?,
            RetiredSourceLock::open(&root, "application.lock", &source["fresh_application_lock"])?,
        ];
        if locks[0].pin[..2] == locks[1].pin[..2] {
            return Err(denied("retired source-lock roles share an inode"));
        }
        let owner = &value["original_working_owner"];
        let bound = &owner["boot"];
        let start = parent.parent_start_ns().map_err(|e| denied(&e))?;
        let end_ns = contract::WorkingSchedule::selected().authorization_end_ns(start)?;
        let watchdog = &owner["watchdog"];
        let last = watchdog["last_keepalive_monotonic_ns"]
            .as_u64()
            .ok_or_else(|| denied("captured watchdog last pulse absent"))?;
        if owner["schema"] != "droidloom.working-owner-progress-custody.v1"
            || owner["owner_start_monotonic_ns"] != start
            || owner["original_authorization_end_monotonic_ns"] != end_ns
            || owner["bootstrap_main_observed_once"] != true
            || owner["detached_feeder"] != false
            || owner["private_original_data_opened"] != false
            || bound["schema"] != "droidloom.working-boot-source-custody.v1"
            || bound["candidate_id"] != boot.config().candidate_id
            || bound["first_once_candidate"] != boot.config().first_once_candidate
            || bound["actual_boot_id"] != boot.boot_id()
            || bound["host_source_commit"] != boot.config().host_source_commit
            || bound["host_source_tree"] != boot.config().host_source_tree
            || bound["joint_policy_sha256"] != boot.config().joint_policy_sha256
            || bound["admitted_materials_sha256"] != boot.config().admitted_materials_sha256
            || bound["applications"]
                != serde_json::to_value(&boot.config().applications).map_err(io::Error::other)?
            || bound["selection"]
                != serde_json::to_value(&boot.config().selection).map_err(io::Error::other)?
            || bound["cell"]
                != serde_json::to_value(&boot.config().cell).map_err(io::Error::other)?
            || watchdog["schema"] != "droidloom.working-watchdog-custody.v1"
            || watchdog["interval_seconds"] != contract::WATCHDOG_INTERVAL_SECONDS
            || watchdog["same_parent_pid"] != parent.parent_pid()
            || !watchdog["successful_keepalives"]
                .as_u64()
                .is_some_and(|n| n > 0)
            || last < start
            || last >= end_ns
            || last > parent.parent_exit_ns().map_err(|e| denied(&e))?
            || watchdog["write_calls"] != 0
            || watchdog["set_timeout_calls"] != 0
            || watchdog["disable_calls"] != 0
            || watchdog["descriptor_passed_to_child"] != false
        {
            return Err(denied(
                "protected capture differs from the actual original boot authorization",
            ));
        }
        let observation = json!({"schema":"droidloom.working-protected-capture-retired.v1",
            "candidate_id":boot.config().candidate_id,"actual_boot_id":boot.boot_id(),"capture":capture.observation(),
            "summary":summary.observation(),"main_binding":binding.observation(),"physical_plan":plan.observation(),
            "stderr":stderr.observation(),"runtime_plan":runtime_plan.observation(),
            "canonical_inputs":material_inputs.iter().map(Input::observation).collect::<Vec<_>>(),"selected_applications":39,"required_gates":377,
            "compiled_cases":contract::budget::CASE_COUNT,"actual_parent_retirement":parent.observation(),
            "inherited_source_ofds_retired":true,"fresh_return_ofds_retained":true,
            "live_main_reconstructed_from_json":false,"live_complete_reconstructed_from_json":false,
            "original_return_observed":false,"production_ready":false});
        let mut inputs = vec![capture, plan, runtime_plan, binding, summary, stderr];
        inputs.extend(material_inputs);
        let result = Self {
            root,
            canonical_inputs,
            inputs,
            locks,
            observation,
        };
        result.guard()?;
        parent.guard(boot).map_err(|e| denied(&e))?;
        Ok(result)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        self.root.guard()?;
        self.canonical_inputs.guard()?;
        for input in &self.inputs {
            input.guard()?;
        }
        for lock in &self.locks {
            lock.guard()?;
        }
        self.root.guard()?;
        self.canonical_inputs.guard()
    }
    pub(super) fn observation(&self) -> io::Result<Value> {
        self.guard()?;
        Ok(self.observation.clone())
    }
}

#[derive(Clone, Copy)]
pub(super) enum Record {
    CandidateObserved,
    CaptureObserved,
    CaptureRejected,
    CollectionObserved,
    ReturnSelected,
    ReturnRequested,
    CommandIntent(MaintenanceOperation),
    CommandResult(MaintenanceOperation),
}
impl Record {
    fn name(self) -> String {
        match self {
            Self::CandidateObserved => "CANDIDATE-OBSERVED.json".into(),
            Self::CaptureObserved => "CAPTURE-OBSERVED.json".into(),
            Self::CaptureRejected => "CAPTURE-REJECTED.json".into(),
            Self::CollectionObserved => "COLLECTION-OBSERVED.json".into(),
            Self::ReturnSelected => "RETURN-SELECTED.json".into(),
            Self::ReturnRequested => "RETURN-REQUESTED.json".into(),
            Self::CommandIntent(operation) => format!("{}-INTENT.json", operation.name()),
            Self::CommandResult(operation) => format!("{}-RESULT.json", operation.name()),
        }
    }
}
pub(super) struct Evidence {
    candidate: Directory,
    boot: Directory,
    directory: Directory,
    lock: File,
    lock_pin: [u64; 9],
}
pub(super) struct CommandOutputs {
    pub(super) stdout: File,
    pub(super) stderr: File,
    operation: MaintenanceOperation,
}
impl Evidence {
    pub(super) fn create(boot: &BootOwner) -> io::Result<Self> {
        boot.require_return()?;
        let root = layout::working_candidate_directory(&boot.config().candidate_id)
            .ok_or_else(|| denied("working candidate path absent"))?;
        let candidate = Directory::open(&root, layout::WORKING_CANDIDATE_DIRECTORY_LABEL)?;
        let boot_dir = candidate.create_directory(
            layout::WORKING_BOOT_EVIDENCE_DIRECTORY,
            layout::WORKING_BOOT_EVIDENCE_DIRECTORY_LABEL,
            true,
        )?;
        let directory = boot_dir.create_directory(
            layout::WORKING_RETURN_EVIDENCE_DIRECTORY,
            layout::WORKING_RETURN_EVIDENCE_DIRECTORY_LABEL,
            false,
        )?;
        let lock = directory.create_file("return.lock", layout::WORKING_RETURN_LOCK_LABEL)?;
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let lock_pin = f9(&lock)?;
        let value = Self {
            candidate,
            boot: boot_dir,
            directory,
            lock,
            lock_pin,
        };
        value.guard()?;
        Ok(value)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        self.candidate.guard()?;
        self.boot.guard()?;
        self.directory.guard()?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(self.directory.path.join("return.lock"))?;
        if f9(&self.lock)? != self.lock_pin
            || f9(&named)? != self.lock_pin
            || held::label(&self.lock)? != layout::WORKING_RETURN_LOCK_LABEL
            || held::label(&named)? != layout::WORKING_RETURN_LOCK_LABEL
        {
            return Err(denied("independent return evidence ownership changed"));
        }
        Ok(())
    }
    pub(super) fn record(&self, name: Record, value: Value, end: Instant) -> io::Result<()> {
        live(end)?;
        self.guard()?;
        let mut raw = serde_json::to_vec_pretty(&value).map_err(io::Error::other)?;
        raw.push(b'\n');
        if raw.len() > 1024 * 1024 {
            return Err(denied("working return record exceeds source bound"));
        }
        let path = name.name();
        let mut file = self
            .directory
            .create_file(&path, layout::WORKING_RETURN_EVIDENCE_FILE_LABEL)?;
        file.write_all(&raw)?;
        file.sync_all()?;
        let pin = f9(&file)?;
        let mut back = vec![0; raw.len()];
        file.read_exact_at(&mut back, 0)?;
        if raw != back || f9(&file)? != pin || file.read_at(&mut [0; 1], raw.len() as u64)? != 0 {
            return Err(denied("working return record whole-file readback failed"));
        }
        file.set_permissions(fs::Permissions::from_mode(0o400))?;
        file.sync_all()?;
        let sealed = f9(&file)?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(self.directory.path.join(&path))?;
        if sealed[2] != u64::from(libc::S_IFREG | 0o400)
            || sealed[3..6] != [0, 0, 1]
            || sealed[6] != raw.len() as u64
            || f9(&named)? != sealed
            || held::label(&file)? != layout::WORKING_RETURN_EVIDENCE_FILE_LABEL
            || held::label(&named)? != layout::WORKING_RETURN_EVIDENCE_FILE_LABEL
        {
            return Err(denied(
                "sealed working return record named identity or label changed",
            ));
        }
        self.directory.file().sync_all()?;
        self.guard()?;
        live(end)
    }
    pub(super) fn command_outputs(
        &self,
        operation: MaintenanceOperation,
    ) -> io::Result<CommandOutputs> {
        self.guard()?;
        let stdout = self.directory.create_file(
            &format!("{}.stdout", operation.name()),
            layout::WORKING_RETURN_EVIDENCE_FILE_LABEL,
        )?;
        let stderr = self.directory.create_file(
            &format!("{}.stderr", operation.name()),
            layout::WORKING_RETURN_EVIDENCE_FILE_LABEL,
        )?;
        Ok(CommandOutputs {
            stdout,
            stderr,
            operation,
        })
    }
    pub(super) fn output_bounds(&self, outputs: &CommandOutputs) -> io::Result<()> {
        self.guard()?;
        if outputs.stdout.metadata()?.len() > 64 * 1024 * 1024
            || outputs.stderr.metadata()?.len() > 65536
        {
            return Err(denied(
                "normal maintenance output exceeded its fixed bounds",
            ));
        }
        Ok(())
    }
    pub(super) fn seal_outputs(
        &self,
        outputs: CommandOutputs,
        end: Instant,
    ) -> io::Result<(Value, Vec<u8>)> {
        self.output_bounds(&outputs)?;
        live(end)?;
        let mut pins = serde_json::Map::new();
        let mut stdout = Vec::new();
        for (suffix, file, max) in [
            ("stdout", outputs.stdout, 64 * 1024 * 1024),
            ("stderr", outputs.stderr, 65536),
        ] {
            let path = self
                .directory
                .path
                .join(format!("{}.{suffix}", outputs.operation.name()));
            let before = f9(&file)?;
            if before[2] != u64::from(libc::S_IFREG | 0o600)
                || before[3..6] != [0, 0, 1]
                || before[6] > max
                || held::label(&file)? != layout::WORKING_RETURN_EVIDENCE_FILE_LABEL
            {
                return Err(denied(
                    "normal maintenance output metadata differs before sealing",
                ));
            }
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&path)?;
            let mut raw = vec![0; before[6] as usize];
            for (index, part) in raw.chunks_mut(65536).enumerate() {
                live(end)?;
                file.read_exact_at(part, (index * 65536) as u64)?;
            }
            if file.read_at(&mut [0; 1], before[6])? != 0
                || f9(&file)? != before
                || f9(&named)? != before
            {
                return Err(denied(
                    "normal maintenance output changed after actual child retirement",
                ));
            }
            file.set_permissions(fs::Permissions::from_mode(0o400))?;
            file.sync_all()?;
            let pin = f9(&file)?;
            if f9(&named)? != pin {
                return Err(denied("sealed maintenance output named identity differs"));
            }
            pins.insert(
                suffix.into(),
                json!({"path":path,"bytes":pin[6],"sha256":sha(&raw),"f9":pin}),
            );
            if suffix == "stdout" {
                stdout = raw;
            }
        }
        self.directory.file().sync_all()?;
        self.guard()?;
        live(end)?;
        Ok((Value::Object(pins), stdout))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_return_fresh_ofd_waits_for_the_last_inherited_source_description() {
        use std::os::unix::fs::OpenOptionsExt;
        let path = std::env::temp_dir().join(format!(
            "droidloom-return-ofd-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let parent = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        assert_eq!(
            unsafe { libc::flock(parent.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        let inherited = parent.try_clone().unwrap();
        let original = f9(&parent).unwrap();
        let fresh = File::open(&path).unwrap();
        assert_ne!(
            unsafe { libc::flock(fresh.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(parent);
        assert_ne!(
            unsafe { libc::flock(fresh.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(inherited);
        assert_eq!(
            unsafe { libc::flock(fresh.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert_eq!(f9(&fresh).unwrap(), original);
        drop(fresh);
        fs::remove_file(path).unwrap();
    }
}
