//! Childless, authenticated catalog queries through the owned cell's root.
//!
//! This module never enters a namespace or starts a process. It follows only
//! kernel children of DevelopmentCell's unreaped owned process, retains pidfds
//! and the discovered PID-1 root, and connects to one fixed pathname socket.

use super::{ControlError, io_error, validate_android_user, validate_component};
use std::collections::BTreeSet;
use std::ffi::CString;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::Shutdown;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::time::{Duration, Instant};

const MAGIC: &[u8; 8] = b"DLCAT001";
const SOCKET_NAME: &str = "droidloom_catalog";
const MAX_RESPONSE: usize = 2 * 1024 * 1024;
const MAX_THREADS: usize = 64;
const MAX_LINEAGE: usize = 4;
const DEADLINE: Duration = Duration::from_secs(5);

#[derive(Clone, Copy)]
pub(super) enum Query<'a> {
    List { user: u32 },
    Icon { user: u32, component: &'a str, size: u32 },
}

fn invalid(message: &'static str) -> ControlError {
    ControlError::Invalid(message.into())
}

fn require(condition: bool, message: &'static str) -> Result<(), ControlError> {
    if condition { Ok(()) } else { Err(invalid(message)) }
}

fn remaining(deadline: Instant) -> Result<Duration, ControlError> {
    deadline.checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or_else(|| invalid("Android catalog query timed out"))
}

