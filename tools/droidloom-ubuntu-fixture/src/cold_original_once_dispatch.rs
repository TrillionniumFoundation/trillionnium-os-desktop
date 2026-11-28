//! The single original-machine dispatcher. Plans select immutable inputs;
//! only actual material/owner factories create mutation and retirement rights.
//! A resumed preparation is retired, never silently advanced past a missing
//! acknowledgement. Permanent activation is deliberately a different gate.
use super::{
    OriginalLabelWindow, OriginalQualificationAuthority, OriginalRestoreLabelWindow,
    RetirementSource,
    commands::{self, CommandEvidence},
    configurations::{
        self, ConfigurationRestoration, Configurations, Entry, Payload,
        package_parents::{self, NativeOperation},
    },
    materials,
    owner::SealedInput,
    quiescence::Quiescence,
    retirement,
    state::Phase,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::{self, OriginalDataTransaction},
    cold_original_once_recovery::contract::{self as c, PayloadPin, ReturnConfiguration},
    ensure, fs,
};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    fs::File,
    path::{Path, PathBuf},
    rc::Rc,
};

fn string<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v[key]
        .as_str()
        .ok_or_else(|| format!("actual once source lacks {key}").into())
}
fn pin(v: &Value) -> Result<FilePin> {
    Ok(serde_json::from_value(v.clone())?)
}
fn read(pin: &FilePin) -> Result<Value> {
    Ok(serde_json::from_slice(&files::read_pin(
        pin,
        128 * 1024 * 1024,
    )?)?)
}
fn save(path: &Path, v: &impl Serialize) -> Result<FilePin> {
    let mut bytes = serde_json::to_vec_pretty(v)?;
    bytes.push(b'\n');
    ensure(
        bytes.len() <= 128 * 1024 * 1024,
        "bounded source-owned once record",
    )?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("record parent")?)?.sync_all()?;
    let p = files::pin_file(path)?;
    SealedInput::open(&p)?;
    Ok(p)
}
fn source(a: &OriginalQualificationAuthority, name: &str, bytes: &[u8]) -> Result<FilePin> {
    ensure(
        !name.is_empty()
            && name.len() <= 96
            && name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
        "fixed source recipe name",
    )?;
    let dir = a.work().join("configuration-sources");
    if !dir.exists() {
        files::private_dir(&dir)?;
        File::open(a.work())?.sync_all()?;
    }
    let path = dir.join(name);
    if path.exists() {
        let p = files::pin_file(&path)?;
        ensure(
            p.bytes == bytes.len() as u64
                && p.sha256 == fs::digest(bytes)
                && files::read_pin(&p, 128 * 1024 * 1024)? == bytes,
            "retained source recipe differs",
        )?;
        let (_, id) = files::open_pin(&p)?;
        ensure(
            id.uid == 0 && id.gid == 0 && id.nlink == 1 && id.mode & 0o7777 == 0o400,
            "source recipe custody",
        )?;
        return Ok(p);
    }
    files::write_new(&path, bytes, 0o400)?;
    File::open(&dir)?.sync_all()?;
    files::pin_file(&path)
}
fn json_source(
    a: &OriginalQualificationAuthority,
    name: &str,
    value: &impl Serialize,
) -> Result<FilePin> {
    let mut body = serde_json::to_vec_pretty(value)?;
    body.push(b'\n');
    source(a, name, &body)
}
fn phase(a: &OriginalQualificationAuthority) -> Result<Phase> {
    a.journal
        .borrow()
        .phase()
        .ok_or("actual once journal is empty".into())
}
fn event(a: &OriginalQualificationAuthority, next: Phase, observed: Value) -> Result<()> {
    a.verify_current_owner()?;
    let boot = a.owner.borrow().boot_id().to_owned();
    a.journal.borrow_mut().append(next, &boot, observed)?;
    a.verify_current_owner()
}
fn observation(a: &OriginalQualificationAuthority, p: Phase) -> Result<Option<Value>> {
    a.journal.borrow().observation(p)
}
// These are the three source-owned producers of command work directories.
// Recognizing a name allocates no operation or qualification authority.
fn command_history_index(directory: &str, name: &str) -> Result<Option<usize>> {
    if let Some(rest) = name.strip_prefix("dispatch-") {
        ensure(
            rest.len() > 5
                && rest.is_ascii()
                && rest.as_bytes()[4] == b'-'
                && rest[..4].bytes().all(|b| b.is_ascii_digit())
                && rest[5..]
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b == b'-'),
            "fixed bounded dispatch history name",
        )?;
        let index = rest[..4].parse::<usize>()?;
        ensure(index < 4096, "bounded dispatch ordinal")?;
        return Ok(Some(index));
    }
    ensure(
        directory == "commands",
        "native parent history is dispatch-only",
    )?;
    for prefix in ["label-writer-inventory-", "label-thaw-guard-start-"] {
        if let Some(rest) = name.strip_prefix(prefix) {
            let (purpose, invocation) = rest.split_once('-').ok_or("quiescence history fields")?;
            ensure(
                matches!(purpose, "forward" | "restore")
                    && invocation.len() == 32
                    && invocation.bytes().all(|b| b.is_ascii_hexdigit()),
                "source-owned quiescence history name",
            )?;
            return Ok(None);
        }
    }
    if let Some(rest) = name.strip_prefix("retirement-") {
        ensure(
            rest.is_ascii()
                && rest.len() > 70
                && rest.as_bytes()[36] == b'-'
                && rest.as_bytes()[69] == b'-'
                && c::uuid(&rest[..36])
                && rest[37..69].bytes().all(|b| b.is_ascii_hexdigit())
                && matches!(&rest[70..], "grub" | "journal"),
            "source-owned retirement observation name",
        )?;
        return Ok(None);
    }
    Err("unknown original once command history member".into())
}
fn next_command_name_in(work: &Path, op: &str) -> Result<String> {
    ensure(
        !op.is_empty() && op.len() <= 48 && op.bytes().all(|b| b.is_ascii_lowercase() || b == b'-'),
        "closed dispatch operation name",
    )?;
    let mut next = 0usize;
    for directory in ["commands", "native-package-parents"] {
        let root = work.join(directory);
        if !root.try_exists()? {
            continue;
        }
        let mut count = 0;
        for row in std::fs::read_dir(&root)? {
            let row = row?;
            ensure(
                row.file_type()?.is_dir(),
                "command history member is not an actual directory",
            )?;
            let name = row
                .file_name()
                .into_string()
                .map_err(|_| "dispatch history nonUTF8 name")?;
            if let Some(index) = command_history_index(directory, &name)? {
                next = next.max(index + 1);
            }
            count += 1;
            ensure(count <= 4096, "bounded resumable command history")?;
        }
    }
    ensure(next < 4096, "resumable dispatch history exhausted")?;
    Ok(format!("dispatch-{next:04}-{op}"))
}
fn next_command_name(a: &OriginalQualificationAuthority, op: &str) -> Result<String> {
    next_command_name_in(a.work(), op)
}

