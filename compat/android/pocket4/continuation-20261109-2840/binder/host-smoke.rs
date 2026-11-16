// SPDX-License-Identifier: Apache-2.0
// Host-only Binder kernel regression probe. This is not Android acceptance.
// Linux Binder UAPI layout is taken from linux/android/{binder,binderfs}.h.
// The earlier VM-only binder_cred_probe.c is reference evidence and is never run.
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::mem::{size_of, zeroed};
use std::os::fd::AsRawFd;
use std::os::raw::{c_char, c_int, c_ulong, c_void};
use std::os::unix::fs::{DirBuilderExt, FileTypeExt, MetadataExt, OpenOptionsExt};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Child, Command, ExitCode, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const ROOT: &str = "/home/alex/work/pocket4-binder-host-smoke-20261109-2840-r1";
const UNIT: &str = "p4-binder-host-smoke-20261109-2840-r1.service";
const KERNEL: &str = "7.0.14-p4cred1";
const MAP_BYTES: usize = 1024 * 1024;
const TEST_CODE: u32 = 0x54584e31;
const REQUEST_MAGIC: u64 = 0x503442494e445231;
const REPLY_MAGIC: u64 = 0x503442494e445232;
const REPLY_XOR: u64 = 0xa67b39025de841c0;
const O_NONBLOCK: i32 = 0x800;
const O_NOFOLLOW: i32 = 0x20000;
const EINTR: i32 = 4;
const EAGAIN: i32 = 11;
const ECHILD: i32 = 10;
const ESRCH: i32 = 3;
const SIGKILL: i32 = 9;
const PR_SET_PDEATHSIG: i32 = 1;
const PR_SET_CHILD_SUBREAPER: i32 = 36;
const CLONE_NEWNS: i32 = 0x20000;
const MS_REC: c_ulong = 16384;
const MS_PRIVATE: c_ulong = 1 << 18;
const MS_NOSUID: c_ulong = 2;
const MS_NOEXEC: c_ulong = 8;

unsafe extern "C" {
    fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
    fn mmap(addr: *mut c_void, len: usize, prot: c_int, flags: c_int, fd: c_int, offset: i64) -> *mut c_void;
    fn munmap(addr: *mut c_void, len: usize) -> c_int;
    fn unshare(flags: c_int) -> c_int;
    fn mount(source: *const c_char, target: *const c_char, fstype: *const c_char, flags: c_ulong, data: *const c_void) -> c_int;
    fn umount2(target: *const c_char, flags: c_int) -> c_int;
    fn prctl(option: c_int, ...) -> c_int;
    fn geteuid() -> u32;
    fn getuid() -> u32;
    fn getpid() -> i32;
    fn getppid() -> i32;
    fn kill(pid: i32, signal: i32) -> i32;
    fn waitpid(pid: i32, status: *mut i32, options: i32) -> i32;
}

type R<T> = Result<T, String>;
fn need(value: bool, message: &str) -> R<()> { if value { Ok(()) } else { Err(message.into()) } }
fn errno(stage: &str) -> String { format!("{stage}: {}", io::Error::last_os_error()) }
fn read(path: impl AsRef<Path>) -> R<String> { fs::read_to_string(path).map_err(|e| e.to_string()) }
fn label() -> R<String> {
    let value = read("/proc/self/attr/current")?.trim_end_matches(['\n', '\r']).to_string();
    need(!value.is_empty() && value.len() < 256 && !value.as_bytes().contains(&0), "unusable actual security label")?;
    Ok(value)
}
fn ns() -> R<String> { fs::read_link("/proc/self/ns/mnt").map(|p| p.to_string_lossy().into_owned()).map_err(|e| e.to_string()) }
fn quoted(value: &str) -> String {
    let mut out = String::from("\"");
    for c in value.chars() {
        match c { '"' => out.push_str("\\\""), '\\' => out.push_str("\\\\"), '\n' => out.push_str("\\n"), '\r' => out.push_str("\\r"), '\t' => out.push_str("\\t"), c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)), c => out.push(c) }
    }
    out.push('"'); out
}
fn cstring(value: &str) -> R<CString> { CString::new(value).map_err(|e| e.to_string()) }
fn fresh_dir(path: &Path) -> R<()> { fs::DirBuilder::new().mode(0o700).create(path).map_err(|e| format!("create {}: {e}", path.display())) }
fn own_mounts() -> R<Vec<String>> { Ok(read("/proc/self/mountinfo")?.lines().filter(|line| line.split_whitespace().nth(4).is_some_and(|p| p.starts_with(ROOT))).map(str::to_owned).collect()) }

