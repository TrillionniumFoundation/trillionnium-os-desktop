//! Explicit, diskless qualification of the fixed per-call peer-LSM interface.
//! This test-only entry is never selected by the ordinary fixture CLI.
use super::{admit_paused_qemu, cpu_budget_allowed, qmp};
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::{Read, Write},
    os::unix::{net::UnixStream, process::ExitStatusExt},
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

const RELEASE: &str = "6.18.64-p4ctx6181-fusectl-aafs-peer-r1";
const KERNEL_SHA: &str = "19052ac77e40a86147f6bc186739763628916033f7c36f3448b4a872914090df";
const INITRD_SHA: &str = "147af975f9e68fc79a7fe66e43229728c15abee52d2ea5092c7474a37e9fd771";
const MATERIALS_SHA: &str = "6b2cc63511d6890965b31f1b32cf7d453af313082d3ae7e5ef00d0bfd2f4aedd";
const COMMAND_LINE: &str = "console=ttyS0 rdinit=/peer-runtime loglevel=5 panic=-1 selinux=1 enforcing=1 apparmor=1 lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm p4_peer_mechanism=1";
const SERIAL_LIMIT: usize = 4 * 1024 * 1024;
const MARKER: &str = "P4_PEER_RUNTIME_RESULT ";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    kernel: FilePin,
    initrd: FilePin,
    materials: FilePin,
    run_name: String,
    cpus: usize,
    memory_mib: u64,
    duration_seconds: u64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct GuestResult {
    schema: String,
    kernel: String,
    threads: u64,
    iterations_per_thread: u64,
    actual_concurrent_calls: u64,
    error_and_denial_checks: u64,
    legacy_provider_unchanged: bool,
    actual_public_library_calls: bool,
    outer_apparmor_denial_preserved: bool,
    production_policy_loaded: bool,
    production_qualified: bool,
    exit_code: i32,
}

fn successful_guest_result(serial: &[u8]) -> Result<GuestResult> {
    ensure(serial.len() <= SERIAL_LIMIT, "peer serial exceeds 4 MiB")?;
    let text = std::str::from_utf8(serial)?;
    ensure(
        !text.contains("P4_PEER_RUNTIME_FAILED") && text.matches(MARKER).count() == 1,
        "guest failed or did not emit exactly one peer result",
    )?;
    let line = text
        .lines()
        .find_map(|line| line.strip_prefix(MARKER))
        .ok_or("peer result was not a complete standalone line")?;
    let result: GuestResult = serde_json::from_str(line.trim_end_matches('\r'))?;
    ensure(
        result.schema == "p4-peer-lsm-real-kernel-mechanism-v1"
            && result.kernel == RELEASE
            && result.threads == 8
            && result.iterations_per_thread == 5000
            && result.actual_concurrent_calls == 50000
            && result.error_and_denial_checks == 23
            && result.legacy_provider_unchanged
            && result.actual_public_library_calls
            && result.outer_apparmor_denial_preserved
            && !result.production_policy_loaded
            && !result.production_qualified
            && result.exit_code == 0,
        "peer result does not prove the fixed mechanism contract",
    )?;
    Ok(result)
}

fn protected_pin(pin: &FilePin) -> Result<File> {
    ensure(
        pin.path.starts_with("/var/lib/droidloom-qualification"),
        "peer input is outside the protected qualification directory",
    )?;
    let file = boot_files::checked_file(pin)?;
    let identity = fs::stat(&file)?;
    ensure(
        identity.uid == 0
            && identity.gid == 0
            && identity.nlink == 1
            && identity.mode & 0o6022 == 0,
        "peer input is not a protected ordinary root file",
    )?;
    Ok(file)
}

