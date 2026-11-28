//! Actual parent-owned child execution and full private Complete capture.
use super::super::application_leaf_unit::qualification::{KernelProfile, UnitOwner};
use super::*;
use crate::development::owned_process::open_pidfd;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::io::{Read, Write};
use std::os::fd::{AsFd, FromRawFd, OwnedFd};
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, ExitStatus, Stdio};
#[path = "physical_qualification_roster.rs"]
mod roster;
#[path = "working_qualification_preparation_capture.rs"]
mod preparation_capture;
pub use preparation_capture::capture_prepared_working_run;
pub(crate) use preparation_capture::PreparationHistory;

// The working variant owns the original singleton/watchdog throughout this
// capture. It never reacquires a template owner or starts another authority clock.
enum RunOwner {
    Template(UnitOwner),
    Working(crate::working_qualification::WorkingQualificationOwner),
}
impl RunOwner {
    fn unit(&self) -> &UnitOwner {
        match self { Self::Template(v)=>v, Self::Working(v)=>v.unit() }
    }
    fn unit_mut(&mut self) -> &mut UnitOwner {
        match self { Self::Template(v)=>v, Self::Working(v)=>v.unit_mut() }
    }
    fn boundary(&self, child:Option<&BoundProcess>, end:Instant)->Result<(),String> {
        if let Self::Working(v)=self { v.guard_local(child,end)?; }
        self.unit().boundary(child,end)
    }
    fn child_guard(&self, child:&BoundProcess)->Result<(),String> { self.unit().child_guard(child) }
    fn switch(&mut self, profile:KernelProfile, child:&BoundProcess,end:Instant)->Result<(),String> {
        self.unit_mut().switch(profile,child,end)
    }
    fn pump(&mut self, child:&BoundProcess,end:Instant)->Result<(),String> {
        if let Self::Working(v)=self { v.pump(Some(child),end)?; }
        Ok(())
    }
    fn child_transition(&self)->Option<libc::c_int> {
        match self { Self::Template(_)=>None,Self::Working(v)=>Some(v.close_in_child()) }
    }
    fn compare_epoch(&self, epoch:&RuntimeEpoch)->Result<(),String> {
        if let Self::Working(v)=self { v.compare_physical_epoch(epoch)?; }
        Ok(())
    }
    fn compare_binding(&self, binding:&RuntimeMainCustody)->Result<(),String> {
        if let Self::Working(v)=self { v.compare_physical_binding(binding)?; }
        Ok(())
    }
    fn begin(&mut self,end:Instant)->Result<(),String> {
        if let Self::Working(v)=self { v.begin_physical(end)?; }
        Ok(())
    }
    fn finish(&mut self,end:Instant)->Result<(),String> {
        if let Self::Working(v)=self { v.finish_physical(end)?; }
        Ok(())
    }
    fn record_failure(&mut self,reason:&str)->Result<Value,String> {
        match self {
            Self::Template(_)=>Ok(json!({"working_singleton":false})),
            Self::Working(v)=>v.record_failure(reason),
        }
    }
    fn observation(&self)->Value {
        match self {Self::Template(v)=>v.observation(),Self::Working(v)=>v.observation()}
    }
}