const fn ioc(direction: u32, kind: u8, number: u8, size: usize) -> u32 { (direction << 30) | ((size as u32) << 16) | ((kind as u32) << 8) | number as u32 }
#[repr(C)] #[derive(Clone, Copy, Default)]
struct Transaction { target: u64, cookie: u64, code: u32, flags: u32, sender_pid: i32, sender_euid: u32, data_size: u64, offsets_size: u64, buffer: u64, offsets: u64 }
#[repr(C)] #[derive(Clone, Copy, Default)]
struct TransactionSecctx { transaction: Transaction, secctx: u64 }
#[repr(C)] #[derive(Clone, Copy, Default)]
struct FlatObject { kind: u32, flags: u32, binder: u64, cookie: u64 }
#[repr(C)] #[derive(Default)]
struct WriteRead { write_size: u64, write_consumed: u64, write_buffer: u64, read_size: u64, read_consumed: u64, read_buffer: u64 }
#[repr(C)] struct Device { name: [u8; 256], major: u32, minor: u32 }
#[repr(C)] #[derive(Default)] struct ExtendedError { id: u32, command: u32, param: i32 }
const BWR: u32 = ioc(3, b'b', 1, size_of::<WriteRead>());
const SET_CONTEXT: u32 = ioc(1, b'b', 13, size_of::<FlatObject>());
const VERSION: u32 = ioc(3, b'b', 9, 4);
const ADD_DEVICE: u32 = ioc(3, b'b', 1, size_of::<Device>());
const EXTENDED_ERROR: u32 = ioc(3, b'b', 17, size_of::<ExtendedError>());
const BC_TRANSACTION: u32 = ioc(1, b'c', 0, size_of::<Transaction>());
const BC_REPLY: u32 = ioc(1, b'c', 1, size_of::<Transaction>());
const BC_FREE_BUFFER: u32 = ioc(1, b'c', 3, 8);
const BC_ENTER_LOOPER: u32 = ioc(0, b'c', 12, 0);
const BR_TRANSACTION: u32 = ioc(2, b'r', 2, size_of::<Transaction>());
const BR_TRANSACTION_SECCTX: u32 = ioc(2, b'r', 2, size_of::<TransactionSecctx>());
const BR_REPLY: u32 = ioc(2, b'r', 3, size_of::<Transaction>());
const BR_COMPLETE: u32 = ioc(0, b'r', 6, 0);
const BR_NOOP: u32 = ioc(0, b'r', 12, 0);
const BR_FAILED_REPLY: u32 = ioc(0, b'r', 17, 0);

fn abi() -> R<()> {
    need(cfg!(target_arch = "x86_64") && size_of::<usize>() == 8, "x86_64 Binder ABI required")?;
    need(size_of::<Transaction>() == 64 && size_of::<TransactionSecctx>() == 72 && size_of::<FlatObject>() == 24 && size_of::<WriteRead>() == 48 && size_of::<Device>() == 264 && size_of::<ExtendedError>() == 12, "Binder UAPI layout mismatch")?;
    need(BWR == 0xc0306201 && SET_CONTEXT == 0x4018620d && ADD_DEVICE == 0xc1086201 && BR_TRANSACTION_SECCTX == 0x80487202, "Binder UAPI ioctl mismatch")
}