fn validate_plan(plan: &Plan) -> Result<Value> {
    ensure(
        plan.schema == "droidloom.peer-lsm-mechanism-run-plan.v1"
            && !plan.run_name.is_empty()
            && plan.run_name.len() <= 32
            && plan
                .run_name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b)),
        "peer plan or private run name differs",
    )?;
    ensure(
        (2..=4).contains(&plan.cpus)
            && cpu_budget_allowed(plan.cpus, std::thread::available_parallelism()?.get())
            && plan.memory_mib == 2048
            && (1..=120).contains(&plan.duration_seconds),
        "peer VM exceeds its CPU, host reservation, memory or duration bound",
    )?;
    ensure(
        plan.kernel.bytes == 16855552
            && plan.kernel.sha256 == KERNEL_SHA
            && plan.initrd.bytes == 1519966
            && plan.initrd.sha256 == INITRD_SHA
            && plan.materials.bytes == 7535
            && plan.materials.sha256 == MATERIALS_SHA,
        "peer VM inputs differ from this fixed complete kernel and test batch",
    )?;
    for pin in [&plan.kernel, &plan.initrd, &plan.materials] {
        protected_pin(pin)?;
    }
    let materials: Value =
        serde_json::from_slice(&boot_files::read_pin(&plan.materials, 16 * 1024)?)?;
    ensure(
        materials["schema"] == "p4-peer-lsm-kernel-mechanism-material-v1"
            && materials["required_kernel_release"] == RELEASE
            && materials["entry_count"] == 19
            && materials["entries"]
                .as_array()
                .is_some_and(|v| v.len() == 19)
            && materials["entries"].as_array().is_some_and(|entries| {
                entries.iter().any(|entry| {
                    entry["path"] == "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
                        && entry["mode"] == 0o100755
                        && entry["bytes"] == 254864
                        && entry["sha256"]
                            == "c0b20d6e1ced12abfe0b1ef2b5b68017950beaaea3df69eb6949d73e0ecf7b40"
                })
            })
            && materials["initrd"]["sha256"] == INITRD_SHA
            && materials["initrd"]["bytes"] == plan.initrd.bytes
            && materials["command_line"] == COMMAND_LINE
            && materials["guest_started"] == false
            && materials["production_policy_loaded"] == false
            && materials["production_qualified"] == false,
        "fixed peer material receipt differs",
    )?;
    Ok(materials)
}

