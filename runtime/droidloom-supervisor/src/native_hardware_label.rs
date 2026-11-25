//! One fixed udev PROGRAM, before stock input builtins open a new device.
//!
//! The executable is shared with the daemon; the SELinux entry role permits
//! only this dispatch. No caller supplies a path outside the three kernel
//! naming grammars, a context, a mode, an owner, or a device operation.

use std::ffi::{CStr, CString, OsStr, OsString};
use std::fs::File;
use std::io;
use std::mem::{size_of, size_of_val, zeroed};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::ffi::OsStrExt;

const ENTRY: &str = "__native-hardware-label";
const ROLE: &[u8] = b"u:system_r:p4_linux_hardware_label_t:s0";
const FACTORY_AA: &[u8] = b"droidloom-instance-factory (enforce)";
const HELPER_AA: &[u8] = b"droidloom-native-hardware-label (enforce)";
const ORIGINAL_DEVICE: &[u8] = b"u:object_r:device:s0";
const DEV_ROOT: &[u8] = b"u:object_r:p4_linux_native_dev_root_t:s0";
const NS_CONTEXT: &[u8] = b"u:object_r:p4_kernel_ns_handle_t:s0";
const HANDOFF: &[u8] = b"u:object_r:p4_linux_early_handoff_dir_t:s0";
const STATX_MNT_ID_UNIQUE: u32 = 0x4000;
const SYS_STATMOUNT: libc::c_long = 457;
const SYS_LSM_GET_SELF_ATTR: libc::c_long = 459;
const SYS_LSM_SET_SELF_ATTR: libc::c_long = 460;
const SYS_SETXATTRAT: libc::c_long = 463;
const SYS_GETXATTRAT: libc::c_long = 464;
const SELINUX: u64 = 101;
const APPARMOR: u64 = 104;
const NSFS_MAGIC: libc::c_long = 0x6e736673;
const MAX_MINOR: u32 = (1 << 20) - 1;

fn reject(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, reason)
}

fn syscall_ok(value: libc::c_long) -> io::Result<libc::c_long> {
    if value < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Kind {
    Card,
    Render,
    Event,
    Video,
}

#[derive(Debug, Eq, PartialEq)]
struct DeviceName {
    kind: Kind,
    number: u32,
}

impl DeviceName {
    fn parse(value: &OsStr) -> io::Result<Self> {
        let bytes = value.as_bytes();
        let (kind, digits) = if let Some(n) = bytes.strip_prefix(b"/dev/dri/card") {
            (Kind::Card, n)
        } else if let Some(n) = bytes.strip_prefix(b"/dev/dri/renderD") {
            (Kind::Render, n)
        } else if let Some(n) = bytes.strip_prefix(b"/dev/input/event") {
            (Kind::Event, n)
        } else if let Some(n) = bytes.strip_prefix(b"/dev/video") {
            (Kind::Video, n)
        } else {
            return Err(reject("not a fixed native DRM, evdev or video node"));
        };
        if digits.is_empty()
            || digits.len() > 7
            || !digits.iter().all(u8::is_ascii_digit)
            || (digits.len() > 1 && digits[0] == b'0')
        {
            return Err(reject("noncanonical native device number"));
        }
        let mut number = 0u32;
        for digit in digits {
            number = number * 10 + u32::from(digit - b'0');
        }
        // Actual 6.18 allocation: DRM primary 0..63, render 128..191,
        // both spill into 192..MINORMASK. Evdev 64..95 is named event0..31;
        // dynamic evdev uses its unmodified minor number starting at 256.
        let valid = match kind {
            Kind::Card => number <= 63 || (192..=MAX_MINOR).contains(&number),
            Kind::Render => (128..=MAX_MINOR).contains(&number),
            Kind::Event => number <= 31 || (256..1024).contains(&number),
            Kind::Video => number < 256,
        };
        if !valid {
            return Err(reject("number is outside the kernel allocation grammar"));
        }
        Ok(Self { kind, number })
    }

    fn parent(&self) -> &'static CStr {
        match self.kind {
            Kind::Card | Kind::Render => c"dri",
            Kind::Event => c"input",
            Kind::Video => c".",
        }
    }
    fn leaf(&self) -> CString {
        CString::new(format!(
            "{}{}",
            match self.kind {
                Kind::Card => "card",
                Kind::Render => "renderD",
                Kind::Event => "event",
                Kind::Video => "video",
            },
            self.number
        ))
        .expect("fixed ASCII and decimal")
    }
    fn context(&self) -> &'static [u8] {
        match self.kind {
            Kind::Card => b"u:object_r:p4_linux_drm_card_t:s0",
            Kind::Render => b"u:object_r:p4_linux_drm_render_t:s0",
            Kind::Event => b"u:object_r:p4_linux_input_event_t:s0",
            Kind::Video => b"u:object_r:p4_linux_uvc_device_t:s0",
        }
    }
    fn parent_context(&self) -> &'static [u8] {
        match self.kind {
            Kind::Card | Kind::Render => b"u:object_r:p4_linux_drm_dir_t:s0",
            Kind::Event => b"u:object_r:p4_linux_input_dir_t:s0",
            Kind::Video => DEV_ROOT,
        }
    }
    fn matches_rdev(&self, value: libc::dev_t) -> bool {
        let (major, minor) = self.rdev();
        libc::major(value) == major
            && if self.kind == Kind::Video {
                // videoN and minor are independently allocated in the target kernel.
                libc::minor(value) < 256
            } else {
                libc::minor(value) == minor
            }
    }
    fn rdev(&self) -> (u32, u32) {
        match self.kind {
            Kind::Card | Kind::Render => (226, self.number),
            Kind::Video => (81, self.number),
            Kind::Event => (
                13,
                if self.number < 32 {
                    self.number + 64
                } else {
                    self.number
                },
            ),
        }
    }
}

