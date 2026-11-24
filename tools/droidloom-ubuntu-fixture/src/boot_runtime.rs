use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use rustix::fs::XattrFlags;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    io::{Seek, Write},
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LabelTools {
    pub setfiles: FilePin,
    pub matchpathcon: FilePin,
    pub producer_libsepol: FilePin,
}

fn walk(path: &Path, out: &mut Vec<PathBuf>) -> Result<()> {
    ensure(
        out.len() < 250_000,
        "fixture tree exceeds bounded file count",
    )?;
    let m = std::fs::symlink_metadata(path)?;
    out.push(path.to_owned());
    if m.file_type().is_dir() {
        let mut entries = std::fs::read_dir(path)?
            .map(|e| e.map(|v| v.path()))
            .collect::<std::io::Result<Vec<_>>>()?;
        entries.sort();
        for p in entries {
            walk(&p, out)?;
        }
    }
    Ok(())
}

fn redirected(
    work: &Path,
    name: &str,
    program: &str,
    args: &[String],
    cwd: Option<&Path>,
    input: Option<&[u8]>,
    output: &Path,
    limit: u64,
    seconds: u64,
) -> Result<FilePin> {
    let log_path = work.join(format!("{name}.log"));
    let log = boot_files::new_file(&log_path, 0o600)?;
    let out = boot_files::new_file(output, 0o600)?;
    let mut cmd = Command::new(program);
    cmd.args(args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(log));
    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }
    cmd.stdin(if input.is_some() {
        Stdio::piped()
    } else {
        Stdio::null()
    });
    let mut child = cmd.spawn()?;
    if let Some(bytes) = input {
        if let Err(e) = child
            .stdin
            .take()
            .ok_or("missing subprocess input")?
            .write_all(bytes)
        {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e.into());
        }
    }
    let start = Instant::now();
    let mut timed_out = false;
    let status = loop {
        if let Some(s) = child.try_wait()? {
            break s;
        }
        if start.elapsed() > Duration::from_secs(seconds)
            || std::fs::metadata(output)?.len() > limit
            || std::fs::metadata(&log_path)?.len() > 16 * 1024 * 1024
        {
            timed_out = true;
            child.kill()?;
            break child.wait()?;
        }
        std::thread::sleep(Duration::from_millis(100));
    };
    let evidence = json!({"program":program,"args":args,"cwd":cwd,"exit_code":status.code(),
        "timed_out":timed_out,"stderr":boot_files::pin_file(&log_path)?,
        "stdout_path":output,"stdout_bytes":std::fs::metadata(output)?.len()});
    fs::write_json(
        &fs::absolute_string(&work.join(format!("{name}.json")))?,
        &evidence,
        0,
    )?;
    ensure(
        !timed_out && status.success() && std::fs::metadata(output)?.len() <= limit,
        &format!("ordinary command {name} failed; original command evidence retained"),
    )?;
    boot_files::pin_file(output)
}

