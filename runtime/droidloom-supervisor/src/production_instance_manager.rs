//! Fixed peer-to-peer systemd observations for one instance launcher.
//! The connection pins the original owner and observer objects across shutdown.
use std::ffi::{CStr, c_char, c_int, c_void};
use std::io;
use std::ptr::{self, NonNull};

#[path = "production_instance_manager_adoption.rs"]
mod adoption;

#[repr(C)]
struct Bus {
    _private: [u8; 0],
}
#[repr(C)]
struct Message {
    _private: [u8; 0],
}
#[link(name = "libsystemd.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn sd_bus_new(bus: *mut *mut Bus) -> c_int;
    fn sd_bus_close_unref(bus: *mut Bus) -> *mut Bus;
    fn sd_bus_set_address(bus: *mut Bus, address: *const c_char) -> c_int;
    fn sd_bus_set_bus_client(bus: *mut Bus, value: c_int) -> c_int;
    fn sd_bus_set_exit_on_disconnect(bus: *mut Bus, value: c_int) -> c_int;
    fn sd_bus_set_method_call_timeout(bus: *mut Bus, usec: u64) -> c_int;
    fn sd_bus_start(bus: *mut Bus) -> c_int;
    fn sd_bus_get_fd(bus: *mut Bus) -> c_int;
    fn sd_bus_message_new_method_call(
        bus: *mut Bus,
        message: *mut *mut Message,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
    ) -> c_int;
    fn sd_bus_message_append_basic(
        message: *mut Message,
        kind: c_char,
        value: *const c_void,
    ) -> c_int;
    fn sd_bus_call(
        bus: *mut Bus,
        message: *mut Message,
        usec: u64,
        error: *mut c_void,
        reply: *mut *mut Message,
    ) -> c_int;
    fn sd_bus_message_at_end(message: *mut Message, complete: c_int) -> c_int;
    fn sd_bus_message_unref(message: *mut Message) -> *mut Message;
    fn sd_bus_get_property(
        bus: *mut Bus,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
        error: *mut c_void,
        reply: *mut *mut Message,
        kind: *const c_char,
    ) -> c_int;
    fn sd_bus_message_read_array(
        message: *mut Message,
        kind: c_char,
        pointer: *mut *const c_void,
        size: *mut usize,
    ) -> c_int;
    fn sd_bus_message_enter_container(
        message: *mut Message,
        kind: c_char,
        contents: *const c_char,
    ) -> c_int;
    fn sd_bus_message_exit_container(message: *mut Message) -> c_int;
    fn sd_bus_message_read_basic(message: *mut Message, kind: c_char, value: *mut c_void) -> c_int;
    fn sd_bus_message_skip(message: *mut Message, types: *const c_char) -> c_int;
    fn sd_bus_get_property_string(
        bus: *mut Bus,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
        error: *mut c_void,
        value: *mut *mut c_char,
    ) -> c_int;
    fn sd_bus_get_property_trivial(
        bus: *mut Bus,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
        error: *mut c_void,
        kind: c_char,
        value: *mut c_void,
    ) -> c_int;
    fn sd_notify(unset_environment: c_int, state: *const c_char) -> c_int;
}
const DEST: &CStr = c"org.freedesktop.systemd1";
const MANAGER: &CStr = c"/org/freedesktop/systemd1";
const UNIT: &CStr = c"org.freedesktop.systemd1.Unit";
const SERVICE: &CStr = c"org.freedesktop.systemd1.Service";
const OWNER: &CStr = c"/org/freedesktop/systemd1/unit/droidloom_2dproduction_2eservice";
const OBSERVER: &CStr = c"/org/freedesktop/systemd1/unit/droidloom_2dearly_2dobserver_2eservice";
const LAUNCHER: &CStr = c"/org/freedesktop/systemd1/unit/droidloom_2dinstance_2dlauncher_2eservice";