struct Binder { file: File, mapping: *mut c_void }
impl Binder {
    fn open(path: &Path) -> R<Self> {
        need(fs::symlink_metadata(path).map_err(|e| e.to_string())?.file_type().is_char_device(), "own Binder path must be a character device")?;
        let file = OpenOptions::new().read(true).write(true).custom_flags(O_NONBLOCK | O_NOFOLLOW).open(path).map_err(|e| e.to_string())?;
        let mut version: i32 = 0;
        if unsafe { ioctl(file.as_raw_fd(), VERSION as c_ulong, &mut version) } < 0 { return Err(errno("BINDER_VERSION")); }
        need(version == 8, "unexpected Binder protocol version")?;
        let mapping = unsafe { mmap(std::ptr::null_mut(), MAP_BYTES, 1, 2, file.as_raw_fd(), 0) };
        if mapping as isize == -1 { return Err(errno("Binder mmap")); }
        Ok(Self { file, mapping })
    }
    fn exchange(&self, write: &[u8], read: &mut [u8]) -> io::Result<usize> {
        let mut wr = WriteRead { write_size: write.len() as u64, write_buffer: if write.is_empty() { 0 } else { write.as_ptr() as u64 }, read_size: read.len() as u64, read_buffer: if read.is_empty() { 0 } else { read.as_mut_ptr() as u64 }, ..Default::default() };
        loop {
            if unsafe { ioctl(self.file.as_raw_fd(), BWR as c_ulong, &mut wr) } >= 0 { break; }
            let e = io::Error::last_os_error();
            if e.raw_os_error() != Some(EINTR) { return Err(e); }
        }
        if wr.write_consumed != write.len() as u64 || wr.read_consumed > read.len() as u64 { return Err(io::Error::new(io::ErrorKind::InvalidData, "Binder wire consumption mismatch")); }
        Ok(wr.read_consumed as usize)
    }
    fn command<T>(&self, command: u32, data: &T) -> R<()> {
        let mut wire = command.to_ne_bytes().to_vec();
        wire.extend_from_slice(unsafe { std::slice::from_raw_parts(data as *const T as *const u8, size_of::<T>()) });
        self.exchange(&wire, &mut []).map(|_| ()).map_err(|e| format!("Binder write command 0x{command:08x}: {e}"))
    }
    fn contains(&self, ptr: u64, bytes: usize) -> bool {
        let begin = self.mapping as usize;
        (ptr as usize).checked_sub(begin).is_some_and(|offset| offset <= MAP_BYTES && bytes <= MAP_BYTES - offset)
    }
    fn payload(&self, tx: &Transaction) -> R<[u64; 2]> {
        need(tx.data_size == 16 && tx.offsets_size == 0 && self.contains(tx.buffer, 16), "invalid Binder transaction payload range")?;
        Ok(unsafe { std::ptr::read_unaligned(tx.buffer as *const [u64; 2]) })
    }
    fn context(&self, ptr: u64) -> R<String> {
        need(self.contains(ptr, 1), "security context outside actual Binder mapping")?;
        let remaining = MAP_BYTES - (ptr as usize - self.mapping as usize);
        let raw = unsafe { std::slice::from_raw_parts(ptr as *const u8, remaining.min(256)) };
        let end = raw.iter().position(|b| *b == 0).ok_or("security context is not bounded and NUL terminated")?;
        need(end > 0, "empty security context")?;
        String::from_utf8(raw[..end].to_vec()).map_err(|e| e.to_string())
    }
    fn failure(&self) -> String {
        let mut error = ExtendedError::default();
        if unsafe { ioctl(self.file.as_raw_fd(), EXTENDED_ERROR as c_ulong, &mut error) } < 0 { errno("BR_FAILED_REPLY/get extended error") }
        else { format!("BR_FAILED_REPLY: extended_error={} command=0x{:08x} id={}", error.param, error.command, error.id) }
    }
}
impl Drop for Binder { fn drop(&mut self) { unsafe { munmap(self.mapping, MAP_BYTES); } } }

fn frames(buffer: &[u8]) -> R<Vec<(u32, &[u8])>> {
    let mut frames = Vec::new(); let mut offset = 0;
    while offset < buffer.len() {
        need(buffer.len() - offset >= 4, "truncated Binder command")?;
        let command = u32::from_ne_bytes(buffer[offset..offset + 4].try_into().unwrap()); offset += 4;
        let bytes = ((command >> 16) & 0x3fff) as usize;
        need(bytes <= buffer.len() - offset, "truncated Binder command payload")?;
        frames.push((command, &buffer[offset..offset + bytes])); offset += bytes;
    }
    Ok(frames)
}
fn decode<T: Copy>(data: &[u8]) -> R<T> { need(data.len() == size_of::<T>(), "Binder command layout length mismatch")?; Ok(unsafe { std::ptr::read_unaligned(data.as_ptr() as *const T) }) }

