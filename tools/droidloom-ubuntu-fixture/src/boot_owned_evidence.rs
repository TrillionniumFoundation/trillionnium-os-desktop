//! Revalidate an actually ended, normally prepared full guest.
//!
//! This is evidence for the first cold-deployment phase, not physical activation
//! or application acceptance. In particular calibration is permitted before any
//! application can run. All runtime observations are recollected from the ended
//! independent disk by the existing bounded collector, never copied from a
//! caller's successful-looking summary.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
    model::Identity,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::{Read, Seek, SeekFrom},
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
};

const BASE: &str = "/var/lib/droidloom-qualification";
const MAC_FILES: [&str; 5] = [
    "contract.json",
    "manager-label.json",
    "policy.bin",
    "policy-export.bin",
    "derivation.json",
];

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum BootPhase {
    MacCalibration,
    AndroidRuntime,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    boot_plan: FilePin,
    collect_plan: FilePin,
    collected: FilePin,
    expected_boot_phase: BootPhase,
    verification_name: String,
}

#[derive(Default)]
struct Custody {
    files: BTreeMap<PathBuf, (FilePin, Identity, File)>,
}

impl Custody {
    fn admit(&mut self, pin: &FilePin) -> Result<()> {
        if let Some((previous, _, _)) = self.files.get(&pin.path) {
            return ensure(
                same_pin(previous, pin),
                "two evidence pins name different bytes at one path",
            );
        }
        protected_ancestors(&pin.path)?;
        let file = boot_files::checked_file(pin)?;
        let id = fs::stat(&file)?;
        ensure(
            id.uid == 0 && id.gid == 0 && id.nlink == 1 && id.mode & 0o6022 == 0,
            "owned-run evidence is not one protected ordinary root file",
        )?;
        self.files.insert(pin.path.clone(), (pin.clone(), id, file));
        Ok(())
    }

    fn json(&mut self, pin: &FilePin, limit: u64) -> Result<Value> {
        ensure(
            pin.bytes > 0 && pin.bytes <= limit,
            "owned-run JSON evidence exceeds its bound",
        )?;
        self.admit(pin)?;
        let (_, before, file) = self.files.get(&pin.path).ok_or("evidence guard missing")?;
        let mut bytes = Vec::new();
        let mut reader = file;
        reader.seek(SeekFrom::Start(0))?;
        Read::by_ref(&mut reader)
            .take(limit + 1)
            .read_to_end(&mut bytes)?;
        ensure(
            bytes.len() as u64 == pin.bytes
                && fs::digest(&bytes) == pin.sha256
                && fs::stat(file)? == *before,
            "owned-run evidence changed during read",
        )?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    fn derived(&mut self, path: &Path, limit: u64) -> Result<(FilePin, Value)> {
        let pin = boot_files::pin_file(path)?;
        let value = self.json(&pin, limit)?;
        Ok((pin, value))
    }

    fn finish(&self) -> Result<Vec<Value>> {
        let mut result = Vec::new();
        for (pin, id, file) in self.files.values() {
            ensure(
                fs::stat(file)? == *id && boot_files::open_pin(pin)?.1 == *id,
                "held or named owned-run evidence changed during verification",
            )?;
            result.push(json!({"file":pin,"identity":id}));
        }
        Ok(result)
    }
}

fn protected_ancestors(path: &Path) -> Result<()> {
    fs::absolute_string(path)?;
    for parent in path.ancestors().skip(1) {
        let tree = fs::Tree::open(&fs::absolute_string(parent)?, 0)?;
        let id = fs::stat(&tree.root)?;
        ensure(
            id.gid == 0 && id.mode & 0o022 == 0,
            "owned-run evidence ancestor is not root protected",
        )?;
    }
    Ok(())
}

fn private(path: &Path) -> Result<()> {
    protected_ancestors(&path.join("unused"))?;
    let tree = fs::Tree::open(&fs::absolute_string(path)?, 0)?;
    ensure(
        fs::stat(&tree.root)?.mode & 0o7777 == 0o700,
        "owned-run directory is not private",
    )
}

fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}

fn pin(value: &Value) -> Result<FilePin> {
    Ok(serde_json::from_value(value.clone())?)
}

fn path(value: &Value) -> Result<PathBuf> {
    let value = PathBuf::from(value.as_str().ok_or("required evidence path missing")?);
    fs::absolute_string(&value)?;
    Ok(value)
}

fn same_value_pin(value: &Value, expected: &FilePin) -> Result<()> {
    ensure(
        same_pin(&pin(value)?, expected),
        "owned-run source pin substitution",
    )
}

fn safe_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 48
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
}

fn no_qualification(value: &Value) -> Result<()> {
    ensure(
        value["guest_qualified"] == false && value["production_ready"] == false,
        "preparation or collection cannot declare application/production qualification",
    )
}