#[repr(C)]
struct LsmContext {
    id: u64,
    flags: u64,
    len: u64,
    ctx_len: u64,
    text: [u8; 480],
}

fn current(provider: u64) -> io::Result<Vec<u8>> {
    let mut context = LsmContext {
        id: provider,
        flags: 0,
        len: 0,
        ctx_len: 0,
        text: [0; 480],
    };
    let mut length = size_of::<LsmContext>() as u32;
    let count = syscall_ok(unsafe {
        libc::syscall(
            SYS_LSM_GET_SELF_ATTR,
            100u32,
            &mut context,
            &mut length,
            1u32,
        )
    })?;
    if count != 1
        || context.id != provider
        || context.flags != 0
        || context.len != u64::from(length)
        || context.len < 32
        || context.len > size_of::<LsmContext>() as u64
        || context.ctx_len == 0
        || context.ctx_len > context.len - 32
    {
        return Err(reject("invalid native LSM self-attribute record"));
    }
    let mut text = context.text[..context.ctx_len as usize].to_vec();
    if text.last() == Some(&0) {
        text.pop();
    }
    if text.contains(&0) {
        return Err(reject("embedded NUL in native LSM self-attribute"));
    }
    Ok(text)
}

fn enter_apparmor() -> io::Result<()> {
    if current(APPARMOR)? != FACTORY_AA {
        return Err(reject(
            "hardware entry did not inherit the published ELF attachment",
        ));
    }
    if unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 0 {
        return Err(reject(
            "stock udev hardware entry must precede no-new-privileges",
        ));
    }
    let command = b"changeprofile droidloom-native-hardware-label\0";
    let mut context = LsmContext {
        id: APPARMOR,
        flags: 0,
        len: (32 + command.len()) as u64,
        ctx_len: command.len() as u64,
        text: [0; 480],
    };
    context.text[..command.len()].copy_from_slice(command);
    syscall_ok(unsafe {
        libc::syscall(
            SYS_LSM_SET_SELF_ATTR,
            100u32,
            &context,
            context.len as u32,
            0u32,
        )
    })?;
    if current(APPARMOR)? != HELPER_AA || current(SELINUX)? != ROLE {
        return Err(reject("fixed hardware MAC transition did not take effect"));
    }
    Ok(())
}

#[repr(C)]
struct CapHeader {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Default)]
struct CapData {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}

