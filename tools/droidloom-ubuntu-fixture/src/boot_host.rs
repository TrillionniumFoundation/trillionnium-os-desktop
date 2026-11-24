use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::Read,
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant},
};

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
    ensure(
        git_id(&m.commit) && git_id(&m.tree),
        "invalid normal source identity",
    )?;
    ensure(
        !m.files.is_empty() && m.files.len() <= 128,
        "unexpected host file count",
    )?;
    let mut paths = BTreeSet::new();
    let mut bytes = 0u64;
    for f in &m.files {
        ensure(
            valid_path(&f.path)
                && (f.path.starts_with("usr/") || f.path.starts_with("etc/selinux/"))
                && paths.insert(f.path.clone()),
            "host file outside normal export or duplicate",
        )?;
        ensure(
            f.size > 0
                && f.size < 32 * 1024 * 1024
                && fs::valid_digest(&f.sha256)
                && f.mode & !0o777 == 0
                && f.mode & 0o022 == 0,
            "invalid host file size/mode/digest",
        )?;
        bytes = bytes.checked_add(f.size).ok_or("host size overflow")?;
    }
    ensure(
        bytes < 512 * 1024 * 1024,
        "host archive expansion exceeds limit",
    )?;
    ensure(
        m.directories.len() == 1,
        "unexpected normal host directory count",
    )?;
    let d = &m.directories[0];
    ensure(
        d.path == STATE && d.uid == 0 && d.gid == 0 && d.mode == 0o700 && d.empty,
        "calibration directory contract differs",
    )
}
pub(crate) fn octal(field: &[u8]) -> Result<u64> {
    ensure(
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
    ensure(
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
    ensure(
        stored == sum && &block[257..263] == b"ustar\0" && &block[263..265] == b"00",
        "noncanonical or corrupt normal ustar header",
    )?;
    let kind = block[156];
    ensure(
        kind == b'0' || kind == 0 || kind == b'5',
        "links, extensions and special archive objects are refused",
    )?;
    ensure(
        octal(&block[108..116])? == 0
            && octal(&block[116..124])? == 0
            && octal(&block[136..148])? == 0,
        "normal archive owner/time differs",
    )?;
    ensure(
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
    ensure(valid_path(&path), "unsafe archive path")?;
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
            ensure(
                second.iter().all(|v| *v == 0),
                "archive lacks two zero terminators",
            )?;
            let mut tail = Vec::new();
            input.take(10241).read_to_end(&mut tail)?;
            ensure(
                tail.len() <= 10240 && tail.iter().all(|v| *v == 0),
                "nonzero or excessive archive tail",
            )?;
            break;
        }
        let h = header(&block)?;
        ensure(seen.insert(h.path.clone()), "duplicate archive path")?;
        let guest = format!("/{}", h.path);
        if h.path == STATE {
            ensure(
                h.kind == b'5' && h.size == 0 && h.mode == 0o700,
                "calibration directory entry differs",
            )?;
            let parent = Path::new(&guest)
                .parent()
                .and_then(Path::to_str)
                .ok_or("invalid archive parent")?;
            boot_files::ensure_dir(root, parent, 0o755)?;
            let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
            tree.mkdir(&guest)?;
            ensure(
                tree.list(&guest)?.is_empty(),
                "calibration directory was not freshly empty",
            )?;
            continue;
        }
        let want = expected
            .get(h.path.as_str())
            .ok_or("unrecorded archive member")?;
        ensure(
            (h.kind == b'0' || h.kind == 0) && h.size == want.size && h.mode == want.mode,
            "archive file differs from normal manifest",
        )?;
        let mut bytes = vec![0; usize::try_from(h.size)?];
        input.read_exact(&mut bytes)?;
        ensure(
            fs::digest(&bytes) == want.sha256,
            "normal archive member digest differs",
        )?;
        let padding = (512 - h.size % 512) % 512;
        let mut pad = vec![0; usize::try_from(padding)?];
        input.read_exact(&mut pad)?;
        ensure(pad.iter().all(|b| *b == 0), "nonzero member padding")?;
        let parent = Path::new(&guest)
            .parent()
            .and_then(Path::to_str)
            .ok_or("invalid archive parent")?;
        boot_files::ensure_dir(root, parent, 0o755)?;
        boot_files::write_new(&boot_files::guest_path(root, &guest)?, &bytes, h.mode)?;
    }
    ensure(
        seen.len() == m.files.len() + 1
            && seen.contains(STATE)
            && m.files.iter().all(|f| seen.contains(&f.path)),
        "normal archive member set incomplete",
    )?;
    Ok(seen.len())
}

pub fn install(
    root: &Path,
    work: &Path,
    manifest_pin: &FilePin,
    archive_pin: &FilePin,
) -> Result<serde_json::Value> {
    let manifest: HostManifest =
        serde_json::from_slice(&boot_files::read_pin(manifest_pin, 1024 * 1024)?)?;
    validate_manifest(&manifest)?;
    ensure(
        archive_pin.bytes <= 64 * 1024 * 1024,
        "compressed host export exceeds limit",
    )?;
    let input = boot_files::checked_file(archive_pin)?;
    let original = fs::stat(&input)?;
    let tar_path = work.join("normal-host.ustar");
    let out = boot_files::new_file(&tar_path, 0o600)?;
    let err_path = work.join("host-xz.log");
    let err = boot_files::new_file(&err_path, 0o600)?;
    let mut command = Command::new("/usr/bin/xz");
    command
        .args(["--decompress", "--stdout"])
        .env_clear()
        .env("LC_ALL", "C")
        .stdin(Stdio::from(input.try_clone()?))
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(err));
    let mut child = crate::boot_child::OwnedChild::spawn(&mut command)?;
    let began = Instant::now();
    let limit = manifest
        .files
        .iter()
        .map(|f| (f.size + 511) / 512 * 512 + 512)
        .sum::<u64>()
        + 16384;
    let status = loop {
        if let Some(s) = child.try_wait()? {
            break s;
        }
        if began.elapsed() > Duration::from_secs(120) || std::fs::metadata(&tar_path)?.len() > limit
        {
            child.stop_and_reap()?;
            return Err("bounded normal archive decompression failed".into());
        }
        std::thread::sleep(Duration::from_millis(50));
    };
    ensure(
        status.success()
            && std::fs::metadata(&tar_path)?.len() <= limit
            && fs::stat(&input)? == original,
        "normal archive decompression or source identity changed",
    )?;
    let tar_pin = boot_files::pin_file(&tar_path)?;
    let mut tar = boot_files::checked_file(&tar_pin)?;
    let entries = decode(&mut tar, &manifest, root)?;
    let installed = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    for f in &manifest.files {
        let guest = format!("/{}", f.path);
        let id = installed.identity(&guest)?;
        let actual = boot_files::pin_file(&root.join(&f.path))?;
        ensure(
            id.uid == 0
                && id.gid == 0
                && id.nlink == 1
                && id.mode & 0o7777 == f.mode
                && actual.bytes == f.size
                && actual.sha256 == f.sha256,
            "normal host installed file readback differs",
        )?;
    }
    let state = installed.identity(&format!("/{STATE}"))?;
    ensure(
        state.uid == 0
            && state.gid == 0
            && state.mode & 0o7777 == 0o700
            && installed.list(&format!("/{STATE}"))?.is_empty(),
        "normal empty StateDirectory readback differs",
    )?;
    let policy = root.join("etc/selinux/droidloom/policy/policy.30");
    let early = root.join("usr/lib/droidloom/production/current/board-policy/joint.policy");
    ensure(
        boot_files::pin_file(&policy)?.sha256 == boot_files::pin_file(&early)?.sha256,
        "native discovery and initial kernel policy bytes differ",
    )?;
    let config = std::fs::read_to_string(root.join("etc/selinux/config"))?;
    ensure(
        config
            .lines()
            .filter(|l| !l.trim().is_empty() && !l.trim_start().starts_with('#'))
            .map(str::trim)
            .eq(["SELINUX=enforcing", "SELINUXTYPE=droidloom"]),
        "native enforcement configuration differs",
    )?;
    Ok(
        serde_json::json!({"normal_host_manifest":manifest_pin,"normal_host_archive":archive_pin,
        "source_commit":manifest.commit,"source_tree":manifest.tree,"entries":entries,
        "decompressed_tar":tar_pin,"full_file_readback":true,"empty_state_readback":true,
        "guest_qualified":false}),
    )
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
