//! A new live cold owner for H2 preparation on the original kernel.
//! It never constructs OriginalQualificationAuthority or historical retirement.
use super::*;
use crate::cold_original_qualification::materials::Guard;

const MODE: &str = "prepare-working-qualification";
const PUBLICATION_MODE: &str = "verify-working-publication";
pub(super) const RUN_MODE: &str = "run-working-qualification";
const RECOVERY_MODE: &str = "recover-working-qualification";
#[derive(Clone, Copy)]
pub(super) enum WorkingOwnerUnit {
    Cold,
    Recovery,
}
const UNIT_PREFIX: &str = "/system.slice/droidloom-working-cold@";

fn working_unit(cgroup: &str, invocation: &str, candidate: &str) -> Result<String> {
    working_unit_for(cgroup, invocation, candidate, WorkingOwnerUnit::Cold)
}
pub(super) fn working_unit_for(
    cgroup: &str,
    invocation: &str,
    candidate: &str,
    unit: WorkingOwnerUnit,
) -> Result<String> {
    ensure(
        fs::valid_digest(candidate),
        "working cold candidate is not a full digest",
    )?;
    let prefix = match unit {
        WorkingOwnerUnit::Cold => UNIT_PREFIX,
        WorkingOwnerUnit::Recovery => "/system.slice/droidloom-working-recovery@",
    };
    let expected = format!("{prefix}{candidate}.service");
    ensure(
        cgroup == format!("0::{expected}\n")
            && invocation.len() == 32
            && invocation
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "working cold owner is not its distinct candidate system unit",
    )?;
    Ok(expected)
}
// New run/recovery producers and their immutable material plans are published
// inside the existing normal qualification RootScope exclusion. An installed
// arbitrary current ELF never becomes a mutable label-custody exception.
fn private_working_source(path: &Path) -> Result<()> {
    let value = fs::absolute_string(path)?;
    let root = Path::new("/var/lib/droidloom-qualification");
    ensure(
        path.starts_with(root)
            && path != root
            && value
                .split('/')
                .skip(1)
                .all(|part| !part.is_empty() && part != "." && part != "..")
            && !value.contains(['\0', '\n', '\r']),
        "working run and recovery require protected qualification source paths",
    )
}
fn exact_arguments(executable: &Path, input: &FilePin) -> Result<String> {
    exact_arguments_for(executable, input, MODE)
}
pub(super) fn exact_arguments_for(
    executable: &Path,
    input: &FilePin,
    mode: &str,
) -> Result<String> {
    ensure(
        matches!(mode, MODE | PUBLICATION_MODE | RUN_MODE | RECOVERY_MODE),
        "working cold command is not a fixed source-owned operation",
    )?;
    ensure(
        input.bytes > 0 && input.bytes <= 16 * 1024 * 1024 && fs::valid_digest(&input.sha256),
        "working cold input has no complete bounded commitment",
    )?;
    if matches!(mode, RUN_MODE | RECOVERY_MODE) {
        private_working_source(executable)?;
        private_working_source(&input.path)?;
    }
    let executable = fs::absolute_string(executable)?;
    let config = fs::absolute_string(&input.path)?;
    ensure(
        [&executable, &config].iter().all(|p| {
            !p.contains('\0')
                && !p.contains('\n')
                && !p.contains('\r')
                && !p.split('/').any(|v| v == "." || v == "..")
        }),
        "working cold arguments are not canonical absolute source paths",
    )?;
    let mut value = [
        executable.as_str(),
        mode,
        "--config",
        config.as_str(),
        "--config-sha256",
        input.sha256.as_str(),
    ]
    .join("\0");
    value.push('\0');
    ensure(
        value.len() <= 32768,
        "working cold actual command line exceeds its bound",
    )?;
    Ok(value)
}
fn exact_singleton(input: &str, pid: u32) -> Result<()> {
    ensure(
        pid > 1 && input == format!("{pid}\n"),
        "working cold unit is not the actual sole owner process",
    )
}
pub(super) fn singleton(observed: &OriginalObservation) -> Result<()> {
    let tree = fs::Tree::open("/sys/fs/cgroup", 0)?;
    ensure(
        rustix::fs::fstatfs(&tree.root)?.f_type as u64 == 0x63677270,
        "working cold owner requires the real cgroup-v2 filesystem",
    )?;
    let directory = tree.dir(&observed.control_group)?;
    let before = fs::stat(&directory)?;
    let path = Path::new("/sys/fs/cgroup").join(observed.control_group.trim_start_matches('/'));
    exact_singleton(&bounded(&path.join("cgroup.procs"), 4096)?, observed.pid)?;
    let events = bounded(&path.join("cgroup.events"), 4096)?;
    let mut fields = BTreeMap::new();
    for line in events.lines() {
        let pair: Vec<_> = line.split_whitespace().collect();
        ensure(
            pair.len() == 2 && fields.insert(pair[0], pair[1]).is_none(),
            "working cold cgroup events are ambiguous",
        )?;
    }
    ensure(
        fields.len() == 2
            && fields.get("populated") == Some(&"1")
            && fields.get("frozen") == Some(&"0"),
        "working cold cgroup is not live and unfrozen",
    )?;
    let mut count = 0usize;
    for member in std::fs::read_dir(&path)? {
        count += 1;
        ensure(
            count <= 512 && !member?.file_type()?.is_dir(),
            "working cold cgroup contains an unowned nested group",
        )?;
    }
    ensure(
        fs::stat(&directory)? == before && fs::stat(&tree.dir(&observed.control_group)?)? == before,
        "working cold cgroup changed during its complete membership observation",
    )
}

