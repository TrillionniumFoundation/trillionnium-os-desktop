// SPDX-License-Identifier: Apache-2.0
// Execute one original root-operator leaf through seven already-held FDs.
// The caller retains authenticated current Main/epoch and whole owned-task
// retirement. This helper does not manufacture a daemon ReadyTreeWitness,
// MAC issuer, release adoption or production qualification from an inode.
// No numeric target host PID is used for namespace entry. This is not setuid.
#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
compile_error!("This qualified helper is Linux x86_64 only.");

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CString;
use std::fs::File;
use std::io::Read;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::raw::{c_char, c_int, c_long, c_short, c_ulong};
use std::os::unix::fs::MetadataExt;
use std::ptr;

#[repr(C)]
struct PollFd { fd: c_int, events: c_short, revents: c_short }
const _: () = assert!(std::mem::size_of::<PollFd>() == 8);
#[repr(C)]
#[derive(Default)]
struct StatFs {
    kind: c_long, block_size: c_long,
    blocks: u64, blocks_free: u64, blocks_available: u64,
    files: u64, files_free: u64, fsid: [c_int; 2],
    name_length: c_long, fragment_size: c_long, flags: c_long,
    spare: [c_long; 4],
}
const _: () = assert!(std::mem::size_of::<StatFs>() == 120);
const USER: c_int = 0x10000000;
const O_CLOEXEC: c_int = 0x80000;
const O_NOFOLLOW: c_int = 0x20000;
const O_DIRECTORY: c_int = 0x10000;
const O_PATH: c_int = 0x200000;
const NS_GET_USERNS: c_ulong = 0xb701;
const NS_GET_PARENT: c_ulong = 0xb702;
const NS_GET_NSTYPE: c_ulong = 0xb703;
const NS_GET_OWNER_UID: c_ulong = 0xb704;
// Same Linux-7 UAPI initial-userns check as the pinned production broker.
const NS_GET_ID: c_ulong = 0x8008_b70d;
const USER_NS_INIT_INO: u64 = 0xefff_fffd;
const USER_NS_INIT_ID: u64 = 3;
const NSFS_MAGIC: c_long = 0x6e736673;
const PROC_MAGIC: c_long = 0x9fa0;
const ENTRIES: [(&str, &str, c_int); 6] = [
    ("--cgroup-fd", "cgroup", 0x02000000), ("--ipc-fd", "ipc", 0x08000000),
    ("--uts-fd", "uts", 0x04000000), ("--net-fd", "net", 0x40000000),
    ("--mnt-fd", "mnt", 0x00020000), ("--pid-fd", "pid", 0x20000000),
];
extern "C" {
    fn getpid() -> c_int;
    fn getppid() -> c_int;
    fn prctl(option: c_int, ...) -> c_int;
    fn fcntl(fd: c_int, command: c_int, ...) -> c_int;
    fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
    fn openat(fd: c_int, path: *const c_char, flags: c_int, ...) -> c_int;
    fn fstatfs(fd: c_int, value: *mut StatFs) -> c_int;
    fn getuid() -> u32;
    fn geteuid() -> u32;
    fn getgid() -> u32;
    fn getegid() -> u32;
    fn getgroups(count: c_int, groups: *mut u32) -> c_int;
    fn setgroups(count: usize, groups: *const u32) -> c_int;
    fn setresuid(real: u32, effective: u32, saved: u32) -> c_int;
    fn setresgid(real: u32, effective: u32, saved: u32) -> c_int;
    fn setns(fd: c_int, namespace_type: c_int) -> c_int;
    fn fchdir(fd: c_int) -> c_int;
    fn chroot(path: *const c_char) -> c_int;
    fn chdir(path: *const c_char) -> c_int;
    fn fork() -> c_int;
    fn waitpid(pid: c_int, status: *mut c_int, options: c_int) -> c_int;
    fn poll(fds: *mut PollFd, count: c_ulong, timeout: c_int) -> c_int;
    fn syscall(number: c_long, ...) -> c_long;
    fn execve(path: *const c_char, argv: *const *const c_char,
              envp: *const *const c_char) -> c_int;
    fn close(fd: c_int) -> c_int;
    fn _exit(status: c_int) -> !;
    static mut environ: *mut *mut c_char;
}