pub fn build_initrd(root: &Path, work: &Path, base: &FilePin) -> Result<FilePin> {
    let original = work.join("original-initrd.img");
    boot_files::copy_pin(base, &original, 0o400)?;
    let unpacked = work.join("unpacked-initrd");
    boot_files::run_logged(
        work,
        "unpack-original-initrd",
        "/usr/bin/unmkinitramfs",
        &[
            original.to_string_lossy().into(),
            unpacked.to_string_lossy().into(),
        ],
        120,
    )?;
    let mut paths = Vec::new();
    walk(&unpacked, &mut paths)?;
    let orders: Vec<_> = paths
        .iter()
        .filter(|p| {
            p.ends_with("scripts/init-bottom/ORDER")
                && std::fs::symlink_metadata(p).is_ok_and(|m| m.is_file())
        })
        .collect();
    ensure(
        orders.len() == 1,
        "ordinary initrd must contain one init-bottom order",
    )?;
    let order_pin = boot_files::pin_file(orders[0])?;
    let order = boot_files::read_pin(&order_pin, 64 * 1024)?;
    let layer = work.join("initrd-layer");
    boot_files::private_dir(&layer)?;
    let hook = root.join("usr/share/initramfs-tools/hooks/droidloom-early-release");
    let hook_pin = boot_files::pin_file(&hook)?;
    boot_files::run_logged(
        work,
        "ordinary-initrd-hook",
        "/usr/bin/bwrap",
        &[
            "--unshare-user".into(),
            "--uid".into(),
            "0".into(),
            "--gid".into(),
            "0".into(),
            "--ro-bind".into(),
            "/".into(),
            "/".into(),
            "--dev".into(),
            "/dev".into(),
            "--proc".into(),
            "/proc".into(),
            "--bind".into(),
            layer.to_string_lossy().into(),
            layer.to_string_lossy().into(),
            "--ro-bind".into(),
            root.join("usr/lib/droidloom").to_string_lossy().into(),
            "/usr/lib/droidloom".into(),
            "--setenv".into(),
            "DESTDIR".into(),
            layer.to_string_lossy().into(),
            "--setenv".into(),
            "verbose".into(),
            "n".into(),
            "--".into(),
            "/bin/sh".into(),
            hook.to_string_lossy().into(),
        ],
        120,
    )?;
    ensure(
        boot_files::pin_file(&hook)?.sha256 == hook_pin.sha256,
        "normal hook changed during execution",
    )?;
    let mut copied = Vec::new();
    walk(&layer, &mut copied)?;
    for lib in ["libsystemd.so.0", "libcrypto.so.3", "libc.so.6"] {
        ensure(
            copied
                .iter()
                .filter(|p| p.file_name().and_then(|n| n.to_str()) == Some(lib))
                .count()
                == 1,
            "ordinary hook omitted a required dynamic dependency",
        )?;
    }
    boot_files::ensure_dir(&layer, "/scripts/init-bottom", 0o755)?;
    let custody =
        root.join("usr/share/initramfs-tools/scripts/init-bottom/droidloom-early-custody");
    let custody_pin = boot_files::pin_file(&custody)?;
    boot_files::copy_pin(
        &custody_pin,
        &layer.join("scripts/init-bottom/droidloom-early-custody"),
        0o755,
    )?;
    let mut body=b"/scripts/init-bottom/droidloom-early-custody || panic \"Droidloom selected generation failed\"\n".to_vec();
    body.extend_from_slice(&order);
    boot_files::write_new(&layer.join("scripts/init-bottom/ORDER"), &body, 0o644)?;
    let mut all = Vec::new();
    walk(&layer, &mut all)?;
    let mut names = Vec::new();
    for p in all.iter().skip(1) {
        let relative = p
            .strip_prefix(&layer)?
            .to_str()
            .ok_or("non-UTF8 ordinary initrd entry")?;
        ensure(!relative.as_bytes().contains(&0), "NUL initrd entry")?;
        names.extend_from_slice(relative.as_bytes());
        names.push(0);
    }
    let cpio = work.join("normal-layer.cpio");
    redirected(
        work,
        "ordinary-cpio",
        "/usr/bin/cpio",
        &[
            "--null".into(),
            "-o".into(),
            "-H".into(),
            "newc".into(),
            "--owner=0:0".into(),
            "--quiet".into(),
        ],
        Some(&layer),
        Some(&names),
        &cpio,
        256 * 1024 * 1024,
        120,
    )?;
    let gz = work.join("normal-layer.cpio.gz");
    redirected(
        work,
        "ordinary-gzip",
        "/usr/bin/gzip",
        &["-n".into(), "-c".into(), cpio.to_string_lossy().into()],
        None,
        None,
        &gz,
        128 * 1024 * 1024,
        120,
    )?;
    let output = work.join("ubuntu-initrd.img");
    let mut dest = boot_files::new_file(&output, 0o400)?;
    let mut original = boot_files::checked_file(&boot_files::pin_file(&original)?)?;
    std::io::copy(&mut original, &mut dest)?;
    let pad = (4 - dest.stream_position()? % 4) % 4;
    dest.write_all(&vec![0; usize::try_from(pad)?])?;
    let mut extra = boot_files::checked_file(&boot_files::pin_file(&gz)?)?;
    std::io::copy(&mut extra, &mut dest)?;
    dest.sync_all()?;
    let result = boot_files::pin_file(&output)?;
    fs::write_json(
        &fs::absolute_string(&work.join("INITRD.json"))?,
        &json!({"original":base,"hook":hook_pin,"custody":custody_pin,"original_order":order_pin,
            "result":result,"synthetic_entrypoint":false,"guest_qualified":false}),
        0,
    )?;
    Ok(result)
}

fn xattr(path: &Path, name: &str) -> Result<Option<Vec<u8>>> {
    let mut buf = vec![0u8; 65536];
    match rustix::fs::lgetxattr(path, name, buf.as_mut_slice()) {
        Ok(n) => {
            buf.truncate(n);
            Ok(Some(buf))
        }
        Err(e) if e == rustix::io::Errno::NODATA => Ok(None),
        Err(e) => Err(e.into()),
    }
}