fn phase(plan: &crate::boot::BootPlan, prepared: &Value, expected: BootPhase) -> Result<()> {
    let calibration = expected == BootPhase::MacCalibration;
    ensure(
        plan.android.calibrate == calibration
            && prepared["calibration_requested"] == calibration
            && plan.android.calibrate != plan.android.mac_release.is_some(),
        "requested boot phase differs from its actual source inputs",
    )?;
    if calibration {
        ensure(
            plan.android.persistent_data.is_none() && plan.public_apks.is_none(),
            "MAC calibration must not contain original working data or public APK imports",
        )?;
    } else {
        let names: BTreeSet<_> = plan
            .android
            .mac_release
            .as_ref()
            .ok_or("five-file MAC release missing")?
            .keys()
            .map(String::as_str)
            .collect();
        ensure(
            names == BTreeSet::from(MAC_FILES),
            "normal runtime lacks the exact five-file MAC release",
        )?;
    }
    if let Some(recorded) = prepared.get("boot_phase") {
        ensure(
            *recorded == serde_json::to_value(expected)?,
            "prepared phase label disagrees with actual inputs",
        )?;
    }
    Ok(())
}

fn process_status(status: &Value, pid: u64) -> Result<()> {
    ensure(
        status["Pid"].as_str().and_then(|s| s.parse::<u64>().ok()) == Some(pid),
        "paused QEMU PID differs",
    )?;
    for field in ["Uid", "Gid"] {
        ensure(
            status[field]
                .as_str()
                .is_some_and(|s| s.split_whitespace().collect::<Vec<_>>() == ["65534"; 4]),
            "paused QEMU retained privileged credentials",
        )?;
    }
    ensure(
        status["Groups"] == "",
        "paused QEMU retained supplementary groups",
    )?;
    for field in ["CapEff", "CapPrm", "CapInh", "CapAmb"] {
        ensure(
            status[field]
                .as_str()
                .and_then(|s| u64::from_str_radix(s, 16).ok())
                == Some(0),
            "paused QEMU retained effective or acquirable privilege",
        )?;
    }
    ensure(
        status["NoNewPrivs"] == "1" && status["Seccomp"] == "2",
        "paused QEMU sandbox was incomplete",
    )
}

fn args_field<'a>(args: &'a [String], name: &str) -> Result<&'a str> {
    let positions: Vec<_> = args
        .iter()
        .enumerate()
        .filter(|(_, v)| *v == name)
        .map(|(n, _)| n)
        .collect();
    ensure(
        positions.len() == 1,
        "missing or duplicated fixed QEMU argument",
    )?;
    Ok(args
        .get(positions[0] + 1)
        .ok_or("QEMU argument value missing")?)
}

fn complete_launch_args(args: &[String], run: &crate::boot_vm::RunPlan) -> Result<()> {
    let singles = [
        "-accel", "-chardev", "-mon", "-sandbox", "-machine", "-cpu", "-m", "-smp", "-display",
        "-vga", "-serial", "-monitor", "-kernel", "-initrd", "-append", "-drive", "-nic",
    ];
    let mut counts = BTreeMap::<&str, usize>::new();
    let mut devices = Vec::new();
    let mut sets = Vec::new();
    let mut descriptors = BTreeSet::new();
    let mut index = 0;
    while index < args.len() {
        let name = args[index].as_str();
        *counts.entry(name).or_default() += 1;
        index += 1;
        if ["-S", "-no-reboot"].contains(&name) {
            continue;
        }
        ensure(
            singles.contains(&name) || ["-add-fd", "-device"].contains(&name),
            "unrecognized extra QEMU option in owned launch",
        )?;
        let value = args.get(index).ok_or("owned QEMU option value absent")?;
        index += 1;
        let fd = if name == "-add-fd" {
            let fields: Vec<_> = value.split(',').collect();
            ensure(
                fields.len() == 2,
                "QEMU descriptor declaration has extra fields",
            )?;
            let fd: u32 = fields[0]
                .strip_prefix("fd=")
                .ok_or("QEMU fd absent")?
                .parse()?;
            let set: u32 = fields[1]
                .strip_prefix("set=")
                .ok_or("QEMU fdset absent")?
                .parse()?;
            sets.push(set);
            Some(fd)
        } else if ["-kernel", "-initrd"].contains(&name) {
            Some(
                value
                    .strip_prefix("/proc/self/fd/")
                    .ok_or("QEMU image is not a held descriptor")?
                    .parse::<u32>()?,
            )
        } else if name == "-chardev" {
            Some(
                value
                    .strip_prefix("socket,id=control,fd=")
                    .and_then(|v| v.strip_suffix(",server=on,wait=off"))
                    .ok_or("QEMU control is not its single inherited private socket")?
                    .parse::<u32>()?,
            )
        } else {
            None
        };
        if let Some(fd) = fd {
            ensure(
                fd >= 3 && descriptors.insert(fd),
                "QEMU input descriptors alias or use stdio",
            )?;
        }
        if name == "-device" {
            devices.push(value.as_str());
        }
    }
    for name in singles.into_iter().chain(["-S", "-no-reboot"]) {
        ensure(
            counts.get(name) == Some(&1),
            "owned QEMU singleton argument absent or duplicated",
        )?;
    }
    sets.sort();
    devices.sort();
    let mut expected_devices = vec![
        "virtio-blk-pci,drive=guest",
        "virtio-keyboard-pci",
        "virtio-mouse-pci",
        "intel-hda",
        "hda-duplex",
    ];
    expected_devices.sort();
    ensure(
        sets == [1, 2, 2] && descriptors.len() == 6 && devices == expected_devices,
        "owned QEMU inherited an extra device or descriptor set",
    )?;
    ensure(
        args_field(args, "-mon")? == "chardev=control,mode=control",
        "QEMU monitor transport differs",
    )?;
    ensure(
        (2..=24).contains(&run.cpus)
            && (4096..=12288).contains(&run.memory_mib)
            && (60..=3600).contains(&run.duration_seconds)
            && run
                .ssh_port
                .is_none_or(|port| run.network && (50000..=59999).contains(&port)),
        "owned run geometry or optional forwarding is outside the normal producer bounds",
    )?;
    let nic = if run.network {
        run.ssh_port.map_or_else(
            || "user,model=virtio-net-pci".to_owned(),
            |port| format!("user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:{port}-:22"),
        )
    } else {
        "none".to_owned()
    };
    ensure(
        args_field(args, "-nic")? == nic,
        "owned QEMU network differs from its explicit plan",
    )
}