fn command(
    a: &OriginalQualificationAuthority,
    op: &str,
    arg: Value,
    seconds: u64,
) -> Result<CommandEvidence> {
    commands::call(a, &next_command_name(a, op)?, op, arg, seconds)
}
fn ctl(a: &OriginalQualificationAuthority, args: &[&str]) -> Result<CommandEvidence> {
    let r = command(a, "systemctl", json!({"argv":args}), 105)?;
    ensure(r.report["exit"] == 0, "actual normal systemctl failed")?;
    Ok(r)
}
fn regular(path: impl Into<PathBuf>, source: FilePin, mode: u32) -> Entry {
    Entry {
        path: path.into(),
        payload: Payload::Regular { source, mode },
    }
}
fn link(path: impl Into<PathBuf>, target: impl Into<String>) -> Entry {
    Entry {
        path: path.into(),
        payload: Payload::Symlink {
            target: target.into(),
        },
    }
}
fn publish(a: &OriginalQualificationAuthority, group: &str, entries: Vec<Entry>) -> Result<Value> {
    Configurations::create(a, group)?.publish(a, entries)
}
fn original_grub(a: &OriginalQualificationAuthority) -> Result<Value> {
    let intent = read(a.intent.pin())?;
    read(&pin(&intent["original_grub"])?)
}
fn original_grub_member(a: &OriginalQualificationAuthority, path: &str) -> Result<FilePin> {
    let v = original_grub(a)?;
    let rows = v["preserved"]
        .as_array()
        .ok_or("original GRUB member roster")?;
    let matches = rows
        .iter()
        .filter(|r| r["source"]["path"] == path)
        .collect::<Vec<_>>();
    ensure(matches.len() == 1, "unique original GRUB member required")?;
    pin(&matches[0]["source"])
}
fn grub(a: &OriginalQualificationAuthority, op: &str) -> Result<CommandEvidence> {
    let cfg = original_grub_member(a, "/boot/grub/grub.cfg")?;
    command(a, op, json!({"original_cfg_sha256":cfg.sha256}), 45)
}

/// The normal private producer still runs while the original package database
/// is untouched. Later installation only publishes this completely read image.
fn prepare_recovery(a: &OriginalQualificationAuthority) -> Result<FilePin> {
    ensure(
        phase(a)? == Phase::Admitted,
        "recovery build must precede public/native package mutation",
    )?;
    let admitted = a.materials.admitted()?;
    let original_input = read(&pin(&admitted["input"])?)?;
    let original_prepared = read(&pin(&original_input["prepared_initramfs"])?)?;
    let initial = pin(&original_prepared["input"])?;
    let mut plan = read(&initial)?;
    ensure(
        plan["schema"] == "droidloom.original-host-initramfs-plan.v1",
        "normal initramfs plan schema",
    )?;
    let work = Path::new("/var/lib/droidloom-qualification").join(format!(
        "original-initramfs-once-{}",
        &a.candidate_id()[..24]
    ));
    ensure(!work.exists(), "recovery producer work must be new")?;
    plan["work_directory"] = json!(work);
    plan["recovery_recipe"] = serde_json::to_value(a.materials.recipe())?;
    let p = json_source(a, "RECOVERY-PRODUCER.json", &plan)?;
    crate::cold_original_initramfs::prepare(&p.path, &p.sha256)?;
    a.verify_current_owner()?;
    let receipt = files::pin_file(&work.join("ORIGINAL-INITRAMFS-PREPARED.json"))?;
    let actual = read(&receipt)?;
    ensure(
        actual["input"] == serde_json::to_value(&p)?
            && actual["recovery_recipe_input"] == serde_json::to_value(a.materials.recipe())?
            && actual["recovery_image_readback"].is_object(),
        "normal recovery image lost the actual recipe/readback",
    )?;
    let initrd = pin(&actual["initrd"])?;
    files::checked_file(&initrd)?;
    save(
        &a.work().join("RECOVERY-PREPARED.json"),
        &json!({"schema":"droidloom.original-once-recovery-prepared.v1","intent":a.intent.pin(),"normal_prepared":receipt,"initrd":initrd,"qualification_accepted":false}),
    )?;
    Ok(initrd)
}