fn open_at(directory: &File, path: &str, flags: i32) -> Result<File, ControlError> {
    let path = CString::new(path)
        .map_err(|_| invalid("invalid internal catalog path"))?;
    // SAFETY: directory is held, path is a terminated string, and openat
    // returns a new descriptor whose sole owner is the returned File.
    let fd = unsafe { libc::openat(directory.as_raw_fd(), path.as_ptr(), flags | libc::O_CLOEXEC) };
    if fd < 0 { return Err(io_error("open catalog binding object", io::Error::last_os_error())); }
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn read_at(directory: &File, path: &str, limit: usize) -> Result<Vec<u8>, ControlError> {
    let file = open_at(directory, path, libc::O_RDONLY | libc::O_NOFOLLOW)?;
    let mut output = Vec::new();
    file.take(limit as u64 + 1).read_to_end(&mut output)
        .map_err(|error| io_error("read catalog process identity", error))?;
    require(output.len() <= limit, "catalog process identity exceeds its bound")?;
    Ok(output)
}

fn text_at(directory: &File, path: &str, limit: usize) -> Result<String, ControlError> {
    String::from_utf8(read_at(directory, path, limit)?)
        .map_err(|_| invalid("catalog process identity is not UTF-8"))
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Object(u64, u64);

fn object(file: &File) -> Result<Object, ControlError> {
    let metadata = file.metadata().map_err(|error| io_error("stat catalog binding object", error))?;
    Ok(Object(metadata.dev(), metadata.ino()))
}

fn positive(value: &str) -> Result<u32, ControlError> {
    require(!value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()),
            "catalog process identifier is malformed")?;
    let value = value.parse().map_err(|_| invalid("catalog process identifier is out of range"))?;
    require(value > 0, "catalog process identifier is zero")?;
    Ok(value)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Key {
    pid: u32,
    parent: u32,
    start: u64,
    namespace_pids: Vec<u32>,
    uids: Vec<u32>,
    proc: Object,
    root: Object,
    pid_ns: Object,
    user_ns: Object,
    net_ns: Object,
    mount_ns: Object,
}

fn key(proc: &File, pid: u32) -> Result<Key, ControlError> {
    let stat = text_at(proc, "stat", 8192)?;
    let prefix = format!("{pid} (");
    require(stat.starts_with(&prefix), "catalog process stat PID differs")?;
    let end = stat.rfind(')').ok_or_else(|| invalid("catalog process stat is incomplete"))?;
    let fields: Vec<_> = stat[end + 1..].split_whitespace().collect();
    require(fields.len() >= 20, "catalog process stat is incomplete")?;
    let parent = positive(fields[1])?;
    let start = fields[19].parse::<u64>()
        .map_err(|_| invalid("catalog process birth is malformed"))?;
    require(start != 0, "catalog process birth is zero")?;
    let status = text_at(proc, "status", 32768)?;
    let status_field = |name: &str| -> Result<&str, ControlError> {
        let mut matches = status.lines().filter_map(|line| line.strip_prefix(name));
        let value = matches.next().ok_or_else(|| invalid("catalog process status is incomplete"))?;
        require(matches.next().is_none(), "catalog process status has duplicate fields")?;
        Ok(value)
    };
    let namespace_pids: Vec<u32> = status_field("NSpid:")?.split_whitespace()
        .map(positive).collect::<Result<_, _>>()?;
    require(!namespace_pids.is_empty() && namespace_pids.len() <= 32
            && namespace_pids[0] == pid, "catalog process namespace PIDs differ")?;
    let uids: Vec<u32> = status_field("Uid:")?.split_whitespace()
        .map(|value| value.parse().map_err(|_| invalid("catalog process UID is malformed")))
        .collect::<Result<_, _>>()?;
    require(uids.len() == 4, "catalog process UID tuple is incomplete")?;
    // Only these kernel proc magic links may be followed. Their owning proc
    // directory and process are retained and checked by a live pidfd.
    let root = open_at(proc, "root", libc::O_PATH | libc::O_DIRECTORY)?;
    let pid_ns = open_at(proc, "ns/pid", libc::O_RDONLY)?;
    let user_ns = open_at(proc, "ns/user", libc::O_RDONLY)?;
    let net_ns = open_at(proc, "ns/net", libc::O_RDONLY)?;
    let mount_ns = open_at(proc, "ns/mnt", libc::O_RDONLY)?;
    Ok(Key { pid, parent, start, namespace_pids, uids, proc: object(proc)?,
        root: object(&root)?, pid_ns: object(&pid_ns)?, user_ns: object(&user_ns)?,
        net_ns: object(&net_ns)?, mount_ns: object(&mount_ns)? })
}

struct Process {
    proc: File,
    pidfd: File,
    key: Key,
}

impl Process {
    fn open(pid: u32) -> Result<Self, ControlError> {
        // SAFETY: pidfd_open has scalar arguments and does not signal a task.
        let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
        if fd < 0 {
            return Err(io_error("hold catalog process identity", io::Error::last_os_error()));
        }
        let pidfd = unsafe { File::from_raw_fd(fd as i32) };
        let proc = fs::OpenOptions::new().read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(format!("/proc/{pid}"))
            .map_err(|error| io_error("hold catalog proc directory", error))?;
        let key = key(&proc, pid)?;
        let process = Self { proc, pidfd, key };
        process.verify()?;
        Ok(process)
    }

    fn verify(&self) -> Result<(), ControlError> {
        let mut poll = libc::pollfd { fd: self.pidfd.as_raw_fd(), events: libc::POLLIN, revents: 0 };
        // SAFETY: poll points to one held pidfd and never blocks or signals it.
        let result = unsafe { libc::poll(&mut poll, 1, 0) };
        if result < 0 { return Err(io_error("observe catalog pidfd", io::Error::last_os_error())); }
        require(result == 0 && poll.revents == 0, "catalog process exited")?;
        let named = fs::symlink_metadata(format!("/proc/{}", self.key.pid))
            .map_err(|error| io_error("recheck catalog proc directory", error))?;
        require(Object(named.dev(), named.ino()) == self.key.proc
                && key(&self.proc, self.key.pid)? == self.key,
                "catalog process binding changed")
    }

    fn children(&self) -> Result<(Vec<u32>, Vec<u32>), ControlError> {
        let tasks = open_at(&self.proc, "task",
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
        let directory = PathBuf::from(format!("/proc/self/fd/{}", tasks.as_raw_fd()));
        let list = || -> Result<Vec<u32>, ControlError> {
            let mut ids = Vec::new();
            for entry in fs::read_dir(&directory)
                    .map_err(|error| io_error("enumerate catalog parent threads", error))? {
                let entry = entry.map_err(|error| io_error("read catalog parent thread", error))?;
                require(ids.len() < MAX_THREADS, "catalog parent thread limit exceeded")?;
                let name = entry.file_name();
                ids.push(positive(name.to_str()
                    .ok_or_else(|| invalid("catalog thread identifier is not UTF-8"))?)?);
            }
            ids.sort_unstable();
            require(!ids.is_empty() && ids.contains(&self.key.pid)
                    && !ids.windows(2).any(|pair| pair[0] == pair[1]),
                    "catalog parent thread table is incomplete")?;
            Ok(ids)
        };
        let tids = list()?;
        let mut children = BTreeSet::new();
        for tid in &tids {
            let thread = open_at(&tasks, &tid.to_string(),
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
            for pid in text_at(&thread, "children", 8192)?.split_whitespace() {
                require(children.len() < 64 && children.insert(positive(pid)?),
                        "catalog parent child table is invalid")?;
            }
        }
        require(list()? == tids, "catalog parent threads changed during observation")?;
        self.verify()?;
        Ok((tids, children.into_iter().collect()))
    }
}

struct OwnedRoot {
    chain: Vec<Process>,
    tables: Vec<(Vec<u32>, Vec<u32>)>,
    root: File,
}

impl OwnedRoot {
    fn capture(owner: u32, deadline: Instant) -> Result<Self, ControlError> {
        remaining(deadline)?;
        let owner = Process::open(owner)?;
        // DevelopmentCell owns the unreaped child; arbitrary process names,
        // global /proc scans and remembered init PIDs are never authorities.
        let our_pid = std::process::id();
        require(owner.key.parent == our_pid, "catalog namespace owner is not our child")?;
        let owner_namespace = owner.key.pid_ns.clone();
        let owner_depth = owner.key.namespace_pids.len();
        let owner_user = owner.key.user_ns.clone();
        let owner_net = owner.key.net_ns.clone();
        let mut chain = vec![owner];
        let mut tables = Vec::new();
        loop {
            remaining(deadline)?;
            let parent = chain.last().expect("owned lineage is nonempty");
            let table = parent.children()?;
            require(table.1.len() == 1, "catalog owner must have one exact direct child")?;
            require(chain.len() < MAX_LINEAGE, "catalog owned init lineage exceeds its bound")?;
            let child = Process::open(table.1[0])?;
            require(child.key.parent == parent.key.pid
                    && child.key.user_ns == owner_user && child.key.net_ns == owner_net,
                    "catalog owned child relationship changed")?;
            let is_init = child.key.namespace_pids.last() == Some(&1);
            if is_init {
                require(child.key.namespace_pids.len() == owner_depth + 1
                        && child.key.pid_ns != owner_namespace,
                        "catalog init is not the owned child PID namespace")?;
            } else {
                require(child.key.namespace_pids.len() == owner_depth
                        && child.key.pid_ns == owner_namespace,
                        "catalog intermediate namespace differs")?;
            }
            tables.push(table);
            chain.push(child);
            if is_init { break; }
        }
        let init = chain.last().expect("owned init was found");
        let root = open_at(&init.proc, "root", libc::O_PATH | libc::O_DIRECTORY)?;
        require(object(&root)? == init.key.root, "catalog init root changed")?;
        let binding = Self { chain, tables, root };
        binding.verify(deadline)?;
        Ok(binding)
    }

    fn verify(&self, deadline: Instant) -> Result<(), ControlError> {
        remaining(deadline)?;
        for (index, process) in self.chain.iter().enumerate() {
            process.verify()?;
            if index < self.tables.len() {
                require(process.children()? == self.tables[index],
                        "catalog owned lineage changed")?;
            }
            remaining(deadline)?;
        }
        require(object(&self.root)? == self.chain.last().expect("owned init").key.root,
                "catalog held root changed")
    }

    fn peer(&self, stream: &UnixStream) -> Result<Process, ControlError> {
        let credentials = credentials(stream)?;
        require(credentials.uid == 0 && credentials.pid > 0,
                "catalog endpoint peer is not root")?;
        let peer = Process::open(credentials.pid as u32)?;
        let init = &self.chain.last().expect("owned init").key;
        require(peer.key.parent == init.pid && peer.key.uids == vec![0; 4]
                && peer.key.pid_ns == init.pid_ns && peer.key.user_ns == init.user_ns
                && peer.key.net_ns == init.net_ns && peer.key.root == init.root,
                "catalog endpoint peer is outside the owned init")?;
        Ok(peer)
    }
}

fn credentials(stream: &UnixStream) -> Result<libc::ucred, ControlError> {
    let mut credentials: libc::ucred = unsafe { std::mem::zeroed() };
    let mut size = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: the two output pointers refer to correctly sized live storage.
    let result = unsafe { libc::getsockopt(stream.as_raw_fd(), libc::SOL_SOCKET,
        libc::SO_PEERCRED, (&mut credentials as *mut libc::ucred).cast(), &mut size) };
    if result != 0 { return Err(io_error("read catalog peer credentials", io::Error::last_os_error())); }
    require(size as usize == std::mem::size_of::<libc::ucred>(),
            "catalog peer credentials are incomplete")?;
    Ok(credentials)
}

fn poll_ready(stream: &UnixStream, events: i16, deadline: Instant) -> Result<(), ControlError> {
    loop {
        let left = remaining(deadline)?;
        let millis = i32::try_from(left.as_millis() + 1).unwrap_or(i32::MAX);
        let mut poll = libc::pollfd { fd: stream.as_raw_fd(), events, revents: 0 };
        // SAFETY: poll observes one held socket and a bounded timeout.
        let result = unsafe { libc::poll(&mut poll, 1, millis) };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted { continue; }
            return Err(io_error("wait for catalog response", error));
        }
        require(poll.revents & libc::POLLNVAL == 0, "catalog socket descriptor is invalid")?;
        if result > 0 && poll.revents & (events | libc::POLLHUP | libc::POLLERR) != 0 {
            return Ok(());
        }
    }
}

fn connect_path(path: &str, deadline: Instant) -> Result<UnixStream, ControlError> {
    let bytes = path.as_bytes();
    let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    require(!bytes.contains(&0) && bytes.len() < address.sun_path.len(),
            "catalog socket pathname exceeds its bound")?;
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    for (destination, byte) in address.sun_path.iter_mut().zip(bytes) {
        *destination = *byte as libc::c_char;
    }
    // SAFETY: socket has no pointers and yields one uniquely owned descriptor.
    let fd = unsafe { libc::socket(libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC, 0) };
    if fd < 0 { return Err(io_error("open catalog socket", io::Error::last_os_error())); }
    let stream = unsafe { UnixStream::from_raw_fd(fd) };
    let size = (std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1)
        as libc::socklen_t;
    // SAFETY: address and size describe the bounded pathname initialized above.
    let result = unsafe { libc::connect(fd, (&address as *const libc::sockaddr_un).cast(), size) };
    if result != 0 {
        let error = io::Error::last_os_error();
        require(error.raw_os_error() == Some(libc::EINPROGRESS),
                "catalog endpoint is unavailable")?;
        poll_ready(&stream, libc::POLLOUT, deadline)?;
        if let Some(error) = stream.take_error()
                .map_err(|error| io_error("check catalog connection", error))? {
            return Err(io_error("connect catalog endpoint", error));
        }
    }
    remaining(deadline)?;
    Ok(stream)
}

fn encode(query: Query<'_>) -> Result<Vec<u8>, ControlError> {
    let (operation, user, size, component) = match query {
        Query::List { user } => (1_u8, user, 0_u32, ""),
        Query::Icon { user, component, size } => {
            validate_component(component)?;
            require((16..=512).contains(&size), "catalog icon size is outside its bound")?;
            (2_u8, user, size, component)
        }
    };
    validate_android_user(user)?;
    let mut frame = Vec::with_capacity(19 + component.len());
    frame.extend_from_slice(MAGIC);
    frame.push(operation);
    frame.extend_from_slice(&user.to_be_bytes());
    frame.extend_from_slice(&size.to_be_bytes());
    frame.extend_from_slice(&(component.len() as u16).to_be_bytes());
    frame.extend_from_slice(component.as_bytes());
    Ok(frame)
}

fn write_all(stream: &mut UnixStream, bytes: &[u8], deadline: Instant) -> Result<(), ControlError> {
    let mut remaining_bytes = bytes;
    while !remaining_bytes.is_empty() {
        remaining(deadline)?;
        match stream.write(remaining_bytes) {
            Ok(0) => return Err(invalid("catalog socket closed while sending")),
            Ok(count) => remaining_bytes = &remaining_bytes[count..],
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                poll_ready(stream, libc::POLLOUT, deadline)?;
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(io_error("send catalog query", error)),
        }
    }
    stream.shutdown(Shutdown::Write).map_err(|error| io_error("finish catalog query frame", error))
}

fn read_some(stream: &mut UnixStream, bytes: &mut [u8], deadline: Instant)
        -> Result<usize, ControlError> {
    loop {
        remaining(deadline)?;
        match stream.read(bytes) {
            Ok(count) => return Ok(count),
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                poll_ready(stream, libc::POLLIN, deadline)?;
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(io_error("read catalog response", error)),
        }
    }
}

fn read_exact(stream: &mut UnixStream, bytes: &mut [u8], deadline: Instant)
        -> Result<(), ControlError> {
    let mut filled = 0;
    while filled < bytes.len() {
        let count = read_some(stream, &mut bytes[filled..], deadline)?;
        require(count != 0, "catalog response was truncated")?;
        filled += count;
    }
    Ok(())
}

fn exchange(stream: &mut UnixStream, frame: &[u8], deadline: Instant)
        -> Result<String, ControlError> {
    write_all(stream, frame, deadline)?;
    let mut header = [0_u8; 13];
    read_exact(stream, &mut header, deadline)?;
    require(&header[..8] == MAGIC, "catalog response version differs")?;
    let status = header[8];
    let length = u32::from_be_bytes(header[9..13].try_into().expect("four length bytes")) as usize;
    require(status <= 4 && length > 0 && length <= MAX_RESPONSE,
            "catalog response exceeds its declared bound")?;
    let mut payload = vec![0_u8; length];
    read_exact(stream, &mut payload, deadline)?;
    let mut tail = [0_u8; 1];
    require(read_some(stream, &mut tail, deadline)? == 0, "catalog response has trailing data")?;
    let payload = String::from_utf8(payload)
        .map_err(|_| invalid("catalog response is not UTF-8"))?;
    if status != 0 {
        let expected = ["", "INVALID_REQUEST", "CATALOG_UNAVAILABLE", "CATALOG_BUSY",
            "CATALOG_OUTPUT_LIMIT"][status as usize];
        require(payload == expected, "catalog error response is not in the closed vocabulary")?;
        return Err(ControlError::Invalid(format!("Android catalog unavailable: {payload}")));
    }
    Ok(payload)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct DirectoryKey {
    object: Object,
    mode: u32,
    uid: u32,
    gid: u32,
}

fn directory_key(file: &File) -> Result<DirectoryKey, ControlError> {
    let metadata = file.metadata().map_err(|error| io_error("stat catalog path directory", error))?;
    require(metadata.mode() & libc::S_IFMT == libc::S_IFDIR,
            "catalog path component is not a directory")?;
    Ok(DirectoryKey { object: Object(metadata.dev(), metadata.ino()),
        mode: metadata.mode(), uid: metadata.uid(), gid: metadata.gid() })
}

struct SocketDirectory {
    root: File,
    dev: File,
    directory: File,
    root_key: DirectoryKey,
    dev_key: DirectoryKey,
    directory_key: DirectoryKey,
}

impl SocketDirectory {
    fn verify(&self) -> Result<(), ControlError> {
        require(directory_key(&self.root)? == self.root_key,
                "catalog held root metadata changed")?;
        for (parent, name, held, expected) in [
            (&self.root, "dev", &self.dev, &self.dev_key),
            (&self.dev, "socket", &self.directory, &self.directory_key),
        ] {
            let named = open_at(parent, name,
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
            require(directory_key(held)? == *expected && directory_key(&named)? == *expected,
                    "catalog socket directory edge changed")?;
        }
        Ok(())
    }
}

fn socket_directory(root: &File, uid: u32) -> Result<SocketDirectory, ControlError> {
    let root = root.try_clone().map_err(|error| io_error("hold catalog root", error))?;
    let dev = open_at(&root, "dev", libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
    let directory = open_at(&dev, "socket",
        libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;
    let binding = SocketDirectory {
        root_key: directory_key(&root)?,
        dev_key: directory_key(&dev)?,
        directory_key: directory_key(&directory)?,
        root, dev, directory,
    };
    for key in [&binding.dev_key, &binding.directory_key] {
        require(key.uid == uid && key.mode & 0o022 == 0,
                "catalog socket directory is not root controlled")?;
    }
    binding.verify()?;
    Ok(binding)
}

fn socket_object(directory: &File, uid: u32, gid: u32)
        -> Result<(Object, u32, u32, u32), ControlError> {
    let socket = open_at(directory, SOCKET_NAME, libc::O_PATH | libc::O_NOFOLLOW)?;
    let metadata = socket.metadata().map_err(|error| io_error("stat catalog socket", error))?;
    require(metadata.mode() & libc::S_IFMT == libc::S_IFSOCK
            && metadata.mode() & 0o7777 == 0o600 && metadata.uid() == uid && metadata.gid() == gid,
            "catalog socket is not the root-only init endpoint")?;
    Ok((Object(metadata.dev(), metadata.ino()), metadata.mode(), metadata.uid(), metadata.gid()))
}

// The production caller fixes uid/gid to root. Host tests reuse the complete
// transport and socket checks with their own private non-root fixture directory.
fn query_endpoint(
    directory: &SocketDirectory,
    uid: u32,
    gid: u32,
    frame: &[u8],
    deadline: Instant,
    bind_peer: impl FnOnce(&UnixStream) -> Result<Process, ControlError>,
    verify_binding: impl Fn() -> Result<(), ControlError>,
) -> Result<String, ControlError> {
    verify_binding()?;
    directory.verify()?;
    let before_socket = socket_object(&directory.directory, uid, gid)?;
    let path = format!("/proc/self/fd/{}/{}", directory.directory.as_raw_fd(), SOCKET_NAME);
    let mut stream = connect_path(&path, deadline)?;
    let peer = bind_peer(&stream)?;
    verify_binding()?;
    directory.verify()?;
    require(socket_object(&directory.directory, uid, gid)? == before_socket,
            "catalog endpoint was replaced")?;
    let result = exchange(&mut stream, frame, deadline);
    let verification = (|| {
        peer.verify()?;
        verify_binding()?;
        directory.verify()?;
        require(socket_object(&directory.directory, uid, gid)? == before_socket,
                "catalog endpoint was replaced")
    })();
    match (result, verification) {
        (Ok(result), Ok(())) => Ok(result),
        (Err(primary), Ok(())) => Err(primary),
        (Ok(_), Err(error)) => Err(error),
        (Err(primary), Err(_)) => Err(ControlError::Invalid(format!(
            "{primary}; final catalog binding could not also be verified"))),
    }
}

pub(super) fn query(owner: u32, request: Query<'_>) -> Result<String, ControlError> {
    let frame = encode(request)?;
    let deadline = Instant::now() + DEADLINE;
    // Only a test build can substitute its owned temporary directory and peer
    // identity for an Android root. No transport, protocol, PM result, or
    // Daemon::handle method is replaced by that narrow authority adapter.
    #[cfg(test)]
    if let Some(result) = tests::query_fixture(owner, &frame, deadline) {
        return result;
    }
    let binding = OwnedRoot::capture(owner, deadline)?;
    let directory = socket_directory(&binding.root, 0)?;
    query_endpoint(&directory, 0, 0, &frame, deadline,
        |stream| binding.peer(stream), || binding.verify(deadline))
}

#[cfg(test)]
#[path = "control_catalog_tests.rs"]
pub(super) mod tests;