fn fail(message: &str) -> ! {
    eprintln!("held-namespace-entry: {message}");
    std::process::exit(125);
}
fn checked(result: c_int, operation: &str) {
    if result < 0 {
        fail(&format!("{operation}: {}", std::io::Error::last_os_error()));
    }
}
fn cloexec(fd: c_int) {
    let flags = unsafe { fcntl(fd, 1) }; // F_GETFD
    checked(flags, "get FD flags");
    checked(unsafe { fcntl(fd, 2, flags | 1) }, "set FD_CLOEXEC");
}

fn need(value: bool, message: &str) {
    if !value { fail(message); }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Node { device: u64, inode: u64 }
fn node(fd: c_int) -> Node {
    // Duplicate solely for safe std metadata access; never replace the held FD.
    let duplicate = unsafe { fcntl(fd, 1030, 3) }; // F_DUPFD_CLOEXEC
    checked(duplicate, "duplicate held descriptor for metadata");
    let file = unsafe { File::from_raw_fd(duplicate) };
    let meta = file.metadata().unwrap_or_else(|e| fail(&format!("held metadata: {e}")));
    Node { device: meta.dev(), inode: meta.ino() }
}
fn fs_type(fd: c_int, kind: c_long) {
    let mut actual = StatFs::default();
    checked(unsafe { fstatfs(fd, &mut actual) }, "held filesystem type");
    need(actual.kind == kind, "held descriptor belongs to a different filesystem");
}
fn namespace(fd: c_int, kind: c_int) -> Node {
    fs_type(fd, NSFS_MAGIC);
    let actual = unsafe { ioctl(fd, NS_GET_NSTYPE) };
    checked(actual, "held namespace type");
    need(actual == kind, "held namespace has wrong type");
    node(fd)
}
fn from_kernel(fd: c_int, message: &str) -> File {
    checked(fd, message);
    need(fd >= 3, "kernel descriptor aliases a standard stream");
    cloexec(fd);
    unsafe { File::from_raw_fd(fd) }
}
fn fixed_open(parent: c_int, name: &str, flags: c_int) -> File {
    need(!name.is_empty() && !name.contains('/') && name != "." && name != "..",
         "internal fixed component only");
    let name = CString::new(name).unwrap_or_else(|_| fail("NUL component"));
    from_kernel(unsafe { openat(parent, name.as_ptr(), flags | O_CLOEXEC) },
                "open fixed held component")
}
fn proc_read(parent: c_int, name: &str, limit: u64) -> Vec<u8> {
    let file = fixed_open(parent, name, O_NOFOLLOW);
    fs_type(file.as_raw_fd(), PROC_MAGIC);
    let mut body = Vec::new();
    file.take(limit + 1).read_to_end(&mut body)
        .unwrap_or_else(|e| fail(&format!("held proc read: {e}")));
    need(body.len() as u64 <= limit, "held proc body exceeds its finite bound");
    body
}
fn root_map(raw: &[u8]) -> Option<(u32, u32)> {
    let text = std::str::from_utf8(raw).ok()?;
    let lines = text.lines().collect::<Vec<_>>();
    if lines.len() != 1 { return None; }
    let fields = lines[0].split_whitespace().collect::<Vec<_>>();
    if fields.len() != 3 || fields[0] != "0" { return None; }
    let start = fields[1].parse::<u32>().ok()?;
    let count = fields[2].parse::<u32>().ok()?;
    if start == 0 || count == 0 || start.checked_add(count).is_none() { return None; }
    Some((start, count))
}
fn init_start(raw: &[u8]) -> Option<u64> {
    let text = std::str::from_utf8(raw).ok()?;
    if !text.starts_with("1 (") { return None; }
    let (_, rest) = text.rsplit_once(") ")?;
    let fields = rest.split_whitespace().collect::<Vec<_>>();
    if fields.len() < 20 || matches!(fields[0], "Z" | "X" | "x") { return None; }
    let value = fields[19].parse::<u64>().ok()?;
    (value > 0).then_some(value)
}

struct Arguments {
    values: BTreeMap<String, c_int>,
    userns: Node,
    init_start: u64,
    command: Vec<String>,
}
fn parse(arguments: &[String]) -> Result<Arguments, &'static str> {
    let separator = arguments.iter().position(|s| s == "--")
        .ok_or("missing -- command separator")?;
    if separator + 1 >= arguments.len() { return Err("missing command"); }
    let mut values = BTreeMap::<String, c_int>::new();
    let mut expected = BTreeMap::<String, u64>::new();
    for arg in &arguments[..separator] {
        let (name, raw) = arg.split_once('=').ok_or("expected --name=value")?;
        if raw.is_empty() || raw.starts_with('0') || !raw.bytes().all(|b| b.is_ascii_digit()) {
            return Err("positive canonical decimal integer required");
        }
        if ["--expected-userns-device", "--expected-userns-inode", "--expected-init-start-ticks"].contains(&name) {
            let value: u64 = raw.parse().map_err(|_| "invalid full kernel identity integer")?;
            if expected.insert(name.to_owned(), value).is_some() { return Err("duplicate comparison"); }
            continue;
        }
        if !["--parent-pid", "--root-fd", "--mnt-fd", "--pid-fd",
             "--uts-fd", "--ipc-fd", "--net-fd", "--cgroup-fd"].contains(&name) {
            return Err("unknown option");
        }
        let value: c_int = raw.parse().map_err(|_| "invalid integer")?;
        if value <= 1 || (name != "--parent-pid" && value < 3) {
            return Err("invalid parent PID or descriptor");
        }
        if values.insert(name.to_owned(), value).is_some() { return Err("duplicate option"); }
    }
    if values.len() != 8 || expected.len() != 3 { return Err("exact seven FDs and complete Main comparisons required"); }
    let descriptors = values.iter().filter(|(name, _)| name.as_str() != "--parent-pid")
        .map(|(_, value)| *value).collect::<BTreeSet<_>>();
    if descriptors.len() != 7 { return Err("descriptor aliases another authority"); }
    let command = arguments[separator + 1..].to_vec();
    if !command[0].starts_with('/') || command.iter().any(|s| s.contains('\0')) {
        return Err("absolute command without NUL required");
    }
    Ok(Arguments { values,
        userns: Node { device: expected["--expected-userns-device"], inode: expected["--expected-userns-inode"] },
        init_start: expected["--expected-init-start-ticks"], command })
}

