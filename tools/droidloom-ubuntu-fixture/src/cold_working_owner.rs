//! A new live cold owner for H2 preparation on the original kernel.
//! It never constructs OriginalQualificationAuthority or historical retirement.
use super::*;
use crate::cold_original_qualification::materials::Guard;

const MODE: &str = "prepare-working-qualification";
const UNIT_PREFIX: &str = "/system.slice/droidloom-working-cold@";

fn working_unit(cgroup: &str, invocation: &str, candidate: &str) -> Result<String> {
    ensure(
        fs::valid_digest(candidate),
        "working cold candidate is not a full digest",
    )?;
    let expected = format!("{UNIT_PREFIX}{candidate}.service");
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
fn exact_arguments(executable: &Path, input: &FilePin) -> Result<String> {
    ensure(
        input.bytes > 0 && input.bytes <= 16 * 1024 * 1024 && fs::valid_digest(&input.sha256),
        "working cold input has no complete bounded commitment",
    )?;
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
        MODE,
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
fn singleton(observed: &OriginalObservation) -> Result<()> {
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
    let control_group = working_unit(&observed_cgroup, &invocation_id, candidate)?;
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
    for kind in ["user", "pid", "mnt", "net", "ipc", "uts"] {
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
        let arguments = exact_arguments(&executable_path, input.pin())?;
        ensure(
            bounded(Path::new("/proc/self/cmdline"), 32768)? == arguments,
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

#[cfg(test)]
mod tests {
    use super::*;
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
