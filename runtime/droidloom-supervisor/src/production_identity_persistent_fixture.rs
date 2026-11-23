// Included only inside production_identity::tests. No production constructor
// or authority is changed. Every image below is newly created before reserve.

pub(crate) mod persistent_fixture {
    use super::super::*;
    use std::cell::{Cell, RefCell};
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
    use std::os::unix::fs::{DirBuilderExt, FileExt, OpenOptionsExt};
    use std::os::unix::process::CommandExt;
    use std::process::{Child, Command, Stdio};
    use std::time::{Duration, Instant};

    pub(crate) const ROOT: &str = "/opt/p4-persistent-data-syscall-20261120-3b9d-r1";
    pub(crate) const START: u32 = 20_000_000;
    pub(crate) const COUNT: u32 = 100_000;
    pub(crate) const APP: u32 = 10061;
    const CURRENT: &str = "/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json";
    const OWN_CGROUP: &str = "0::/system.slice/p4-persistent-data-syscall-20261120-3b9d-r1.service\n";
    const MKFS: &str = "/usr/sbin/mke2fs";
    const MKFS_BYTES: u64 = 146136;
    const MKFS_SHA: &str = "e42e49656dfc308efeed86f9bfad7746fc22ad1d4a3b0d508b5dba7a4b9a904f";
    const FEATURES: &str = "none,has_journal,ext_attr,resize_inode,dir_index,filetype,extent,64bit,flex_bg,metadata_csum,metadata_csum_seed,sparse_super,large_file,huge_file,dir_nlink,extra_isize";
    const COHORT: &str = "4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b4b";

    fn need(value: bool, reason: &str) -> Result<()> {
        if value { Ok(()) } else { Err(IdentityError::UnsafeCustody(reason.into())) }
    }

    fn stable(left: &Metadata, right: &Metadata) -> bool {
        (left.dev(), left.ino(), left.mode(), left.uid(), left.gid(), left.nlink(), left.len())
            == (right.dev(), right.ino(), right.mode(), right.uid(), right.gid(), right.nlink(), right.len())
    }

    fn create_directory(path: &Path) -> Result<File> {
        fs::DirBuilder::new().mode(0o700).create(path)?;
        let fd = trusted_directory(path, 0, false)?;
        need(fd.metadata()?.mode() == libc::S_IFDIR | 0o700, "new private directory must be exactly root 0700")?;
        Ok(fd)
    }

    fn create_file(parent: &File, name: &str, raw: &[u8]) -> Result<File> {
        let mut file = open_at(parent, name, libc::O_RDWR | libc::O_CREAT | libc::O_EXCL, 0o600)?;
        file.write_all(raw)?;
        file.sync_all()?;
        let meta = file.metadata()?;
        need(meta.mode() == libc::S_IFREG | 0o600 && meta.uid() == 0 && meta.gid() == 0 && meta.nlink() == 1,
            "create-only root-private singleton fixture")?;
        Ok(file)
    }

    pub(crate) fn digest(file: &File) -> Result<String> {
        let before = file.metadata()?;
        need(before.is_file() && before.nlink() == 1 && before.len() <= 128 * 1024 * 1024,
            "bounded fresh fixture/tool digest")?;
        let mut sha = Sha256::new();
        let mut block = [0u8; 65536];
        let mut offset = 0;
        while offset < before.len() {
            let count = (before.len() - offset).min(block.len() as u64) as usize;
            file.read_exact_at(&mut block[..count], offset)?;
            sha.update(&block[..count]);
            offset += count as u64;
        }
        need(same_metadata(&before, &file.metadata()?), "whole held digest bookend")?;
        Ok(format!("{:x}", sha.finalize()))
    }