fn root_without_capabilities() -> io::Result<()> {
    let mut ids = [1u32; 6];
    syscall_ok(unsafe { libc::getresuid(&mut ids[0], &mut ids[1], &mut ids[2]) } as _)?;
    syscall_ok(unsafe { libc::getresgid(&mut ids[3], &mut ids[4], &mut ids[5]) } as _)?;
    if ids != [0; 6] {
        return Err(reject(
            "hardware labeling is only an original root udev operation",
        ));
    }
    let header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let empty = [CapData::default(), CapData::default()];
    syscall_ok(unsafe { libc::syscall(libc::SYS_capset, &header, empty.as_ptr()) })?;
    syscall_ok(unsafe {
        libc::prctl(
            libc::PR_CAP_AMBIENT,
            libc::PR_CAP_AMBIENT_CLEAR_ALL,
            0,
            0,
            0,
        )
    } as _)?;
    syscall_ok(unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } as _)?;
    let mut readback = [CapData::default(), CapData::default()];
    syscall_ok(unsafe { libc::syscall(libc::SYS_capget, &header, readback.as_mut_ptr()) })?;
    if readback
        .iter()
        .any(|v| v.effective != 0 || v.permitted != 0 || v.inheritable != 0)
        || unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } != 1
    {
        return Err(reject("hardware helper capabilities did not retire"));
    }
    // This one-shot branch has no worker threads. Other same-UID tasks must
    // not inspect its held descriptors, even if they entered the same role.
    syscall_ok(unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } as _)?;
    if unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) } != 0 {
        return Err(reject("hardware helper remained dumpable"));
    }
    Ok(())
}

pub(crate) fn path_at(parent: RawFd, name: &CStr) -> io::Result<File> {
    let fd = syscall_ok(unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    } as _)?;
    Ok(unsafe { File::from_raw_fd(fd as RawFd) })
}

pub(crate) fn metadata(file: &File) -> io::Result<libc::stat> {
    let mut st = unsafe { zeroed::<libc::stat>() };
    syscall_ok(unsafe { libc::fstat(file.as_raw_fd(), &mut st) } as _)?;
    Ok(st)
}

pub(crate) fn directory(file: &File) -> io::Result<libc::stat> {
    let st = metadata(file)?;
    if st.st_mode & libc::S_IFMT != libc::S_IFDIR
        || st.st_uid != 0
        || st.st_gid != 0
        || st.st_mode & 0o022 != 0
    {
        return Err(reject(
            "native hardware parent is not a protected root directory",
        ));
    }
    Ok(st)
}

pub(crate) fn same_inode(a: &libc::stat, b: &libc::stat) -> bool {
    a.st_dev == b.st_dev
        && a.st_ino == b.st_ino
        && a.st_rdev == b.st_rdev
        && a.st_uid == b.st_uid
        && a.st_gid == b.st_gid
        && a.st_mode == b.st_mode
}

#[repr(C)]
struct XattrArgs {
    value: u64,
    size: u32,
    flags: u32,
}

// In the target 6.18 kernel, xattrat's empty-path branch uses fdget(),
// which deliberately excludes O_PATH. The pathname branch accepts the
// original held inode through this task's fixed proc-FD link. No caller
// chooses the pathname, another PID, an fd number, or an xattr key.
fn held_xattr(
    file: &File,
    operation: libc::c_long,
    key: &CStr,
    args: &XattrArgs,
) -> io::Result<libc::c_long> {
    if operation != SYS_GETXATTRAT && operation != SYS_SETXATTRAT {
        return Err(reject("not a held-inode xattr operation"));
    }
    let flags = syscall_ok(unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) } as _)?;
    if flags as i32 & libc::O_PATH == 0 {
        return Err(reject("hardware xattr requires the original O_PATH handle"));
    }
    let before = metadata(file)?;
    let mount = mount_id(file)?;
    let path = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .expect("fixed ASCII and the held nonnegative descriptor");
    let verify = || -> io::Result<()> {
        // Follow only the self-constructed proc magic link. This second
        // O_PATH handle also cannot read or write the device body.
        let fd = syscall_ok(unsafe {
            libc::openat(
                libc::AT_FDCWD,
                path.as_ptr(),
                libc::O_PATH | libc::O_CLOEXEC,
            )
        } as _)?;
        let observed = unsafe { File::from_raw_fd(fd as RawFd) };
        if !same_inode(&before, &metadata(file)?)
            || !same_inode(&before, &metadata(&observed)?)
            || mount_id(file)? != mount
            || mount_id(&observed)? != mount
        {
            return Err(reject("self-FD link no longer identifies the held inode"));
        }
        Ok(())
    };
    verify()?;
    let result = syscall_ok(unsafe {
        libc::syscall(
            operation,
            libc::AT_FDCWD,
            path.as_ptr(),
            0u32,
            key.as_ptr(),
            args,
            size_of::<XattrArgs>(),
        )
    })?;
    verify()?;
    Ok(result)
}