/// A socket stream bounds the producer and prevents an unbounded serial file.
/// The sink never exceeds SERIAL_LIMIT, including the overflow failure case.
fn drain_serial(reader: &mut UnixStream, output: &mut File, bytes: &mut Vec<u8>) -> Result<bool> {
    let mut block = [0u8; 16384];
    for _ in 0..512 {
        let remaining = SERIAL_LIMIT - bytes.len();
        let count = block.len().min(remaining.saturating_add(1));
        match reader.read(&mut block[..count]) {
            Ok(0) => return Ok(true),
            Ok(n) => {
                let accepted = n.min(remaining);
                output.write_all(&block[..accepted])?;
                bytes.extend_from_slice(&block[..accepted]);
                ensure(n <= remaining, "peer serial exceeded its 4 MiB bound")?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => return Ok(false),
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Err("peer serial exceeded its bounded drain work".into())
}

fn execute(plan: &Plan, run: &Path, receipt: &mut Value) -> Result<()> {
    let dummy = run.join("unattached-private-dummy");
    let file = boot_files::new_file(&dummy, 0o600)?;
    file.set_len(2 * 1024 * 1024)?;
    file.sync_all()?;
    drop(file);
    let monitor = run.join("qmp.sock");
    ensure(monitor.as_os_str().len() < 104, "peer QMP path is too long")?;
    let serial_path = run.join("serial.log");
    let mut serial_file = boot_files::new_file(&serial_path, 0o600)?;
    let (mut reader, writer) = UnixStream::pair()?;
    reader.set_nonblocking(true)?;
    let writer: File = std::os::fd::OwnedFd::from(writer).into();
    let launch =
        crate::boot_qemu::Launch::prepare(run, &dummy, &plan.kernel, &plan.initrd, &monitor)?;
    let mut args = launch.fixed_args();
    args.extend([
        "-machine".into(),
        "q35".into(),
        "-cpu".into(),
        "host".into(),
        "-smp".into(),
        plan.cpus.to_string(),
        "-m".into(),
        plan.memory_mib.to_string(),
        "-nodefaults".into(),
        "-S".into(),
        "-display".into(),
        "none".into(),
        "-serial".into(),
        "stdio".into(),
        "-monitor".into(),
        "none".into(),
        "-nic".into(),
        "none".into(),
        "-no-reboot".into(),
        "-kernel".into(),
        launch.kernel_path(),
        "-initrd".into(),
        launch.initrd_path(),
        "-append".into(),
        COMMAND_LINE.into(),
    ]);
    // fdset 2 exists only because the shared launcher holds its fixed eight
    // descriptors. No -drive, -blockdev or guest storage device consumes it.
    receipt["launcher"] = launch.receipt.clone();
    receipt["arguments"] = json!(args);
    receipt["guest_disk_attached"] = json!(false);
    receipt["network_enabled"] = json!(false);
    receipt["serial_limit_bytes"] = json!(SERIAL_LIMIT);
    let start = Instant::now();
    let deadline = start + Duration::from_secs(plan.duration_seconds);
    let mut child = launch.spawn(&args, &writer)?;
    drop(writer);
    receipt["qemu_pid"] = json!(child.id());
    let mut serial = Vec::new();
    let outcome = (|| -> Result<()> {
        receipt["admission"] = admit_paused_qemu(&mut child, &launch, &monitor)?;
        let kvm = qmp(&monitor, "query-kvm")?;
        ensure(
            kvm["return"]["enabled"] == true,
            "peer VM did not use actual KVM",
        )?;
        receipt["kvm"] = kvm;
        let cpus = qmp(&monitor, "query-cpus-fast")?;
        ensure(
            cpus["return"]
                .as_array()
                .is_some_and(|v| v.len() == plan.cpus),
            "peer VM CPU count differs",
        )?;
        receipt["cpus"] = cpus;
        ensure(
            Instant::now() < deadline,
            "peer VM expired before guest admission",
        )?;
        qmp(&monitor, "cont")?;
        receipt["guest_cpus_started"] = json!(true);
        loop {
            drain_serial(&mut reader, &mut serial_file, &mut serial)?;
            if let Some(status) = child.try_wait()? {
                receipt["exit_code"] = json!(status.code());
                receipt["signal"] = json!(status.signal());
                ensure(status.success(), "peer QEMU did not exit normally")?;
                ensure(
                    drain_serial(&mut reader, &mut serial_file, &mut serial)?,
                    "retired peer VM still has an open serial writer",
                )?;
                break;
            }
            ensure(
                Instant::now() < deadline,
                "peer VM exceeded its complete time bound",
            )?;
            std::thread::sleep(Duration::from_millis(20));
        }
        let result = successful_guest_result(&serial)?;
        receipt["guest_result"] = serde_json::to_value(result)?;
        Ok(())
    })();
    // Retire the original owned child on every error, before reading evidence.
    let forced = child.try_wait()?.is_none();
    let exit = child.stop_and_reap()?;
    receipt["forced_termination"] = json!(forced);
    receipt["exit_code"] = json!(exit.code());
    receipt["signal"] = json!(exit.signal());
    receipt["elapsed_seconds"] = json!(start.elapsed().as_secs_f64());
    let final_drain = drain_serial(&mut reader, &mut serial_file, &mut serial);
    serial_file.sync_all()?;
    receipt["serial"] = serde_json::to_value(boot_files::pin_file(&serial_path)?)?;
    receipt["serial_bytes"] = json!(serial.len());
    outcome?;
    ensure(
        !forced && exit.success(),
        "peer VM was forced or failed to retire",
    )?;
    ensure(
        final_drain?,
        "peer serial writer survived process retirement",
    )?;
    for pin in [&plan.kernel, &plan.initrd, &plan.materials] {
        protected_pin(pin)?;
    }
    receipt["inputs_revalidated_after_retirement"] = json!(true);
    Ok(())
}

#[test]
#[ignore = "requires explicit pinned root/KVM plan; boots only the fixed diskless peer mechanism"]
fn actual_peer_lsm_kernel_mechanism() -> Result<()> {
    ensure(
        rustix::process::geteuid().as_raw() == 0,
        "explicit root peer run required",
    )?;
    let path = PathBuf::from(std::env::var("DROIDLOOM_PEER_MECHANISM_PLAN")?);
    let expected = std::env::var("DROIDLOOM_PEER_MECHANISM_PLAN_SHA256")?;
    ensure(fs::valid_digest(&expected), "peer plan digest is invalid")?;
    let plan_pin = boot_files::pin_file(&path)?;
    ensure(
        plan_pin.bytes <= 64 * 1024 && plan_pin.sha256 == expected,
        "peer plan differs from explicit bounded digest",
    )?;
    protected_pin(&plan_pin)?;
    let plan: Plan = serde_json::from_slice(&boot_files::read_pin(&plan_pin, 64 * 1024)?)?;
    let materials = validate_plan(&plan)?;
    let run =
        Path::new("/var/lib/droidloom-qualification").join(format!("r127-peer-{}", plan.run_name));
    fs::Tree::create(&fs::absolute_string(&run)?, 0)?;
    let mut receipt = json!({
        "schema":"droidloom.peer-lsm-mechanism-run-result.v1",
        "plan":plan_pin,"inputs":plan,"materials":materials,
        "run_directory":run,"guest_cpus_started":false,
        "production_policy_loaded":false,"production_qualified":false,
        "production_ready":false
    });
    fs::write_json(
        &fs::absolute_string(&run.join("RUN-STARTED.json"))?,
        &receipt,
        0,
    )?;
    let outcome =
        execute(&plan, &run, &mut receipt).and_then(|()| protected_pin(&plan_pin).map(|_| ()));
    receipt["passed"] = json!(outcome.is_ok());
    receipt["error"] = json!(outcome.as_ref().err().map(ToString::to_string));
    let result = run.join("RESULT.json");
    let digest = fs::write_json(&fs::absolute_string(&result)?, &receipt, 0)?;
    println!(
        "{}",
        json!({"receipt":result,"sha256":digest,"passed":outcome.is_ok()})
    );
    outcome
}

#[test]
fn peer_result_requires_complete_success_even_when_guest_poweroff_exits_zero() -> Result<()> {
    let value = json!({
        "schema":"p4-peer-lsm-real-kernel-mechanism-v1","kernel":RELEASE,
        "threads":8,"iterations_per_thread":5000,"actual_concurrent_calls":50000,
        "error_and_denial_checks":23,"legacy_provider_unchanged":true,
        "actual_public_library_calls":true,"outer_apparmor_denial_preserved":true,
        "production_policy_loaded":false,"production_qualified":false,"exit_code":0
    });
    let line = format!("{MARKER}{value}\r\n");
    successful_guest_result(line.as_bytes())?;
    for invalid in [
        String::new(),
        format!("{line}{line}"),
        format!("P4_PEER_RUNTIME_FAILED bad assertion errno=13\n{line}"),
        line.replace(
            "\"actual_concurrent_calls\":50000",
            "\"actual_concurrent_calls\":49999",
        ),
        line.replace(
            "\"error_and_denial_checks\":23",
            "\"error_and_denial_checks\":22",
        ),
        line.replace(
            "\"outer_apparmor_denial_preserved\":true",
            "\"outer_apparmor_denial_preserved\":false",
        ),
        line.replace(
            "\"production_qualified\":false",
            "\"production_qualified\":true",
        ),
        line.replace(RELEASE, "unadmitted-kernel"),
        line.replace("\"exit_code\":0", "\"exit_code\":1"),
    ] {
        ensure(
            successful_guest_result(invalid.as_bytes()).is_err(),
            "invalid result admitted",
        )?;
    }
    Ok(())
}

#[test]
fn peer_serial_overflow_keeps_the_evidence_file_within_its_bound() -> Result<()> {
    let (mut reader, mut writer) = UnixStream::pair()?;
    reader.set_nonblocking(true)?;
    writer.write_all(b"12345")?;
    drop(writer);
    let mut file = tempfile::tempfile()?;
    let mut captured = vec![0u8; SERIAL_LIMIT - 4];
    ensure(
        drain_serial(&mut reader, &mut file, &mut captured).is_err(),
        "serial overflow was accepted",
    )?;
    ensure(
        captured.len() == SERIAL_LIMIT
            && captured[SERIAL_LIMIT - 4..] == *b"1234"
            && file.metadata()?.len() == 4,
        "serial overflow wrote beyond the evidence bound",
    )
}