fn owner_entries(a: &OriginalQualificationAuthority) -> Result<Vec<Entry>> {
    let intent = read(a.intent.pin())?;
    let producer = pin(&intent["normal_producer"])?;
    let input = pin(&a.materials.admitted()?["input"])?;
    for p in [&producer.path, &input.path] {
        let s = fs::absolute_string(p)?;
        ensure(
            !s.contains([' ', '\t', '\n', '%', '\\', '"']),
            "normal owner path requires literal unit-safe bytes",
        )?;
    }
    let unit = format!(
        "droidloom-original-qualification@{}.service",
        a.candidate_id()
    );
    let body = format!(
        "[Unit]\nDescription=Droidloom original once qualification recovery\nAfter=local-fs.target\nBefore=display-manager.service graphical.target\nConditionKernelVersion={}\nConditionKernelCommandLine=!droidloom.once\nConditionPathExists={}\nStartLimitIntervalSec=600\nStartLimitBurst=3\n\n[Service]\nType=oneshot\nExecStart={} run-original-once --config {} --config-sha256 {}\nRestart=on-failure\nRestartSec=5\nKillMode=control-group\nTimeoutStartSec=infinity\nTimeoutStopSec=120\nUMask=0077\nAmbientCapabilities=\nNoNewPrivileges=no\nStandardInput=null\n\n[Install]\nWantedBy=multi-user.target\n",
        c::ORIGINAL_KERNEL,
        a.intent.pin().path.display(),
        producer.path.display(),
        input.path.display(),
        input.sha256
    );
    let p = source(a, "ORIGINAL-OWNER.service", body.as_bytes())?;
    Ok(vec![
        regular(format!("/etc/systemd/system/{unit}"), p, 0o644),
        link(
            format!("/etc/systemd/system/multi-user.target.wants/{unit}"),
            format!("../{unit}"),
        ),
    ])
}

fn runtime_entries(a: &OriginalQualificationAuthority) -> Result<(Vec<Entry>, FilePin)> {
    let admitted = a.materials.admitted()?;
    let normal = &admitted["normal_initramfs"];
    let m = &normal["normal_materials"];
    let original = read(a.intent.pin())?;
    let monotonic = rustix::time::clock_gettime(rustix::time::ClockId::Monotonic);
    let installed_ns = u64::try_from(monotonic.tv_sec)?
        .checked_mul(1_000_000_000)
        .and_then(|n| n.checked_add(monotonic.tv_nsec as u64))
        .ok_or("monotonic installation overflow")?;
    let installation = json_source(
        a,
        "INSTALLATION.json",
        &json!({"schema":"droidloom-maintenance-installation-v1","release_id":m["public_release_id"],"root_uuid":c::ROOT_UUID,"original_entry":c::ORIGINAL_ENTRY,"original_kernel":c::ORIGINAL_KERNEL,"grub_cfg":original_grub_member(a,"/boot/grub/grub.cfg")?,"grubenv":original_grub_member(a,"/boot/grub/grubenv")?,"installed_monotonic_ns":installed_ns}),
    )?;
    let executable = a
        .materials
        .normal_host_file(c::RETURN_EXECUTABLE.trim_start_matches('/'))?;
    let maintenance = a
        .materials
        .normal_host_file(c::MAINTENANCE_EXECUTABLE.trim_start_matches('/'))?;
    let payload = |p: &FilePin| PayloadPin {
        bytes: p.bytes,
        sha256: p.sha256.clone(),
    };
    let policy = a
        .materials
        .mac_files()
        .into_iter()
        .find(|p| p.path.file_name().is_some_and(|s| s == "policy.bin"))
        .ok_or("normal five-file policy absent")?;
    let conf = ReturnConfiguration {
        schema: "droidloom.original-once-return.v1".into(),
        intent_sha256: a.intent.pin().sha256.clone(),
        candidate_id: a.candidate_id().into(),
        original_boot_id: string(&original, "original_boot_id")?.into(),
        original_kernel: c::ORIGINAL_KERNEL.into(),
        original_entry: c::ORIGINAL_ENTRY.into(),
        root_uuid: c::ROOT_UUID.into(),
        early_config_sha256: a.materials.early().sha256.clone(),
        admitted_materials_sha256: a.materials.report().sha256.clone(),
        joint_policy_sha256: policy.sha256.clone(),
        host_source_commit: string(normal, "host_source_commit")?.into(),
        host_source_tree: string(normal, "host_source_tree")?.into(),
        recovery: a.materials.recovery().clone(),
        executable: payload(&executable),
        maintenance: payload(&maintenance),
        installation: payload(&installation),
        cell: payload(a.new_cell.pin()),
        selection: payload(a.selection()),
    };
    conf.validate()?;
    let return_pin = json_source(a, "RETURN.json", &conf)?;
    let manager = a
        .materials
        .normal_host_file("usr/lib/droidloom/production/current/droidloomd")?;
    let launcher = json_source(
        a,
        "CONTAINER-LAUNCHER.json",
        &json!({"schema":"droidloom-public-early-launcher-v1","launcher":"early_boot_shared_kernel_v1","selection_sha256":a.selection().sha256,"manager_sha256":manager.sha256,"manager_bytes":manager.bytes}),
    )?;
    let mut entries = vec![
        regular("/etc/droidloom/cell.json", a.new_cell.pin().clone(), 0o644),
        regular("/etc/droidloom/container-launcher.json", launcher, 0o644),
        regular(c::INSTALLATION, installation, 0o400),
        regular(c::EARLY_CONFIG, a.materials.early().clone(), 0o400),
        regular(c::RETURN_CONFIG, return_pin.clone(), 0o400),
    ];
    for p in a.materials.mac_files() {
        entries.push(regular(
            Path::new("/etc/droidloom/host-mac").join(p.path.file_name().ok_or("MAC member")?),
            p.clone(),
            0o400,
        ));
    }
    for name in [
        "droidloom-manager-label.service",
        "droidloom-instance-factory.service",
        "droidloom-instance-launcher.service",
        "droidloom-production.service",
        "droidloom-early-observer.service",
    ] {
        entries.push(regular(
            format!("/etc/systemd/system/{name}"),
            a.materials
                .normal_host_file(&format!("usr/share/droidloom/production/{name}"))?,
            0o644,
        ));
    }
    for name in [
        "droidloom-original-once.target",
        "droidloom-original-once-return.service",
        "droidloom-original-once-return.timer",
    ] {
        entries.push(regular(
            format!("/etc/systemd/system/{name}"),
            a.materials
                .normal_host_file(&format!("usr/share/droidloom/production/{name}"))?,
            0o644,
        ));
    }
    let presenter = a
        .materials
        .normal_host_file("usr/lib/systemd/user/droidloom-production-desktop.service")?;
    let body = String::from_utf8(files::read_pin(&presenter, 65536)?)?;
    ensure(
        body.lines().filter(|s| *s == "ConditionUser=1000").count() == 1
            && body
                .lines()
                .any(|s| s == "WantedBy=graphical-session.target"),
        "actual normal presenter must be confined to the authenticated UID1000 graphical session",
    )?;
    entries.push(link(
        "/etc/systemd/user/graphical-session.target.wants/droidloom-production-desktop.service",
        "/usr/lib/systemd/user/droidloom-production-desktop.service",
    ));
    let evidence = conf.runtime_evidence_directory();
    entries.push(regular(
        evidence.join("owner.lock"),
        source(a, "EMPTY-RUNTIME-LOCK", b"")?,
        0o400,
    ));
    Ok((entries, return_pin))
}

