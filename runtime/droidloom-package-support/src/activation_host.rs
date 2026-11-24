//! Import the normal host producer's exact bounded archive into a private tree.
use super::{
    Result,
    activation_files::{self as files, FilePin, HeldFile},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::Read,
    os::unix::fs::MetadataExt,
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};
fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
const ALLOWED: &[(&str, u32)] = &[
    ("etc/selinux/config", 0o444),
    ("etc/selinux/droidloom/contexts/dbus_contexts", 0o444),
    ("etc/selinux/droidloom/contexts/default_contexts", 0o444),
    ("etc/selinux/droidloom/contexts/files/file_contexts", 0o444),
    ("etc/selinux/droidloom/policy/policy.30", 0o444),
    ("etc/selinux/droidloom/seusers", 0o444),
    ("usr/bin/droidloom-applications", 0o755),
    ("usr/bin/droidloom-doctor", 0o755),
    ("usr/bin/droidloom-wayland", 0o755),
    ("usr/bin/droidloomctl", 0o755),
    ("usr/include/droidloom/early-custody.h", 0o644),
    ("usr/lib/droidloom/droidloom-package-helper", 0o755),
    (
        "usr/lib/droidloom/production/current/board-policy/joint.policy",
        0o444,
    ),
    (
        "usr/lib/droidloom/production/current/board-policy/ubuntu-apparmor.profiles",
        0o444,
    ),
    (
        "usr/lib/droidloom/production/current/droidloom-board-init",
        0o755,
    ),
    (
        "usr/lib/droidloom/production/current/droidloom-container-entry",
        0o755,
    ),
    (
        "usr/lib/droidloom/production/current/droidloom-early-firststage",
        0o755,
    ),
    (
        "usr/lib/droidloom/production/current/droidloom-host-mac",
        0o755,
    ),
    (
        "usr/lib/droidloom/production/current/droidloom-supervisor",
        0o755,
    ),
    ("usr/lib/droidloom/production/current/droidloomctl", 0o755),
    ("usr/lib/droidloom/production/current/droidloomd", 0o755),
    (
        "usr/lib/droidloom/production/libdroidloom_early_custody.a",
        0o644,
    ),
    (
        "usr/lib/systemd/system/droidloom-mac-calibration.service",
        0o644,
    ),
    (
        "usr/lib/systemd/user/droidloom-production-desktop.service",
        0o644,
    ),
    ("usr/lib/tmpfiles.d/droidloom-production.conf", 0o644),
    (
        "usr/share/droidloom/board/ubuntu-native-file_contexts",
        0o444,
    ),
    ("usr/share/droidloom/board/ubuntu-real-root-devices", 0o444),
    (
        "usr/share/droidloom/board/ubuntu-real-root-file_contexts",
        0o444,
    ),
    (
        "usr/share/droidloom/production/droidloom-container-entry.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-container-guest.socket",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-container-services.target",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-early-observer.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-instance-factory.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-instance-launcher.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-mac-calibration.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-manager-label.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/droidloom-production.service",
        0o644,
    ),
    (
        "usr/share/droidloom/production/linux-initial-calibration-file_contexts",
        0o444,
    ),
    (
        "usr/share/droidloom/production/linux-service-file_contexts",
        0o444,
    ),
    (
        "usr/share/initramfs-tools/hooks/droidloom-early-release",
        0o755,
    ),
    (
        "usr/share/initramfs-tools/scripts/init-bottom/droidloom-early-custody",
        0o755,
    ),
];
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct HostInputs {
    pub release: FilePin,
    pub manifest: FilePin,
    pub archive: FilePin,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Output {
    path: String,
    sha256: String,
    size: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Release {
    schema: String,
    commit: String,
    tree: String,
    stage: String,
    archive: Output,
    manifest: Output,
    files_verified: usize,
    protected_empty_directories_verified: usize,
    production_activated: bool,
    runtime_qualified: bool,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostFile {
    pub path: String,
    pub size: u64,
    pub sha256: String,
    pub mode: u32,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostDirectory {
    pub path: String,
    pub uid: u32,
    pub gid: u32,
    pub mode: u32,
    pub empty: bool,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostManifest {
    pub commit: String,
    pub tree: String,
    pub stage: String,
    pub files: Vec<HostFile>,
    pub directories: Vec<HostDirectory>,
}
const STATE: &str = "var/lib/droidloom-mac-calibration";
fn valid_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && path.split('/').all(|p| {
            !p.is_empty()
                && p != "."
                && p != ".."
                && p.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        })
}
pub fn validate_manifest(m: &HostManifest) -> Result<()> {
    let git_id = |s: &str| {
        s.len() == 40
            && s.bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    };
    require(
        git_id(&m.commit) && git_id(&m.tree),
        "invalid normal source identity",
    )?;
    require(
        !m.files.is_empty() && m.files.len() <= 128,
        "unexpected host file count",
    )?;
    require(
        m.files
            .iter()
            .map(|f| (f.path.as_str(), f.mode))
            .collect::<BTreeSet<_>>()
            == ALLOWED.iter().copied().collect::<BTreeSet<_>>(),
        "host manifest may contain only this helper's fixed normal product inventory",
    )?;
    let mut paths = BTreeSet::new();
    let mut bytes = 0u64;
    for f in &m.files {
        require(
            valid_path(&f.path)
                && (f.path.starts_with("usr/") || f.path.starts_with("etc/selinux/"))
                && paths.insert(f.path.clone()),
            "host file outside normal export or duplicate",
        )?;
        require(
            f.size > 0
                && f.size < 32 * 1024 * 1024
                && files::valid_digest(&f.sha256)
                && f.mode & !0o777 == 0
                && f.mode & 0o022 == 0,
            "invalid host file size/mode/digest",
        )?;
        bytes = bytes.checked_add(f.size).ok_or("host size overflow")?;
    }
    require(
        bytes < 512 * 1024 * 1024,
        "host archive expansion exceeds limit",
    )?;
    require(
        m.directories.len() == 1,
        "unexpected normal host directory count",
    )?;
    let d = &m.directories[0];
    require(
        d.path == STATE && d.uid == 0 && d.gid == 0 && d.mode == 0o700 && d.empty,
        "calibration directory contract differs",
    )
}
pub(crate) fn octal(field: &[u8]) -> Result<u64> {
    require(
        field
            .iter()
            .all(|b| *b == 0 || *b == b' ' || (b'0'..=b'7').contains(b)),
        "non-octal tar field",
    )?;
    let value = std::str::from_utf8(field)?.trim_matches(|c| c == '\0' || c == ' ');
    if value.is_empty() {
        Ok(0)
    } else {
        Ok(u64::from_str_radix(value, 8)?)
    }
}
pub(crate) fn text_field(field: &[u8]) -> Result<&str> {
    let end = field.iter().position(|b| *b == 0).unwrap_or(field.len());
    require(
        field[end..].iter().all(|b| *b == 0),
        "nonzero tar string padding",
    )?;
    Ok(std::str::from_utf8(&field[..end])?)
}
struct Header {
    path: String,
    kind: u8,
    mode: u32,
    size: u64,
}
fn header(block: &[u8; 512]) -> Result<Header> {
    let stored = octal(&block[148..156])?;
    let sum: u64 = block
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
        stored == sum && &block[257..263] == b"ustar\0" && &block[263..265] == b"00",
        "noncanonical or corrupt normal ustar header",
    )?;
    let kind = block[156];
    require(
        kind == b'0' || kind == 0 || kind == b'5',
        "links, extensions and special archive objects are refused",
    )?;
    require(
        octal(&block[108..116])? == 0
            && octal(&block[116..124])? == 0
            && octal(&block[136..148])? == 0,
        "normal archive owner/time differs",
    )?;
    require(
        text_field(&block[157..257])?.is_empty(),
        "unexpected link target",
    )?;
    let name = text_field(&block[..100])?;
    let prefix = text_field(&block[345..500])?;
    let mut path = if prefix.is_empty() {
        name.to_owned()
    } else {
        format!("{prefix}/{name}")
    };
    if kind == b'5' && path.ends_with('/') {
        path.pop();
    }
    require(valid_path(&path), "unsafe archive path")?;
    let mode = u32::try_from(octal(&block[100..108])?)?;
    let size = octal(&block[124..136])?;
    Ok(Header {
        path,
        kind,
        mode,
        size,
    })
}
fn decode(input: &mut File, m: &HostManifest, root: &Path) -> Result<usize> {
    let expected: BTreeMap<_, _> = m.files.iter().map(|f| (f.path.as_str(), f)).collect();
    let mut seen = BTreeSet::new();
    let mut block = [0u8; 512];
    loop {
        input.read_exact(&mut block)?;
        if block.iter().all(|v| *v == 0) {
            let mut second = [0u8; 512];
            input.read_exact(&mut second)?;
            require(
                second.iter().all(|v| *v == 0),
                "archive lacks two zero terminators",
            )?;
            let mut tail = Vec::new();
            input.take(10241).read_to_end(&mut tail)?;
            require(
                tail.len() <= 10240 && tail.iter().all(|v| *v == 0),
                "nonzero or excessive archive tail",
            )?;
            break;
        }
        let h = header(&block)?;
        require(seen.insert(h.path.clone()), "duplicate archive path")?;
        let guest = format!("/{}", h.path);
        if h.path == STATE {
            require(
                h.kind == b'5' && h.size == 0 && h.mode == 0o700,
                "calibration directory entry differs",
            )?;
            let parent = Path::new(&guest)
                .parent()
                .and_then(Path::to_str)
                .ok_or("invalid archive parent")?;
            files::ensure_dir(root, parent.trim_start_matches('/'))?;
            files::private_dir(&root.join(STATE))?;
            continue;
        }
        let want = expected
            .get(h.path.as_str())
            .ok_or("unrecorded archive member")?;
        require(
            (h.kind == b'0' || h.kind == 0) && h.size == want.size && h.mode == want.mode,
            "archive file differs from normal manifest",
        )?;
        let mut bytes = vec![0; usize::try_from(h.size)?];
        input.read_exact(&mut bytes)?;
        require(
            files::digest(&bytes) == want.sha256,
            "normal archive member digest differs",
        )?;
        let padding = (512 - h.size % 512) % 512;
        let mut pad = vec![0; usize::try_from(padding)?];
        input.read_exact(&mut pad)?;
        require(pad.iter().all(|b| *b == 0), "nonzero member padding")?;
        let parent = Path::new(&guest)
            .parent()
            .and_then(Path::to_str)
            .ok_or("invalid archive parent")?;
        files::ensure_dir(root, parent.trim_start_matches('/'))?;
        files::write_new(&root.join(&h.path), &bytes, h.mode)?;
    }
    require(
        seen.len() == m.files.len() + 1
            && seen.contains(STATE)
            && m.files.iter().all(|f| seen.contains(&f.path)),
        "normal archive member set incomplete",
    )?;
    Ok(seen.len())
}

struct Owned(std::process::Child);
impl Drop for Owned {
    fn drop(&mut self) {
        if matches!(self.0.try_wait(), Ok(None)) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}
pub(super) fn stage(
    root: &Path,
    work: &Path,
    input: &HostInputs,
    commit: &str,
    tree: &str,
) -> Result<HostManifest> {
    let release_file = HeldFile::open(&input.release, 64 * 1024)?;
    let release: Release = serde_json::from_slice(&release_file.read_all(64 * 1024)?)?;
    let manifest_file = HeldFile::open(&input.manifest, 1024 * 1024)?;
    let manifest: HostManifest = serde_json::from_slice(&manifest_file.read_all(1024 * 1024)?)?;
    validate_manifest(&manifest)?;
    require(
        release.schema == "droidloom-normal-container-host-release-v1"
            && release.commit == commit
            && release.tree == tree
            && manifest.commit == commit
            && manifest.tree == tree
            && release.stage == manifest.stage
            && !release.production_activated
            && !release.runtime_qualified
            && release.files_verified == manifest.files.len()
            && release.protected_empty_directories_verified == 1
            && release.archive.size == input.archive.bytes
            && release.archive.sha256 == input.archive.sha256
            && release.manifest.size == input.manifest.bytes
            && release.manifest.sha256 == input.manifest.sha256
            && Path::new(&release.archive.path)
                .file_name()
                .is_some_and(|n| n == "HOST-STAGE.tar.xz")
            && Path::new(&release.manifest.path)
                .file_name()
                .is_some_and(|n| n == "HOST-STAGE.json"),
        "normal release, archive and manifest do not name one source generation",
    )?;
    let archive = HeldFile::open(&input.archive, 64 * 1024 * 1024)?;
    let tar_path = work.join("normal-host.ustar");
    let out = files::new_file(&tar_path, 0o600)?;
    let err_path = work.join("normal-host-xz.log");
    let err = files::new_file(&err_path, 0o600)?;
    let limit = manifest
        .files
        .iter()
        .map(|f| (f.size + 511) / 512 * 512 + 512)
        .sum::<u64>()
        + 16384;
    let mut cmd = Command::new("/usr/bin/xz");
    cmd.args(["--decompress", "--stdout", "--memlimit-decompress=256MiB"])
        .env_clear()
        .env("LC_ALL", "C")
        .stdin(Stdio::from(archive.file().try_clone()?))
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(err));
    let mut child = Owned(cmd.spawn()?);
    let start = Instant::now();
    let status = loop {
        if let Some(s) = child.0.try_wait()? {
            break s;
        }
        require(
            start.elapsed() < Duration::from_secs(120)
                && fs::metadata(&tar_path)?.len() <= limit
                && fs::metadata(&err_path)?.len() <= 64 * 1024,
            "normal host decompression exceeded its bound",
        )?;
        std::thread::sleep(Duration::from_millis(50));
    };
    require(
        status.success() && fs::metadata(&tar_path)?.len() <= limit,
        "normal host archive decompression failed",
    )?;
    archive.revalidate()?;
    let tar_pin = files::pin_file(&tar_path)?;
    let tar = HeldFile::open(&tar_pin, 512 * 1024 * 1024)?;
    decode(&mut tar.file().try_clone()?, &manifest, root)?;
    tar.revalidate()?;
    release_file.revalidate()?;
    manifest_file.revalidate()?;
    for item in &manifest.files {
        let actual = files::pin_file(&root.join(&item.path))?;
        let file = HeldFile::open(&actual, 32 * 1024 * 1024)?;
        let m = file.file().metadata()?;
        require(
            m.uid() == 0
                && m.gid() == 0
                && m.nlink() == 1
                && m.mode() & 0o7777 == item.mode
                && actual.bytes == item.size
                && actual.sha256 == item.sha256,
            "staged normal host member differs on full readback",
        )?;
        files::no_privilege_xattrs(file.file())?;
    }
    let board: Value = serde_json::from_str(include_str!(
        "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
    ))?;
    for (name, relative) in [
        (
            "joint.policy",
            "usr/lib/droidloom/production/current/board-policy/joint.policy",
        ),
        ("joint.policy", "etc/selinux/droidloom/policy/policy.30"),
        (
            "ubuntu-apparmor.profiles",
            "usr/lib/droidloom/production/current/board-policy/ubuntu-apparmor.profiles",
        ),
    ] {
        let f = manifest
            .files
            .iter()
            .find(|f| f.path == relative)
            .ok_or("missing board policy")?;
        require(
            board["files"][name]["size"] == f.size && board["files"][name]["sha256"] == f.sha256,
            "normal host policy differs from the compiled release lock",
        )?;
    }
    require(
        fs::read(root.join("etc/selinux/config"))? == b"SELINUX=enforcing\nSELINUXTYPE=droidloom\n",
        "normal host enforcement configuration differs",
    )?;
    Ok(manifest)
}
pub(super) fn verify_staged(
    root: &Path,
    input: &HostInputs,
    commit: &str,
    tree: &str,
) -> Result<HostManifest> {
    let release_file = HeldFile::open(&input.release, 64 * 1024)?;
    let release: Release = serde_json::from_slice(&release_file.read_all(64 * 1024)?)?;
    let manifest_file = HeldFile::open(&input.manifest, 1024 * 1024)?;
    let manifest: HostManifest = serde_json::from_slice(&manifest_file.read_all(1024 * 1024)?)?;
    validate_manifest(&manifest)?;
    require(
        release.schema == "droidloom-normal-container-host-release-v1"
            && release.commit == commit
            && release.tree == tree
            && manifest.commit == commit
            && manifest.tree == tree
            && release.stage == manifest.stage
            && !release.production_activated
            && !release.runtime_qualified
            && release.files_verified == manifest.files.len()
            && release.protected_empty_directories_verified == 1
            && release.archive.size == input.archive.bytes
            && release.archive.sha256 == input.archive.sha256
            && release.manifest.size == input.manifest.bytes
            && release.manifest.sha256 == input.manifest.sha256
            && Path::new(&release.archive.path)
                .file_name()
                .is_some_and(|n| n == "HOST-STAGE.tar.xz")
            && Path::new(&release.manifest.path)
                .file_name()
                .is_some_and(|n| n == "HOST-STAGE.json"),
        "normal release, archive and manifest do not name one source generation",
    )?;
    let archive = HeldFile::open(&input.archive, 64 * 1024 * 1024)?;
    archive.revalidate()?;
    release_file.revalidate()?;
    manifest_file.revalidate()?;
    for item in &manifest.files {
        let actual = files::pin_file(&root.join(&item.path))?;
        let file = HeldFile::open(&actual, 32 * 1024 * 1024)?;
        let m = file.file().metadata()?;
        require(
            m.uid() == 0
                && m.gid() == 0
                && m.nlink() == 1
                && m.mode() & 0o7777 == item.mode
                && actual.bytes == item.size
                && actual.sha256 == item.sha256,
            "staged normal host member differs on full readback",
        )?;
        files::no_privilege_xattrs(file.file())?;
    }
    let board: Value = serde_json::from_str(include_str!(
        "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
    ))?;
    for (name, relative) in [
        (
            "joint.policy",
            "usr/lib/droidloom/production/current/board-policy/joint.policy",
        ),
        ("joint.policy", "etc/selinux/droidloom/policy/policy.30"),
        (
            "ubuntu-apparmor.profiles",
            "usr/lib/droidloom/production/current/board-policy/ubuntu-apparmor.profiles",
        ),
    ] {
        let f = manifest
            .files
            .iter()
            .find(|f| f.path == relative)
            .ok_or("missing board policy")?;
        require(
            board["files"][name]["size"] == f.size && board["files"][name]["sha256"] == f.sha256,
            "normal host policy differs from the compiled release lock",
        )?;
    }
    require(
        fs::read(root.join("etc/selinux/config"))? == b"SELINUX=enforcing\nSELINUXTYPE=droidloom\n",
        "normal host enforcement configuration differs",
    )?;
    Ok(manifest)
}
pub(super) fn executing_helper_matches(manifest: &HostManifest) -> Result<()> {
    let expected = manifest
        .files
        .iter()
        .find(|f| f.path == "usr/lib/droidloom/droidloom-package-helper")
        .ok_or("normal release has no package helper")?;
    // procfs executable is an intentional kernel magic-link read, not a caller path.
    let file = File::open("/proc/self/exe")?;
    let id = files::FileIdentity::read(file.metadata()?)?;
    require(
        id.bytes == expected.size && files::hash_file(&file, id.bytes)? == expected.sha256,
        "the executing activation helper is not the same normal host release",
    )?;
    require(
        files::FileIdentity::read(file.metadata()?)? == id,
        "executing helper changed while observed",
    )
}
pub(super) fn receipt(manifest: &HostManifest, input: &HostInputs) -> Value {
    json!({"normal_host_release":input.release,"normal_host_manifest":input.manifest,"normal_host_archive":input.archive,
    "source_commit":manifest.commit,"source_tree":manifest.tree,"files":manifest.files,
    "full_file_readback":true,"protected_empty_directories_verified":1,"production_ready":false})
}
#[cfg(test)]
mod tests {
    use super::*;
    fn sample(path: &str, kind: u8) -> [u8; 512] {
        let mut b = [0u8; 512];
        b[..path.len()].copy_from_slice(path.as_bytes());
        b[100..108].copy_from_slice(b"0000644\0");
        b[108..116].copy_from_slice(b"0000000\0");
        b[116..124].copy_from_slice(b"0000000\0");
        b[124..136].copy_from_slice(b"00000000000\0");
        b[136..148].copy_from_slice(b"00000000000\0");
        b[148..156].fill(b' ');
        b[156] = kind;
        b[257..263].copy_from_slice(b"ustar\0");
        b[263..265].copy_from_slice(b"00");
        let sum: u64 = b.iter().map(|v| u64::from(*v)).sum();
        b[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        b
    }
    #[test]
    fn accepts_normal_header_but_rejects_traversal_links_and_damage() {
        assert!(header(&sample("usr/bin/droidloomctl", b'0')).is_ok());
        assert!(header(&sample("../escape", b'0')).is_err());
        assert!(header(&sample("usr/bin/droidloomctl", b'2')).is_err());
        let mut damaged = sample("usr/bin/droidloomctl", b'0');
        damaged[3] = b'x';
        assert!(header(&damaged).is_err());
    }
}
