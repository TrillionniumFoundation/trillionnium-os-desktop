//! Explicit host qualification only. No product namespace or egress authority.
//!
//! This runs before embedder threads or Servo content startup. A separate host
//! supervisor must bind these observations to actual retained process handles.

use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpStream, UdpSocket};
use std::os::fd::{AsRawFd, BorrowedFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, Instant};

pub const PROFILE: &str = "immutable-origin-v1";
const MAX_FDS: usize = 256;
const MAX_PROC_BYTES: u64 = 8192;
const PROBE_BUDGET: Duration = Duration::from_secs(10);

unsafe extern "C" {
    fn getsockopt(fd: i32, level: i32, name: i32, value: *mut i32, length: *mut u32) -> i32;
    fn getuid() -> u32;
    fn raise(signal: i32) -> i32;
}

#[derive(Clone, Copy, Debug)]
pub enum Role {
    Embedder,
    Content,
}

impl Role {
    fn as_str(self) -> &'static str {
        match self {
            Self::Embedder => "embedder",
            Self::Content => "content",
        }
    }
}

/// Opaque observation of the current process, never an installed permit.
pub struct QualificationProfile {
    owner_pid: u32,
    network_namespace_inode: u64,
}

impl QualificationProfile {
    pub fn check_current(&self) -> io::Result<()> {
        if self.owner_pid != std::process::id()
            || self.network_namespace_inode != namespace_inode()?
        {
            return Err(refused("qualification process namespace changed"));
        }
        Ok(())
    }
}

fn refused(message: &'static str) -> io::Error {
    io::Error::other(message)
}

fn bounded_proc(path: impl AsRef<Path>) -> io::Result<String> {
    let mut file = File::open(path)?;
    let mut result = String::new();
    Read::by_ref(&mut file)
        .take(MAX_PROC_BYTES + 1)
        .read_to_string(&mut result)?;
    if result.len() as u64 > MAX_PROC_BYTES {
        return Err(refused("qualification proc record exceeded bound"));
    }
    Ok(result)
}

fn namespace_inode() -> io::Result<u64> {
    let name = fs::read_link("/proc/self/ns/net")?;
    let raw = name
        .to_str()
        .ok_or_else(|| refused("namespace name is not UTF-8"))?;
    let digits = raw
        .strip_prefix("net:[")
        .and_then(|raw| raw.strip_suffix(']'))
        .ok_or_else(|| refused("namespace name is not canonical"))?;
    positive_decimal(digits)
}

fn positive_decimal(raw: &str) -> io::Result<u64> {
    if raw.is_empty() || raw.starts_with('0') || !raw.bytes().all(|value| value.is_ascii_digit()) {
        return Err(refused("qualification integer is not canonical"));
    }
    raw.parse::<u64>()
        .map_err(|_| refused("qualification integer overflow"))
}

fn start_time() -> io::Result<u64> {
    let stat = bounded_proc("/proc/self/stat")?;
    let after_name = stat
        .rsplit_once(')')
        .map(|(_, after)| after)
        .ok_or_else(|| refused("qualification process stat is malformed"))?;
    positive_decimal(
        after_name
            .split_whitespace()
            .nth(19)
            .ok_or_else(|| refused("qualification process start is absent"))?,
    )
}

fn require_kernel_restrictions() -> io::Result<()> {
    let status = bounded_proc("/proc/self/status")?;
    for (key, expected) in [
        ("CapEff", "0000000000000000"),
        ("CapBnd", "0000000000000000"),
        ("CapAmb", "0000000000000000"),
        ("NoNewPrivs", "1"),
        ("Seccomp", "2"),
    ] {
        let matches: Vec<_> = status
            .lines()
            .filter_map(|line| line.split_once(':'))
            .filter(|(name, _)| *name == key)
            .collect();
        if matches.len() != 1 || matches[0].1.trim() != expected {
            return Err(refused("required kernel confinement is absent"));
        }
    }
    Ok(())
}

fn deadline_check(deadline: Instant) -> io::Result<()> {
    if Instant::now() >= deadline {
        return Err(refused("network qualification entry deadline exceeded"));
    }
    Ok(())
}