fn grub_entries(a: &OriginalQualificationAuthority, return_pin: &FilePin) -> Result<Vec<Entry>> {
    let old = Path::new("/boot/grub/custom.cfg");
    let mut bytes = match std::fs::symlink_metadata(old) {
        Ok(_) => {
            let p = files::pin_file(old)?;
            let (f, id) = files::open_pin(&p)?;
            ensure(
                id.uid == 0
                    && id.gid == 0
                    && id.nlink == 1
                    && id.mode & 0o022 == 0
                    && fs::xattrs(&f)?.keys().all(|k| k == "security.selinux"),
                "original custom GRUB file custody",
            )?;
            files::read_pin(&p, 1024 * 1024)?
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Vec::new(),
        Err(e) => return Err(e.into()),
    };
    let text = std::str::from_utf8(&bytes)?;
    ensure(
        !text.contains("droidloom-original-once-"),
        "an original once GRUB entry already exists",
    )?;
    let id = a.candidate_id();
    let args = format!(
        "root=UUID={} ro rootwait init=/usr/lib/droidloom/board-init lsm=lockdown,capability,landlock,yama,selinux,apparmor,bpf,ima,evm enforcing=1 selinux=1 audit=1 panic=10 systemd.unit=droidloom-original-once.target droidloom.once={} droidloom.once.config={} droidloom.once.return={}{}",
        c::ROOT_UUID,
        a.intent.pin().sha256,
        a.materials.early().sha256,
        return_pin.sha256,
        c::PACKAGE_WRITERS
            .iter()
            .chain(c::SUSPEND_TARGETS.iter())
            .map(|s| format!(" systemd.mask={s}"))
            .collect::<String>()
    );
    c::boot_arguments(&args)?;
    let entry = format!(
        "\nmenuentry 'Droidloom controlled original qualification' --id 'droidloom-original-once-{id}' {{\n  search --no-floppy --fs-uuid --set=root {}\n  linux /boot/droidloom/kernels/{}/vmlinuz {args}\n  initrd /boot/droidloom/qualification/{id}/initrd.img\n}}\n",
        c::ROOT_UUID,
        c::KERNEL_SHA
    );
    // Existing normal grub.cfg loads custom.cfg and already defaults to the
    // exact original kernel. Do not introduce a second save_env mechanism.
    bytes.extend_from_slice(entry.as_bytes());
    let p = source(a, "CUSTOM-GRUB.cfg", &bytes)?;
    Ok(vec![regular(old, p, 0o644)])
}

fn forward(a: Rc<OriginalQualificationAuthority>) -> Result<Value> {
    let initrd = prepare_recovery(&a)?;
    let owner = publish(&a, "owner", owner_entries(&a)?)?;
    ctl(&a, &["daemon-reload"])?;
    let writers = command(
        &a,
        "package-writers-stop",
        json!({"units":c::PACKAGE_WRITERS}),
        180,
    )?;
    save(
        &a.work().join("PACKAGE-WRITERS.json"),
        &json!({"intent":a.intent.pin(),"source":writers.pin,"actual":writers.report}),
    )?;
    let masks = publish(
        &a,
        "package-masks",
        c::PACKAGE_WRITERS
            .iter()
            .chain(c::SUSPEND_TARGETS.iter())
            .map(|s| link(format!("/etc/systemd/system/{s}"), "/dev/null"))
            .collect(),
    )?;
    ctl(&a, &["daemon-reload"])?;
    let public = command(&a, "public-snapshot", json!({}), 180)?;
    event(
        &a,
        Phase::PublicInstallIntent,
        json!({"normal_snapshot":public.pin,"actual":public.report,"owner_configuration":owner}),
    )?;
    let public = command(
        &a,
        "public-apply",
        json!({"snapshot":public.report["snapshot"]}),
        600,
    )?;
    event(
        &a,
        Phase::PublicInstalled,
        json!({"normal_transaction":public.pin,"actual":public.report}),
    )?;
    let native = command(&a, "native-snapshot", json!({}), 180)?;
    let native_snapshot = pin(&native.report["snapshot"])?;
    let attempt = string(&native.report, "attempt")?;
    let name = next_command_name(&a, "native-apply")?;
    let parents = package_parents::capture(
        &a,
        NativeOperation::Install,
        &native_snapshot,
        attempt,
        &name,
        None,
    )?;
    event(
        &a,
        Phase::NativeInstallIntent,
        json!({"normal_snapshot":native.pin,"actual":native.report,"parent_preimage":parents.before_pin(),"command_name":name}),
    )?;
    let native = commands::call(
        &a,
        &name,
        "native-apply",
        json!({"snapshot":native_snapshot,"attempt":attempt}),
        600,
    )?;
    let changes = parents.finish(&a, &native)?;
    event(
        &a,
        Phase::NativeInstalled,
        json!({"normal_transaction":native.pin,"actual":native.report,"package_parent_changes":changes.pin()}),
    )?;
    event(
        &a,
        Phase::CellPublishIntent,
        json!({"candidate_cell":a.new_cell.pin(),"selection":a.selection()}),
    )?;
    let (entries, return_pin) = runtime_entries(&a)?;
    let runtime = publish(&a, "runtime", entries)?;
    event(
        &a,
        Phase::CellPublished,
        json!({"runtime":runtime,"masks":masks,"candidate_cell":a.expected_cell(),"return_configuration":return_pin}),
    )?;
    let data = OriginalDataTransaction::prepare(&a, a.cold_clone.pin())?;
    a.bind_pair_intent(data.intent())?;
    event(
        &a,
        Phase::PairExchangeIntent,
        json!({"pair_intent":data.intent()}),
    )?;
    let exchange = data.exchange(&a)?;
    event(&a, Phase::PairExchanged, exchange)?;
    event(
        &a,
        Phase::RecoveryInstallIntent,
        json!({"normal_initrd":initrd}),
    )?;
    let recovery = publish(
        &a,
        "recovery",
        vec![regular(
            format!(
                "/boot/droidloom/qualification/{}/initrd.img",
                a.candidate_id()
            ),
            initrd,
            0o400,
        )],
    )?;
    event(&a, Phase::RecoveryInstalled, recovery)?;
    event(
        &a,
        Phase::GrubPublishIntent,
        json!({"original_grub":read(a.intent.pin())?["original_grub"]}),
    )?;
    let actual_grub = publish(&a, "grub", grub_entries(&a, &return_pin)?)?;
    event(&a, Phase::GrubPublished, actual_grub)?;
    let frozen = Quiescence::begin(&a)?;
    let mut labels = cold_original_data::labels::OriginalLabelTransaction::prepare(
        &a,
        a.label_sources()?,
        &data,
    )?;
    a.begin_labels(labels.source_plan())?;
    let window = OriginalLabelWindow::open(&a, &frozen)?;
    let applied = labels.apply(&a, &data, &window)?;
    window.finish()?;
    event(
        &a,
        Phase::LabelsApplied,
        json!({"source_plan":applied.source_plan(),"actual":applied.report()}),
    )?;
    event(
        &a,
        Phase::SelectionPublishIntent,
        json!({"selection":a.selection(),"labels":applied.report()}),
    )?;
    let selection = data.publish_selection(&a, &applied)?;
    event(&a, Phase::SelectionPublished, selection)?;
    applied.verify_published(&a, &data)?;
    frozen.finish()?;
    let before = grub(&a, "grub-read")?;
    ensure(
        before.report["after_fields"]
            .get("next_entry")
            .is_none_or(|v| v == ""),
        "a next boot was already selected",
    )?;
    event(
        &a,
        Phase::ArmIntent,
        json!({"actual_prearm":before.pin,"source_plan":applied.source_plan(),"labels":applied.report()}),
    )?;
    let armed = grub(&a, "grub-arm")?;
    event(
        &a,
        Phase::Armed,
        json!({"actual_grub":armed.pin,"actual":armed.report}),
    )?;
    let reboot = ctl(&a, &["--no-block", "reboot"])?;
    event(
        &a,
        Phase::RebootRequested,
        json!({"normal_request":reboot.pin,"completed":false}),
    )?;
    // A request is not shutdown proof. The independent original unit remains
    // the live lock owner until PID1 terminates it during the real shutdown.
    for _ in 0..90 {
        a.owner.borrow().revalidate()?;
        std::thread::sleep(std::time::Duration::from_secs(1));
    }
    Err("original reboot request did not retire its live owner within the normal deadline".into())
}

fn recover(a: Rc<OriginalQualificationAuthority>, cause: Option<&str>) -> Result<Value> {
    a.verify_current_owner()?;
    if phase(&a)? == Phase::Returned {
        return observation(&a, Phase::Returned)?.ok_or("returned evidence absent".into());
    }
    // Cover ArmIntent -> real grub mutation -> crash before Armed. Clearing a
    // real owned next_entry is proved before the unbooted factory demands empty.
    let disarm = grub(&a, "grub-disarm")?;
    let admitted = read(a.intent.pin())?;
    let same_boot = admitted["original_boot_id"] == a.owner.borrow().boot_id();
    let p = phase(&a)?;
    if matches!(p, Phase::ArmIntent | Phase::Armed | Phase::RebootRequested) && !same_boot {
        event(
            &a,
            Phase::OriginalReturned,
            json!({"actual_owner":a.owner.borrow().evidence(),"actual_disarm":disarm.pin,"qualification_accepted":false}),
        )?;
    } else if !matches!(
        p,
        Phase::OriginalReturned
            | Phase::SelectionWithdrawIntent
            | Phase::Aborting
            | Phase::SelectionWithdrawn
            | Phase::PairRestored
            | Phase::LabelsRestored
            | Phase::CellRestoreIntent
            | Phase::CellRestored
            | Phase::NativeRestored
            | Phase::PublicRestored
            | Phase::GrubRestored
    ) {
        event(
            &a,
            Phase::Aborting,
            json!({"actual_owner":a.owner.borrow().evidence(),"actual_disarm":disarm.pin,"cause":cause,"candidate_business_accepted":false}),
        )?;
    }
    // Reconstruct only the exact active interrupted package namespace. This
    // may observe a real completed RESULT whose phase acknowledgement was
    // interrupted, or record metadata-only partial work; it never invents a
    // successful dpkg transaction.
    configurations::native_parent_history(&a, NativeOperation::Install, true)?;
    configurations::native_parent_history(&a, NativeOperation::Rollback, true)?;
    let has_pair = matches!(*a.retirement.borrow(), RetirementSource::Prepared(_));
    let mut data = if has_pair {
        Some(OriginalDataTransaction::resume(&a)?)
    } else {
        None
    };
    let mut retirement = None;
    let mut restoration;
    let resume_configuration =
        observation(&a, Phase::CellRestoreIntent)?.or(observation(&a, Phase::LabelsRestored)?);
    if let Some(v) = resume_configuration {
        restoration = ConfigurationRestoration::reopen(&a, &pin(&v["configuration_source"])?)?;
        if phase(&a)? == Phase::LabelsRestored {
            event(
                &a,
                Phase::CellRestoreIntent,
                json!({"configuration_source":restoration.pin(),
                "actual_retirement":v["actual_retirement"],"package_preservation":v["package_preservation"],"labels_were_prepared":true}),
            )?;
        }
    } else {
        let mut preservation = None;
        if let Some(d) = data.as_mut() {
            if matches!(phase(&a)?, Phase::OriginalReturned | Phase::Aborting) {
                event(
                    &a,
                    Phase::SelectionWithdrawIntent,
                    json!({"pair_intent":d.intent(),"actual_disarm":disarm.pin}),
                )?;
            }
            if phase(&a)? == Phase::SelectionWithdrawIntent {
                let withdrawn = d.withdraw_selection(&a)?;
                event(&a, Phase::SelectionWithdrawn, withdrawn)?;
            }
            let r = retirement::prove(Rc::clone(&a), d)?;
            if phase(&a)? == Phase::SelectionWithdrawn {
                let restored = d.restore_pair(&r)?;
                restored.revalidate(&r, d)?;
                event(
                    &a,
                    Phase::PairRestored,
                    json!({"actual_pair_restoration":restored.report(),"actual_retirement":r.report_pin()}),
                )?;
            }
            if let Some(v) = observation(&a, Phase::LabelsIntent)? {
                let plan = pin(&v["label_plan"])?;
                let frozen = Quiescence::begin_restore(&r)?;
                let window = OriginalRestoreLabelWindow::open(&r, &frozen)?;
                let mut transaction =
                    cold_original_data::labels::OriginalLabelRestorationTransaction::resume(
                        &r, d, &plan,
                    )?;
                let restored = transaction.restore(d, &window)?;
                window.finish()?;
                restored.verify_complete(&r, d)?;
                restoration = ConfigurationRestoration::after_labels(&r, d, &restored)?;
                // A private typed bridge, not a replacement of the old package
                // SNAPSHOT. It records only actual source/current/restored
                // metadata for the existing fixed account/SSH/home contract.
                preservation = Some(configurations::seal_public_preservation(&r, d, &restored)?);
                // The finite label window includes all target readbacks and
                // sealed metadata derivations. Normal package reversal is a
                // separate real transaction; its writers stay stopped/masked.
                frozen.finish()?;
                // The durable completion includes all inputs needed for the
                // next stage. A crash here resumes these exact seals, rather
                // than attempting to mint a second retirement after completion.
                event(
                    &a,
                    Phase::LabelsRestored,
                    json!({"actual":restored.report(),"actual_retirement":r.report_pin(),
                    "configuration_source":restoration.pin(),"package_preservation":preservation}),
                )?;
            } else {
                ensure(
                    observation(&a, Phase::LabelsApplied)?.is_none(),
                    "label completion has no original plan",
                )?;
                restoration = ConfigurationRestoration::unlabelled(&a)?;
            }
            retirement = Some(r);
        } else {
            ensure(
                observation(&a, Phase::PairExchangeIntent)?.is_none()
                    && observation(&a, Phase::LabelsIntent)?.is_none()
                    && observation(&a, Phase::ArmIntent)?.is_none(),
                "zero-pair recovery has actual later side effects",
            )?;
            let initial = cold_original_data::assert_initial_pair_retired(a.cold_clone.pin())?;
            save(
                &a.work().join(format!(
                    "ZERO-PAIR-{}-{}.json",
                    a.owner.borrow().boot_id(),
                    a.owner.borrow().evidence()["actual_original"]["invocation_id"]
                        .as_str()
                        .ok_or("owner invocation")?
                )),
                &json!({"schema":"droidloom.original-once-zero-pair-recovery.v1","intent":a.intent.pin(),"actual_initial_pair":initial,"actual_disarm":disarm.pin,"candidate_boot_observed":false}),
            )?;
            restoration = ConfigurationRestoration::unlabelled(&a)?;
        }
        event(
            &a,
            Phase::CellRestoreIntent,
            json!({"configuration_source":restoration.pin(),"actual_retirement":retirement.as_ref().map(|r|r.report_pin()),"package_preservation":preservation,"labels_were_prepared":observation(&a,Phase::LabelsIntent)?.is_some()}),
        )?;
    }
    if phase(&a)? == Phase::CellRestoreIntent {
        configurations::archive_runtime_evidence(&a, &mut restoration)?;
        for group in ["grub", "recovery", "runtime"] {
            if let Some(c) = Configurations::reopen(&a, group)? {
                c.restore(&a, &mut restoration)?;
            }
        }
        ctl(&a, &["daemon-reload"])?;
        event(
            &a,
            Phase::CellRestored,
            json!({"actual_configurations":restoration.pin(),"original_cell":a.original_cell.pin()}),
        )?;
    }
    if phase(&a)? == Phase::CellRestored {
        let mut parent_effects = None;
        let actual = if let Some(v) = observation(&a, Phase::NativeInstallIntent)? {
            let prior =
                configurations::native_parent_history(&a, NativeOperation::Rollback, false)?;
            if let Some(last) = prior.last().filter(|v| v.is_completed_command()) {
                // The exact normal RESULT, stdout, terminal transaction event
                // and all original sources were reopened by Changes::reopen.
                parent_effects = Some(last.pin().clone());
                Some(pin(&read(last.pin())?["command_result"])?)
            } else {
                let n = &v["actual"];
                let snapshot = pin(&n["snapshot"])?;
                let attempt = string(n, "attempt")?;
                let apply =
                    configurations::native_parent_history(&a, NativeOperation::Install, false)?;
                let absent = match std::fs::symlink_metadata(
                    "/etc/systemd/system/display-manager.service",
                ) {
                    Ok(_) => false,
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => true,
                    Err(e) => return Err(e.into()),
                };
                let earlier = if absent {
                    prior.last().or_else(|| apply.last())
                } else {
                    None
                };
                let name = next_command_name(&a, "native-rollback")?;
                let parents = package_parents::capture(
                    &a,
                    NativeOperation::Rollback,
                    &snapshot,
                    attempt,
                    &name,
                    earlier,
                )?;
                let result = commands::call(
                    &a,
                    &name,
                    "native-rollback",
                    json!({"snapshot":snapshot,"attempt":attempt,"restored_metadata":configurations::public_preservation_pin(&a)?}),
                    600,
                )?;
                let changes = parents.finish(&a, &result)?;
                restoration.advance_native(&a, &changes)?;
                parent_effects = Some(changes.pin().clone());
                Some(result.pin)
            }
        } else {
            None
        };
        event(
            &a,
            Phase::NativeRestored,
            json!({"normal_rollback":actual,"package_parent_changes":parent_effects,"no_native_install_intent":actual.is_none()}),
        )?;
    }
    if phase(&a)? == Phase::NativeRestored {
        let actual = if let Some(v) = observation(&a, Phase::PublicInstallIntent)? {
            Some(command(&a,"public-rollback",json!({"snapshot":v["actual"]["snapshot"],"restored_metadata":configurations::public_preservation_pin(&a)?}),600)?.pin)
        } else {
            None
        };
        event(
            &a,
            Phase::PublicRestored,
            json!({"normal_rollback":actual,"no_public_install_intent":actual.is_none()}),
        )?;
    }
    if phase(&a)? == Phase::PublicRestored {
        if let Some(c) = Configurations::reopen(&a, "package-masks")? {
            c.restore(&a, &mut restoration)?;
        }
        ctl(&a, &["daemon-reload"])?;
        if let Some(v) = configurations::package_writers_preimage(&a)? {
            command(
                &a,
                "package-writers-restore",
                json!({"original":v,"units":c::PACKAGE_WRITERS}),
                180,
            )?;
        }
        // The sole recovery unit is the last public configuration removed.
        if let Some(c) = Configurations::reopen(&a, "owner")? {
            c.restore(&a, &mut restoration)?;
        }
        ctl(&a, &["daemon-reload"])?;
        let actual = grub(&a, "grub-read")?;
        event(
            &a,
            Phase::GrubRestored,
            json!({"actual_original_grub":actual.pin,"owner_unit_removed_last":true}),
        )?;
    }
    let value = json!({"schema":"droidloom.original-once-completed.v1","intent":a.intent.pin(),"candidate_id":a.candidate_id(),"actual_original_owner":a.owner.borrow().evidence(),"retirement":retirement.as_ref().map(|r|r.report_pin()),"interrupted_cause":cause,"production_ready":false,"application_business_accepted":false,"permanent_default_changed":false});
    if phase(&a)? == Phase::GrubRestored {
        event(&a, Phase::Returned, value.clone())?;
    }
    ensure(
        phase(&a)? == Phase::Returned,
        "recovery did not reach its actual terminal state",
    )?;
    Ok(value)
}

pub(super) fn run(input: &Path, expected: &str) -> Result<Value> {
    ensure(fs::valid_digest(expected), "once input digest required")?;
    let p = files::pin_file(input)?;
    ensure(p.sha256 == expected, "once input bytes differ")?;
    let seal = SealedInput::open(&p)?;
    let raw: Value = serde_json::from_slice(&seal.read()?)?;
    ensure(
        raw["schema"] == "droidloom.original-once-plan.v1",
        "once input schema differs",
    )?;
    let candidate = string(&raw, "candidate_id")?;
    ensure(
        fs::valid_digest(candidate),
        "once candidate is not a digest",
    )?;
    let path = Path::new("/var/lib/droidloom-qualification")
        .join(format!("original-once-{candidate}/INTENT.json"));
    materials::retire_unadmitted(&p)?;
    if path.exists() {
        let intent_pin = files::pin_file(&path)?;
        let a = materials::resume(&intent_pin)?;
        let admitted = a.materials.admitted()?;
        ensure(
            admitted["input"] == serde_json::to_value(&p)?,
            "resume input is not the original sealed preparation",
        )?;
        seal.revalidate()?;
        return recover(a, None);
    }
    let a = materials::admit(&p)?;
    seal.revalidate()?;
    match forward(Rc::clone(&a)) {
        Ok(v) => Ok(v),
        Err(error) => {
            let text = error.to_string();
            match recover(a,Some(&text)) {
                Ok(v)=>Err(format!("original once forward action failed: {text}; actual original restoration: {}",serde_json::to_string(&v)?).into()),
                Err(restoration)=>Err(format!("original once forward action failed: {text}; durable restoration remains incomplete: {restoration}").into()),
            }
        }
    }
}

#[cfg(test)]
mod dispatch_history_tests {
    use super::*;
    #[test]
    fn actual_mixed_command_directories_keep_dispatch_ordinals_and_reject_unknown_members()
    -> Result<()> {
        let root = tempfile::tempdir()?;
        for n in ["commands", "native-package-parents"] {
            std::fs::create_dir(root.path().join(n))?;
        }
        let invocation = "a".repeat(32);
        let boot = "12345678-1234-1234-1234-123456789abc";
        for name in [
            "dispatch-0000-public-snapshot".into(),
            "dispatch-0007-native-apply".into(),
            format!("label-writer-inventory-forward-{invocation}"),
            format!("label-thaw-guard-start-forward-{invocation}"),
            format!("label-writer-inventory-restore-{invocation}"),
            format!("label-thaw-guard-start-restore-{invocation}"),
            format!("retirement-{boot}-{invocation}-grub"),
            format!("retirement-{boot}-{invocation}-journal"),
        ] {
            std::fs::create_dir(root.path().join("commands").join(name))?;
        }
        std::fs::create_dir(
            root.path()
                .join("native-package-parents/dispatch-0009-native-rollback"),
        )?;
        assert_eq!(
            next_command_name_in(root.path(), "grub-read")?,
            "dispatch-0010-grub-read"
        );
        for name in [
            "foreign",
            "label-writer-inventory-unknown-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "label-thaw-guard-start-forward-aaaa",
            "retirement-not-a-uuid-grub",
            "dispatch-4096-systemctl",
        ] {
            let p = root.path().join("commands").join(name);
            std::fs::create_dir(&p)?;
            assert!(
                next_command_name_in(root.path(), "grub-read").is_err(),
                "{name}"
            );
            std::fs::remove_dir(p)?;
        }
        let name = format!("label-writer-inventory-forward-{invocation}");
        let p = root.path().join("native-package-parents").join(&name);
        std::fs::create_dir(&p)?;
        assert!(next_command_name_in(root.path(), "grub-read").is_err());
        std::fs::remove_dir(p)?;
        let p = root.path().join("commands/dispatch-0012-systemctl");
        std::os::unix::fs::symlink(
            root.path().join("commands/dispatch-0000-public-snapshot"),
            &p,
        )?;
        assert!(next_command_name_in(root.path(), "grub-read").is_err());
        Ok(())
    }
}