struct Output {
    file: File,
    path: PathBuf,
    bytes: u64,
    hash: Sha256,
    limit: u64,
    eof: bool,
}
impl Output {
    fn create(plan: &Plan, name: &str, limit: u64) -> io::Result<Self> {
        let path = plan
            .path
            .parent()
            .ok_or_else(|| error("physical plan parent absent"))?
            .join(name);
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o600) || pin[3..6] != [0, 0, 1] {
            return Err(error("physical output must be a new root private inode"));
        }
        Ok(Self {
            file,
            path,
            bytes: 0,
            hash: Sha256::new(),
            limit,
            eof: false,
        })
    }
    fn drain(&mut self, pipe: &mut impl Read) -> io::Result<()> {
        let mut buffer = [0u8; 32768];
        loop {
            match pipe.read(&mut buffer) {
                Ok(0) => {
                    self.eof = true;
                    return Ok(());
                }
                Ok(n) => {
                    self.bytes = self
                        .bytes
                        .checked_add(n as u64)
                        .ok_or_else(|| error("physical output overflow"))?;
                    if self.bytes > self.limit {
                        return Err(error("physical normal output exceeded full capture bound"));
                    }
                    self.file.write_all(&buffer[..n])?;
                    self.hash.update(&buffer[..n]);
                }
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
                Err(e) => return Err(e),
            }
        }
    }
    fn digest(&self) -> String {
        format!("{:x}", self.hash.clone().finalize())
    }
    fn seal(self) -> io::Result<SealedOutput> {
        self.file.sync_all()?;
        let pin = f9(&self.file)?;
        if pin[6] != self.bytes || pin[3..6] != [0, 0, 1] {
            return Err(error("physical capture inode size or owner changed"));
        }
        let digest = self.digest();
        let result = SealedOutput {
            path: self.path,
            file: self.file,
            pin,
            sha: digest,
        };
        result.guard()?;
        Ok(result)
    }
}
struct SealedOutput {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    sha: String,
}
impl SealedOutput {
    fn guard(&self) -> io::Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&self.path)?;
        if f9(&named)? != self.pin || f9(&self.file)? != self.pin {
            return Err(error("physical captured output changed"));
        }
        let mut h = Sha256::new();
        let mut offset = 0;
        let mut raw = [0u8; 32768];
        while offset < self.pin[6] {
            let n = self.file.read_at(&mut raw, offset)?;
            if n == 0 {
                return Err(error("physical captured output shortened"));
            }
            h.update(&raw[..n]);
            offset += n as u64;
        }
        if offset != self.pin[6]
            || format!("{:x}", h.finalize()) != self.sha
            || self.file.read_at(&mut [0; 1], offset)? != 0
            || f9(&self.file)? != self.pin
        {
            return Err(error("physical captured full output differs"));
        }
        Ok(())
    }
    fn observation(&self) -> Value {
        json!({"path":self.path,"bytes":self.pin[6],"sha256":self.sha,"f9":self.pin})
    }
}

