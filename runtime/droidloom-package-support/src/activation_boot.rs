//! First physical boot of an admitted shared-kernel generation.
//! Preparation is read-only with respect to the live boot configuration. Only
//! the original installation owner's opaque permit can publish and arm it.
use super::{
    Result,
    activation_files::{self as files, HeldFile},
    activation_labels::Labeler,
    activation_owner::InstallationPermit,
    activation_platform::PlatformInputs,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{fs::MetadataExt, process::CommandExt},
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

const BOARD: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);
const SCRIPT: &str = "/etc/grub.d/42_droidloom";
const CONFIG: &str = "/boot/grub/grub.cfg";
const ENVIRONMENT: &str = "/boot/grub/grubenv";
const MIB: u64 = 1024 * 1024;

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn root_file(path: &Path, limit: u64) -> Result<HeldFile> {
    let held = HeldFile::open(&files::pin_file(path)?, limit)?;
    require(
        held.identity().uid == 0 && held.identity().gid == 0,
        "boot input is not owned by root",
    )?;
    files::no_privilege_xattrs(held.file())?;
    Ok(held)
}

struct OwnedCommand {
    child: Child,
    pidfd: File,
    reaped: bool,
}
impl OwnedCommand {
    fn exited(&self) -> Result<Option<bool>> {
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        // WNOWAIT retains the original child's PID while its process group is
        // retired, so cleanup can never signal a recycled group number.
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        if unsafe { info.si_pid() } == 0 {
            return Ok(None);
        }
        Ok(Some(
            info.si_code == libc::CLD_EXITED && unsafe { info.si_status() } == 0,
        ))
    }
    fn retire(&mut self) -> Result<()> {
        if self.reaped {
            return Ok(());
        }
        let pid = i32::try_from(self.child.id())?;
        if unsafe { libc::kill(-pid, libc::SIGKILL) } != 0
            && std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(std::io::Error::last_os_error().into());
        }
        self.child.wait()?;
        self.reaped = true;
        Ok(())
    }
}
impl Drop for OwnedCommand {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    self.pidfd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                )
            };
            let _ = self.retire();
        }
    }
}