pub fn label_root(root: &Path, work: &Path, tools: &LabelTools) -> Result<Value> {
    let toolroot = work.join("label-tools");
    boot_files::private_dir(&toolroot)?;
    for (name, pin, mode) in [
        ("setfiles", &tools.setfiles, 0o500),
        ("matchpathcon", &tools.matchpathcon, 0o500),
        ("libsepol.so.2", &tools.producer_libsepol, 0o444),
    ] {
        boot_files::copy_pin(pin, &toolroot.join(name), mode)?;
    }
    let env = BTreeMap::from([("LD_LIBRARY_PATH".into(), toolroot.to_string_lossy().into())]);
    let policy = root.join("etc/selinux/droidloom/policy/policy.30");
    let contexts = root.join("etc/selinux/droidloom/contexts/files/file_contexts");
    let policy_pin = boot_files::pin_file(&policy)?;
    let contexts_pin = boot_files::pin_file(&contexts)?;
    boot_files::ensure_dir(root, "/lost+found", 0o700)?;
    let result = boot_files::run_logged_env(
        work,
        "original-setfiles",
        &fs::absolute_string(&toolroot.join("setfiles"))?,
        &[
            "-F".into(),
            "-E".into(),
            "-m".into(),
            "-r".into(),
            root.to_string_lossy().into(),
            "-c".into(),
            policy.to_string_lossy().into(),
            contexts.to_string_lossy().into(),
            root.to_string_lossy().into(),
        ],
        300,
        &env,
    )?;
    // setfiles -r resolves the traversal root as an empty prefix. Obtain its
    // actual '/' context from the same libselinux matcher, never a hardcoded label.
    let matched = boot_files::run_logged_env(
        work,
        "original-root-context",
        &fs::absolute_string(&toolroot.join("matchpathcon"))?,
        &[
            "-N".into(),
            "-n".into(),
            "-f".into(),
            contexts.to_string_lossy().into(),
            "/".into(),
        ],
        30,
        &env,
    )?;
    let root_label = String::from_utf8(boot_files::read_pin(&matched.log, 65536)?)?;
    let root_label = root_label.trim();
    ensure(
        root_label.starts_with("u:object_r:")
            && root_label.ends_with(":s0")
            && !root_label.bytes().any(|b| b.is_ascii_whitespace()),
        "ordinary matcher did not return one canonical root context",
    )?;
    let mut raw = root_label.as_bytes().to_vec();
    raw.push(0);
    let dir = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    rustix::fs::fsetxattr(&dir.root, "security.selinux", &raw, XattrFlags::empty())?;
    let mut paths = Vec::new();
    walk(root, &mut paths)?;
    let mut rows = Vec::new();
    let mut missing = Vec::new();
    for path in paths {
        let guest = if path == root {
            "/".to_owned()
        } else {
            format!("/{}", path.strip_prefix(root)?.to_string_lossy())
        };
        let m = std::fs::symlink_metadata(&path)?;
        if let Some(label) = xattr(&path, "security.selinux")? {
            let context = std::str::from_utf8(&label)?.trim_end_matches('\0');
            ensure(
                context.starts_with("u:object_r:") && context.ends_with(":s0"),
                "unexpected actual Linux root label",
            )?;
            rows.push(json!({"path":guest,"mode":m.mode(),"uid":m.uid(),"gid":m.gid(),"label_hex":hex::encode(label)}));
        } else {
            missing.push(guest);
        }
    }
    let output = json!({"policy":policy_pin,"contexts":contexts_pin,"setfiles":result,"root_match":matched,
        "labels":rows,"missing":missing,"coverage_complete":missing.is_empty(),"guest_qualified":false});
    fs::write_json(
        &fs::absolute_string(&work.join("ROOT-LABELS.json"))?,
        &output,
        0,
    )?;
    ensure(
        missing.is_empty(),
        "selected native file_contexts leave unlabeled paths; exact list retained",
    )?;
    Ok(output)
}

fn debugfs_command_path(path: &str) -> Result<String> {
    ensure(
        path.starts_with('/') && !path.bytes().any(|b| b < 32 || b == b'"' || b == b'\\'),
        "unsupported debugfs readback path",
    )?;
    Ok(format!("\"{path}\""))
}

