use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Read, Write},
    os::unix::{net::UnixStream, process::ExitStatusExt},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunPlan {
    pub schema: String,
    pub prepared: FilePin,
    pub run_name: String,
    pub cpus: usize,
    pub memory_mib: u64,
    pub duration_seconds: u64,
    pub network: bool,
    pub ssh_port: Option<u16>,
}

fn qmp(path: &Path, command: &str) -> Result<Value> {
    ensure(
        ["system_powerdown", "query-status"].contains(&command),
        "unsupported monitor operation",
    )?;
    let stream = UnixStream::connect(path)?;
    stream.set_read_timeout(Some(Duration::from_secs(3)))?;
    stream.set_write_timeout(Some(Duration::from_secs(3)))?;
    let mut reader = BufReader::new(stream);
    let deadline = Instant::now() + Duration::from_secs(6);
    let greeting = qmp_line(&mut reader, deadline)?;
    ensure(
        greeting.get("QMP").is_some(),
        "invalid private QMP greeting",
    )?;
    for (index, op) in ["qmp_capabilities", command].iter().enumerate() {
        let request = json!({"execute":op,"id":index});
        reader
            .get_mut()
            .write_all(serde_json::to_string(&request)?.as_bytes())?;
        reader.get_mut().write_all(b"\n")?;
        let mut answered = false;
        for _ in 0..32 {
            let value = qmp_line(&mut reader, deadline)?;
            if value["id"] == index {
                ensure(
                    value.get("error").is_none(),
                    "QMP operation returned an error",
                )?;
                if index == 1 {
                    return Ok(value);
                }
                answered = true;
                break;
            }
        }
        ensure(answered, "QMP exceeded its bounded event count")?;
    }
    Err("QMP result absent".into())
}

fn qmp_line(reader: &mut BufReader<UnixStream>, deadline: Instant) -> Result<Value> {
    let remaining = deadline
        .checked_duration_since(Instant::now())
        .ok_or("QMP exceeded its complete operation deadline")?;
    reader
        .get_mut()
        .set_read_timeout(Some(remaining.min(Duration::from_secs(3))))?;
    let mut line = Vec::new();
    Read::take(&mut *reader, 65537).read_until(b'\n', &mut line)?;
    ensure(
        line.len() <= 65536 && line.last() == Some(&b'\n'),
        "QMP line is absent, incomplete or exceeds 64 KiB",
    )?;
    Ok(serde_json::from_slice(&line)?)
}

fn known_host(root: &Path, run: &Path, port: u16) -> Result<FilePin> {
    let source = boot_files::pin_file(&root.join("etc/ssh/ssh_host_ed25519_key.pub"))?;
    let bytes = boot_files::read_pin(&source, 4096)?;
    let public = std::str::from_utf8(&bytes)?;
    let fields: Vec<_> = public.split_whitespace().collect();
    ensure(
        fields.len() == 3
            && fields[0] == "ssh-ed25519"
            && fields[1]
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"+/=".contains(&b)),
        "fresh fixture host key is not one Ed25519 public key",
    )?;
    let path = run.join("known_hosts");
    boot_files::write_new(
        &path,
        format!("[127.0.0.1]:{port} {} {}\n", fields[0], fields[1]).as_bytes(),
        0o600,
    )?;
    boot_files::pin_file(&path)
}

fn cpu_budget_allowed(cpus: usize, available: usize) -> bool {
    // The production guest has the same fixed 24-CPU geometry as the board.
    // Qualification still leaves at least two actual host CPUs available.
    (2..=24).contains(&cpus)
        && cpus.checked_add(2).is_some_and(|required| required <= available)
}