fn working_observation(candidate: &str) -> Result<OriginalObservation> {
    working_observation_for(candidate, WorkingOwnerUnit::Cold)
}
pub(super) fn working_observation_for(
    candidate: &str,
    unit: WorkingOwnerUnit,
) -> Result<OriginalObservation> {
    ensure(
        rustix::process::getuid().as_raw() == 0
            && rustix::process::geteuid().as_raw() == 0
            && rustix::process::getgid().as_raw() == 0
            && rustix::process::getegid().as_raw() == 0,
        "original qualification requires actual original root credentials",
    )?;
    let capabilities = owner_capabilities(&bounded(Path::new("/proc/self/status"), 64 * 1024)?)?;
    let invocation_id = std::env::var("INVOCATION_ID")?;
    let observed_cgroup = bounded(Path::new("/proc/self/cgroup"), 4096)?;
    let control_group = working_unit_for(&observed_cgroup, &invocation_id, candidate, unit)?;
    let pid = std::process::id();
    ensure(pid > 1, "original qualification owner cannot be PID1")?;
    let kernel = bounded(Path::new("/proc/sys/kernel/osrelease"), 256)?
        .trim()
        .to_owned();
    ensure(
        kernel == ORIGINAL_KERNEL,
        "qualification preparation is not on the original kernel",
    )?;
    let boot_id = bounded(Path::new("/proc/sys/kernel/random/boot_id"), 80)?
        .trim()
        .to_owned();
    ensure(uuid(&boot_id), "actual kernel boot ID is invalid")?;
    let (_, starttime) = starttime(&bounded(Path::new("/proc/self/stat"), 8192)?)?;
    let mut namespaces = BTreeMap::new();
    for kind in ["user", "pid", "mnt", "net", "ipc", "uts", "cgroup"] {
        let own = std::fs::read_link(format!("/proc/self/ns/{kind}"))?;
        let initial = std::fs::read_link(format!("/proc/1/ns/{kind}"))?;
        ensure(
            own == initial,
            "qualification owner is outside an original PID1 namespace",
        )?;
        let value = own
            .into_os_string()
            .into_string()
            .map_err(|_| "non-UTF8 namespace identity")?;
        if kind == "user" {
            ensure(
                value == "user:[4026531837]",
                "initial user namespace required",
            )?;
        }
        namespaces.insert(kind.into(), value);
    }
    ensure(
        bounded(Path::new("/proc/self/uid_map"), 256)?
            .split_whitespace()
            .collect::<Vec<_>>()
            == ["0", "0", "4294967295"],
        "original full uid mapping required",
    )?;
    let tree = fs::Tree::open("/", 0)?;
    let root = fs::stat(&tree.root)?;
    let pid1_root = File::from(rustix::fs::open(
        "/proc/1/root",
        OFlags::PATH | OFlags::DIRECTORY | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    ensure(
        same_directory(&root, &fs::stat(&pid1_root)?),
        "qualification owner is chrooted",
    )?;
    ensure(
        rustix::fs::fstatfs(&tree.root)?.f_type as u64 == 0xef53,
        "original root is not ext4",
    )?;
    let boot = fs::stat(&tree.dir("/boot")?)?;
    ensure(
        boot.dev == root.dev,
        "original /boot is on a different filesystem",
    )?;
    let mountinfo = bounded(Path::new("/proc/self/mountinfo"), PROC_LIMIT)?;
    let mut roots = Vec::new();
    for line in mountinfo.lines() {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure(fields.len() >= 10, "invalid original mountinfo record")?;
        if fields[4] != "/" {
            continue;
        }
        let dash = fields
            .iter()
            .position(|v| *v == "-")
            .ok_or("mountinfo separator missing")?;
        ensure(
            fields[3] == "/"
                && fields.get(dash + 1) == Some(&"ext4")
                && fields[5].split(',').any(|x| x == "rw"),
            "original root mount contract differs",
        )?;
        roots.push((fields[0].parse::<u64>()?, fields[2].to_owned()));
    }
    ensure(roots.len() == 1, "ambiguous original root mount")?;
    let (root_mount_id, root_device) = roots.remove(0);
    ensure(
        root_device
            == format!(
                "{}:{}",
                rustix::fs::major(root.dev),
                rustix::fs::minor(root.dev)
            ),
        "root mount major/minor differs from held root",
    )?;
    let uuid_path = format!("/dev/disk/by-uuid/{ROOT_UUID}");
    let (link_id, target) = tree.read_link(&uuid_path)?;
    ensure(
        link_id.uid == 0 && link_id.gid == 0,
        "root UUID link is not root owned",
    )?;
    let leaf = target
        .strip_prefix("../../")
        .ok_or("unexpected root UUID alias")?;
    ensure(
        !leaf.is_empty()
            && leaf
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
        "unsafe root UUID device alias",
    )?;
    let device = File::from(rustix::fs::openat(
        &tree.dir("/dev")?,
        leaf,
        OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    let stat = rustix::fs::fstat(&device)?;
    ensure(
        FileType::from_raw_mode(stat.st_mode) == FileType::BlockDevice
            && stat.st_uid == 0
            && stat.st_rdev == root.dev,
        "actual original UUID device does not own this root",
    )?;
    Ok(OriginalObservation {
        boot_id,
        kernel,
        pid,
        starttime,
        namespaces,
        root,
        boot,
        root_mount_id,
        root_device,
        control_group,
        invocation_id,
        capabilities,
    })
}

pub(crate) struct WorkingColdOwner {
    observation: OriginalObservation,
    locks: Vec<ExistingLock>,
    candidate: String,
    input: SealedInput,
    executable: Guard,
    arguments: String,
}
impl WorkingColdOwner {
    pub(crate) fn acquire(candidate: &str, input: &FilePin) -> Result<Self> {
        let input = SealedInput::open(input)?;
        let before = working_observation(candidate)?;
        singleton(&before)?;
        let executable_path = std::fs::read_link("/proc/self/exe")?;
        let executable = Guard::open(&files::pin_file(&executable_path)?)?;
        let actual = File::open("/proc/self/exe")?;
        ensure(
            fs::stat(&actual)? == *executable.identity(),
            "working cold producer is not its held named executable",
        )?;
        let arguments = bounded(Path::new("/proc/self/cmdline"), 32768)?;
        ensure(
            arguments == exact_arguments(&executable_path, input.pin())?
                || arguments
                    == exact_arguments_for(&executable_path, input.pin(), PUBLICATION_MODE)?
                || arguments == exact_arguments_for(&executable_path, input.pin(), RUN_MODE)?,
            "working cold actual argv differs from its exact source input",
        )?;
        let locks = LOCK_PATHS
            .iter()
            .map(|p| ExistingLock::acquire(Path::new(p), 0))
            .collect::<Result<Vec<_>>>()?;
        let value = Self {
            observation: before,
            locks,
            candidate: candidate.into(),
            input,
            executable,
            arguments,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn revalidate_label_custody(&self) -> Result<()> {
        for lock in &self.locks {
            lock.revalidate()?;
        }
        let observed = working_observation(&self.candidate)?;
        ensure(
            same_observation(&observed, &self.observation),
            "working cold owner changed boot, process, unit or namespace",
        )?;
        singleton(&observed)?;
        self.input.revalidate_custody()?;
        self.executable.revalidate_custody()?;
        ensure(
            fs::stat(&File::open("/proc/self/exe")?)? == *self.executable.identity()
                && bounded(Path::new("/proc/self/cmdline"), 32768)? == self.arguments,
            "working cold actual producer or argv changed",
        )?;
        Ok(())
    }

    pub(crate) fn revalidate(&self) -> Result<()> {
        for lock in &self.locks {
            lock.revalidate()?;
        }
        let observed = working_observation(&self.candidate)?;
        ensure(
            same_observation(&observed, &self.observation),
            "working cold owner changed boot, process, unit or namespace",
        )?;
        singleton(&observed)?;
        self.input.revalidate()?;
        self.executable.revalidate()?;
        ensure(
            fs::stat(&File::open("/proc/self/exe")?)? == *self.executable.identity()
                && bounded(Path::new("/proc/self/cmdline"), 32768)? == self.arguments,
            "working cold actual producer or argv changed",
        )?;
        Ok(())
    }
    pub(crate) fn accept_working_label_batch(
        &mut self,
        batch: &crate::cold_original_data::labels::WorkingLabelBatch,
    ) -> Result<()> {
        ensure(
            batch.candidate_id() == self.candidate
                && self
                    .locks
                    .iter()
                    .map(|lock| lock.path.as_path())
                    .eq(LOCK_PATHS.iter().map(Path::new)),
            "working lock label batch belongs to another live owner or roster",
        )?;
        batch.revalidate()?;
        // The caller's entry source and immutable plan remain under the fixed
        // private RootScope exclusions (or already have their final labels).
        // They are never rebound through a JSON comparison or a fresh open.
        self.input.revalidate_custody()?;
        self.executable.revalidate_custody()?;
        let updates = self
            .locks
            .iter()
            .enumerate()
            .map(|(index, lock)| {
                if let Some(record) = batch
                    .records()
                    .iter()
                    .find(|record| record.paths().iter().any(|path| path == &lock.path))
                {
                    ensure(
                        index != 0,
                        "private VM controller lock is outside host label scope",
                    )?;
                    let after =
                        record.require_held_transition(&lock.path, &lock.held, &lock.identity)?;
                    Ok((lock.identity.clone(), after))
                } else {
                    lock.revalidate()?;
                    Ok((lock.identity.clone(), lock.identity.clone()))
                }
            })
            .collect::<Result<Vec<_>>>()?;
        for (lock, (before, after)) in self.locks.iter_mut().zip(updates) {
            lock.accept_label_identity(&before, &after)?;
        }
        self.revalidate_label_custody()
    }

    // Transfer only genuine duplicates of the same kernel lock descriptions.
    // Fresh return ownership independently re-observes PID1 and the host.
    pub(super) fn fresh_return_parts(
        &self,
    ) -> Result<(String, FilePin, FilePin, Vec<ExistingLock>, String)> {
        self.revalidate()?;
        ensure(
            self.arguments
                == exact_arguments_for(&self.executable.pin().path, self.input.pin(), RUN_MODE)?,
            "only the actual fixed running working owner can enter same-boot recovery",
        )?;
        let locks = self
            .locks
            .iter()
            .map(ExistingLock::try_clone_owned)
            .collect::<Result<Vec<_>>>()?;
        self.revalidate()?;
        Ok((
            self.candidate.clone(),
            self.input.pin().clone(),
            self.executable.pin().clone(),
            locks,
            self.observation.boot_id.clone(),
        ))
    }
    pub(crate) fn boot_id(&self) -> &str {
        &self.observation.boot_id
    }
    pub(crate) fn evidence(&self) -> serde_json::Value {
        serde_json::json!({
            "schema":"droidloom.working-qualification-cold-owner.v1",
            "actual_original":self.observation,"candidate_id":self.candidate,
            "input":self.input.pin(),"actual_producer":self.executable.pin(),
            "actual_producer_identity":self.executable.identity(),
            "locks":self.locks.iter().map(|l|serde_json::json!({
                "path":l.path,"identity":l.identity
            })).collect::<Vec<_>>(),
            "historical_live_retirement_reconstructed":false,
            "qualification_boot_authorized":false
        })
    }
}

impl ExistingLock {
    pub(super) fn try_clone_owned(&self) -> Result<Self> {
        self.revalidate()?;
        let value = Self {
            parent: self.parent.try_clone()?,
            parent_identity: self.parent_identity.clone(),
            name: self.name.clone(),
            held: self.held.try_clone()?,
            identity: self.identity.clone(),
            sha256: self.sha256.clone(),
            path: self.path.clone(),
        };
        value.revalidate()?;
        self.revalidate()?;
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_run_and_recovery_exclude_installed_or_ambiguous_producer_paths() -> Result<()> {
        let executable = Path::new(
            "/var/lib/droidloom-qualification/normal-current/bin/droidloom-ubuntu-fixture",
        );
        let input = FilePin {
            path: "/var/lib/droidloom-qualification/working-current/MATERIALS.json".into(),
            bytes: 1,
            sha256: "1".repeat(64),
        };
        for mode in [RUN_MODE, RECOVERY_MODE] {
            exact_arguments_for(executable, &input, mode)?;
            for wrong in [
                "/usr/bin/droidloom-ubuntu-fixture",
                "/var/lib/droidloom-qualification",
                "/var/lib/droidloom-qualification-other/fixture",
                "/var/lib/droidloom-qualification/../fixture",
                "/var/lib/droidloom-qualification/./fixture",
                "/var/lib/droidloom-qualification//fixture",
                "/var/lib/droidloom-qualification/fixture/",
                "var/lib/droidloom-qualification/fixture",
            ] {
                assert!(
                    exact_arguments_for(Path::new(wrong), &input, mode).is_err(),
                    "{wrong}"
                );
                let mut outside = input.clone();
                outside.path = wrong.into();
                assert!(
                    exact_arguments_for(executable, &outside, mode).is_err(),
                    "{wrong}"
                );
            }
        }
        // Historical read-only prepare/publication operations keep their
        // existing independent source contract.
        exact_arguments_for(Path::new("/usr/bin/historical-producer"), &input, MODE)?;
        exact_arguments_for(
            Path::new("/usr/bin/historical-producer"),
            &input,
            PUBLICATION_MODE,
        )?;
        Ok(())
    }

    #[test]
    fn working_fresh_lock_duplicate_retains_real_exclusion_after_original_drop() -> Result<()> {
        use std::os::unix::fs::PermissionsExt;
        let directory = tempfile::tempdir()?;
        let path = directory.path().join("source.lock");
        std::fs::write(&path, b"existing complete lock contents")?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
        let owner = rustix::process::geteuid().as_raw();
        let first = ExistingLock::acquire(&path, owner)?;
        let duplicate = first.try_clone_owned()?;
        drop(first);
        assert!(ExistingLock::acquire(&path, owner).is_err());
        duplicate.revalidate()?;
        drop(duplicate);
        ExistingLock::acquire(&path, owner)?.revalidate()?;
        Ok(())
    }
    #[test]
    fn working_cold_publication_has_a_distinct_exact_command_without_freeform_mode() -> Result<()> {
        let executable = Path::new("/usr/lib/droidloom/fixture");
        let input = FilePin {
            path: "/var/lib/droidloom-qualification/working-plan.json".into(),
            bytes: 23,
            sha256: "a".repeat(64),
        };
        let preparation = exact_arguments(executable, &input)?;
        let publication = exact_arguments_for(executable, &input, PUBLICATION_MODE)?;
        let before: Vec<_> = preparation.split('\0').collect();
        let after: Vec<_> = publication.split('\0').collect();
        assert_eq!(before.len(), after.len());
        assert_eq!(before[1], MODE);
        assert_eq!(after[1], PUBLICATION_MODE);
        for index in [0, 2, 3, 4, 5, 6] {
            assert_eq!(before[index], after[index]);
        }
        for invalid in [
            "",
            "original-once",
            "reboot",
            "verify-working-publication --force",
        ] {
            assert!(exact_arguments_for(executable, &input, invalid).is_err());
        }
        Ok(())
    }

    #[test]
    fn working_cold_owner_rejects_old_runtime_units_candidates_and_extra_members() -> Result<()> {
        let candidate = "a".repeat(64);
        let invocation = "b".repeat(32);
        let correct = format!("0::{UNIT_PREFIX}{candidate}.service\n");
        working_unit(&correct, &invocation, &candidate)?;
        for wrong in [
            correct.replace(
                "droidloom-working-cold@",
                "droidloom-original-qualification@",
            ),
            correct.replace(
                "droidloom-working-cold@",
                "droidloom-working-qualification@",
            ),
            correct.replace("/system.slice/", "/user.slice/"),
            correct.replace(&candidate, &"c".repeat(64)),
            correct.clone() + "1:name=systemd:/\n",
            correct.trim_end().to_owned(),
        ] {
            assert!(working_unit(&wrong, &invocation, &candidate).is_err());
        }
        assert!(working_unit(&correct, "", &candidate).is_err());
        assert!(working_unit(&correct, &invocation, "short").is_err());
        exact_singleton("72\n", 72)?;
        for bad in ["", "72\n73\n", "73\n", "072\n", "72\n72\n"] {
            assert!(exact_singleton(bad, 72).is_err());
        }
        assert!(exact_singleton("1\n", 1).is_err());
        Ok(())
    }
    #[test]
    fn working_cold_exact_argv_binds_program_mode_plan_and_complete_hash() -> Result<()> {
        let input = FilePin {
            path: "/root/working-plan.json".into(),
            bytes: 321,
            sha256: "a".repeat(64),
        };
        let actual = exact_arguments(Path::new("/root/normal-producer"), &input)?;
        assert_eq!(
            actual.split_terminator('\0').collect::<Vec<_>>(),
            [
                "/root/normal-producer",
                "prepare-working-qualification",
                "--config",
                "/root/working-plan.json",
                "--config-sha256",
                &"a".repeat(64)
            ]
        );
        assert_ne!(
            actual,
            actual.replace("prepare-working-qualification", "run-original-once")
        );
        let mut changed = input.clone();
        changed.sha256 = "b".repeat(64);
        assert_ne!(
            actual,
            exact_arguments(Path::new("/root/normal-producer"), &changed)?
        );
        changed = input.clone();
        changed.path = "/root/../other.json".into();
        assert!(exact_arguments(Path::new("/root/normal-producer"), &changed).is_err());
        changed = input;
        changed.bytes = 0;
        assert!(exact_arguments(Path::new("/root/normal-producer"), &changed).is_err());
        Ok(())
    }
}