struct MainBinding {
    user: File,
    proc_one: File,
    ns_dir: File,
    user_map: Vec<u8>,
    group_map: Vec<u8>,
    root: Node,
}
impl MainBinding {
    fn capture(args: &Arguments) -> Self {
        // No permission is obtained from this check. The process must already
        // be the original privileged operator in the same initial host userns.
        need(unsafe { getuid() == 0 && geteuid() == 0 && getgid() == 0 && getegid() == 0 },
             "initial privileged root operator required");
        let initial = File::open("/proc/self/ns/user")
            .unwrap_or_else(|e| fail(&format!("own user namespace: {e}")));
        let initial_node = namespace(initial.as_raw_fd(), USER);
        let mut initial_id = 0_u64;
        checked(unsafe { ioctl(initial.as_raw_fd(), NS_GET_ID, &mut initial_id) }, "initial namespace ID");
        need(initial_node.inode == USER_NS_INIT_INO && initial_id == USER_NS_INIT_ID,
             "same production initial-userns identifiers required");
        namespace(args.values["--mnt-fd"], 0x00020000);
        let user = from_kernel(unsafe { ioctl(args.values["--mnt-fd"], NS_GET_USERNS) },
                               "derive owning userns from held mount namespace");
        need(namespace(user.as_raw_fd(), USER) == args.userns && args.userns != initial_node,
             "derived namespace is not the exact held Main userns");
        let parent = from_kernel(unsafe { ioctl(user.as_raw_fd(), NS_GET_PARENT) }, "derive actual userns parent");
        need(namespace(parent.as_raw_fd(), USER) == initial_node, "Main userns is not the original direct child");
        let mut owner = u32::MAX;
        checked(unsafe { ioctl(user.as_raw_fd(), NS_GET_OWNER_UID, &mut owner) }, "actual userns owner UID");
        need(owner == 0, "Main userns was not created by the privileged broker");
        for (option, _, kind) in ENTRIES {
            namespace(args.values[option], kind);
            let owner = from_kernel(unsafe { ioctl(args.values[option], NS_GET_USERNS) }, "held namespace owner");
            need(namespace(owner.as_raw_fd(), USER) == args.userns, "mixed namespace owners");
        }
        // Fixed PID 1 is resolved solely inside the supplied held Main root's
        // actual procfs. No host target PID, pathname selector or /proc scan is
        // accepted. All namespace links below are deliberately kernel links.
        let root = node(args.values["--root-fd"]);
        let proc = fixed_open(args.values["--root-fd"], "proc", O_PATH | O_DIRECTORY | O_NOFOLLOW);
        fs_type(proc.as_raw_fd(), PROC_MAGIC);
        let proc_one = fixed_open(proc.as_raw_fd(), "1", O_PATH | O_DIRECTORY | O_NOFOLLOW);
        fs_type(proc_one.as_raw_fd(), PROC_MAGIC);
        let ns_dir = fixed_open(proc_one.as_raw_fd(), "ns", O_PATH | O_DIRECTORY | O_NOFOLLOW);
        let user_map = proc_read(proc_one.as_raw_fd(), "uid_map", 4096);
        let group_map = proc_read(proc_one.as_raw_fd(), "gid_map", 4096);
        root_map(&user_map).unwrap_or_else(|| fail("invalid mapped Main UID extent"));
        root_map(&group_map).unwrap_or_else(|| fail("invalid mapped Main GID extent"));
        let mut binding = Self { user, proc_one, ns_dir, user_map, group_map, root };
        binding.guard(args);
        binding
    }
    fn guard(&mut self, args: &Arguments) {
        need(node(self.user.as_raw_fd()) == args.userns, "held userns changed");
        let observed_user = fixed_open(self.ns_dir.as_raw_fd(), "user", 0);
        need(namespace(observed_user.as_raw_fd(), USER) == args.userns, "Main proc userns differs");
        for (option, name, kind) in ENTRIES {
            let actual = fixed_open(self.ns_dir.as_raw_fd(), name, 0);
            need(namespace(actual.as_raw_fd(), kind) == namespace(args.values[option], kind),
                 "actual original init namespace differs from transferred descriptor");
        }
        let root = fixed_open(self.proc_one.as_raw_fd(), "root", O_PATH | O_DIRECTORY);
        need(node(root.as_raw_fd()) == self.root && node(args.values["--root-fd"]) == self.root,
             "actual original init root differs from transferred descriptor");
        need(init_start(&proc_read(self.proc_one.as_raw_fd(), "stat", 8192)) == Some(args.init_start),
             "actual fixed Main init generation changed");
        need(proc_read(self.proc_one.as_raw_fd(), "uid_map", 4096) == self.user_map
             && proc_read(self.proc_one.as_raw_fd(), "gid_map", 4096) == self.group_map,
             "actual Main maps changed");
    }
}

