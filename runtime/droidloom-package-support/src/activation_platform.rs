//! Create-only staging of the exact Pocket4 kernel and native library batch.
//! This module never writes a live boot entry, installs a Debian package, changes
//! a service, or issues runtime authority. Its receipts describe bytes only.
use super::{
    Result,
    activation_files::{self as files, FilePin, HeldFile},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    os::{fd::AsRawFd, unix::fs::MetadataExt},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

const BOARD: &str = include_str!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);
const KERNEL_SOURCE: &str = include_str!("../../../packaging/ubuntu/linux/source.lock.json");
const SELINUX_SOURCE: &str = include_str!("../../../packaging/ubuntu/libselinux/source.lock.json");
const HOOK: &[u8] = include_bytes!("../../droidloom-early-boot/initramfs-hook");
const CUSTODY: &[u8] = include_bytes!("../../droidloom-early-boot/init-bottom");
const MIB: u64 = 1024 * 1024;
// Output pins of the admitted normal producers. These are not runtime evidence.
const MODULE_MANIFEST: (u64, &str) = (
    2144597,
    "5399a707d1aa2b8511a936dbc1b056891613f6043b8eafe0a1c0ad5c45eb7fa8",
);
const MODULE_FIXTURE: (u64, &str) = (
    5685234,
    "ff2017733d4739d6d3e15f3e20cda928eb8798c6490b41c4828ccbe6539233fd",
);
const BASE_INITRD: (u64, &str) = (
    10520919,
    "a95032f5bf74cd8c8dde63d04709e7b7584bff060584c1ad70c8a04d8cb71a67",
);
const SELINUX_DEB: (u64, &str) = (
    91320,
    "90794d3dfcabcfec6687f2f3279fdb7133536234a31639a39352747a6fadd84a",
);
const APPARMOR_DEB: (u64, &str) = (
    51804,
    "ccc039b1512c0b87975428b0c1d91fc2f74a028a844b79767341ec13d781528e",
);
const SELINUX_LIBRARY: (u64, &str) = (
    199120,
    "4dab059ee57d5be56bdf21db5e5bcc56e881d354010c7b3eaa0027c662692e9b",
);
const APPARMOR_LIBRARY: (u64, &str) = (
    89056,
    "86a87926294b49dba460ea815dc7123a21a65777982984f8e028b61c1e78cb63",
);

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct KernelInputs {
    pub material: FilePin,
    pub image: FilePin,
    pub module_root: PathBuf,
    pub fixture_manifest: FilePin,
    pub normal_module_manifest: FilePin,
    pub normal_initrd: FilePin,
    pub build_receipt: FilePin,
    pub source_comparison: FilePin,
    pub source_manifest: FilePin,
    pub module_signing_public_der: FilePin,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct NativeLibraryInputs {
    pub candidate: FilePin,
    pub package: FilePin,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct PreparedInitrd {
    pub image: FilePin,
    pub construction_receipt: FilePin,
    pub boot_receipt: FilePin,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct PlatformInputs {
    pub schema: String,
    pub kernel: KernelInputs,
    pub initrd: PreparedInitrd,
    pub libselinux: NativeLibraryInputs,
    pub libapparmor: NativeLibraryInputs,
}

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn object(file: &HeldFile, limit: u64) -> Result<Value> {
    Ok(serde_json::from_slice(&file.read_all(limit)?)?)
}
fn matches_pin(value: &Value, pin: &FilePin) -> bool {
    value["bytes"] == pin.bytes && value["sha256"] == pin.sha256
}
fn pinned(pin: &FilePin, fixed: (u64, &str)) -> Result<()> {
    require(
        pin.bytes == fixed.0 && pin.sha256 == fixed.1,
        "platform input differs from the admitted normal batch",
    )
}
fn from_value(value: &Value) -> Result<FilePin> {
    Ok(FilePin {
        path: value["path"]
            .as_str()
            .ok_or("missing ordinary source path")?
            .into(),
        bytes: value["bytes"]
            .as_u64()
            .ok_or("missing ordinary source size")?,
        sha256: value["sha256"]
            .as_str()
            .ok_or("missing ordinary source digest")?
            .into(),
    })
}

/// Hold each directory itself; do not substitute a named path after a rename.
struct Directory {
    path: PathBuf,
    fd: File,
    dev: u64,
    ino: u64,
}
impl Directory {
    fn open(path: &Path, private: bool) -> Result<Self> {
        let (parent, name) = files::parent(path)?;
        let raw = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        use std::os::fd::FromRawFd;
        let fd = unsafe { File::from_raw_fd(raw) };
        let m = fd.metadata()?;
        require(
            m.is_dir()
                && m.uid() == 0
                && m.gid() == 0
                && m.mode() & 0o7022 == 0
                && (!private || m.mode() & 0o7777 == 0o700),
            "platform directory is not protected root-owned storage",
        )?;
        Ok(Self {
            path: path.into(),
            fd,
            dev: m.dev(),
            ino: m.ino(),
        })
    }
    fn revalidate(&self) -> Result<()> {
        let actual = Self::open(&self.path, false)?;
        let m = self.fd.metadata()?;
        require(
            (m.dev(), m.ino(), actual.dev, actual.ino) == (self.dev, self.ino, self.dev, self.ino),
            "original platform directory was replaced or renamed",
        )
    }
}

fn relative(value: &str) -> Result<&str> {
    require(
        !value.is_empty()
            && value.len() <= 1024
            && value.is_ascii()
            && !value.starts_with('/')
            && !value.contains('\\')
            && !value.bytes().any(|b| b.is_ascii_control())
            && !value
                .split('/')
                .any(|p| p.is_empty() || p == "." || p == ".."),
        "unsafe platform member path",
    )?;
    Ok(value)
}
fn parent_for(root: &Path, name: &str) -> Result<PathBuf> {
    relative(name)?;
    let path = Path::new(name);
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        files::ensure_dir(root, parent.to_str().ok_or("non-UTF8 platform parent")?)?;
    }
    Ok(root.join(path))
}

fn module_members(
    manifest: &Value,
    normal: &Value,
    release: &str,
    source: &Value,
) -> Result<BTreeMap<String, (u64, String)>> {
    require(
        manifest["schema"] == "droidloom.ubuntu-public-fixture-manifest.v1"
            && manifest["target_kernel_release"] == release
            && manifest["guest_qualified"] == false
            && manifest["kernel"]["complete_installed_tree"] == true
            && normal["schema"] == "p4-normal-kernel-installed-module-manifest-v1"
            && normal["release"] == release
            && normal["count"] == 6797
            && normal["all_pkcs7_signatures_verified"] == true
            && normal["all_vermagic_exact"] == true,
        "incomplete original kernel material batch",
    )?;
    let prefix = format!("usr/lib/modules/{release}");
    let mut wanted = BTreeMap::new();
    let rows = normal["rows"]
        .as_array()
        .ok_or("normal kernel module rows missing")?;
    let indexes = normal["indexes"]
        .as_array()
        .ok_or("normal kernel indexes missing")?;
    require(
        rows.len() == 6797 && indexes.len() == 15,
        "normal kernel module/index cardinality differs",
    )?;
    for (entries, modules) in [(rows, true), (indexes, false)] {
        for row in entries {
            let path = relative(row["relative"].as_str().ok_or("missing kernel member")?)?;
            if modules {
                require(
                    path.starts_with("kernel/")
                        && path.ends_with(".ko")
                        && row["pkcs7_signature_verified"] == true
                        && row["vermagic"]
                            == format!("{release} SMP preempt mod_unload modversions"),
                    "normal module signature or vermagic record differs",
                )?;
            } else {
                require(
                    !path.contains('/') && path.starts_with("modules."),
                    "unrelated kernel index",
                )?;
            }
            let bytes = row["bytes"].as_u64().ok_or("missing module size")?;
            let sha = row["sha256"].as_str().ok_or("missing module digest")?;
            require(
                bytes > 0
                    && bytes <= 128 * MIB
                    && files::valid_digest(sha)
                    && wanted
                        .insert(format!("{prefix}/{path}"), (bytes, sha.into()))
                        .is_none(),
                "duplicate or invalid normal kernel member",
            )?;
        }
    }
    let config = &source["config"];
    wanted.insert(
        format!("{prefix}/config-{release}"),
        (
            config["bytes"]
                .as_u64()
                .ok_or("missing source config size")?,
            config["sha256"]
                .as_str()
                .ok_or("missing source config digest")?
                .into(),
        ),
    );
    let mut actual = BTreeMap::new();
    let mut names = BTreeSet::new();
    let mut dirs = BTreeSet::new();
    for entry in manifest["entries"]
        .as_array()
        .ok_or("kernel fixture entries missing")?
    {
        let path = entry["path"]
            .as_str()
            .ok_or("missing kernel fixture path")?;
        let path = relative(
            path.strip_prefix('/')
                .ok_or("kernel fixture name is not absolute")?,
        )?;
        require(
            names.insert(path.to_owned())
                && entry["source"]["uid"] == 0
                && entry["source"]["gid"] == 0
                && entry["xattrs"].as_object().is_some_and(|o| o.is_empty()),
            "kernel fixture has duplicate paths, unrelated owners or extended state",
        )?;
        let in_tree = path == prefix || path.starts_with(&(prefix.clone() + "/"));
        match entry["content"]["kind"].as_str() {
            Some("directory") => {
                require(
                    (in_tree || ["usr", "usr/lib", "usr/lib/modules"].contains(&path))
                        && entry["source"]["mode"] == 0o40755
                        && ["ancestor_directory", "target_module"]
                            .contains(&entry["component"].as_str().unwrap_or("")),
                    "kernel directory escapes the installed module tree",
                )?;
                dirs.insert(path.to_owned());
            }
            Some("regular") => {
                require(
                    in_tree
                        && entry["component"] == "target_module"
                        && entry["source"]["mode"] == 0o100644
                        && entry["source"]["nlink"] == 1,
                    "kernel fixture member is not an ordinary root-owned file",
                )?;
                actual.insert(
                    path.to_owned(),
                    (
                        entry["source"]["size"]
                            .as_u64()
                            .ok_or("kernel size missing")?,
                        entry["content"]["sha256"]
                            .as_str()
                            .ok_or("kernel digest missing")?
                            .into(),
                    ),
                );
            }
            _ => {
                return Err(
                    "kernel fixture contains a link, special file or unsupported member".into(),
                );
            }
        }
    }
    require(
        actual == wanted,
        "kernel fixture and normal producer do not contain the same complete module set",
    )?;
    for name in wanted.keys() {
        let mut path = Path::new(name).parent();
        while let Some(parent) = path.filter(|p| !p.as_os_str().is_empty()) {
            require(
                dirs.contains(parent.to_str().ok_or("invalid kernel parent")?),
                "kernel ancestor omitted",
            )?;
            path = parent.parent();
        }
    }
    Ok(wanted)
}

/// Reopens the normal producers' fixed full manifests for the installer; a
/// caller-supplied staged receipt cannot introduce another module path.
pub(super) fn installation_module_members(
    input: &KernelInputs,
) -> Result<BTreeMap<String, (u64, String)>> {
    pinned(&input.fixture_manifest, MODULE_FIXTURE)?;
    pinned(&input.normal_module_manifest, MODULE_MANIFEST)?;
    let board: Value = serde_json::from_str(BOARD)?;
    let source: Value = serde_json::from_str(KERNEL_SOURCE)?;
    let release = board["kernel"]["release"]
        .as_str()
        .ok_or("compiled kernel release missing")?;
    require(
        source["candidate_release"] == release && board["kernel"]["sha256"] == input.image.sha256,
        "installation module generation differs from the compiled board",
    )?;
    let fixture = HeldFile::open(&input.fixture_manifest, 8 * MIB)?;
    let normal = HeldFile::open(&input.normal_module_manifest, 4 * MIB)?;
    let members = module_members(
        &object(&fixture, 8 * MIB)?,
        &object(&normal, 4 * MIB)?,
        release,
        &source,
    )?;
    fixture.revalidate()?;
    normal.revalidate()?;
    Ok(members)
}

fn scan_module_tree(root: &Path) -> Result<BTreeMap<String, bool>> {
    fn walk(root: &Path, path: &Path, out: &mut BTreeMap<String, bool>) -> Result<()> {
        require(
            out.len() <= 9000,
            "module tree exceeds the admitted member budget",
        )?;
        for row in fs::read_dir(path)? {
            let path = row?.path();
            let name = path
                .strip_prefix(root)?
                .to_str()
                .ok_or("non-UTF8 kernel path")?
                .to_owned();
            relative(&name)?;
            let m = fs::symlink_metadata(&path)?;
            require(
                m.uid() == 0
                    && m.gid() == 0
                    && (m.is_dir() && m.mode() & 0o7777 == 0o755
                        || m.is_file() && m.mode() & 0o7777 == 0o644 && m.nlink() == 1),
                "actual module tree has a link, special file or changed metadata",
            )?;
            require(
                out.insert(name, m.is_dir()).is_none(),
                "duplicate actual module member",
            )?;
            if m.is_dir() {
                walk(root, &path, out)?;
            }
        }
        Ok(())
    }
    let mut out = BTreeMap::new();
    walk(root, root, &mut out)?;
    Ok(out)
}

pub(super) fn stage_kernel(input: &KernelInputs, root: &Path, work: &Path) -> Result<Value> {
    let board: Value = serde_json::from_str(BOARD)?;
    let source: Value = serde_json::from_str(KERNEL_SOURCE)?;
    let release = board["kernel"]["release"]
        .as_str()
        .ok_or("missing compiled kernel release")?;
    require(
        source["candidate_release"] == release && board["kernel"]["sha256"] == input.image.sha256,
        "kernel is outside the selected board/source batch",
    )?;
    pinned(&input.fixture_manifest, MODULE_FIXTURE)?;
    pinned(&input.normal_module_manifest, MODULE_MANIFEST)?;
    pinned(&input.normal_initrd, BASE_INITRD)?;
    require(
        matches_pin(&source["full_source_comparison"], &input.source_comparison)
            && matches_pin(&source["full_source_manifest"], &input.source_manifest),
        "kernel source custody differs from the compiled source lock",
    )?;
    let material_file = HeldFile::open(&input.material, MIB)?;
    let material = object(&material_file, MIB)?;
    for (name, pin) in [
        ("image", &input.image),
        ("fixture_manifest", &input.fixture_manifest),
        ("normal_module_manifest", &input.normal_module_manifest),
        ("normal_initrd", &input.normal_initrd),
    ] {
        require(
            matches_pin(&material[name], pin),
            "normal kernel material member differs",
        )?;
    }
    let manifest_file = HeldFile::open(&input.fixture_manifest, 16 * MIB)?;
    let normal_file = HeldFile::open(&input.normal_module_manifest, 8 * MIB)?;
    let manifest = object(&manifest_file, 16 * MIB)?;
    let normal = object(&normal_file, 8 * MIB)?;
    require(
        manifest["kernel"]["binding"]["image_sha256"] == input.image.sha256
            && manifest["kernel"]["binding"]["module_manifest_sha256"]
                == input.normal_module_manifest.sha256
            && manifest["kernel"]["binding"]["config_sha256"] == source["config"]["sha256"],
        "normal kernel fixture binding differs",
    )?;
    let mut custody = Vec::new();
    for (name, pin, max) in [
        ("build_receipt", &input.build_receipt, MIB),
        ("source_comparison", &input.source_comparison, MIB),
        ("source_manifest", &input.source_manifest, 64 * MIB),
        (
            "module_signing_public_der",
            &input.module_signing_public_der,
            64 * 1024,
        ),
    ] {
        require(
            matches_pin(&normal[name], pin),
            "normal kernel source receipt changed",
        )?;
        custody.push(HeldFile::open(pin, max)?);
    }
    let wanted = module_members(&manifest, &normal, release, &source)?;
    let original = Directory::open(&input.module_root, false)?;
    require(
        !input.module_root.starts_with(root) && !root.starts_with(&input.module_root),
        "kernel source and stage overlap",
    )?;
    let actual = scan_module_tree(&input.module_root)?;
    let expected: BTreeMap<String, bool> = manifest["entries"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| {
            (
                e["path"].as_str().unwrap()[1..].to_owned(),
                e["content"]["kind"] == "directory",
            )
        })
        .collect();
    require(
        actual == expected,
        "actual module root has missing or extra entries",
    )?;
    let mut outputs = Vec::new();
    for (name, (bytes, sha256)) in wanted {
        original.revalidate()?;
        let pin = FilePin {
            path: input.module_root.join(&name),
            bytes,
            sha256,
        };
        let held = HeldFile::open(&pin, 128 * MIB)?;
        require(
            held.identity().uid == 0
                && held.identity().gid == 0
                && held.identity().mode == 0o100644,
            "original kernel module lost its normal metadata",
        )?;
        outputs.push(held.copy_new(&parent_for(root, &name)?, 0o644)?);
    }
    original.revalidate()?;
    require(
        scan_module_tree(&input.module_root)? == expected,
        "original module namespace changed while staged",
    )?;
    let image = HeldFile::open(&input.image, 64 * MIB)?;
    let installed = image.copy_new(
        &parent_for(root, &format!("boot/vmlinuz-{release}"))?,
        0o644,
    )?;
    let config_path = format!("usr/lib/modules/{release}/config-{release}");
    let config = HeldFile::open(&files::pin_file(&root.join(&config_path))?, MIB)?;
    let installed_config =
        config.copy_new(&parent_for(root, &format!("boot/config-{release}"))?, 0o644)?;
    let evidence = files::ensure_dir(work, "platform-kernel-evidence")?;
    let mut retained = Vec::new();
    for (name, held) in [
        ("MODULES.json", &normal_file),
        ("MANIFEST.json", &manifest_file),
        ("KERNEL-MATERIAL.json", &material_file),
    ] {
        retained.push(held.copy_new(&evidence.join(name), 0o400)?);
    }
    for held in &custody {
        held.revalidate()?;
    }
    Ok(
        json!({"release":release,"kernel":installed,"config":installed_config,
        "module_files":outputs,"normal_custody":input,"retained_manifests":retained,
        "normal_signature_manifest_bound":true,"runtime_qualified":false}),
    )
}

/// Execute only a held, root-owned distribution reader. No shell and no service.
struct OwnedReader {
    child: std::process::Child,
    reaped: bool,
}
impl Drop for OwnedReader {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}
fn reader_tool(
    work: &Path,
    name: &str,
    program: &str,
    args: &[String],
    limit: u64,
) -> Result<FilePin> {
    require(
        ["/usr/bin/dpkg-deb", "/usr/bin/gzip"].contains(&program),
        "unsupported platform reader",
    )?;
    relative(name)?;
    let executable = HeldFile::open(&files::pin_file(Path::new(program))?, 16 * MIB)?;
    require(
        executable.identity().uid == 0
            && executable.identity().gid == 0
            && executable.identity().mode & 0o111 != 0,
        "platform reader is not a protected root executable",
    )?;
    let output_path = work.join(format!("{name}.out"));
    let error_path = work.join(format!("{name}.err"));
    let out = files::new_file(&output_path, 0o600)?;
    let error = files::new_file(&error_path, 0o600)?;
    let child = Command::new(format!("/proc/self/fd/{}", executable.file().as_raw_fd()))
        .args(args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LC_ALL", "C")
        .current_dir(work)
        .stdin(Stdio::null())
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(error))
        .spawn()?;
    let mut owner = OwnedReader {
        child,
        reaped: false,
    };
    let deadline = Instant::now() + Duration::from_secs(60);
    let result = loop {
        if let Some(status) = owner.child.try_wait()? {
            owner.reaped = true;
            break status;
        }
        if Instant::now() >= deadline
            || fs::metadata(&output_path)?.len() > limit
            || fs::metadata(&error_path)?.len() > MIB
        {
            return Err("platform reader exceeded its bounded execution/output budget".into());
        }
        std::thread::sleep(Duration::from_millis(25));
    };
    executable.revalidate()?;
    require(
        result.success() && fs::metadata(&output_path)?.len() <= limit,
        "native platform reader failed",
    )?;
    files::pin_file(&output_path)
}

fn archive_name(path: &Path) -> Result<String> {
    let name = path.to_str().ok_or("non-UTF8 native package member")?;
    let name = name
        .strip_prefix("./")
        .unwrap_or(name)
        .trim_end_matches('/');
    if name == "." || name.is_empty() {
        return Ok(String::new());
    }
    Ok(relative(name)?.to_owned())
}
pub(super) fn native_path_allowed(name: &str, package: &str, directory: bool) -> bool {
    let doc = format!("usr/share/doc/{package}");
    if directory {
        return [
            "",
            "usr",
            "usr/lib",
            "usr/lib/x86_64-linux-gnu",
            "usr/share",
            "usr/share/doc",
        ]
        .contains(&name)
            || name == doc
            || (package == "libselinux1"
                && [
                    "usr/lib/tmpfiles.d",
                    "usr/libexec",
                    "usr/libexec/libselinux",
                ]
                .contains(&name));
    }
    [
        format!("{doc}/changelog.Debian.gz"),
        format!("{doc}/copyright"),
    ]
    .iter()
    .any(|path| path == name)
        || if package == "libselinux1" {
            [
                "usr/lib/x86_64-linux-gnu/libselinux.so.1",
                "usr/lib/tmpfiles.d/libselinux1.conf",
                "usr/libexec/libselinux/selinux_compile_fcontexts",
            ]
            .contains(&name)
        } else {
            [
                "usr/lib/x86_64-linux-gnu/libapparmor.so.1",
                "usr/lib/x86_64-linux-gnu/libapparmor.so.1.30.7",
            ]
            .contains(&name)
        }
}

#[derive(Debug)]
pub(super) struct NativeMember {
    pub(super) name: String,
    pub(super) mode: u32,
    pub(super) kind: u8,
    pub(super) bytes: Vec<u8>,
    pub(super) target: String,
}
fn tar_text(field: &[u8]) -> Result<&str> {
    let end = field.iter().position(|b| *b == 0).unwrap_or(field.len());
    require(
        field[end..].iter().all(|b| *b == 0),
        "native tar text has trailing hidden bytes",
    )?;
    Ok(std::str::from_utf8(&field[..end])?)
}
fn tar_number(field: &[u8]) -> Result<u64> {
    require(
        field.iter().all(|b| matches!(*b, b'0'..=b'7' | b' ' | 0)),
        "native tar numeric field is not bounded octal",
    )?;
    let text = std::str::from_utf8(field)?.trim_matches(|c| c == '\0' || c == ' ');
    if text.is_empty() {
        Ok(0)
    } else {
        Ok(u64::from_str_radix(text, 8)?)
    }
}
pub(super) fn parse_native_tar(bytes: &[u8]) -> Result<Vec<NativeMember>> {
    require(
        bytes.len() as u64 <= 16 * MIB && bytes.len() % 512 == 0,
        "native tar exceeds its byte/alignment bound",
    )?;
    let mut offset = 0usize;
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    loop {
        let header = bytes
            .get(offset..offset.checked_add(512).ok_or("tar offset overflow")?)
            .ok_or("native tar lacks its terminal blocks")?;
        if header.iter().all(|b| *b == 0) {
            require(
                bytes.len() - offset >= 1024 && bytes[offset..].iter().all(|b| *b == 0),
                "native tar has hidden trailing data",
            )?;
            return Ok(out);
        }
        let checksum: u64 = header
            .iter()
            .enumerate()
            .map(|(i, b)| {
                if (148..156).contains(&i) {
                    32
                } else {
                    u64::from(*b)
                }
            })
            .sum();
        require(
            checksum == tar_number(&header[148..156])?,
            "native tar header checksum differs",
        )?;
        require(
            &header[257..263] == b"ustar\0" || &header[257..265] == b"ustar  \0",
            "native tar is not ordinary ustar/GNU",
        )?;
        let short = tar_text(&header[..100])?;
        let prefix = if &header[257..263] == b"ustar\0" {
            tar_text(&header[345..500])?
        } else {
            ""
        };
        let full = if prefix.is_empty() {
            short.to_owned()
        } else {
            format!("{prefix}/{short}")
        };
        let name = archive_name(Path::new(&full))?;
        let mode = u32::try_from(tar_number(&header[100..108])?)?;
        let size = usize::try_from(tar_number(&header[124..136])?)?;
        let kind = header[156];
        require(
            matches!(kind, 0 | b'0' | b'2' | b'5')
                && tar_number(&header[108..116])? == 0
                && tar_number(&header[116..124])? == 0
                && size as u64 <= 4 * MIB
                && (!matches!(kind, b'2' | b'5') || size == 0)
                && out.len() < 128
                && seen.insert(name.clone()),
            "native tar has duplicate, linked, special or non-root members",
        )?;
        let target = tar_text(&header[157..257])?.to_owned();
        require(
            kind == b'2' || target.is_empty(),
            "non-link native tar member has a hidden target",
        )?;
        offset += 512;
        let end = offset.checked_add(size).ok_or("native tar size overflow")?;
        let body = bytes
            .get(offset..end)
            .ok_or("native tar content truncated")?
            .to_vec();
        let next = end
            .checked_add(511)
            .ok_or("native tar alignment overflow")?
            & !511;
        require(
            bytes
                .get(end..next)
                .is_some_and(|p| p.iter().all(|b| *b == 0)),
            "native tar padding differs",
        )?;
        out.push(NativeMember {
            name,
            mode,
            kind,
            bytes: body,
            target,
        });
        offset = next;
    }
}

#[derive(Clone, Copy)]
pub(super) struct NativeDefinition {
    pub(super) package: &'static str,
    pub(super) version: &'static str,
    pub(super) member: &'static str,
    pub(super) deb: (u64, &'static str),
    pub(super) library: (u64, &'static str),
    pub(super) candidate_sha: &'static str,
}
pub(super) fn native_definition(selinux: bool) -> NativeDefinition {
    if selinux {
        NativeDefinition {
            package: "libselinux1",
            version: "3.9-4build1+p4lsmexec3",
            member: "usr/lib/x86_64-linux-gnu/libselinux.so.1",
            deb: SELINUX_DEB,
            library: SELINUX_LIBRARY,
            candidate_sha: "6ce4e12fe6bf65a8080809961d30d4150f712689edbff907dd0fc82bdf300582",
        }
    } else {
        NativeDefinition {
            package: "libapparmor1",
            version: "5.0.2-0ubuntu1~26.04.1+p4peer1",
            member: "usr/lib/x86_64-linux-gnu/libapparmor.so.1.30.7",
            deb: APPARMOR_DEB,
            library: APPARMOR_LIBRARY,
            candidate_sha: "fce4a15c3b485dc09e03a1d4b7cca0c5ffce50bd9d782671576f370050c7cd7f",
        }
    }
}

pub(super) fn stage_native(
    input: &NativeLibraryInputs,
    root: &Path,
    work: &Path,
    selinux: bool,
) -> Result<Value> {
    let NativeDefinition {
        package,
        version,
        member,
        deb: deb_pin,
        library: library_pin,
        candidate_sha,
    } = native_definition(selinux);
    pinned(&input.package, deb_pin)?;
    require(
        input.candidate.sha256 == candidate_sha,
        "native candidate differs from the reviewed normal build",
    )?;
    let candidate_file = HeldFile::open(&input.candidate, MIB)?;
    let candidate = object(&candidate_file, MIB)?;
    require(
        candidate["package_name"] == package
            && candidate["version"] == version
            && candidate["architecture"] == "amd64"
            && candidate["member"] == member
            && matches_pin(&candidate["package"], &input.package)
            && candidate["candidate_library"]["bytes"] == library_pin.0
            && candidate["candidate_library"]["sha256"] == library_pin.1,
        "native candidate metadata does not match the fixed package",
    )?;
    if selinux {
        let source: Value = serde_json::from_str(SELINUX_SOURCE)?;
        require(
            source["candidate_version"] == version
                && source["patch"]["sha256"] == candidate["source"]["patch_sha256"]
                && source["source_file"]["patched_sha256"]
                    == candidate["source"]["procattr_sha256"],
            "native SELinux source and deployed package differ",
        )?;
    }
    let area = work.join(package);
    files::private_dir(&area)?;
    let original = HeldFile::open(&input.package, MIB)?;
    let archive = original.copy_new(&area.join(format!("{package}_{version}_amd64.deb")), 0o400)?;
    let control = reader_tool(
        &area,
        "control",
        "/usr/bin/dpkg-deb",
        &[
            "--show".into(),
            "--showformat=${Package}\t${Version}\t${Architecture}\n".into(),
            archive.path.to_string_lossy().into(),
        ],
        65536,
    )?;
    let control_bytes = HeldFile::open(&control, 65536)?.read_all(65536)?;
    require(
        control_bytes == format!("{package}\t{version}\tamd64\n").as_bytes(),
        "normal Debian control metadata differs",
    )?;
    let tar_pin = reader_tool(
        &area,
        "payload",
        "/usr/bin/dpkg-deb",
        &[
            "--fsys-tarfile".into(),
            archive.path.to_string_lossy().into(),
        ],
        16 * MIB,
    )?;
    let tar_file = HeldFile::open(&tar_pin, 16 * MIB)?;
    let bytes = tar_file.read_all(16 * MIB)?;
    let mut payload = Vec::new();
    let mut found = false;
    for entry in parse_native_tar(&bytes)? {
        let NativeMember {
            name,
            mode,
            kind,
            bytes: contents,
            target,
        } = entry;
        require(
            (if kind == b'2' {
                mode == 0o777
            } else {
                mode & 0o7022 == 0
            }) && native_path_allowed(&name, package, kind == b'5'),
            "native archive contains duplicate, unrelated or unsafe members",
        )?;
        if kind == b'5' {
            require(mode == 0o755, "native package directory mode differs")?;
            if !name.is_empty() {
                files::ensure_dir(root, &name)?;
            }
        } else if kind == 0 || kind == b'0' {
            require(
                [0o644, 0o755].contains(&mode),
                "native archive file mode differs",
            )?;
            if name == member {
                require(
                    contents.len() as u64 == library_pin.0
                        && files::digest(&contents) == library_pin.1
                        && contents.get(..6) == Some(&b"\x7fELF\x02\x01"[..])
                        && contents.get(18..20) == Some(&[62, 0]),
                    "native library ELF or exact bytes differ",
                )?;
                found = true;
            }
            payload.push(files::write_new(
                &parent_for(root, &name)?,
                &contents,
                mode,
            )?);
        } else if kind == b'2' {
            require(
                !selinux
                    && name == "usr/lib/x86_64-linux-gnu/libapparmor.so.1"
                    && target == "libapparmor.so.1.30.7",
                "native package contains an unreviewed alias",
            )?;
            let destination = parent_for(root, &name)?;
            std::os::unix::fs::symlink("libapparmor.so.1.30.7", &destination)?;
            require(
                fs::read_link(&destination)? == Path::new("libapparmor.so.1.30.7"),
                "native alias readback differs",
            )?;
        } else {
            return Err("native package contains a hardlink or special file".into());
        }
    }
    require(found, "native package omitted its exact reviewed library")?;
    candidate_file.revalidate()?;
    original.revalidate()?;
    tar_file.revalidate()?;
    Ok(
        json!({"package":package,"version":version,"architecture":"amd64","normal_deb":archive,
        "candidate":input.candidate,"library_member":member,"payload":payload,
        "native_package_installed":false,"maintainer_scripts_executed":false}),
    )
}

#[derive(Debug)]
struct CpioMember {
    mode: u32,
    bytes: Vec<u8>,
}
fn cpio_hex(field: &[u8]) -> Result<u32> {
    Ok(u32::from_str_radix(std::str::from_utf8(field)?, 16)?)
}
fn align4(value: usize) -> Result<usize> {
    Ok(value.checked_add(3).ok_or("cpio offset overflow")? & !3)
}
fn parse_newc(bytes: &[u8]) -> Result<BTreeMap<String, CpioMember>> {
    let mut offset = 0usize;
    let mut members = BTreeMap::new();
    loop {
        let header = bytes
            .get(offset..offset.checked_add(110).ok_or("cpio offset overflow")?)
            .ok_or("truncated cpio header")?;
        require(
            &header[..6] == b"070701",
            "initrd layer is not ordinary newc",
        )?;
        let mut fields = [0u32; 13];
        for (i, value) in fields.iter_mut().enumerate() {
            *value = cpio_hex(&header[6 + i * 8..14 + i * 8])?;
        }
        let [
            _,
            mode,
            uid,
            gid,
            links,
            _,
            size,
            _,
            _,
            rmajor,
            rminor,
            name_size,
            check,
        ] = fields;
        require(
            uid == 0
                && gid == 0
                && rmajor == 0
                && rminor == 0
                && check == 0
                && (1..=1025).contains(&name_size)
                && size as u64 <= 128 * MIB,
            "unsafe initrd member metadata",
        )?;
        offset += 110;
        let name_end = offset
            .checked_add(name_size as usize)
            .ok_or("cpio name overflow")?;
        let name = bytes.get(offset..name_end).ok_or("truncated cpio name")?;
        require(
            name.last() == Some(&0) && !name[..name.len() - 1].contains(&0),
            "invalid cpio name terminator",
        )?;
        let name = std::str::from_utf8(&name[..name.len() - 1])?;
        offset = align4(name_end)?;
        if name == "TRAILER!!!" {
            require(
                size == 0
                    && bytes
                        .get(offset..)
                        .is_some_and(|b| b.iter().all(|b| *b == 0)),
                "undeclared cpio trailer data",
            )?;
            break;
        }
        relative(name)?;
        let end = offset
            .checked_add(size as usize)
            .ok_or("cpio member overflow")?;
        let contents = bytes
            .get(offset..end)
            .ok_or("truncated cpio content")?
            .to_vec();
        require(
            matches!(
                mode & libc::S_IFMT,
                libc::S_IFREG | libc::S_IFDIR | libc::S_IFLNK
            ) && (if mode & libc::S_IFMT == libc::S_IFLNK {
                mode & 0o7777 == 0o777
            } else {
                mode & 0o7022 == 0
            }) && (mode & libc::S_IFMT == libc::S_IFDIR || links == 1)
                && (mode & libc::S_IFMT != libc::S_IFDIR || size == 0)
                && members.len() < 256
                && members
                    .insert(
                        name.into(),
                        CpioMember {
                            mode,
                            bytes: contents,
                        },
                    )
                    .is_none(),
            "initrd layer has duplicate, linked, writable or special members",
        )?;
        offset = align4(end)?;
    }
    Ok(members)
}

fn resolve_cpio<'a>(
    members: &'a BTreeMap<String, CpioMember>,
    name: &str,
) -> Result<&'a CpioMember> {
    let mut current = name.to_owned();
    let mut seen = BTreeSet::new();
    for _ in 0..8 {
        require(seen.insert(current.clone()), "initrd library alias cycle")?;
        let entry = members
            .get(&current)
            .ok_or("initrd alias escapes its exact layer")?;
        if entry.mode & libc::S_IFMT == libc::S_IFREG {
            return Ok(entry);
        }
        require(
            entry.mode & libc::S_IFMT == libc::S_IFLNK,
            "initrd alias does not resolve to a regular file",
        )?;
        let target = std::str::from_utf8(&entry.bytes)?;
        let mut parts: Vec<String> = if target.starts_with('/') {
            Vec::new()
        } else {
            Path::new(&current)
                .parent()
                .unwrap()
                .iter()
                .map(|p| p.to_string_lossy().into_owned())
                .collect()
        };
        for part in target.split('/') {
            match part {
                "" | "." => (),
                ".." => {
                    require(parts.pop().is_some(), "initrd alias escapes root")?;
                }
                part => {
                    relative(part)?;
                    parts.push(part.into());
                }
            }
        }
        if parts
            .first()
            .is_some_and(|p| ["lib", "lib64"].contains(&p.as_str()))
        {
            parts.insert(0, "usr".into());
        }
        current = parts.join("/");
        require(
            current.starts_with("usr/lib/") || current.starts_with("usr/lib64/"),
            "initrd alias left its library closure",
        )?;
    }
    Err("initrd alias exceeds bounded depth".into())
}

pub(super) fn stage_initrd(
    input: &PreparedInitrd,
    kernel: &KernelInputs,
    root: &Path,
    work: &Path,
) -> Result<Value> {
    let receipt_file = HeldFile::open(&input.construction_receipt, 8 * MIB)?;
    let boot_file = HeldFile::open(&input.boot_receipt, 16 * MIB)?;
    let receipt = object(&receipt_file, 8 * MIB)?;
    let boot = object(&boot_file, 16 * MIB)?;
    let board: Value = serde_json::from_str(BOARD)?;
    require(
        boot["schema"] == "droidloom.full-ubuntu-boot-prepared.v1"
            && boot["target_kernel_release"] == board["kernel"]["release"]
            && matches_pin(&boot["kernel"], &kernel.image)
            && matches_pin(&boot["initrd"], &input.image)
            && matches_pin(&receipt["original"], &kernel.normal_initrd)
            && matches_pin(&receipt["result"], &input.image)
            && receipt["synthetic_entrypoint"] == false
            && receipt["hook"]["sha256"] == files::digest(HOOK)
            && receipt["custody"]["sha256"] == files::digest(CUSTODY),
        "final initrd is not the ordinary selected host construction",
    )?;
    let expected_root = PathBuf::from(
        boot["work_directory"]
            .as_str()
            .ok_or("normal boot work missing")?,
    )
    .join("root");
    require(
        receipt["dependency_root"] == expected_root.to_string_lossy().as_ref(),
        "initrd dependency root differs from normal preparation",
    )?;
    let bytes_file = HeldFile::open(&input.image, 256 * MIB)?;
    let bytes = bytes_file.read_all(256 * MIB)?;
    let base = HeldFile::open(&kernel.normal_initrd, 64 * MIB)?;
    let base_bytes = base.read_all(64 * MIB)?;
    let layer_offset = align4(base_bytes.len())?;
    require(
        bytes.get(..base_bytes.len()) == Some(base_bytes.as_slice())
            && bytes
                .get(base_bytes.len()..layer_offset)
                .is_some_and(|v| v.iter().all(|b| *b == 0)),
        "final initrd does not preserve the exact normal base and zero alignment",
    )?;
    let suffix = bytes
        .get(layer_offset..)
        .ok_or("final initrd layer absent")?;
    let stream = &receipt["stream_readback"];
    require(
        stream["format"] == "linux-concatenated-initramfs"
            && stream["trailing_bytes"] == 0
            && stream["layer"]["offset"] == layer_offset
            && stream["layer"]["bytes"] == suffix.len()
            && stream["layer"]["input"]["sha256"] == files::digest(suffix),
        "final initrd member boundaries differ",
    )?;
    let area = work.join("initrd-readback");
    files::private_dir(&area)?;
    let suffix_pin = files::write_new(&area.join("ordinary-layer.cpio.gz"), suffix, 0o400)?;
    let cpio = reader_tool(
        &area,
        "ordinary-layer",
        "/usr/bin/gzip",
        &[
            "-d".into(),
            "-c".into(),
            suffix_pin.path.to_string_lossy().into(),
        ],
        256 * MIB,
    )?;
    let cpio_file = HeldFile::open(&cpio, 256 * MIB)?;
    let members = parse_newc(&cpio_file.read_all(256 * MIB)?)?;
    let mut expected = BTreeSet::new();
    for row in receipt["final_directory_readback"]
        .as_array()
        .ok_or("final initrd directory readback absent")?
    {
        let name = row["path"]
            .as_str()
            .ok_or("initrd directory name absent")?
            .trim_start_matches('/');
        relative(name)?;
        require(
            expected.insert(name.to_owned()),
            "duplicate initrd directory record",
        )?;
        let actual = members.get(name).ok_or("normal initrd directory missing")?;
        require(
            actual.mode == 0o40755 && actual.bytes.is_empty(),
            "initrd directory metadata changed",
        )?;
    }
    let mut seen_files = BTreeSet::new();
    for row in receipt["final_layer_readback"]
        .as_array()
        .ok_or("final initrd file readback absent")?
    {
        let name = row["path"]
            .as_str()
            .ok_or("initrd member name absent")?
            .trim_start_matches('/');
        relative(name)?;
        require(
            expected.insert(name.to_owned()) && seen_files.insert(name.to_owned()),
            "duplicate initrd file record",
        )?;
        require(
            name.starts_with("usr/lib/")
                || name.starts_with("usr/lib64/")
                || [
                    "scripts/init-bottom/droidloom-early-custody",
                    "scripts/init-bottom/ORDER",
                ]
                .contains(&name),
            "unexpected initrd file outside the fixed normal closure",
        )?;
        let actual = resolve_cpio(&members, name)?;
        require(
            row["bytes"] == actual.bytes.len() && row["sha256"] == files::digest(&actual.bytes),
            "actual initrd bytes differ from its original readback",
        )?;
        if name == "scripts/init-bottom/droidloom-early-custody" {
            require(
                actual.bytes == CUSTODY && actual.mode == 0o100755,
                "initrd custody script differs",
            )?;
        } else if name == "scripts/init-bottom/ORDER" {
            let prefix = b"/scripts/init-bottom/droidloom-early-custody || panic \"Droidloom selected generation failed\"\n";
            require(
                actual.bytes.starts_with(prefix)
                    && files::digest(&actual.bytes[prefix.len()..])
                        == receipt["original_order"]["sha256"],
                "initrd custody order is not the original ordered hook",
            )?;
        } else if name.starts_with("usr/lib/droidloom/") {
            require(
                [
                    "usr/lib/droidloom/production/current/droidloomd",
                    "usr/lib/droidloom/production/current/droidloom-early-firststage",
                ]
                .contains(&name),
                "unexpected initrd project executable",
            )?;
            let staged = HeldFile::open(&files::pin_file(&root.join(name))?, 128 * MIB)?;
            require(
                staged.pin().sha256 == files::digest(&actual.bytes)
                    && staged.pin().bytes == actual.bytes.len() as u64,
                "initrd project ELF differs from staged host release",
            )?;
        }
    }
    require(
        expected == members.keys().cloned().collect(),
        "normal initrd contains missing or extra members",
    )?;
    let mut dependencies = BTreeSet::new();
    for row in receipt["dependency_readback"]
        .as_array()
        .ok_or("normal initrd dependency evidence missing")?
    {
        let pin = from_value(&row["source"])?;
        let guest = pin
            .path
            .strip_prefix(&expected_root)
            .map_err(|_| "initrd dependency escaped normal root")?;
        let name = guest.to_str().ok_or("non-UTF8 initrd dependency")?;
        require(
            name.starts_with("usr/lib/") || name.starts_with("usr/lib64/"),
            "initrd dependency is outside ordinary ELF paths",
        )?;
        let actual = resolve_cpio(&members, name)?;
        let held = HeldFile::open(&pin, 128 * MIB)?;
        require(
            pin.sha256 == files::digest(&actual.bytes)
                && pin.bytes == actual.bytes.len() as u64
                && actual.bytes.get(..6) == Some(&b"\x7fELF\x02\x01"[..])
                && actual.bytes.get(18..20) == Some(&[62, 0]),
            "normal initrd ELF source dependency changed",
        )?;
        held.revalidate()?;
        dependencies.insert(name.to_owned());
    }
    for name in &seen_files {
        if name.starts_with("scripts/") {
            continue;
        }
        let actual = resolve_cpio(&members, name)?;
        let resolved = members
            .iter()
            .find(|(_, member)| std::ptr::eq(*member, actual))
            .map(|(path, _)| path)
            .ok_or("initrd resolved member missing")?;
        require(
            dependencies.contains(resolved),
            "initrd contains an ELF outside the actual normal dependency closure",
        )?;
    }
    for name in [
        "usr/lib/droidloom/production/current/droidloomd",
        "usr/lib/droidloom/production/current/droidloom-early-firststage",
        "scripts/init-bottom/droidloom-early-custody",
        "scripts/init-bottom/ORDER",
    ] {
        require(
            seen_files.contains(name),
            "initrd omitted a required startup member",
        )?;
    }
    for (name, fixed) in [
        ("usr/lib/x86_64-linux-gnu/libselinux.so.1", SELINUX_LIBRARY),
        (
            "usr/lib/x86_64-linux-gnu/libapparmor.so.1.30.7",
            APPARMOR_LIBRARY,
        ),
    ] {
        let actual = resolve_cpio(&members, name)?;
        require(
            actual.bytes.len() as u64 == fixed.0 && files::digest(&actual.bytes) == fixed.1,
            "initrd retained an older native security library",
        )?;
    }
    let release = board["kernel"]["release"].as_str().unwrap();
    let output = bytes_file.copy_new(
        &parent_for(root, &format!("boot/initrd.img-{release}"))?,
        0o644,
    )?;
    base.revalidate()?;
    receipt_file.revalidate()?;
    boot_file.revalidate()?;
    Ok(
        json!({"image":output,"normal_construction":input.construction_receipt,"normal_boot_preparation":input.boot_receipt,
        "actual_layer_members":members.len(),"actual_dependency_sources":dependencies.len(),"ordinary_base_preserved":true,
        "live_boot_modified":false,"runtime_qualified":false}),
    )
}

pub(super) fn stage(input: &PlatformInputs, root: &Path, work: &Path) -> Result<Value> {
    require(
        input.schema == "droidloom.pocket4-platform-stage-inputs.v1"
            && unsafe { libc::geteuid() } == 0,
        "platform staging requires the fixed schema and root-owned private stage",
    )?;
    require(
        root != work
            && !root.starts_with(work)
            && !work.starts_with(root)
            && root.parent() == work.parent()
            && root.file_name().is_some_and(|n| n == "root")
            && work.file_name().is_some_and(|n| n == "work"),
        "platform outputs must be independent fixed root/work siblings",
    )?;
    let generation = root.parent().ok_or("platform stage generation missing")?;
    require(
        generation.parent() == Some(Path::new("/var/lib/droidloom/activation-staging"))
            && generation
                .file_name()
                .and_then(|n| n.to_str())
                .is_some_and(files::valid_digest),
        "platform outputs are outside the fixed activation stage",
    )?;
    let generation_guard = Directory::open(generation, true)?;
    let root_guard = Directory::open(root, true)?;
    let work_guard = Directory::open(work, true)?;
    let kernel = stage_kernel(&input.kernel, root, work)?;
    let selinux = stage_native(&input.libselinux, root, work, true)?;
    let apparmor = stage_native(&input.libapparmor, root, work, false)?;
    let initrd = stage_initrd(&input.initrd, &input.kernel, root, work)?;
    root_guard.revalidate()?;
    work_guard.revalidate()?;
    generation_guard.revalidate()?;
    Ok(
        json!({"schema":"droidloom.pocket4-platform-staged.v1","kernel":kernel,"initrd":initrd,
        "native_packages":[selinux,apparmor],"live_system_modified":false,"runtime_authority_issued":false,"production_ready":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn cpio(entries: &[(&str, u32, &[u8])]) -> Vec<u8> {
        let mut output = Vec::new();
        for (name, mode, body) in
            entries
                .iter()
                .copied()
                .chain(std::iter::once(("TRAILER!!!", 0, &[][..])))
        {
            output.extend_from_slice(b"070701");
            for n in [
                1,
                mode,
                0,
                0,
                1,
                0,
                body.len() as u32,
                0,
                0,
                0,
                0,
                name.len() as u32 + 1,
                0,
            ] {
                output.extend_from_slice(format!("{n:08x}").as_bytes());
            }
            output.extend_from_slice(name.as_bytes());
            output.push(0);
            while output.len() % 4 != 0 {
                output.push(0);
            }
            output.extend_from_slice(body);
            while output.len() % 4 != 0 {
                output.push(0);
            }
        }
        output
    }
    #[test]
    fn final_initrd_parser_rejects_escape_duplicates_devices_and_trailer_data() -> Result<()> {
        let data = cpio(&[("usr", 0o40755, b""), ("usr/lib/x", 0o100644, b"ordinary")]);
        assert_eq!(parse_newc(&data)?["usr/lib/x"].bytes, b"ordinary");
        for entries in [
            vec![("../etc/shadow", 0o100644, &b"x"[..])],
            vec![("usr/lib/x", 0o20600, &b""[..])],
            vec![
                ("usr/lib/x", 0o100644, &b"x"[..]),
                ("usr/lib/x", 0o100644, &b"x"[..]),
            ],
            vec![("usr/lib/x", 0o100666, &b"x"[..])],
        ] {
            assert!(parse_newc(&cpio(&entries)).is_err());
        }
        let mut trailing = data.clone();
        trailing.push(1);
        assert!(parse_newc(&trailing).is_err());
        assert!(parse_newc(&data[..data.len() - 1]).is_err());
        Ok(())
    }
    #[test]
    fn initrd_alias_cannot_import_files_outside_its_layer() -> Result<()> {
        let members = parse_newc(&cpio(&[
            ("usr/lib/x", 0o100644, b"ELF"),
            ("usr/lib/link", 0o120777, b"x"),
        ]))?;
        assert_eq!(resolve_cpio(&members, "usr/lib/link")?.bytes, b"ELF");
        for target in ["/etc/shadow", "../../../../root/key", "missing", "link"] {
            let members = parse_newc(&cpio(&[("usr/lib/link", 0o120777, target.as_bytes())]))?;
            assert!(resolve_cpio(&members, "usr/lib/link").is_err());
        }
        Ok(())
    }
    #[test]
    fn native_package_allowlist_excludes_services_boot_and_private_state() {
        assert!(native_path_allowed(
            "usr/lib/x86_64-linux-gnu/libselinux.so.1",
            "libselinux1",
            false
        ));
        for path in [
            "etc/shadow",
            "boot/vmlinuz",
            "usr/bin/other",
            "usr/lib/systemd/system/foreign.service",
            "usr/share/doc/libselinux1-other/file",
        ] {
            assert!(!native_path_allowed(path, "libselinux1", false));
        }
        for path in ["../escape", "/etc/passwd", "a//b", "a/./b", "a\\b"] {
            assert!(relative(path).is_err());
        }
    }
    #[test]
    fn native_package_keeps_only_its_normal_support_members() {
        for path in [
            "usr/lib/tmpfiles.d/libselinux1.conf",
            "usr/libexec/libselinux/selinux_compile_fcontexts",
        ] {
            assert!(native_path_allowed(path, "libselinux1", false));
            assert!(!native_path_allowed(path, "libapparmor1", false));
            assert!(!native_path_allowed(path, "libselinux1", true));
        }
        for path in [
            "usr/lib/tmpfiles.d",
            "usr/libexec",
            "usr/libexec/libselinux",
        ] {
            assert!(native_path_allowed(path, "libselinux1", true));
            assert!(!native_path_allowed(path, "libselinux1", false));
        }
        for path in [
            "usr/lib/tmpfiles.d/other.conf",
            "usr/libexec/libselinux/other",
            "usr/share/doc/libselinux1/extra",
        ] {
            assert!(!native_path_allowed(path, "libselinux1", false));
        }
    }
    #[test]
    fn native_tar_rejects_hardlinks_specials_checksum_changes_and_hidden_tail() -> Result<()> {
        fn archive(kind: u8) -> Vec<u8> {
            let mut header = vec![0u8; 512];
            let name = b"./usr/lib/x86_64-linux-gnu/libselinux.so.1";
            header[..name.len()].copy_from_slice(name);
            for (offset, width, value) in [
                (100, 8, 0o644u64),
                (108, 8, 0),
                (116, 8, 0),
                (124, 12, 0),
                (136, 12, 0),
            ] {
                let value = format!("{value:0width$o}\0", width = width - 1);
                header[offset..offset + width].copy_from_slice(value.as_bytes());
            }
            header[148..156].fill(b' ');
            header[156] = kind;
            header[257..263].copy_from_slice(b"ustar\0");
            header[263..265].copy_from_slice(b"00");
            let sum: u64 = header.iter().map(|b| u64::from(*b)).sum();
            header[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
            header.resize(1536, 0);
            header
        }
        let data = archive(b'0');
        let parsed = parse_native_tar(&data)?;
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].name, "usr/lib/x86_64-linux-gnu/libselinux.so.1");
        for kind in [b'1', b'3', b'4', b'6', b'x', b'L'] {
            assert!(parse_native_tar(&archive(kind)).is_err());
        }
        let mut changed = data.clone();
        changed[0] ^= 1;
        assert!(parse_native_tar(&changed).is_err());
        let mut changed = data.clone();
        *changed.last_mut().unwrap() = 1;
        assert!(parse_native_tar(&changed).is_err());
        assert!(parse_native_tar(&data[..1024]).is_err());
        Ok(())
    }
    #[test]
    fn fixed_platform_batch_rejects_same_name_with_other_bytes() {
        let mut pin = FilePin {
            path: "/same/package.deb".into(),
            bytes: SELINUX_DEB.0,
            sha256: SELINUX_DEB.1.into(),
        };
        assert!(pinned(&pin, SELINUX_DEB).is_ok());
        pin.sha256 = "0".repeat(64);
        assert!(pinned(&pin, SELINUX_DEB).is_err());
    }
}