/// Commands and their arguments are selected only by this module. A JSON plan
/// cannot name an executable, command line or GRUB expression.
fn command(area: &Path, name: &str, executable: &str, args: &[&str]) -> Result<Vec<u8>> {
    let tool = root_file(Path::new(executable), 32 * MIB)?;
    require(
        tool.identity().mode & 0o111 != 0,
        "boot tool is not executable",
    )?;
    let out_path = area.join(format!("{name}.stdout"));
    let err_path = area.join(format!("{name}.stderr"));
    let out = files::new_file(&out_path, 0o600)?;
    let err = files::new_file(&err_path, 0o600)?;
    // A script's interpreter opens /proc/self/fd/N after exec. Preserve this
    // dedicated duplicate across exec rather than losing it to CLOEXEC.
    let inherited = unsafe { libc::fcntl(tool.file().as_raw_fd(), libc::F_DUPFD, 3) };
    if inherited < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let inherited = unsafe { File::from_raw_fd(inherited) };
    let mut process = Command::new(format!("/proc/self/fd/{}", inherited.as_raw_fd()));
    process
        .args(args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C")
        .env("LC_ALL", "C")
        .env("DEBIAN_FRONTEND", "noninteractive")
        .env("GRUB_DISABLE_OS_PROBER", "true")
        .current_dir("/")
        .stdin(Stdio::null())
        .stdout(out.try_clone()?)
        .stderr(err.try_clone()?);
    unsafe {
        process.pre_exec(|| {
            if libc::setsid() < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    tool.revalidate()?;
    let mut child = process.spawn()?;
    let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
    if fd < 0 {
        let error = std::io::Error::last_os_error();
        let _ = unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
        let _ = child.wait();
        return Err(error.into());
    }
    let mut owned = OwnedCommand {
        child,
        pidfd: unsafe { File::from_raw_fd(fd as i32) },
        reaped: false,
    };
    let deadline = Instant::now() + Duration::from_secs(120);
    loop {
        require(
            Instant::now() < deadline,
            "normal boot command exceeded its deadline",
        )?;
        require(
            out.metadata()?.len() <= MIB && err.metadata()?.len() <= MIB,
            "normal boot command exceeded its output bound",
        )?;
        if let Some(success) = owned.exited()? {
            require(
                Instant::now() < deadline,
                "normal boot command completed after its deadline",
            )?;
            owned.retire()?;
            out.sync_all()?;
            err.sync_all()?;
            tool.revalidate()?;
            require(
                success,
                &format!(
                    "normal boot command {name} failed; see {}",
                    err_path.display()
                ),
            )?;
            return root_file(&out_path, MIB)?.read_all(MIB);
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn valid_uuid(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit() && !b.is_ascii_uppercase()
            }
        })
}
fn token(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
}
fn text_line(bytes: &[u8]) -> Result<&str> {
    let text = std::str::from_utf8(bytes)?;
    let line = text
        .strip_suffix('\n')
        .ok_or("normal boot query lacks a terminal newline")?;
    require(
        !line.contains(['\n', '\r', '\0']),
        "normal boot query contains extra records",
    )?;
    Ok(line)
}
fn environment(bytes: &[u8]) -> Result<BTreeMap<String, String>> {
    require(bytes.len() <= 65536, "GRUB environment exceeds its bound")?;
    let mut result = BTreeMap::new();
    for line in std::str::from_utf8(bytes)?.lines() {
        let (key, value) = line.split_once('=').ok_or("malformed GRUB environment")?;
        require(
            !key.is_empty()
                && key.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
                && !value.contains(['\0', '\r'])
                && result.insert(key.into(), value.into()).is_none(),
            "duplicate or unsafe GRUB environment record",
        )?;
    }
    Ok(result)
}
fn fallback(config: &[u8]) -> Result<String> {
    let text = std::str::from_utf8(config)?;
    let marker = "if [ \"${next_entry}\" ] ; then\n";
    require(
        text.matches(marker).count() == 1,
        "GRUB one-shot header is not unique",
    )?;
    let block = text
        .split_once(marker)
        .unwrap()
        .1
        .split_once("\nfi\n")
        .ok_or("GRUB one-shot header is incomplete")?
        .0;
    require(
        block.contains("set next_entry=\n")
            && block.contains("save_env next_entry")
            && block.contains("set boot_once=true"),
        "GRUB cannot consume a one-shot selection",
    )?;
    let branch = block
        .rsplit_once("\nelse\n")
        .ok_or("GRUB fallback branch absent")?
        .1
        .trim();
    let selected = branch
        .strip_prefix("set default=\"")
        .and_then(|v| v.strip_suffix('"'))
        .ok_or("GRUB fallback is not an explicit entry identifier")?;
    require(
        selected.starts_with("gnulinux-") && selected.split('>').all(token),
        "GRUB fallback must identify the retained Ubuntu recovery kernel",
    )?;
    for component in selected.split('>') {
        require(
            text.contains(&format!("'{component}'")),
            "GRUB fallback entry is missing",
        )?;
    }
    Ok(selected.into())
}
fn render(release: &str, uuid: &str, generation: &str) -> Result<(String, Vec<u8>)> {
    require(
        token(release) && valid_uuid(uuid) && files::valid_digest(generation),
        "boot generation, release or filesystem UUID is invalid",
    )?;
    let entry = format!("droidloom-production-{generation}");
    let source = format!(
        "#!/bin/sh\nexec tail -n +3 \"$0\"\n\
        # Managed by the admitted Droidloom first-activation producer.\n\
        menuentry 'Pocket4 Android shared kernel' --id '{entry}' {{\n\
            insmod part_gpt\n\
            insmod ext2\n\
            search --no-floppy --fs-uuid --set=root {uuid}\n\
            linux /boot/vmlinuz-{release} root=UUID={uuid} rootfstype=ext4 rw rootwait console=tty0 loglevel=7 enforcing=1 audit_backlog_limit=32768 lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm audit=1 module.sig_enforce=1 panic=30 init=/usr/lib/droidloom/production/current/droidloom-board-init systemd.unit=graphical.target systemd.log_target=journal-or-kmsg systemd.show_status=1 systemd.log_level=info\n\
            initrd /boot/initrd.img-{release}\n\
        }}\n"
    );
    Ok((entry, source.into_bytes()))
}

fn source_names() -> Result<BTreeSet<PathBuf>> {
    let mut names = BTreeSet::from([
        PathBuf::from("/etc/default/grub"),
        PathBuf::from("/usr/share/grub/grub-mkconfig_lib"),
    ]);
    for directory in ["/etc/grub.d", "/etc/default/grub.d"] {
        for entry in fs::read_dir(directory)? {
            let path = entry?.path();
            if directory.ends_with("default/grub.d") && path.extension().is_none_or(|e| e != "cfg")
            {
                continue;
            }
            require(
                fs::symlink_metadata(&path)?.is_file(),
                "GRUB source contains an unexpected alias or directory",
            )?;
            names.insert(path);
        }
    }
    let custom = PathBuf::from("/boot/grub/custom.cfg");
    match fs::symlink_metadata(&custom) {
        Ok(_) => {
            names.insert(custom);
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e.into()),
    }
    Ok(names)
}
struct Sources {
    names: BTreeSet<PathBuf>,
    files: Vec<HeldFile>,
}
impl Sources {
    fn capture() -> Result<Self> {
        let names = source_names()?;
        require(
            !names.contains(Path::new(SCRIPT)),
            "first activation boot entry already exists",
        )?;
        let files = names
            .iter()
            .map(|p| root_file(p, 4 * MIB))
            .collect::<Result<_>>()?;
        Ok(Self { names, files })
    }
    fn revalidate(&self, installed: bool) -> Result<()> {
        let mut expected = self.names.clone();
        if installed {
            expected.insert(SCRIPT.into());
        }
        require(
            source_names()? == expected,
            "original GRUB source namespace changed",
        )?;
        for file in &self.files {
            file.revalidate()?;
        }
        Ok(())
    }
}

pub(super) struct PreparedBoot {
    area: PathBuf,
    entry: String,
    fallback: String,
    root_uuid: String,
    script: HeldFile,
    kernel: HeldFile,
    initrd: HeldFile,
    original_config: HeldFile,
    original_environment: HeldFile,
    variables: BTreeMap<String, String>,
    sources: Sources,
}
impl PreparedBoot {
    pub(super) fn receipt(&self) -> Value {
        json!({"schema":"droidloom.first-boot-prepared.v1","entry":self.entry,
            "root_filesystem_uuid":self.root_uuid,"retained_fallback":self.fallback,
            "script":self.script.pin(),"kernel":self.kernel.pin(),"initrd":self.initrd.pin(),
            "original_grub_config":self.original_config.pin(),
            "live_boot_modified":false,"production_ready":false})
    }
    fn revalidate(&self) -> Result<()> {
        self.script.revalidate()?;
        self.kernel.revalidate()?;
        self.initrd.revalidate()?;
        self.original_config.revalidate()?;
        self.original_environment.revalidate()?;
        self.sources.revalidate(false)
    }
}

pub(super) fn prepare(
    root: &Path,
    work: &Path,
    generation: &str,
    platform: &PlatformInputs,
) -> Result<PreparedBoot> {
    require(
        unsafe { libc::geteuid() } == 0 && files::valid_digest(generation),
        "boot preparation requires its root installation writer",
    )?;
    let selected = PathBuf::from("/var/lib/droidloom/activation-staging").join(generation);
    require(
        root == selected.join("root") && work.starts_with(selected.join("work")),
        "boot preparation is outside its selected activation stage",
    )?;
    let area = work.join("boot");
    files::private_dir(&area)?;
    let board: Value = serde_json::from_str(BOARD)?;
    let release = board["kernel"]["release"]
        .as_str()
        .ok_or("board kernel release absent")?;
    require(token(release), "board kernel release is invalid")?;
    let kernel = root_file(&root.join(format!("boot/vmlinuz-{release}")), 64 * MIB)?;
    let initrd = root_file(&root.join(format!("boot/initrd.img-{release}")), 256 * MIB)?;
    require(
        kernel.pin().sha256 == platform.kernel.image.sha256
            && kernel.pin().bytes == platform.kernel.image.bytes
            && kernel.pin().sha256 == board["kernel"]["sha256"]
            && initrd.pin().sha256 == platform.initrd.image.sha256
            && initrd.pin().bytes == platform.initrd.image.bytes,
        "boot files differ from the actual admitted platform stage",
    )?;
    let original_config = root_file(Path::new(CONFIG), 16 * MIB)?;
    let fallback = fallback(&original_config.read_all(16 * MIB)?)?;
    let original_environment = root_file(Path::new(ENVIRONMENT), 65536)?;
    let sources = Sources::capture()?;
    let uuid = command(
        &area,
        "root-uuid",
        "/usr/sbin/grub-probe",
        &["--target=fs_uuid", "/"],
    )?;
    let root_uuid = text_line(&uuid)?.to_owned();
    require(valid_uuid(&root_uuid), "root filesystem UUID is invalid")?;
    let boot_uuid = command(
        &area,
        "boot-uuid",
        "/usr/sbin/grub-probe",
        &["--target=fs_uuid", "/boot"],
    )?;
    let fs_type = command(
        &area,
        "boot-fs",
        "/usr/sbin/grub-probe",
        &["--target=fs", "/boot"],
    )?;
    let abstraction = command(
        &area,
        "environment-device",
        "/usr/sbin/grub-probe",
        &["--target=abstraction", ENVIRONMENT],
    )?;
    require(
        text_line(&boot_uuid)? == root_uuid
            && text_line(&fs_type)? == "ext2"
            && (abstraction.is_empty() || abstraction == b"\n")
            && fs::metadata("/")?.dev() == fs::metadata("/boot")?.dev(),
        "one-shot boot requires the actual writable ordinary shared ext4 boot filesystem",
    )?;
    let variables = environment(&command(
        &area,
        "initial-environment",
        "/usr/bin/grub-editenv",
        &[ENVIRONMENT, "list"],
    )?)?;
    for name in [
        "next_entry",
        "prev_saved_entry",
        "initrdfail",
        "prev_entry",
        "env_block",
    ] {
        require(
            variables.get(name).is_none_or(String::is_empty),
            "another pending boot or fallback operation is still selected",
        )?;
    }
    let (entry, bytes) = render(release, &root_uuid, generation)?;
    let pin = files::write_new(&area.join("42_droidloom"), &bytes, 0o755)?;
    let script = root_file(&pin.path, MIB)?;
    // grub-script-check parses GRUB, not the normal two-line shell producer.
    let body = bytes
        .splitn(3, |b| *b == b'\n')
        .nth(2)
        .ok_or("boot script body absent")?;
    let body = files::write_new(&area.join("entry.cfg"), body, 0o400)?;
    command(
        &area,
        "preview-syntax",
        "/usr/bin/grub-script-check",
        &[body.path.to_str().unwrap()],
    )?;
    original_config.copy_new(&area.join("original-grub.cfg"), 0o400)?;
    original_environment.copy_new(&area.join("original-grubenv"), 0o400)?;
    let prepared = PreparedBoot {
        area,
        entry,
        fallback,
        root_uuid,
        script,
        kernel,
        initrd,
        original_config,
        original_environment,
        variables,
        sources,
    };
    prepared.revalidate()?;
    Ok(prepared)
}

pub(super) struct CommittedBoot {
    entry: String,
    fallback: String,
    kernel: HeldFile,
    initrd: HeldFile,
    script: HeldFile,
    config: HeldFile,
    environment: HeldFile,
    sources: Sources,
}
impl CommittedBoot {
    pub(super) fn revalidate(&self) -> Result<()> {
        for held in [
            &self.kernel,
            &self.initrd,
            &self.script,
            &self.config,
            &self.environment,
        ] {
            held.revalidate()?;
        }
        self.sources.revalidate(true)
    }
    pub(super) fn receipt(&self) -> Value {
        json!({"schema":"droidloom.first-boot-committed.v1","entry":self.entry,
            "retained_fallback":self.fallback,"kernel":self.kernel.pin(),"initrd":self.initrd.pin(),
            "script":self.script.pin(),"grub_config":self.config.pin(),
            "grub_environment":self.environment.pin(),"next_boot_selected":true,
            "boot_completed":false,"production_ready":false})
    }
}

pub(super) fn commit(
    prepared: PreparedBoot,
    permit: &InstallationPermit,
    labels: &Labeler,
) -> Result<CommittedBoot> {
    require(
        prepared.entry == format!("droidloom-production-{}", permit.plan()),
        "boot publication crossed the original installation generation",
    )?;
    permit.revalidate()?;
    prepared.revalidate()?;
    let live = |source: &HeldFile| -> Result<HeldFile> {
        let path = PathBuf::from("/boot").join(
            source
                .pin()
                .path
                .file_name()
                .ok_or("boot basename absent")?,
        );
        let file = root_file(&path, 256 * MIB)?;
        require(
            file.pin().bytes == source.pin().bytes && file.pin().sha256 == source.pin().sha256,
            "live boot member differs from the admitted installation readback",
        )?;
        Ok(file)
    };
    let kernel = live(&prepared.kernel)?;
    let initrd = live(&prepared.initrd)?;
    permit.revalidate()?;
    prepared.script.copy_new(Path::new(SCRIPT), 0o755)?;
    files::sync_parent(Path::new(SCRIPT))?;
    labels.apply_file(&files::open_regular(Path::new(SCRIPT))?, Path::new(SCRIPT))?;
    let script = root_file(Path::new(SCRIPT), MIB)?;
    prepared.sources.revalidate(true)?;
    permit.revalidate()?;
    command(
        &prepared.area,
        "normal-mkconfig",
        "/usr/sbin/grub-mkconfig",
        &["-o", CONFIG],
    )?;
    files::sync_parent(Path::new(CONFIG))?;
    command(
        &prepared.area,
        "generated-syntax",
        "/usr/bin/grub-script-check",
        &[CONFIG],
    )?;
    labels.apply_file(&files::open_regular(Path::new(CONFIG))?, Path::new(CONFIG))?;
    let config = root_file(Path::new(CONFIG), 16 * MIB)?;
    let generated = config.read_all(16 * MIB)?;
    require(
        fallback(&generated)? == prepared.fallback,
        "normal boot generation changed the retained recovery selection",
    )?;
    let source = prepared.script.read_all(MIB)?;
    let body = source
        .splitn(3, |b| *b == b'\n')
        .nth(2)
        .ok_or("boot script body absent")?;
    let generated_text = std::str::from_utf8(&generated)?;
    require(
        generated_text.matches(std::str::from_utf8(body)?).count() == 1
            && generated_text
                .matches(&format!("--id '{}'", prepared.entry))
                .count()
                == 1,
        "normal GRUB configuration omitted or duplicated the exact selected entry",
    )?;
    prepared.sources.revalidate(true)?;
    kernel.revalidate()?;
    initrd.revalidate()?;
    script.revalidate()?;
    config.revalidate()?;
    prepared.original_environment.revalidate()?;
    let before = environment(&command(
        &prepared.area,
        "environment-before-arm",
        "/usr/bin/grub-editenv",
        &[ENVIRONMENT, "list"],
    )?)?;
    require(
        before == prepared.variables,
        "GRUB environment changed before one-shot selection",
    )?;
    permit.revalidate()?;
    command(
        &prepared.area,
        "normal-reboot-selection",
        "/usr/sbin/grub-reboot",
        &[prepared.entry.as_str()],
    )?;
    files::sync_parent(Path::new(ENVIRONMENT))?;
    let after = environment(&command(
        &prepared.area,
        "environment-armed",
        "/usr/bin/grub-editenv",
        &[ENVIRONMENT, "list"],
    )?)?;
    let mut expected = before;
    expected.insert("next_entry".into(), prepared.entry.clone());
    require(after == expected, "normal GRUB one-shot readback differs")?;
    labels.apply_file(
        &files::open_regular(Path::new(ENVIRONMENT))?,
        Path::new(ENVIRONMENT),
    )?;
    let environment = root_file(Path::new(ENVIRONMENT), 65536)?;
    let committed = CommittedBoot {
        entry: prepared.entry,
        fallback: prepared.fallback,
        kernel,
        initrd,
        script,
        config,
        environment,
        sources: prepared.sources,
    };
    committed.revalidate()?;
    permit.revalidate()?;
    Ok(committed)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_entry_has_both_macs_and_cannot_inject_grub_or_kernel_arguments() -> Result<()> {
        let generation = "a".repeat(64);
        let uuid = "01c27223-3933-481e-9836-7bd0ef1be8c9";
        let (_, bytes) = render("6.18.64-p4ctx6181-fusectl-aafs-peer-r1", uuid, &generation)?;
        let text = std::str::from_utf8(&bytes)?;
        assert!(text.contains("selinux,apparmor"));
        assert!(text.contains("enforcing=1"));
        assert!(text.contains("module.sig_enforce=1"));
        assert!(text.contains("init=/usr/lib/droidloom/production/current/droidloom-board-init"));
        assert!(text.contains("systemd.unit=graphical.target"));
        for bad in ["x rw enforcing=0", "x'; reboot; #", "../other", ""] {
            assert!(render(bad, uuid, &generation).is_err());
        }
        assert!(render("6.18", uuid, "../generation").is_err());
        assert!(render("6.18", "$(command)", &generation).is_err());
        Ok(())
    }
    #[test]
    fn one_shot_header_must_retain_an_existing_explicit_fallback() -> Result<()> {
        let config = b"if [ \"${next_entry}\" ] ; then\n   set default=\"${next_entry}\"\n   set next_entry=\n   save_env next_entry\n   set boot_once=true\nelse\n   set default=\"gnulinux-advanced-id>gnulinux-old-id\"\nfi\nsubmenu 'Linux' --id 'gnulinux-advanced-id' {\nmenuentry 'Old' --id 'gnulinux-old-id' {}\n}\n";
        assert_eq!(fallback(config)?, "gnulinux-advanced-id>gnulinux-old-id");
        let text = std::str::from_utf8(config)?;
        for (from, to) in [
            ("save_env next_entry", "# omitted"),
            ("gnulinux-advanced-id>gnulinux-old-id", "0"),
            ("--id 'gnulinux-old-id'", "--id 'missing'"),
        ] {
            assert!(fallback(text.replace(from, to).as_bytes()).is_err());
        }
        assert!(fallback(format!("{text}{text}").as_bytes()).is_err());
        Ok(())
    }
    #[test]
    fn environment_readback_cannot_hide_duplicate_or_additional_records() -> Result<()> {
        assert_eq!(environment(b"next_entry=\n")?["next_entry"], "");
        for bad in [
            &b"next_entry=a\nnext_entry=b\n"[..],
            &b"broken\n"[..],
            &b"bad key=x\n"[..],
            &b"next_entry=x\0\n"[..],
        ] {
            assert!(environment(bad).is_err());
        }
        assert!(text_line(b"one\ntwo\n").is_err());
        assert!(text_line(b"one").is_err());
        Ok(())
    }
}
