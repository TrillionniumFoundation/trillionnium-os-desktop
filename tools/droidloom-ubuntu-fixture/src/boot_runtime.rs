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
    io::{Read, Seek, SeekFrom, Write},
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

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InitrdTools {
    pub package_name: String,
    pub package_version: String,
    pub hook_functions: FilePin,
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

pub(crate) fn redirected(
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
    cmd.stdin(if let Some(bytes) = input {
        // A regular private input file cannot block the caller before its
        // subprocess timeout begins, unlike filling an unread pipe.
        let path = work.join(format!("{name}.stdin"));
        boot_files::write_new(&path, bytes, 0o400)?;
        Stdio::from(boot_files::checked_file(&boot_files::pin_file(&path)?)?)
    } else {
        Stdio::null()
    });
    let mut child = crate::boot_child::OwnedChild::spawn(&mut cmd)?;
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
            break child.stop_and_reap()?;
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

fn readback_initrd_streams(
    work: &Path,
    result: &FilePin,
    base: &FilePin,
    layer: &FilePin,
) -> Result<(FilePin, Value)> {
    let padding = (4 - base.bytes % 4) % 4;
    let layer_offset = base
        .bytes
        .checked_add(padding)
        .ok_or("initrd offset overflow")?;
    ensure(
        result.bytes
            == layer_offset
                .checked_add(layer.bytes)
                .ok_or("initrd size overflow")?,
        "final initrd has truncated or trailing bytes",
    )?;
    let mut input = boot_files::checked_file(result)?;
    let before = fs::stat(&input)?;
    let prefix_path = work.join("final-base-readback.img");
    let mut prefix = boot_files::new_file(&prefix_path, 0o400)?;
    ensure(
        std::io::copy(&mut Read::by_ref(&mut input).take(base.bytes), &mut prefix)? == base.bytes,
        "final initrd base truncated",
    )?;
    prefix.sync_all()?;
    let mut zeros = vec![0; usize::try_from(padding)?];
    input.read_exact(&mut zeros)?;
    ensure(
        zeros.iter().all(|b| *b == 0),
        "final initrd alignment is not zero padding",
    )?;
    let suffix_path = work.join("final-layer-readback.cpio.gz");
    let mut suffix = boot_files::new_file(&suffix_path, 0o400)?;
    ensure(
        std::io::copy(&mut Read::by_ref(&mut input).take(layer.bytes), &mut suffix)? == layer.bytes,
        "final initrd layer truncated",
    )?;
    suffix.sync_all()?;
    ensure(
        input.read(&mut [0u8; 1])? == 0,
        "final initrd has an undeclared member",
    )?;
    input.seek(SeekFrom::Start(0))?;
    ensure(
        fs::hash(&input)? == result.sha256
            && fs::stat(&input)? == before
            && boot_files::open_pin(result)?.1 == before,
        "final initrd changed during stream readback",
    )?;
    let prefix = boot_files::pin_file(&prefix_path)?;
    let suffix = boot_files::pin_file(&suffix_path)?;
    ensure(
        prefix.sha256 == base.sha256 && suffix.sha256 == layer.sha256,
        "final initrd member digest differs from its normal producer",
    )?;
    Ok((
        suffix.clone(),
        json!({
            "format":"linux-concatenated-initramfs",
            "format_reference":"https://docs.kernel.org/driver-api/early-userspace/buffer-format.html",
            "base":{"offset":0,"bytes":base.bytes,"input":base,"actual_readback":prefix},
            "padding":{"offset":base.bytes,"bytes":padding,"all_zero":true},
            "layer":{"offset":layer_offset,"bytes":layer.bytes,"input":layer,"actual_readback":suffix},
            "final":result,"trailing_bytes":0,"target_kernel_unpack_qualified":false
        }),
    ))
}

fn check_initrd_overlay_layout(
    root: &Path,
    base_root: &Path,
    layer: &Path,
    members: &[PathBuf],
) -> Result<Value> {
    let base = fs::Tree::open(&fs::absolute_string(base_root)?, 0)?;
    let fixture = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let mut aliases = Vec::new();
    for path in ["/bin", "/sbin", "/lib", "/lib64"] {
        let (base_id, base_target) = base.read_link(path)?;
        let (_, fixture_target) = fixture.read_link(path)?;
        ensure(
            base_id.uid == 0
                && base_id.gid == 0
                && crate::paths::normalize_link(path, &base_target)?
                    == crate::paths::normalize_link(path, &fixture_target)?,
            "normal base usrmerge aliases differ from the admitted fixture",
        )?;
        ensure(
            !members.iter().any(|p| {
                p.strip_prefix(layer)
                    .is_ok_and(|p| p == Path::new(&path[1..]))
            }),
            "custody layer unexpectedly replaces a root usrmerge alias",
        )?;
        aliases
            .push(json!({"path":path,"base_target":base_target,"fixture_target":fixture_target}));
    }
    let mut collisions = Vec::new();
    for path in members.iter().skip(1) {
        let guest = format!("/{}", path.strip_prefix(layer)?.to_string_lossy());
        let wanted = std::fs::symlink_metadata(path)?;
        match base.identity(&guest) {
            Ok(existing) => {
                ensure(
                    rustix::fs::FileType::from_raw_mode(existing.mode)
                        == rustix::fs::FileType::from_raw_mode(wanted.mode()),
                    "initrd layer would replace a base entry with a different type",
                )?;
                if wanted.is_dir() {
                    ensure(
                        existing.mode & 0o7777 == wanted.mode() & 0o7777
                            && existing.uid == wanted.uid()
                            && existing.gid == wanted.gid(),
                        "initrd layer would change a base directory's permissions",
                    )?;
                } else {
                    ensure(
                        existing.nlink == 1 && wanted.nlink() == 1,
                        "initrd overlay collision involves an ambiguous hardlink",
                    )?;
                }
                collisions.push(json!({"path":guest,"base_identity":existing,
                    "layer_mode":wanted.mode(),"layer_uid":wanted.uid(),"layer_gid":wanted.gid()}));
            }
            Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
                ()
            }
            Err(e) => return Err(e),
        }
    }
    Ok(
        json!({"usrmerge_aliases":aliases,"existing_entry_collisions":collisions,
        "base_directories_preserved":true,"target_kernel_unpack_qualified":false}),
    )
}

pub fn build_initrd(
    root: &Path,
    work: &Path,
    base: &FilePin,
    tools: &InitrdTools,
) -> Result<FilePin> {
    ensure(
        tools.package_name == "initramfs-tools-core"
            && !tools.package_version.is_empty()
            && tools.package_version.len() <= 64
            && tools
                .package_version
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b".+:~-".contains(&b)),
        "initrd support must identify the reviewed native initramfs-tools-core package",
    )?;
    ensure(
        tools.hook_functions.bytes <= 65536,
        "public initrd hook support exceeds bound",
    )?;
    let support = root.join("usr/share/initramfs-tools/hook-functions");
    boot_files::ensure_dir(root, "/usr/share/initramfs-tools", 0o755)?;
    // A complete original package supplement already carries this exact support.
    // Reuse it only after full content and native metadata verification.
    match std::fs::symlink_metadata(&support) {
        Ok(_) => {
            let expected = boot_files::read_pin(&tools.hook_functions, 65536)?;
            let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
            let (id, sha, attrs) =
                fs::read_regular(&tree, "/usr/share/initramfs-tools/hook-functions")?;
            ensure(
                id.mode == 0o100644
                    && id.uid == 0
                    && id.gid == 0
                    && id.nlink == 1
                    && id.size == expected.len() as u64
                    && sha == tools.hook_functions.sha256
                    && attrs.is_empty(),
                "existing original initrd hook support differs from its pin",
            )?;
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            boot_files::copy_pin(&tools.hook_functions, &support, 0o644)?;
        }
        Err(e) => return Err(e.into()),
    }
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
    ensure(
        !order
            .windows(b"droidloom-early-custody".len())
            .any(|w| w == b"droidloom-early-custody"),
        "base initrd already schedules Droidloom custody; a fresh normal base is required to avoid double execution",
    )?;
    let layer = work.join("initrd-layer");
    boot_files::private_dir(&layer)?;
    let hook = root.join("usr/share/initramfs-tools/hooks/droidloom-early-release");
    let hook_pin = boot_files::pin_file(&hook)?;
    let selinux = root.join("usr/lib/x86_64-linux-gnu/libselinux.so.1");
    let selinux_pin = boot_files::pin_file(&selinux)?;
    let (apparmor_pin, _) =
        boot_files::resolve_public_file(root, "/usr/lib/x86_64-linux-gnu/libapparmor.so.1")?;
    // Use the upstream shell interface, with its normal construction umask.
    // The exported project hook need not link libselinux itself; explicitly
    // carry the admitted native library so an older base cannot retain it.
    let hook_command = "umask 022\n/usr/share/initramfs-tools/hooks/droidloom-early-release\n. /usr/share/initramfs-tools/hook-functions\ncopy_exec /usr/lib/x86_64-linux-gnu/libselinux.so.1\ncopy_exec /usr/lib/x86_64-linux-gnu/libapparmor.so.1\n";
    boot_files::run_logged(
        work,
        "ordinary-initrd-hook",
        "/usr/bin/bwrap",
        &[
            "--unshare-user".into(),
            "--unshare-pid".into(),
            "--unshare-net".into(),
            "--die-with-parent".into(),
            "--uid".into(),
            "0".into(),
            "--gid".into(),
            "0".into(),
            "--ro-bind".into(),
            root.to_string_lossy().into(),
            "/".into(),
            "--dev".into(),
            "/dev".into(),
            "--proc".into(),
            "/proc".into(),
            "--tmpfs".into(),
            "/run".into(),
            "--dir".into(),
            "/run/droidloom-initrd-layer".into(),
            "--bind".into(),
            layer.to_string_lossy().into(),
            "/run/droidloom-initrd-layer".into(),
            "--setenv".into(),
            "DESTDIR".into(),
            "/run/droidloom-initrd-layer".into(),
            "--setenv".into(),
            "verbose".into(),
            "n".into(),
            "--".into(),
            "/bin/sh".into(),
            "-eu".into(),
            "-c".into(),
            hook_command.into(),
        ],
        120,
    )?;
    ensure(
        boot_files::pin_file(&hook)?.sha256 == hook_pin.sha256
            && boot_files::pin_file(&support)?.sha256 == tools.hook_functions.sha256
            && boot_files::pin_file(&selinux)?.sha256 == selinux_pin.sha256
            && boot_files::pin_file(&apparmor_pin.path)?.sha256 == apparmor_pin.sha256,
        "normal hook changed during execution",
    )?;
    let mut copied = Vec::new();
    walk(&layer, &mut copied)?;
    for lib in [
        "libsystemd.so.0",
        "libcrypto.so.3",
        "libc.so.6",
        "libselinux.so.1",
        "libapparmor.so.1",
    ] {
        ensure(
            copied
                .iter()
                .filter(|p| p.file_name().and_then(|n| n.to_str()) == Some(lib))
                .count()
                == 1,
            &format!("ordinary initrd construction omitted required library {lib}"),
        )?;
    }
    let mut dependency_readback = Vec::new();
    for path in &copied {
        let metadata = std::fs::symlink_metadata(path)?;
        let kind = metadata.file_type();
        if kind.is_dir() && path != &layer {
            ensure(
                metadata.mode() & 0o7777 == 0o755 && metadata.uid() == 0 && metadata.gid() == 0,
                "normal initrd construction directory mode/owner differs",
            )?;
        }
        if !kind.is_file() && !kind.is_symlink() {
            continue;
        }
        let guest = format!("/{}", path.strip_prefix(&layer)?.to_string_lossy());
        let (source, aliases) = boot_files::resolve_public_file(root, &guest)?;
        let (actual, layer_aliases) = boot_files::resolve_public_file(&layer, &guest)?;
        ensure(
            source.bytes == actual.bytes && source.sha256 == actual.sha256,
            "normal initrd hook copied bytes outside the admitted fixture dependency closure",
        )?;
        dependency_readback.push(json!({"source":source,"layer":actual,"resolution":aliases,"layer_resolution":layer_aliases}));
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
    let overlay_layout = check_initrd_overlay_layout(
        root,
        orders[0]
            .ancestors()
            .nth(3)
            .ok_or("invalid base initrd root")?,
        &layer,
        &all,
    )?;
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
    // Linux consumes concatenated compressed newc members. The distribution
    // unpacker may silently stop after its first compressed member. Re-read
    // both declared members from the actual final FD, including every padding
    // byte and EOF, then independently unpack the verified final layer.
    let (final_layer, stream_readback) =
        readback_initrd_streams(work, &result, base, &boot_files::pin_file(&gz)?)?;
    let final_unpack = work.join("unpacked-final-initrd");
    boot_files::run_logged(
        work,
        "unpack-final-initrd",
        "/usr/bin/unmkinitramfs",
        &[
            final_layer.path.to_string_lossy().into(),
            final_unpack.to_string_lossy().into(),
        ],
        120,
    )?;
    let mut final_paths = Vec::new();
    walk(&final_unpack, &mut final_paths)?;
    let effective_roots: Vec<_> = final_paths
        .iter()
        .filter(|p| {
            p.ends_with("scripts/init-bottom/ORDER")
                && std::fs::symlink_metadata(p).is_ok_and(|m| m.is_file())
        })
        .map(|p| p.ancestors().nth(3).ok_or("invalid final initrd root"))
        .collect::<std::result::Result<Vec<_>, _>>()?;
    ensure(
        effective_roots.len() == 1,
        "final initrd lacks one effective init-bottom root",
    )?;
    let mut effective_members = Vec::new();
    walk(effective_roots[0], &mut effective_members)?;
    let relative_set =
        |paths: &[PathBuf], root: &Path| -> Result<std::collections::BTreeSet<PathBuf>> {
            paths
                .iter()
                .skip(1)
                .map(|p| Ok(p.strip_prefix(root)?.to_owned()))
                .collect()
        };
    ensure(
        relative_set(&all, &layer)? == relative_set(&effective_members, effective_roots[0])?,
        "final initrd layer has missing or unexpected members",
    )?;
    let mut final_readback = Vec::new();
    let mut final_directories = Vec::new();
    for path in &all {
        let source_metadata = std::fs::symlink_metadata(path)?;
        let kind = source_metadata.file_type();
        if kind.is_dir() && path != &layer {
            let guest = format!("/{}", path.strip_prefix(&layer)?.to_string_lossy());
            let final_tree = fs::Tree::open(&fs::absolute_string(effective_roots[0])?, 0)?;
            let actual = final_tree.identity(&guest)?;
            ensure(
                rustix::fs::FileType::from_raw_mode(actual.mode) == rustix::fs::FileType::Directory
                    && actual.mode & 0o7777 == source_metadata.mode() & 0o7777
                    && actual.uid == source_metadata.uid()
                    && actual.gid == source_metadata.gid(),
                "final initrd directory metadata differs from its ordinary layer",
            )?;
            final_directories.push(
                json!({"path":guest,"mode":actual.mode & 0o7777,"uid":actual.uid,"gid":actual.gid}),
            );
        }
        if !kind.is_file() && !kind.is_symlink() {
            continue;
        }
        let guest = format!("/{}", path.strip_prefix(&layer)?.to_string_lossy());
        let final_tree = fs::Tree::open(&fs::absolute_string(effective_roots[0])?, 0)?;
        let actual_metadata = final_tree.identity(&guest)?;
        ensure(
            actual_metadata.mode == source_metadata.mode()
                && actual_metadata.uid == source_metadata.uid()
                && actual_metadata.gid == source_metadata.gid(),
            &format!("final initrd file metadata differs for {guest}"),
        )?;
        let (expected, _) = boot_files::resolve_public_file(&layer, &guest)?;
        let (actual, resolution) = boot_files::resolve_public_file(effective_roots[0], &guest)?;
        ensure(
            actual.bytes == expected.bytes && actual.sha256 == expected.sha256,
            &format!(
                "final initrd does not contain the exact ordinary hook layer bytes for {guest}"
            ),
        )?;
        if kind.is_symlink() {
            let source_tree = fs::Tree::open(&fs::absolute_string(&layer)?, 0)?;
            let final_tree = fs::Tree::open(&fs::absolute_string(effective_roots[0])?, 0)?;
            ensure(
                source_tree.read_link(&guest)?.1 == final_tree.read_link(&guest)?.1,
                "final initrd altered an ordinary hook library alias",
            )?;
        }
        final_readback.push(json!({"path":guest,"sha256":actual.sha256,"bytes":actual.bytes,"resolution":resolution}));
    }
    fs::write_json(
        &fs::absolute_string(&work.join("INITRD.json"))?,
        &json!({"original":base,"hook":hook_pin,"custody":custody_pin,"original_order":order_pin,
            "support":tools,"dependency_root":root,"dependency_readback":dependency_readback,
            "libselinux_input":selinux_pin,"stock_hook_command":hook_command,
            "stream_readback":stream_readback,"overlay_layout":overlay_layout,
            "final_layer_readback":final_readback,"final_directory_readback":final_directories,"result":result,
            "synthetic_entrypoint":false,"guest_qualified":false}),
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

pub fn label_root(
    root: &Path,
    work: &Path,
    tools: &LabelTools,
    query_runtime: Option<&str>,
) -> Result<Value> {
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
    let query_inputs = query_runtime
        .map(|runtime| crate::boot_query::label_inputs(root, runtime))
        .transpose()?;
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
        "labels":rows,"missing":missing,"coverage_complete":missing.is_empty(),
        "fixed_query_inputs":query_inputs,"guest_qualified":false});
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

pub(super) fn debugfs_command_path(path: &str) -> Result<String> {
    ensure(
        path.starts_with('/') && !path.bytes().any(|b| b < 32 || b == b'"' || b == b'\\'),
        "unsupported debugfs readback path",
    )?;
    Ok(format!("\"{path}\""))
}

fn stat_fields(text: &str) -> Result<(String, u32, u32, u32, u64)> {
    // debugfs also prints a historical Fragment ... Size field. Only its
    // two canonical inode identity lines contain the metadata being compared.
    let header = text
        .lines()
        .filter(|line| line.starts_with("Inode:") || line.starts_with("User:"))
        .collect::<Vec<_>>()
        .join("\n");
    let tokens: Vec<_> = header.split_whitespace().collect();
    let one = |name: &str| -> Result<&str> {
        let positions: Vec<_> = tokens
            .iter()
            .enumerate()
            .filter(|(_, value)| **value == name)
            .collect();
        ensure(
            positions.len() == 1,
            "debugfs inode field missing or repeated",
        )?;
        tokens
            .get(positions[0].0 + 1)
            .copied()
            .ok_or_else(|| "debugfs inode field truncated".into())
    };
    Ok((
        one("Type:")?.into(),
        u32::from_str_radix(one("Mode:")?, 8)?,
        one("User:")?.parse()?,
        one("Group:")?.parse()?,
        one("Size:")?.parse()?,
    ))
}

fn readback_metadata(root: &Path, work: &Path, disk: &Path, paths: &[String]) -> Result<Value> {
    ensure(
        !paths.is_empty() && paths.len() <= 8192,
        "inode readback set outside bound",
    )?;
    let mut commands = String::new();
    let mut expected = BTreeMap::new();
    for path in paths {
        let command = format!("stat {}", debugfs_command_path(path)?);
        commands.push_str(&command);
        commands.push('\n');
        let source = if path == "/" {
            root.to_owned()
        } else {
            boot_files::guest_path(root, path)?
        };
        let m = std::fs::symlink_metadata(&source)?;
        ensure(
            expected
                .insert(format!("debugfs: {command}"), (path, m))
                .is_none(),
            "duplicate inode readback path",
        )?;
    }
    let command_file = work.join("inode-readback.commands");
    boot_files::write_new(&command_file, commands.as_bytes(), 0o600)?;
    let result = boot_files::run_logged(
        work,
        "inode-readback",
        "/usr/sbin/debugfs",
        &[
            "-f".into(),
            command_file.to_string_lossy().into(),
            disk.to_string_lossy().into(),
        ],
        120,
    )?;
    let text = String::from_utf8(boot_files::read_pin(&result.log, 32 * 1024 * 1024)?)?;
    let mut sections = BTreeMap::<String, String>::new();
    let mut current = None;
    for line in text.lines() {
        if line.starts_with("debugfs: stat ") {
            ensure(
                expected.contains_key(line) && !sections.contains_key(line),
                "unexpected or repeated debugfs inode result",
            )?;
            current = Some(line.to_owned());
            sections.insert(line.to_owned(), String::new());
        } else if let Some(key) = &current {
            sections
                .get_mut(key)
                .ok_or("missing inode output section")?
                .push_str(line);
            sections
                .get_mut(key)
                .ok_or("missing inode output section")?
                .push('\n');
        }
    }
    ensure(
        sections.len() == expected.len(),
        "incomplete actual ext4 inode readback",
    )?;
    let mut rows = Vec::new();
    for (key, (path, m)) in expected {
        let (kind, mode, uid, gid, size) = stat_fields(sections.get(&key).ok_or("missing inode")?)?;
        let wanted = match rustix::fs::FileType::from_raw_mode(m.mode()) {
            rustix::fs::FileType::RegularFile => "regular",
            rustix::fs::FileType::Directory => "directory",
            rustix::fs::FileType::Symlink => "symlink",
            rustix::fs::FileType::CharacterDevice => "character",
            rustix::fs::FileType::BlockDevice => "block",
            _ => return Err("unsupported critical inode type".into()),
        };
        ensure(
            kind == wanted
                && mode == m.mode() & 0o7777
                && uid == m.uid()
                && gid == m.gid()
                && (!(m.is_file() || m.file_type().is_symlink()) || size == m.len()),
            &format!("actual ext4 inode metadata differs for {path}"),
        )?;
        rows.push(json!({"path":path,"type":kind,"mode":mode,"uid":uid,"gid":gid,"size":size}));
    }
    Ok(json!({"command":result,"inodes":rows,"all_matched":true}))
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
    let mut selected: Vec<String> = [
        "/",
        "/usr",
        "/etc",
        "/var",
        "/bin",
        "/lib",
        "/lib64",
        "/usr/lib/systemd/systemd",
        "/usr/lib/systemd/systemd-executor",
        "/usr/lib/x86_64-linux-gnu/libselinux.so.1",
        "/usr/lib/x86_64-linux-gnu/libapparmor.so.1",
        "/usr/lib/x86_64-linux-gnu/libapparmor.so.1.30.7",
        "/etc/passwd",
        "/etc/shadow",
        "/etc/selinux/droidloom/policy/policy.30",
        "/etc/selinux/droidloom/contexts/dbus_contexts",
        "/etc/selinux/droidloom/seusers",
        "/etc/selinux/droidloom/contexts/default_contexts",
        "/usr/lib/droidloom/production/current/droidloom-board-init",
        "/usr/lib/droidloom/production/current/droidloomd",
        "/usr/lib/droidloom/production/current/board-devices/console",
        "/usr/lib/droidloom/production/current/board-devices/kmsg",
        "/usr/lib/droidloom/production/current/board-devices/null",
        "/usr/lib/droidloom/production/current/board-devices/full",
        "/usr/bin/droidloomctl",
        "/usr/bin/droidloom-wayland",
        "/etc/droidloom/production/selected.json",
        "/etc/droidloom/container-launcher.json",
        "/var/lib/droidloom-mac-calibration",
        "/var/lib/droidloom-public-apks",
        "/var/lib/droidloom/users/1000/data/data.img",
        "/var/lib/droidloom/users/1000/data/metadata.img",
        "/lost+found",
    ]
    .iter()
    .map(|path| (*path).to_owned())
    .collect();
    let query_runtime = labels["fixed_query_inputs"]["runtime_manifest_sha256"].as_str();
    if let Some(runtime) = query_runtime {
        selected.extend(crate::boot_query::guest_paths(runtime)?);
    }
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
    let mut metadata_paths: std::collections::BTreeSet<String> =
        selected.iter().map(|p| p.to_string()).collect();
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
        if m.mode() & 0o6000 != 0 || m.uid() != 0 || m.gid() != 0 {
            metadata_paths.insert(guest.clone());
        }
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
                metadata_paths.insert(guest.clone());
            }
        }
    }
    let metadata = readback_metadata(
        root,
        &check,
        &disk,
        &metadata_paths.into_iter().collect::<Vec<_>>(),
    )?;
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
    let query_readback = query_runtime
        .map(|runtime| crate::boot_query_image::verify(root, work, &disk, runtime))
        .transpose()?;
    let apparmor_readback = crate::boot_apparmor_candidate::verify_image(root, work, &disk)?;
    let record = boot_files::pin_file(&disk)?;
    fs::write_json(
        &fs::absolute_string(&work.join("ROOT-IMAGE.json"))?,
        &json!({
        "image":record,"root_filesystem_uuid":uuid,"critical_label_paths":selected,
        "privilege_attributes_verified":attrs.len(),"inode_metadata_readback":metadata,
        "fixed_query_input_readback":query_readback,"apparmor_library_readback":apparmor_readback,"guest_qualified":false}),
        0,
    )?;
    Ok(record)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn final_initrd_members_reject_wrong_padding_content_and_trailing_bytes() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let base_path = temp.path().join("base");
        let layer_path = temp.path().join("layer");
        boot_files::write_new(&base_path, b"base-data", 0o400)?;
        boot_files::write_new(&layer_path, b"layer-data", 0o400)?;
        let base = boot_files::pin_file(&base_path)?;
        let layer = boot_files::pin_file(&layer_path)?;
        let valid = b"base-data\0\0\0layer-data".to_vec();
        let mut padding = valid.clone();
        padding[9] = 1;
        let mut prefix = valid.clone();
        prefix[0] ^= 1;
        let mut suffix = valid.clone();
        suffix[12] ^= 1;
        let mut trailing = valid.clone();
        trailing.push(0);
        let mut truncated = valid.clone();
        truncated.pop();
        for (i, bytes) in [valid, padding, prefix, suffix, trailing, truncated]
            .iter()
            .enumerate()
        {
            let work = temp.path().join(format!("case-{i}"));
            boot_files::private_dir(&work)?;
            let output = work.join("final.img");
            boot_files::write_new(&output, bytes, 0o400)?;
            let result =
                readback_initrd_streams(&work, &boot_files::pin_file(&output)?, &base, &layer);
            assert_eq!(result.is_ok(), i == 0, "case {i}");
            if let Ok((actual, report)) = result {
                assert_eq!(boot_files::read_pin(&actual, 32)?, b"layer-data");
                assert_eq!(report["layer"]["offset"], 12);
                assert_eq!(report["padding"]["bytes"], 3);
                assert_eq!(report["target_kernel_unpack_qualified"], false);
            }
        }
        Ok(())
    }

    #[test]
    fn actual_ext4_metadata_including_symlink_is_read_back() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let root = temp.path().join("root");
        std::fs::create_dir(&root)?;
        std::fs::write(root.join("file"), b"native fixture bytes")?;
        std::fs::set_permissions(root.join("file"), std::fs::Permissions::from_mode(0o640))?;
        std::os::unix::fs::symlink("file", root.join("alias"))?;
        let disk = temp.path().join("test.ext4");
        let image = boot_files::new_file(&disk, 0o600)?;
        image.set_len(16 * 1024 * 1024)?;
        boot_files::run_logged(
            temp.path(),
            "test-mkfs",
            "/usr/sbin/mke2fs",
            &[
                "-q".into(),
                "-F".into(),
                "-t".into(),
                "ext4".into(),
                "-d".into(),
                root.to_string_lossy().into(),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let work = temp.path().join("readback");
        boot_files::private_dir(&work)?;
        let paths = vec!["/file".into(), "/alias".into()];
        assert!(readback_metadata(&root, &work, &disk, &paths)?["all_matched"] == true);
        std::fs::set_permissions(root.join("file"), std::fs::Permissions::from_mode(0o600))?;
        let negative = temp.path().join("negative");
        boot_files::private_dir(&negative)?;
        assert!(readback_metadata(&root, &negative, &disk, &paths).is_err());
        // A device inside this disposable ext4 file needs no host mknod or
        // privileged device access. Exercise debugfs's actual type spelling.
        boot_files::run_logged(
            temp.path(),
            "test-device-create",
            "/usr/sbin/debugfs",
            &[
                "-w".into(),
                "-R".into(),
                "mknod device c 5 1".into(),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let device = boot_files::run_logged(
            temp.path(),
            "test-device-stat",
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                "stat /device".into(),
                disk.to_string_lossy().into(),
            ],
            30,
        )?;
        let text = String::from_utf8(boot_files::read_pin(&device.log, 65536)?)?;
        assert_eq!(stat_fields(&text)?.0, "character");
        Ok(())
    }
}
