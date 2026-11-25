//! Kernel-observed references to the exact held data and directory inodes.
//! Only metadata is read. Permission errors and an unresolvable live loop are
//! evidence gaps, never a reported empty owner set.
use super::*;
use std::{
    collections::BTreeSet,
    io::Read,
    os::unix::fs::MetadataExt,
    time::{Duration, Instant},
};

type Nodes = BTreeSet<(u64, u64)>;
fn vanished(e: &std::io::Error) -> bool {
    e.kind() == std::io::ErrorKind::NotFound
        || e.raw_os_error() == Some(rustix::io::Errno::SRCH.raw_os_error())
}
fn bounded(path: &Path, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    File::open(path)?.take(limit + 1).read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 <= limit,
        "kernel reference inventory exceeds bound",
    )?;
    Ok(bytes)
}
fn start(pid: u32) -> Result<Option<u64>> {
    let path = PathBuf::from(format!("/proc/{pid}/stat"));
    let raw = match std::fs::read_to_string(&path) {
        Ok(v) => v,
        Err(e) if vanished(&e) => return Ok(None),
        Err(e) => return Err(e.into()),
    };
    ensure(
        raw.len() <= 64 * 1024,
        "process identity record exceeds bound",
    )?;
    let rest = raw
        .rsplit_once(") ")
        .ok_or("malformed kernel process identity")?
        .1;
    let fields = rest.split_whitespace().collect::<Vec<_>>();
    Ok(Some(
        fields
            .get(19)
            .ok_or("process start identity missing")?
            .parse()?,
    ))
}
fn metadata_matches(path: &Path, nodes: &Nodes) -> Result<bool> {
    match std::fs::metadata(path) {
        Ok(m) => Ok(nodes.contains(&(m.dev(), m.ino()))),
        Err(e) if vanished(&e) => Ok(false),
        Err(e) => Err(e.into()),
    }
}
fn decode_mount_path(raw: &str) -> Result<PathBuf> {
    let b = raw.as_bytes();
    let mut result = Vec::new();
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'\\' {
            ensure(
                i + 3 < b.len() && b[i + 1..i + 4].iter().all(|n| (b'0'..=b'7').contains(n)),
                "invalid kernel mount path escape",
            )?;
            let n = u16::from(b[i + 1] - b'0') * 64
                + u16::from(b[i + 2] - b'0') * 8
                + u16::from(b[i + 3] - b'0');
            ensure(n > 0 && n <= 255, "invalid byte in kernel mount path")?;
            result.push(n as u8);
            i += 4;
        } else {
            result.push(b[i]);
            i += 1;
        }
    }
    let value = String::from_utf8(result)?;
    let path = PathBuf::from(&value);
    ensure(
        path.is_absolute()
            && path.components().all(|c| {
                matches!(
                    c,
                    std::path::Component::RootDir | std::path::Component::Normal(_)
                )
            }),
        "non-normal kernel mountpoint path",
    )?;
    Ok(path)
}
fn check_maps(pid: u32, nodes: &Nodes) -> Result<u64> {
    let path = PathBuf::from(format!("/proc/{pid}/maps"));
    let raw = match bounded(&path, 16 * 1024 * 1024) {
        Ok(v) => v,
        Err(e) => {
            if start(pid)?.is_none() {
                return Ok(0);
            }
            return Err(e);
        }
    };
    for line in raw.split(|b| *b == b'\n').filter(|s| !s.is_empty()) {
        let fields = line
            .split(|b| b.is_ascii_whitespace())
            .filter(|s| !s.is_empty())
            .take(5)
            .map(std::str::from_utf8)
            .collect::<std::result::Result<Vec<_>, _>>()?;
        ensure(fields.len() == 5, "malformed process map metadata")?;
        let inode: u64 = fields[4].parse()?;
        if inode == 0 {
            continue;
        }
        let (major, minor) = fields[3]
            .split_once(':')
            .ok_or("mapping device metadata missing")?;
        let major = u32::from_str_radix(major, 16)?;
        let minor = u32::from_str_radix(minor, 16)?;
        ensure(
            !nodes.iter().any(|(d, i)| {
                *i == inode && rustix::fs::major(*d) == major && rustix::fs::minor(*d) == minor
            }),
            &format!("process {pid} maps an original or working data inode"),
        )?;
    }
    Ok(raw.len() as u64)
}
fn check_mounts(pid: u32, nodes: &Nodes) -> Result<u64> {
    let path = PathBuf::from(format!("/proc/{pid}/mountinfo"));
    let raw = match bounded(&path, 16 * 1024 * 1024) {
        Ok(v) => v,
        Err(e) => {
            if start(pid)?.is_none() {
                return Ok(0);
            }
            return Err(e);
        }
    };
    for line in raw.split(|b| *b == b'\n').filter(|s| !s.is_empty()) {
        let fields = std::str::from_utf8(line)?
            .split_whitespace()
            .collect::<Vec<_>>();
        ensure(
            fields.len() >= 10 && fields.contains(&"-"),
            "malformed kernel mount identity",
        )?;
        let (major, minor) = fields[2]
            .split_once(':')
            .ok_or("mount device metadata missing")?;
        let major: u32 = major.parse()?;
        let minor: u32 = minor.parse()?;
        if !nodes
            .iter()
            .any(|(d, _)| rustix::fs::major(*d) == major && rustix::fs::minor(*d) == minor)
        {
            continue;
        }
        let target = decode_mount_path(fields[4])?;
        let rooted = PathBuf::from(format!("/proc/{pid}/root")).join(target.strip_prefix("/")?);
        ensure(
            !metadata_matches(&rooted, nodes)?,
            &format!("process {pid} retains a bind mount of a data inode"),
        )?;
    }
    Ok(raw.len() as u64)
}
fn check_process(
    pid: u32,
    nodes: &Nodes,
    mount_namespaces: &mut BTreeSet<(u64, u64)>,
    held_namespaces: &mut Vec<File>,
) -> Result<(u64, u64)> {
    let Some(before) = start(pid)? else {
        return Ok((0, 0));
    };
    let root = PathBuf::from(format!("/proc/{pid}"));
    let entries = match std::fs::read_dir(root.join("fd")) {
        Ok(v) => v,
        Err(e) if vanished(&e) => return Ok((0, 0)),
        Err(e) => return Err(e.into()),
    };
    let mut fds = 0;
    for row in entries {
        let row = match row {
            Ok(v) => v,
            Err(e) if vanished(&e) => continue,
            Err(e) => return Err(e.into()),
        };
        fds += 1;
        ensure(
            fds <= 65536,
            "process descriptor count exceeds reference-scan bound",
        )?;
        ensure(
            !metadata_matches(&row.path(), nodes)?,
            &format!(
                "process {pid} retains descriptor {} to a data inode",
                row.file_name().to_string_lossy()
            ),
        )?;
    }
    for name in ["cwd", "root"] {
        ensure(
            !metadata_matches(&root.join(name), nodes)?,
            &format!("process {pid} retains a selected data directory as {name}"),
        )?;
    }
    let mut bytes = check_maps(pid, nodes)?;
    let namespace = match File::open(root.join("ns/mnt")) {
        Ok(v) => v,
        Err(e) if vanished(&e) => return Ok((fds, bytes)),
        Err(e) => return Err(e.into()),
    };
    let ns = fs::stat(&namespace)?;
    if mount_namespaces.insert((ns.dev, ns.ino)) {
        bytes += check_mounts(pid, nodes)?;
        held_namespaces.push(namespace);
    }
    if let Some(after) = start(pid)? {
        ensure(
            after == before,
            "process identity changed during data reference scan",
        )?;
    }
    Ok((fds, bytes))
}
fn loop_names() -> Result<BTreeSet<String>> {
    let mut names = BTreeSet::new();
    for row in std::fs::read_dir("/sys/block")? {
        let row = row?;
        let name = row.file_name().to_string_lossy().into_owned();
        if name
            .strip_prefix("loop")
            .is_some_and(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
        {
            names.insert(name);
        }
    }
    ensure(
        names.len() <= 8192,
        "loop reference inventory exceeds bound",
    )?;
    Ok(names)
}
fn check_loops(nodes: &Nodes) -> Result<usize> {
    let names = loop_names()?;
    for name in &names {
        let path = PathBuf::from("/sys/block")
            .join(name)
            .join("loop/backing_file");
        let raw = match bounded(&path, 16384) {
            Ok(v) => v,
            Err(e) => {
                if e.downcast_ref::<std::io::Error>().is_some_and(vanished) {
                    continue;
                }
                return Err(e);
            }
        };
        let value = String::from_utf8(raw.clone())?;
        let value = value.strip_suffix('\n').unwrap_or(&value);
        if value.is_empty() {
            continue;
        }
        ensure(
            !value.ends_with(" (deleted)") && !value.contains('\n') && !value.contains('\0'),
            "live loop backing cannot be resolved to an original inode",
        )?;
        let backing = if value.starts_with('/') {
            PathBuf::from(value)
        } else {
            Path::new("/").join(value)
        };
        // A missing backing is not an empty loop: the kernel may still hold a
        // deleted alias. It must be reconciled before any data directory move.
        let m = std::fs::metadata(&backing)?;
        ensure(
            !nodes.contains(&(m.dev(), m.ino())),
            "loop device retains original or working backing",
        )?;
        ensure(
            bounded(&path, 16384)? == raw,
            "loop backing changed during reference observation",
        )?;
    }
    ensure(
        loop_names()? == names,
        "loop devices changed during data reference scan",
    )?;
    Ok(names.len())
}

pub(super) fn require_no_other_references(identities: &[Identity]) -> Result<Value> {
    let nodes = identities.iter().map(|s| (s.dev, s.ino)).collect::<Nodes>();
    ensure(
        nodes.len() == identities.len() && !nodes.is_empty(),
        "distinct data reference targets required",
    )?;
    let own = std::process::id();
    let start = Instant::now();
    let mut processes = 0;
    let mut fds = 0;
    let mut bytes = 0;
    let mut namespaces = BTreeSet::new();
    let mut held = Vec::new();
    let loops_before = check_loops(&nodes)?;
    for row in std::fs::read_dir("/proc")? {
        let row = row?;
        let name = row.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        if !name.bytes().all(|b| b.is_ascii_digit()) {
            continue;
        }
        let pid: u32 = name.parse()?;
        if pid == own {
            continue;
        }
        processes += 1;
        ensure(
            processes <= 32768 && start.elapsed() < Duration::from_secs(45),
            "bounded original process reference scan expired",
        )?;
        let (n, b) = check_process(pid, &nodes, &mut namespaces, &mut held)?;
        fds += n;
        bytes += b;
        ensure(
            fds <= 2_000_000 && bytes <= 512 * 1024 * 1024,
            "complete process reference inventory exceeds bound",
        )?;
    }
    let loops_after = check_loops(&nodes)?;
    Ok(
        json!({"schema":"droidloom.original-data-reference-observation.v1","observer_pid":own,
        "target_identities":identities,"processes_observed":processes,"descriptors_observed":fds,
        "process_metadata_bytes":bytes,"mount_namespaces_observed":namespaces.len(),
        "loop_devices_before":loops_before,"loop_devices_after":loops_after,"other_references":0,
        "permission_errors":0,"elapsed_seconds":start.elapsed().as_secs_f64()}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::{Command, Stdio};
    #[test]
    fn owner_probe_child() {
        if let Ok(path) = std::env::var("DROIDLOOM_DATA_REFERENCE_CHILD") {
            let file = File::open(&path).unwrap();
            std::fs::write(
                std::env::var("DROIDLOOM_DATA_REFERENCE_READY").unwrap(),
                b"ready",
            )
            .unwrap();
            let mut byte = [0];
            let _ = std::io::stdin().read(&mut byte);
            std::hint::black_box(file);
        }
    }
    #[test]
    fn actual_foreign_descriptor_is_rejected_and_retired_child_is_not_a_holder() {
        let t = tempfile::tempdir().unwrap();
        let path = t.path().join("image");
        std::fs::write(&path, b"test bytes").unwrap();
        let held = File::open(&path).unwrap();
        let id = fs::stat(&held).unwrap();
        let nodes = BTreeSet::from([(id.dev, id.ino)]);
        let ready = t.path().join("ready");
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "cold_original_data::reference_scan::tests::owner_probe_child",
            ])
            .env("DROIDLOOM_DATA_REFERENCE_CHILD", &path)
            .env("DROIDLOOM_DATA_REFERENCE_READY", &ready)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let limit = Instant::now() + Duration::from_secs(5);
        while !ready.exists() && Instant::now() < limit {
            std::thread::sleep(Duration::from_millis(10));
        }
        let result = if ready.exists() {
            check_process(child.id(), &nodes, &mut BTreeSet::new(), &mut Vec::new())
        } else {
            Err("child did not reach the owned descriptor checkpoint".into())
        };
        drop(child.stdin.take());
        let status = child.wait().unwrap();
        assert!(status.success());
        assert!(
            result
                .unwrap_err()
                .to_string()
                .contains("retains descriptor")
        );
        assert_eq!(
            check_process(child.id(), &nodes, &mut BTreeSet::new(), &mut Vec::new()).unwrap(),
            (0, 0)
        );
    }
    #[test]
    fn kernel_mount_path_escapes_are_bounded_and_never_traversal() {
        assert_eq!(
            decode_mount_path("/data/with\\040space").unwrap(),
            Path::new("/data/with space")
        );
        for value in [
            "relative",
            "/a/../b",
            "/a/\\000b",
            "/bad\\99x",
            "/bad\\0",
            "/bad\\777",
        ] {
            assert!(decode_mount_path(value).is_err());
        }
    }
}
