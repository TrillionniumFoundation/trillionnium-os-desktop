//! Build a candidate with the original host's normal initramfs mechanism.
//! Only a private overlay is writable. This is not a physical installation,
//! qualification boot, service activation, or a fresh Ubuntu initialization.
use crate::boot_systemd_candidate::dependencies;
use crate::{Result, boot_files as files, ensure, fs, model::Identity};
#[path = "../../../packaging/ubuntu/production/cold_modules.rs"]
mod cold_modules;
#[path = "cold_original_initramfs_verify.rs"]
mod verify;
use files::FilePin;
use rustix::fs::{FlockOperation, Mode, OFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    os::unix::fs::{FileTypeExt, MetadataExt},
    path::{Path, PathBuf},
};
pub(super) use verify::verify_original_initramfs_files;
pub(super) use verify::verify_prepared_original_initramfs;

const ROOT_UUID: &str = "01c27223-3933-481e-9836-7bd0ef1be8c9";
const ORIGINAL_KERNEL: &str = "7.0.14-p4cred1";
const KERNEL: &str = "6.18.64-p4ctx6181-fusectl-aafs-peer-r1";
const KERNEL_SHA: &str = "19052ac77e40a86147f6bc186739763628916033f7c36f3448b4a872914090df";
const MODULES_SHA: &str = "5399a707d1aa2b8511a936dbc1b056891613f6043b8eafe0a1c0ad5c45eb7fa8";
const QUALIFICATION: &str = "/var/lib/droidloom-qualification";
const PYTHON: &str = "/usr/bin/python3.14";
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";
const TOOLS: &[&str] = &[
    PYTHON,
    "/usr/bin/unshare",
    "/usr/bin/mount",
    "/usr/bin/chroot",
    "/usr/bin/setpriv",
    "/usr/bin/apt-get",
    "/usr/bin/dpkg",
    "/usr/bin/dpkg-deb",
    "/usr/sbin/mkinitramfs",
    "/usr/bin/unmkinitramfs",
    "/usr/bin/gpgv",
    "/usr/sbin/fsck",
    "/usr/sbin/fsck.ext4",
    "/usr/sbin/logsave",
];
const FILESYSTEM_CHECKERS: &[&str] =
    &["/usr/sbin/fsck", "/usr/sbin/fsck.ext4", "/usr/sbin/logsave"];
const ORIGINAL_FSTYPE: &[u8] =
    b"# Original Pocket4 root UUID and mounted ext4 were verified before staging.\nFSTYPE=ext4\n";