struct ChildOwner {
    child: Child,
    pidfd: OwnedFd,
    pid: u32,
    reaped: Option<ExitStatus>,
}
impl ChildOwner {
    fn try_wait(&mut self) -> io::Result<Option<ExitStatus>> {
        if self.reaped.is_none() {
            self.reaped = self.child.try_wait()?;
        }
        Ok(self.reaped)
    }
    fn stop(&mut self, end: Instant) -> io::Result<()> {
        if self.try_wait()?.is_some() {
            return Ok(());
        }
        // The PIDFD belongs to the unreaped direct child; never signal a caller PID.
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGTERM,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        let graceful = end.min(Instant::now() + Duration::from_secs(10));
        while Instant::now() < graceful {
            if self.try_wait()?.is_some() {
                return Ok(());
            }
            let _ = socket::wait(self.pidfd.as_raw_fd(), libc::POLLIN, graceful);
        }
        if self.try_wait()?.is_some() {
            return Ok(());
        }
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        socket::wait(self.pidfd.as_raw_fd(), libc::POLLIN, end)?;
        self.try_wait()?
            .ok_or_else(|| error("physical direct child remains unreaped"))?;
        Ok(())
    }
}
impl Drop for ChildOwner {
    fn drop(&mut self) {
        // Error paths preserve the unit profile and let its unchanged KillMode
        // retire remaining descendants. This is not a success receipt.
        if self.reaped.is_none() {
            unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    self.pidfd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                );
            }
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
enum Phase {
    Hello,
    Between(u8),
    Case { ordinal: u8, end_ns: u64 },
    Complete,
}
struct PendingComplete {
    header: CompleteHeader,
    binding: RuntimeMainCustody,
    body: Vec<u8>,
    packet: socket::Packet,
}

// This is a comparison of this actual child's committed output. It cannot
// create an application Complete or turn a saved summary into runtime authority.
fn validate_case_summaries(package: &str, row: &Value, epoch: &RuntimeEpoch) -> io::Result<usize> {
    let expected = (0..CASE_COUNT)
        .map(|ordinal| QualificationCase::from_ordinal(ordinal as u8))
        .collect::<io::Result<Vec<_>>>()?
        .into_iter().filter(|case| case.package() == package).collect::<Vec<_>>();
    let actual = row.get("cases").and_then(Value::as_array)
        .ok_or_else(|| error("complete row omitted its actual case histories"))?;
    if expected.is_empty() || actual.len() != expected.len() {
        return Err(error("complete row does not have its exact source-owned case histories"));
    }
    let epoch = serde_json::to_value(epoch)?;
    for (case, history) in expected.iter().zip(actual) {
        let kind_matches = match (case.native_route(), *case) {
            (Some(route), _) => history.get("route") == Some(&json!(route)) && history.get("kind").is_none(),
            (None, QualificationCase::CameraPhotoCaptureReopen) =>
                history.get("kind") == Some(&json!("camera_photo_capture_reopen")) && history.get("route").is_none(),
            (None, QualificationCase::SettingsPermissionInterfaces) =>
                history.get("kind") == Some(&json!("settings_permission_interfaces")) && history.get("route").is_none(),
            (None, _) => history.get("kind") == Some(&json!("family_observation")) && history.get("route").is_none(),
        };
        if !kind_matches
            || history.get("sealed_inside_original_case_window") != Some(&json!(true))
            || history.get("historical_observation") != Some(&json!(true))
            || history.get("continuous_app_or_target_directory_custody_after_case_claimed") != Some(&json!(false))
            || history.get("actual").and_then(|v| v.get("package")) != Some(&json!(package))
            || history.get("actual").and_then(|v| v.get("user")) != Some(&json!(0))
            || history.get("actual").and_then(|v| v.get("epoch")) != Some(&epoch)
        {
            return Err(error("complete historical case order, subject or original window differs"));
        }
    }
    Ok(actual.len())
}

fn validate_summary(raw: &[u8], plan: &Plan, epoch: &RuntimeEpoch) -> io::Result<Value> {
    if raw.last() != Some(&b'\n') {
        return Err(error(
            "complete summary requires its entire normal trailing newline",
        ));
    }
    let value: Value = serde_json::from_slice(raw)?;
    let get = |k: &str| {
        value
            .get(k)
            .ok_or_else(|| error("complete summary omitted a normal field"))
    };
    if get("schema")? != "droidloom.physical-application-run.v1"
        || get("selected_applications")? != 41
        || get("required_gates")? != 401
        || get("observed_cases")? != CASE_COUNT
        || get("accepted_applications")? != 41
        || get("accepted_gates")? != 401
        || get("runtime_qualified")? != true
        || get("production_ready")? != true
        || get("automatic_retry")? != false
        || !get("retained_failure")?.is_null()
        || get("epoch")? != &serde_json::to_value(epoch)?
        || get("original_window_seconds")? != SUITE_SECONDS
        || get("gate_registry")?.get("bytes") != Some(&json!(32_688))
        || get("gate_registry")?.get("sha256") != Some(&json!(roster::REGISTRY_SHA))
        || get("plan")?.get("sha256") != Some(&Value::String(plan.digest.clone()))
        || get("plan")?.get("bytes") != Some(&json!(plan.pin[6]))
        || get("plan")?.get("path") != Some(&json!(plan.path))
    {
        return Err(error(
            "actual complete summary is partial or belongs to another plan/epoch",
        ));
    }
    let rows = get("applications")?
        .as_array()
        .ok_or_else(|| error("complete application rows absent"))?;
    let mut packages = BTreeSet::new();
    let mut gates = 0;
    let mut observed_cases = 0;
    for row in rows {
        let package = row
            .get("package")
            .and_then(Value::as_str)
            .ok_or_else(|| error("complete package absent"))?;
        if !packages.insert(package)
            || row.get("runtime_qualified") != Some(&Value::Bool(true))
            || row.get("production_ready") != Some(&Value::Bool(true))
            || row.get("blocked") != Some(&Value::Null)
            || !matches!(row.get("blocked_gates"), Some(Value::Array(blocked)) if blocked.is_empty())
        {
            return Err(error("complete application row remains partial"));
        }
        observed_cases += validate_case_summaries(package, row, epoch)?;
        let assertions = row
            .get("gate_assertions")
            .and_then(Value::as_array)
            .ok_or_else(|| error("complete gate rows absent"))?;
        let mut ids = BTreeSet::new();
        for gate in assertions {
            let id = gate
                .get("id")
                .and_then(Value::as_str)
                .ok_or_else(|| error("complete gate id absent"))?;
            if !ids.insert(id) || gate.get("status") != Some(&Value::String("passed".into())) {
                return Err(error("complete gate is absent, duplicate or not passed"));
            }
        }
        let (_, business) = roster::PACKAGES
            .iter()
            .find(|(p, _)| *p == package)
            .ok_or_else(|| error("unselected package in actual Complete"))?;
        let expected: BTreeSet<&str> = roster::COMMON
            .iter()
            .chain(business.iter())
            .copied()
            .collect();
        if ids != expected {
            return Err(error(
                "actual Complete differs from exact source-owned per-package gate roster",
            ));
        }
        if row.get("accepted_gates") != Some(&json!(assertions.len())) {
            return Err(error("complete row gate count differs"));
        }
        gates += assertions.len();
    }
    if rows.len() != 41 || packages.len() != 41 || gates != 401 || observed_cases != CASE_COUNT {
        return Err(error(
            "actual complete producer did not cover the exact normal 41/401 roster",
        ));
    }
    // These structural comparisons cannot mint Complete. Provenance is the
    // held same-exec direct child and this run's private authenticated frame.
    Ok(value)
}

/// Parent-side historical capture of this run, not a deserialized App Complete.
/// The actual parent unit must still be externally retired after this process exits.
pub struct CapturedCompleteApplicationRun {
    owner: RunOwner,
    plan: Plan,
    summary: SealedOutput,
    stderr: SealedOutput,
    binding_output: SealedOutput,
    binding: RuntimeMainCustody,
    child_pid: u32,
    child_start: u64,
    end: Instant,
}
impl CapturedCompleteApplicationRun {
    /// Comparison metadata from this actual private child, not an authority constructor.
    pub fn binding(&self) -> &RuntimeMainCustody {
        &self.binding
    }
    pub fn guard(&self) -> Result<(), String> {
        self.owner.boundary(None, self.end)?;
        self.plan.guard().map_err(|e| e.to_string())?;
        for out in [&self.summary, &self.stderr, &self.binding_output] {
            out.guard().map_err(|e| e.to_string())?;
        }
        Ok(())
    }
    pub fn observation(&self) -> Value {
        json!({"schema":"droidloom.captured-physical-application-run.v1","plan":{"path":self.plan.path,
            "bytes":self.plan.pin[6],"sha256":self.plan.digest,"f9":self.plan.pin},
            "actual_parent":self.owner.observation(),"actual_child":{"pid":self.child_pid,
                "start_ticks":self.child_start,"exit_code":0,"direct_child_reaped":true,
                "all_child_cgroups_absent":true,"every_frame_scm_credentials_checked":true},
            "summary":self.summary.observation(),"stderr":self.stderr.observation(),
            "main_binding":self.binding_output.observation(),
            "source_factory_complete_captured":true,"runtime_qualified":false,
            "production_ready":false,"requires_independent_parent_retirement_and_private_copy_return":true})
    }
    /// Source-owned one-shot receipt. It is evidence for a later normal owner,
    /// never an API to restore this process-local capture from JSON.
    pub fn write_receipt(&self) -> Result<PathBuf, String> {
        self.guard()?;
        let mut out =
            Output::create(&self.plan, "CAPTURE.json", 1024 * 1024).map_err(|e| e.to_string())?;
        let mut bytes =
            serde_json::to_vec_pretty(&self.observation()).map_err(|e| e.to_string())?;
        bytes.push(b'\n');
        out.file.write_all(&bytes).map_err(|e| e.to_string())?;
        out.bytes = bytes.len() as u64;
        out.hash.update(&bytes);
        let path = out.path.clone();
        let sealed = out.seal().map_err(|e| e.to_string())?;
        self.guard()?;
        sealed.guard().map_err(|e| e.to_string())?;
        File::open(path.parent().ok_or("physical capture parent absent")?)
            .and_then(|f| f.sync_all())
            .map_err(|e| e.to_string())?;
        Ok(path)
    }
}

/// Called only by the normal installed applications parent CLI. No arbitrary
/// command, PID, resource profile, report or externally asserted pass is accepted.
pub fn capture_installed_physical_run(
    plan_sha: &str,
) -> Result<CapturedCompleteApplicationRun, String> {
    let initial_end = Instant::now() + Duration::from_secs(SUITE_SECONDS);
    let plan = Plan::open(plan_sha).map_err(|e| e.to_string())?;
    let owner = RunOwner::Template(UnitOwner::capture(plan_sha, initial_end)?);
    capture_actual(plan,owner,initial_end)
}
/// Crate-private continuation. The normal preparation owner supplies its retained
/// Plan; no public saved-report or replacement-owner constructor is added.
pub(crate) fn capture_working_physical_run(
    plan: Plan,
    mut owner: crate::working_qualification::WorkingQualificationOwner,
) -> Result<CapturedCompleteApplicationRun,String> {
    let end=owner.deadline().min(Instant::now()+Duration::from_secs(SUITE_SECONDS));
    plan.guard().map_err(|e|e.to_string())?;
    owner.bind_physical_plan(&plan.digest,end)?;
    capture_actual(plan,RunOwner::Working(owner),end)
}
fn capture_actual(plan:Plan, mut owner:RunOwner, initial_end:Instant)
    -> Result<CapturedCompleteApplicationRun,String> {
    let plan_sha=plan.digest.clone();
    let parent_end_ns = owner.unit().manager_deadline_ns()?;
    let mut end = instant_until(parent_end_ns, initial_end).map_err(|e| e.to_string())?;
    let mut stdout = Output::create(&plan, "applications.stdout", SUMMARY_LIMIT as u64)
        .map_err(|e| e.to_string())?;
    let mut stderr =
        Output::create(&plan, "applications.stderr", 1024 * 1024).map_err(|e| e.to_string())?;
    let (socket, child_socket) = socket::Socket::pair().map_err(|e| e.to_string())?;
    // Duplicate above all stdio/fixed channel FDs so pre_exec cannot alias them.
    let inherited =
        unsafe { libc::fcntl(child_socket.file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
    if inherited < 0 {
        return Err(io::Error::last_os_error().to_string());
    }
    let inherited = unsafe { OwnedFd::from_raw_fd(inherited) };
    let parent_pid = std::process::id();
    let mut command = Command::new(format!("/proc/self/fd/{}", owner.unit().executable().as_raw_fd()));
    command.arg0(EXE).args(
        child_argv(&plan_sha)
            .map_err(|e| e.to_string())?
            .into_iter()
            .skip(1),
    );
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C.UTF-8")
        .current_dir("/");
    let channel_fd = inherited.as_raw_fd();
    let working_watchdog = owner.child_transition();
    // SAFETY: only async-signal-safe descriptor/prctl operations before exec.
    unsafe {
        command.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                return Err(io::Error::last_os_error());
            }
            if libc::getppid() as u32 != parent_pid {
                return Err(error("physical parent died before child exec"));
            }
            if let Some(fd) = working_watchdog {
                crate::working_qualification::child_exec::prepare(
                    crate::working_qualification::child_exec::Kind::Physical, fd)?;
            }
            if libc::dup2(channel_fd, 3) < 0 || libc::fcntl(3, libc::F_SETFD, 0) < 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
    plan.guard().map_err(|e| e.to_string())?;
    owner.boundary(None, end)?;
    owner.begin(end)?;
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    drop(inherited);
    drop(child_socket);
    let pid = child.id();
    let pidfd = match open_pidfd(pid) {
        Ok(v) => v,
        Err(e) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("actual direct child PIDFD: {e}"));
        }
    };
    let mut output_pipe = child
        .stdout
        .take()
        .ok_or("normal child stdout pipe absent")?;
    let mut error_pipe = child
        .stderr
        .take()
        .ok_or("normal child stderr pipe absent")?;
    socket::nonblocking(output_pipe.as_raw_fd()).map_err(|e| e.to_string())?;
    socket::nonblocking(error_pipe.as_raw_fd()).map_err(|e| e.to_string())?;
    let mut child = ChildOwner {
        child,
        pidfd,
        pid,
        reaped: None,
    };
    let cleanup_end = initial_end + Duration::from_secs(RETIREMENT_SECONDS);
    let execute = (|| -> Result<(RuntimeMainCustody, u64, SealedOutput), String> {
        let bound = BoundProcess::capture(pid).map_err(|e| e.to_string())?;
        let mut phase = Phase::Hello;
        let mut sequence = 0u32;
        let mut epoch = None;
        let mut pending: Option<PendingComplete> = None;
        let mut captured_binding = None;
        loop {
            let until = match phase {
                Phase::Case {
                    end_ns: case_end, ..
                } => instant_until(case_end, end).map_err(|e| e.to_string())?,
                _ => end,
            };
            if Instant::now() >= until {
                return Err("physical producer exhausted its original case/suite end".into());
            }
            stdout.drain(&mut output_pipe).map_err(|e| e.to_string())?;
            stderr.drain(&mut error_pipe).map_err(|e| e.to_string())?;
            if phase != Phase::Complete && child.try_wait().map_err(|e|e.to_string())?.is_none() {
                owner.pump(&bound,until)?;
            }
            if pending.is_none() && phase != Phase::Complete {
                if let Some(packet) = socket.try_receive(pid).map_err(|e| e.to_string())? {
                    packet.require_sequence(sequence).map_err(|e| e.to_string())?;
                    owner.child_guard(&bound)?;
                    let mut ack_end = packet.end_ns;
                    match (&phase,packet.kind) {
                        (Phase::Hello,1) if packet.case==255=>{
                            let hello:Hello=serde_json::from_slice(&packet.payload).map_err(|e|e.to_string())?;
                            if hello.plan_sha256!=plan.digest || hello.plan_bytes!=plan.pin[6]
                                || hello.suite_seconds!=SUITE_SECONDS || packet.end_ns==0 {
                                return Err("physical normal child's exact source plan/window differs".into());
                            }
                            ack_end=packet.end_ns.min(parent_end_ns);
                            end=instant_until(ack_end,end).map_err(|e|e.to_string())?;
                            owner.boundary(Some(&bound),end)?;
                            owner.compare_epoch(&hello.epoch)?;
                            epoch=Some(hello.epoch);phase=Phase::Between(0);
                        }
                        (Phase::Between(next),2) if packet.case==*next && packet.payload.is_empty()=>{
                            let case=QualificationCase::from_ordinal(*next).map_err(|e|e.to_string())?;
                            let now=monotonic_ns().map_err(|e|e.to_string())?;
                            if packet.end_ns<=now || packet.end_ns>parent_end_ns
                                || packet.end_ns-now>case.window_seconds()*1_000_000_000 {
                                return Err("physical original fixed case deadline differs".into());
                            }
                            let case_end=instant_until(packet.end_ns,end).map_err(|e|e.to_string())?;
                            owner.switch(case.profile(),&bound,case_end)?;
                            phase=Phase::Case{ordinal:*next,end_ns:packet.end_ns};
                        }
                        (Phase::Case{ordinal,end_ns:case_end},3)
                            if packet.case==*ordinal && packet.end_ns==*case_end && packet.payload.is_empty()=>{
                            let case_end=instant_until(*case_end,end).map_err(|e|e.to_string())?;
                            owner.boundary(Some(&bound),case_end)?;
                            phase=Phase::Between(*ordinal+1);
                        }
                        (Phase::Between(next),4) if usize::from(*next)==CASE_COUNT && packet.case==255=>{
                            let line=packet.payload.iter().position(|b|*b==b'\n').ok_or("Complete header missing")?;
                            if line>4096 {return Err("Complete header exceeds fixed bound".into());}
                            let header:CompleteHeader=serde_json::from_slice(&packet.payload[..line]).map_err(|e|e.to_string())?;
                            let body=packet.payload[line+1..].to_vec();
                            if header.selected_applications!=41 || header.required_gates!=401 || body.len()>BINDING_LIMIT
                                || header.binding_bytes!=body.len() as u64 || header.binding_sha256!=sha(&body)
                                || header.summary_bytes==0 || header.summary_bytes>SUMMARY_LIMIT as u64
                                || !digest_ok(&header.summary_sha256) {
                                return Err("actual private Complete body/commitment differs".into());
                            }
                            let binding:RuntimeMainCustody=serde_json::from_slice(&body).map_err(|e|e.to_string())?;
                            binding.validate(epoch.as_ref().ok_or("Complete lacks initial actual epoch")?)?;
                            owner.compare_binding(&binding)?;
                            if packet.end_ns>parent_end_ns {return Err("Complete attempted to extend the original end".into());}
                            pending=Some(PendingComplete{header,binding,body,packet});
                            continue;
                        }
                        _=>return Err("physical private channel requested an unreviewed or reordered operation".into()),
                    }
                    socket
                        .send(
                            &socket::Packet {
                                sequence,
                                kind: 5,
                                case: packet.case,
                                end_ns: ack_end,
                                payload: Vec::new(),
                            },
                            until.min(end),
                        )
                        .map_err(|e| e.to_string())?;
                    sequence += 1;
                }
            }
            if let Some(value) = pending.as_ref() {
                if stdout.bytes > value.header.summary_bytes {
                    return Err("normal Complete stdout has an uncommitted suffix".into());
                }
                if stdout.bytes == value.header.summary_bytes {
                    if stdout.digest() != value.header.summary_sha256 || stderr.bytes != 0 {
                        return Err("actual Complete whole stdout/stderr differs".into());
                    }
                    let mut raw = vec![0u8; stdout.bytes as usize];
                    stdout
                        .file
                        .read_exact_at(&mut raw, 0)
                        .map_err(|e| e.to_string())?;
                    validate_summary(&raw, &plan, epoch.as_ref().ok_or("summary epoch absent")?)
                        .map_err(|e| e.to_string())?;
                    owner.boundary(Some(&bound), end)?;
                    plan.guard().map_err(|e| e.to_string())?;
                    socket
                        .send(
                            &socket::Packet {
                                sequence,
                                kind: 5,
                                case: 255,
                                end_ns: value.packet.end_ns,
                                payload: Vec::new(),
                            },
                            end,
                        )
                        .map_err(|e| e.to_string())?;
                    sequence += 1;
                    phase = Phase::Complete;
                    let value = pending.take().unwrap();
                    captured_binding = Some((value.binding, value.body, value.header));
                }
            }
            if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
                stdout.drain(&mut output_pipe).map_err(|e| e.to_string())?;
                stderr.drain(&mut error_pipe).map_err(|e| e.to_string())?;
                if !status.success()
                    || phase != Phase::Complete
                    || !stdout.eof
                    || !stderr.eof
                    || stderr.bytes != 0
                {
                    return Err(format!(
                        "actual physical producer incomplete: exit={status}, phase={phase:?}"
                    ));
                }
                let (binding, body, commitment) = captured_binding
                    .take()
                    .ok_or("actual Complete frame absent")?;
                if stdout.bytes != commitment.summary_bytes
                    || stdout.digest() != commitment.summary_sha256
                {
                    return Err("Complete stdout changed after acknowledgement".into());
                }
                owner.boundary(None, end)?;
                owner.finish(end)?;
                plan.guard().map_err(|e| e.to_string())?;
                let mut binding_out =
                    Output::create(&plan, "MAIN-BINDING.json", BINDING_LIMIT as u64)
                        .map_err(|e| e.to_string())?;
                binding_out
                    .file
                    .write_all(&body)
                    .map_err(|e| e.to_string())?;
                binding_out.bytes = body.len() as u64;
                binding_out.hash.update(&body);
                let sealed = binding_out.seal().map_err(|e| e.to_string())?;
                sealed.guard().map_err(|e| e.to_string())?;
                return Ok((binding, bound.identity.start_ticks, sealed));
            }
            let mut fds = [
                libc::pollfd {
                    fd: socket.file.as_raw_fd(),
                    events: if phase == Phase::Complete {
                        0
                    } else {
                        libc::POLLIN
                    },
                    revents: 0,
                },
                libc::pollfd {
                    fd: output_pipe.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: error_pipe.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: child.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let left = until
                .min(end)
                .checked_duration_since(Instant::now())
                .ok_or("physical poll deadline expired")?;
            let ms = left.as_millis().max(1).min(100) as i32;
            // SAFETY: fds is this loop's initialized fixed descriptor array.
            if unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as _, ms) } < 0
                && io::Error::last_os_error().kind() != io::ErrorKind::Interrupted
            {
                return Err(io::Error::last_os_error().to_string());
            }
        }
    })();
    let (binding, child_start, binding_output) = match execute {
        Ok(value) => value,
        Err(original) => {
            let retirement = child.stop(cleanup_end);
            let _ = stdout.drain(&mut output_pipe);
            let _ = stderr.drain(&mut error_pipe);
            let _ = stdout.file.sync_all();
            let _ = stderr.file.sync_all();
            let reason=format!(
                "{original}; direct-child-retirement={retirement:?}; retain private outputs; parent-unit external retirement remains required");
            let recorded=owner.record_failure(&reason);
            return Err(format!("{reason}; normal-owner-failure-record={recorded:?}"));
        }
    };
    let stdout = stdout.seal().map_err(|e| e.to_string())?;
    let stderr = stderr.seal().map_err(|e| e.to_string())?;
    let value = CapturedCompleteApplicationRun {
        owner,
        plan,
        summary: stdout,
        stderr,
        binding_output,
        binding,
        child_pid: pid,
        child_start,
        end,
    };
    value.guard()?;
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_complete_case_comparison_rejects_missing_reordered_and_foreign_histories() {
        let epoch = RuntimeEpoch {
            boot_id: "12345678-1234-4234-8234-123456789abc".into(),
            cell_host_pid: 41,
            framework_host_pid: 42,
            framework_start_ticks: 43,
        };
        let make = |package: &str| -> Value {
            let cases = (0..CASE_COUNT).filter_map(|ordinal| {
                let case = QualificationCase::from_ordinal(ordinal as u8).unwrap();
                if case.package() != package { return None; }
                let mut history = json!({
                    "actual":{"package":package,"user":0,"epoch":epoch},
                    "sealed_inside_original_case_window":true,
                    "historical_observation":true,
                    "continuous_app_or_target_directory_custody_after_case_claimed":false,
                });
                if let Some(route) = case.native_route() {
                    history["route"] = json!(route);
                } else if case == QualificationCase::CameraPhotoCaptureReopen {
                    history["kind"] = json!("camera_photo_capture_reopen");
                } else if case == QualificationCase::SettingsPermissionInterfaces {
                    history["kind"] = json!("settings_permission_interfaces");
                } else {
                    history["kind"] = json!("family_observation");
                }
                Some(history)
            }).collect::<Vec<_>>();
            json!({"cases":cases})
        };
        let mut total = 0;
        for (package, _) in roster::PACKAGES {
            total += validate_case_summaries(package, &make(package), &epoch).unwrap();
        }
        assert_eq!(total, CASE_COUNT);
        let camera = make("com.android.camera2");
        assert_eq!(camera["cases"].as_array().unwrap().len(), 2);
        assert_eq!(camera["cases"][0]["route"], "camera_photo");
        assert_eq!(camera["cases"][1]["kind"], "camera_photo_capture_reopen");
        let mut wrong = camera.clone();
        wrong["cases"].as_array_mut().unwrap().pop();
        assert!(validate_case_summaries("com.android.camera2", &wrong, &epoch).is_err());
        let mut wrong = camera.clone();
        wrong["cases"].as_array_mut().unwrap().swap(0, 1);
        assert!(validate_case_summaries("com.android.camera2", &wrong, &epoch).is_err());
        let mut wrong = camera.clone();
        wrong["cases"][1]["kind"] = json!("family_observation");
        assert!(validate_case_summaries("com.android.camera2", &wrong, &epoch).is_err());
        let mut wrong = camera.clone();
        wrong["cases"][1]["actual"]["epoch"]["framework_start_ticks"] = json!(44);
        assert!(validate_case_summaries("com.android.camera2", &wrong, &epoch).is_err());
        let mut wrong = camera;
        wrong["cases"][1]["route"] = json!("camera_photo");
        assert!(validate_case_summaries("com.android.camera2", &wrong, &epoch).is_err());
        let settings = make("com.android.settings");
        assert_eq!(settings["cases"].as_array().unwrap().len(), 2);
        assert_eq!(settings["cases"][0]["route"], "settings_supported_pages");
        assert_eq!(settings["cases"][1]["kind"], "settings_permission_interfaces");
        for changed in 0..4 {
            let mut wrong = settings.clone();
            match changed {
                0 => { wrong["cases"].as_array_mut().unwrap().pop(); }
                1 => { wrong["cases"].as_array_mut().unwrap().swap(0, 1); }
                2 => { wrong["cases"][1]["kind"] = json!("family_observation"); }
                _ => { wrong["cases"][1]["actual"]["package"] = json!("com.android.permissioncontroller"); }
            }
            assert!(validate_case_summaries("com.android.settings", &wrong, &epoch).is_err());
        }
        let family = make("org.mozilla.firefox");
        let mut wrong = family.clone();
        wrong["cases"] = json!([]);
        assert!(validate_case_summaries("org.mozilla.firefox", &wrong, &epoch).is_err());
        let mut wrong = family.clone();
        wrong["cases"][0]["actual"]["package"] = json!("com.android.settings");
        assert!(validate_case_summaries("org.mozilla.firefox", &wrong, &epoch).is_err());
        let mut wrong = family;
        wrong["cases"][0]["actual"]["epoch"]["framework_start_ticks"] = json!(44);
        assert!(validate_case_summaries("org.mozilla.firefox", &wrong, &epoch).is_err());
        let mut wrong = make("com.android.calendar");
        wrong["cases"].as_array_mut().unwrap().swap(0,1);
        assert!(validate_case_summaries("com.android.calendar", &wrong, &epoch).is_err());
        assert!(validate_case_summaries("caller.package", &json!({"cases":[]}), &epoch).is_err());
    }
}