fn child_command(args: &[String]) -> R<Child> {
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    let parent = unsafe { getpid() };
    let mut cmd = Command::new(executable);
    cmd.args(args).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    unsafe { cmd.pre_exec(move || {
        if prctl(PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) != 0 { return Err(io::Error::last_os_error()); }
        if getppid() != parent { return Err(io::Error::new(io::ErrorKind::Interrupted, "parent retired during launch")); }
        Ok(())
    }); }
    cmd.spawn().map_err(|e| e.to_string())
}
struct OwnedChild { child: Child, reaped: bool }
impl OwnedChild {
    fn new(child: Child) -> Self { Self { child, reaped: false } }
    fn retire(&mut self) -> R<()> {
        if !self.reaped { let _ = self.child.kill(); self.child.wait().map_err(|e| e.to_string())?; self.reaped = true; }
        Ok(())
    }
    fn output(&mut self) -> R<(Vec<u8>, String)> {
        let mut out = Vec::new(); let mut err = String::new();
        if let Some(stream) = self.child.stdout.take() { stream.take(16385).read_to_end(&mut out).map_err(|e| e.to_string())?; }
        if let Some(stream) = self.child.stderr.take() { stream.take(8193).read_to_string(&mut err).map_err(|e| e.to_string())?; }
        need(out.len() <= 16384 && err.len() <= 8192, "child output exceeded bound")?;
        Ok((out, err))
    }
}
impl Drop for OwnedChild { fn drop(&mut self) { let _ = self.retire(); } }

fn client(path: &Path, expected_parent: i32, expected_ns: &str, nonce: u64) -> R<()> {
    need(unsafe { getppid() } == expected_parent && ns()? == expected_ns, "client ownership/namespace mismatch")?;
    need(path.starts_with(ROOT) && matches!(path.file_name().and_then(|p| p.to_str()), Some("plain") | Some("security")), "client device escaped own test root")?;
    let opened_label = label()?; let opened_euid = unsafe { geteuid() };
    let binder = Binder::open(path)?;
    need(label()? == opened_label && unsafe { geteuid() } == opened_euid, "opening credentials changed")?;
    let payload = [REQUEST_MAGIC, nonce];
    let tx = Transaction { code: TEST_CODE, data_size: 16, buffer: payload.as_ptr() as u64, ..Default::default() };
    binder.command(BC_TRANSACTION, &tx)?;
    let deadline = Instant::now() + Duration::from_secs(6); let mut complete = 0;
    while Instant::now() < deadline {
        let mut buffer = [0u8; 4096];
        let count = match binder.exchange(&[], &mut buffer) {
            Ok(n) => n, Err(e) if e.raw_os_error() == Some(EAGAIN) => { std::thread::sleep(Duration::from_millis(5)); continue; }, Err(e) => return Err(format!("client Binder read: {e}")),
        };
        for (command, data) in frames(&buffer[..count])? {
            match command {
                BR_REPLY => {
                    let reply: Transaction = decode(data)?;
                    need(binder.payload(&reply)? == [REPLY_MAGIC, nonce ^ REPLY_XOR] && reply.flags & 8 == 0, "reply content/status does not match request")?;
                    binder.command(BC_FREE_BUFFER, &reply.buffer)?;
                    let mut receipt = b"BNSMOKE1".to_vec();
                    for value in [unsafe { getpid() } as u32, opened_euid, 8, complete, opened_label.len() as u32] { receipt.extend_from_slice(&value.to_ne_bytes()); }
                    receipt.extend_from_slice(opened_label.as_bytes());
                    io::stdout().write_all(&receipt).map_err(|e| e.to_string())?;
                    return Ok(());
                },
                BR_COMPLETE => complete += 1,
                BR_NOOP => {},
                BR_FAILED_REPLY => return Err(binder.failure()),
                other => return Err(format!("unexpected client Binder command 0x{other:08x}")),
            }
        }
    }
    Err("client transaction timed out".into())
}