fn alive(fd: c_int) {
    let mut current = PollFd { fd, events: 1, revents: 0 };
    need(unsafe { poll(&mut current, 1, 0) } == 0, "original parent exited");
}
fn arm_parent(parent: c_int, pidfd: c_int) {
    checked(unsafe { prctl(1, 9 as c_ulong, 0 as c_ulong, 0 as c_ulong, 0 as c_ulong) },
            "set launcher parent-death signal");
    need(unsafe { getppid() } == parent, "original launcher parent changed");
    alive(pidfd);
}

fn main() {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let args = parse(&arguments).unwrap_or_else(|message| fail(message));
    let values = &args.values;
    let parent = values["--parent-pid"];
    if unsafe { getppid() } != parent { fail("unexpected launcher parent"); }
    checked(unsafe { prctl(1, 9 as c_ulong, 0 as c_ulong, 0 as c_ulong, 0 as c_ulong) },
            "set launcher parent-death signal");
    if unsafe { getppid() } != parent { fail("launcher parent exited during admission"); }

    let parent_pidfd = from_kernel(unsafe { syscall(434, parent as c_long, 0 as c_long) } as c_int,
                                  "pin original launcher parent");
    arm_parent(parent, parent_pidfd.as_raw_fd());
    let root = values["--root-fd"];
    let mut unique = BTreeSet::<c_int>::new();
    for (name, fd) in values {
        if name == "--parent-pid" { continue; }
        if !unique.insert(*fd) { fail("descriptor aliases another authority"); }
        cloexec(*fd); // pass_fds cleared this flag; restore it before the final exec.
    }
    let mut binding = MainBinding::capture(&args);
    let command: Vec<CString> = args.command.iter()
        .map(|s| CString::new(s.as_bytes()).unwrap_or_else(|_| fail("NUL in command"))).collect();
    let mut argv: Vec<*const c_char> = command.iter().map(|s| s.as_ptr()).collect();
    argv.push(ptr::null());
    // A pidfd remains meaningful in the child's different PID namespace.
    // getppid() alone could become zero there and cannot close this race.
    let own_pidfd = unsafe { syscall(434, getpid() as c_long, 0 as c_long) }; // pidfd_open
    if own_pidfd < 0 || own_pidfd > c_int::MAX as c_long { fail("cannot pin entry parent"); }
    let own_pidfd = own_pidfd as c_int;
    cloexec(own_pidfd);
    binding.guard(&args);
    alive(parent_pidfd.as_raw_fd());
    // Groups cannot retain host IDs across this transition. Joining a userns
    // changes capability scope, but does not itself translate the current
    // kernel UID into guest zero. Set both GID and UID explicitly afterwards.
    checked(unsafe { setgroups(0, ptr::null()) }, "clear host supplementary groups");
    need(unsafe { getgroups(0, ptr::null_mut()) } == 0, "host groups remain");
    checked(unsafe { setns(binding.user.as_raw_fd(), USER) }, "enter derived held Main user namespace");
    arm_parent(parent, parent_pidfd.as_raw_fd());
    checked(unsafe { setresgid(0, 0, 0) }, "select fixed guest root GID");
    arm_parent(parent, parent_pidfd.as_raw_fd());
    checked(unsafe { setresuid(0, 0, 0) }, "select fixed guest root UID");
    arm_parent(parent, parent_pidfd.as_raw_fd());
    need(unsafe { getuid() == 0 && geteuid() == 0 && getgid() == 0 && getegid() == 0
        && getgroups(0, ptr::null_mut()) == 0 }, "guest root or empty groups were not established");
    for (name, _, kind) in ENTRIES {
        if let Some(fd) = values.get(name) {
            checked(unsafe { setns(*fd, kind) }, "enter held namespace");
        }
    }
    checked(unsafe { fchdir(root) }, "enter held root");
    checked(unsafe { chroot(b".\0".as_ptr().cast()) }, "set held root");
    checked(unsafe { chdir(b"/\0".as_ptr().cast()) }, "set root working directory");
    // uid_map/gid_map text is relative to the reading userns; the pre-entry
    // host representation was already checked twice. Namespace/root/start
    // comparisons below stay physical and are not inferred from map numbers.
    need(node(binding.user.as_raw_fd()) == args.userns, "entered userns changed");
    need(init_start(&proc_read(binding.proc_one.as_raw_fd(), "stat", 8192)) == Some(args.init_start),
         "Main init ended during entry");
    arm_parent(parent, parent_pidfd.as_raw_fd());
    let child = unsafe { fork() };
    checked(child, "fork into held PID namespace");
    if child == 0 {
        checked(unsafe { prctl(1, 9 as c_ulong, 0 as c_ulong, 0 as c_ulong, 0 as c_ulong) },
                "set entry parent-death signal");
        let mut parent_poll = PollFd { fd: own_pidfd, events: 1, revents: 0 };
        let ready = unsafe { poll(&mut parent_poll, 1, 0) };
        if ready != 0 { fail("entry parent exited before command"); }
        need(init_start(&proc_read(binding.proc_one.as_raw_fd(), "stat", 8192)) == Some(args.init_start),
             "Main init changed before command");
        // All namespace/root/pidfd authorities are CLOEXEC and cannot leak into
        // the Android command or its descendants.
        unsafe { execve(command[0].as_ptr(), argv.as_ptr(), environ.cast()) };
        fail(&format!("execute command: {}", std::io::Error::last_os_error()));
    }
    for fd in unique { unsafe { close(fd) }; }
    unsafe { close(own_pidfd) };
    drop(binding);
    drop(parent_pidfd);
    let mut status = 0;
    loop {
        let result = unsafe { waitpid(child, &mut status, 0) };
        if result == child { break; }
        if result < 0 && std::io::Error::last_os_error().raw_os_error() == Some(4) { continue; }
        fail("cannot reap entry child");
    }
    let signal = status & 0x7f;
    let code = if signal == 0 { (status >> 8) & 0xff } else { 128 + signal };
    unsafe { _exit(code) };
}

