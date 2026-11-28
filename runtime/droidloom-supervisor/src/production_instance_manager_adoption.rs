//! Original system-manager evidence for the boot factory's one-time adoption.
use super::*;
use std::fs::File;
use std::io::Read;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};

const FACTORY: &CStr = c"/org/freedesktop/systemd1/unit/droidloom_2dinstance_2dfactory_2eservice";
const FACTORY_NAME: &CStr = c"droidloom-instance-factory.service";
const FACTORY_CGROUP: &str = "/system.slice/droidloom-instance-factory.service";
const UNIT_FILE: &str = "/etc/systemd/system/droidloom-instance-factory.service";
const UNIT_BYTES: &[u8] = include_bytes!("droidloom-instance-factory.service");

#[link(name = "libsystemd.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn sd_pid_notify_with_fds(
        pid: libc::pid_t,
        unset_environment: c_int,
        state: *const c_char,
        fds: *const c_int,
        n_fds: u32,
    ) -> c_int;
}
fn original_unit_file() -> io::Result<()> {
    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(UNIT_FILE)?;
    let original = file.metadata()?;
    if !original.is_file()
        || original.uid() != 0
        || original.gid() != 0
        || original.mode() & 0o7777 != 0o644
        || original.nlink() != 1
        || original.len() != UNIT_BYTES.len() as u64
    {
        return Err(invalid("factory service is not its original source unit"));
    }
    let mut contents = Vec::new();
    file.take(16 * 1024 + 1).read_to_end(&mut contents)?;
    let current = std::fs::symlink_metadata(UNIT_FILE)?;
    if contents != UNIT_BYTES
        || current.file_type().is_symlink()
        || (current.dev(), current.ino()) != (original.dev(), original.ino())
        || current.uid() != 0
        || current.gid() != 0
        || current.mode() & 0o7777 != 0o644
        || current.nlink() != 1
    {
        return Err(invalid("factory service source changed during admission"));
    }
    Ok(())
}
impl Manager {
    pub fn acquire_factory() -> io::Result<Self> {
        let manager = Self::acquire()?;
        manager.reference(FACTORY_NAME)?;
        Ok(manager)
    }
    fn factory_has_no_dropins(&self) -> io::Result<()> {
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_get_property(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                FACTORY.as_ptr(),
                UNIT.as_ptr(),
                c"DropInPaths".as_ptr(),
                ptr::null_mut(),
                &mut raw,
                c"as".as_ptr(),
            )
        })?;
        let reply = Reply::new(raw)?;
        if checked(unsafe {
            sd_bus_message_enter_container(reply.0.as_ptr(), b'a' as c_char, c"s".as_ptr())
        })? != 1
            || unsafe { sd_bus_message_at_end(reply.0.as_ptr(), 0) } != 1
        {
            return Err(invalid("factory service has an additional unit drop-in"));
        }
        checked(unsafe { sd_bus_message_exit_container(reply.0.as_ptr()) })?;
        if unsafe { sd_bus_message_at_end(reply.0.as_ptr(), 1) } != 1 {
            return Err(invalid("ambiguous factory service drop-in list"));
        }
        Ok(())
    }
    fn factory_needs_reload(&self) -> io::Result<bool> {
        let mut value = 0i32;
        checked(unsafe {
            sd_bus_get_property_trivial(
                self.bus.as_ptr(),
                DEST.as_ptr(),
                FACTORY.as_ptr(),
                UNIT.as_ptr(),
                c"NeedDaemonReload".as_ptr(),
                ptr::null_mut(),
                b'b' as c_char,
                (&mut value as *mut i32).cast(),
            )
        })?;
        match value {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(invalid("invalid factory reload property")),
        }
    }
    pub fn factory_state(&self) -> io::Result<Snapshot> {
        self.check_peer()?;
        original_unit_file()?;
        self.factory_has_no_dropins()?;
        self.fixed_exec(
            FACTORY,
            &[
                "/usr/lib/droidloom/production/current/droidloomd",
                "--adopt-early-factory",
            ],
        )?;
        if self.factory_needs_reload()?
            || self.string(FACTORY, UNIT, c"FragmentPath")? != UNIT_FILE
            || self.string(FACTORY, UNIT, c"ControlGroup")? != FACTORY_CGROUP
            || self.string(FACTORY, SERVICE, c"Type")? != "notify"
            || self.string(FACTORY, SERVICE, c"NotifyAccess")? != "main"
            || self.string(FACTORY, SERVICE, c"User")? != "root"
            || self.string(FACTORY, SERVICE, c"Group")? != "root"
            || self.string(FACTORY, SERVICE, c"StandardInput")? != "null"
            || self.string(FACTORY, SERVICE, c"StandardOutput")? != "file"
            || self.string(FACTORY, SERVICE, c"StandardError")? != "journal"
            || self.string(FACTORY, SERVICE, c"Restart")? != "no"
            || self.string(FACTORY, SERVICE, c"KillMode")? != "process"
            || self.boolean(FACTORY, c"SendSIGKILL")?
            || !self.boolean(FACTORY, c"NoNewPrivileges")?
            || self.security_context(FACTORY, c"SELinuxContext")?
                != "u:r:droidloom_instance_launcher:s0"
            || self.security_context(FACTORY, c"AppArmorProfile")? != "droidloom-instance-launcher"
        {
            return Err(invalid("fixed factory service contract differs"));
        }
        self.snapshot(FACTORY)
    }
    pub fn verify_factory_adopter(&self, pid: u32) -> io::Result<[u8; 16]> {
        let state = self.factory_state()?;
        if !state.live()
            || state.state != "activating"
            || state.main_pid != pid
            || state.exec_pid != pid
        {
            return Err(invalid(
                "original factory adopter is not this service MainPID",
            ));
        }
        Ok(state.invocation)
    }
    /// This is systemd 259's actual h -> osay API. The manager resolves the
    /// held PIDFD, returns the original unit invocation, then pidref_verify()s.
    /// Numeric PID lookup never replaces the caller's retained original handle.
    pub fn verify_factory_membership(&self, pidfd: &File, invocation: &[u8; 16]) -> io::Result<()> {
        self.check_peer()?;
        if invocation == &[0; 16] {
            return Err(invalid("factory invocation is absent"));
        }
        let mut raw = ptr::null_mut();
        checked(unsafe {
            sd_bus_message_new_method_call(
                self.bus.as_ptr(),
                &mut raw,
                DEST.as_ptr(),
                MANAGER.as_ptr(),
                c"org.freedesktop.systemd1.Manager".as_ptr(),
                c"GetUnitByPIDFD".as_ptr(),
            )
        })?;
        let request = Reply::new(raw)?;
        let fd = pidfd.as_raw_fd();
        checked(unsafe {
            sd_bus_message_append_basic(
                request.0.as_ptr(),
                b'h' as c_char,
                (&fd as *const i32).cast(),
            )
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
        let m = response.0.as_ptr();
        for (kind, expected) in [(b'o', FACTORY), (b's', FACTORY_NAME)] {
            let mut value: *const c_char = ptr::null();
            if checked(unsafe {
                sd_bus_message_read_basic(
                    m,
                    kind as c_char,
                    (&mut value as *mut *const c_char).cast(),
                )
            })? != 1
                || value.is_null()
                || unsafe { CStr::from_ptr(value) } != expected
            {
                return Err(invalid("original PIDFD is outside the fixed factory unit"));
            }
        }
        let mut data = ptr::null();
        let mut size = 0;
        checked(unsafe { sd_bus_message_read_array(m, b'y' as c_char, &mut data, &mut size) })?;
        if size != 16
            || data.is_null()
            || unsafe { std::slice::from_raw_parts(data.cast::<u8>(), size) } != invocation
            || unsafe { sd_bus_message_at_end(m, 1) } != 1
            || self.invocation(FACTORY)? != *invocation
        {
            return Err(invalid(
                "original PIDFD belongs to a different factory invocation",
            ));
        }
        self.check_peer()
    }
    pub fn verify_factory_main(&self, pid: u32, invocation: &[u8; 16]) -> io::Result<()> {
        let state = self.factory_state()?;
        if !state.live()
            || state.state != "active"
            || state.main_pid != pid
            || state.invocation != *invocation
        {
            return Err(invalid(
                "original boot factory is not the active service MainPID",
            ));
        }
        Ok(())
    }
    pub fn notify_factory_main(
        &self,
        adopter: u32,
        factory: &File,
        invocation: &[u8; 16],
    ) -> io::Result<()> {
        if self.verify_factory_adopter(adopter)? != *invocation {
            return Err(invalid(
                "factory adopter invocation changed before notification",
            ));
        }
        self.verify_factory_membership(factory, invocation)?;
        if std::env::var_os("NOTIFY_SOCKET").as_deref()
            != Some(std::ffi::OsStr::new("/run/systemd/notify"))
        {
            return Err(invalid(
                "factory notification endpoint is not original Linux PID 1",
            ));
        }
        let fd = factory.as_raw_fd();
        // systemd authorizes the original sender first, takes the one live
        // MainPIDFD, and only then processes READY in this same message.
        if checked(unsafe {
            sd_pid_notify_with_fds(
                0,
                0,
                c"MAINPIDFD=1\nREADY=1\nSTATUS=Original boot factory adopted in its permanent service".as_ptr(),
                &fd,
                1,
            )
        })? != 1
        {
            return Err(invalid("factory adoption notification was not sent"));
        }
        Ok(())
    }
}