/// Snapshot all entry descriptors through owned duplicates. New socket creation
/// is independently refused by the actual protocol probes and the host unit.
fn descriptor_inventory(deadline: Instant) -> io::Result<Vec<(i32, u64, u64, &'static str)>> {
    let mut names = Vec::new();
    let own_directory = format!("/proc/{}/fd", std::process::id());
    for entry in fs::read_dir("/proc/self/fd")? {
        let entry = entry?;
        let raw = entry.file_name();
        let raw = raw
            .to_str()
            .ok_or_else(|| refused("descriptor name is not canonical"))?;
        let fd = raw
            .parse::<i32>()
            .map_err(|_| refused("descriptor name is not numeric"))?;
        let enumerator = fs::read_link(entry.path())?.to_str() == Some(own_directory.as_str());
        names.push((fd, enumerator));
        if names.len() > MAX_FDS {
            return Err(refused("descriptor inventory exceeded bound"));
        }
    }
    names.sort_unstable();
    let mut records = Vec::new();
    for (fd, enumerator) in names {
        deadline_check(deadline)?;
        // read_dir has retired its own descriptor. Only that specifically
        // identified proc directory may disappear from this single-thread scan.
        if enumerator {
            continue;
        }
        // SAFETY: /proc/self/fd just enumerated this process-owned descriptor;
        // cloning immediately retains it. The borrowed wrapper never closes it.
        let owned = unsafe { BorrowedFd::borrow_raw(fd) }.try_clone_to_owned()?;
        let file = File::from(owned);
        let before = file.metadata()?;
        let kind = if before.file_type().is_socket() {
            let mut domain = 0_i32;
            let mut length = std::mem::size_of::<i32>() as u32;
            // SAFETY: both output pointers refer to initialized local values;
            // SO_DOMAIN retains neither pointer. The owned duplicate stays live.
            let status = unsafe { getsockopt(file.as_raw_fd(), 1, 39, &mut domain, &mut length) };
            if status != 0 || length as usize != std::mem::size_of::<i32>() || domain != 1 {
                return Err(refused("entry holds a socket outside AF_UNIX"));
            }
            "unix_socket"
        } else if before.file_type().is_fifo() {
            "pipe"
        } else if before.file_type().is_char_device() {
            "character_device"
        } else {
            "file"
        };
        let named = fs::metadata(format!("/proc/self/fd/{fd}"))?;
        if (before.dev(), before.ino(), before.mode()) != (named.dev(), named.ino(), named.mode()) {
            return Err(refused("entry descriptor changed during inventory"));
        }
        records.push((fd, before.dev(), before.ino(), kind));
    }
    Ok(records)
}

fn canary(name: &str, ipv6: bool) -> io::Result<SocketAddr> {
    let raw = env::var(name).map_err(|_| refused("required canary endpoint is absent"))?;
    let value = raw
        .parse::<SocketAddr>()
        .map_err(|_| refused("canary endpoint is invalid"))?;
    if value.port() == 0
        || value.is_ipv6() != ipv6
        || !value.ip().is_loopback()
        || value.to_string() != raw
    {
        return Err(refused("canary endpoint is not exact loopback"));
    }
    Ok(value)
}

fn refused_protocol<T>(result: io::Result<T>) -> io::Result<i32> {
    match result {
        Err(error) if matches!(error.raw_os_error(), Some(1 | 13 | 97)) => {
            Ok(error.raw_os_error().unwrap())
        }
        _ => Err(refused("INET protocol was not refused by kernel policy")),
    }
}

fn host_observation_stop(deadline: Instant, inode: u64) -> io::Result<()> {
    deadline_check(deadline)?;
    // This qualification-only stop precedes engine/thread startup. A retained
    // host pidfd must inspect this exact stopped incarnation before resumption.
    // SAFETY: fixed Linux SIGSTOP takes no pointer and retains no data.
    if unsafe { raise(19) } != 0 {
        return Err(io::Error::last_os_error());
    }
    deadline_check(deadline)?;
    require_kernel_restrictions()?;
    if inode != namespace_inode()? {
        return Err(refused("namespace changed across host observation"));
    }
    Ok(())
}

