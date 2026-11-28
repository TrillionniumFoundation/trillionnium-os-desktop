//! A fresh original-kernel recovery owner. Retained JSON is comparison data;
//! the live PID1, namespaces, producer and actual global lock descriptions
//! are established here again. This type never owns the four Android backings.
use super::working::{self, WorkingOwnerUnit};
use super::*;
use crate::cold_original_data::labels::WorkingReturnedLabelRestoration;
use crate::cold_original_qualification::materials::Guard;
use crate::cold_original_qualification::working_return_packages::{
    PackageReplacementAttempt, WorkingPid1PackageReplacement,
};
use serde_json::{Value, json};
use std::cell::RefCell;
use std::collections::BTreeSet;
use std::{
    os::fd::AsRawFd,
    rc::Rc,
    time::{Duration, Instant},
};

const RECOVERY_MODE: &str = "recover-working-qualification";
const PROC_MAGIC: u64 = 0x9fa0;
const NS_MAGIC: u64 = 0x6e736673;
const NAMESPACES: [&str; 7] = ["user", "pid", "mnt", "net", "ipc", "uts", "cgroup"];
const MAX_PROCESSES: usize = 32768;

fn gone(error: &(dyn std::error::Error + 'static)) -> bool {
    error
        .downcast_ref::<rustix::io::Errno>()
        .is_some_and(|v| matches!(*v, rustix::io::Errno::NOENT | rustix::io::Errno::SRCH))
        || error
            .downcast_ref::<std::io::Error>()
            .is_some_and(|v| v.kind() == std::io::ErrorKind::NotFound)
}
fn read_at(directory: &File, name: &str, maximum: u64) -> Result<Vec<u8>> {
    let file = File::from(rustix::fs::openat(
        directory,
        name,
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    let mut bytes = Vec::new();
    file.take(maximum + 1).read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 <= maximum,
        "fresh proc observation exceeded its fixed bound",
    )?;
    Ok(bytes)
}
fn text_at(directory: &File, name: &str, maximum: u64) -> Result<String> {
    Ok(String::from_utf8(read_at(directory, name, maximum)?)?)
}
fn namespace(path: &str) -> Result<(File, Identity)> {
    let file = File::from(rustix::fs::open(
        path,
        OFlags::RDONLY | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    ensure(
        rustix::fs::fstatfs(&file)?.f_type as u64 == NS_MAGIC,
        "fresh namespace witness is not a real namespace descriptor",
    )?;
    let identity = fs::stat(&file)?;
    Ok((file, identity))
}
fn kernel_object(a: &Identity, b: &Identity) -> bool {
    (a.dev, a.ino, a.mode, a.uid, a.gid, a.nlink) == (b.dev, b.ino, b.mode, b.uid, b.gid, b.nlink)
}
struct Pid1Witness {
    proc: File,
    proc_identity: Identity,
    directory: File,
    directory_identity: Identity,
    pidfd: File,
    starttime: u64,
    executable: File,
    executable_identity: RefCell<Identity>,
    executable_sha256: String,
    executable_link: RefCell<PathBuf>,
    namespaces: BTreeMap<String, (File, Identity)>,
}
impl Pid1Witness {
    fn capture() -> Result<Self> {
        let proc = fs::Tree::open("/proc", 0)?.root;
        ensure(
            rustix::fs::fstatfs(&proc)?.f_type as u64 == PROC_MAGIC,
            "fresh PID1 observations require the actual procfs",
        )?;
        let proc_identity = fs::stat(&proc)?;
        let directory = File::from(rustix::fs::openat(
            &proc,
            "1",
            OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let directory_identity = fs::stat(&directory)?;
        let pidfd = File::from(rustix::process::pidfd_open(
            rustix::process::Pid::from_raw(1).ok_or("PID1 absent")?,
            rustix::process::PidfdFlags::empty(),
        )?);
        let (state, ticks) = starttime(&text_at(&directory, "stat", 8192)?)?;
        ensure(!matches!(state, 'Z' | 'X'), "original PID1 is retired")?;
        let executable = File::open("/proc/1/exe")?;
        let executable_identity = fs::stat(&executable)?;
        let executable_link = std::fs::read_link("/proc/1/exe")?;
        ensure(
            matches!(
                executable_link.to_str(),
                Some("/usr/lib/systemd/systemd" | "/usr/lib/systemd/systemd (deleted)")
            ) && FileType::from_raw_mode(executable_identity.mode) == FileType::RegularFile
                && executable_identity.uid == 0
                && executable_identity.gid == 0
                && executable_identity.mode & 0o7777 == 0o755
                && executable_identity.size > 0
                && executable_identity.size <= 128 * 1024 * 1024,
            "actual original PID1 is outside the fixed normal systemd executable",
        )?;
        let executable_sha256 = complete_hash(&executable)?;
        let mut namespaces = BTreeMap::new();
        for name in NAMESPACES {
            let (file, id) = namespace(&format!("/proc/1/ns/{name}"))?;
            let (_, own) = namespace(&format!("/proc/self/ns/{name}"))?;
            ensure(
                kernel_object(&id, &own),
                "fresh original owner differs from PID1 namespace",
            )?;
            namespaces.insert(name.to_owned(), (file, id));
        }
        let value = Self {
            proc,
            proc_identity,
            directory,
            directory_identity,
            pidfd,
            starttime: ticks,
            executable,
            executable_identity: RefCell::new(executable_identity),
            executable_sha256,
            executable_link: RefCell::new(executable_link),
            namespaces,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate_process_identity(&self) -> Result<()> {
        let proc = fs::Tree::open("/proc", 0)?.root;
        ensure(
            rustix::fs::fstatfs(&proc)?.f_type as u64 == PROC_MAGIC
                && same_directory(&fs::stat(&proc)?, &self.proc_identity)
                && same_directory(&fs::stat(&self.proc)?, &self.proc_identity),
            "fresh PID1 procfs was replaced",
        )?;
        let named = File::from(rustix::fs::openat(
            &self.proc,
            "1",
            OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let (state, ticks) = starttime(&text_at(&self.directory, "stat", 8192)?)?;
        let fdinfo = bounded(
            &PathBuf::from(format!("/proc/self/fdinfo/{}", self.pidfd.as_raw_fd())),
            8192,
        )?;
        let pids = fdinfo
            .lines()
            .filter_map(|v| v.strip_prefix("Pid:"))
            .map(str::trim)
            .collect::<Vec<_>>();
        ensure(
            pids == ["1"]
                && !matches!(state, 'Z' | 'X')
                && ticks == self.starttime
                && kernel_object(&fs::stat(&self.directory)?, &self.directory_identity)
                && kernel_object(&fs::stat(&named)?, &self.directory_identity),
            "fresh PID1 process or pidfd identity changed",
        )?;
        for (name, (held, id)) in &self.namespaces {
            let (_, named) = namespace(&format!("/proc/1/ns/{name}"))?;
            let (_, own) = namespace(&format!("/proc/self/ns/{name}"))?;
            ensure(
                kernel_object(&fs::stat(held)?, id)
                    && kernel_object(&named, id)
                    && kernel_object(&own, id),
                "fresh held PID1 namespace changed",
            )?;
        }
        Ok(())
    }
    fn revalidate_process(&self) -> Result<()> {
        self.revalidate_process_identity()?;
        ensure(
            std::fs::read_link("/proc/1/exe")? == *self.executable_link.borrow(),
            "fresh PID1 kernel executable link changed",
        )
    }
    fn revalidate_executable(&self, expected: &Identity) -> Result<()> {
        self.revalidate_executable_at(expected, &self.executable_link.borrow())
    }
    fn revalidate_executable_at(&self, expected: &Identity, link: &Path) -> Result<()> {
        ensure(
            fs::stat(&self.executable)? == *expected
                && fs::stat(&File::open("/proc/1/exe")?)? == *expected
                && std::fs::read_link("/proc/1/exe")? == link
                && complete_hash(&self.executable)? == self.executable_sha256
                && fs::stat(&self.executable)? == *expected
                && fs::stat(&File::open("/proc/1/exe")?)? == *expected,
            "fresh PID1 complete executable inode or contents changed",
        )
    }
    fn revalidate(&self) -> Result<()> {
        self.revalidate_process()?;
        self.revalidate_executable(&self.executable_identity.borrow())?;
        self.revalidate_process()
    }
    fn prepare_label_restoration(
        &self,
        proof: &WorkingReturnedLabelRestoration,
    ) -> Result<Option<Identity>> {
        self.revalidate_process()?;
        // An upgraded, deleted PID1 executable is still a valid held process
        // witness, but the newly named systemd inode is not that witness.
        let path = Path::new("/usr/lib/systemd/systemd");
        if self.executable_link.borrow().as_path() != path
            || !proof.paths().iter().any(|p| p == path)
        {
            self.revalidate()?;
            return Ok(None);
        }
        let before = self.executable_identity.borrow();
        let after = proof.require_held_transition(path, &self.executable, &before)?;
        returned_label_identity(&before, &after)?;
        self.revalidate_executable(&after)?;
        self.revalidate_process()?;
        Ok(Some(after))
    }
    fn accept_label_restoration(&self, after: Option<Identity>) -> Result<()> {
        if let Some(after) = after {
            self.revalidate_process()?;
            returned_label_identity(&self.executable_identity.borrow(), &after)?;
            self.revalidate_executable(&after)?;
            *self.executable_identity.borrow_mut() = after;
        }
        self.revalidate()
    }
    fn evidence(&self) -> Value {
        json!({"actual_pid":1,"pidfd_held":true,"starttime":self.starttime,
            "proc_directory":self.directory_identity,"executable":*self.executable_identity.borrow(),
            "executable_sha256":self.executable_sha256,"kernel_executable_link":*self.executable_link.borrow(),
            "namespaces":self.namespaces.iter().map(|(name,(_,id))|
                (name.clone(),serde_json::to_value(id).unwrap())).collect::<BTreeMap<_,_>>()})
    }
}
fn android_process(comm: &str, argv: &[u8], executable: &Path, cgroup: &str) -> bool {
    let command = argv.split(|b| *b == 0).next().unwrap_or_default();
    let native = |value: &[u8]| {
        value.starts_with(b"/system/")
            || value.starts_with(b"/apex/")
            || value.starts_with(b"/vendor/bin/")
            || value.starts_with(b"/product/bin/")
            || value.starts_with(b"/odm/bin/")
    };
    use std::os::unix::ffi::OsStrExt;
    let names = [
        "system_server",
        "zygote",
        "zygote32",
        "zygote64",
        "surfaceflinger",
        "servicemanager",
        "hwservicemanager",
        "vndservicemanag",
    ];
    names.contains(&comm.trim_end())
        || native(command)
        || native(executable.as_os_str().as_bytes())
        || cgroup.lines().any(|line| {
            line.split('/').any(|part| {
                [
                    "gdm.service",
                    "droidloom-production.service",
                    "droidloom-instance-launcher.service",
                    "droidloom-instance-factory.service",
                    "droidloom-early-observer.service",
                    "droidloom-working-qualification.service",
                    "droidloom-working-qualification-return.service",
                ]
                .contains(&part)
                    || part.starts_with("droidloom-cell@")
                    || part.starts_with("droidloom-android@")
            })
        })
}
fn no_android() -> Result<Value> {
    let proc = fs::Tree::open("/proc", 0)?.root;
    ensure(
        rustix::fs::fstatfs(&proc)?.f_type as u64 == PROC_MAGIC,
        "Android absence observation requires the actual procfs",
    )?;
    let identity = fs::stat(&proc)?;
    let end = Instant::now() + Duration::from_secs(15);
    let mut examined = 0usize;
    let mut exited = 0usize;
    for entry in std::fs::read_dir(format!("/proc/self/fd/{}", proc.as_raw_fd()))? {
        ensure(
            Instant::now() < end,
            "complete Android absence scan exceeded its finite interval",
        )?;
        let entry = entry?;
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            return Err("non-UTF8 proc member".into());
        };
        if name.is_empty() || !name.bytes().all(|v| v.is_ascii_digit()) {
            continue;
        }
        examined += 1;
        ensure(
            examined <= MAX_PROCESSES,
            "complete original process inventory exceeded its bound",
        )?;
        let directory = match rustix::fs::openat(
            &proc,
            name,
            OFlags::PATH | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        ) {
            Ok(v) => File::from(v),
            Err(rustix::io::Errno::NOENT | rustix::io::Errno::SRCH) => {
                exited += 1;
                continue;
            }
            Err(e) => return Err(e.into()),
        };
        let inspect = || -> Result<()> {
            let before = text_at(&directory, "stat", 8192)?;
            let (state, ticks) = starttime(&before)?;
            if matches!(state, 'Z' | 'X') {
                return Ok(());
            }
            let comm = text_at(&directory, "comm", 4096)?;
            let argv = read_at(&directory, "cmdline", 65536)?;
            let cgroup = text_at(&directory, "cgroup", 65536)?;
            let path = format!("/proc/self/fd/{}/exe", directory.as_raw_fd());
            let executable = match std::fs::read_link(path) {
                Ok(v) => v,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound && argv.is_empty() => {
                    PathBuf::new()
                }
                Err(e) => return Err(e.into()),
            };
            ensure(
                !android_process(&comm, &argv, &executable, &cgroup),
                "an actual graphical or Android owner still occupies the original host",
            )?;
            let (_after_state, after_ticks) = starttime(&text_at(&directory, "stat", 8192)?)?;
            ensure(
                after_ticks == ticks,
                "process changed during complete Android absence observation",
            )
        };
        if let Err(error) = inspect() {
            if gone(error.as_ref()) {
                match text_at(&directory, "stat", 8192) {
                    Err(last) if gone(last.as_ref()) => exited += 1,
                    _ => return Err(error),
                }
            } else {
                return Err(error);
            }
        }
    }
    ensure(
        same_directory(&fs::stat(&proc)?, &identity)
            && same_directory(&fs::stat(&fs::Tree::open("/proc", 0)?.root)?, &identity),
        "original procfs changed during complete Android absence observation",
    )?;
    Ok(
        json!({"schema":"droidloom.working-return-process-observation.v1",
        "complete":true,"numeric_proc_entries_examined":examined,"entries_exited":exited,
        "known_android_or_graphical_owners":[],
        "backing_reference_scan_performed":false,"backing_locks_owned":false}),
    )
}
#[derive(Clone, Copy)]
enum Entry {
    Recovery,
    Live,
}
/// No Deserialize, Clone, caller-selected mode, namespace or lock constructor.
pub(crate) struct WorkingReturnOwner {
    observation: OriginalObservation,
    locks: RefCell<Vec<ExistingLock>>,
    candidate: String,
    input: SealedInput,
    executable: Guard,
    arguments: String,
    entry: Entry,
    pid1: Pid1Witness,
    absence: Value,
}
impl WorkingReturnOwner {
    pub(crate) fn acquire(candidate: &str, input: &FilePin) -> Result<Self> {
        let before = working::working_observation_for(candidate, WorkingOwnerUnit::Recovery)?;
        working::singleton(&before)?;
        let input = SealedInput::open(input)?;
        let executable_path = std::fs::read_link("/proc/self/exe")?;
        let executable = Guard::open(&files::pin_file(&executable_path)?)?;
        let arguments = bounded(Path::new("/proc/self/cmdline"), 32768)?;
        ensure(
            arguments
                == working::exact_arguments_for(&executable_path, input.pin(), RECOVERY_MODE)?
                && fs::stat(&File::open("/proc/self/exe")?)? == *executable.identity(),
            "fresh recovery producer or complete argv differs",
        )?;
        let locks = LOCK_PATHS
            .iter()
            .map(|p| ExistingLock::acquire(Path::new(p), 0))
            .collect::<Result<Vec<_>>>()?;
        let pid1 = Pid1Witness::capture()?;
        let absence = no_android()?;
        let value = Self {
            observation: before,
            locks: RefCell::new(locks),
            candidate: candidate.into(),
            input,
            executable,
            arguments,
            entry: Entry::Recovery,
            pid1,
            absence,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn from_live(source: &working::WorkingColdOwner) -> Result<Self> {
        let (candidate, input_pin, program, locks, original_boot_id) =
            source.fresh_return_parts()?;
        let before = working::working_observation_for(&candidate, WorkingOwnerUnit::Cold)?;
        working::singleton(&before)?;
        ensure(
            before.boot_id == original_boot_id,
            "same-boot recovery factory cannot cross an actual kernel boot",
        )?;
        let input = SealedInput::open(&input_pin)?;
        let executable = Guard::open(&program)?;
        let arguments = bounded(Path::new("/proc/self/cmdline"), 32768)?;
        ensure(
            arguments
                == working::exact_arguments_for(&program.path, input.pin(), working::RUN_MODE)?
                && fs::stat(&File::open("/proc/self/exe")?)? == *executable.identity(),
            "same-boot return needs the exact still-running normal cold producer",
        )?;
        let pid1 = Pid1Witness::capture()?;
        let absence = no_android()?;
        let value = Self {
            observation: before,
            locks: RefCell::new(locks),
            candidate,
            input,
            executable,
            arguments,
            entry: Entry::Live,
            pid1,
            absence,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate_process_custody(&self) -> Result<()> {
        self.revalidate_process_custody_inner(true)
    }
    fn revalidate_process_custody_inner(&self, exact_pid1_link: bool) -> Result<()> {
        let unit = match self.entry {
            Entry::Recovery => WorkingOwnerUnit::Recovery,
            Entry::Live => WorkingOwnerUnit::Cold,
        };
        let actual = working::working_observation_for(&self.candidate, unit)?;
        ensure(
            same_observation(&actual, &self.observation),
            "fresh return owner changed boot, process, namespace or original root",
        )?;
        working::singleton(&actual)?;
        if exact_pid1_link {
            self.pid1.revalidate_process()?;
        } else {
            self.pid1.revalidate_process_identity()?;
        }
        self.input.revalidate()?;
        self.executable.revalidate()?;
        ensure(
            bounded(Path::new("/proc/self/cmdline"), 32768)? == self.arguments
                && fs::stat(&File::open("/proc/self/exe")?)? == *self.executable.identity(),
            "fresh return owner producer identity or exact argv changed",
        )?;
        no_android()?;
        if exact_pid1_link {
            self.pid1.revalidate_process()
        } else {
            self.pid1.revalidate_process_identity()
        }
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        for lock in self.locks.borrow().iter() {
            lock.revalidate()?;
        }
        self.revalidate_process_custody()?;
        self.pid1.revalidate()?;
        for lock in self.locks.borrow().iter() {
            lock.revalidate()?;
        }
        Ok(())
    }
    pub(crate) fn label_sensitive_paths(&self) -> BTreeSet<PathBuf> {
        let mut paths = LOCK_PATHS
            .iter()
            .skip(1)
            .map(PathBuf::from)
            .collect::<BTreeSet<_>>();
        if self.pid1.executable_link.borrow().as_path() == Path::new("/usr/lib/systemd/systemd") {
            paths.insert(self.pid1.executable_link.borrow().clone());
        }
        paths
    }
    pub(crate) fn accept_label_restoration_custody(
        &self,
        proof: &WorkingReturnedLabelRestoration,
    ) -> Result<()> {
        // The proof itself checks only immutable source custody and its actual
        // completed target. It must not recurse into these pending checkpoints.
        proof.require_owner(self)?;
        ensure(
            proof.candidate_id() == self.candidate,
            "returned label belongs to another fresh candidate",
        )?;
        self.revalidate_process_custody()?;
        let updates = {
            let locks = self.locks.borrow();
            ensure(
                locks
                    .iter()
                    .map(|l| l.path.as_path())
                    .eq(LOCK_PATHS.iter().map(Path::new)),
                "fresh return global lock roster changed",
            )?;
            locks
                .iter()
                .enumerate()
                .map(|(index, lock)| {
                    if proof.paths().iter().any(|path| path == &lock.path) {
                        ensure(
                            index != 0,
                            "private controller lock is outside returned label scope",
                        )?;
                        let after = proof.require_held_transition(
                            &lock.path,
                            &lock.held,
                            &lock.identity,
                        )?;
                        returned_label_identity(&lock.identity, &after)?;
                        Ok(Some((lock.identity.clone(), after)))
                    } else {
                        lock.revalidate()?;
                        Ok(None)
                    }
                })
                .collect::<Result<Vec<_>>>()?
        };
        let pid1_update = self.pid1.prepare_label_restoration(proof)?;
        for (lock, update) in self.locks.borrow_mut().iter_mut().zip(updates) {
            if let Some((before, after)) = update {
                lock.accept_label_identity(&before, &after)?;
            }
        }
        self.pid1.accept_label_restoration(pid1_update)?;
        proof.revalidate()?;
        self.revalidate()
    }
    /// Duplicate the actual held PID1 executable for a new normal package
    /// operation. These read-only observations do not adopt any change.
    pub(crate) fn actual_pid1_for_package(
        self: &Rc<Self>,
    ) -> Result<(File, Identity, String, PathBuf)> {
        self.revalidate()?;
        let held = self.pid1.executable.try_clone()?;
        let identity = self.pid1.executable_identity.borrow().clone();
        let link = self.pid1.executable_link.borrow().clone();
        ensure(
            fs::stat(&held)? == identity
                && complete_hash(&held)? == self.pid1.executable_sha256
                && fs::stat(&held)? == identity,
            "normal package PID1 duplicate lost its original held executable",
        )?;
        self.revalidate()?;
        Ok((held, identity, self.pid1.executable_sha256.clone(), link))
    }
    /// Only the opaque, source-bound pending package operation may observe its
    /// actual unlink before adoption. Every global lock and live owner/PID1
    /// birth, namespace, producer and Android-absence check remains active.
    /// This fence is not successful package restoration or general authority.
    pub(crate) fn revalidate_package_custody(
        &self,
        attempt: &PackageReplacementAttempt,
    ) -> Result<()> {
        attempt.require_owner(self)?;
        for lock in self.locks.borrow().iter() {
            lock.revalidate()?;
        }
        self.revalidate_process_custody_inner(false)?;
        attempt.require_current_pid1(&self.pid1.executable, &self.pid1.executable_sha256)?;
        self.pid1.revalidate_process_identity()?;
        for lock in self.locks.borrow().iter() {
            lock.revalidate()?;
        }
        Ok(())
    }
    pub(crate) fn accept_package_replacement_custody(
        &self,
        proof: &WorkingPid1PackageReplacement,
    ) -> Result<()> {
        proof.require_owner(self)?;
        self.revalidate_package_custody(proof.attempt())?;
        let (after, link) = proof.require_held_transition(
            &self.pid1.executable,
            &self.pid1.executable_identity.borrow(),
            &self.pid1.executable_link.borrow(),
        )?;
        self.pid1.revalidate_process_identity()?;
        self.pid1.revalidate_executable_at(&after, &link)?;
        proof.revalidate()?;
        // Neither executable nor pidfd description is exchanged. All fallible
        // readback precedes this same-thread checkpoint update.
        *self.pid1.executable_identity.borrow_mut() = after;
        *self.pid1.executable_link.borrow_mut() = link;
        self.revalidate()?;
        proof.revalidate()
    }
    pub(crate) fn evidence(&self) -> Value {
        json!({"schema":"droidloom.working-qualification-return-owner.v1",
            "candidate_id":self.candidate,"actual_original":self.observation,
            "actual_pid1":self.pid1.evidence(),"actual_process_observation":self.absence,
            "input":self.input.pin(),"actual_producer":self.executable.pin(),
            "actual_producer_identity":self.executable.identity(),
            "entry":match self.entry {Entry::Recovery=>"fresh-recovery-unit",Entry::Live=>"fresh-same-process-observation"},
            "global_locks":self.locks.borrow().iter().map(|l|json!({"path":l.path,"identity":l.identity,
                "sha256":l.sha256})).collect::<Vec<_>>(),
            "global_lock_descriptions":match self.entry {Entry::Recovery=>"newly-acquired",Entry::Live=>"same-actual-ofd-duplicates"},
            "old_owner_rc_reconstructed":false,"old_root_snapshot_reused":false,
            "freezer_deadline_extended":false,"backing_locks_owned":false,
            "backing_reference_scan_performed":false})
    }
    pub(crate) fn boot_id(&self) -> &str {
        &self.observation.boot_id
    }
    pub(crate) fn candidate(&self) -> &str {
        &self.candidate
    }
    pub(crate) fn input_pin(&self) -> &FilePin {
        self.input.pin()
    }
    pub(crate) fn program_pin(&self) -> &FilePin {
        self.executable.pin()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fresh_return_rejects_known_android_processes_and_service_descendants() {
        for (comm, argv, exe, group) in [
            (
                "system_server",
                b"renamed".as_slice(),
                "/usr/bin/anything",
                "0::/ordinary\n",
            ),
            (
                "benign",
                b"/system/bin/app_process64\0",
                "/usr/bin/anything",
                "0::/ordinary\n",
            ),
            (
                "benign",
                b"renamed\0",
                "/apex/com.android.runtime/bin/linker64",
                "0::/ordinary\n",
            ),
            (
                "benign",
                b"renamed\0",
                "/usr/bin/anything",
                "0::/system.slice/droidloom-production.service/child\n",
            ),
            (
                "benign",
                b"renamed\0",
                "/usr/bin/anything",
                "0::/system.slice/droidloom-cell@1000.service\n",
            ),
        ] {
            assert!(android_process(comm, argv, Path::new(exe), group));
        }
        assert!(!android_process(
            "sshd",
            b"/usr/sbin/sshd\0",
            Path::new("/usr/sbin/sshd"),
            "0::/system.slice/ssh.service\n"
        ));
        assert!(!android_process(
            "fixture",
            b"/usr/bin/fixture\0",
            Path::new("/usr/bin/fixture"),
            "0::/system.slice/droidloom-working-recovery@abc.service\n"
        ));
    }
    #[test]
    fn recovery_unit_cannot_use_forward_or_historical_owner() -> Result<()> {
        let candidate = "a".repeat(64);
        let invocation = "b".repeat(32);
        let group = format!("0::/system.slice/droidloom-working-recovery@{candidate}.service\n");
        working::working_unit_for(&group, &invocation, &candidate, WorkingOwnerUnit::Recovery)?;
        assert!(
            working::working_unit_for(&group, &invocation, &candidate, WorkingOwnerUnit::Cold)
                .is_err()
        );
        let forward = group.replace("working-recovery@", "working-cold@");
        assert!(
            working::working_unit_for(
                &forward,
                &invocation,
                &candidate,
                WorkingOwnerUnit::Recovery
            )
            .is_err()
        );
        let plan = FilePin {
            path: "/var/lib/droidloom-qualification/test-return/plan.json".into(),
            bytes: 10,
            sha256: "c".repeat(64),
        };
        let argv = working::exact_arguments_for(
            Path::new("/var/lib/droidloom-qualification/test-return/producer"),
            &plan,
            RECOVERY_MODE,
        )?;
        assert_eq!(
            argv.split_terminator('\0').collect::<Vec<_>>()[1],
            RECOVERY_MODE
        );
        assert!(
            working::exact_arguments_for(
                Path::new("/var/lib/droidloom-qualification/test-return/producer"),
                &plan,
                "recover-working-qualification --force"
            )
            .is_err()
        );
        Ok(())
    }
}