fn checked(value: c_int) -> io::Result<c_int> {
    if value < 0 {
        Err(io::Error::from_raw_os_error(-value))
    } else {
        Ok(value)
    }
}
fn invalid(reason: &'static str) -> io::Error {
    io::Error::other(reason)
}
struct Reply(NonNull<Message>);
impl Drop for Reply {
    fn drop(&mut self) {
        unsafe {
            sd_bus_message_unref(self.0.as_ptr());
        }
    }
}
impl Reply {
    fn new(raw: *mut Message) -> io::Result<Self> {
        Ok(Self(
            NonNull::new(raw).ok_or_else(|| invalid("systemd returned a null reply"))?,
        ))
    }
}
pub(super) struct Manager {
    bus: NonNull<Bus>,
}
impl Drop for Manager {
    fn drop(&mut self) {
        unsafe {
            sd_bus_close_unref(self.bus.as_ptr());
        }
    }
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub(super) struct Snapshot {
    pub invocation: [u8; 16],
    pub state: String,
    pub main_pid: u32,
    pub exec_pid: u32,
    pub code: i32,
    pub status: i32,
    pub result: String,
}
impl Snapshot {
    pub fn live(&self) -> bool {
        self.invocation != [0; 16]
            && self.main_pid > 1
            && matches!(
                self.state.as_str(),
                "active" | "activating" | "deactivating"
            )
    }
    pub fn clean_exit(&self, original: &[u8; 16], original_pid: u32) -> io::Result<bool> {
        if self.invocation != *original {
            return Err(invalid("the original resource owner invocation changed"));
        }
        if self.state == "failed" || (self.state == "inactive" && self.result != "success") {
            return Err(invalid(
                "the original resource owner did not stop successfully",
            ));
        }
        if self.state != "inactive" || self.main_pid != 0 {
            return Ok(false);
        }
        if self.exec_pid != original_pid || self.code != 1 || self.status != 0 {
            return Err(invalid(
                "resource owner exit was not its original normal status zero",
            ));
        }
        Ok(true)
    }
}
impl Manager {
    pub fn acquire() -> io::Result<Self> {
        let mut raw = ptr::null_mut();
        checked(unsafe { sd_bus_new(&mut raw) })?;
        let held = Self {
            bus: NonNull::new(raw).ok_or_else(|| invalid("systemd returned a null bus"))?,
        };
        // The service never accepts a user-selected bus or an alternate manager.
        checked(unsafe { sd_bus_set_address(raw, c"unix:path=/run/systemd/private".as_ptr()) })?;
        checked(unsafe { sd_bus_set_bus_client(raw, 0) })?;
        checked(unsafe { sd_bus_set_exit_on_disconnect(raw, 0) })?;
        checked(unsafe { sd_bus_set_method_call_timeout(raw, 5_000_000) })?;
        checked(unsafe { sd_bus_start(raw) })?;
        held.check_peer()?;
        for name in [
            c"droidloom-production.service",
            c"droidloom-early-observer.service",
        ] {
            held.reference(name)?;
        }
        Ok(held)
    }
    fn check_peer(&self) -> io::Result<()> {
        let fd = checked(unsafe { sd_bus_get_fd(self.bus.as_ptr()) })?;
        let mut credentials: libc::ucred = unsafe { std::mem::zeroed() };
        let mut length = std::mem::size_of_val(&credentials) as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                fd,
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                (&mut credentials as *mut libc::ucred).cast(),
                &mut length,
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        if length as usize != std::mem::size_of_val(&credentials)
            || credentials.pid != 1
            || credentials.uid != 0
            || credentials.gid != 0
        {
            return Err(invalid(
                "the private system manager is not original Linux PID 1",
            ));
        }
        Ok(())
    }
    fn reference(&self, name: &CStr) -> io::Result<()> {
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_message_new_method_call(
                self.bus.as_ptr(),
                &mut raw,
                DEST.as_ptr(),
                MANAGER.as_ptr(),
                c"org.freedesktop.systemd1.Manager".as_ptr(),
                c"RefUnit".as_ptr(),
            )
        })?;
        let request = Reply::new(raw)?;
        checked(unsafe {
            sd_bus_message_append_basic(request.0.as_ptr(), b's' as c_char, name.as_ptr().cast())
        })?;
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_call(
                self.bus.as_ptr(),
                request.0.as_ptr(),
                5_000_000,
                ptr::null_mut(),
                &mut raw,
            )
        })?;
        let response = Reply::new(raw)?;
        if unsafe { sd_bus_message_at_end(response.0.as_ptr(), 1) } != 1 {
            return Err(invalid("unexpected systemd reference response"));
        }
        Ok(())
    }
    fn string(&self, path: &CStr, interface: &CStr, member: &CStr) -> io::Result<String> {
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_get_property_string(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                path.as_ptr(),
                interface.as_ptr(),
                member.as_ptr(),
                ptr::null_mut(),
                &mut raw,
            )
        })?;
        let pointer = NonNull::new(raw).ok_or_else(|| invalid("null systemd string"))?;
        let result = unsafe { CStr::from_ptr(pointer.as_ptr()) }
            .to_str()
            .map(str::to_owned)
            .map_err(io::Error::other);
        unsafe {
            libc::free(pointer.as_ptr().cast());
        }
        result
    }
    fn security_context(&self, path: &CStr, member: &CStr) -> io::Result<String> {
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_get_property(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                path.as_ptr(),
                SERVICE.as_ptr(),
                member.as_ptr(),
                ptr::null_mut(),
                &mut raw,
                c"(bs)".as_ptr(),
            )
        })?;
        let reply = Reply::new(raw)?;
        checked(unsafe {
            sd_bus_message_enter_container(reply.0.as_ptr(), b'r' as c_char, c"bs".as_ptr())
        })?;
        let mut ignore = 0i32;
        let mut value: *const c_char = ptr::null();
        checked(unsafe {
            sd_bus_message_read_basic(
                reply.0.as_ptr(),
                b'b' as c_char,
                (&mut ignore as *mut i32).cast(),
            )
        })?;
        checked(unsafe {
            sd_bus_message_read_basic(
                reply.0.as_ptr(),
                b's' as c_char,
                (&mut value as *mut *const c_char).cast(),
            )
        })?;
        if ignore != 0 || value.is_null() {
            return Err(invalid("launcher security context is optional or absent"));
        }
        let text = unsafe { CStr::from_ptr(value) }
            .to_str()
            .map_err(io::Error::other)?
            .to_owned();
        checked(unsafe { sd_bus_message_exit_container(reply.0.as_ptr()) })?;
        if unsafe { sd_bus_message_at_end(reply.0.as_ptr(), 1) } != 1 {
            return Err(invalid("ambiguous launcher security context"));
        }
        Ok(text)
    }
    fn boolean(&self, path: &CStr, member: &CStr) -> io::Result<bool> {
        let mut value = 0i32;
        checked(unsafe {
            sd_bus_get_property_trivial(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                path.as_ptr(),
                SERVICE.as_ptr(),
                member.as_ptr(),
                ptr::null_mut(),
                b'b' as c_char,
                (&mut value as *mut i32).cast(),
            )
        })?;
        match value {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(invalid("invalid systemd boolean")),
        }
    }
    fn fixed_exec(&self, path: &CStr, expected: &[&str]) -> io::Result<()> {
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_get_property(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                path.as_ptr(),
                SERVICE.as_ptr(),
                c"ExecStart".as_ptr(),
                ptr::null_mut(),
                &mut raw,
                c"a(sasbttttuii)".as_ptr(),
            )
        })?;
        let reply = Reply::new(raw)?;
        let m = reply.0.as_ptr();
        if checked(unsafe {
            sd_bus_message_enter_container(m, b'a' as c_char, c"(sasbttttuii)".as_ptr())
        })? != 1
            || checked(unsafe {
                sd_bus_message_enter_container(m, b'r' as c_char, c"sasbttttuii".as_ptr())
            })? != 1
        {
            return Err(invalid("fixed service has no original exec command"));
        }
        let read_string = || -> io::Result<Option<String>> {
            let mut value: *const c_char = ptr::null();
            let n = checked(unsafe {
                sd_bus_message_read_basic(
                    m,
                    b's' as c_char,
                    (&mut value as *mut *const c_char).cast(),
                )
            })?;
            if n == 0 {
                return Ok(None);
            }
            if value.is_null() {
                return Err(invalid("null original exec argument"));
            }
            Ok(Some(
                unsafe { CStr::from_ptr(value) }
                    .to_str()
                    .map_err(io::Error::other)?
                    .to_owned(),
            ))
        };
        let executable = read_string()?.ok_or_else(|| invalid("original exec path is absent"))?;
        if checked(unsafe { sd_bus_message_enter_container(m, b'a' as c_char, c"s".as_ptr()) })?
            != 1
        {
            return Err(invalid("original exec arguments are absent"));
        }
        let mut arguments = Vec::new();
        while let Some(value) = read_string()? {
            if arguments.len() >= 8 || value.len() > 256 {
                return Err(invalid("original exec arguments differ"));
            }
            arguments.push(value);
        }
        checked(unsafe { sd_bus_message_exit_container(m) })?;
        let mut ignored = 0i32;
        if checked(unsafe {
            sd_bus_message_read_basic(m, b'b' as c_char, (&mut ignored as *mut i32).cast())
        })? != 1
            || ignored != 0
            || executable != expected[0]
            || arguments != expected
        {
            return Err(invalid(
                "fixed service exec command differs or ignores failure",
            ));
        }
        if checked(unsafe { sd_bus_message_skip(m, c"ttttuii".as_ptr()) })? != 1 {
            return Err(invalid("original exec outcome is incomplete"));
        }
        checked(unsafe { sd_bus_message_exit_container(m) })?;
        if unsafe { sd_bus_message_at_end(m, 0) } != 1 {
            return Err(invalid("fixed service has additional exec commands"));
        }
        checked(unsafe { sd_bus_message_exit_container(m) })?;
        if unsafe { sd_bus_message_at_end(m, 1) } != 1 {
            return Err(invalid("ambiguous original exec property"));
        }
        Ok(())
    }
    fn number(&self, path: &CStr, member: &CStr, signed: bool) -> io::Result<u32> {
        let mut value = 0u32;
        checked(unsafe {
            sd_bus_get_property_trivial(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                path.as_ptr(),
                SERVICE.as_ptr(),
                member.as_ptr(),
                ptr::null_mut(),
                if signed { b'i' } else { b'u' } as c_char,
                (&mut value as *mut u32).cast(),
            )
        })?;
        Ok(value)
    }
    fn invocation(&self, path: &CStr) -> io::Result<[u8; 16]> {
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_get_property(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                path.as_ptr(),
                UNIT.as_ptr(),
                c"InvocationID".as_ptr(),
                ptr::null_mut(),
                &mut raw,
                c"ay".as_ptr(),
            )
        })?;
        let reply = Reply::new(raw)?;
        let mut data = ptr::null();
        let mut size = 0;
        checked(unsafe {
            sd_bus_message_read_array(reply.0.as_ptr(), b'y' as c_char, &mut data, &mut size)
        })?;
        if size == 0 {
            return Ok([0; 16]);
        }
        if size != 16 || data.is_null() {
            return Err(invalid("invalid systemd invocation identity"));
        }
        let mut value = [0; 16];
        value.copy_from_slice(unsafe { std::slice::from_raw_parts(data.cast::<u8>(), size) });
        Ok(value)
    }
    fn snapshot(&self, path: &CStr) -> io::Result<Snapshot> {
        self.check_peer()?;
        let invocation = self.invocation(path)?;
        let state = self.string(path, UNIT, c"ActiveState")?;
        let value = Snapshot {
            invocation,
            state,
            main_pid: self.number(path, c"MainPID", false)?,
            exec_pid: self.number(path, c"ExecMainPID", false)?,
            code: self.number(path, c"ExecMainCode", true)? as i32,
            status: self.number(path, c"ExecMainStatus", true)? as i32,
            result: self.string(path, SERVICE, c"Result")?,
        };
        if value.invocation != self.invocation(path)? {
            return Err(invalid(
                "systemd invocation changed while reading its outcome",
            ));
        }
        Ok(value)
    }
    pub fn owner(&self) -> io::Result<Snapshot> {
        self.fixed_exec(
            OWNER,
            &[
                "/usr/lib/droidloom/production/current/droidloomd",
                "--socket",
                "/run/droidloom/control.sock",
            ],
        )?;
        if self.string(OWNER, SERVICE, c"Type")? != "exec"
            || self.string(OWNER, SERVICE, c"User")? != "root"
            || self.string(OWNER, SERVICE, c"Group")? != "root"
            || self.string(OWNER, SERVICE, c"Restart")? != "no"
            || self.string(OWNER, SERVICE, c"KillMode")? != "mixed"
            || !self.boolean(OWNER, c"NoNewPrivileges")?
            || self.security_context(OWNER, c"SELinuxContext")? != "u:r:droidloom_broker:s0"
            || self.security_context(OWNER, c"AppArmorProfile")? != "droidloom-production-broker"
        {
            return Err(invalid("original resource owner contract differs"));
        }
        self.snapshot(OWNER)
    }
    pub fn observer(&self) -> io::Result<Snapshot> {
        self.snapshot(OBSERVER)
    }
    pub fn verify_launcher(&self) -> io::Result<[u8; 16]> {
        self.verify_launcher_pid(unsafe { libc::getpid() } as u32)
    }
    pub fn verify_launcher_pid(&self, pid: u32) -> io::Result<[u8; 16]> {
        self.fixed_exec(
            LAUNCHER,
            &[
                "/usr/lib/droidloom/production/current/droidloomd",
                "--launch-early-instance",
            ],
        )?;
        let value = self.snapshot(LAUNCHER)?;
        if !value.live()
            || value.main_pid != pid
            || self.string(LAUNCHER, SERVICE, c"Type")? != "notify"
            || self.string(LAUNCHER, SERVICE, c"KillMode")? != "process"
            || self.string(LAUNCHER, SERVICE, c"Restart")? != "no"
            || !self.boolean(LAUNCHER, c"NoNewPrivileges")?
            || self.security_context(LAUNCHER, c"SELinuxContext")?
                != "u:r:droidloom_instance_launcher:s0"
            || self.security_context(LAUNCHER, c"AppArmorProfile")? != "droidloom-instance-launcher"
        {
            return Err(invalid(
                "this is not the fixed production instance launcher",
            ));
        }
        Ok(value.invocation)
    }
    pub fn ready(&self) -> io::Result<()> {
        self.verify_launcher()?;
        if std::env::var_os("NOTIFY_SOCKET").as_deref()
            != Some(std::ffi::OsStr::new("/run/systemd/notify"))
        {
            return Err(invalid(
                "launcher notification endpoint is not the original manager path",
            ));
        }
        if checked(unsafe {
            sd_notify(0, c"READY=1\nSTATUS=Original Android namespace created; resource owner may prepare it".as_ptr())
        })? != 1
        {
            return Err(invalid(
                "the original manager did not receive launcher readiness",
            ));
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn ended() -> Snapshot {
        Snapshot {
            invocation: [7; 16],
            state: "inactive".into(),
            main_pid: 0,
            exec_pid: 1234,
            code: 1,
            status: 0,
            result: "success".into(),
        }
    }
    #[test]
    fn retirement_requires_same_original_normal_exit() {
        let good = ended();
        assert!(good.clean_exit(&[7; 16], 1234).unwrap());
        assert!(good.clean_exit(&[8; 16], 1234).is_err());
        assert!(good.clean_exit(&[7; 16], 4321).is_err());
        for (code, status) in [(2, 15), (2, 9), (1, 1), (0, 0)] {
            let mut bad = good.clone();
            bad.code = code;
            bad.status = status;
            assert!(bad.clean_exit(&[7; 16], 1234).is_err());
        }
        let mut active = good.clone();
        active.state = "deactivating".into();
        active.main_pid = 1234;
        assert!(!active.clean_exit(&[7; 16], 1234).unwrap());
    }
}
