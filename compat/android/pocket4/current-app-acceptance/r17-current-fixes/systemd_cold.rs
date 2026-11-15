//! Fixed original-systemd cold diagnostics in the authenticated disposable VM.
//! This is not a policy loader, production selection, or admission constructor.
//! The original143 MAC decisions and both surrogate execs run before handoff.
use super::*;
use std::ffi::CStr;

const SYSTEMD: &str = "/usr/lib/systemd/systemd";
const SYSTEMD_BYTES: usize = 141776;
const SYSTEMD_SHA: &str = "a37f481da20c11ba2b5d06fcf549f3a0afdbfd903c7694411295e39f11f34234";
const SO_PEERPIDFD: i32 = 77;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;

fn before(until: Instant) -> R<()> {
    need(
        Instant::now() < until,
        "original manager observation deadline",
    )
}
fn node(f: &File) -> R<[u64; 9]> {
    let m = io(f.metadata())?;
    Ok([
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
        m.nlink(),
        m.len(),
        (m.mtime() as u64)
            .wrapping_mul(1_000_000_000)
            .wrapping_add(m.mtime_nsec() as u64),
        (m.ctime() as u64)
            .wrapping_mul(1_000_000_000)
            .wrapping_add(m.ctime_nsec() as u64),
    ])
}
fn open_at(dir: &File, name: &CStr, flags: i32, follow_proc_magic: bool) -> R<File> {
    let raw = unsafe {
        libc::openat(
            dir.as_raw_fd(),
            name.as_ptr(),
            flags
                | libc::O_CLOEXEC
                | if follow_proc_magic {
                    0
                } else {
                    libc::O_NOFOLLOW
                },
        )
    };
    if raw < 0 {
        return Err(format!(
            "held open {:?}: {}",
            name,
            std::io::Error::last_os_error()
        ));
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn read_proc(dir: &File, name: &CStr) -> R<Vec<u8>> {
    let file = open_at(dir, name, libc::O_RDONLY, false)?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    check(
        unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) },
        "held proc filesystem",
    )?;
    need(fs.f_type == 0x9fa0, "actual proc inode required")?;
    let mut b = Vec::new();
    io(file.take(65537).read_to_end(&mut b))?;
    need(b.len() <= 65536, "bounded actual held proc value")?;
    Ok(b)
}
fn start(raw: &[u8], pid: i32) -> R<u64> {
    let s = std::str::from_utf8(raw).map_err(|e| e.to_string())?;
    need(
        s.split_once(' ').map(|p| p.0) == Some(&pid.to_string()),
        "original held process PID",
    )?;
    s.rsplit_once(") ")
        .ok_or("process stat shape")?
        .1
        .split_ascii_whitespace()
        .nth(19)
        .ok_or("process start field")?
        .parse()
        .map_err(|_| "process start value".into())
}
fn label(f: &File, opath: bool) -> R<Vec<u8>> {
    let mut out = [0_u8; 512];
    let alias = CString::new(format!("/proc/self/fd/{}", f.as_raw_fd())).unwrap();
    let n = unsafe {
        if opath {
            libc::getxattr(
                alias.as_ptr(),
                c"security.selinux".as_ptr(),
                out.as_mut_ptr().cast(),
                out.len(),
            )
        } else {
            libc::fgetxattr(
                f.as_raw_fd(),
                c"security.selinux".as_ptr(),
                out.as_mut_ptr().cast(),
                out.len(),
            )
        }
    };
    if n < 0 {
        return Err(format!(
            "actual held inode security.selinux: {}",
            std::io::Error::last_os_error()
        ));
    }
    need(
        n > 0 && n as usize <= out.len(),
        "complete actual inode context",
    )?;
    Ok(out[..n as usize].to_vec())
}
fn initial_namespaces() -> R<Vec<File>> {
    let mut result = Vec::new();
    for (path, kind, expected) in [
        ("/proc/self/ns/user", libc::CLONE_NEWUSER, 3_u64),
        ("/proc/self/ns/pid", libc::CLONE_NEWPID, 4_u64),
    ] {
        let file = io(File::open(path))?;
        let mut id = 0_u64;
        let before = node(&file)?;
        let context = label(&file, false)?;
        let expected_context = b"u:object_r:droidloom_nsfs:s0";
        need(
            context == expected_context
                || context.strip_suffix(b"\0") == Some(expected_context.as_slice()),
            "actual fixed nsfs inode label",
        )?;
        need(
            unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) } == kind,
            "actual initial namespace type",
        )?;
        check(
            unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_ID, &mut id as *mut u64) },
            "actual namespace ID",
        )?;
        need(id == expected, "original initial user/PID namespace")?;
        let mut denials = Vec::new();
        for command in [0xb701 as libc::c_ulong, 0xb702, 0xb704, 0xb603] {
            let mut owner_uid = 0_u32;
            let value =
                unsafe { libc::ioctl(file.as_raw_fd(), command, &mut owner_uid as *mut u32) };
            let error = std::io::Error::last_os_error().raw_os_error();
            // The first two commands would return a newly held FD if a bad
            // policy allowed them. Close only that actual return value, fail,
            // and keep every original namespace/generation check unchanged.
            if value >= 0 && (command == 0xb701 || command == 0xb702) {
                drop(unsafe { File::from_raw_fd(value) });
            }
            need(
                value == -1 && error == Some(libc::EACCES),
                "adjacent namespace ioctl requires exact policy EACCES",
            )?;
            denials.push(json!({"command":command,"return":value,"errno":error}));
        }
        need(
            node(&file)? == before && label(&file, false)? == context,
            "same actual namespace inode after positive and negative ioctls",
        )?;
        emit(
            "P4_NSFS_FIXED_QUERY",
            json!({"path":path,"context":String::from_utf8_lossy(&context),
            "inode":before,"actual_type":kind,"actual_id":id,"denied":denials,"production_ready":false}),
        );
        result.push(file);
    }
    Ok(result)
}
fn original_file() -> R<File> {
    let f = io(OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(SYSTEMD))?;
    let m = io(f.metadata())?;
    need(
        m.is_file()
            && m.uid() == 0
            && m.gid() == 0
            && m.nlink() == 1
            && m.mode() & 0o7777 == 0o555
            && m.len() == SYSTEMD_BYTES as u64,
        "fixed sealed original systemd inode",
    )?;
    let before = node(&f)?;
    let mut b = Vec::new();
    io((&f).take(SYSTEMD_BYTES as u64 + 1).read_to_end(&mut b))?;
    need(
        b.len() == SYSTEMD_BYTES && digest(&b) == SYSTEMD_SHA && node(&f)? == before,
        "whole original systemd ELF identity",
    )?;
    Ok(f)
}
fn loaded() -> R<Value> {
    let lsms = text("/sys/kernel/security/lsm", 4096)?;
    let names: Vec<_> = lsms.trim().split(',').collect();
    let se = names
        .iter()
        .position(|x| *x == "selinux")
        .ok_or("actual SELinux inactive")?;
    let aa = names
        .iter()
        .position(|x| *x == "apparmor")
        .ok_or("actual AppArmor inactive")?;
    need(
        se < aa
            && names.iter().filter(|x| **x == "selinux").count() == 1
            && names.iter().filter(|x| **x == "apparmor").count() == 1,
        "actual SELinux-before-AppArmor for default proc attr",
    )?;
    let before = epoch()?;
    let contract: Value =
        serde_json::from_slice(&bounded("/control/fixture-contract.json", 1024 * 1024)?)
            .map_err(|e| e.to_string())?;
    need(
        contract["scope"] == "ISOLATED_COMPONENT_ONLY_NOT_PRODUCTION"
            && expected_cases(&contract)? == 143,
        "same143 component-only contract",
    )?;
    let original = pinned(
        &contract["policy"],
        "/control/component.policy",
        16 * 1024 * 1024,
    )?;
    let expected = pinned(
        &contract["policy_export"],
        "/control/policy-export.bin",
        16 * 1024 * 1024,
    )?;
    let actual = bounded("/sys/fs/selinux/policy", 16 * 1024 * 1024)?;
    need(
        actual == expected && epoch()? == before,
        "same actual complete export and enforcing epoch",
    )?;
    need(
        text("/sys/fs/selinux/policy_capabilities/netlink_xperm", 16)?.trim() == "1",
        "actual netlink_xperm",
    )?;
    let own = bounded("/proc/self/attr/current", 512)?;
    need(
        context_eq(&own, HOST),
        "actual host SID for original systemd bootstrap/observer",
    )?;
    let aa = bounded("/proc/self/attr/apparmor/current", 512)?;
    need(
        aa == b"unconfined\n",
        "original manager host AA label; loaded fixture profiles stay separate",
    )?;
    Ok(
        json!({"epoch":before,"LSM":lsms.trim(),"input_bytes":original.len(),"input_sha256":digest(&original),
        "export_bytes":actual.len(),"export_sha256":digest(&actual),"selinux":String::from_utf8_lossy(&own),
        "apparmor":String::from_utf8_lossy(&aa),"netlink_xperm":1}),
    )
}
fn inputs() -> R<Value> {
    let manifest: Value = serde_json::from_slice(include_bytes!("../systemd-inputs.json"))
        .map_err(|e| e.to_string())?;
    need(
        manifest["schema"] == "p4-original-systemd-disposable-inputs-v1"
            && manifest["scope"] == "ISOLATED_COMPONENT_ONLY_NOT_PRODUCTION",
        "fixed cold input manifest",
    )?;
    let members = manifest["members"].as_object().ok_or("fixed members")?;
    need(members.len() == 45, "exact28 ELF plus17 original aliases")?;
    let mut files = 0;
    let mut aliases = 0;
    for (relative, expected) in members {
        need(
            !relative.starts_with('/')
                && relative
                    .split('/')
                    .all(|p| !p.is_empty() && p != "." && p != ".."),
            "fixed guest member path",
        )?;
        let path = format!("/{relative}");
        let m = io(fs::symlink_metadata(&path))?;
        need(
            m.uid() == 0
                && m.gid() == 0
                && m.nlink() == 1
                && Some((m.mode() & 0o7777) as u64) == expected["mode"].as_u64(),
            "root-owned original public member",
        )?;
        if let Some(target) = expected["symlink"].as_str() {
            need(
                m.file_type().is_symlink()
                    && io(fs::read_link(&path))?.as_os_str() == std::ffi::OsStr::new(target),
                "exact original guest alias",
            )?;
            aliases += 1;
        } else {
            need(m.is_file(), "fixed regular public ELF")?;
            let raw = bounded(&path, 8 * 1024 * 1024)?;
            need(
                Some(raw.len() as u64) == expected["bytes"].as_u64()
                    && expected["sha256"].as_str() == Some(&digest(&raw)),
                "complete original public ELF hash",
            )?;
            files += 1;
        }
    }
    need(
        files == 28 && aliases == 17,
        "full actual selected public input closure",
    )?;
    Ok(
        json!({"ELFs":files,"original_aliases":aliases,"archive_sha256":manifest["archive_sha256"],
        "input_manifest_sha256":digest(include_bytes!("../systemd-inputs.json")),"complete_dlopen_closure":false}),
    )
}
pub(super) fn handoff(mac: &Value, api: &systemd_api::PreparedApiMounts) -> R<()> {
    auth(true)?;
    let namespaces = initial_namespaces()?;
    let actual_inputs = at("original systemd public inputs", inputs())?;
    let policy = at("original systemd pre-exec policy", loaded())?;
    let api_mounts = api.revalidate()?;
    need(
        mac["passed"] == true && mac["epoch_after"] == policy["epoch"],
        "original MAC suite and same epoch before actual PID1 handoff",
    )?;
    let file = original_file()?;
    let held = node(&file)?;
    let context = label(&file, false)?;
    let birth = start(&bounded("/proc/1/stat", 8192)?, 1)?;
    emit(
        "P4_SYSTEMD_BEFORE_EXEC",
        json!({"original_PID1":1,"start_ticks":birth,"original_ELF_bytes":SYSTEMD_BYTES,
        "original_ELF_sha256":SYSTEMD_SHA,"held_ELF_node":held,"actual_ELF_context":String::from_utf8_lossy(&context),
        "policy":policy,"api_mounts":api_mounts,"inputs":actual_inputs,"actual_initial_namespaces":namespaces.iter().map(node).collect::<R<Vec<_>>>()?,
        "natural_NNP":0,"production_ready":false,"Android_starts":0}),
    );
    need(
        api.revalidate()? == api_mounts,
        "same held API mounts immediately before original handoff",
    )?;
    check(
        unsafe { libc::tcdrain(libc::STDOUT_FILENO) },
        "handoff component channel drained",
    )?;
    let saved_serial = unsafe { libc::fcntl(libc::STDOUT_FILENO, libc::F_DUPFD_CLOEXEC, 3) };
    need(
        saved_serial >= 3,
        "held original component channel for exec error",
    )?;
    let saved_serial = unsafe { File::from_raw_fd(saved_serial) };
    let console = io(OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NOCTTY)
        .open("/dev/console"))?;
    let m = io(console.metadata())?;
    need(
        m.file_type().is_char_device() && libc::major(m.rdev()) == 5 && libc::minor(m.rdev()) == 1,
        "fixed guest console",
    )?;
    for descriptor in [libc::STDIN_FILENO, libc::STDOUT_FILENO, libc::STDERR_FILENO] {
        need(
            unsafe { libc::dup2(console.as_raw_fd(), descriptor) } == descriptor,
            "fixed original manager console",
        )?;
    }
    need(
        node(&file)? == held
            && label(&file, false)? == context
            && epoch()?
                == serde_json::from_value::<[u32; 5]>(policy["epoch"].clone())
                    .map_err(|e| e.to_string())?,
        "held original ELF and policy unchanged immediately before exec",
    )?;
    let argv = [
        c"/usr/lib/systemd/systemd".as_ptr(),
        c"--system".as_ptr(),
        c"--unit=p4-systemd-observe.target".as_ptr(),
        c"--log-target=console".as_ptr(),
        c"--log-level=debug".as_ptr(),
        std::ptr::null(),
    ];
    let env = [
        c"PATH=/usr/bin:/usr/sbin".as_ptr(),
        c"LANG=C".as_ptr(),
        c"SYSTEMD_LOG_COLOR=0".as_ptr(),
        c"SYSTEMD_LOG_LOCATION=1".as_ptr(),
        std::ptr::null(),
    ];
    unsafe {
        libc::syscall(
            libc::SYS_execveat,
            file.as_raw_fd(),
            c"".as_ptr(),
            argv.as_ptr(),
            env.as_ptr(),
            libc::AT_EMPTY_PATH,
        );
    }
    let error = std::io::Error::last_os_error();
    need(
        unsafe { libc::dup2(saved_serial.as_raw_fd(), libc::STDOUT_FILENO) } == libc::STDOUT_FILENO,
        "restore held original component error channel",
    )?;
    Err(format!("actual original systemd execveat: {error}"))
}