fn launched(
    running: &Value,
    admitted: &Value,
    ended: &Value,
    run_plan: &crate::boot_vm::RunPlan,
    prepared: &Value,
) -> Result<(u32, Identity)> {
    let pid = running["pid"].as_u64().ok_or("owned runner PID missing")?;
    ensure(
        pid > 1 && pid <= i32::MAX as u64,
        "owned QEMU PID outside process range",
    )?;
    ensure(
        admitted["schema"] == "droidloom.qemu-paused-launch-admitted.v1"
            && admitted["qmp"]["return"]["running"] == false
            && ["prelaunch", "paused"]
                .contains(&admitted["qmp"]["return"]["status"].as_str().unwrap_or("")),
        "actual paused QMP admission missing",
    )?;
    process_status(&admitted["actual_process"]["process_status"], pid)?;
    let launcher = &admitted["launcher"];
    ensure(
        launcher["schema"] == "droidloom.qemu-fixed-descriptor-launch.v1"
            && *launcher == running["fixed_descriptor_launcher"]
            && launcher["sandbox"] == crate::boot_qemu::SANDBOX,
        "runner and paused process do not share the normal descriptor launcher",
    )?;
    let exe: Identity = serde_json::from_value(launcher["private_qemu_identity"].clone())?;
    ensure(
        exe.uid == 0
            && exe.gid == 0
            && exe.nlink == 1
            && exe.mode & 0o7777 == 0o511
            && admitted["actual_process"]["live_executable_device"] == exe.dev
            && admitted["actual_process"]["live_executable_inode"] == exe.ino
            && admitted["actual_process"]["proc_status_owner_for_non_dumpable_exec"]
                == json!([0, 0]),
        "live QEMU executable or non-dumpable ownership differs",
    )?;
    same_value_pin(&launcher["qemu_source"], &pin(&running["program"])?)?;
    same_value_pin(&ended["qemu"], &pin(&running["program"])?)?;
    let args: Vec<String> = serde_json::from_value(running["args"].clone())?;
    ensure(args.len() <= 128, "QEMU argument bound exceeded")?;
    complete_launch_args(&args, run_plan)?;
    for (name, expected) in [
        ("-accel", "kvm,device=/dev/fdset/1"),
        ("-sandbox", crate::boot_qemu::SANDBOX),
        ("-machine", "q35"),
        ("-cpu", "host"),
        ("-display", "none"),
        ("-vga", "virtio"),
        ("-serial", "stdio"),
        ("-monitor", "none"),
        (
            "-drive",
            "if=none,id=guest,format=raw,cache=writethrough,file=/dev/fdset/2",
        ),
    ] {
        ensure(
            args_field(&args, name)? == expected,
            "fixed owned QEMU launch argument changed",
        )?;
    }
    ensure(
        args_field(&args, "-m")? == run_plan.memory_mib.to_string()
            && args_field(&args, "-smp")? == run_plan.cpus.to_string()
            && args.iter().filter(|v| v.as_str() == "-S").count() == 1
            && args.iter().filter(|v| v.as_str() == "-no-reboot").count() == 1,
        "actual QEMU geometry or paused single-boot launch differs",
    )?;
    let uuid = prepared["root_filesystem_uuid"]
        .as_str()
        .ok_or("prepared root UUID absent")?;
    let line =
        crate::boot_vm::kernel_command_line(uuid, prepared["calibration_requested"] == true)?;
    ensure(
        args_field(&args, "-append")? == line,
        "actual kernel command line is not the enforcing normal entry",
    )?;
    ordinary_end(ended, run_plan.duration_seconds)?;
    Ok((pid as u32, exe))
}