pub(crate) fn label(file: &File) -> io::Result<Vec<u8>> {
    let mut buffer = [0u8; 256];
    let args = XattrArgs {
        value: buffer.as_mut_ptr() as u64,
        size: buffer.len() as u32,
        flags: 0,
    };
    let len = held_xattr(file, SYS_GETXATTRAT, c"security.selinux", &args)? as usize;
    if len == 0 || len > buffer.len() {
        return Err(reject("invalid held-inode SELinux label"));
    }
    let mut result = buffer[..len].to_vec();
    if result.last() == Some(&0) {
        result.pop();
    }
    Ok(result)
}

fn label_fixed(file: &File, wanted: &[u8]) -> io::Result<()> {
    let before = label(file)?;
    if before == wanted {
        return Ok(());
    }
    if before != ORIGINAL_DEVICE {
        return Err(reject(
            "native hardware inode has an unexpected source type",
        ));
    }
    let args = XattrArgs {
        value: wanted.as_ptr() as u64,
        size: wanted.len() as u32,
        flags: 0,
    };
    held_xattr(file, SYS_SETXATTRAT, c"security.selinux", &args)?;
    if label(file)? != wanted {
        return Err(reject("native hardware label readback differs"));
    }
    Ok(())
}

pub(crate) fn mount_id(file: &File) -> io::Result<u64> {
    let mut st = unsafe { zeroed::<libc::statx>() };
    syscall_ok(unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            STATX_MNT_ID_UNIQUE,
            &mut st,
        )
    } as _)?;
    if st.stx_mask & STATX_MNT_ID_UNIQUE == 0 || st.stx_mnt_id == 0 {
        return Err(reject("kernel did not return a unique held mount identity"));
    }
    Ok(st.stx_mnt_id)
}

pub(crate) fn mount_identity(file: &File) -> io::Result<(u64, u64, Vec<u8>)> {
    let id = mount_id(file)?;
    // Ver0 request selects this caller's mount namespace; never another PID.
    let request = [24u64, id, 0x22u64]; // MNT_BASIC | FS_TYPE
    let mut buffer = [0u64; 1024];
    syscall_ok(unsafe {
        libc::syscall(
            SYS_STATMOUNT,
            request.as_ptr(),
            buffer.as_mut_ptr(),
            size_of_val(&buffer),
            0u32,
        )
    })?;
    let bytes =
        unsafe { std::slice::from_raw_parts(buffer.as_ptr().cast::<u8>(), size_of_val(&buffer)) };
    let u32_at = |offset| u32::from_ne_bytes(bytes[offset..offset + 4].try_into().unwrap());
    let u64_at = |offset| u64::from_ne_bytes(bytes[offset..offset + 8].try_into().unwrap());
    let length = u32_at(0) as usize;
    let offset = 512usize
        .checked_add(u32_at(36) as usize)
        .ok_or_else(|| reject("statmount offset overflow"))?;
    if length < 513
        || length > bytes.len()
        || u64_at(8) & 0x22 != 0x22
        || u64_at(40) != id
        || offset >= length
    {
        return Err(reject("invalid statmount identity record"));
    }
    let tail = &bytes[offset..length];
    let end = tail
        .iter()
        .position(|v| *v == 0)
        .ok_or_else(|| reject("unterminated statmount filesystem"))?;
    if mount_id(file)? != id {
        return Err(reject("held mount identity changed"));
    }
    Ok((id, u64_at(64), tail[..end].to_vec()))
}