pub fn run(config: &Path, expected: &str) -> Result<()> {
    let plan: RunPlan = fs::read_json(&fs::absolute_string(config)?, expected)?;
    ensure(
        plan.schema == "droidloom.full-ubuntu-run-plan.v1",
        "unsupported run plan",
    )?;
    ensure(
        !plan.run_name.is_empty()
            && plan.run_name.len() <= 64
            && plan
                .run_name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b)),
        "invalid private run name",
    )?;
    let available = std::thread::available_parallelism()?.get();
    ensure(
        cpu_budget_allowed(plan.cpus, available),
        "VM must preserve at least two logical CPUs",
    )?;
    ensure(
        (4096..=12288).contains(&plan.memory_mib) && (60..=3600).contains(&plan.duration_seconds),
        "VM memory or duration is outside the explicit bounded range",
    )?;
    ensure(
        plan.ssh_port
            .is_none_or(|p| plan.network && (50000..=59999).contains(&p)),
        "guest SSH forwarding must be explicit, high-port and loopback only",
    )?;
    let prepared: Value =
        serde_json::from_slice(&boot_files::read_pin(&plan.prepared, 8 * 1024 * 1024)?)?;
    ensure(
        prepared["schema"] == "droidloom.full-ubuntu-boot-prepared.v1"
            && prepared["guest_qualified"] == false
            && prepared["production_ready"] == false,
        "not an admitted unbooted image",
    )?;
    let work = PathBuf::from(prepared["work_directory"].as_str().ok_or("work missing")?);
    let boot = PathBuf::from(
        prepared["boot_directory"]
            .as_str()
            .ok_or("boot directory missing")?,
    );
    ensure(
        work.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && boot == work.join("boot"),
        "prepared image is outside the protected qualification root",
    )?;
    let owner = fs::Tree::open(&fs::absolute_string(&work)?, 0)?;
    ensure(
        fs::stat(&owner.root)?.mode & 0o777 == 0o700,
        "qualification work is no longer private",
    )?;
    let kernel: FilePin = serde_json::from_value(prepared["kernel"].clone())?;
    let initrd: FilePin = serde_json::from_value(prepared["initrd"].clone())?;
    let source: FilePin = serde_json::from_value(prepared["root_image"].clone())?;
    ensure(
        [&kernel.path, &initrd.path, &source.path]
            .iter()
            .all(|p| p.parent() == Some(boot.as_path())),
        "boot input paths differ from prepared private files",
    )?;
    let _kernel_fd = boot_files::checked_file(&kernel)?;
    let _initrd_fd = boot_files::checked_file(&initrd)?;
    let run = boot.join(&plan.run_name);
    boot_files::private_dir(&run)?;
    fs::write_json(
        &fs::absolute_string(&run.join("RUN-INPUTS.json"))?,
        &plan,
        0,
    )?;
    let (source_guard, source_identity) = boot_files::open_pin(&source)?;
    let disk = run.join("working.ext4");
    boot_files::copy_pin(&source, &disk, 0o600)?;
    let known = if let Some(port) = plan.ssh_port {
        Some(known_host(&work.join("root"), &run, port)?)
    } else {
        None
    };
    let serial = run.join("serial.log");
    let output = boot_files::new_file(&serial, 0o600)?;
    let monitor = run.join("qmp.sock");
    ensure(
        monitor.as_os_str().len() < 104,
        "private QMP pathname exceeds Unix socket limit",
    )?;
    let unit = if prepared["calibration_requested"] == true {
        "droidloom-calibration-qualification.target"
    } else {
        "graphical.target"
    };
    let uuid = prepared["root_filesystem_uuid"]
        .as_str()
        .ok_or("root UUID missing")?;
    ensure(
        uuid.len() == 36 && uuid.bytes().all(|b| b.is_ascii_hexdigit() || b == b'-'),
        "invalid root UUID",
    )?;
    let cmdline = format!(
        "console=ttyS0,115200 root=UUID={uuid} rootfstype=ext4 rw rootwait loglevel=7 enforcing=1 audit_backlog_limit=32768 lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm audit=1 init=/usr/lib/droidloom/production/current/droidloom-board-init systemd.unit={unit} systemd.log_target=journal-or-kmsg systemd.show_status=1 systemd.log_level=info"
    );
    let mut args = vec![
        "-accel".into(),
        "kvm".into(),
        "-machine".into(),
        "q35".into(),
        "-cpu".into(),
        "host".into(),
        "-m".into(),
        plan.memory_mib.to_string(),
        "-smp".into(),
        plan.cpus.to_string(),
        "-display".into(),
        "none".into(),
        "-vga".into(),
        "virtio".into(),
        "-serial".into(),
        "stdio".into(),
        "-no-reboot".into(),
        "-monitor".into(),
        "none".into(),
        "-qmp".into(),
        format!("unix:{},server=on,wait=off", monitor.display()),
        "-kernel".into(),
        kernel.path.to_string_lossy().into(),
        "-initrd".into(),
        initrd.path.to_string_lossy().into(),
        "-append".into(),
        cmdline,
        "-drive".into(),
        format!(
            "if=none,id=guest,format=raw,cache=writethrough,file={}",
            disk.display()
        ),
        "-device".into(),
        "virtio-blk-pci,drive=guest".into(),
        "-device".into(),
        "virtio-keyboard-pci".into(),
        "-device".into(),
        "virtio-mouse-pci".into(),
        "-device".into(),
        "intel-hda".into(),
        "-device".into(),
        "hda-duplex".into(),
        "-run-with".into(),
        "user=nobody".into(),
        "-sandbox".into(),
        "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny".into(),
    ];
    let nic = if plan.network {
        match plan.ssh_port {
            Some(port) => format!("user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:{port}-:22"),
            None => "user,model=virtio-net-pci".into(),
        }
    } else {
        "none".into()
    };
    args.extend(["-nic".into(), nic]);
    let qemu = boot_files::pin_file(Path::new("/usr/bin/qemu-system-x86_64"))?;
    let mut command = Command::new(&qemu.path);
    command
        .args(&args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C.UTF-8")
        .stdin(Stdio::null())
        .stdout(Stdio::from(output.try_clone()?))
        .stderr(Stdio::from(output));
    let mut child = crate::boot_child::OwnedChild::spawn(&mut command)?;
    let started = Instant::now();
    let attempt = (|| -> Result<(std::process::ExitStatus, bool)> {
        fs::write_json(
            &fs::absolute_string(&run.join("RUNNING.json"))?,
            &json!({
        "pid":child.id(),"program":qemu,"args":args,"known_hosts":known,
        "fresh_client_key":work.join("fixture-ssh-client-key"),
        "private_qmp":monitor,"working_disk":disk,"original_userdata_opened":false,
        "preserved_source_image":source,"source_identity":source_identity,
        "guest_qualified":false,"production_ready":false}),
            0,
        )?;
        println!(
            "{}",
            json!({"running_pid":child.id(),"run_directory":run,"private_qmp":monitor,
        "ssh_port":plan.ssh_port,"guest_qualified":false})
        );
        std::io::stdout().flush()?;
        let mut power_attempt = None;
        let mut forced = false;
        let status = loop {
            if let Some(s) = child.try_wait()? {
                break s;
            }
            let elapsed = started.elapsed().as_secs();
            if elapsed >= plan.duration_seconds && power_attempt.is_none() {
                let result = qmp(&monitor, "system_powerdown")
                    .map(|v| json!({"result":v}))
                    .unwrap_or_else(|e| json!({"error":e.to_string()}));
                fs::write_json(
                    &fs::absolute_string(&run.join("POWER-DOWN.json"))?,
                    &result,
                    0,
                )?;
                power_attempt = Some(elapsed);
            }
            if power_attempt.is_some_and(|t| elapsed >= t + 45)
                || std::fs::metadata(&serial)?.len() > 512 * 1024 * 1024
            {
                forced = true;
                break child.stop_and_reap()?;
            }
            std::thread::sleep(Duration::from_millis(250));
        };
        Ok((status, forced))
    })();
    let (status, forced) = match attempt {
        Ok(value) => value,
        Err(error) => {
            // Stop before attempting any further evidence I/O. Even if that
            // I/O also fails, OwnedChild's Drop retries unreaped cleanup.
            let stopped = child.stop_and_reap();
            let source_preserved = fs::stat(&source_guard).is_ok_and(|id| id == source_identity)
                && boot_files::open_pin(&source).is_ok_and(|(_, id)| id == source_identity);
            let failure = json!({"schema":"droidloom.full-ubuntu-run-failed.v1",
                "prepared":plan.prepared,"error":error.to_string(),"qemu":qemu,
                "owned_pid":child.id(),"child_reaped":stopped.is_ok(),
                "exit_code":stopped.as_ref().ok().and_then(|s|s.code()),
                "signal":stopped.as_ref().ok().and_then(|s|s.signal()),
                "stop_error":stopped.as_ref().err().map(ToString::to_string),
                "preserved_source_image":source,"source_identity":source_identity,
                "source_image_preserved":source_preserved,"working_disk":disk,
                "serial_path":serial,"guest_qualified":false,"production_ready":false});
            let saved = fs::write_json(
                &fs::absolute_string(&run.join("RUN-FAILED.json"))?,
                &failure,
                0,
            );
            return Err(format!(
                "guest runner failed: {error}; owned-child cleanup: {}; failure receipt: {}",
                if stopped.is_ok() {
                    "reaped"
                } else {
                    "failed; Drop will retry"
                },
                saved.map_or_else(|e| e.to_string(), |sha| sha)
            )
            .into());
        }
    };
    ensure(
        fs::stat(&source_guard)? == source_identity
            && boot_files::open_pin(&source)?.1 == source_identity,
        "prepared source image changed while isolated guest ran",
    )?;
    let receipt = json!({"schema":"droidloom.full-ubuntu-run-ended.v1","prepared":plan.prepared,
        "run_directory":run,"qemu":qemu,"exit_code":status.code(),"forced_stop":forced,
        "elapsed_seconds":started.elapsed().as_secs(),"serial":boot_files::pin_file(&serial)?,
        "working_disk":boot_files::pin_file(&disk)?,"source_image_preserved":true,
        "preserved_source_image":source,"source_identity":source_identity,
        "signal":status.signal(),
        "guest_qualified":false,"production_ready":false,
        "next_required":"Inspect the original persistent journal and complete the independent runtime and application gates."});
    let receipt_path = run.join("RUN-ENDED.json");
    let sha = fs::write_json(&fs::absolute_string(&receipt_path)?, &receipt, 0)?;
    println!(
        "{}",
        json!({"receipt":receipt_path,"sha256":sha,"guest_qualified":false,"production_ready":false})
    );
    ensure(
        status.success() && !forced,
        "guest did not terminate normally; exact journal/serial remains for diagnosis",
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cpu_budget_supports_the_production_geometry_and_preserves_host_reservation() {
        for (cpus, available, allowed) in [
            (2, 4, true),
            (4, 6, true),
            (16, 18, true),
            (24, 26, true),
            (24, 25, false),
            (25, 64, false),
            (1, 64, false),
            (usize::MAX, usize::MAX, false),
        ] {
            assert_eq!(cpu_budget_allowed(cpus, available), allowed);
        }
    }
    #[test]
    fn private_qmp_line_bounds_and_deadline_are_enforced() -> Result<()> {
        let (input, mut output) = UnixStream::pair()?;
        output.write_all(b"{\"QMP\":{}}\n")?;
        let mut reader = BufReader::new(input);
        assert!(
            qmp_line(&mut reader, Instant::now() + Duration::from_secs(1))?
                .get("QMP")
                .is_some()
        );
        assert!(qmp_line(&mut reader, Instant::now() - Duration::from_millis(1)).is_err());
        output.write_all(&vec![b'x'; 65537])?;
        assert!(qmp_line(&mut reader, Instant::now() + Duration::from_secs(1)).is_err());
        Ok(())
    }
}