#[cfg(test)]
mod tests {
    use super::*;
    fn argv() -> Vec<String> {
        ["--parent-pid=42", "--root-fd=3", "--mnt-fd=4", "--pid-fd=5", "--uts-fd=6",
         "--ipc-fd=7", "--net-fd=8", "--cgroup-fd=9", "--expected-userns-device=4",
         "--expected-userns-inode=4026533000", "--expected-init-start-ticks=123456789",
         "--", "/system/bin/true"].into_iter().map(str::to_owned).collect()
    }
    #[test]
    fn exact_seven_fd_contract_and_full_width_comparisons() {
        let parsed = parse(&argv()).unwrap();
        assert_eq!(parsed.values.len(), 8);
        assert_eq!(parsed.userns.inode, 4026533000);
        assert_eq!(parsed.init_start, 123456789);
        for index in 0..11 {
            let mut missing = argv(); missing.remove(index);
            assert!(parse(&missing).is_err());
        }
    }
    #[test]
    fn aliases_unknown_options_and_noncanonical_ids_are_rejected() {
        for replacement in ["--mnt-fd=3", "--mnt-fd=0", "--mnt-fd=+4", "--mnt-fd=04",
                            "--mnt-fd=2147483648", "--target-pid=42"] {
            let mut candidate = argv(); candidate[2] = replacement.into();
            assert!(parse(&candidate).is_err());
        }
        let mut duplicate = argv(); duplicate.insert(0, "--root-fd=11".into());
        assert!(parse(&duplicate).is_err());
        let mut overflow = argv(); overflow[9] = "--expected-userns-inode=18446744073709551616".into();
        assert!(parse(&overflow).is_err());
    }
    #[test]
    fn only_complete_non_host_single_root_maps_are_accepted() {
        assert_eq!(root_map(b"         0     100000     200000\n"), Some((100000, 200000)));
        for raw in [b"0 0 4294967295\n".as_slice(), b"1 100000 200000\n", b"0 100000 0\n",
                    b"0 4294967290 20\n", b"0 100000 200000\n1 2 3\n", b"0 100000\n"] {
            assert_eq!(root_map(raw), None);
        }
    }
    #[test]
    fn fixed_pid_one_start_epoch_handles_parentheses_and_rejects_dead_init() {
        let raw = format!("1 (init (original)) S {} 987654 0\n", vec!["0"; 18].join(" "));
        assert_eq!(init_start(raw.as_bytes()), Some(987654));
        assert_eq!(init_start(raw.replacen("1 (", "2 (", 1).as_bytes()), None);
        assert_eq!(init_start(raw.replacen(") S ", ") Z ", 1).as_bytes()), None);
        assert_eq!(init_start(b"1 (init) S 0"), None);
    }
}