    #[derive(Clone, Copy, Debug)]
    pub(crate) enum Case { Positive, Dirty, Foreign, SendUnknown, Swapped, CleanupHeld }
    impl Case {
        fn name(self) -> &'static str {
            match self {
                Self::Positive => "positive", Self::Dirty => "dirty",
                Self::Foreign => "foreign", Self::SendUnknown => "send-unknown", Self::Swapped => "swapped",
                Self::CleanupHeld => "cleanup-held",
            }
        }
    }

    #[derive(Clone, Copy)]
    pub(crate) enum ImageRole { Data, Metadata, System, Vendor }
    impl ImageRole {
        pub(crate) fn name(self) -> &'static str {
            match self { Self::Data => "data.img", Self::Metadata => "metadata.img", Self::System => "system.img", Self::Vendor => "vendor.img" }
        }
        pub(crate) fn bytes(self) -> u64 {
            match self { Self::Data => 64 * 1024 * 1024, _ => 32 * 1024 * 1024 }
        }
        pub(crate) fn uuid(self) -> &'static str {
            match self {
                Self::Data => "748861cb-65b5-4fcb-8aba-5c5dc40811df",
                Self::Metadata => "a91dcb63-4c0a-49d2-b43e-14152cd85bdd",
                Self::System => "b4408b1b-e0aa-4930-9dac-548a7f449aa1",
                Self::Vendor => "4c8aeb2e-e847-4935-b5ca-ea07a3f87961",
            }
        }
    }

    struct HeldNamed {
        path: PathBuf,
        fd: File,
        metadata: Metadata,
    }
    impl HeldNamed {
        fn metadata_only(path: &str) -> Result<Self> {
            let fd = OpenOptions::new().read(true).custom_flags(libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW).open(path)?;
            let metadata = fd.metadata()?;
            need(!metadata.file_type().is_symlink(), "metadata bookend rejects links")?;
            Ok(Self { path: path.into(), fd, metadata })
        }
        fn verify(&self) -> Result<()> {
            need(same_metadata(&self.metadata, &self.fd.metadata()?)
                && same_metadata(&self.metadata, &fs::symlink_metadata(&self.path)?),
                "held original metadata-only bookend changed")
        }
    }

    // A failed mkfs which has not been positively reaped keeps its actual
    // process and all owned file descriptions. Only the separately reviewed
    // dedicated outer unit may subsequently finish that uncertain teardown.
    struct RetainedFormat {
        _child: Child,
        _pidfd: Option<OwnedFd>,
        _image: File,
        _directory: File,
        _tree: Option<File>,
        _tool: File,
        _stdout: File,
        _stderr: File,
    }

    fn format_exit_readable(pidfd: &OwnedFd, deadline: Instant) -> io::Result<bool> {
        loop {
            let Some(left) = deadline.checked_duration_since(Instant::now()) else { return Ok(false); };
            if left.is_zero() { return Ok(false); }
            let millis = left.as_millis().clamp(1, 20) as i32;
            let mut poll = libc::pollfd { fd: pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
            let rc = unsafe { libc::poll(&mut poll, 1, millis) };
            if rc > 0 && poll.revents & libc::POLLIN != 0 { return Ok(true); }
            if rc > 0 { return Err(io::Error::other("owned mkfs pidfd returned no exit readiness")); }
            if rc < 0 {
                let error = io::Error::last_os_error();
                if error.kind() != io::ErrorKind::Interrupted { return Err(error); }
            }
        }
    }

    /// One fixed run owns its directory, tool, deadline and read-only bookends.
    /// Drop deliberately preserves names. Only checked per-case retirement may
    /// unlink its own backing inodes; failure never recursively removes a tree.
    pub(crate) struct FixtureRun {
        root: File,
        root_metadata: Metadata,
        tool: File,
        tool_metadata: Metadata,
        started: Instant,
        mounts: Vec<u8>,
        children: Vec<u8>,
        namespaces: Vec<(String, File, Metadata)>,
        current: HeldNamed,
        cell: HeldNamed,
        cgroup: File,
        cgroup_metadata: Metadata,
        cgroup_path: String,
        cgroup_controls: Vec<(String, Vec<u8>)>,
        commands: RefCell<Vec<serde_json::Value>>,
        retained_commands: RefCell<Vec<RetainedFormat>>,
    }

    impl Drop for FixtureRun {
        fn drop(&mut self) {
            // Unknown process custody is not released by an error return or
            // test unwind. The fixed outer cgroup remains the final owner.
            for owned in self.retained_commands.get_mut().drain(..) {
                std::mem::forget(owned);
            }
        }
    }

    fn read_bounded(path: &Path, limit: usize) -> Result<Vec<u8>> {
        let mut fd = OpenOptions::new().read(true).custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW).open(path)?;
        let mut raw = Vec::new();
        (&mut fd).take(limit as u64 + 1).read_to_end(&mut raw)?;
        need(raw.len() <= limit, "bounded fixture input")?;
        Ok(raw)
    }

    fn disjoint_host_ranges() -> Result<()> {
        for path in ["/etc/subuid", "/etc/subgid"] {
            let raw = read_bounded(Path::new(path), 1024 * 1024)?;
            let text = std::str::from_utf8(&raw).map_err(|_| IdentityError::Record("host grant encoding".into()))?;
            for line in text.lines().filter(|s| !s.is_empty() && !s.starts_with('#')) {
                let fields: Vec<_> = line.split(':').collect();
                need(fields.len() == 3, "complete actual host grant row")?;
                let start: u64 = fields[1].parse().map_err(|_| IdentityError::Record("host range start".into()))?;
                let count: u64 = fields[2].parse().map_err(|_| IdentityError::Record("host range count".into()))?;
                let end = start.checked_add(count).ok_or_else(|| IdentityError::Record("host range overflow".into()))?;
                need(end <= u64::from(START) || start >= u64::from(START + COUNT), "test range overlaps a real host grant")?;
            }
        }
        let raw = read_bounded(Path::new("/etc/droidloom/cell.json"), 65536)?;
        let cell: serde_json::Value = serde_json::from_slice(&raw).map_err(|e| IdentityError::Record(e.to_string()))?;
        for key in ["subordinate_uids", "subordinate_gids"] {
            let range = cell.get(key).ok_or_else(|| IdentityError::Record("actual cell range absent".into()))?;
            let start = range.get("start").and_then(|v| v.as_u64()).ok_or_else(|| IdentityError::Record("cell start".into()))?;
            let count = range.get("count").and_then(|v| v.as_u64()).ok_or_else(|| IdentityError::Record("cell count".into()))?;
            let end = start.checked_add(count).ok_or_else(|| IdentityError::Record("cell range overflow".into()))?;
            need(end <= u64::from(START) || start >= u64::from(START + COUNT), "test range overlaps production cell")?;
        }
        Ok(())
    }

    impl FixtureRun {
        pub(crate) fn create() -> Result<Self> {
            need(unsafe { libc::getuid() } == 0 && unsafe { libc::geteuid() } == 0
                && unsafe { libc::getgid() } == 0 && unsafe { libc::getegid() } == 0,
                "separately reviewed real initial-root fixture required")?;
            need(read_bounded(Path::new("/proc/self/uid_map"), 256)?.split(|b| *b == b'\n').filter(|s| !s.is_empty()).count() == 1,
                "single initial UID-map row required")?;
            let map = fs::read_to_string("/proc/self/uid_map")?;
            need(map.split_ascii_whitespace().collect::<Vec<_>>() == ["0", "0", "4294967295"], "actual initial user namespace required")?;
            let mut affinity: libc::cpu_set_t = unsafe { std::mem::zeroed() };
            need(unsafe { libc::sched_getaffinity(0, std::mem::size_of_val(&affinity), &mut affinity) } == 0,
                "actual fixture affinity")?;
            let cpus: Vec<_> = (0..libc::CPU_SETSIZE as usize).filter(|cpu| unsafe { libc::CPU_ISSET(*cpu, &affinity) }).collect();
            need(cpus == [23] && unsafe { libc::sysconf(libc::_SC_NPROCESSORS_ONLN) } >= 3,
                "single fixed CPU23 and at least two other online host CPUs")?;
            let core = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
            need(unsafe { libc::setrlimit(libc::RLIMIT_CORE, &core) } == 0, "no core output")?;
            disjoint_host_ranges()?;
            let cgroup_path = fs::read_to_string("/proc/self/cgroup")?;
            need(cgroup_path == OWN_CGROUP, "fixed dedicated fixture unit cgroup required")?;
            let relative = cgroup_path.strip_prefix("0::/").and_then(|s| s.strip_suffix('\n'))
                .ok_or_else(|| IdentityError::UnsafeCustody("one actual cgroup2 membership".into()))?;
            need(!relative.is_empty() && !relative.split('/').any(|p| p.is_empty() || p == "." || p == ".."), "owned nonroot cgroup")?;
            let cgroup = trusted_directory(&Path::new("/sys/fs/cgroup").join(relative), 0, false)?;
            let cgroup_metadata = cgroup.metadata()?;
            let mut cgroup_stat: libc::statfs = unsafe { std::mem::zeroed() };
            need(unsafe { libc::fstatfs(cgroup.as_raw_fd(), &mut cgroup_stat) } == 0 && cgroup_stat.f_type == 0x6367_7270,
                "actual held cgroup2 controller scope")?;
            let mut cgroup_controls = Vec::new();
            for (name, expected) in [("memory.max", "1073741824\n"), ("memory.swap.max", "0\n"), ("pids.max", "32\n")] {
                let raw = read_bounded(&PathBuf::from(format!("/proc/self/fd/{}/{}", cgroup.as_raw_fd(), name)), 256)?;
                need(raw == expected.as_bytes(), "exact own fixture cgroup bound")?;
                cgroup_controls.push((name.into(), raw));
            }
            let cpu = read_bounded(&PathBuf::from(format!("/proc/self/fd/{}/cpu.max", cgroup.as_raw_fd())), 256)?;
            let text = std::str::from_utf8(&cpu).map_err(|_| IdentityError::Record("cpu budget encoding".into()))?;
            let parts: Vec<_> = text.split_ascii_whitespace().collect();
            need(parts.len() == 2 && parts[0] != "max", "finite actual CPU quota")?;
            let quota: u64 = parts[0].parse().map_err(|_| IdentityError::Record("quota".into()))?;
            let period: u64 = parts[1].parse().map_err(|_| IdentityError::Record("period".into()))?;
            need(quota > 0 && period > 0 && quota <= period, "at most one CPU quota")?;
            cgroup_controls.push(("cpu.max".into(), cpu));
            let tool = OpenOptions::new().read(true).custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW).open(MKFS)?;
            let tool_metadata = tool.metadata()?;
            need(tool_metadata.mode() == libc::S_IFREG | 0o755 && tool_metadata.uid() == 0 && tool_metadata.gid() == 0
                && tool_metadata.len() == MKFS_BYTES && digest(&tool)? == MKFS_SHA, "exact actual reviewed mke2fs")?;
            let current = HeldNamed::metadata_only(CURRENT)?;
            let cell = HeldNamed::metadata_only("/etc/droidloom/cell.json")?;
            let mounts = fs::read("/proc/self/mountinfo")?;
            let tid = unsafe { libc::syscall(libc::SYS_gettid) };
            let children = fs::read(format!("/proc/self/task/{tid}/children"))?;
            need(children.is_empty(), "fresh fixture thread has no existing child")?;
            let mut namespaces = Vec::new();
            for name in ["user", "mnt", "pid", "ipc", "uts", "net", "cgroup", "time"] {
                let fd = File::open(format!("/proc/self/ns/{name}"))?;
                let meta = fd.metadata()?;
                namespaces.push((name.into(), fd, meta));
            }
            let parent = trusted_directory(Path::new("/opt"), 0, false)?;
            let parent_meta = parent.metadata()?;
            let root = create_directory(Path::new(ROOT))?;
            need((parent_meta.dev(), parent_meta.ino(), parent_meta.mode(), parent_meta.uid(), parent_meta.gid())
                == { let m = fs::symlink_metadata("/opt")?; (m.dev(), m.ino(), m.mode(), m.uid(), m.gid()) }, "same /opt authority across create-only root")?;
            let root_metadata = root.metadata()?;
            Ok(Self { root, root_metadata, tool, tool_metadata, started: Instant::now(), mounts, children,
                namespaces, current, cell, cgroup, cgroup_metadata, cgroup_path, cgroup_controls,
                commands: RefCell::new(Vec::new()), retained_commands: RefCell::new(Vec::new()) })
        }

        pub(crate) fn operation_time(&self) -> Result<()> {
            need(self.started.elapsed() < Duration::from_secs(150), "150-second work cutoff reserves 30 seconds for actual teardown")
        }

        pub(crate) fn verify(&self, complete: bool) -> Result<()> {
            need(self.started.elapsed() < Duration::from_secs(180), "same 180-second whole fixture deadline")?;
            let root = fs::symlink_metadata(ROOT)?;
            need((root.dev(), root.ino(), root.mode(), root.uid(), root.gid()) ==
                (self.root_metadata.dev(), self.root_metadata.ino(), self.root_metadata.mode(), self.root_metadata.uid(), self.root_metadata.gid())
                && stable(&root, &self.root.metadata()?), "same create-only private root")?;
            need(same_metadata(&self.tool_metadata, &self.tool.metadata()?) && same_metadata(&self.tool_metadata, &fs::symlink_metadata(MKFS)?)
                && digest(&self.tool)? == MKFS_SHA, "held mkfs tool unchanged")?;
            self.current.verify()?;
            self.cell.verify()?;
            need(fs::read_to_string("/proc/self/cgroup")? == self.cgroup_path, "actual controller cgroup unchanged")?;
            let relative = self.cgroup_path.strip_prefix("0::/").and_then(|s| s.strip_suffix('\n')).unwrap();
            let named = trusted_directory(&Path::new("/sys/fs/cgroup").join(relative), 0, false)?;
            for actual in [self.cgroup.metadata()?, named.metadata()?] {
                need((actual.dev(), actual.ino(), actual.mode(), actual.uid(), actual.gid()) ==
                    (self.cgroup_metadata.dev(), self.cgroup_metadata.ino(), self.cgroup_metadata.mode(), self.cgroup_metadata.uid(), self.cgroup_metadata.gid()),
                    "same held and named original owned cgroup")?;
            }
            for (name, original) in &self.cgroup_controls {
                need(read_bounded(&PathBuf::from(format!("/proc/self/fd/{}/{}", self.cgroup.as_raw_fd(), name)), 256)? == *original,
                    "held cgroup bound changed")?;
            }
            let events = read_bounded(&PathBuf::from(format!("/proc/self/fd/{}/memory.events", self.cgroup.as_raw_fd())), 4096)?;
            let events = std::str::from_utf8(&events).map_err(|_| IdentityError::Record("memory event encoding".into()))?;
            for key in ["oom", "oom_kill", "oom_group_kill"] {
                let rows: Vec<_> = events.lines().filter_map(|line| line.split_once(' ')).filter(|(name, _)| *name == key).collect();
                need(rows.len() == 1 && rows[0].1 == "0", "no OOM event in this actual owned fixture scope")?;
            }
            need(fs::read("/proc/self/mountinfo")? == self.mounts, "host mount inventory unchanged")?;
            for (name, fd, before) in &self.namespaces {
                let after = File::open(format!("/proc/self/ns/{name}"))?.metadata()?;
                need((before.dev(), before.ino()) == (fd.metadata()?.dev(), fd.metadata()?.ino())
                    && (before.dev(), before.ino()) == (after.dev(), after.ino()), "held and named host namespace unchanged")?;
            }
            if complete {
                need(self.retained_commands.borrow().is_empty(), "no uncertain owned mkfs remains retained")?;
                let tid = unsafe { libc::syscall(libc::SYS_gettid) };
                need(fs::read(format!("/proc/self/task/{tid}/children"))? == self.children, "all original owned children reaped")?;
            }
            Ok(())
        }

        pub(crate) fn case(&self, case: Case) -> Result<PersistentFixture<'_>> {
            self.operation_time()?;
            self.verify(false)?;
            let path = Path::new(ROOT).join(case.name());
            let directory = create_directory(&path)?;
            for (name, content) in [
                ("passwd", "alex:x:1000:1000::/home/alex:/bin/bash\ndroidloom-cell-u1000:x:997:997::/nonexistent:/usr/sbin/nologin\n".to_owned()),
                ("group", "alex:x:1000:\ndroidloom-cell-u1000:x:997:\n".to_owned()),
                ("subuid", format!("alex:100000:65536\ndroidloom-cell-u1000:{START}:{COUNT}\n")),
                ("subgid", format!("alex:100000:65536\n997:{START}:{COUNT}\n")),
            ] { create_file(&directory, name, content.as_bytes())?; }
            let backings_path = path.join("backings");
            let backings = create_directory(&backings_path)?;
            let data = self.format(&path, &backings, ImageRole::Data, None)?;
            let metadata = self.format(&path, &backings, ImageRole::Metadata, None)?;
            let nodes = [data.metadata()?, metadata.metadata()?];
            let paths = AuthorityPaths { passwd: path.join("passwd"), group: path.join("group"),
                subuid: path.join("subuid"), subgid: path.join("subgid"), owner: 0 };
            let authority = IdentityAuthority::read_paths(1000, IdRange { start: START, count: COUNT },
                IdRange { start: START, count: COUNT }, paths)?;
            // No reservation or HeldBackings existed before both real mkfs runs.
            let value = PersistentFixture { run: self, path, directory, backings_path, backings,
                files: [data, metadata], nodes, authority, state: Cell::new(FixtureState::Fresh) };
            value.verify()?;
            Ok(value)
        }

        pub(crate) fn format(&self, case_path: &Path, parent: &File, role: ImageRole, tree: Option<&File>) -> Result<File> {
            self.operation_time()?;
            need(case_path.parent() == Some(Path::new(ROOT)), "mkfs only inside this run's fixed case")?;
            let path = fs::read_link(format!("/proc/self/fd/{}", parent.as_raw_fd()))?;
            let leaf = path.file_name().and_then(|s| s.to_str()).ok_or_else(|| IdentityError::Record("fixture parent name".into()))?;
            need(path.parent() == Some(case_path) && (leaf == "backings" || leaf.starts_with("base-")),
                "mkfs parent must be this actual fresh case's backing or base directory")?;
            let named = trusted_directory(&path, 0, false)?;
            need((named.metadata()?.dev(), named.metadata()?.ino()) == (parent.metadata()?.dev(), parent.metadata()?.ino()),
                "held actual mkfs directory matches its fresh private path")?;
            if let Some(tree) = tree {
                let path = fs::read_link(format!("/proc/self/fd/{}", tree.as_raw_fd()))?;
                let name = path.file_name().and_then(|s| s.to_str()).ok_or_else(|| IdentityError::Record("fixture seed name".into()))?;
                let parent_path = fs::read_link(format!("/proc/self/fd/{}", parent.as_raw_fd()))?;
                need(path.parent() == Some(parent_path.as_path()) && ["system-tree", "vendor-tree"].contains(&name),
                    "fixed seed tree inside this same owned image directory")?;
                let named = trusted_directory(&path, 0, false)?;
                need((named.metadata()?.dev(), named.metadata()?.ino()) == (tree.metadata()?.dev(), tree.metadata()?.ino()),
                    "same actual new immutable seed directory")?;
            }
            let file = create_file(parent, role.name(), b"")?;
            file.set_len(role.bytes())?;
            file.sync_all()?;
            let before = file.metadata()?;
            let output_name = format!("{}-mke2fs.stdout", role.name());
            let errors_name = format!("{}-mke2fs.stderr", role.name());
            let case = trusted_directory(case_path, 0, false)?;
            let stdout = create_file(&case, &output_name, b"")?;
            let stderr = create_file(&case, &errors_name, b"")?;
            let mut command = Command::new(format!("/proc/self/fd/{}", self.tool.as_raw_fd()));
            command.arg0(MKFS).args(["-F", "-t", "ext4", "-b", "4096", "-I", "256", "-m", "0", "-U", role.uuid(),
                "-O", FEATURES, "-E", "lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0"]);
            if let Some(tree) = tree { command.args(["-d", &format!("/proc/self/fd/{}", tree.as_raw_fd())]); }
            command.arg(format!("/proc/self/fd/{}", file.as_raw_fd())).env_clear().env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
                .env("LC_ALL", "C").env("HOME", "/").stdin(Stdio::null())
                .stdout(Stdio::from(stdout.try_clone()?)).stderr(Stdio::from(stderr.try_clone()?));
            let body_fd = file.as_raw_fd();
            let tree_fd = tree.map(|f| f.as_raw_fd());
            // These potentially fallible clones precede child creation. On an
            // uncertain exit all actual custody can therefore be retained.
            let held_parent = parent.try_clone()?;
            let held_tool = self.tool.try_clone()?;
            let held_tree = tree.map(File::try_clone).transpose()?;
            let parent_pid = unsafe { libc::getpid() };
            unsafe { command.pre_exec(move || {
                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL, 0, 0, 0) != 0 || libc::getppid() != parent_pid {
                    return Err(io::Error::last_os_error());
                }
                for fd in [Some(body_fd), tree_fd].into_iter().flatten() {
                    if libc::fcntl(fd, libc::F_SETFD, 0) != 0 { return Err(io::Error::last_os_error()); }
                }
                Ok(())
            }); }
            let mut child = command.spawn()?;
            let raw_pidfd = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
            if raw_pidfd < 0 {
                // This is still exactly our unreaped std::process::Child. A
                // failure is retained, never a positive or a numeric discovery.
                let original = io::Error::last_os_error();
                let _ = child.kill();
                let deadline = Instant::now() + Duration::from_secs(2);
                let status = loop {
                    match child.try_wait() {
                        Ok(Some(status)) => break Some(status),
                        Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(20)),
                        _ => break None,
                    }
                };
                self.commands.borrow_mut().push(serde_json::json!({"role":role.name(),"pid":child.id(),
                    "pidfd_open_error":original.to_string(),"reaped":status.is_some(),
                    "exit_code":status.as_ref().and_then(|value| value.code()),"passed":false,
                    "original_pidfd_held_until_reap":false,"retained_custody":status.is_none()}));
                if status.is_none() {
                    self.retained_commands.borrow_mut().push(RetainedFormat { _child:child, _pidfd:None,
                        _image:file, _directory:held_parent, _tree:held_tree,
                        _tool:held_tool, _stdout:stdout, _stderr:stderr });
                }
                return Err(original.into());
            }
            let pidfd = unsafe { OwnedFd::from_raw_fd(raw_pidfd as i32) };
            let deadline = (Instant::now() + Duration::from_secs(20)).min(self.started + Duration::from_secs(150));
            let ready = format_exit_readable(&pidfd, deadline);
            let timed_out = !matches!(ready, Ok(true));
            let mut cleanup_error = ready.err().map(|error| error.to_string());
            let readable = if timed_out {
                let signal = unsafe { libc::syscall(libc::SYS_pidfd_send_signal, pidfd.as_raw_fd(),
                    libc::SIGKILL, std::ptr::null::<libc::siginfo_t>(), 0) };
                if signal < 0 { cleanup_error = Some(io::Error::last_os_error().to_string()); }
                match format_exit_readable(&pidfd, Instant::now() + Duration::from_secs(2)) {
                    Ok(value) => value,
                    Err(error) => { cleanup_error = Some(error.to_string()); false }
                }
            } else { true };
            let status = if readable {
                match child.try_wait() {
                    Ok(value) => value,
                    Err(error) => { cleanup_error = Some(error.to_string()); None }
                }
            } else { None };
            let Some(status) = status else {
                self.commands.borrow_mut().push(serde_json::json!({"role":role.name(),"pid":child.id(),
                    "timed_out":timed_out,"reaped":false,"cleanup_error":cleanup_error,
                    "original_pidfd_retained":true,"retained_custody":true,"passed":false}));
                self.retained_commands.borrow_mut().push(RetainedFormat { _child:child, _pidfd:Some(pidfd),
                    _image:file, _directory:held_parent, _tree:held_tree,
                    _tool:held_tool, _stdout:stdout, _stderr:stderr });
                return Err(IdentityError::UnsafeCustody("original mkfs exit not proven within bounded teardown; custody retained".into()));
            };
            let exit = status.code();
            self.commands.borrow_mut().push(serde_json::json!({"role":role.name(),"pid":child.id(),
                "exit_code":exit,"timed_out":timed_out,"reaped":true,"cleanup_error":cleanup_error,
                "original_pidfd_held_until_reap":true,"retained_custody":false,
                "stdout_sha256":digest(&stdout)?,"stderr_sha256":digest(&stderr)?,
                "stdout_bytes":stdout.metadata()?.len(),"stderr_bytes":stderr.metadata()?.len()}));
            drop(pidfd);
            need(status.success() && !timed_out, "actual fixed mkfs and original owned reap must succeed")?;
            need(stable(&before, &file.metadata()?), "mkfs changed only its own file contents")?;
            let named = open_at(parent, role.name(), libc::O_PATH, 0)?;
            need(same_metadata(&file.metadata()?, &named.metadata()?), "mkfs original source inode remains named")?;
            file.sync_all()?;
            Ok(file)
        }

        pub(crate) fn report(&self, value: &serde_json::Value) -> Result<()> {
            let mut complete = value.clone();
            complete["mkfs_commands"] = serde_json::Value::Array(self.commands.borrow().clone());
            complete["production_ready"] = serde_json::Value::Bool(false);
            complete["runtime_qualified"] = serde_json::Value::Bool(false);
            complete["Android_started"] = serde_json::Value::Bool(false);
            complete["original_data_images_opened"] = serde_json::Value::Bool(false);
            let raw = serde_json::to_vec_pretty(&complete).map_err(|e| IdentityError::Record(e.to_string()))?;
            create_file(&self.root, "ACTUAL-CONTROLS.json", &raw)?;
            self.root.sync_all()?;
            Ok(())
        }
    }

    /// Unforgeable within non-test builds: its constructor is cfg(test), fixed
    /// path, create-only and finishes actual formatting before exposing reserve.
    #[derive(Clone, Copy, Eq, PartialEq)]
    enum FixtureState { Fresh, Reserved, BodyClaimed, Retired, Removed }

    pub(crate) struct PersistentFixture<'a> {
        run: &'a FixtureRun,
        path: PathBuf,
        directory: File,
        backings_path: PathBuf,
        backings: File,
        files: [File; 2],
        nodes: [Metadata; 2],
        authority: IdentityAuthority,
        state: Cell<FixtureState>,
    }

    impl PersistentFixture<'_> {
        pub(crate) fn path(&self) -> &Path { &self.path }
        pub(crate) fn backings_path(&self) -> &Path { &self.backings_path }
        pub(crate) fn parent(&self) -> &File { &self.backings }
        pub(crate) fn files(&self) -> &[File; 2] { &self.files }
        pub(crate) fn run(&self) -> &FixtureRun { self.run }
        pub(crate) fn verify(&self) -> Result<()> {
            self.run.verify(false)?;
            let parent = trusted_directory(&self.backings_path, 0, false)?;
            need((parent.metadata()?.dev(), parent.metadata()?.ino()) == (self.backings.metadata()?.dev(), self.backings.metadata()?.ino()), "same fresh backing parent")?;
            let case = trusted_directory(&self.path, 0, false)?;
            need((case.metadata()?.dev(), case.metadata()?.ino()) == (self.directory.metadata()?.dev(), self.directory.metadata()?.ino()), "same fresh case parent")?;
            for (index, name) in ["data.img", "metadata.img"].into_iter().enumerate() {
                let named = open_at(&self.backings, name, libc::O_PATH, 0)?;
                need(stable(&self.nodes[index], &named.metadata()?) && stable(&self.nodes[index], &self.files[index].metadata()?), "exact formatted fixture inode role")?;
            }
            Ok(())
        }
        pub(crate) fn reserve(&self) -> Result<IdentityLease> {
            self.verify()?;
            need(matches!(self.state.get(), FixtureState::Fresh | FixtureState::Retired),
                "one original private body lifetime at a time")?;
            let lease = self.authority.reserve_at(&self.path.join("registry"), 0, COHORT,
                HeldBackings::open(&self.backings_path, 0)?)?;
            lease.revalidate_for_broker()?;
            self.state.set(FixtureState::Reserved);
            Ok(lease)
        }
        pub(crate) fn claim_body_access(&self) -> Result<()> {
            self.verify()?;
            need(self.state.get() == FixtureState::Reserved, "exactly one typed provider/header observer may consume this fresh lifetime")?;
            self.state.set(FixtureState::BodyClaimed);
            Ok(())
        }
        pub(crate) fn accept_retirement(&self,
            proof: &crate::production_mounts::persistent_data::private_control::VerifiedPrivateRetirement) -> Result<()> {
            self.verify()?;
            need(self.state.get() == FixtureState::BodyClaimed, "retirement belongs to the actually claimed body lifetime")?;
            proof.matches_fixture(self).map_err(|e| IdentityError::UnsafeCustody(e.to_string()))?;
            need(self.lease_available()?, "whole original lifetime lease released after actual retirement")?;
            self.state.set(FixtureState::Retired);
            Ok(())
        }
        pub(crate) fn lease_available(&self) -> Result<bool> {
            let file = OpenOptions::new().read(true).write(true).custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
                .open(self.path.join("registry/u1000.lease"))?;
            let rc = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
            if rc == 0 { return Ok(true); } // Close this new OFD; never LOCK_UN the original.
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::WouldBlock { Ok(false) } else { Err(error.into()) }
        }
        pub(crate) fn verify_lease(&self, lease: &IdentityLease) -> Result<()> {
            self.verify()?;
            lease.revalidate_for_broker()?;
            need(lease.host_uid() == 1000 && lease.broker_cohort() == COHORT
                && lease.broker_ranges() == (IdRange { start: START, count: COUNT }, IdRange { start: START, count: COUNT }),
                "same private fixture real lease binding")?;
            lease.broker_verify_backing(&self.files[0], &self.files[1])
        }
        pub(crate) fn remove_retired_images(&self,
            proof: &crate::production_mounts::persistent_data::private_control::VerifiedPrivateRetirement) -> Result<()> {
            self.verify()?;
            proof.matches_fixture(self).map_err(|e| IdentityError::UnsafeCustody(e.to_string()))?;
            need(self.lease_available()?, "actual unbind then whole original lease release before unlink")?;
            self.accept_retirement(proof)?;
            for (index, name) in ["data.img", "metadata.img"].into_iter().enumerate() {
                need(stable(&self.nodes[index], &self.files[index].metadata()?), "same owned inode before unlink")?;
                let name = std::ffi::CString::new(name).unwrap();
                if unsafe { libc::unlinkat(self.backings.as_raw_fd(), name.as_ptr(), 0) } != 0 { return Err(io::Error::last_os_error().into()); }
                need(self.files[index].metadata()?.nlink() == 0, "original fixture pathname actually removed")?;
            }
            self.backings.sync_all()?;
            self.state.set(FixtureState::Removed);
            Ok(())
        }
    }

}
