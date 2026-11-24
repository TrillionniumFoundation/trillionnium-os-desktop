use crate::{
    Result,
    boot_files::{self, FilePin},
    boot_native::{self, NativeInputs},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NativePlan {
    pub schema: String,
    pub work_directory: PathBuf,
    pub fixture_manifest: FilePin,
    pub fixture_root: PathBuf,
    pub native: NativeInputs,
}

pub fn create_work(path: &Path) -> Result<()> {
    ensure(
        path.parent() == Some(Path::new("/var/lib/droidloom-qualification")),
        "qualification work must be a direct child of the protected qualification directory",
    )?;
    let name = path
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("invalid work name")?;
    ensure(
        !name.is_empty()
            && name.len() <= 96
            && name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b)),
        "invalid work name",
    )?;
    let parent = fs::Tree::open("/var/lib/droidloom-qualification", 0)?;
    rustix::fs::mkdirat(&parent.root, name, rustix::fs::Mode::from_raw_mode(0o700))?;
    let fresh = fs::Tree::open(&fs::absolute_string(path)?, 0)?;
    ensure(
        fs::stat(&fresh.root)?.mode & 0o7777 == 0o700,
        "fresh work directory is not private",
    )
}

pub fn prepare_native(config: &Path, expected_sha: &str) -> Result<()> {
    let plan: NativePlan = fs::read_json(&fs::absolute_string(config)?, expected_sha)?;
    ensure(
        plan.schema == "droidloom.ubuntu-native-boot-plan.v1",
        "unsupported native boot plan",
    )?;
    ensure(
        plan.fixture_root.is_absolute() && plan.fixture_root != Path::new("/"),
        "fixture must be an independent materialized root",
    )?;
    create_work(&plan.work_directory)?;
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("INPUTS.json"))?,
        &plan,
        0,
    )?;
    let root = plan.work_directory.join("root");
    let clone = boot_files::clone_materialized(&plan.fixture_manifest, &plan.fixture_root, &root)?;
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("PUBLIC-CLONE.json"))?,
        &clone,
        0,
    )?;
    let initialized = boot_native::initialize(&root, &plan.work_directory, &plan.native)?;
    let receipt = serde_json::json!({
        "schema":"droidloom.ubuntu-native-prepared.v1",
        "input_sha256":expected_sha,
        "work_directory":plan.work_directory,
        "root":root,
        "root_identity":fs::stat(&fs::Tree::open(&fs::absolute_string(&root)?,0)?.root)?,
        "fixture_manifest":plan.fixture_manifest,
        "root_filesystem_uuid":plan.native.root_filesystem_uuid,
        "network_connection_uuid":plan.native.network_connection_uuid,
        "native_initialization":initialized,
        "guest_qualified":false,
        "production_ready":false,
        "next_required":"Install the normal selected host/Android release, build the ordinary initramfs layer, label using the selected joint policy, and boot the shared kernel with enforcing SELinux and AppArmor."
    });
    let path = plan.work_directory.join("NATIVE-PREPARED.json");
    let sha = fs::write_json(&fs::absolute_string(&path)?, &receipt, 0)?;
    println!(
        "{}",
        serde_json::json!({"receipt":path,"sha256":sha,"guest_qualified":false,"production_ready":false})
    );
    Ok(())
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BootPlan {
    pub schema: String,
    pub native_receipt: FilePin,
    pub host_manifest: FilePin,
    pub host_archive: FilePin,
    pub kernel: FilePin,
    pub base_initrd: FilePin,
    pub replacement_kernel: Option<crate::boot_kernel::KernelMaterial>,
    pub android: crate::boot_release::AndroidInputs,
    pub label_tools: crate::boot_runtime::LabelTools,
    pub root_image_gib: u64,
}