fn ready(fd: i32, events: i16, until: Instant) -> R<()> {
    loop {
        before(until)?;
        let millis = until
            .saturating_duration_since(Instant::now())
            .as_millis()
            .saturating_add(1);
        need(
            millis <= i32::MAX as u128,
            "bounded original socket deadline",
        )?;
        let mut p = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        let n = unsafe { libc::poll(&mut p, 1, millis as i32) };
        if n < 0 {
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() == Some(libc::EINTR) {
                continue;
            }
            return Err(format!("original socket poll: {error}"));
        }
        before(until)?;
        if n == 0 {
            continue;
        }
        need(
            n == 1
                && p.revents & events != 0
                && p.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) == 0,
            "original connected socket remains usable",
        )?;
        return Ok(());
    }
}
fn send_fixed(f: &File, bytes: &[u8], until: Instant) -> R<()> {
    let mut sent = 0;
    while sent < bytes.len() {
        ready(f.as_raw_fd(), libc::POLLOUT, until)?;
        let n = unsafe {
            libc::send(
                f.as_raw_fd(),
                bytes[sent..].as_ptr().cast(),
                bytes.len() - sent,
                libc::MSG_NOSIGNAL,
            )
        };
        if n < 0 {
            let e = std::io::Error::last_os_error();
            if matches!(e.raw_os_error(), Some(libc::EAGAIN) | Some(libc::EINTR)) {
                continue;
            }
            return Err(format!("fixed original manager auth write: {e}"));
        }
        need(
            n > 0 && n as usize <= bytes.len() - sent,
            "actual fixed authentication write",
        )?;
        sent += n as usize;
    }
    before(until)
}
fn line(f: &File, until: Instant) -> R<Vec<u8>> {
    let mut bytes = Vec::new();
    while bytes.len() < 128 {
        ready(f.as_raw_fd(), libc::POLLIN, until)?;
        let mut b = 0_u8;
        let n = unsafe { libc::recv(f.as_raw_fd(), (&mut b as *mut u8).cast(), 1, 0) };
        if n < 0 {
            let e = std::io::Error::last_os_error();
            if matches!(e.raw_os_error(), Some(libc::EAGAIN) | Some(libc::EINTR)) {
                continue;
            }
            return Err(format!("fixed original manager auth read: {e}"));
        }
        need(n == 1 && b != 0, "one actual auth response byte")?;
        bytes.push(b);
        if bytes.ends_with(b"\r\n") {
            before(until)?;
            return Ok(bytes);
        }
    }
    Err("manager authentication line exceeds128 bytes".into())
}
fn connect(directory: &File, until: Instant) -> R<File> {
    let path = format!("/proc/self/fd/{}/private", directory.as_raw_fd());
    let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    need(
        path.len() < address.sun_path.len(),
        "fixed held-directory Unix alias",
    )?;
    address.sun_family = libc::AF_UNIX as libc::sa_family_t;
    for (out, value) in address.sun_path.iter_mut().zip(path.bytes()) {
        *out = value as libc::c_char;
    }
    before(until)?;
    let fd = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    };
    if fd < 0 {
        return Err(format!(
            "actual private socket create: {}",
            std::io::Error::last_os_error()
        ));
    }
    let f = unsafe { File::from_raw_fd(fd) };
    let length = (std::mem::size_of::<libc::sa_family_t>() + path.len() + 1) as libc::socklen_t;
    if unsafe { libc::connect(fd, (&address as *const libc::sockaddr_un).cast(), length) } != 0 {
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() != Some(libc::EINPROGRESS) {
            return Err(format!("actual original manager connect: {e}"));
        }
        ready(fd, libc::POLLOUT, until)?;
        let mut error = -1_i32;
        let mut bytes = std::mem::size_of::<i32>() as libc::socklen_t;
        check(
            unsafe {
                libc::getsockopt(
                    fd,
                    libc::SOL_SOCKET,
                    libc::SO_ERROR,
                    (&mut error as *mut i32).cast(),
                    &mut bytes,
                )
            },
            "actual private connect status",
        )?;
        need(
            bytes as usize == std::mem::size_of::<i32>() && error == 0,
            "actual connected private manager socket",
        )?;
    }
    before(until)?;
    Ok(f)
}
fn peer(f: &File) -> R<(libc::ucred, Vec<u8>)> {
    let mut cred: libc::ucred = unsafe { std::mem::zeroed() };
    let mut size = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    check(
        unsafe {
            libc::getsockopt(
                f.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                (&mut cred as *mut libc::ucred).cast(),
                &mut size,
            )
        },
        "actual manager SO_PEERCRED",
    )?;
    need(
        size as usize == std::mem::size_of::<libc::ucred>()
            && cred.pid == 1
            && cred.uid == 0
            && cred.gid == 0,
        "same connection actual root PID1 peer",
    )?;
    let mut context = [0_u8; 512];
    let mut bytes = context.len() as libc::socklen_t;
    check(
        unsafe {
            libc::getsockopt(
                f.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERSEC,
                context.as_mut_ptr().cast(),
                &mut bytes,
            )
        },
        "actual manager SO_PEERSEC",
    )?;
    need(
        bytes > 0
            && bytes as usize <= context.len()
            && context_eq(&context[..bytes as usize], HOST),
        "same connection actual original manager host SID",
    )?;
    Ok((cred, context[..bytes as usize].to_vec()))
}
fn live(pidfd: &File) -> R<()> {
    let mut p = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let n = unsafe { libc::poll(&mut p, 1, 0) };
    need(
        n == 0 && p.revents == 0,
        "held original manager PIDFD still live",
    )?;
    let fdinfo = text(&format!("/proc/self/fdinfo/{}", pidfd.as_raw_fd()), 4096)?;
    for key in ["Pid:", "NSpid:"] {
        let lines: Vec<_> = fdinfo.lines().filter_map(|l| l.strip_prefix(key)).collect();
        need(
            lines.len() == 1 && lines[0].split_ascii_whitespace().collect::<Vec<_>>() == ["1"],
            "kernel peer PIDFD binds initial PID1",
        )?;
    }
    Ok(())
}
fn server_metadata(server_node: &[u64; 9]) -> Value {
    // Observation only: retain the actual mode even when the next gate refuses it.
    json!({"node":server_node,"expected_mode":0o700,
        "peer_authenticated":false,"label_mutations":0})
}
fn validate_original_server_node(server_node: &[u64; 9]) -> R<()> {
    // systemd 259.9 bus_init_private binds under WITH_UMASK(0077); the fixed
    // Linux AF_UNIX implementation creates S_IFSOCK | (0777 & ~umask).
    // R9 did not emit its actual mode. This is the source-derived expectation,
    // not a retrospective claim about that failed guest or permission repair.
    need(
        server_node[2] == (libc::S_IFSOCK as u64 | 0o700)
            && server_node[3] == 0
            && server_node[4] == 0
            && server_node[5] == 1,
        "actual root0700 original server sock_file",
    )
}
fn observe_inner() -> R<Value> {
    let until = Instant::now() + Duration::from_secs(7);
    let before_policy = loaded()?;
    let namespaces = initial_namespaces()?;
    let api_mounts = systemd_api::observe()?;
    let expected = original_file()?;
    let expected_node = node(&expected)?;
    let mut directories = vec![io(OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/"))?];
    for name in [c"run", c"systemd"] {
        let f = open_at(
            directories.last().unwrap(),
            name,
            libc::O_RDONLY | libc::O_DIRECTORY,
            false,
        )?;
        directories.push(f);
    }
    let mut directory_nodes = Vec::new();
    for f in &directories {
        let m = io(f.metadata())?;
        need(
            m.is_dir() && m.uid() == 0 && m.gid() == 0 && m.mode() & 0o022 == 0,
            "actual root-controlled manager parent directory",
        )?;
        directory_nodes.push(node(f)?);
    }
    let server = open_at(directories.last().unwrap(), c"private", libc::O_PATH, false)?;
    let server_node = node(&server)?;
    emit("P4_SYSTEMD_SERVER_METADATA", server_metadata(&server_node));
    validate_original_server_node(&server_node)?;
    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };
    check(
        unsafe { libc::fstatfs(server.as_raw_fd(), &mut fs) },
        "actual server filesystem",
    )?;
    need(
        fs.f_type == 0x01021994,
        "original manager server inode on actual tmpfs",
    )?;
    let server_label = label(&server, true)?;
    emit(
        "P4_SYSTEMD_SERVER_INODE",
        json!({"node":server_node,"actual_security_selinux":String::from_utf8_lossy(&server_label),
        "filesystem_magic":fs.f_type,"peer_authenticated":false,"label_mutations":0}),
    );
    let connection = connect(directories.last().unwrap(), until)?;
    let (credentials, peer_context) = peer(&connection)?;
    let mut descriptor = -1_i32;
    let mut size = std::mem::size_of::<i32>() as libc::socklen_t;
    check(
        unsafe {
            libc::getsockopt(
                connection.as_raw_fd(),
                libc::SOL_SOCKET,
                SO_PEERPIDFD,
                (&mut descriptor as *mut i32).cast(),
                &mut size,
            )
        },
        "actual same-connection SO_PEERPIDFD",
    )?;
    need(descriptor >= 0, "kernel manager PIDFD returned")?;
    let pidfd = unsafe { File::from_raw_fd(descriptor) };
    need(
        size as usize == std::mem::size_of::<i32>()
            && unsafe { libc::fcntl(descriptor, libc::F_GETFD) } & libc::FD_CLOEXEC != 0,
        "peer PIDFD exact width and CLOEXEC",
    )?;
    live(&pidfd)?;
    let proc = io(OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/proc/1"))?;
    let proc_node = node(&proc)?;
    let birth = start(&read_proc(&proc, c"stat")?, 1)?;
    let exe = open_at(&proc, c"exe", libc::O_RDONLY, true)?;
    need(
        node(&exe)? == expected_node,
        "actual held PID1 executable is original systemd inode",
    )?;
    let mut executable = Vec::new();
    io((&exe)
        .take(SYSTEMD_BYTES as u64 + 1)
        .read_to_end(&mut executable))?;
    need(
        executable.len() == SYSTEMD_BYTES && digest(&executable) == SYSTEMD_SHA,
        "whole actual held PID1 ELF",
    )?;
    for (name, original) in [c"ns/user", c"ns/pid"].iter().zip(&namespaces) {
        let current = open_at(&proc, name, libc::O_RDONLY, true)?;
        need(
            node(&current)? == node(original)?,
            "actual PID1 shares original initial namespaces",
        )?;
    }
    let context = read_proc(&proc, c"attr/current")?;
    let aa = read_proc(&proc, c"attr/apparmor/current")?;
    need(
        context_eq(&context, HOST) && context_eq(&peer_context, HOST) && aa == b"unconfined\n",
        "held original PID1 LSM values agree with same private connection",
    )?;
    let status = String::from_utf8(read_proc(&proc, c"status")?).map_err(|e| e.to_string())?;
    for key in ["Uid:", "Gid:"] {
        let rows: Vec<_> = status.lines().filter_map(|l| l.strip_prefix(key)).collect();
        need(
            rows.len() == 1
                && rows[0].split_ascii_whitespace().collect::<Vec<_>>() == ["0", "0", "0", "0"],
            "actual original manager credentials",
        )?;
    }
    send_fixed(&connection, b"\0AUTH EXTERNAL 30\r\n", until)?;
    let auth_reply = line(&connection, until)?;
    need(
        auth_reply.len() == 37
            && auth_reply.starts_with(b"OK ")
            && auth_reply.ends_with(b"\r\n")
            && auth_reply[3..35].iter().all(u8::is_ascii_hexdigit),
        "actual private EXTERNAL-root authentication and complete GUID",
    )?;
    send_fixed(&connection, b"NEGOTIATE_UNIX_FD\r\n", until)?;
    need(
        line(&connection, until)? == b"AGREE_UNIX_FD\r\n",
        "same authenticated connection supports real UNIX_FD",
    )?;
    send_fixed(&connection, b"BEGIN\r\n", until)?;
    let cgroup = read_proc(&proc, c"cgroup")?;
    let own_cgroup = bounded("/proc/self/cgroup", 8192)?;
    let after_policy = loaded()?;
    need(
        systemd_api::observe()? == api_mounts,
        "same API mount generations throughout real manager observation",
    )?;
    need(
        before_policy == after_policy,
        "unchanged complete loaded policy throughout original manager observation",
    )?;
    live(&pidfd)?;
    need(
        node(&proc)? == proc_node && start(&read_proc(&proc, c"stat")?, 1)? == birth,
        "same original held PID1 generation",
    )?;
    need(
        node(&exe)? == expected_node
            && node(&open_at(&proc, c"exe", libc::O_RDONLY, true)?)? == expected_node,
        "same held original PID1 executable after authentication",
    )?;
    need(
        read_proc(&proc, c"attr/current")? == context
            && read_proc(&proc, c"attr/apparmor/current")? == aa
            && peer(&connection)?.1 == peer_context,
        "same actual manager MAC on original connection",
    )?;
    for (f, expected) in directories.iter().zip(&directory_nodes) {
        need(
            node(f)? == *expected,
            "held manager directory identity unchanged",
        )?;
    }
    for (i, name) in [c"run", c"systemd"].iter().enumerate() {
        need(
            node(&open_at(
                &directories[i],
                name,
                libc::O_RDONLY | libc::O_DIRECTORY,
                false,
            )?)? == directory_nodes[i + 1],
            "same manager parent name and inode",
        )?;
    }
    need(
        node(&server)? == server_node
            && node(&open_at(
                directories.last().unwrap(),
                c"private",
                libc::O_PATH,
                false,
            )?)? == server_node
            && label(&server, true)? == server_label,
        "original service-side inode and actual label unchanged",
    )?;
    before(until)?;
    Ok(
        json!({"actual_original_systemd_PID1":true,"actual_original_ELF_bytes":executable.len(),"actual_original_ELF_sha256":digest(&executable),
        "original_PID1_start_ticks":birth,"held_proc_node":proc_node,"held_exe_node":expected_node,
        "same_connection_SO_PEERCRED":[credentials.pid as i64,credentials.uid as i64,credentials.gid as i64],
        "same_connection_SO_PEERPIDFD_live":true,"same_connection_SO_PEERSEC":String::from_utf8_lossy(&peer_context),
        "actual_manager_SELinux":String::from_utf8_lossy(&context),"actual_manager_AppArmor":String::from_utf8_lossy(&aa),
        "actual_server_node":server_node,"actual_server_security_selinux":String::from_utf8_lossy(&server_label),
        "actual_manager_cgroup":String::from_utf8_lossy(&cgroup),"actual_observer_cgroup":String::from_utf8_lossy(&own_cgroup),
        "actual_authentication":String::from_utf8_lossy(&auth_reply),"UNIX_FD_negotiated":true,"policy":after_policy,"api_mounts":api_mounts,
        "effective_production_unit_qualified":false,"daemon_death_qualified":false,"label_mutations":0,"passed":true}),
    )
}
pub(super) fn observe() -> R<()> {
    // Rejection runs before opening the component channel or the private socket.
    auth(false)?;
    need(
        unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } == 1,
        "actual original manager applied observer NNP1",
    )?;
    component_channel()?;
    emit(
        "P4_SYSTEMD_OBSERVER_STARTED",
        json!({"PID":unsafe { libc::getpid() },"PPID":unsafe { libc::getppid() },
        "NNP":unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS,0,0,0,0) },"scope":"ISOLATED_COMPONENT_ONLY_NOT_PRODUCTION"}),
    );
    let (detail, error) = match observe_inner() {
        Ok(v) => (v, None),
        Err(e) => (Value::Null, Some(e)),
    };
    emit(
        "P4_SYSTEMD_GUEST_FINAL",
        json!({"passed":error.is_none(),"detail":detail,"error":error,
        "production_ready":false,"runtime_qualified":false,"Android_starts":0,"host_policy_loads":0,
        "actual_original_Android_ELF_execs":0,"label_mutations":0,"host_survival_qualified":false}),
    );
    check(
        unsafe { libc::tcdrain(libc::STDOUT_FILENO) },
        "original systemd diagnostic output drained",
    )?;
    unsafe {
        libc::sync();
        libc::reboot(libc::RB_POWER_OFF);
    }
    Err(format!(
        "disposable guest poweroff returned: {}",
        std::io::Error::last_os_error()
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    // These are metadata-only controls. They do not authenticate a live manager
    // or construct a cold-boot, namespace, policy, or production witness.
    fn socket_node() -> [u64; 9] {
        [5, 23, libc::S_IFSOCK as u64 | 0o700, 0, 0, 1, 0, 100, 100]
    }

    #[test]
    fn original_server_requires_exact_source_derived_private_mode() {
        let original = socket_node();
        assert!(validate_original_server_node(&original).is_ok());
        for mode in [
            0o600, 0o000, 0o500, 0o710, 0o701, 0o770, 0o777, 0o4700, 0o2700, 0o1700,
        ] {
            let mut changed = original;
            changed[2] = libc::S_IFSOCK as u64 | mode;
            assert!(validate_original_server_node(&changed).is_err());
        }
    }

    #[test]
    fn original_server_rejects_wrong_owner_kind_or_link_count() {
        for (index, value) in [(3, 1000), (4, 1000), (5, 0), (5, 2)] {
            let mut changed = socket_node();
            changed[index] = value;
            assert!(validate_original_server_node(&changed).is_err());
        }
        for kind in [libc::S_IFREG, libc::S_IFDIR, libc::S_IFLNK, libc::S_IFIFO] {
            let mut changed = socket_node();
            changed[2] = kind as u64 | 0o700;
            assert!(validate_original_server_node(&changed).is_err());
        }
    }

    #[test]
    fn refused_server_metadata_retains_actual_node_without_authentication() {
        let mut actual = socket_node();
        actual[2] = libc::S_IFSOCK as u64 | 0o777;
        actual[3] = 1000;
        let observation = server_metadata(&actual);
        assert_eq!(observation["node"], json!(actual));
        assert_eq!(observation["expected_mode"], json!(0o700));
        assert_eq!(observation["peer_authenticated"], json!(false));
        assert_eq!(observation["label_mutations"], json!(0));
        assert_eq!(observation.as_object().unwrap().len(), 4);
        assert!(observation.to_string().len() < 512);
        assert!(validate_original_server_node(&actual).is_err());
    }
}