fn run_case(path: &Path, security: bool, nonce: u64) -> R<String> {
    let binder = Binder::open(path)?;
    let mut object = FlatObject { kind: 0x73622a85, flags: 0x100 | if security { 0x1000 } else { 0 }, ..Default::default() };
    if unsafe { ioctl(binder.file.as_raw_fd(), SET_CONTEXT as c_ulong, &mut object) } < 0 { return Err(errno("BINDER_SET_CONTEXT_MGR_EXT")); }
    binder.exchange(&BC_ENTER_LOOPER.to_ne_bytes(), &mut []).map_err(|e| format!("BC_ENTER_LOOPER: {e}"))?;
    let namespace = ns()?;
    let mut child = OwnedChild::new(child_command(&["--client".into(), path.to_string_lossy().into_owned(), unsafe { getpid() }.to_string(), namespace, nonce.to_string()])?);
    let pid = child.child.id(); let deadline = Instant::now() + Duration::from_secs(8);
    let mut transaction_count = 0; let mut security_label = None; let mut sender_euid = None;
    let status;
    loop {
        if let Some(exit) = child.child.try_wait().map_err(|e| e.to_string())? { child.reaped = true; status = exit; break; }
        if Instant::now() >= deadline { child.retire()?; return Err("server transaction timed out; owned client killed/reaped".into()); }
        let mut buffer = [0u8; 4096];
        let count = match binder.exchange(&[], &mut buffer) {
            Ok(n) => n, Err(e) if e.raw_os_error() == Some(EAGAIN) => { std::thread::sleep(Duration::from_millis(5)); continue; }, Err(e) => return Err(format!("server Binder read: {e}")),
        };
        for (command, data) in frames(&buffer[..count])? {
            if command == BR_TRANSACTION || command == BR_TRANSACTION_SECCTX {
                need((command == BR_TRANSACTION_SECCTX) == security, "security-context delivery mode does not match request")?;
                let tx = if security { let secured: TransactionSecctx = decode(data)?; security_label = Some(binder.context(secured.secctx)?); secured.transaction } else { decode::<Transaction>(data)? };
                transaction_count += 1;
                need(transaction_count == 1 && tx.code == TEST_CODE && tx.sender_pid as u32 == pid, "unexpected transaction code/count/sender")?;
                need(binder.payload(&tx)? == [REQUEST_MAGIC, nonce], "request content mismatch")?;
                sender_euid = Some(tx.sender_euid);
                let response = [REPLY_MAGIC, nonce ^ REPLY_XOR];
                let reply = Transaction { data_size: 16, buffer: response.as_ptr() as u64, ..Default::default() };
                binder.command(BC_REPLY, &reply)?;
                binder.command(BC_FREE_BUFFER, &tx.buffer)?;
            } else if command == BR_FAILED_REPLY { return Err(binder.failure()); }
            else { need(command == BR_NOOP || command == BR_COMPLETE, &format!("unexpected server Binder command 0x{command:08x}"))?; }
        }
    }
    let (output, stderr) = child.output()?;
    need(status.success(), &format!("client failed: {status}; {stderr}"))?;
    need(stderr.is_empty() && output.len() >= 28 && &output[..8] == b"BNSMOKE1", "invalid client receipt")?;
    let word = |offset| u32::from_ne_bytes(output[offset..offset + 4].try_into().unwrap());
    let label_length = word(24) as usize;
    need(label_length > 0 && label_length < 256 && output.len() == 28 + label_length && word(8) == pid && word(16) == 8, "client receipt identity/layout mismatch")?;
    let opened = std::str::from_utf8(&output[28..]).map_err(|e| e.to_string())?;
    need(transaction_count == 1 && sender_euid == Some(word(12)), "actual sender credentials mismatch")?;
    need(if security { security_label.as_deref() == Some(opened) } else { security_label.is_none() }, "delivered security context differs from actual opening credential")?;
    need(!Path::new(&format!("/proc/{pid}")).exists(), "owned client proc entry remains after reaping")?;
    Ok(format!("{{\"context_requested\":{security},\"passed\":true,\"transaction_received\":1,\"reply_valid\":true,\"client_pid\":{pid},\"client_reaped\":true,\"sender_euid\":{},\"opened_credential\":{},\"received_context\":{},\"failed_reply\":false,\"system_errno\":0,\"extended_error\":0,\"transaction_complete_events\":{}}}", word(12), quoted(opened), security_label.as_deref().map(quoted).unwrap_or("null".into()), word(20)))
}