pub fn make_root_image(
    root: &Path,
    work: &Path,
    uuid: &str,
    gib: u64,
    labels: &Value,
) -> Result<FilePin> {
    ensure(
        (64..=96).contains(&gib),
        "full Ubuntu root image must be bounded to 64..96 GiB",
    )?;
    ensure(
        uuid.len() == 36
            && uuid.bytes().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    b == b'-'
                } else {
                    b.is_ascii_hexdigit() && !b.is_ascii_uppercase()
                }
            }),
        "invalid selected root filesystem UUID",
    )?;
    let disk = work.join("ubuntu.ext4");
    let file = boot_files::new_file(&disk, 0o600)?;
    file.set_len(gib * 1024 * 1024 * 1024)?;
    file.sync_all()?;
    boot_files::run_logged(
        work,
        "mkfs-ubuntu",
        "/usr/sbin/mke2fs",
        &[
            "-q".into(),
            "-F".into(),
            "-t".into(),
            "ext4".into(),
            "-m".into(),
            "0".into(),
            "-b".into(),
            "4096".into(),
            "-L".into(),
            "p4qualification".into(),
            "-U".into(),
            uuid.into(),
            "-E".into(),
            "root_owner=0:0".into(),
            "-d".into(),
            root.to_string_lossy().into(),
            disk.to_string_lossy().into(),
        ],
        1200,
    )?;
    let check = work.join("ext4-readback");
    boot_files::private_dir(&check)?;
    let selected = [
        "/",
        "/usr",
        "/etc",
        "/var",
        "/bin",
        "/lib",
        "/lib64",
        "/usr/lib/systemd/systemd",
        "/usr/lib/systemd/systemd-executor",
        "/etc/passwd",
        "/etc/shadow",
        "/etc/selinux/droidloom/policy/policy.30",
        "/usr/lib/droidloom/production/current/droidloom-board-init",
        "/usr/lib/droidloom/production/current/droidloomd",
        "/usr/bin/droidloomctl",
        "/usr/bin/droidloom-wayland",
        "/etc/droidloom/production/selected.json",
        "/var/lib/droidloom-mac-calibration",
        "/var/lib/droidloom/users/1000/data/data.img",
        "/var/lib/droidloom/users/1000/data/metadata.img",
        "/lost+found",
    ];
    let rows = labels["labels"]
        .as_array()
        .ok_or("missing actual source label inventory")?;
    let mut commands = String::new();
    let mut expected = Vec::new();
    for (i, path) in selected.iter().enumerate() {
        let row = rows
            .iter()
            .find(|r| r["path"] == *path)
            .ok_or("critical source label missing")?;
        let out = check.join(format!("label-{i:03}"));
        commands.push_str(&format!(
            "ea_get -f {} {} security.selinux\n",
            out.to_string_lossy(),
            debugfs_command_path(path)?
        ));
        expected.push((
            out,
            row["label_hex"]
                .as_str()
                .ok_or("invalid label evidence")?
                .to_owned(),
        ));
    }
    let cmd = work.join("ext4-label-readback.commands");
    boot_files::write_new(&cmd, commands.as_bytes(), 0o600)?;
    boot_files::run_logged(
        work,
        "ext4-label-readback",
        "/usr/sbin/debugfs",
        &[
            "-f".into(),
            cmd.to_string_lossy().into(),
            disk.to_string_lossy().into(),
        ],
        120,
    )?;
    for (path, hex) in expected {
        ensure(
            std::fs::read(&path)? == hex::decode(hex)?,
            "actual ext4 label differs from admitted source xattr",
        )?;
    }
    // Preserve native capabilities and ACLs; all nonempty public privilege
    // attributes are checked independently on the generated filesystem.
    let mut native = Vec::new();
    walk(root, &mut native)?;
    let mut attr_commands = String::new();
    let mut attrs = Vec::new();
    for path in native {
        let m = std::fs::symlink_metadata(&path)?;
        if !m.is_file() && !m.is_dir() {
            continue;
        }
        let guest = if path == root {
            "/".into()
        } else {
            format!("/{}", path.strip_prefix(root)?.to_string_lossy())
        };
        for name in [
            "security.capability",
            "system.posix_acl_access",
            "system.posix_acl_default",
        ] {
            if let Some(value) = xattr(&path, name)? {
                let out = check.join(format!("privilege-{:04}", attrs.len()));
                attr_commands.push_str(&format!(
                    "ea_get -f {} {} {name}\n",
                    out.to_string_lossy(),
                    debugfs_command_path(&guest)?
                ));
                attrs.push((out, value, guest.clone(), name));
            }
        }
    }
    if !attrs.is_empty() {
        let cmd = work.join("ext4-privilege-readback.commands");
        boot_files::write_new(&cmd, attr_commands.as_bytes(), 0o600)?;
        boot_files::run_logged(
            work,
            "ext4-privilege-readback",
            "/usr/sbin/debugfs",
            &[
                "-f".into(),
                cmd.to_string_lossy().into(),
                disk.to_string_lossy().into(),
            ],
            120,
        )?;
        for (path, value, _, _) in &attrs {
            ensure(
                std::fs::read(path)? == *value,
                "ext4 native capability/ACL differs",
            )?;
        }
    }
    let record = boot_files::pin_file(&disk)?;
    fs::write_json(
        &fs::absolute_string(&work.join("ROOT-IMAGE.json"))?,
        &json!({
        "image":record,"root_filesystem_uuid":uuid,"critical_label_paths":selected,
        "privilege_attributes_verified":attrs.len(),"guest_qualified":false}),
        0,
    )?;
    Ok(record)
}