fn board_devices(root: &Path) -> Result<()> {
    let declaration = root.join("usr/share/droidloom/board/ubuntu-real-root-devices");
    let pin = boot_files::pin_file(&declaration)?;
    let bytes = boot_files::read_pin(&pin, 65536)?;
    let text = std::str::from_utf8(&bytes)?;
    let base = "/usr/lib/droidloom/production/current/board-devices";
    let mut entries = std::collections::BTreeMap::new();
    for line in text
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty() && !s.starts_with('#'))
    {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure(
            fields.len() == 7 && fields[1] == "c" && fields[3] == "0" && fields[4] == "0",
            "unexpected normal board device declaration",
        )?;
        let name = Path::new(fields[0])
            .file_name()
            .and_then(|v| v.to_str())
            .ok_or("invalid board node")?;
        ensure(
            Path::new(fields[0]).parent() == Some(Path::new(base.trim_start_matches('/'))),
            "normal board node is outside its protected source directory",
        )?;
        ensure(
            entries
                .insert(
                    name.to_owned(),
                    (
                        u32::from_str_radix(fields[2], 8)?,
                        fields[5].parse::<u32>()?,
                        fields[6].parse::<u32>()?,
                    ),
                )
                .is_none(),
            "duplicate board device",
        )?;
    }
    ensure(
        entries
            == std::collections::BTreeMap::from([
                ("console".into(), (0o600, 5, 1)),
                ("null".into(), (0o666, 1, 3)),
                ("full".into(), (0o666, 1, 7)),
            ]),
        "normal board standard-device set differs",
    )?;
    boot_files::ensure_dir(root, base, 0o755)?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let parent = tree.dir(base)?;
    for (name, (mode, major, minor)) in entries {
        rustix::fs::mknodat(
            &parent,
            name.as_str(),
            rustix::fs::FileType::CharacterDevice,
            rustix::fs::Mode::from_raw_mode(mode),
            rustix::fs::makedev(major, minor),
        )?;
        rustix::fs::chmodat(
            &parent,
            name.as_str(),
            rustix::fs::Mode::from_raw_mode(mode),
            rustix::fs::AtFlags::empty(),
        )?;
        let s = rustix::fs::statat(
            &parent,
            name.as_str(),
            rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
        )?;
        ensure(
            s.st_uid == 0
                && s.st_gid == 0
                && s.st_mode & 0o7777 == mode
                && s.st_rdev == rustix::fs::makedev(major, minor),
            "fresh board node metadata differs",
        )?;
    }
    Ok(())
}