pub(crate) fn namespaces(root: &File) -> io::Result<()> {
    let run = path_at(root.as_raw_fd(), c"run")?;
    directory(&run)?;
    let handoff = path_at(run.as_raw_fd(), c"droidloom-early")?;
    directory(&handoff)?;
    if label(&handoff)? != HANDOFF {
        return Err(reject("boot namespace publisher is not the original owner"));
    }
    let pidfd = syscall_ok(unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0u32) })?;
    let pidfd = unsafe { File::from_raw_fd(pidfd as RawFd) };
    for (leaf, request, kind) in [
        (c"host-userns", 0xff09u64, libc::CLONE_NEWUSER),
        (c"host-pidns", 0xff05u64, libc::CLONE_NEWPID),
    ] {
        let actual = syscall_ok(unsafe {
            libc::ioctl(
                pidfd.as_raw_fd(),
                request as libc::c_ulong,
                0 as libc::c_ulong,
            )
        } as _)?;
        let actual = unsafe { File::from_raw_fd(actual as RawFd) };
        let original = path_at(handoff.as_raw_fd(), leaf)?;
        let a = metadata(&actual)?;
        let b = metadata(&original)?;
        let mut fs = unsafe { zeroed::<libc::statfs>() };
        syscall_ok(unsafe { libc::fstatfs(actual.as_raw_fd(), &mut fs) } as _)?;
        if fs.f_type != NSFS_MAGIC
            || a.st_dev != b.st_dev
            || a.st_ino != b.st_ino
            || label(&original)? != NS_CONTEXT
            || mount_identity(&original)?.1 & 1 == 0
            || unsafe {
                libc::ioctl(
                    actual.as_raw_fd(),
                    0xb703u64 as libc::c_ulong,
                    0 as libc::c_ulong,
                )
            } != kind
        {
            return Err(reject(
                "hardware entry is outside the boot-held initial namespace",
            ));
        }
    }
    Ok(())
}

fn apply(name: &DeviceName) -> io::Result<()> {
    let root = path_at(libc::AT_FDCWD, c"/")?;
    directory(&root)?;
    namespaces(&root)?;
    let dev = path_at(root.as_raw_fd(), c"dev")?;
    let dev_stat = directory(&dev)?;
    let (dev_mount, _, fs_type) = mount_identity(&dev)?;
    let dev_label = label(&dev)?;
    if fs_type != b"devtmpfs" || ![ORIGINAL_DEVICE, DEV_ROOT].contains(&dev_label.as_slice()) {
        return Err(reject(
            "hardware label entry requires the native devtmpfs root",
        ));
    }
    let parent = path_at(dev.as_raw_fd(), name.parent())?;
    let parent_stat = directory(&parent)?;
    let leaf = path_at(parent.as_raw_fd(), &name.leaf())?;
    let before = metadata(&leaf)?;
    if before.st_mode & libc::S_IFMT != libc::S_IFCHR
        || before.st_uid != 0
        || before.st_nlink != 1
        || !name.matches_rdev(before.st_rdev)
        || before.st_dev != dev_stat.st_dev
        || parent_stat.st_dev != dev_stat.st_dev
        || mount_id(&parent)? != dev_mount
        || mount_id(&leaf)? != dev_mount
    {
        return Err(reject(
            "native hardware node does not match its original kernel identity",
        ));
    }
    // Resolve the entire fixed chain before mutating any held inode.
    let parent_label = label(&parent)?;
    let leaf_label = label(&leaf)?;
    if ![ORIGINAL_DEVICE, name.parent_context()].contains(&parent_label.as_slice())
        || ![ORIGINAL_DEVICE, name.context()].contains(&leaf_label.as_slice())
    {
        return Err(reject("native hardware source labels are not admissible"));
    }
    // devtmpfs shadows the offline /dev directory; its first real root
    // label must be established here, not assumed from file_contexts.
    label_fixed(&dev, DEV_ROOT)?;
    label_fixed(&parent, name.parent_context())?;
    label_fixed(&leaf, name.context())?;
    if !same_inode(&before, &metadata(&leaf)?)
        || !same_inode(&dev_stat, &metadata(&dev)?)
        || !same_inode(&dev_stat, &metadata(&path_at(root.as_raw_fd(), c"dev")?)?)
        || mount_id(&dev)? != dev_mount
        || label(&dev)? != DEV_ROOT
        || label(&parent)? != name.parent_context()
        || label(&leaf)? != name.context()
        || !same_inode(&parent_stat, &metadata(&parent)?)
        || !same_inode(
            &before,
            &metadata(&path_at(parent.as_raw_fd(), &name.leaf())?)?,
        )
        || !same_inode(
            &parent_stat,
            &metadata(&path_at(dev.as_raw_fd(), name.parent())?)?,
        )
        || mount_id(&leaf)? != dev_mount
        || mount_id(&parent)? != dev_mount
    {
        return Err(reject(
            "native hardware inode changed during fixed labeling",
        ));
    }
    Ok(())
}