fn private_worker(runtime: &Path, expected_parent: i32, original_ns: &str, nonce: u64) -> R<bool> {
    need(unsafe { getppid() } == expected_parent && ns()? == original_ns, "worker starting parent/namespace mismatch")?;
    need(runtime.parent() == Some(Path::new(ROOT)) && runtime.file_name().and_then(|p| p.to_str()).is_some_and(|s| s.starts_with("runtime-")), "worker root mismatch")?;
    let mountpoint = runtime.join("binderfs");
    need(fs::symlink_metadata(&mountpoint).map_err(|e| e.to_string())?.is_dir(), "own mountpoint absent")?;
    if unsafe { unshare(CLONE_NEWNS) } != 0 { return Err(errno("unshare private mount namespace")); }
    let namespace = ns()?; need(namespace != original_ns, "mount namespace did not change")?;
    let slash = cstring("/")?;
    if unsafe { mount(std::ptr::null(), slash.as_ptr(), std::ptr::null(), MS_REC | MS_PRIVATE, std::ptr::null()) } != 0 { return Err(errno("make new namespace private")); }
    let target = cstring(mountpoint.to_str().ok_or("non-UTF8 own path")?)?;
    let binder = cstring("binder")?; let options = cstring("max=2")?;
    if unsafe { mount(binder.as_ptr(), target.as_ptr(), binder.as_ptr(), MS_NOSUID | MS_NOEXEC, options.as_ptr().cast()) } != 0 { return Err(errno("mount own binderfs")); }
    let mut cases = Vec::new(); let mut errors = Vec::new(); let mut created = Vec::new();
    let run = (|| -> R<()> {
        let entry = own_mounts()?; need(entry.len() == 1 && entry[0].contains(" - binder "), "private Binder mount not observed")?;
        let control = OpenOptions::new().read(true).write(true).custom_flags(O_NOFOLLOW).open(mountpoint.join("binder-control")).map_err(|e| e.to_string())?;
        for name in ["plain", "security"] {
            let mut device: Device = unsafe { zeroed() }; device.name[..name.len()].copy_from_slice(name.as_bytes());
            if unsafe { ioctl(control.as_raw_fd(), ADD_DEVICE as c_ulong, &mut device) } < 0 { return Err(errno("BINDER_CTL_ADD own device")); }
            created.push(mountpoint.join(name));
        }
        drop(control);
        for (index, name) in ["plain", "security"].iter().enumerate() {
            let security = index == 1;
            match run_case(&mountpoint.join(name), security, nonce ^ index as u64) {
                Ok(result) => cases.push(result),
                Err(error) => { cases.push(format!("{{\"context_requested\":{security},\"passed\":false,\"error\":{}}}", quoted(&error))); errors.push(error); },
            }
        }
        Ok(())
    })();
    if let Err(error) = run { errors.push(error); }
    for path in created { if let Err(error) = fs::remove_file(path) { errors.push(format!("unlink own Binder device: {error}")); } }
    let unmounted = unsafe { umount2(target.as_ptr(), 0) } == 0;
    if !unmounted { errors.push(errno("normal unmount own binderfs")); }
    let absent = own_mounts()?.is_empty();
    if !absent { errors.push("own Binder mount remains in worker namespace".into()); }
    let children = read(format!("/proc/self/task/{}/children", unsafe { getpid() }))?;
    let children_retired = children.trim().is_empty();
    if !children_retired { errors.push("owned worker child remains".into()); }
    let passed = errors.is_empty() && cases.len() == 2 && unmounted && absent && children_retired;
    println!("{{\"schema\":\"pocket4-binder-private-worker-v1\",\"passed\":{passed},\"mount_namespace\":{},\"original_namespace\":{},\"devices_created\":2,\"cases\":[{}],\"normal_unmount\":{unmounted},\"own_mount_absent_after\":{absent},\"children_retired\":{children_retired},\"errors\":[{}]}}", quoted(&namespace), quoted(original_ns), cases.join(","), errors.iter().map(|x| quoted(x)).collect::<Vec<_>>().join(","));
    Ok(passed)
}