const NATIVE_HOOK: &[u8] = b"#!/bin/sh\nset -eu\ncase \"${1:-}\" in prereqs) exit 0 ;; esac\n. /usr/share/initramfs-tools/hook-functions\ncopy_exec /usr/lib/x86_64-linux-gnu/libselinux.so.1\ncopy_exec /usr/lib/x86_64-linux-gnu/libapparmor.so.1\n";
const POLICY_RC: &[u8] = b"#!/bin/sh\nexit 101\n";
const PRIVATE_STATE_PATHS: &[&str] = &[
    "/home",
    "/root",
    "/var/lib/droidloom",
    "/var/lib/droidloom-maintenance",
    "/var/lib/droidloom-qualification",
];
const PUBLIC_NAMESPACE_ROOTS: &[&str] = &["/usr/lib/droidloom", "/usr/share/droidloom"];

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    work_directory: PathBuf,
    public_release: FilePin,
    native_release: FilePin,
    native_release_id: String,
    target_preflight: FilePin,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Package {
    role: String,
    package: FilePin,
    name: String,
    version: String,
    architecture: String,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Required {
    source_path: String,
    initrd_path: String,
    bytes: u64,
    sha256: String,
    mode: u32,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Materials {
    schema: String,
    public_release: FilePin,
    public_release_id: String,
    deployment_id: String,
    native_release: FilePin,
    native_release_id: String,
    native_closure: String,
    kernel_release: String,
    kernel_sha256: String,
    root_uuid: String,
    original_kernel: String,
    cohort_sha256: String,
    runtime_sha256: String,
    packages: Vec<Package>,
    required_initrd_members: Vec<Required>,
    module_manifest: FilePin,
    public_directories: BTreeMap<String, u32>,
    physical_install: bool,
    qualification_boot_authorized: bool,
    production_ready: bool,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Stage {
    schema: String,
    work_directory: PathBuf,
    original: Value,
    materials: Materials,
    producer: FilePin,
    input: FilePin,
}

fn string(value: &Value, key: &str) -> Result<String> {
    Ok(value
        .get(key)
        .and_then(Value::as_str)
        .ok_or("required text field missing")?
        .to_owned())
}
fn text(path: &str, max: usize) -> Result<String> {
    let bytes = std::fs::read(path)?;
    ensure(bytes.len() <= max, "fixed kernel observation exceeds bound")?;
    Ok(String::from_utf8(bytes)?)
}
fn namespaces() -> Result<BTreeMap<String, String>> {
    ["user", "mnt", "pid", "net"]
        .into_iter()
        .map(|name| {
            Ok((
                name.to_owned(),
                std::fs::read_link(format!("/proc/self/ns/{name}"))?
                    .to_string_lossy()
                    .into_owned(),
            ))
        })
        .collect()
}
fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn held_hash(mut file: &File) -> Result<String> {
    use std::io::Seek;
    // These descriptors stay open across both readbacks. The shared hash
    // helper consumes from the current offset, so restart every full read.
    file.rewind()?;
    fs::hash(file)
}
fn trusted(pin: &FilePin) -> Result<(File, Identity)> {
    let tree = fs::Tree::open("/", 0)?;
    tree.parent(&fs::absolute_string(&pin.path)?)?;
    let (file, id) = files::open_pin(pin)?;
    ensure(
        id.uid == 0 && id.gid == 0 && id.nlink == 1 && id.mode & 0o022 == 0,
        "original-host input is not a protected root-owned regular inode",
    )?;
    ensure(
        held_hash(&file)? == pin.sha256 && fs::stat(&file)? == id,
        "original-host input changed",
    )?;
    Ok((file, id))
}
fn read<T: serde::de::DeserializeOwned>(pin: &FilePin, maximum: u64) -> Result<T> {
    let _held = trusted(pin)?;
    Ok(serde_json::from_slice(&files::read_pin(pin, maximum)?)?)
}
fn actual_pin(path: &Path) -> Result<FilePin> {
    let pin = files::pin_file(path).map_err(|e| format!("cannot pin {}: {e}", path.display()))?;
    trusted(&pin).map_err(|e| format!("untrusted original-host path {}: {e}", path.display()))?;
    Ok(pin)
}
fn original_chroot_layout(requested: &str, pin: &FilePin, resolution: &Value) -> Result<()> {
    ensure(
        pin.path == Path::new("/usr/lib/cargo/bin/coreutils/chroot")
            && pin.bytes == 11_807_104
            && pin.sha256 == "f84e76ea4da1e0c4e92254bd0d7dccdabe2c8b3098e734f27997dae3ee5d8e02"
            && resolution["guest_path"] == requested
            && resolution["resolved_path"] == pin.path.to_string_lossy().as_ref()
            && resolution["aliases"]
                .as_array()
                .is_some_and(|v| v.len() == 1)
            && resolution["aliases"][0]["path"] == requested
            && resolution["aliases"][0]["target"] == "../lib/cargo/bin/coreutils/chroot",
        "original source-bound uutils chroot alias/ELF differs",
    )
}
fn original_tool(requested: &str, pin: &FilePin, resolution: &Value) -> Result<(File, Identity)> {
    if requested != "/usr/bin/chroot" {
        return trusted(pin);
    }
    // The original distribution's uutils chroot is a protected symlink to its
    // normal multi-call ELF. This exact original read-only tool has 116 links;
    // no candidate input, output or other executable gains this exception.
    original_chroot_layout(requested, pin, resolution)?;
    fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&pin.path)?)?;
    let (file, id) = files::open_pin(pin)?;
    ensure(
        id.uid == 0
            && id.gid == 0
            && id.mode == 0o100755
            && id.nlink == 116
            && held_hash(&file)? == pin.sha256
            && fs::stat(&file)? == id,
        "original uutils hard-linked read-only executable identity differs",
    )?;
    Ok((file, id))
}
fn config<T: serde::de::DeserializeOwned>(path: &Path, expected: &str) -> Result<(T, FilePin)> {
    let pin = actual_pin(path)?;
    ensure(pin.sha256 == expected, "original-host plan digest differs")?;
    Ok((read(&pin, 2 * 1024 * 1024)?, pin))
}
fn allowed_work(path: &Path) -> Result<()> {
    let name = path
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or("work directory name missing")?;
    ensure(
        path.parent() == Some(Path::new(QUALIFICATION))
            && name.starts_with("original-initramfs-")
            && (20..=80).contains(&name.len())
            && name
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'),
        "original-host work must be a create-only protected qualification child",
    )
}
pub(super) fn original_context() -> Result<Value> {
    ensure(
        rustix::process::getuid().as_raw() == 0 && rustix::process::geteuid().as_raw() == 0,
        "original host root rights are required",
    )?;
    ensure(
        text("/proc/sys/kernel/osrelease", 128)?.trim() == ORIGINAL_KERNEL,
        "this is not the original Pocket4 kernel",
    )?;
    ensure(
        text("/proc/self/uid_map", 1024)?
            .split_whitespace()
            .collect::<Vec<_>>()
            == ["0", "0", "4294967295"],
        "original-host preparation requires the initial user namespace",
    )?;
    let root = std::fs::metadata("/")?;
    let pid1 = std::fs::metadata("/proc/1/root")?;
    let boot = std::fs::metadata("/boot")?;
    ensure(
        (root.dev(), root.ino()) == (pid1.dev(), pid1.ino()) && root.dev() == boot.dev(),
        "original host PID1/root/boot filesystem identity differs",
    )?;
    let device = std::fs::metadata(format!("/dev/disk/by-uuid/{ROOT_UUID}"))?;
    ensure(
        device.file_type().is_block_device() && device.rdev() == root.dev(),
        "the actual original root UUID is not the mounted block filesystem",
    )?;
    let mounts = text("/proc/self/mountinfo", 1024 * 1024)?;
    ensure(
        mounts.lines().any(|line| {
            let v: Vec<_> = line.split_whitespace().collect();
            v.get(4) == Some(&"/") && line.contains(" - ext4 ")
        }),
        "original root is not ext4",
    )?;
    let accounts = ["/etc/passwd", "/etc/group"]
        .into_iter()
        .map(|p| Ok((p.to_owned(), actual_pin(Path::new(p))?)))
        .collect::<Result<BTreeMap<_, _>>>()?;
    let mut metadata = BTreeMap::new();
    for path in [
        "/etc/passwd",
        "/etc/group",
        "/etc/shadow",
        "/etc/gshadow",
        "/etc/ssh",
        "/etc/ssh/sshd_config",
        "/home/alex",
    ] {
        let m = std::fs::symlink_metadata(path)?;
        ensure(
            !m.file_type().is_symlink(),
            "original preserved path is an alias",
        )?;
        metadata.insert(
            path,
            json!([
                m.dev(),
                m.ino(),
                m.mode(),
                m.uid(),
                m.gid(),
                m.nlink(),
                m.size(),
                m.mtime(),
                m.mtime_nsec(),
                m.ctime(),
                m.ctime_nsec()
            ]),
        );
    }
    let public_directories = PUBLIC_NAMESPACE_ROOTS
        .iter()
        .map(|path| {
            let (file, _parent) = public_namespace_directory(path)?;
            Ok(((*path).to_owned(), fs::stat(&file)?))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let status = actual_pin(Path::new("/var/lib/dpkg/status"))?;
    Ok(
        json!({"kernel":ORIGINAL_KERNEL,"root_uuid":ROOT_UUID,"root_identity":[root.dev(),root.ino()],
        "boot_id":text("/proc/sys/kernel/random/boot_id",128)?.trim(),"namespaces":namespaces()?,
        "account_files":accounts,"preserved_metadata":metadata,"dpkg_status":status,
        "public_namespace_directories":public_directories}),
    )
}
type SourceGuard = (String, Value, FilePin, Identity, File);
fn source_guards(target: &Value, original: &Value) -> Result<Vec<SourceGuard>> {
    ensure(
        target["schema"] == "droidloom-original-ubuntu-cold-preflight-v1"
            && target["kernel"] == ORIGINAL_KERNEL
            && target["root_uuid"] == ROOT_UUID
            && target["root_identity"] == original["root_identity"]
            && target["boot_id"] == original["boot_id"],
        "fresh actual original-host preflight differs",
    )?;
    let expected: BTreeSet<String> = [
        "/boot/grub/grub.cfg",
        "/boot/grub/grubenv",
        "/usr/bin/grub-script-check",
        "/usr/bin/grub-editenv",
        "/usr/sbin/update-grub",
        "/usr/sbin/grub-mkconfig",
        "/usr/sbin/mkinitramfs",
        "/usr/bin/dpkg",
        "/usr/bin/dpkg-deb",
    ]
    .into_iter()
    .map(str::to_owned)
    .chain([
        format!("/boot/vmlinuz-{ORIGINAL_KERNEL}"),
        format!("/boot/initrd.img-{ORIGINAL_KERNEL}"),
    ])
    .collect();
    let originals = target["public_originals"]
        .as_object()
        .ok_or("original public inventory missing")?;
    ensure(
        originals.keys().cloned().collect::<BTreeSet<_>>() == expected,
        "complete fixed original boot/tool inventory required",
    )?;
    let mut guards = Vec::new();
    for (path, row) in originals {
        let pin: FilePin = serde_json::from_value(row["pin"].clone())?;
        ensure(
            pin.path == Path::new(path),
            "original preflight substituted a source path",
        )?;
        let (file, id) = trusted(&pin)?;
        let identity = json!([
            id.dev,
            id.ino,
            id.mode,
            id.uid,
            id.gid,
            id.nlink,
            id.size,
            id.mtime_sec * 1_000_000_000 + id.mtime_nsec,
            id.ctime_sec * 1_000_000_000 + id.ctime_nsec
        ]);
        ensure(
            row["identity"] == identity,
            "original preflight inode identity changed",
        )?;
        guards.push((
            path.clone(),
            json!({"guest_path":path,"resolved_path":path,"aliases":[]}),
            pin,
            id,
            file,
        ));
    }
    for tool in TOOLS {
        let (pin, aliases) = files::resolve_public_file(Path::new("/"), tool)
            .map_err(|e| format!("cannot resolve original tool {tool}: {e}"))?;
        if *tool == PYTHON {
            ensure(
                pin.bytes == 7_477_160 && pin.sha256 == PYTHON_SHA,
                "fixed original Python differs",
            )?;
        }
        let (file, id) = original_tool(tool, &pin, &aliases)?;
        guards.push(((*tool).to_owned(), aliases, pin, id, file));
    }
    Ok(guards)
}
fn guard_readback(guards: &[SourceGuard]) -> Result<Value> {
    let mut out = Vec::new();
    let root = fs::Tree::open("/", 0)?;
    for (requested, aliases, pin, id, file) in guards {
        let (current, current_aliases) = files::resolve_public_file(Path::new("/"), requested)?;
        ensure(
            same_pin(&current, pin) && current_aliases == *aliases,
            &format!(
                "original requested tool path or its protected alias chain changed: {requested}"
            ),
        )?;
        ensure(
            fs::stat(file)? == *id
                && root.identity(&fs::absolute_string(&pin.path)?)? == *id
                && held_hash(file)? == pin.sha256
                && fs::stat(file)? == *id,
            &format!("original tool or boot source changed during preparation: {requested}"),
        )?;
        out.push(json!({"requested_path":requested,"aliases":aliases,"pin":pin,"identity":id}));
    }
    Ok(json!(out))
}
fn validate_materials(m: &Materials) -> Result<()> {
    ensure(
        m.schema == "droidloom.original-host-initramfs-materials.v3"
            && m.root_uuid == ROOT_UUID
            && m.original_kernel == ORIGINAL_KERNEL
            && m.kernel_release == KERNEL
            && m.kernel_sha256 == KERNEL_SHA
            && m.module_manifest.sha256 == MODULES_SHA
            && !m.physical_install
            && !m.qualification_boot_authorized
            && !m.production_ready,
        "normal original-host material scope differs",
    )?;
    ensure(
        m.packages.len() == 24 && m.required_initrd_members.len() == 5,
        "exact original native22 and public host/kernel materials required",
    )?;
    let names = m
        .packages
        .iter()
        .map(|r| r.name.as_str())
        .collect::<BTreeSet<_>>();
    let expected: BTreeSet<_> = [
        "libselinux1",
        "apparmor",
        "libapparmor1",
        "gdm3",
        "libgdm1",
        "gir1.2-gdm-1.0",
        "libnss-systemd",
        "libpam-systemd",
        "libsystemd-shared",
        "libsystemd0",
        "libudev1",
        "systemd",
        "systemd-resolved",
        "systemd-sysv",
        "systemd-timesyncd",
        "udev",
        "droidloom-shared-host",
        "droidloom-shared-kernel",
        "libselinux-dev",
        "libsystemd-dev",
        "libudev-dev",
        "systemd-cryptsetup",
        "systemd-dev",
        "systemd-oomd",
    ]
    .into_iter()
    .collect();
    ensure(
        names == expected
            && m.packages.iter().all(|p| {
                let architecture = if p.name == "systemd-dev" {
                    "all"
                } else {
                    "amd64"
                };
                p.architecture == architecture && !p.version.is_empty()
            }),
        "fixed original-host normal package family differs",
    )?;
    ensure(
        [
            &m.public_release_id,
            &m.deployment_id,
            &m.native_release_id,
            &m.native_closure,
            &m.cohort_sha256,
            &m.runtime_sha256,
        ]
        .iter()
        .all(|s| fs::valid_digest(s)),
        "normal source identity is not a SHA256",
    )?;
    for row in &m.required_initrd_members {
        crate::paths::parts(&row.source_path)?;
        crate::paths::parts(&row.initrd_path)?;
        ensure(
            row.bytes > 0
                && row.bytes < 64 * 1024 * 1024
                && fs::valid_digest(&row.sha256)
                && row.mode & !0o777 == 0,
            "required normal initrd member differs",
        )?;
    }
    validate_public_directories(&m.public_directories)?;
    Ok(())
}
fn save(path: &Path, value: &impl Serialize) -> Result<FilePin> {
    let mut body = serde_json::to_vec_pretty(value)?;
    body.push(b'\n');
    files::write_new(path, &body, 0o400)?;
    actual_pin(path)
}
fn run(work: &Path, name: &str, program: &str, args: Vec<String>, seconds: u64) -> Result<Value> {
    Ok(serde_json::to_value(files::run_logged(
        work, name, program, &args, seconds,
    )?)?)
}
fn original_package_read_locks() -> Result<Vec<File>> {
    // POSIX read locks conflict with actual dpkg/apt writers, unlike a separate
    // advisory BSD flock. Keep both original database lock descriptors alive.
    let mut locks = Vec::new();
    for path in ["/var/lib/dpkg/lock", "/var/lib/dpkg/lock-frontend"] {
        let file = File::from(rustix::fs::open(
            path,
            OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        rustix::fs::fcntl_lock(&file, FlockOperation::NonBlockingLockShared)?;
        locks.push(file);
    }
    Ok(locks)
}

pub fn prepare(path: &Path, expected: &str) -> Result<()> {
    let (plan, input): (Plan, FilePin) = config(path, expected)?;
    ensure(
        plan.schema == "droidloom.original-host-initramfs-plan.v1",
        "original-host initramfs plan schema",
    )?;
    allowed_work(&plan.work_directory)?;
    ensure(
        plan.public_release.path.file_name() == Some(std::ffi::OsStr::new("RELEASE.json"))
            && plan.native_release.path.file_name()
                == Some(std::ffi::OsStr::new("NATIVE-RELEASE.json"))
            && fs::valid_digest(&plan.native_release_id),
        "normal public/native source manifest required",
    )?;
    trusted(&plan.public_release)?;
    trusted(&plan.native_release)?;
    let before = original_context()?;
    let preflight: Value = read(&plan.target_preflight, 2 * 1024 * 1024)?;
    let guards = source_guards(&preflight, &before)?;
    let locks = original_package_read_locks()?;
    ensure(
        original_context()? == before,
        "original host changed before its package locks",
    )?;
    guard_readback(&guards)?;
    let work = &plan.work_directory;
    files::private_dir(work)?;
    let modules = work.join("controller");
    files::private_dir(&modules)?;
    for (name, bytes) in cold_modules::FILES {
        files::write_new(
            &modules.join(Path::new(name).file_name().ok_or("module basename")?),
            bytes,
            0o444,
        )?;
    }
    let module_guard = cold_modules::FILES
        .iter()
        .map(|(name, _)| actual_pin(&modules.join(Path::new(name).file_name().unwrap())))
        .collect::<Result<Vec<_>>>()?;
    let materials_path = work.join("MATERIALS.json");
    let script = "import sys; sys.path.insert(0, sys.argv.pop(1)); from cold_transaction import main; main()";
    let command = run(
        work,
        "admit-normal-materials",
        PYTHON,
        vec![
            "-I".into(),
            "-B".into(),
            "-c".into(),
            script.into(),
            fs::absolute_string(&modules)?,
            "initramfs-materials".into(),
            "--bundle".into(),
            fs::absolute_string(plan.public_release.path.parent().unwrap())?,
            "--release".into(),
            plan.public_release.sha256.clone(),
            "--native-bundle".into(),
            fs::absolute_string(plan.native_release.path.parent().unwrap())?,
            "--native-release".into(),
            plan.native_release_id.clone(),
            "--output".into(),
            fs::absolute_string(&materials_path)?,
        ],
        600,
    )?;
    let material_pin = actual_pin(&materials_path)?;
    let mut materials: Materials = read(&material_pin, 2 * 1024 * 1024)?;
    validate_materials(&materials)?;
    ensure(
        same_pin(&materials.public_release, &plan.public_release)
            && same_pin(&materials.native_release, &plan.native_release)
            && materials.native_release_id == plan.native_release_id,
        "admitted archives differ from original plan",
    )?;
    let packages = work.join("packages");
    files::private_dir(&packages)?;
    for (i, row) in materials.packages.iter_mut().enumerate() {
        trusted(&row.package)?;
        let destination = packages.join(format!("{i:02}.deb"));
        files::copy_pin(&row.package, &destination, 0o444)?;
        row.package = files::pin_file(&destination)?;
        row.package.path = PathBuf::from(format!("/inputs/{i:02}.deb"));
    }
    let build = work.join("build");
    files::private_dir(&build)?;
    for name in ["overlay-volatile", "view", "lower"] {
        files::private_dir(&work.join(name))?;
    }
    let producer = actual_pin(&std::env::current_exe()?)?;
    files::copy_pin(&producer, &build.join("producer"), 0o555)?;
    let stage = Stage {
        schema: "droidloom.original-host-initramfs-stage.v1".into(),
        work_directory: work.clone(),
        original: before.clone(),
        materials,
        producer,
        input: input.clone(),
    };
    let stage_pin = save(&build.join("INNER-INPUTS.json"), &stage)?;
    let namespace = run(
        work,
        "normal-original-host-namespace",
        "/usr/bin/unshare",
        vec![
            "--mount".into(),
            "--net".into(),
            "--ipc".into(),
            "--uts".into(),
            "--propagation=private".into(),
            fs::absolute_string(&build.join("producer"))?,
            "original-initramfs-namespace".into(),
            "--config".into(),
            fs::absolute_string(&stage_pin.path)?,
            "--config-sha256".into(),
            stage_pin.sha256.clone(),
        ],
        1800,
    );
    ensure(
        original_context()? == before,
        "original host database/accounts/boot context changed",
    )?;
    let guarded = guard_readback(&guards)?;
    for pin in &module_guard {
        trusted(pin)?;
    }
    trusted(&stage_pin)?;
    trusted(&input)?;
    let namespace = namespace?;
    let inner_pin = actual_pin(&build.join("BUILT.json"))?;
    let inner: Value = read(&inner_pin, 16 * 1024 * 1024)?;
    ensure(
        inner["schema"] == "droidloom.original-host-normal-initramfs-build.v1"
            && inner["stage_sha256"] == stage_pin.sha256
            && inner["package_count"] == 24
            && inner["kernel_release"] == KERNEL,
        "actual private normal initramfs result differs",
    )?;
    let image = actual_pin(&build.join("initrd.img"))?;
    ensure(
        inner["initrd"]["sha256"] == image.sha256 && inner["initrd"]["bytes"] == image.bytes,
        "actual initramfs output differs",
    )?;
    let result = json!({"schema":"droidloom.original-host-initramfs-prepared.v1","phase":"candidate_preparation",
        "input":input,"target_preflight":plan.target_preflight,"original_host":before,"original_files_unchanged":guarded,
        "normal_public_release":plan.public_release,"normal_native_release":plan.native_release,
        "normal_materials":material_pin,"normal_admission_command":command,"namespace_command":namespace,
        "actual_private_build":inner_pin,"initrd":image,"kernel_release":KERNEL,"kernel_sha256":KERNEL_SHA,
        "root_uuid":ROOT_UUID,"physical_package_database_modified":false,"original_accounts_replaced":false,
        "original_android_data_accessed":false,"default_boot_changed":false,"services_enabled":false,
        "qualification_boot_authorized":false,"permanent_activation_authorized":false,"production_ready":false,
        "remaining_qualification_inputs":["same_candidate_owned_calibration_and_runtime_mechanism",
            "original_account_and_independent_original_data_working_copy_identity","actual_original_host_file_contexts_readback",
            "same_candidate_selected_data_and_five_MAC_files","atomic_recovery_entry_and_maintenance_configuration"],
        "permanent_activation_requires":["selected_39_complete_business_and_common_gates","private_data_migration_acceptance",
            "actual_maintenance_and_original_Ubuntu_return"]});
    let receipt = save(&work.join("ORIGINAL-INITRAMFS-PREPARED.json"), &result)?;
    println!(
        "{}",
        json!({"receipt":receipt,"initrd":image,"phase":"candidate_preparation","production_ready":false})
    );
    drop(locks);
    Ok(())
}

fn private_mount_tree(raw: &str) -> Result<()> {
    ensure(!raw.trim().is_empty(), "private mount inventory is empty")?;
    for line in raw.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        let separator = fields
            .iter()
            .position(|s| *s == "-")
            .ok_or("mountinfo separator missing")?;
        ensure(
            separator >= 6
                && fields.len() >= separator + 4
                && fields[6..separator].iter().all(|s| {
                    !s.starts_with("shared:")
                        && !s.starts_with("master:")
                        && !s.starts_with("propagate_from:")
                }),
            "mount setup requires a recursively private mount tree",
        )?;
    }
    Ok(())
}
fn isolated_network() -> Result<()> {
    let network = text("/proc/net/dev", 65536)?;
    ensure(
        network
            .lines()
            .filter_map(|l| l.split_once(':').map(|r| r.0.trim()))
            .all(|name| name == "lo"),
        "private build has an external network interface",
    )
}
fn setup_namespace(stage: &Stage) -> Result<()> {
    ensure(
        stage.schema == "droidloom.original-host-initramfs-stage.v1",
        "private original-host stage schema",
    )?;
    // Only fixed source-bound mount setup runs in this private mount namespace
    // before the user namespace exists. Inherited locked child mounts prevent
    // cloning / as an overlay lower after entering a less privileged userns.
    let current = original_context()?;
    for key in [
        "kernel",
        "root_uuid",
        "root_identity",
        "boot_id",
        "account_files",
        "preserved_metadata",
        "dpkg_status",
    ] {
        ensure(
            current[key] == stage.original[key],
            "original host changed before private mount setup",
        )?;
    }
    let ns = &current["namespaces"];
    let original = &stage.original["namespaces"];
    ensure(
        ns["user"] == original["user"]
            && ns["pid"] == original["pid"]
            && ns["mnt"] != original["mnt"]
            && ns["net"] != original["net"],
        "fixed mount setup requires a new mount/network namespace on the original user namespace",
    )?;
    private_mount_tree(&text("/proc/self/mountinfo", 1024 * 1024)?)?;
    isolated_network()
}
fn readonly_mount(path: &Path) -> Result<String> {
    let raw = text("/proc/self/mountinfo", 1024 * 1024)?;
    private_mount_tree(&raw)?;
    let name = fs::absolute_string(path)?;
    let rows = raw
        .lines()
        .filter(|line| line.split_whitespace().nth(4) == Some(name.as_str()))
        .collect::<Vec<_>>();
    ensure(
        rows.len() == 1
            && rows[0]
                .split_whitespace()
                .nth(5)
                .is_some_and(|s| s.split(',').any(|v| v == "ro")),
        "required private bind mount is not actually readonly",
    )?;
    Ok(rows[0].to_owned())
}
fn mapped_namespace(stage: &Stage) -> Result<()> {
    ensure(
        stage.schema == "droidloom.original-host-initramfs-stage.v1",
        "private original-host stage schema",
    )?;
    for path in ["/proc/self/uid_map", "/proc/self/gid_map"] {
        ensure(
            text(path, 1024)?.split_whitespace().collect::<Vec<_>>() == ["0", "0", "65536"],
            "private normal package namespace needs the original complete UID/GID range",
        )?;
    }
    ensure(
        text("/proc/self/setgroups", 64)?.trim() == "allow",
        "normal service groups are unavailable",
    )?;
    let current = namespaces()?;
    for name in ["user", "mnt", "pid", "net"] {
        ensure(
            stage.original["namespaces"][name] != current[name],
            "required private namespace was not created",
        )?;
    }
    isolated_network()?;
    Ok(())
}
fn mount(work: &Path, name: &str, args: Vec<String>) -> Result<()> {
    run(work, name, "/usr/bin/mount", args, 30)?;
    Ok(())
}
fn prepare_mountpoint(root: &Path, guest: &str) -> Result<()> {
    ensure(
        ["/build", "/inputs", "/dev", "/proc", "/run", "/tmp", "/sys"].contains(&guest)
            || PRIVATE_STATE_PATHS.contains(&guest),
        "only fixed private mountpoints may be prepared",
    )?;
    let owner = rustix::process::geteuid().as_raw();
    let group = rustix::process::getegid().as_raw();
    let tree = fs::Tree::open(&fs::absolute_string(root)?, owner)?;
    match tree.identity(guest) {
        Ok(id) => {
            // This reads only the final inode through a protected parent FD.
            // The original sticky /tmp is overmounted without opening its
            // contents or changing its mode; no descendant gets an exception.
            ensure(
                id.mode & 0o170000 == 0o040000
                    && id.uid == owner
                    && id.gid == group
                    && (id.mode & 0o022 == 0 || (guest == "/tmp" && id.mode == 0o041777)),
                &format!(
                    "fixed private mountpoint is an alias, special or unprotected directory: {guest}"
                ),
            )?;
        }
        Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
            tree.mkdir(guest)?;
            rustix::fs::fchmod(&tree.dir(guest)?, Mode::from_raw_mode(0o755))?;
        }
        Err(e) => return Err(e),
    }
    Ok(())
}
pub fn namespace(path: &Path, expected: &str) -> Result<()> {
    let (stage, pin): (Stage, FilePin) = config(path, expected)?;
    allowed_work(&stage.work_directory)?;
    setup_namespace(&stage)?;
    validate_materials(&stage.materials)?;
    let work = &stage.work_directory;
    let view = work.join("view");
    ensure(
        pin.path == work.join("build/INNER-INPUTS.json"),
        "private namespace stage path differs",
    )?;
    // A distinct private superblock avoids nesting an overlay upper/work tree
    // in its own original-root lower filesystem. All transient package writes
    // disappear when this namespace retires; the normal image/evidence remain.
    let volatile = work.join("overlay-volatile");
    mount(
        work,
        "private-overlay-storage",
        vec![
            "-t".into(),
            "tmpfs".into(),
            "-o".into(),
            "nosuid,nodev,mode=0700,size=2G".into(),
            "tmpfs".into(),
            fs::absolute_string(&volatile)?,
        ],
    )?;
    for name in ["upper", "work"] {
        files::private_dir(&volatile.join(name))?;
    }
    // A nonrecursive bind excludes all original child mounts. Making it
    // readonly before the final userns also locks that flag in the child.
    let lower = work.join("lower");
    mount(
        work,
        "bind-original-lower",
        vec!["--bind".into(), "/".into(), fs::absolute_string(&lower)?],
    )?;
    mount(
        work,
        "readonly-original-lower",
        vec![
            "-o".into(),
            "remount,bind,ro,nosuid,nodev".into(),
            fs::absolute_string(&lower)?,
        ],
    )?;
    let lower_mount = readonly_mount(&lower)?;
    let lower_id = std::fs::metadata(&lower)?;
    ensure(
        json!([lower_id.dev(), lower_id.ino()]) == stage.original["root_identity"],
        "readonly lower is not the actual original root",
    )?;
    let options = format!(
        "lowerdir={},upperdir={},workdir={}",
        lower.display(),
        volatile.join("upper").display(),
        volatile.join("work").display()
    );
    mount(
        work,
        "mount-private-original-overlay",
        vec![
            "-t".into(),
            "overlay".into(),
            "-o".into(),
            options,
            "overlay".into(),
            fs::absolute_string(&view)?,
        ],
    )?;
    for name in ["/build", "/inputs", "/dev", "/proc", "/run", "/tmp", "/sys"]
        .into_iter()
        .chain(PRIVATE_STATE_PATHS.iter().copied())
    {
        prepare_mountpoint(&view, name)?;
    }
    for (name, source, dest) in [
        ("build", work.join("build"), "/build"),
        ("inputs", work.join("packages"), "/inputs"),
    ] {
        let target = view.join(&dest[1..]);
        mount(
            work,
            &format!("bind-{name}"),
            vec![
                "--bind".into(),
                fs::absolute_string(&source)?,
                fs::absolute_string(&target)?,
            ],
        )?;
        if name == "inputs" {
            mount(
                work,
                "readonly-inputs",
                vec![
                    "-o".into(),
                    "remount,bind,ro,nosuid,nodev".into(),
                    fs::absolute_string(&target)?,
                ],
            )?;
        }
    }
    for (index, dest) in ["/dev", "/run", "/tmp"]
        .into_iter()
        .chain(PRIVATE_STATE_PATHS.iter().copied())
        .enumerate()
    {
        let options = if dest == "/tmp" {
            "nosuid,nodev,mode=1777,size=1G"
        } else {
            "nosuid,nodev,mode=0755,size=64M"
        };
        mount(
            work,
            &format!("private-empty-{index}"),
            vec![
                "-t".into(),
                "tmpfs".into(),
                "-o".into(),
                options.into(),
                "tmpfs".into(),
                fs::absolute_string(&view.join(&dest[1..]))?,
            ],
        )?;
    }
    // Bind only these harmless original character devices into a new /dev.
    // No original block device or host runtime socket enters the build root.
    for (name, minor) in [
        ("null", 3),
        ("zero", 5),
        ("random", 8),
        ("urandom", 9),
        ("full", 7),
    ] {
        let original = std::fs::symlink_metadata(format!("/dev/{name}"))?;
        ensure(
            original.file_type().is_char_device()
                && original.rdev() == (0x100 | minor)
                && original.uid() == 0
                && original.gid() == 0,
            "fixed harmless original character device differs",
        )?;
        let target = view.join("dev").join(name);
        files::write_new(&target, b"", 0o600)?;
        mount(
            work,
            &format!("private-device-{name}"),
            vec![
                "--bind".into(),
                format!("/dev/{name}"),
                fs::absolute_string(&target)?,
            ],
        )?;
        mount(
            work,
            &format!("readonly-device-inode-{name}"),
            vec![
                "-o".into(),
                "remount,bind,ro,nosuid".into(),
                fs::absolute_string(&target)?,
            ],
        )?;
    }
    files::ensure_dir(&view, "/dev/pts", 0o755)?;
    mount(
        work,
        "private-devpts",
        vec![
            "-t".into(),
            "devpts".into(),
            "-o".into(),
            "newinstance,nosuid,noexec,mode=0620,ptmxmode=0666".into(),
            "devpts".into(),
            fs::absolute_string(&view.join("dev/pts"))?,
        ],
    )?;
    std::os::unix::fs::symlink("pts/ptmx", view.join("dev/ptmx"))?;
    std::os::unix::fs::symlink("/proc/self/fd", view.join("dev/fd"))?;
    mount(
        work,
        "private-hardware-sys",
        vec![
            "--bind".into(),
            "/sys".into(),
            fs::absolute_string(&view.join("sys"))?,
        ],
    )?;
    mount(
        work,
        "readonly-hardware-sys",
        vec![
            "-o".into(),
            "remount,bind,ro,nosuid,nodev,noexec".into(),
            fs::absolute_string(&view.join("sys"))?,
        ],
    )?;
    let mount_observations = save(
        &work.join("PREPARED-MOUNTS.json"),
        &json!({
        "schema":"droidloom.original-host-private-mounts.v1","setup_namespaces":namespaces()?,
        "readonly_lower":lower_mount,"original_root_identity":[lower_id.dev(),lower_id.ino()],
        "readonly_inputs":readonly_mount(&view.join("inputs"))?,"readonly_sys":readonly_mount(&view.join("sys"))?}),
    )?;
    // The setup process still sees the original root. Put all package scripts
    // in a *nested* PID namespace, whose PID1 has already chrooted. They cannot
    // escape through /proc/1/root back to the setup process's original root.
    let nested=run(work,"private-normal-package-and-initramfs","/usr/bin/unshare",vec![
        "--user".into(),"--map-users=0,0,65536".into(),"--map-groups=0,0,65536".into(),"--setgroups=allow".into(),
        "--mount".into(),"--propagation=private".into(),
        "--pid".into(),"--fork".into(),"--kill-child".into(),format!("--mount-proc={}",view.join("proc").display()),
        "/usr/bin/chroot".into(),fs::absolute_string(&view)?,"/usr/bin/setpriv".into(),
        "--bounding-set=-all,+chown,+dac_override,+fowner,+fsetid,+setgid,+setuid,+setpcap,+net_bind_service,+audit_write,+setfcap".into(),
        "--inh-caps=-all".into(),"--ambient-caps=-all".into(),"--no-new-privs".into(),
        "/build/producer".into(),"original-initramfs-build".into(),
        "--config".into(),"/build/INNER-INPUTS.json".into(),"--config-sha256".into(),pin.sha256.clone()],1500)?;
    save(
        &work.join("NAMESPACE-ENDED.json"),
        &json!({"schema":"droidloom.original-host-build-namespace-ended.v1","command":nested,"stage":pin,"prepared_mounts":mount_observations}),
    )?;
    Ok(())
}

fn constrained_capabilities() -> Result<Value> {
    let status = text("/proc/self/status", 65536)?;
    let fields = status
        .lines()
        .filter_map(|line| line.split_once(':').map(|(k, v)| (k, v.trim())))
        .collect::<BTreeMap<_, _>>();
    let allowed: u64 = [0, 1, 3, 4, 6, 7, 8, 10, 29, 31]
        .into_iter()
        .fold(0, |mask, bit| mask | (1u64 << bit));
    for name in ["CapEff", "CapPrm", "CapBnd"] {
        let value = u64::from_str_radix(fields.get(name).ok_or("capability status missing")?, 16)?;
        ensure(
            value & !allowed == 0,
            "private package process retains mount/global-device/MAC authority",
        )?;
    }
    for name in ["CapInh", "CapAmb"] {
        ensure(
            u64::from_str_radix(fields.get(name).ok_or("capability status missing")?, 16)? == 0,
            "private process has inherited or ambient capabilities",
        )?;
    }
    ensure(
        fields.get("NoNewPrivs") == Some(&"1"),
        "private package process can acquire new privileges",
    )?;
    Ok(json!({"allowed_mask":format!("{allowed:016x}"),"actual":fields}))
}

type Roster = BTreeMap<String, (String, String, String)>;
fn roster(raw: &[u8]) -> Result<Roster> {
    let records = dependencies::control(std::str::from_utf8(raw)?)?;
    let mut result = BTreeMap::new();
    for row in records {
        let status = dependencies::field(&row, "Status")?;
        let purged = status == "purge ok not-installed";
        ensure(
            status == "install ok installed"
                || status == "hold ok installed"
                || status == "deinstall ok config-files"
                || purged,
            "normal source contains an incomplete package transaction",
        )?;
        let name = dependencies::field(&row, "Package")?.to_owned();
        let retained = |key: &str| -> Result<String> {
            if purged && !row.contains_key(key) {
                Ok(String::new())
            } else {
                Ok(dependencies::field(&row, key)?.to_owned())
            }
        };
        ensure(
            result
                .insert(
                    name,
                    (
                        retained("Version")?,
                        retained("Architecture")?,
                        status.to_owned(),
                    ),
                )
                .is_none(),
            "duplicate original package identity",
        )?;
    }
    ensure(!result.is_empty(), "empty original package database")?;
    Ok(result)
}
fn expected_roster(before: &Roster, packages: &[Package]) -> Result<Roster> {
    let mut expected = before.clone();
    for package in packages {
        ensure(
            package.name.starts_with("droidloom-shared-")
                || before.get(&package.name).is_some_and(|(_, arch, status)| {
                    arch == &package.architecture
                        && (status == "install ok installed" || status == "hold ok installed")
                }),
            "original native package family is not already installed with the selected architecture",
        )?;
        expected.insert(
            package.name.clone(),
            (
                package.version.clone(),
                package.architecture.clone(),
                "install ok installed".into(),
            ),
        );
    }
    Ok(expected)
}
fn apt_archive_path(package: &Package) -> Result<PathBuf> {
    ensure(
        !package.name.is_empty()
            && package.name.len() <= 128
            && package
                .name
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"+.-".contains(&b))
            && !package.version.is_empty()
            && package.version.len() <= 256
            && package
                .version
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b".+:~-".contains(&b))
            && matches!(package.architecture.as_str(), "amd64" | "all"),
        "normal Debian archive cache identity",
    )?;
    // The complete source installer's normal offline transaction prepopulates
    // APT's canonical archive cache. --no-download must not rely on acquiring
    // and renaming an unrelated /inputs/NN.deb before dpkg sees the archive.
    Ok(Path::new("/var/cache/apt/archives").join(format!(
        "{}_{}_{}.deb",
        package.name,
        package.version.replace(':', "%3a"),
        package.architecture
    )))
}
fn validate_public_directories(directories: &BTreeMap<String, u32>) -> Result<()> {
    ensure(
        (2..=4096).contains(&directories.len()),
        "bounded complete public directory inventory",
    )?;
    for path in PUBLIC_NAMESPACE_ROOTS {
        ensure(
            directories.get(*path) == Some(&0o755),
            "normal packages must own the fixed public namespace roots",
        )?;
    }
    for (path, mode) in directories {
        crate::paths::parts(path)?;
        ensure(
            matches!(*mode, 0o700 | 0o755)
                && !PRIVATE_STATE_PATHS
                    .iter()
                    .any(|p| path.as_str() == *p || path.starts_with(&format!("{p}/")))
                && (path == "/usr"
                    || path.starts_with("/usr/")
                    || path == "/boot"
                    || path.starts_with("/boot/droidloom/")
                    || path == "/boot/droidloom"
                    || path == "/etc"
                    || path == "/etc/selinux"
                    || path.starts_with("/etc/selinux/")
                    || path == "/etc/systemd"
                    || path == "/etc/systemd/system"
                    || path == "/etc/systemd/system/user-runtime-dir@.service.d"
                    || path == "/var"
                    || path == "/var/lib"
                    || path == "/var/lib/droidloom-mac-calibration"
                    || path == "/var/lib/droidloom-public-apks"),
            "normal public directory scope differs",
        )?;
    }
    Ok(())
}
fn legacy_public_namespace(path: &str, id: &Identity) -> bool {
    PUBLIC_NAMESPACE_ROOTS.contains(&path) && id.uid == 1000 && id.gid == 1000 && id.mode == 0o40755
}
fn public_namespace_directory(path: &str) -> Result<(File, File)> {
    ensure(
        PUBLIC_NAMESPACE_ROOTS.contains(&path),
        "only the fixed public namespace root may change owner",
    )?;
    let (parent, name) = fs::Tree::open("/", 0)?.parent(path)?;
    let file = File::from(rustix::fs::openat(
        &parent,
        name.as_str(),
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    Ok((file, parent))
}
fn claim_private_public_namespaces(work: &Path, stage: &Stage) -> Result<FilePin> {
    // This runs only after build() proves the isolated overlay, private PID1,
    // constrained capabilities and hidden original private trees. Neither
    // recursive chown nor original-host directory repair is an operation here.
    let mut held = Vec::new();
    let mut originals = Vec::new();
    for path in PUBLIC_NAMESPACE_ROOTS {
        ensure(
            stage.materials.public_directories.get(*path) == Some(&0o755),
            "normal archive does not own the public namespace",
        )?;
        let (file, parent) = public_namespace_directory(path)?;
        let before = fs::stat(&file)?;
        let original: Identity =
            serde_json::from_value(stage.original["public_namespace_directories"][*path].clone())?;
        ensure(
            (before.uid, before.gid, before.mode) == (original.uid, original.gid, original.mode)
                && ((before.uid == 0 && before.gid == 0 && before.mode == 0o40755)
                    || legacy_public_namespace(path, &before)),
            "unreviewed original public namespace ownership",
        )?;
        originals.push(json!({"path":path,"original_host":original,"private_before":before,"normal_mode":0o755}));
        held.push(((*path).to_owned(), file, parent, before));
    }
    let intent = save(
        &work.join("PUBLIC-DIRECTORY-CLAIM-INTENT.json"),
        &json!({
        "schema":"droidloom.private-public-directory-claim-intent.v1",
        "public_release_id":stage.materials.public_release_id,"directories":originals,
        "recursive":false,"physical_install":false}),
    )?;
    let mut rows = Vec::new();
    for (path, file, parent, before) in held {
        ensure(
            fs::stat(&file)? == before,
            "private public namespace changed before ownership repair",
        )?;
        if before.uid != 0 || before.gid != 0 {
            rustix::fs::fchown(
                &file,
                Some(rustix::process::Uid::from_raw(0)),
                Some(rustix::process::Gid::from_raw(0)),
            )?;
            rustix::fs::fchmod(&file, Mode::from_raw_mode(0o755))?;
            file.sync_all()?;
            parent.sync_all()?;
        }
        let after = fs::stat(&file)?;
        let current = fs::stat(&fs::Tree::open("/", 0)?.dir(&path)?)?;
        ensure(
            (after.dev, after.ino) == (before.dev, before.ino)
                && current == after
                && after.uid == 0
                && after.gid == 0
                && after.mode == 0o40755,
            "private normal public namespace ownership readback differs",
        )?;
        rows.push(json!({"path":path,"before":before,"after":after,"recursive":false}));
    }
    save(
        &work.join("PUBLIC-DIRECTORY-CLAIM.json"),
        &json!({
        "schema":"droidloom.private-public-directory-claim.v1","intent":intent,"directories":rows,
        "physical_install":false,"qualification_boot_authorized":false}),
    )
}
fn readback_public_directories(m: &Materials) -> Result<Value> {
    let root = fs::Tree::open("/", 0)?;
    let mut rows = Vec::new();
    for (path, mode) in &m.public_directories {
        let file = root
            .dir(path)
            .map_err(|e| format!("normal public directory {path}: {e}"))?;
        let id = fs::stat(&file)?;
        ensure(
            id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == *mode,
            &format!("normal public directory owner/mode differs: {path}"),
        )?;
        rows.push(json!({"path":path,"identity":id,"normal_mode":mode}));
    }
    Ok(json!(rows))
}
fn effective_initrd_path(relative: &str, layered: bool) -> Result<&str> {
    if !layered {
        return Ok(relative);
    }
    let (section, effective) = relative.split_once('/').unwrap_or((relative, ""));
    let early = section == "early"
        || section.strip_prefix("early").is_some_and(|n| {
            !n.starts_with('0')
                && n.bytes().all(|b| b.is_ascii_digit())
                && n.parse::<u32>().is_ok_and(|v| v >= 2)
        });
    ensure(
        section == "main" || early,
        "unmkinitramfs produced an unknown archive layer",
    )?;
    Ok(effective)
}
fn public_initrd_path(effective: &str) -> Result<()> {
    ensure(
        !PRIVATE_STATE_PATHS
            .iter()
            .any(|p| effective.starts_with(&format!("{}/", &p[1..])))
            && !effective.starts_with("etc/ssh/ssh_host")
            && !["etc/shadow", "etc/gshadow"].contains(&effective),
        "private account or Android data appeared in normal initramfs",
    )
}
fn walk(
    root: &Path,
    path: &Path,
    layered: bool,
    rows: &mut Vec<Value>,
    total: &mut u64,
) -> Result<()> {
    let mut paths = std::fs::read_dir(path)?
        .map(|r| r.map(|v| v.path()))
        .collect::<std::io::Result<Vec<_>>>()?;
    paths.sort();
    for path in paths {
        ensure(rows.len() < 50000, "normal initramfs has too many members")?;
        let metadata = std::fs::symlink_metadata(&path)?;
        let relative = path.strip_prefix(root)?.to_string_lossy().into_owned();
        let effective = effective_initrd_path(&relative, layered)?;
        public_initrd_path(effective)?;
        let mut row = json!({"path":relative,"effective_path":effective,"mode":metadata.mode(),"uid":metadata.uid(),"gid":metadata.gid(),"nlink":metadata.nlink()});
        if metadata.is_dir() {
            row["kind"] = json!("directory");
            rows.push(row);
            walk(root, &path, layered, rows, total)?;
        } else if metadata.is_file() {
            *total = total
                .checked_add(metadata.len())
                .ok_or("normal initrd length overflow")?;
            ensure(
                *total <= 1024 * 1024 * 1024,
                "normal unpacked initramfs exceeds one GiB",
            )?;
            let pin = files::pin_file(&path)?;
            row["kind"] = json!("file");
            row["bytes"] = json!(pin.bytes);
            row["sha256"] = json!(pin.sha256);
            rows.push(row);
        } else if metadata.file_type().is_symlink() {
            row["kind"] = json!("symlink");
            row["target"] = json!(std::fs::read_link(&path)?.to_string_lossy());
            rows.push(row);
        } else {
            return Err("normal initramfs has an unreviewed special file".into());
        }
    }
    Ok(())
}
fn readback(work: &Path, m: &Materials) -> Result<Value> {
    readback_image(
        work,
        m,
        Path::new("/build/initrd.img"),
        &m.module_manifest,
        true,
    )
}
fn readback_image(
    work: &Path,
    m: &Materials,
    image: &Path,
    module_source: &FilePin,
    check_installed_candidate: bool,
) -> Result<Value> {
    let module_pin = actual_pin(&module_source.path)?;
    ensure(
        module_pin.bytes == m.module_manifest.bytes
            && module_pin.sha256 == m.module_manifest.sha256,
        "normally admitted module manifest differs",
    )?;
    let module: Value = read(&module_pin, 4 * 1024 * 1024)?;
    ensure(
        module["release"] == KERNEL && module["count"] == 6797,
        "complete original signed module family missing",
    )?;
    let index = module["rows"]
        .as_array()
        .ok_or("module rows missing")?
        .iter()
        .map(|r| Ok((string(r, "relative")?, r)))
        .collect::<Result<BTreeMap<_, _>>>()?;
    let unpack = work.join("unpacked");
    let command = run(
        work,
        "normal-initramfs-full-unpack",
        "/usr/bin/unmkinitramfs",
        vec![fs::absolute_string(image)?, fs::absolute_string(&unpack)?],
        120,
    )?;
    let possible = [unpack.clone(), unpack.join("main")]
        .into_iter()
        .filter(|p| p.join("init").is_file())
        .collect::<Vec<_>>();
    ensure(
        possible.len() == 1,
        "normal initramfs must contain one effective initial root",
    )?;
    let root = &possible[0];
    let mut required = Vec::new();
    for wanted in &m.required_initrd_members {
        if check_installed_candidate {
            let (source, _) = files::resolve_public_file(Path::new("/"), &wanted.source_path)?;
            ensure(
                source.bytes == wanted.bytes && source.sha256 == wanted.sha256,
                "normally installed candidate initrd source differs",
            )?;
        }
        let (actual, aliases) = files::resolve_public_file(root, &wanted.initrd_path)?;
        let id = files::open_pin(&actual)?.1;
        ensure(
            actual.bytes == wanted.bytes
                && actual.sha256 == wanted.sha256
                && id.uid == 0
                && id.gid == 0
                && id.mode & 0o7777 == wanted.mode,
            "normal initramfs omitted or changed an exact candidate ELF/script",
        )?;
        required.push(json!({"required":wanted,"actual":actual,"identity":id,"aliases":aliases}));
    }
    let original_init = actual_pin(Path::new("/usr/share/initramfs-tools/init"))?;
    let actual_init = files::pin_file(&root.join("init"))?;
    ensure(
        original_init.bytes == actual_init.bytes && original_init.sha256 == actual_init.sha256,
        "normal upstream /init was changed",
    )?;
    let mut filesystem_checkers = Vec::new();
    for path in FILESYSTEM_CHECKERS {
        let (source, source_aliases) = files::resolve_public_file(Path::new("/"), path)?;
        let (source_file, source_id) = trusted(&source)?;
        let (actual, aliases) = files::resolve_public_file(root, path)?;
        let id = files::open_pin(&actual)?.1;
        ensure(
            actual.bytes == source.bytes
                && actual.sha256 == source.sha256
                && id.uid == 0
                && id.gid == 0
                && id.mode == source_id.mode
                && fs::stat(&source_file)? == source_id,
            "normal initramfs omitted or changed an original filesystem checker",
        )?;
        filesystem_checkers.push(
            json!({"requested_path":path,"source":source,"source_aliases":source_aliases,
            "source_identity":source_id,"actual":actual,"identity":id,"aliases":aliases}),
        );
    }
    let order = std::fs::read(root.join("scripts/init-bottom/ORDER"))?;
    ensure(
        order
            .split(|b| *b == b'\n')
            .filter(|line| {
                line.windows(b"droidloom-early-custody".len())
                    .any(|w| w == b"droidloom-early-custody")
            })
            .count()
            == 1,
        "normal early custody is not scheduled exactly once",
    )?;
    let mut rows = Vec::new();
    let mut total = 0;
    walk(
        &unpack,
        &unpack,
        root == &unpack.join("main"),
        &mut rows,
        &mut total,
    )?;
    let needle = format!("/modules/{KERNEL}/");
    let mut found = 0;
    for row in &rows {
        let path = string(row, "effective_path")?;
        if row["kind"] == "file" && (path.ends_with(".ko") || path.contains(".ko.")) {
            let (_, relative) = path
                .split_once(&needle)
                .ok_or("normal initramfs contains a foreign-kernel module")?;
            let expected = index
                .get(relative)
                .ok_or("initramfs module is absent from the signed normal manifest")?;
            ensure(
                row["bytes"] == expected["bytes"] && row["sha256"] == expected["sha256"],
                "initramfs module changed from its signed source",
            )?;
            found += 1;
        }
    }
    ensure(
        found > 0,
        "normal initramfs contains no retained shared-kernel modules",
    )?;
    let inventory = save(
        &work.join("INITRAMFS-INVENTORY.json"),
        &json!({"schema":"droidloom.original-host-initramfs-inventory.v1","members":rows,"total_regular_bytes":total}),
    )?;
    Ok(
        json!({"normal_unpack_command":command,"complete_inventory":inventory,"required_members":required,
        "stock_init":actual_init,"original_filesystem_checkers":filesystem_checkers,
        "signed_normal_modules_readback":found,"module_manifest":module_pin}),
    )
}
pub fn build(path: &Path, expected: &str) -> Result<()> {
    let (stage, pin): (Stage, FilePin) = config(path, expected)?;
    mapped_namespace(&stage)?;
    validate_materials(&stage.materials)?;
    ensure(
        path == Path::new("/build/INNER-INPUTS.json") && std::process::id() == 1,
        "package build must be private chroot PID1",
    )?;
    let root = std::fs::metadata("/")?;
    let pid1 = std::fs::metadata("/proc/1/root")?;
    ensure(
        (root.dev(), root.ino()) == (pid1.dev(), pid1.ino())
            && json!([root.dev(), root.ino()]) != stage.original["root_identity"],
        "package scripts can see an original-host process root",
    )?;
    ensure(
        text("/proc/self/mountinfo", 1024 * 1024)?
            .lines()
            .any(|line| {
                let p: Vec<_> = line.split_whitespace().collect();
                p.get(4) == Some(&"/") && line.contains(" - overlay ")
            }),
        "normal private build root is not the isolated overlay",
    )?;
    for path in PRIVATE_STATE_PATHS {
        ensure(
            std::fs::read_dir(path)?.next().is_none(),
            "original private state is visible to package scripts",
        )?;
    }
    let work = Path::new("/build");
    let capabilities = constrained_capabilities()?;
    // A readonly-to-readonly remount changes no host state even if a regression
    // accidentally retained authority. Successful remount is still a rejection.
    let probe = files::run_logged(
        work,
        "readonly-remount-authority-probe",
        "/usr/bin/mount",
        &["-o".into(), "remount,bind,ro".into(), "/sys".into()],
        10,
    );
    ensure(
        probe.is_err(),
        "private process can remount its readonly hardware view",
    )?;
    let probe_pin = actual_pin(&work.join("readonly-remount-authority-probe.json"))?;
    let probe: Value = read(&probe_pin, 65536)?;
    ensure(
        probe["timed_out"] == false && probe["exit_code"].as_i64().is_some_and(|v| v != 0),
        "remount probe did not return a real privilege denial",
    )?;
    let log: FilePin = serde_json::from_value(probe["log"].clone())?;
    let denial = String::from_utf8(files::read_pin(&log, 65536)?)?;
    ensure(
        denial.contains("permission denied") || denial.contains("Operation not permitted"),
        "remount probe failed for an unrelated reason",
    )?;
    let account_before = ["/etc/passwd", "/etc/group"]
        .into_iter()
        .map(|p| Ok((p.to_owned(), actual_pin(Path::new(p))?)))
        .collect::<Result<BTreeMap<_, _>>>()?;
    ensure(
        serde_json::to_value(&account_before)? == stage.original["account_files"],
        "private root account source differs from actual original host",
    )?;
    let status = actual_pin(Path::new("/var/lib/dpkg/status"))?;
    ensure(
        status.sha256 == stage.original["dpkg_status"]["sha256"],
        "private normal database differs before installation",
    )?;
    let before = roster(&files::read_pin(&status, 32 * 1024 * 1024)?)?;
    let wanted = expected_roster(&before, &stage.materials.packages)?;
    let public_claim = claim_private_public_namespaces(work, &stage)?;
    for p in &stage.materials.packages {
        trusted(&p.package)?;
    }
    let _cache = fs::Tree::open("/", 0)?.dir("/var/cache/apt/archives")?;
    let mut archives = Vec::new();
    for package in &stage.materials.packages {
        let destination = apt_archive_path(package)?;
        files::copy_pin(&package.package, &destination, 0o444)?;
        let actual = actual_pin(&destination)?;
        ensure(
            actual.bytes == package.package.bytes && actual.sha256 == package.package.sha256,
            "normal private APT archive cache differs from the admitted source",
        )?;
        archives.push(actual);
    }
    let policy = Path::new("/usr/sbin/policy-rc.d");
    // Only this private overlay is mutable. Preserve any original policy file
    // as an audit pin before replacing the private name with the fixed 101.
    let previous_policy = if policy.exists() {
        Some(actual_pin(policy)?)
    } else {
        None
    };
    if policy.exists() {
        std::fs::remove_file(policy)?;
    }
    files::write_new(policy, POLICY_RC, 0o755)?;
    let policy_pin = actual_pin(policy)?;
    let mut apt = vec![
        "DEBIAN_FRONTEND=noninteractive".into(),
        "SYSTEMD_OFFLINE=1".into(),
        "APT_LISTCHANGES_FRONTEND=none".into(),
        "/usr/bin/apt-get".into(),
        "-o".into(),
        "Dir::Etc::sourcelist=-".into(),
        "-o".into(),
        "Dir::Etc::sourceparts=-".into(),
        "-o".into(),
        "DPkg::Options::=--force-confold".into(),
        "--yes".into(),
        "--no-download".into(),
        "--no-install-recommends".into(),
        "--no-remove".into(),
        "--reinstall".into(),
    ];
    let mut simulation = apt.clone();
    simulation.extend(["--simulate".into(), "install".into()]);
    simulation.extend(
        archives
            .iter()
            .map(|p| p.path.to_string_lossy().into_owned()),
    );
    let simulated = run(
        work,
        "normal-apt-simulation",
        "/usr/bin/env",
        simulation,
        120,
    )?;
    let simulation_log: FilePin = serde_json::from_value(simulated["log"].clone())?;
    let text = String::from_utf8(files::read_pin(&simulation_log, 4 * 1024 * 1024)?)?;
    let allowed = stage
        .materials
        .packages
        .iter()
        .map(|p| p.name.as_str())
        .collect::<BTreeSet<_>>();
    for line in text.lines() {
        ensure(
            !line.starts_with("Remv "),
            "normal candidate simulation would remove an original package",
        )?;
        if let Some(value) = line.strip_prefix("Inst ") {
            let name = value
                .split_whitespace()
                .next()
                .ok_or("empty normal install simulation")?
                .split(':')
                .next()
                .unwrap();
            ensure(
                allowed.contains(name),
                "normal candidate requires an unadmitted extra package",
            )?;
        }
    }
    apt.push("install".into());
    apt.extend(
        archives
            .iter()
            .map(|p| p.path.to_string_lossy().into_owned()),
    );
    let installed = run(work, "normal-apt-install", "/usr/bin/env", apt, 900)?;
    trusted(&policy_pin)?;
    let audit = run(
        work,
        "normal-dpkg-audit",
        "/usr/bin/dpkg",
        vec!["--audit".into()],
        60,
    )?;
    let audit_log: FilePin = serde_json::from_value(audit["log"].clone())?;
    ensure(
        files::read_pin(&audit_log, 1024 * 1024)?
            .iter()
            .all(|b| b.is_ascii_whitespace()),
        "normal candidate package audit is not empty",
    )?;
    let after = actual_pin(Path::new("/var/lib/dpkg/status"))?;
    ensure(
        roster(&files::read_pin(&after, 32 * 1024 * 1024)?)? == wanted,
        "normal private install changed unselected original package versions or states",
    )?;
    files::copy_pin(&after, &work.join("PRIVATE-DPKG-STATUS"), 0o400)?;
    for (path, pin) in &account_before {
        let current = actual_pin(Path::new(path))?;
        ensure(
            current.bytes == pin.bytes && current.sha256 == pin.sha256,
            "normal private installation changed original account identities",
        )?;
    }
    let public_directories = readback_public_directories(&stage.materials)?;
    let native_hook =
        Path::new("/etc/initramfs-tools/hooks/droidloom-source-bound-native-libraries");
    files::write_new(native_hook, NATIVE_HOOK, 0o755)?;
    let hook_pin = actual_pin(native_hook)?;
    // The upstream fsck hook supports this normal setting. The original root
    // was proved ext4; exposing its raw block device to package scripts is not
    // needed for automatic type discovery inside the private root.
    let fstype =
        Path::new("/etc/initramfs-tools/conf.d/droidloom-source-bound-original-root-fstype");
    files::write_new(fstype, ORIGINAL_FSTYPE, 0o644)?;
    let fstype_pin = actual_pin(fstype)?;
    let built = run(
        work,
        "normal-mkinitramfs",
        "/usr/sbin/mkinitramfs",
        vec![
            "-c".into(),
            "gzip".into(),
            "-o".into(),
            "/build/initrd.img".into(),
            KERNEL.into(),
        ],
        300,
    )?;
    trusted(&hook_pin)?;
    trusted(&fstype_pin)?;
    let observed = readback(work, &stage.materials)?;
    let image = actual_pin(Path::new("/build/initrd.img"))?;
    ensure(
        image.bytes > 1024 && image.bytes <= 512 * 1024 * 1024,
        "bounded normal original-host initramfs",
    )?;
    let report = json!({"schema":"droidloom.original-host-normal-initramfs-build.v1","stage_sha256":pin.sha256,
        "kernel_release":KERNEL,"package_count":24,"private_namespaces":namespaces()?,"root_identity":[root.dev(),root.ino()],
        "normal_simulation":simulated,"normal_install":installed,"normal_audit":audit,"normal_archive_cache":archives,
        "public_directory_claim":public_claim,"complete_public_directories":public_directories,
        "constrained_capabilities":capabilities,"actual_remount_denial":probe_pin,
        "status_before":status,"status_after":after,"retained_private_status":actual_pin(&work.join("PRIVATE-DPKG-STATUS"))?,"original_account_files":account_before,
        "policy_rc_101":policy_pin,"previous_private_policy_rc":previous_policy,"normal_native_hook":hook_pin,
        "original_fstype_configuration":fstype_pin,
        "normal_mkinitramfs":built,"full_readback":observed,"initrd":image,"physical_install":false,
        "qualification_boot_authorized":false,"permanent_activation_authorized":false});
    save(&work.join("BUILT.json"), &report)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_namespace_claim_cannot_authorize_private_paths_or_other_owners() {
        let mut id = Identity {
            dev: 1,
            ino: 2,
            mode: 0o40755,
            uid: 1000,
            gid: 1000,
            nlink: 2,
            size: 1,
            mtime_sec: 0,
            mtime_nsec: 0,
            ctime_sec: 0,
            ctime_nsec: 0,
        };
        assert!(legacy_public_namespace("/usr/lib/droidloom", &id));
        assert!(legacy_public_namespace("/usr/share/droidloom", &id));
        for path in [
            "/usr/lib/droidloom/old",
            "/var/lib/droidloom",
            "/home/alex",
            "/usr/lib",
        ] {
            assert!(!legacy_public_namespace(path, &id));
        }
        id.uid = 1001;
        assert!(!legacy_public_namespace("/usr/lib/droidloom", &id));
        id.uid = 1000;
        id.mode = 0o40777;
        assert!(!legacy_public_namespace("/usr/lib/droidloom", &id));
        let mut dirs = PUBLIC_NAMESPACE_ROOTS
            .iter()
            .map(|p| ((*p).to_owned(), 0o755))
            .collect::<BTreeMap<_, _>>();
        assert!(validate_public_directories(&dirs).is_ok());
        dirs.insert("/var/lib/droidloom/users".into(), 0o755);
        assert!(validate_public_directories(&dirs).is_err());
        dirs.remove("/var/lib/droidloom/users");
        dirs.insert("/usr/share/droidloom".into(), 0o777);
        assert!(validate_public_directories(&dirs).is_err());
    }
    #[test]
    fn offline_archive_cache_names_preserve_identity_and_reject_path_injection() {
        let mut package = Package {
            role: "systemd-dev".into(),
            name: "systemd-dev".into(),
            version: "1:259.9-0ubuntu0.1+p4gentmp1".into(),
            architecture: "all".into(),
            package: FilePin {
                path: "/inputs/00.deb".into(),
                bytes: 1,
                sha256: "0".repeat(64),
            },
        };
        assert_eq!(
            apt_archive_path(&package).unwrap(),
            Path::new("/var/cache/apt/archives/systemd-dev_1%3a259.9-0ubuntu0.1+p4gentmp1_all.deb")
        );
        for version in ["../other", "x/y", "x\n", "x%2fy", ""] {
            package.version = version.into();
            assert!(apt_archive_path(&package).is_err());
        }
        package.version = "1".into();
        package.name = "../../other".into();
        assert!(apt_archive_path(&package).is_err());
        package.name = "systemd-dev".into();
        package.architecture = "arm64".into();
        assert!(apt_archive_path(&package).is_err());
    }
    #[test]
    fn residual_package_records_are_preserved_and_cannot_supply_native_installation() {
        let raw=b"Package: systemd\nStatus: install ok installed\nVersion: old\nArchitecture: amd64\n\nPackage: legacy\nStatus: deinstall ok config-files\nVersion: 1\nArchitecture: all\n\nPackage: purged\nStatus: purge ok not-installed\n";
        let before = roster(raw).unwrap();
        assert_eq!(before.len(), 3);
        let package = Package {
            role: "systemd".into(),
            name: "systemd".into(),
            version: "new".into(),
            architecture: "amd64".into(),
            package: FilePin {
                path: "/inputs/0.deb".into(),
                bytes: 1,
                sha256: "0".repeat(64),
            },
        };
        let expected = expected_roster(&before, &[package.clone()]).unwrap();
        assert_eq!(expected["legacy"], before["legacy"]);
        assert_eq!(expected["purged"], before["purged"]);
        let mut changed = expected.clone();
        changed.remove("legacy");
        assert_ne!(changed, expected);
        let mut residual_native = before.clone();
        residual_native.get_mut("systemd").unwrap().2 = "deinstall ok config-files".into();
        assert!(expected_roster(&residual_native, &[package.clone()]).is_err());
        let mut other_arch = before;
        other_arch.get_mut("systemd").unwrap().1 = "i386".into();
        assert!(expected_roster(&other_arch, &[package]).is_err());
    }
    #[test]
    #[ignore = "requires actual original Pocket4 public package database and admitted materials; read-only"]
    fn actual_original_package_model_retains_every_status_record() {
        let context = original_context().unwrap();
        let locks = original_package_read_locks().unwrap();
        assert_eq!(original_context().unwrap(), context);
        let status = actual_pin(Path::new("/var/lib/dpkg/status")).unwrap();
        let raw = files::read_pin(&status, 32 * 1024 * 1024).unwrap();
        let records = dependencies::control(std::str::from_utf8(&raw).unwrap()).unwrap();
        let before = roster(&raw).unwrap();
        assert_eq!(before.len(), records.len());
        let materials_pin = FilePin {
            path:
                "/var/lib/droidloom-qualification/original-initramfs-normal-4b91-r2/MATERIALS.json"
                    .into(),
            bytes: 8381,
            sha256: "56559487023853db8ed187b89890c534c72e77d15efd9bc04b15a1049dbb56c4".into(),
        };
        let materials: Materials = read(&materials_pin, 2 * 1024 * 1024).unwrap();
        validate_materials(&materials).unwrap();
        let after = expected_roster(&before, &materials.packages).unwrap();
        let selected = materials
            .packages
            .iter()
            .map(|r| r.name.as_str())
            .collect::<BTreeSet<_>>();
        let mut counts = BTreeMap::new();
        for (name, row) in &before {
            *counts.entry(row.2.clone()).or_insert(0usize) += 1;
            if !selected.contains(name.as_str()) {
                assert_eq!(after.get(name), Some(row));
            }
        }
        assert_eq!(counts.get("deinstall ok config-files"), Some(&25));
        assert_eq!(counts.get("install ok installed"), Some(&2366));
        assert_eq!(original_context().unwrap(), context);
        trusted(&status).unwrap();
        println!(
            "{}",
            json!({"schema":"droidloom.original-package-model-readback-test.v1",
            "status":status,"materials":materials_pin,"actual_source_records":records.len(),
            "retained_source_records":before.len(),"status_counts":counts,"expected_candidate_records":after.len(),
            "selected_packages":materials.packages.len(),"posix_shared_locks":locks.len(),"physical_install":false})
        );
        drop(locks);
    }
    #[test]
    fn fixed_sticky_tmp_mountpoint_is_preserved_without_opening_descendants() {
        use std::os::unix::fs::PermissionsExt;
        let root = tempfile::tempdir().unwrap();
        let tmp = root.path().join("tmp");
        std::fs::create_dir(&tmp).unwrap();
        std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o1777)).unwrap();
        let before = std::fs::symlink_metadata(&tmp).unwrap();
        prepare_mountpoint(root.path(), "/tmp").unwrap();
        let after = std::fs::symlink_metadata(&tmp).unwrap();
        assert_eq!(
            (
                before.dev(),
                before.ino(),
                before.mode(),
                before.ctime(),
                before.ctime_nsec()
            ),
            (
                after.dev(),
                after.ino(),
                after.mode(),
                after.ctime(),
                after.ctime_nsec()
            )
        );
        assert!(prepare_mountpoint(root.path(), "/tmp/child").is_err());
        prepare_mountpoint(root.path(), "/build").unwrap();
        assert_eq!(
            std::fs::metadata(root.path().join("build")).unwrap().mode() & 0o777,
            0o755
        );
        let run = root.path().join("run");
        std::fs::create_dir(&run).unwrap();
        std::fs::set_permissions(&run, std::fs::Permissions::from_mode(0o1777)).unwrap();
        assert!(prepare_mountpoint(root.path(), "/run").is_err());
        std::os::unix::fs::symlink("tmp", root.path().join("inputs")).unwrap();
        assert!(prepare_mountpoint(root.path(), "/inputs").is_err());
    }
    #[test]
    fn mount_setup_rejects_shared_or_slave_propagation_before_any_mount() {
        let root = "31 22 259:2 / / rw,relatime - ext4 /dev/nvme0n1p2 rw\n";
        private_mount_tree(root).unwrap();
        for optional in ["shared:7", "master:4", "propagate_from:2"] {
            assert!(private_mount_tree(&root.replace(" - ", &format!(" {optional} - "))).is_err());
        }
        assert!(private_mount_tree("").is_err());
        assert!(private_mount_tree("31 22 - ext4 /dev/root rw").is_err());
    }
    #[test]
    fn repeated_held_hash_reads_the_whole_inode_and_detects_changed_bytes() {
        use std::io::{Seek, SeekFrom, Write};
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"abc").unwrap();
        let identity = fs::stat(&file).unwrap();
        let expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        assert_eq!(held_hash(&file).unwrap(), expected);
        assert_eq!(held_hash(&file).unwrap(), expected);
        file.seek(SeekFrom::Start(1)).unwrap();
        assert_eq!(held_hash(&file).unwrap(), expected);
        assert_eq!(fs::stat(&file).unwrap(), identity);
        file.seek(SeekFrom::Start(2)).unwrap();
        file.write_all(b"d").unwrap();
        assert_ne!(held_hash(&file).unwrap(), expected);
    }
    #[test]
    #[ignore = "requires the exact original Pocket4 preflight; read-only, never prepares a root"]
    fn actual_original_source_guards_survive_locks_and_two_readbacks() {
        let path = Path::new(
            "/var/lib/droidloom-qualification/p4-original-initramfs-inputs-4b91-r1/PLAN.json",
        );
        let (plan, input): (Plan, FilePin) = config(
            path,
            "aeae05b27cd6a7929091be7324a05608dafcaca3dea97bb7cb426bb406502056",
        )
        .unwrap();
        assert_eq!(plan.schema, "droidloom.original-host-initramfs-plan.v1");
        allowed_work(&plan.work_directory).unwrap();
        assert!(!plan.work_directory.try_exists().unwrap());
        let before = original_context().unwrap();
        let preflight: Value = read(&plan.target_preflight, 2 * 1024 * 1024).unwrap();
        let guards = source_guards(&preflight, &before).unwrap();
        let locks = original_package_read_locks().unwrap();
        assert_eq!(locks.len(), 2);
        assert_eq!(original_context().unwrap(), before);
        let first = guard_readback(&guards).unwrap();
        let second = guard_readback(&guards).unwrap();
        assert_eq!(first, second);
        assert_eq!(original_context().unwrap(), before);
        assert!(!plan.work_directory.try_exists().unwrap());
        println!(
            "{}",
            json!({"schema":"droidloom.original-source-guards-readback-test.v1",
            "input":input,"guard_count":guards.len(),"posix_shared_lock_count":locks.len(),
            "readbacks":2,"source_guards":second,"work_created":false,"physical_install":false})
        );
        drop(locks);
    }
    #[test]
    fn original_chroot_uses_the_readers_full_resolution_object() {
        let pin = FilePin {
            path: "/usr/lib/cargo/bin/coreutils/chroot".into(),
            bytes: 11_807_104,
            sha256: "f84e76ea4da1e0c4e92254bd0d7dccdabe2c8b3098e734f27997dae3ee5d8e02".into(),
        };
        let resolution = json!({"guest_path":"/usr/bin/chroot","resolved_path":pin.path,
            "aliases":[{"path":"/usr/bin/chroot","target":"../lib/cargo/bin/coreutils/chroot","identity":{"uid":0}}]});
        original_chroot_layout("/usr/bin/chroot", &pin, &resolution).unwrap();
        assert!(original_chroot_layout("/usr/bin/chroot", &pin, &resolution["aliases"]).is_err());
        let mut changed = resolution.clone();
        changed["resolved_path"] = json!("/usr/bin/other");
        assert!(original_chroot_layout("/usr/bin/chroot", &pin, &changed).is_err());
        changed = resolution.clone();
        changed["aliases"][0]["target"] = json!("/untrusted/tool");
        assert!(original_chroot_layout("/usr/bin/chroot", &pin, &changed).is_err());
    }
    #[test]
    fn normal_main_and_early_archive_paths_preserve_public_members() {
        for (raw, effective) in [
            ("main/usr/lib/libc.so.6", "usr/lib/libc.so.6"),
            (
                "early/kernel/x86/microcode/GenuineIntel.bin",
                "kernel/x86/microcode/GenuineIntel.bin",
            ),
            (
                "early2/kernel/x86/microcode/AuthenticAMD.bin",
                "kernel/x86/microcode/AuthenticAMD.bin",
            ),
        ] {
            assert_eq!(effective_initrd_path(raw, true).unwrap(), effective);
            public_initrd_path(effective).unwrap();
        }
        assert_eq!(
            effective_initrd_path("usr/bin/sh", false).unwrap(),
            "usr/bin/sh"
        );
        for raw in ["unknown/etc/passwd", "early0/a", "early01/a", "earlyx/a"] {
            assert!(effective_initrd_path(raw, true).is_err(), "{raw}");
        }
    }
    #[test]
    fn every_normal_archive_layer_rejects_private_payloads() {
        for prefix in ["", "main/", "early/", "early2/"] {
            for path in [
                "etc/shadow",
                "etc/gshadow",
                "etc/ssh/ssh_host_ed25519_key",
                "home/alex/private",
                "root/private",
                "var/lib/droidloom/data/user",
                "var/lib/droidloom-maintenance/private",
                "var/lib/droidloom-qualification/data-working-copy/private",
            ] {
                let raw = format!("{prefix}{path}");
                let effective = effective_initrd_path(&raw, !prefix.is_empty()).unwrap();
                assert!(public_initrd_path(effective).is_err(), "{raw}");
            }
        }
    }
    #[test]
    fn only_private_qualification_work_names_are_admitted() {
        assert!(
            allowed_work(Path::new(
                "/var/lib/droidloom-qualification/original-initramfs-test-r1"
            ))
            .is_ok()
        );
        for p in [
            "/boot/original-initramfs-test-r1",
            "/var/lib/droidloom-qualification/original-initramfs-../x",
            "/var/lib/droidloom-qualification/other",
            "/var/lib/droidloom-qualification/original-initramfs-x,lowerdir=bad",
        ] {
            assert!(allowed_work(Path::new(p)).is_err(), "{p}");
        }
    }
    #[test]
    fn actual_package_roster_rejects_partial_or_duplicate_states() {
        let valid =
            "Package: systemd\nStatus: install ok installed\nVersion: 259.9\nArchitecture: amd64\n";
        assert_eq!(roster(valid.as_bytes()).unwrap().len(), 1);
        assert!(roster(valid.replace("ok installed", "ok unpacked").as_bytes()).is_err());
        assert!(roster(format!("{valid}\n{valid}").as_bytes()).is_err());
    }
    #[test]
    fn staging_cannot_replace_a_missing_native_family_with_a_new_install() {
        let before = Roster::from([(
            "systemd".into(),
            ("old".into(), "amd64".into(), "install ok installed".into()),
        )]);
        let package = Package {
            role: "systemd".into(),
            name: "systemd".into(),
            version: "new".into(),
            architecture: "amd64".into(),
            package: FilePin {
                path: "/inputs/0.deb".into(),
                bytes: 1,
                sha256: "0".repeat(64),
            },
        };
        assert_eq!(
            expected_roster(&before, &[package.clone()]).unwrap()["systemd"].0,
            "new"
        );
        assert!(expected_roster(&Roster::new(), &[package]).is_err());
    }
    #[test]
    fn plan_has_no_arbitrary_commands_or_approval_flags() {
        let pin = json!({"path":"/protected/manifest.json","bytes":1,"sha256":"0".repeat(64)});
        let mut plan = json!({"schema":"droidloom.original-host-initramfs-plan.v1",
            "work_directory":"/var/lib/droidloom-qualification/original-initramfs-test-r1",
            "public_release":pin,"native_release":pin,"native_release_id":"0".repeat(64),"target_preflight":pin});
        assert!(serde_json::from_value::<Plan>(plan.clone()).is_ok());
        plan["passed"] = json!(true);
        assert!(serde_json::from_value::<Plan>(plan).is_err());
    }
}