pub fn prepare_boot(config: &Path, expected: &str) -> Result<()> {
    let plan: BootPlan = fs::read_json(&fs::absolute_string(config)?, expected)?;
    ensure(
        plan.schema == "droidloom.full-ubuntu-boot-plan.v1",
        "unsupported full boot plan",
    )?;
    let native: serde_json::Value = serde_json::from_slice(&boot_files::read_pin(
        &plan.native_receipt,
        4 * 1024 * 1024,
    )?)?;
    ensure(
        native["schema"] == "droidloom.ubuntu-native-prepared.v1"
            && native["guest_qualified"] == false
            && native["production_ready"] == false,
        "native receipt must describe an unbooted prepared fixture",
    )?;
    let work = PathBuf::from(
        native["work_directory"]
            .as_str()
            .ok_or("native work absent")?,
    );
    let root = PathBuf::from(native["root"].as_str().ok_or("native root absent")?);
    ensure(
        work.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && root == work.join("root"),
        "native root is outside protected qualification work",
    )?;
    let enclosing = fs::Tree::open(&fs::absolute_string(&work)?, 0)?;
    ensure(
        fs::stat(&enclosing.root)?.mode & 0o777 == 0o700,
        "native work is no longer private",
    )?;
    let root_tree = fs::Tree::open(&fs::absolute_string(&root)?, 0)?;
    let identity: crate::model::Identity = serde_json::from_value(native["root_identity"].clone())?;
    ensure(
        fs::stat(&root_tree.root)? == identity,
        "native root identity changed before release admission",
    )?;
    let original_pin: FilePin = serde_json::from_value(native["fixture_manifest"].clone())?;
    let original: crate::model::Manifest =
        serde_json::from_slice(&boot_files::read_pin(&original_pin, 128 * 1024 * 1024)?)?;
    let old_kernel = original
        .kernel
        .as_ref()
        .ok_or("original fixture lacks target kernel binding")?;
    let boot = work.join("boot");
    boot_files::private_dir(&boot)?;
    fs::write_json(
        &fs::absolute_string(&boot.join("BOOT-INPUTS.json"))?,
        &plan,
        0,
    )?;
    let (kernel_report, release) = if let Some(replacement) = &plan.replacement_kernel {
        ensure(
            replacement.image.sha256 == plan.kernel.sha256
                && replacement.image.bytes == plan.kernel.bytes
                && replacement.normal_initrd.sha256 == plan.base_initrd.sha256
                && replacement.normal_initrd.bytes == plan.base_initrd.bytes,
            "candidate kernel/initrd inputs disagree",
        )?;
        let result = crate::boot_kernel::install(
            &root,
            &boot,
            &original.target_kernel_release,
            replacement,
        )?;
        let release = result["target_kernel_release"]
            .as_str()
            .ok_or("candidate release absent")?
            .to_owned();
        (result, release)
    } else {
        ensure(
            plan.kernel.sha256 == old_kernel.binding.image_sha256
                && plan.kernel.bytes == old_kernel.image_identity.size,
            "original kernel image does not match complete selected modules",
        )?;
        (
            serde_json::json!({"original_kernel_binding":old_kernel}),
            original.target_kernel_release,
        )
    };
    let host = crate::boot_host::install(&root, &boot, &plan.host_manifest, &plan.host_archive)?;
    for path in [
        "usr/bin/droidloomctl",
        "usr/bin/droidloom-wayland",
        "usr/bin/droidloom-applications",
        "usr/bin/droidloom-doctor",
    ] {
        let (parent, name) = fs::absolute_parent(&fs::absolute_string(&root.join(path))?)?;
        let s = rustix::fs::statat(
            &parent,
            name.as_str(),
            rustix::fs::AtFlags::SYMLINK_NOFOLLOW,
        )?;
        ensure(
            rustix::fs::FileType::from_raw_mode(s.st_mode) == rustix::fs::FileType::RegularFile
                && s.st_nlink == 1
                && s.st_uid == 0
                && s.st_mode & 0o7777 == 0o755,
            "normal host release lacks a complete public desktop executable",
        )?;
    }
    let android = crate::boot_release::install_android(&root, &boot, &plan.android)?;
    let unit = "droidloom-production-desktop.service";
    let installed = root.join(format!("usr/lib/systemd/user/{unit}"));
    if std::fs::symlink_metadata(&installed)
        .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound)
    {
        let template = root.join(format!("usr/share/droidloom/production/{unit}"));
        let pin = boot_files::pin_file(&template)?;
        boot_files::ensure_dir(&root, "/usr/lib/systemd/user", 0o755)?;
        boot_files::copy_pin(&pin, &installed, 0o644)?;
    }
    boot_files::run_logged(
        &boot,
        "enable-production-desktop",
        "/usr/bin/systemctl",
        &[
            "--root".into(),
            root.to_string_lossy().into(),
            "--global".into(),
            "enable".into(),
            unit.into(),
        ],
        30,
    )?;
    let journal_gid = native["native_initialization"]["accounts"]["groups"]["systemd-journal"]
        .as_u64()
        .ok_or("native journal group missing")?;
    persistent_journal(&root, &boot, u32::try_from(journal_gid)?)?;
    board_devices(&root)?;
    let kernel = boot.join("vmlinuz");
    boot_files::copy_pin(&plan.kernel, &kernel, 0o400)?;
    let initrd = crate::boot_runtime::build_initrd(&root, &boot, &plan.base_initrd)?;
    let labels = crate::boot_runtime::label_root(&root, &boot, &plan.label_tools)?;
    let uuid = native["root_filesystem_uuid"]
        .as_str()
        .ok_or("native root UUID absent")?;
    let disk =
        crate::boot_runtime::make_root_image(&root, &boot, uuid, plan.root_image_gib, &labels)?;
    let result = serde_json::json!({"schema":"droidloom.full-ubuntu-boot-prepared.v1",
        "input_sha256":expected,"native_receipt":plan.native_receipt,"work_directory":work,
        "boot_directory":boot,"root_filesystem_uuid":uuid,"target_kernel_release":release,
        "kernel":boot_files::pin_file(&kernel)?,"initrd":initrd,"root_image":disk,
        "kernel_admission":kernel_report,"host_release":host,"android_release":android,
        "labels":boot_files::pin_file(&boot.join("ROOT-LABELS.json"))?,
        "calibration_requested":plan.android.calibrate,"guest_qualified":false,"production_ready":false});
    let path = boot.join("BOOT-PREPARED.json");
    let sha = fs::write_json(&fs::absolute_string(&path)?, &result, 0)?;
    println!(
        "{}",
        serde_json::json!({"receipt":path,"sha256":sha,"guest_qualified":false,"production_ready":false})
    );
    Ok(())
}