fn bounds() -> R<String> {
    let row = read("/proc/self/cgroup")?;
    let path = row.trim().strip_prefix("0::/").ok_or("cgroup v2 required")?;
    need(path.ends_with(UNIT) && !path.split('/').any(|p| p == ".."), "dedicated bounded systemd unit required")?;
    let base = Path::new("/sys/fs/cgroup").join(path);
    need(read(base.join("memory.max"))?.trim() == "268435456", "256 MiB cap required")?;
    need(read(base.join("memory.swap.max"))?.trim() == "0", "no swap budget required")?;
    need(read(base.join("cpu.max"))?.trim() == "100000 100000", "one CPU quota required")?;
    Ok(base.to_string_lossy().into_owned())
}
fn main_supervisor() -> R<bool> {
    need(unsafe { getuid() == 0 && geteuid() == 0 }, "explicit root supervisor is required for private Binder mount")?;
    need(read("/proc/sys/kernel/osrelease")?.trim() == KERNEL, "running kernel differs from candidate")?;
    need(read("/proc/filesystems")?.lines().any(|l| l.split_whitespace().last() == Some("binder")) && Path::new("/sys/module/binder_linux").is_dir(), "Binder driver/filesystem must already be loaded")?;
    let root = fs::symlink_metadata(ROOT).map_err(|e| e.to_string())?;
    need(root.is_dir() && !root.file_type().is_symlink() && root.uid() == 1000 && root.mode() & 0o777 == 0o700, "private pre-created UID1000 work root required")?;
    let cgroup = bounds()?; let original_ns = ns()?;
    need(own_mounts()?.is_empty(), "preexisting mount under own root refused")?;
    if unsafe { prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) } != 0 { return Err(errno("subreaper")); }
    let pid = unsafe { getpid() }; let runtime = Path::new(ROOT).join(format!("runtime-{pid}"));
    fresh_dir(&runtime)?; fresh_dir(&runtime.join("binderfs"))?;
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos() as u64;
    let start = Instant::now();
    let mut command = Command::new(std::env::current_exe().map_err(|e| e.to_string())?);
    command.args(["--worker", runtime.to_str().unwrap(), &pid.to_string(), &original_ns, &nonce.to_string()]).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped()).process_group(0);
    unsafe { command.pre_exec(move || {
        if prctl(PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) != 0 { return Err(io::Error::last_os_error()); }
        if getppid() != pid { return Err(io::Error::new(io::ErrorKind::Interrupted, "parent retired")); }
        Ok(())
    }); }
    let mut worker = OwnedChild::new(command.spawn().map_err(|e| e.to_string())?);
    let worker_pid = worker.child.id() as i32; let deadline = Instant::now() + Duration::from_secs(40);
    let mut timed_out = false;
    let exit = loop {
        if let Some(status) = worker.child.try_wait().map_err(|e| e.to_string())? { worker.reaped = true; break status; }
        if Instant::now() >= deadline { timed_out = true; unsafe { kill(-worker_pid, SIGKILL); } break worker.child.wait().map_err(|e| e.to_string())?; }
        std::thread::sleep(Duration::from_millis(10));
    };
    worker.reaped = true;
    let drain_deadline = Instant::now() + Duration::from_secs(3); let mut reaped_adopted = Vec::new();
    let all_children_reaped = loop {
        let mut status = 0; let got = unsafe { waitpid(-1, &mut status, 1) };
        if got > 0 { reaped_adopted.push(got); continue; }
        if got < 0 && io::Error::last_os_error().raw_os_error() == Some(ECHILD) { break true; }
        if Instant::now() >= drain_deadline { break false; }
        unsafe { kill(-worker_pid, SIGKILL); }
        std::thread::sleep(Duration::from_millis(10));
    };
    let (output, stderr) = worker.output()?;
    let output = String::from_utf8(output).map_err(|e| e.to_string())?;
    let own_absent = own_mounts()?.is_empty();
    let namespace_unchanged = ns()? == original_ns;
    let worker_proc_absent = !Path::new(&format!("/proc/{worker_pid}")).exists();
    let group_absent = unsafe { kill(-worker_pid, 0) } < 0 && io::Error::last_os_error().raw_os_error() == Some(ESRCH);
    let mountpoint_removed = fs::remove_dir(runtime.join("binderfs")).is_ok();
    let runtime_removed = mountpoint_removed && fs::remove_dir(&runtime).is_ok();
    let events = read(Path::new(&cgroup).join("memory.events"))?;
    let oom_zero = events.lines().filter(|l| l.starts_with("oom ") || l.starts_with("oom_kill ") || l.starts_with("oom_group_kill ")).all(|l| l.split_whitespace().nth(1) == Some("0"));
    let peak = read(Path::new(&cgroup).join("memory.peak"))?.trim().to_string();
    let worker_json = output.trim();
    let report_syntax = worker_json.starts_with("{\"schema\":\"pocket4-binder-private-worker-v1\",") && worker_json.ends_with('}');
    let passed = exit.success() && !timed_out && stderr.is_empty() && report_syntax && own_absent && namespace_unchanged && worker_proc_absent && group_absent && runtime_removed && all_children_reaped && oom_zero;
    let report = format!("{{\"schema\":\"pocket4-binder-host-smoke-v1\",\"state\":{},\"kernel\":{},\"host_binder_ipc_qualified\":{passed},\"android_runtime_qualified\":false,\"production_ready\":false,\"worker_pid\":{worker_pid},\"worker_exit_code\":{},\"timed_out\":{timed_out},\"elapsed_ms\":{},\"parent_mount_namespace\":{},\"parent_namespace_unchanged\":{namespace_unchanged},\"parent_own_mount_absent\":{own_absent},\"worker_proc_and_namespace_absent\":{worker_proc_absent},\"worker_process_group_absent\":{group_absent},\"all_children_reaped\":{all_children_reaped},\"adopted_reaped_pids\":{:?},\"runtime_directory_removed\":{runtime_removed},\"memory_max_bytes\":268435456,\"memory_peak_bytes\":{peak},\"oom_events_zero\":{oom_zero},\"cpu_quota_percent\":100,\"stderr\":{},\"worker\":{}}}\n", quoted(if passed { "PASS" } else { "FAIL" }), quoted(KERNEL), exit.code().map(|n| n.to_string()).unwrap_or("null".into()), start.elapsed().as_millis(), quoted(&original_ns), reaped_adopted, quoted(&stderr), if report_syntax { worker_json.to_string() } else { quoted(&output) });
    let mut file = OpenOptions::new().create_new(true).write(true).mode(0o644).custom_flags(O_NOFOLLOW).open(Path::new(ROOT).join("result.json")).map_err(|e| e.to_string())?;
    file.write_all(report.as_bytes()).map_err(|e| e.to_string())?; file.sync_all().map_err(|e| e.to_string())?;
    print!("{report}");
    Ok(passed)
}

fn entry() -> R<bool> {
    abi()?;
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("--self-check") if args.len() == 1 => { need(frames(&[0]).is_err(), "truncated-wire rejection failed")?; println!("{{\"abi_checked\":true,\"truncated_wire_rejected\":true,\"device_actions\":0}}"); Ok(true) },
        Some("--run-host-smoke") if args.len() == 1 => main_supervisor(),
        Some("--worker") if args.len() == 5 => private_worker(Path::new(&args[1]), args[2].parse().map_err(|_| "bad parent")?, &args[3], args[4].parse().map_err(|_| "bad nonce")?),
        Some("--client") if args.len() == 5 => { client(Path::new(&args[1]), args[2].parse().map_err(|_| "bad parent")?, &args[3], args[4].parse().map_err(|_| "bad nonce")?)?; Ok(true) },
        _ => Err("explicit --self-check or bounded --run-host-smoke is required".into()),
    }
}
fn main() -> ExitCode { match entry() { Ok(true) => ExitCode::SUCCESS, Ok(false) => ExitCode::from(1), Err(error) => { eprintln!("{error}"); ExitCode::from(2) } } }
