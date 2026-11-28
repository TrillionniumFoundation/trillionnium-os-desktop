//! Normal create-exclusive independent EMPTY producer. No source data image is
//! accepted or opened. Complete initial bytes are checked against the shared
//! source recipe before this value can be returned.
use crate::{
    Result,
    boot_files::{self, FilePin},
    empty_meituan_contract as contract, ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::{Read, Seek},
    os::fd::AsRawFd,
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Inputs {
    pub official_apk: FilePin,
}

#[derive(Serialize)]
pub struct RunBudget {
    pub observation_seconds: u64,
    pub shutdown_seconds: u64,
    source_unit_seconds: Value,
}

fn unit_seconds(unit: &str, key: &str) -> Result<u64> {
    let values = unit
        .lines()
        .filter_map(|line| line.strip_prefix(key))
        .collect::<Vec<_>>();
    ensure(
        values.len() == 1,
        "normal diagnostic timeout must have exactly one source definition",
    )?;
    let raw = values[0].strip_suffix('s').unwrap_or(values[0]);
    let seconds = raw.parse::<u64>()?;
    ensure(
        (1..=1800).contains(&seconds),
        "normal diagnostic timeout is outside its bounded seconds contract",
    )?;
    Ok(seconds)
}

/// Fixed diagnostic observation allowance derived from the normal unit sources.
/// It does not extend the client's single deadline or prove service readiness.
pub fn run_budget() -> Result<RunBudget> {
    let diagnostic = include_str!(
        "../../../packaging/systemd/system/droidloom-empty-meituan-diagnostic.service"
    );
    let manager =
        include_str!("../../../runtime/droidloom-supervisor/src/droidloom-manager-label.service");
    let factory = include_str!(
        "../../../runtime/droidloom-supervisor/src/droidloom-instance-factory.service"
    );
    let launcher = include_str!(
        "../../../runtime/droidloom-supervisor/src/droidloom-instance-launcher.service"
    );
    let observer =
        include_str!("../../../runtime/droidloom-supervisor/src/droidloom-early-observer.service");
    let broker =
        include_str!("../../../runtime/droidloom-supervisor/src/droidloom-production.service");
    let startup = [
        unit_seconds(manager, "TimeoutStartSec=")?,
        unit_seconds(factory, "TimeoutStartSec=")?,
        unit_seconds(launcher, "TimeoutStartSec=")?,
        unit_seconds(observer, "TimeoutStartSec=")?,
    ];
    let runtime = unit_seconds(diagnostic, "RuntimeMaxSec=")?;
    let stop = [
        unit_seconds(diagnostic, "TimeoutStopSec=")?,
        unit_seconds(observer, "TimeoutStopSec=")?,
        unit_seconds(broker, "TimeoutStopSec=")?,
        unit_seconds(launcher, "TimeoutStopSec=")?,
        unit_seconds(factory, "TimeoutStopSec=")?,
        unit_seconds(manager, "TimeoutStopSec=")?,
    ];
    Ok(RunBudget {
        observation_seconds: 120 + startup.iter().sum::<u64>() + runtime + stop[0] + 45,
        shutdown_seconds: stop.iter().sum::<u64>() + 40,
        source_unit_seconds: json!({"start_manager_factory_launcher_observer": startup,
            "diagnostic_runtime":runtime,"stop_diagnostic_observer_broker_launcher_factory_manager":stop,
            "native_startup_allowance":120,"report_margin":45,"shutdown_journal_margin":40}),
    })
}

pub struct CreatedImage {
    held: File,
    reader: File,
    identity: crate::model::Identity,
    pin: FilePin,
    command: Value,
}
impl CreatedImage {
    pub fn revalidate(&self) -> Result<()> {
        let (named, node) = boot_files::open_pin(&self.pin)?;
        ensure(
            node == self.identity
                && fs::stat(&self.held)? == self.identity
                && fs::stat(&self.reader)? == self.identity
                && fs::stat(&named)? == self.identity,
            "actual newly formatted EMPTY inode changed before installation",
        )
    }
    pub fn comparison(&self) -> Result<Value> {
        self.revalidate()?;
        Ok(
            json!({"pin":self.pin,"identity":self.identity,"normal_mkfs":self.command,
            "production_ready":false,"original_data_migration":false}),
        )
    }
}
fn retired(pidfd: &File) -> Result<bool> {
    let mut raw = String::new();
    File::open(format!("/proc/self/fdinfo/{}", pidfd.as_raw_fd()))?
        .take(8193)
        .read_to_string(&mut raw)?;
    ensure(
        raw.len() <= 8192,
        "owned EMPTY formatter pidfd record exceeds bound",
    )?;
    let values = raw
        .lines()
        .filter_map(|v| v.strip_prefix("Pid:").map(str::trim))
        .collect::<Vec<_>>();
    ensure(
        values.len() == 1,
        "owned EMPTY formatter pidfd has no exact PID observation",
    )?;
    Ok(values[0] == "-1")
}
pub fn create(work: &Path, path: &Path, role: usize) -> Result<CreatedImage> {
    let recipe = contract::IMAGES
        .get(role)
        .ok_or("fixed EMPTY role required")?;
    ensure(
        rustix::process::geteuid().is_root(),
        "normal EMPTY image producer must own root-private outputs",
    )?;
    let tool_pin = FilePin {
        path: "/usr/sbin/mke2fs".into(),
        bytes: contract::MKFS_BYTES,
        sha256: contract::MKFS_SHA256.into(),
    };
    let mut tool = boot_files::checked_file(&tool_pin)?;
    let tool_node = fs::stat(&tool)?;
    ensure(
        tool_node.uid == 0
            && tool_node.gid == 0
            && tool_node.mode == 0o100755
            && tool_node.nlink == 1,
        "normal reviewed EMPTY formatter identity differs",
    )?;
    let held = boot_files::new_file(path, 0o600)?;
    let initial = fs::stat(&held)?;
    ensure(
        initial.uid == 0
            && initial.gid == 0
            && initial.nlink == 1
            && initial.size == 0
            && initial.mode == 0o100600,
        "EMPTY producer requires this actual newly created root-private file",
    )?;
    held.set_len(recipe.bytes)?;
    held.sync_all()?;
    let before = fs::stat(&held)?;
    let log = boot_files::new_file(&work.join(format!("empty-mkfs-{}.log", recipe.name)), 0o600)?;
    let tool_path = format!("/proc/{}/fd/{}", std::process::id(), tool.as_raw_fd());
    let image_path = format!("/proc/{}/fd/{}", std::process::id(), held.as_raw_fd());
    let args = vec![
        "-q".into(),
        "-F".into(),
        "-t".into(),
        "ext4".into(),
        "-b".into(),
        "4096".into(),
        "-I".into(),
        "256".into(),
        "-m".into(),
        "0".into(),
        "-N".into(),
        recipe.inodes.to_string(),
        "-U".into(),
        recipe.uuid.into(),
        "-O".into(),
        contract::FEATURES.into(),
        "-E".into(),
        format!(
            "lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0,hash_seed={}",
            recipe.uuid
        ),
        image_path,
    ];
    let mut command = Command::new(&tool_path);
    command
        .args(&args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .env("E2FSPROGS_FAKE_TIME", contract::MKFS_TIME)
        .env("MKE2FS_CONFIG", "/dev/null")
        .stdin(Stdio::null())
        .stdout(Stdio::from(log.try_clone()?))
        .stderr(Stdio::from(log.try_clone()?));
    let mut child = crate::boot_child::OwnedChild::spawn(&mut command)?;
    let pidfd = File::from(rustix::process::pidfd_open(
        rustix::process::Pid::from_raw(i32::try_from(child.id())?)
            .ok_or("new formatter PID invalid")?,
        rustix::process::PidfdFlags::empty(),
    )?);
    let end = Instant::now() + Duration::from_secs(120);
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if Instant::now() >= end || log.metadata()?.len() > 65536 {
            child.stop_and_reap()?;
            ensure(
                retired(&pidfd)?,
                "timed out EMPTY formatter retirement unproven",
            )?;
            return Err(
                "EMPTY formatter deadline/output limit expired; no initial-generation proof issued"
                    .into(),
            );
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    ensure(
        retired(&pidfd)? && status.success(),
        "actual normal EMPTY formatter did not successfully retire",
    )?;
    tool.rewind()?;
    ensure(
        fs::stat(&tool)? == tool_node
            && fs::hash(&tool)? == tool_pin.sha256
            && fs::stat(&tool)? == tool_node,
        "held normal formatter changed across its actual child",
    )?;
    held.sync_all()?;
    let after = fs::stat(&held)?;
    ensure(
        (
            before.dev,
            before.ino,
            before.mode,
            before.uid,
            before.gid,
            before.nlink,
            before.size,
        ) == (
            after.dev,
            after.ino,
            after.mode,
            after.uid,
            after.gid,
            after.nlink,
            after.size,
        ),
        "normal formatter did not preserve its create-exclusive image inode",
    )?;
    let pin = FilePin {
        path: path.into(),
        bytes: recipe.bytes,
        sha256: recipe.sha256.into(),
    };
    let (reader, identity) = boot_files::open_pin(&pin)?;
    ensure(
        identity == after,
        "EMPTY readback does not hold the newly formatted inode",
    )?;
    contract::verify_initial_image(&reader, role, || Ok(()))?;
    let result = CreatedImage {
        held,
        reader,
        identity,
        pin,
        command: json!({"program":tool_pin,"argv":args,
        "exit_code":status.code(),"actual_owned_child_reaped":true,"actual_pidfd_retired":true,
        "environment":{"E2FSPROGS_FAKE_TIME":contract::MKFS_TIME,"MKE2FS_CONFIG":"/dev/null"}}),
    };
    result.revalidate()?;
    Ok(result)
}

pub fn install_original_apk(root: &Path, input: &Inputs) -> Result<Value> {
    ensure(
        input.official_apk.bytes == contract::APK_BYTES
            && input.official_apk.sha256 == contract::APK_SHA256,
        "independent EMPTY diagnostic accepts only the fixed unmodified official Meituan APK",
    )?;
    boot_files::ensure_dir(root, "/var/lib/droidloom-qualification", 0o700)?;
    boot_files::ensure_dir(root, contract::DIRECTORY, 0o700)?;
    let destination = boot_files::guest_path(root, contract::APK_PATH)?;
    let source = boot_files::copy_pin_with_identity(&input.official_apk, &destination, 0o400)?;
    let pin = FilePin {
        path: destination,
        bytes: contract::APK_BYTES,
        sha256: contract::APK_SHA256.into(),
    };
    let held = boot_files::checked_file(&pin)?;
    let node = fs::stat(&held)?;
    ensure(
        node.uid == 0 && node.gid == 0 && node.nlink == 1 && node.mode == 0o100400,
        "independent official APK publication lost root-private custody",
    )?;
    Ok(
        json!({"source":input.official_apk,"held_source_identity":source,"destination":pin,
        "destination_identity":node,"production_ready":false,"original_data_migration":false}),
    )
}

pub fn enable_fixed_diagnostic(root: &Path, work: &Path) -> Result<Value> {
    let unit_path = format!("/usr/lib/systemd/system/{}", contract::UNIT);
    let unit = boot_files::pin_file(&boot_files::guest_path(root, &unit_path)?)?;
    let original = include_bytes!(
        "../../../packaging/systemd/system/droidloom-empty-meituan-diagnostic.service"
    );
    ensure(
        boot_files::read_pin(&unit, 65536)? == original,
        "normal EMPTY unit is not the complete source-owned publication",
    )?;
    let held = boot_files::checked_file(&unit)?;
    let before = fs::stat(&held)?;
    ensure(
        before.uid == 0 && before.gid == 0 && before.mode == 0o100444 && before.nlink == 1,
        "normal EMPTY unit custody differs",
    )?;
    let link = format!(
        "/etc/systemd/system/graphical.target.wants/{}",
        contract::UNIT
    );
    let named = boot_files::guest_path(root, &link)?;
    ensure(
        std::fs::symlink_metadata(&named).is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
        "EMPTY scheduling is create-only in this independent root",
    )?;
    let command = boot_files::run_logged(
        work,
        "enable-empty-meituan-diagnostic",
        "/usr/bin/systemctl",
        &[
            "--root".into(),
            root.to_string_lossy().into(),
            "add-wants".into(),
            "graphical.target".into(),
            contract::UNIT.into(),
        ],
        30,
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let (identity, target) = tree.read_link(&link)?;
    ensure(
        identity.uid == 0
            && identity.gid == 0
            && crate::paths::normalize_link(&link, &target)? == unit_path
            && fs::stat(&held)? == before
            && boot_files::pin_file(&unit.path)?.sha256 == unit.sha256,
        "normal add-wants did not preserve the exact diagnostic unit and graphical target",
    )?;
    Ok(
        json!({"unit":unit,"command":command,"wants_path":link,"target":target,"identity":identity,
        "systemd_unit":"graphical.target","guest_started":false,"production_ready":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::FileExt;
    #[test]
    fn empty_meituan_budget_includes_normal_unit_dependencies_and_actual_retirement() -> Result<()>
    {
        let budget = run_budget()?;
        assert_eq!(budget.observation_seconds, 1560);
        assert_eq!(budget.shutdown_seconds, 480);
        assert!(
            unit_seconds(
                "TimeoutStartSec=30s\nTimeoutStartSec=60s",
                "TimeoutStartSec="
            )
            .is_err()
        );
        assert!(unit_seconds("TimeoutStartSec=infinity", "TimeoutStartSec=").is_err());
        Ok(())
    }
    #[test]
    #[ignore = "actual root-owned private systemctl --root fixture required"]
    fn empty_meituan_actual_fixed_graphical_add_wants_preserves_source_and_rejects_replay()
    -> Result<()> {
        ensure(
            rustix::process::geteuid().is_root(),
            "private normal enable gate requires root",
        )?;
        let directory = tempfile::Builder::new()
            .prefix("empty-meituan-enable-test-")
            .tempdir_in("/var/lib/droidloom-qualification")?;
        let root = directory.path().join("root");
        boot_files::private_dir(&root)?;
        boot_files::ensure_dir(&root, "/usr/lib/systemd/system", 0o755)?;
        let path = boot_files::guest_path(
            &root,
            &format!("/usr/lib/systemd/system/{}", contract::UNIT),
        )?;
        boot_files::write_new(
            &path,
            include_bytes!(
                "../../../packaging/systemd/system/droidloom-empty-meituan-diagnostic.service"
            ),
            0o444,
        )?;
        let target = boot_files::pin_file(Path::new("/usr/lib/systemd/system/graphical.target"))?;
        boot_files::copy_pin_with_identity(
            &target,
            &root.join("usr/lib/systemd/system/graphical.target"),
            0o644,
        )?;
        let result = match enable_fixed_diagnostic(&root, directory.path()) {
            Ok(value) => value,
            Err(error) => {
                let retained = directory.keep();
                let log =
                    std::fs::read_to_string(retained.join("enable-empty-meituan-diagnostic.log"))
                        .unwrap_or_default();
                return Err(format!(
                    "{error}; actual private test retained at {}; normal tool: {log}",
                    retained.display()
                )
                .into());
            }
        };
        assert_eq!(result["systemd_unit"], "graphical.target");
        assert!(enable_fixed_diagnostic(&root, directory.path()).is_err());
        assert!(!root.join("etc/systemd/system/default.target").exists());
        Ok(())
    }
    #[test]
    #[ignore = "actual root-owned private new images and reviewed mke2fs required"]
    fn empty_meituan_actual_new_pair_full_bytes_and_changed_body_rejection() -> Result<()> {
        ensure(
            rustix::process::geteuid().is_root(),
            "explicit private image gate requires root",
        )?;
        let directory = tempfile::Builder::new()
            .prefix("empty-meituan-factory-test-")
            .tempdir_in("/var/lib/droidloom-qualification")?;
        let mut actual = Vec::new();
        for (role, recipe) in contract::IMAGES.into_iter().enumerate() {
            let value = create(
                directory.path(),
                &directory.path().join(format!("{}.img", recipe.name)),
                role,
            )?;
            value.revalidate()?;
            actual.push(value);
        }
        ensure(
            actual[0].identity.ino != actual[1].identity.ino,
            "two new test images alias",
        )?;
        // Changes only this test's newly created, unmounted image. Neither a
        // header/UUID nor a previous receipt can replace the complete read.
        actual[0]
            .held
            .write_all_at(b"not-empty", contract::IMAGES[0].bytes - 32)?;
        actual[0].held.sync_all()?;
        assert!(actual[0].revalidate().is_err());
        assert!(contract::verify_initial_image(&actual[0].reader, 0, || Ok(())).is_err());
        assert!(contract::verify_initial_image(&actual[1].reader, 0, || Ok(())).is_err());
        assert!(create(directory.path(), &actual[1].pin.path, 1).is_err());
        actual[1].revalidate()?;
        Ok(())
    }
}