fn persistent_journal(root: &Path, work: &Path, gid: u32) -> Result<serde_json::Value> {
    ensure(
        gid > 0 && gid < 1000,
        "journal group must be the admitted native service group",
    )?;
    let log_path = root.join("var/log");
    let (var, log_name) = fs::absolute_parent(&fs::absolute_string(&log_path)?)?;
    match rustix::fs::mkdirat(
        &var,
        log_name.as_str(),
        rustix::fs::Mode::from_raw_mode(0o755),
    ) {
        Ok(()) => (),
        Err(e) if e == rustix::io::Errno::EXIST => (),
        Err(e) => return Err(e.into()),
    }
    let logs = std::fs::File::from(rustix::fs::openat(
        &var,
        log_name.as_str(),
        rustix::fs::OFlags::RDONLY
            | rustix::fs::OFlags::DIRECTORY
            | rustix::fs::OFlags::NOFOLLOW
            | rustix::fs::OFlags::CLOEXEC,
        rustix::fs::Mode::empty(),
    )?);
    let before = fs::stat(&logs)?;
    ensure(
        before.uid == 0 && before.mode & 0o002 == 0,
        "native log directory is untrusted or world writable",
    )?;
    match rustix::fs::mkdirat(&logs, "journal", rustix::fs::Mode::from_raw_mode(0o700)) {
        Ok(()) => (),
        Err(e) if e == rustix::io::Errno::EXIST => (),
        Err(e) => return Err(e.into()),
    }
    let journal = std::fs::File::from(rustix::fs::openat(
        &logs,
        "journal",
        rustix::fs::OFlags::RDONLY
            | rustix::fs::OFlags::DIRECTORY
            | rustix::fs::OFlags::NOFOLLOW
            | rustix::fs::OFlags::CLOEXEC,
        rustix::fs::Mode::empty(),
    )?);
    ensure(
        fs::stat(&journal)?.uid == 0,
        "native journal directory has an unexpected owner",
    )?;
    let mut listing = rustix::fs::Dir::read_from(&journal)?;
    for entry in &mut listing {
        let entry = entry?;
        let name = entry.file_name().to_str()?;
        ensure(
            name == "." || name == "..",
            "fresh fixture unexpectedly contains previous native journals",
        )?;
    }
    rustix::fs::fchown(
        &journal,
        Some(rustix::process::Uid::from_raw(0)),
        Some(rustix::process::Gid::from_raw(gid)),
    )?;
    rustix::fs::fchmod(&journal, rustix::fs::Mode::from_raw_mode(0o2755))?;
    rustix::fs::fsync(&journal)?;
    boot_files::ensure_dir(root, "/etc/systemd/journald.conf.d", 0o755)?;
    let config = root.join("etc/systemd/journald.conf.d/99-droidloom-qualification.conf");
    boot_files::write_new(&config,b"[Journal]\nStorage=persistent\nSyncIntervalSec=1s\nSystemMaxUse=256M\nRuntimeMaxUse=64M\n",0o644)?;
    let result = serde_json::json!({"configuration":boot_files::pin_file(&config)?,
        "journal_directory":fs::stat(&journal)?,"original_journald_unit_modified":false,
        "fresh_journal_empty":true,"guest_qualified":false});
    fs::write_json(
        &fs::absolute_string(&work.join("JOURNAL-CONFIGURATION.json"))?,
        &result,
        0,
    )?;
    Ok(result)
}