fn publish(root: &Path, name: &str, bytes: &[u8]) -> io::Result<()> {
    if !root.is_absolute() || bytes.len() > 32768 {
        return Err(refused("qualification output is invalid"));
    }
    let mut retained = Vec::new();
    let mut named = PathBuf::from("/");
    retained.push((
        named.clone(),
        OpenOptions::new()
            .read(true)
            .custom_flags(0o400000 | 0o200000)
            .open(&named)?,
    ));
    for component in root.components().skip(1) {
        let Component::Normal(component) = component else {
            return Err(refused("qualification output path is not canonical"));
        };
        let parent = format!("/proc/self/fd/{}", retained.last().unwrap().1.as_raw_fd());
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(0o400000 | 0o200000)
            .open(Path::new(&parent).join(component))?;
        named.push(component);
        retained.push((named.clone(), directory));
    }
    let check_parents = || -> io::Result<()> {
        for (path, held) in &retained {
            let held = held.metadata()?;
            let named = fs::symlink_metadata(path)?;
            if !named.is_dir() || (held.dev(), held.ino()) != (named.dev(), named.ino()) {
                return Err(refused("qualification output ancestor was replaced"));
            }
        }
        Ok(())
    };
    check_parents()?;
    let directory = &retained.last().unwrap().1;
    let metadata = directory.metadata()?;
    // SAFETY: getuid reads this process's real UID and has no pointer argument.
    if !metadata.is_dir()
        || metadata.mode() & 0o777 != 0o700
        || metadata.uid() != unsafe { getuid() }
    {
        return Err(refused("qualification output is not private"));
    }
    let parent = format!("/proc/self/fd/{}", directory.as_raw_fd());
    let path = Path::new(&parent).join(name);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(0o400000)
        .open(&path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    check_parents()?;
    directory.sync_all()?;
    Ok(())
}

/// Default calls do nothing. An explicit profile must prove actual kernel
/// restrictions and publish its current-process entry facts or fail closed.
pub fn qualify_if_requested(role: Role, root: &Path) -> io::Result<Option<QualificationProfile>> {
    let Some(profile) = env::var_os("HEPTA_D0A02_NETNS_PROFILE") else {
        return Ok(None);
    };
    if profile != PROFILE {
        return Err(refused("unknown network qualification profile"));
    }
    let deadline = Instant::now()
        .checked_add(PROBE_BUDGET)
        .ok_or_else(|| refused("network qualification deadline overflow"))?;
    let inode = namespace_inode()?;
    let started = start_time()?;
    require_kernel_restrictions()?;
    let inventory = match descriptor_inventory(deadline) {
        Ok(inventory) => inventory,
        Err(error) => {
            // Explicit inherited-INET negatives must prove the actual offending
            // descriptor independently at this pre-engine stop. This record
            // grants no entry or runtime success and never allows continuation.
            let pid = std::process::id();
            let record = format!(
                concat!(
                    "{{\"schema\":\"trillionnium.desktop.netns-refusal.v1\",",
                    "\"profile\":\"immutable-origin-v1\",\"role\":\"{}\",\"pid\":{},\"start_time\":{},",
                    "\"network_namespace_inode\":{},\"reason\":\"entry_descriptor_inventory_refused\",",
                    "\"entry_stop_requested\":true,\"engine_started\":false,",
                    "\"source_qualification_only\":true,\"installed_qualified\":false,\"production_ready\":false}}\n"
                ),
                role.as_str(),
                pid,
                started,
                inode
            );
            publish(
                root,
                &format!("namespace-refusal-{pid}-{started}.json"),
                record.as_bytes(),
            )?;
            host_observation_stop(deadline, inode)?;
            return Err(error);
        }
    };
    let ipv4 = canary("HEPTA_NETNS_CANARY_IPV4", false)?;
    let ipv6 = canary("HEPTA_NETNS_CANARY_IPV6", true)?;
    let mut errors = Vec::new();
    for address in [ipv4, ipv6] {
        deadline_check(deadline)?;
        errors.push(refused_protocol(TcpStream::connect_timeout(
            &address,
            Duration::from_millis(250),
        ))?);
        deadline_check(deadline)?;
        errors.push(refused_protocol(UdpSocket::bind(SocketAddr::new(
            address.ip(),
            0,
        )))?);
    }
    let (mut left, mut right) = UnixStream::pair()?;
    left.set_write_timeout(Some(Duration::from_millis(250)))?;
    right.set_read_timeout(Some(Duration::from_millis(250)))?;
    left.write_all(b"hepta-netns-unix-v1")?;
    let mut received = [0_u8; 19];
    right.read_exact(&mut received)?;
    if &received != b"hepta-netns-unix-v1" {
        return Err(refused("AF_UNIX qualification payload differs"));
    }
    deadline_check(deadline)?;
    require_kernel_restrictions()?;
    if inode != namespace_inode()? {
        return Err(refused("namespace changed during entry qualification"));
    }
    let descriptors = inventory
        .iter()
        .map(|(fd, device, inode, kind)| {
            format!("{{\"fd\":{fd},\"device\":{device},\"inode\":{inode},\"kind\":\"{kind}\"}}")
        })
        .collect::<Vec<_>>()
        .join(",");
    let pid = std::process::id();
    let record = format!(
        concat!(
            "{{\"schema\":\"trillionnium.desktop.netns-entry.v1\",",
            "\"profile\":\"immutable-origin-v1\",\"role\":\"{}\",\"pid\":{},\"start_time\":{},",
            "\"network_namespace_inode\":{},\"cap_effective\":0,\"cap_bounding\":0,\"cap_ambient\":0,",
            "\"no_new_privileges\":true,\"seccomp_filter_observed\":true,",
            "\"tcp_ipv4_errno\":{},\"udp_ipv4_errno\":{},\"tcp_ipv6_errno\":{},\"udp_ipv6_errno\":{},",
            "\"unix_payload_roundtrip\":true,\"descriptor_inventory\":[{}],\"entry_stop_requested\":true,",
            "\"source_qualification_only\":true,\"installed_qualified\":false,\"production_ready\":false}}\n"
        ),
        role.as_str(),
        pid,
        started,
        inode,
        errors[0],
        errors[1],
        errors[2],
        errors[3],
        descriptors
    );
    publish(
        root,
        &format!("namespace-entry-{pid}-{started}.json"),
        record.as_bytes(),
    )?;
    host_observation_stop(deadline, inode)?;
    Ok(Some(QualificationProfile {
        owner_pid: pid,
        network_namespace_inode: inode,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn integer_parser_refuses_noncanonical_zero_and_overflow() {
        for value in ["", "0", "01", "-1", "1.0", "true", "18446744073709551616"] {
            assert!(positive_decimal(value).is_err(), "{value}");
        }
        assert_eq!(positive_decimal("123").unwrap(), 123);
    }

    #[test]
    fn namespace_and_process_start_are_actual_nonzero_facts() {
        assert!(namespace_inode().unwrap() > 0);
        assert!(start_time().unwrap() > 0);
    }

    #[test]
    fn route_failure_or_success_cannot_masquerade_as_kernel_protocol_refusal() {
        for errno in [101, 111, 110] {
            assert!(refused_protocol::<()>(Err(io::Error::from_raw_os_error(errno))).is_err());
        }
        assert!(refused_protocol(Ok(())).is_err());
        for errno in [1, 13, 97] {
            assert_eq!(
                refused_protocol::<()>(Err(io::Error::from_raw_os_error(errno))).unwrap(),
                errno
            );
        }
    }

    #[test]
    fn entry_inventory_refuses_an_actual_existing_inet_socket() {
        let _listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let result = descriptor_inventory(Instant::now() + PROBE_BUDGET);
        assert!(result.unwrap_err().to_string().contains("outside AF_UNIX"));
    }

    #[test]
    fn output_publication_refuses_an_actual_symlink_ancestor_and_shared_leaf() {
        use std::os::unix::fs::{PermissionsExt, symlink};
        let root = env::temp_dir().join(format!("hepta-netns-publish-test-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        let private = root.join("private");
        fs::create_dir(&private).unwrap();
        fs::set_permissions(&private, fs::Permissions::from_mode(0o700)).unwrap();
        let alias = root.join("alias");
        symlink(&private, &alias).unwrap();
        let result = publish(&alias, "entry.json", b"{}\n");
        assert!(result.is_err());
        assert!(!private.join("entry.json").exists());
        fs::set_permissions(&private, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(publish(&private, "entry.json", b"{}\n").is_err());
        assert!(!private.join("entry.json").exists());
        fs::set_permissions(&private, fs::Permissions::from_mode(0o700)).unwrap();
        publish(&private, "entry.json", b"{}\n").unwrap();
        assert_eq!(fs::read(private.join("entry.json")).unwrap(), b"{}\n");
        assert!(publish(&private, "entry.json", b"new").is_err());
        fs::remove_dir_all(&root).unwrap();
    }
}