/// Dispatch before any normal daemon CLI parsing. `true` means this one-shot
/// operation completed. A task in the helper role cannot invoke another mode.
pub fn dispatch(arguments: &[OsString]) -> io::Result<bool> {
    let requested = arguments.first().is_some_and(|v| v == ENTRY);
    let role = current(SELINUX);
    let is_helper = role.as_ref().is_ok_and(|v| v == ROLE);
    if !requested && !is_helper {
        return Ok(false);
    }
    if !requested || arguments.len() != 2 || !is_helper {
        return Err(reject(
            "hardware label role accepts only its one fixed udev operation",
        ));
    }
    let name = DeviceName::parse(&arguments[1])?;
    enter_apparmor()?;
    root_without_capabilities()?;
    apply(&name)?;
    if current(SELINUX)? != ROLE || current(APPARMOR)? != HELPER_AA {
        return Err(reject("hardware helper MAC identity changed"));
    }
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn actual_kernel_names_and_device_numbers_are_closed() {
        for (path, expected) in [
            ("/dev/dri/card1", (226, 1)),
            ("/dev/dri/card192", (226, 192)),
            ("/dev/dri/renderD128", (226, 128)),
            ("/dev/input/event2", (13, 66)),
            ("/dev/input/event256", (13, 256)),
        ] {
            assert_eq!(
                DeviceName::parse(OsStr::new(path)).unwrap().rdev(),
                expected
            );
        }
        for path in [
            "/dev/dri/card64",
            "/dev/dri/renderD127",
            "/dev/input/event32",
            "/dev/input/event1024",
            "/dev/dri/card1048576",
            "/dev/dri/card01",
            "/dev/input/event-1",
            "/dev/input/event0/../event1",
            "/dev/video256",
            "/dev/video00",
            "/dev/video-1",
            "/dev/dri/controlD64",
            "/dev/input/mouse0",
            "card0",
            "/dev/dri/card",
            "/dev/dri/card0\0",
            "/dev/dri/card0\n",
        ] {
            assert!(DeviceName::parse(OsStr::new(path)).is_err(), "{path:?}");
        }
    }

    #[test]
    fn video_name_and_minor_have_independent_closed_kernel_ranges() {
        let first = DeviceName::parse(OsStr::new("/dev/video0")).unwrap();
        let last = DeviceName::parse(OsStr::new("/dev/video255")).unwrap();
        for name in [first, last] {
            assert!(name.matches_rdev(libc::makedev(81, 0)));
            assert!(name.matches_rdev(libc::makedev(81, 255)));
            assert!(!name.matches_rdev(libc::makedev(81, 256)));
            assert!(!name.matches_rdev(libc::makedev(82, 0)));
            assert_eq!(name.parent(), c".");
            assert_eq!(name.context(), b"u:object_r:p4_linux_uvc_device_t:s0");
        }
    }

    #[test]
    fn held_path_rejects_symlinks_and_does_not_follow_replacements() {
        use std::os::unix::fs::symlink;
        let dir = tempfile::tempdir().unwrap();
        let original = dir.path().join("original");
        std::fs::write(&original, b"public test input").unwrap();
        symlink(&original, dir.path().join("alias")).unwrap();
        let parent = path_at(
            libc::AT_FDCWD,
            &CString::new(dir.path().as_os_str().as_bytes()).unwrap(),
        )
        .unwrap();
        let link = path_at(parent.as_raw_fd(), c"alias").unwrap();
        assert_eq!(
            metadata(&link).unwrap().st_mode & libc::S_IFMT,
            libc::S_IFLNK
        );
        let held = path_at(parent.as_raw_fd(), c"original").unwrap();
        let before = metadata(&held).unwrap();
        std::fs::rename(&original, dir.path().join("retired")).unwrap();
        std::fs::write(&original, b"replacement").unwrap();
        assert!(same_inode(&before, &metadata(&held).unwrap()));
        assert!(!same_inode(
            &before,
            &metadata(&path_at(parent.as_raw_fd(), c"original").unwrap()).unwrap()
        ));
    }

    #[test]
    fn real_statmount_uses_held_mount_and_returns_filesystem() {
        let root = path_at(libc::AT_FDCWD, c"/").unwrap();
        let (id, _, fs) = mount_identity(&root).unwrap();
        assert_eq!(id, mount_id(&root).unwrap());
        assert!(!fs.is_empty());
        let dev = path_at(root.as_raw_fd(), c"dev").unwrap();
        let (_, _, devfs) = mount_identity(&dev).unwrap();
        assert!([b"devtmpfs".as_slice(), b"tmpfs".as_slice()].contains(&devfs.as_slice()));
        // A tmpfs /dev in a build container is not production-qualified.
    }

    #[test]
    fn real_self_pidfd_namespaces_need_no_ptrace_capability() {
        let header = CapHeader {
            version: 0x2008_0522,
            pid: 0,
        };
        let mut caps = [CapData::default(), CapData::default()];
        syscall_ok(unsafe { libc::syscall(libc::SYS_capget, &header, caps.as_mut_ptr()) }).unwrap();
        assert!(caps.iter().all(|c| c.permitted == 0 && c.effective == 0));
        let raw = syscall_ok(unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0u32) })
            .unwrap();
        let pidfd = unsafe { File::from_raw_fd(raw as RawFd) };
        for (request, kind, name) in [
            (0xff09u64, libc::CLONE_NEWUSER, "user"),
            (0xff05u64, libc::CLONE_NEWPID, "pid"),
        ] {
            let raw = syscall_ok(unsafe {
                libc::ioctl(
                    pidfd.as_raw_fd(),
                    request as libc::c_ulong,
                    0 as libc::c_ulong,
                )
            } as _)
            .unwrap();
            let actual = unsafe { File::from_raw_fd(raw as RawFd) };
            assert_eq!(
                unsafe {
                    libc::ioctl(
                        actual.as_raw_fd(),
                        0xb703u64 as libc::c_ulong,
                        0 as libc::c_ulong,
                    )
                },
                kind
            );
            let expected = File::open(format!("/proc/self/ns/{name}")).unwrap();
            let a = metadata(&actual).unwrap();
            let b = metadata(&expected).unwrap();
            assert_eq!((a.st_dev, a.st_ino), (b.st_dev, b.st_ino));
        }
    }

    #[test]
    fn real_xattrat_binds_to_an_opath_inode_without_body_access() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("public-xattr-probe");
        std::fs::write(&path, b"public syscall mechanism").unwrap();
        let held = path_at(
            libc::AT_FDCWD,
            &CString::new(path.as_os_str().as_bytes()).unwrap(),
        )
        .unwrap();
        let data = b"held-original";
        let args = XattrArgs {
            value: data.as_ptr() as u64,
            size: data.len() as u32,
            flags: 0,
        };
        held_xattr(
            &held,
            SYS_SETXATTRAT,
            c"user.droidloom_hardware_probe",
            &args,
        )
        .unwrap();
        std::fs::rename(&path, dir.path().join("retired")).unwrap();
        std::fs::write(&path, b"new inode").unwrap();
        let mut buffer = [0u8; 64];
        let args = XattrArgs {
            value: buffer.as_mut_ptr() as u64,
            size: buffer.len() as u32,
            flags: 0,
        };
        let length = held_xattr(
            &held,
            SYS_GETXATTRAT,
            c"user.droidloom_hardware_probe",
            &args,
        )
        .unwrap() as usize;
        assert_eq!(&buffer[..length], data);
        let new = path_at(
            libc::AT_FDCWD,
            &CString::new(path.as_os_str().as_bytes()).unwrap(),
        )
        .unwrap();
        let error = held_xattr(
            &new,
            SYS_GETXATTRAT,
            c"user.droidloom_hardware_probe",
            &args,
        )
        .unwrap_err();
        assert_eq!(error.raw_os_error(), Some(libc::ENODATA));
    }

    #[test]
    fn native_apparmor_record_matches_the_same_tasks_provider_specific_view() {
        let actual = current(APPARMOR).unwrap();
        let expected = std::fs::read("/proc/self/attr/apparmor/current").unwrap();
        let expected = expected.strip_suffix(b"\n").unwrap_or(&expected);
        assert_eq!(actual, expected);
    }
}