fn ordinary_end(ended: &Value, budget: u64) -> Result<()> {
    ensure(
        ended["exit_code"] == 0 && ended["signal"].is_null() && ended["forced_stop"] == false,
        "owned QEMU did not return through normal guest shutdown",
    )?;
    let elapsed = ended["elapsed_seconds"]
        .as_u64()
        .ok_or("owned run duration absent")?;
    ensure(
        elapsed >= 1 && elapsed <= budget + 60,
        "owned run exceeded its normal termination budget",
    )?;
    Ok(())
}

fn retired(pid: u32, exe: &Identity) -> Result<()> {
    match std::fs::metadata(format!("/proc/{pid}/exe")) {
        Ok(id) => ensure(
            (id.dev(), id.ino()) != (exe.dev, exe.ino),
            "the admitted original QEMU still executes",
        )?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

pub fn run(config: &Path, expected: &str) -> Result<()> {
    let config_pin = boot_files::pin_file(config)?;
    ensure(
        config_pin.sha256 == expected,
        "owned-guest verification plan digest differs",
    )?;
    let mut custody = Custody::default();
    let verifier = boot_files::pin_file(&std::env::current_exe()?)?;
    custody.admit(&verifier)?;
    let plan: Plan = serde_json::from_value(custody.json(&config_pin, 1024 * 1024)?)?;
    ensure(
        plan.schema == "droidloom.owned-full-guest-evidence-plan.v1"
            && safe_name(&plan.verification_name),
        "unsupported owned-guest evidence plan",
    )?;
    let collected = custody.json(&plan.collected, 8 * 1024 * 1024)?;
    ensure(
        collected["schema"] == "droidloom.full-ubuntu-boot-collected.v1"
            && collected["status"] == "collected"
            && collected["errors"] == json!([]),
        "the source collector did not finish; keep its actual failure evidence",
    )?;
    no_qualification(&collected)?;
    let collect_plan = custody.json(&plan.collect_plan, 1024 * 1024)?;
    ensure(
        collect_plan["schema"] == "droidloom.full-ubuntu-boot-collect-plan.v1"
            && collected["input_sha256"] == plan.collect_plan.sha256,
        "actual collector input identity differs",
    )?;
    let ended_pin = pin(&collected["ended"])?;
    same_value_pin(&collect_plan["ended"], &ended_pin)?;
    let ended = custody.json(&ended_pin, 1024 * 1024)?;
    ensure(
        ended["schema"] == "droidloom.full-ubuntu-run-ended.v1",
        "original owned runner did not end",
    )?;
    no_qualification(&ended)?;
    let prepared_pin = pin(&ended["prepared"])?;
    same_value_pin(&collected["prepared"], &prepared_pin)?;
    let prepared = custody.json(&prepared_pin, 8 * 1024 * 1024)?;
    ensure(
        prepared["schema"] == "droidloom.full-ubuntu-boot-prepared.v1"
            && prepared["input_sha256"] == plan.boot_plan.sha256,
        "actual full-guest preparation source differs",
    )?;
    no_qualification(&prepared)?;
    let boot_value = custody.json(&plan.boot_plan, 8 * 1024 * 1024)?;
    let boot_plan: crate::boot::BootPlan = serde_json::from_value(boot_value.clone())?;
    ensure(
        boot_plan.schema == "droidloom.full-ubuntu-boot-plan.v1"
            && boot_plan.libselinux_candidate.is_none()
            && boot_plan.libapparmor_candidate.is_none()
            && boot_plan.gdm_candidate.is_none(),
        "owned full-guest evidence requires complete normal native packages",
    )?;
    phase(&boot_plan, &prepared, plan.expected_boot_phase)?;
    let work = path(&prepared["work_directory"])?;
    let boot = work.join("boot");
    let run = path(&ended["run_directory"])?;
    let collection = path(&collected["collection_directory"])?;
    ensure(
        work.parent() == Some(Path::new(BASE))
            && path(&prepared["boot_directory"])? == boot
            && prepared_pin.path == boot.join("BOOT-PREPARED.json")
            && run.parent() == Some(boot.as_path())
            && ended_pin.path == run.join("RUN-ENDED.json")
            && collection.parent() == Some(run.as_path())
            && plan.collected.path == collection.join("COLLECTED.json"),
        "owned evidence does not belong to one private qualification tree",
    )?;
    for dir in [&work, &boot, &run, &collection] {
        private(dir)?;
    }
    ensure(
        !run.join("RUN-FAILED.json").exists(),
        "owned runner retained a failure receipt",
    )?;
    let (_, recorded_boot) = custody.derived(&boot.join("BOOT-INPUTS.json"), 8 * 1024 * 1024)?;
    let (_, recorded_collect) =
        custody.derived(&collection.join("COLLECT-INPUTS.json"), 1024 * 1024)?;
    let recorded_boot: crate::boot::BootPlan = serde_json::from_value(recorded_boot)?;
    ensure(
        serde_json::to_value(recorded_boot)? == serde_json::to_value(&boot_plan)?
            && recorded_collect == collect_plan,
        "preserved original plan semantics differ",
    )?;
    let (run_inputs, run_value) = custody.derived(&run.join("RUN-INPUTS.json"), 1024 * 1024)?;
    let run_plan: crate::boot_vm::RunPlan = serde_json::from_value(run_value)?;
    ensure(
        run_plan.schema == "droidloom.full-ubuntu-run-plan.v1"
            && run.file_name().and_then(|v| v.to_str()) == Some(run_plan.run_name.as_str())
            && same_pin(&run_plan.prepared, &prepared_pin),
        "actual owned run input binding differs",
    )?;
    let (running_pin, running) = custody.derived(&run.join("RUNNING.json"), 1024 * 1024)?;
    let (admitted_pin, admitted) = custody.derived(&run.join("QEMU-ADMITTED.json"), 1024 * 1024)?;
    let (pid, executable) = launched(&running, &admitted, &ended, &run_plan, &prepared)?;
    retired(pid, &executable)?;
    let launch = &admitted["launcher"];
    ensure(
        path(&running["private_qmp"])? == run.join("qmp.sock")
            && pin(&launch["qemu_source"])?.path == Path::new("/usr/bin/qemu-system-x86_64")
            && pin(&launch["privilege_tool"])?.path == Path::new("/usr/bin/setpriv"),
        "owned launcher changed its fixed native executables or monitor",
    )?;
    for (field, filename) in [
        ("private_qemu", "qemu-original"),
        ("private_privilege_tool", "setpriv-original"),
        ("kernel_readonly", "kernel-readonly"),
        ("initrd_readonly", "initrd-readonly"),
    ] {
        let value = pin(&launch[field])?;
        ensure(
            value.path == run.join(filename),
            "private descriptor source path differs",
        )?;
        custody.admit(&value)?;
    }
    let private_qemu = pin(&launch["private_qemu"])?;
    ensure(
        boot_files::open_pin(&private_qemu)?.1 == executable,
        "admitted QEMU private inode changed",
    )?;
    for (source_field, copied_field) in [
        ("qemu_source", "private_qemu"),
        ("privilege_tool", "private_privilege_tool"),
    ] {
        let source = pin(&launch[source_field])?;
        let copy = pin(&launch[copied_field])?;
        ensure(
            source.bytes == copy.bytes && source.sha256 == copy.sha256,
            "private launcher is not the original tool bytes",
        )?;
    }
    let source = pin(&prepared["root_image"])?;
    let working = pin(&ended["working_disk"])?;
    ensure(
        source.path.parent() == Some(boot.as_path())
            && working.path == run.join("working.ext4")
            && path(&running["working_disk"])? == working.path,
        "owned disk paths differ",
    )?;
    same_value_pin(&ended["preserved_source_image"], &source)?;
    same_value_pin(&running["preserved_source_image"], &source)?;
    let source_identity: Identity = serde_json::from_value(ended["source_identity"].clone())?;
    ensure(
        running["source_identity"] == ended["source_identity"]
            && boot_files::open_pin(&source)?.1 == source_identity,
        "original prepared disk custody changed",
    )?;
    custody.admit(&source)?;
    custody.admit(&working)?;
    let working_id = boot_files::open_pin(&working)?.1;
    ensure(
        working.bytes == source.bytes
            && (working_id.dev, working_id.ino) != (source_identity.dev, source_identity.ino),
        "working disk aliases its prepared source",
    )?;
    let launched_disk: Identity = serde_json::from_value(launch["working_disk_identity"].clone())?;
    ensure(
        (working_id.dev, working_id.ino) == (launched_disk.dev, launched_disk.ino)
            && working_id.mode & 0o7777 == 0o600
            && source_identity.mode & 0o7777 == 0o600,
        "actual launched working disk differs from ended evidence",
    )?;
    let serial = pin(&ended["serial"])?;
    ensure(
        serial.path == run.join("serial.log"),
        "owned serial belongs to another run",
    )?;
    custody.admit(&serial)?;
    let native_pin = pin(&prepared["native_receipt"])?;
    same_value_pin(&prepared["native_receipt"], &boot_plan.native_receipt)?;
    ensure(
        native_pin.path == work.join("NATIVE-PREPARED.json"),
        "complete native receipt path differs",
    )?;
    let native = custody.json(&native_pin, 8 * 1024 * 1024)?;
    ensure(
        native["schema"] == crate::boot_complete::PREPARED_SCHEMA,
        "historical partial fixture is not complete native evidence",
    )?;
    ensure(
        native["root_filesystem_uuid"] == prepared["root_filesystem_uuid"]
            && path(&native["root"])? == work.join("root"),
        "complete native root identity differs",
    )?;
    let manifest_pin = pin(&native["complete_fixture_manifest"])?;
    custody.admit(&manifest_pin)?;
    let manifest = crate::boot_complete::admitted_manifest(&manifest_pin)?;
    let families = crate::boot_complete::normal_families(&manifest.packages)?;
    ensure(
        families == native["normal_native_packages"]
            && same_pin(
                &pin(&prepared["complete_native_package_admission"]["manifest"])?,
                &manifest_pin,
            ),
        "complete native family and source manifest differ",
    )?;
    let database = pin(&native["dpkg_status_preserved"])?;
    ensure(
        database.path == work.join("root/var/lib/dpkg/status"),
        "complete normal package database path differs",
    )?;
    custody.admit(&database)?;
    let host: crate::boot_host::HostManifest =
        serde_json::from_value(custody.json(&boot_plan.host_manifest, 1024 * 1024)?)?;
    crate::boot_host::validate_manifest(&host)?;
    same_value_pin(
        &prepared["host_release"]["normal_host_manifest"],
        &boot_plan.host_manifest,
    )?;
    same_value_pin(
        &prepared["host_release"]["normal_host_archive"],
        &boot_plan.host_archive,
    )?;
    ensure(
        prepared["host_release"]["source_commit"] == host.commit
            && prepared["host_release"]["source_tree"] == host.tree,
        "normal host producer identity differs",
    )?;
    custody.admit(&boot_plan.host_archive)?;
    for (field, expected) in [("kernel", &boot_plan.kernel)] {
        let copied = pin(&prepared[field])?;
        custody.admit(&copied)?;
        ensure(
            copied.bytes == expected.bytes && copied.sha256 == expected.sha256,
            "prepared shared kernel bytes differ",
        )?;
        let readonly = pin(&launch["kernel_readonly"])?;
        ensure(
            readonly.bytes == copied.bytes && readonly.sha256 == copied.sha256,
            "QEMU received another kernel",
        )?;
    }
    ensure(
        prepared["target_kernel_release"] == manifest.target_kernel_release
            && manifest.target_kernel_release
                == crate::boot_apparmor_candidate::REQUIRED_KERNEL_RELEASE,
        "full guest did not use the retained shared kernel",
    )?;
    let initrd = pin(&prepared["initrd"])?;
    custody.admit(&initrd)?;
    let readonly = pin(&launch["initrd_readonly"])?;
    ensure(
        readonly.bytes == initrd.bytes && readonly.sha256 == initrd.sha256,
        "QEMU received another initramfs",
    )?;
    for (field, expected) in [
        ("cohort", &boot_plan.android.cohort),
        ("runtime", &boot_plan.android.runtime),
    ] {
        same_value_pin(&prepared["android_release"][field], expected)?;
        custody.admit(expected)?;
    }
    if let Some(files) = &boot_plan.android.mac_release {
        for value in files.values() {
            custody.admit(value)?;
        }
    }
    let labels_pin = pin(&prepared["labels"])?;
    ensure(
        labels_pin.path == boot.join("ROOT-LABELS.json"),
        "native label evidence path differs",
    )?;
    let labels = custody.json(&labels_pin, 32 * 1024 * 1024)?;
    ensure(
        labels["missing"] == json!([])
            && labels["labels"].as_array().is_some_and(|v| !v.is_empty()),
        "full native labeling left missing paths",
    )?;
    for (field, host_path) in [
        ("policy", "etc/selinux/droidloom/policy/policy.30"),
        (
            "contexts",
            "etc/selinux/droidloom/contexts/files/file_contexts",
        ),
    ] {
        let selected = pin(&labels[field])?;
        custody.admit(&selected)?;
        let row = host
            .files
            .iter()
            .find(|f| f.path == host_path)
            .ok_or("normal host lacks native MAC input")?;
        ensure(
            selected.bytes == row.size && selected.sha256 == row.sha256,
            "native MAC input differs from normal host",
        )?;
    }
    let verify_dir = run.join(&plan.verification_name);
    let fresh_name = format!("{}-journals", plan.verification_name);
    ensure(
        verify_dir != collection
            && fresh_name != collect_plan["collection_name"].as_str().unwrap_or(""),
        "verification must not replace the original collection",
    )?;
    boot_files::private_dir(&verify_dir)?;
    let mut fresh_plan = collect_plan.clone();
    fresh_plan["collection_name"] = json!(fresh_name);
    let fresh_input = verify_dir.join("COLLECT-INPUTS.json");
    let fresh_sha = fs::write_json(&fs::absolute_string(&fresh_input)?, &fresh_plan, 0)?;
    let fresh_pin = crate::boot_collect::collect_to_receipt(&fresh_input, &fresh_sha)?;
    let fresh = custody.json(&fresh_pin, 16 * 1024 * 1024)?;
    ensure(
        fresh["status"] == "collected" && fresh["errors"] == json!([]),
        "actual ended-disk recollection failed",
    )?;
    ensure(
        fresh["details"]["ordinary_guest_shutdown"] == true
            && fresh["details"]["journal_integrity_verified"] == true,
        "normal shutdown or native journal integrity failed",
    )?;
    if plan.expected_boot_phase == BootPhase::MacCalibration {
        ensure(
            fresh["details"]["calibration_capture_proven"] == true,
            "same-candidate MAC calibration lacks actual PID 1 exit/job/capture evidence",
        )?;
    }
    retired(pid, &executable)?;
    let evidence = custody.finish()?;
    let result = json!({
        "schema":"droidloom.owned-full-guest-evidence.v1", "input":config_pin, "verifier":verifier,
        "boot_phase":plan.expected_boot_phase, "scope":"owned_normal_guest_mechanism_only",
        "boot_inputs":plan.boot_plan,"run_inputs":run_inputs,"running":running_pin,"paused_admission":admitted_pin,
        "ended":ended_pin,"original_collection":plan.collected,"fresh_collection":fresh_pin,
        "complete_native_manifest":manifest_pin,"normal_native_packages":families,
        "normal_host_manifest":boot_plan.host_manifest,"source_commit":host.commit,"source_tree":host.tree,
        "shared_kernel":prepared["kernel"],"cohort":boot_plan.android.cohort,"runtime":boot_plan.android.runtime,
        "independent_working_disk":working,"preserved_source_image":source,
        "data_scope":if boot_plan.android.persistent_data.is_some(){"independent_copy_supplied_not_yet_business_accepted"}else{"fresh_fixture_data"},
        "actual_native_observations":fresh["details"],"verified_file_custody":evidence,
        "remaining_cold_authorities":["normal_public_and_sixteen_native_release_binding",
            "original_host_initramfs_and_file_contexts_readback","independent_original_data_business_acceptance",
            "same_candidate_five_file_mac_publication","selected_39_complete_business_and_common_gates",
            "actual_maintenance_and_original_ubuntu_return"],
        "physical_publication_authorized":false,"physical_activation_authorized":false,
        "guest_qualified":false,"runtime_qualified":false,"production_ready":false
    });
    let output = verify_dir.join("OWNED-GUEST-VERIFIED.json");
    let sha = fs::write_json(&fs::absolute_string(&output)?, &result, 0)?;
    println!(
        "{}",
        json!({"receipt":output,"sha256":sha,"scope":"owned_normal_guest_mechanism_only",
        "physical_activation_authorized":false,"production_ready":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn status() -> Value {
        json!({"Pid":"42","Uid":"65534 65534 65534 65534","Gid":"65534 65534 65534 65534",
            "Groups":"","CapEff":"0000000000000000","CapPrm":"0","CapInh":"0","CapAmb":"0",
            "NoNewPrivs":"1","Seccomp":"2"})
    }

    #[test]
    fn actual_process_fields_reject_privilege_or_another_owner() -> Result<()> {
        process_status(&status(), 42)?;
        assert!(process_status(&status(), 43).is_err());
        for (name, value) in [
            ("Uid", "0 0 0 0"),
            ("Gid", "65534 0 65534 65534"),
            ("Groups", "993"),
            ("CapEff", "1"),
            ("CapPrm", "1"),
            ("CapInh", "1"),
            ("CapAmb", "1"),
            ("NoNewPrivs", "0"),
            ("Seccomp", "0"),
        ] {
            let mut changed = status();
            changed[name] = json!(value);
            assert!(process_status(&changed, 42).is_err(), "{name}");
        }
        Ok(())
    }

    #[test]
    fn plan_cannot_add_pass_flags_or_escape_the_private_verification_name() {
        assert!(safe_name("owned-r1"));
        for value in ["", "../outside", "a/b", "a;command", "name journals"] {
            assert!(!safe_name(value));
        }
        let p = json!({"path":"/evidence","bytes":1,"sha256":"a".repeat(64)});
        let mut value = json!({"schema":"droidloom.owned-full-guest-evidence-plan.v1",
            "boot_plan":p,"collect_plan":p,"collected":p,"expected_boot_phase":"mac_calibration",
            "verification_name":"owned-r1"});
        assert!(serde_json::from_value::<Plan>(value.clone()).is_ok());
        value["passed"] = json!(true);
        assert!(serde_json::from_value::<Plan>(value).is_err());
    }

    #[test]
    fn fixed_launch_arguments_reject_duplicates_and_missing_values() -> Result<()> {
        assert_eq!(
            args_field(&["-sandbox".into(), "original".into()], "-sandbox")?,
            "original"
        );
        assert!(args_field(&[], "-sandbox").is_err());
        assert!(args_field(&["-sandbox".into()], "-sandbox").is_err());
        assert!(
            args_field(
                &[
                    "-sandbox".into(),
                    "original".into(),
                    "-sandbox".into(),
                    "off".into()
                ],
                "-sandbox"
            )
            .is_err()
        );
        Ok(())
    }

    fn normal_args() -> (Vec<String>, crate::boot_vm::RunPlan) {
        let plan = crate::boot_vm::RunPlan {
            schema: "droidloom.full-ubuntu-run-plan.v1".into(),
            prepared: FilePin {
                path: "/prepared".into(),
                bytes: 1,
                sha256: "a".repeat(64),
            },
            run_name: "run1".into(),
            cpus: 2,
            memory_mib: 4096,
            duration_seconds: 60,
            network: false,
            ssh_port: None,
        };
        let args = [
            "-accel",
            "kvm,device=/dev/fdset/1",
            "-add-fd",
            "fd=3,set=1",
            "-add-fd",
            "fd=4,set=2",
            "-add-fd",
            "fd=5,set=2",
            "-chardev",
            "socket,id=control,fd=6,server=on,wait=off",
            "-mon",
            "chardev=control,mode=control",
            "-sandbox",
            crate::boot_qemu::SANDBOX,
            "-S",
            "-machine",
            "q35",
            "-cpu",
            "host",
            "-m",
            "4096",
            "-smp",
            "2",
            "-display",
            "none",
            "-vga",
            "virtio",
            "-serial",
            "stdio",
            "-no-reboot",
            "-monitor",
            "none",
            "-kernel",
            "/proc/self/fd/7",
            "-initrd",
            "/proc/self/fd/8",
            "-append",
            "admitted-command-line",
            "-drive",
            "if=none,id=guest,format=raw,cache=writethrough,file=/dev/fdset/2",
            "-device",
            "virtio-blk-pci,drive=guest",
            "-device",
            "virtio-keyboard-pci",
            "-device",
            "virtio-mouse-pci",
            "-device",
            "intel-hda",
            "-device",
            "hda-duplex",
            "-nic",
            "none",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect();
        (args, plan)
    }

    #[test]
    fn complete_launch_rejects_extra_storage_network_and_descriptor_aliases() -> Result<()> {
        let (args, plan) = normal_args();
        complete_launch_args(&args, &plan)?;
        for extra in [
            vec!["-drive", "file=/original.img"],
            vec!["-readconfig", "/unverified"],
            vec!["-device", "vfio-pci"],
            vec!["-add-fd", "fd=9,set=3"],
        ] {
            let mut changed = args.clone();
            changed.extend(extra.into_iter().map(str::to_owned));
            assert!(complete_launch_args(&changed, &plan).is_err());
        }
        for (from, to) in [
            ("fd=5,set=2", "fd=4,set=2"),
            ("/proc/self/fd/8", "/proc/self/fd/3"),
            ("fd=3,set=1", "fd=0,set=1"),
        ] {
            let changed: Vec<_> = args
                .iter()
                .map(|v| if v == from { to.into() } else { v.clone() })
                .collect();
            assert!(complete_launch_args(&changed, &plan).is_err());
        }
        let mut changed = args.clone();
        *changed.last_mut().unwrap() = "user,hostfwd=tcp::22-:22".into();
        assert!(complete_launch_args(&changed, &plan).is_err());
        Ok(())
    }

    #[test]
    fn shared_kernel_command_line_keeps_calibration_before_runtime() -> Result<()> {
        let uuid = "01c27223-3933-481e-9836-7bd0ef1be8c9";
        let first = crate::boot_vm::kernel_command_line(uuid, true)?;
        let normal = crate::boot_vm::kernel_command_line(uuid, false)?;
        assert!(first.contains("systemd.unit=droidloom-calibration-qualification.target "));
        assert!(normal.contains("systemd.unit=graphical.target "));
        for line in [first, normal] {
            assert!(line.contains(" enforcing=1 "));
            assert!(line.contains("yama,selinux,apparmor,bpf"));
            assert!(
                line.contains(" init=/usr/lib/droidloom/production/current/droidloom-board-init ")
            );
        }
        assert!(
            crate::boot_vm::kernel_command_line("------------------------------------", true)
                .is_err()
        );
        Ok(())
    }
    #[test]
    fn ordinary_guest_exit_cannot_be_replaced_by_forced_or_failed_shutdown() -> Result<()> {
        let original =
            json!({"exit_code":0,"signal":null,"forced_stop":false,"elapsed_seconds":65});
        ordinary_end(&original, 60)?;
        for (field, value) in [
            ("exit_code", json!(1)),
            ("signal", json!(9)),
            ("forced_stop", json!(true)),
            ("elapsed_seconds", json!(0)),
            ("elapsed_seconds", json!(121)),
        ] {
            let mut changed = original.clone();
            changed[field] = value;
            assert!(ordinary_end(&changed, 60).is_err(), "{field}");
        }
        Ok(())
    }
}
