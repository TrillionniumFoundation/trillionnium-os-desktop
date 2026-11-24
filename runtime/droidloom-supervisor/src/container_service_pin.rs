//! Keep all three original systemd unit objects alive while a stop transaction
//! completes. Without RefUnit, successful inactive services may be collected
//! before the caller can read their original InvocationID and exit status.
use std::ffi::{CStr, CString, c_char, c_int, c_void};
use std::io;
use std::ptr::{self, NonNull};

#[repr(C)]
struct SdBus {
    _private: [u8; 0],
}
#[repr(C)]
struct SdMessage {
    _private: [u8; 0],
}

#[link(name = "libsystemd.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn sd_bus_new(bus: *mut *mut SdBus) -> c_int;
    fn sd_bus_close_unref(bus: *mut SdBus) -> *mut SdBus;
    fn sd_bus_set_address(bus: *mut SdBus, address: *const c_char) -> c_int;
    fn sd_bus_set_bus_client(bus: *mut SdBus, value: c_int) -> c_int;
    fn sd_bus_set_exit_on_disconnect(bus: *mut SdBus, value: c_int) -> c_int;
    fn sd_bus_set_method_call_timeout(bus: *mut SdBus, usec: u64) -> c_int;
    fn sd_bus_start(bus: *mut SdBus) -> c_int;
    fn sd_bus_message_new_method_call(
        bus: *mut SdBus,
        message: *mut *mut SdMessage,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
    ) -> c_int;
    fn sd_bus_message_append_basic(
        message: *mut SdMessage,
        kind: c_char,
        value: *const c_void,
    ) -> c_int;
    fn sd_bus_call(
        bus: *mut SdBus,
        message: *mut SdMessage,
        usec: u64,
        error: *mut c_void,
        reply: *mut *mut SdMessage,
    ) -> c_int;
    fn sd_bus_message_at_end(message: *mut SdMessage, complete: c_int) -> c_int;
    fn sd_bus_message_unref(message: *mut SdMessage) -> *mut SdMessage;
}

fn status(value: c_int) -> io::Result<()> {
    if value < 0 {
        Err(io::Error::from_raw_os_error(-value))
    } else {
        Ok(())
    }
}
struct Message(NonNull<SdMessage>);
impl Drop for Message {
    fn drop(&mut self) {
        unsafe {
            sd_bus_message_unref(self.0.as_ptr());
        }
    }
}
/// Held systemd unit references for an exact early shutdown transaction.
pub struct EarlyUnitReferences {
    bus: NonNull<SdBus>,
}
impl Drop for EarlyUnitReferences {
    fn drop(&mut self) {
        // The manager releases all references owned by this connection when it
        // disconnects. No unit start, stop, reset-failed or signal is sent here.
        unsafe {
            sd_bus_close_unref(self.bus.as_ptr());
        }
    }
}
impl EarlyUnitReferences {
    fn connect(address: &CStr) -> io::Result<Self> {
        let mut raw = ptr::null_mut();
        status(unsafe { sd_bus_new(&mut raw) })?;
        let bus = Self {
            bus: NonNull::new(raw)
                .ok_or_else(|| io::Error::other("systemd returned a null bus"))?,
        };
        status(unsafe { sd_bus_set_address(raw, address.as_ptr()) })?;
        status(unsafe { sd_bus_set_bus_client(raw, 1) })?;
        status(unsafe { sd_bus_set_exit_on_disconnect(raw, 0) })?;
        status(unsafe { sd_bus_set_method_call_timeout(raw, 5_000_000) })?;
        status(unsafe { sd_bus_start(raw) })?;
        Ok(bus)
    }
    fn reference(&self, name: &CStr) -> io::Result<()> {
        let mut raw = ptr::null_mut();
        status(unsafe {
            sd_bus_message_new_method_call(
                self.bus.as_ptr(),
                &mut raw,
                c"org.freedesktop.systemd1".as_ptr(),
                c"/org/freedesktop/systemd1".as_ptr(),
                c"org.freedesktop.systemd1.Manager".as_ptr(),
                c"RefUnit".as_ptr(),
            )
        })?;
        let request = Message(
            NonNull::new(raw).ok_or_else(|| io::Error::other("systemd returned a null request"))?,
        );
        status(unsafe {
            sd_bus_message_append_basic(request.0.as_ptr(), b's' as c_char, name.as_ptr().cast())
        })?;
        let mut raw_reply = ptr::null_mut();
        status(unsafe {
            sd_bus_call(
                self.bus.as_ptr(),
                request.0.as_ptr(),
                5_000_000,
                ptr::null_mut(),
                &mut raw_reply,
            )
        })?;
        let reply = Message(
            NonNull::new(raw_reply)
                .ok_or_else(|| io::Error::other("systemd returned a null reply"))?,
        );
        if unsafe { sd_bus_message_at_end(reply.0.as_ptr(), 1) } != 1 {
            return Err(io::Error::other("unexpected systemd RefUnit response"));
        }
        Ok(())
    }
    /// Pin the fixed original launcher, production owner and observer on the system bus.
    pub fn early() -> io::Result<Self> {
        // Never take a bus address or unit name from the environment, selected
        // release, command line or an Android reply.
        let held = Self::connect(c"unix:path=/run/dbus/system_bus_socket")?;
        for name in [
            "droidloom-instance-launcher.service",
            "droidloom-production.service",
            "droidloom-early-observer.service",
        ] {
            let name = CString::new(name).map_err(io::Error::other)?;
            held.reference(&name)?;
        }
        Ok(held)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::{
        collections::BTreeMap,
        fs,
        process::Command,
        time::{Duration, Instant, SystemTime, UNIX_EPOCH},
    };

    struct PrivateService {
        name: String,
        directory: std::path::PathBuf,
    }
    impl Drop for PrivateService {
        fn drop(&mut self) {
            let _ = Command::new("/usr/bin/systemctl")
                .args(["--user", "--no-ask-password", "stop", &self.name])
                .output();
            let _ = fs::remove_dir_all(&self.directory);
        }
    }
    fn checked(command: &mut Command) -> String {
        let output = command.output().unwrap();
        assert!(
            output.status.success(),
            "{command:?}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8(output.stdout).unwrap()
    }
    fn properties(name: &str) -> BTreeMap<String, String> {
        checked(Command::new("/usr/bin/systemctl").args([
            "--user","show","--property=LoadState,InvocationID,ExecMainPID,ExecMainCode,ExecMainStatus,ActiveState,Result",name]))
            .lines().map(|line| { let (k,v)=line.split_once('=').unwrap(); (k.to_owned(),v.to_owned()) }).collect()
    }

    #[test]
    #[ignore = "requires a real user systemd manager and creates one bounded disposable service"]
    fn actual_manager_retains_original_exit_until_reference_connection_closes() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let directory =
            std::env::temp_dir().join(format!("droidloom-unit-ref-{}-{stamp}", std::process::id()));
        fs::create_dir(&directory).unwrap();
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
        let service = PrivateService {
            name: format!("droidloom-unit-ref-{}-{stamp}.service", std::process::id()),
            directory,
        };
        let ready = service.directory.join("ready");
        let script = "import signal,sys,time;from pathlib import Path;signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));Path(sys.argv[1]).write_text('ready');\nwhile True:time.sleep(1)";
        checked(
            Command::new("/usr/bin/systemd-run")
                .args([
                    "--user",
                    &format!("--unit={}", service.name),
                    "--property=Type=exec",
                    "--property=KillMode=mixed",
                    "--property=Restart=no",
                    "--property=TimeoutStopSec=3s",
                    "--property=RuntimeMaxSec=15s",
                    "/usr/bin/python3",
                    "-c",
                    script,
                ])
                .arg(&ready),
        );
        let until = Instant::now() + Duration::from_secs(5);
        while !ready.exists() {
            assert!(Instant::now() < until, "test process did not become ready");
            std::thread::sleep(Duration::from_millis(20));
        }
        let runtime = std::env::var("XDG_RUNTIME_DIR").unwrap();
        let address = CString::new(format!("unix:path={runtime}/bus")).unwrap();
        let held = EarlyUnitReferences::connect(&address).unwrap();
        held.reference(&CString::new(service.name.clone()).unwrap())
            .unwrap();
        let before = properties(&service.name);
        assert_eq!(before["ActiveState"], "active");
        assert!(!before["InvocationID"].is_empty());
        checked(Command::new("/usr/bin/systemctl").args([
            "--user",
            "--job-mode=fail",
            "stop",
            &service.name,
        ]));
        let after = properties(&service.name);
        assert_eq!(after["LoadState"], "loaded");
        assert_eq!(after["ActiveState"], "inactive");
        assert_eq!(after["InvocationID"], before["InvocationID"]);
        assert_eq!(after["ExecMainPID"], before["ExecMainPID"]);
        assert_eq!(after["ExecMainCode"], "1");
        assert_eq!(after["ExecMainStatus"], "0");
        assert_eq!(after["Result"], "success");
        println!(
            "held original invocation {} and normal exit 0",
            after["InvocationID"]
        );
        drop(held);
        let until = Instant::now() + Duration::from_secs(5);
        loop {
            if properties(&service.name)["LoadState"] == "not-found" {
                break;
            }
            assert!(
                Instant::now() < until,
                "test unit reference was not released"
            );
            std::thread::sleep(Duration::from_millis(20));
        }
        println!("released own connection and observed disposable unit collection");
    }
    #[test]
    #[ignore = "requires a real user systemd manager and creates three bounded disposable services"]
    fn actual_manager_restarts_three_retained_service_generations() {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let prefix = format!("droidloom-instance-ref-{}-{stamp}", std::process::id());
        let services: Vec<_> = ["launcher", "owner", "observer"]
            .into_iter()
            .map(|role| {
                let directory = std::env::temp_dir().join(format!("{prefix}-{role}"));
                fs::create_dir(&directory).unwrap();
                fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
                PrivateService {
                    name: format!("{prefix}-{role}.service"),
                    directory,
                }
            })
            .collect();
        let script = "import signal,sys,time;from pathlib import Path;signal.signal(signal.SIGTERM,lambda *_:sys.exit(0));Path(sys.argv[1]).write_text('ready');\nwhile True:time.sleep(1)";
        for (index, service) in services.iter().enumerate() {
            let mut command = Command::new("/usr/bin/systemd-run");
            command.args([
                "--user",
                &format!("--unit={}", service.name),
                "--property=Type=exec",
                "--property=KillMode=process",
                "--property=Restart=no",
                "--property=TimeoutStopSec=3s",
                "--property=RuntimeMaxSec=30s",
                "--property=SendSIGKILL=no",
            ]);
            match index {
                0 => {
                    command.arg(format!("--property=PartOf={}", services[1].name));
                }
                1 => {
                    command.arg(format!("--property=Requires={}", services[0].name));
                    command.arg(format!("--property=After={}", services[0].name));
                    command.arg(format!("--property=BindsTo={}", services[0].name));
                }
                2 => {
                    command.arg(format!("--property=Requires={}", services[1].name));
                    command.arg(format!("--property=After={}", services[1].name));
                    command.arg(format!("--property=BindsTo={}", services[1].name));
                }
                _ => unreachable!(),
            }
            checked(
                command
                    .args(["/usr/bin/python3", "-c", script])
                    .arg(service.directory.join("ready")),
            );
        }
        let wait_ready = || {
            let until = Instant::now() + Duration::from_secs(5);
            while services.iter().any(|s| !s.directory.join("ready").exists()) {
                assert!(
                    Instant::now() < until,
                    "test service group did not become ready"
                );
                std::thread::sleep(Duration::from_millis(20));
            }
        };
        wait_ready();
        let runtime = std::env::var("XDG_RUNTIME_DIR").unwrap();
        let address = CString::new(format!("unix:path={runtime}/bus")).unwrap();
        let held = EarlyUnitReferences::connect(&address).unwrap();
        for service in &services {
            held.reference(&CString::new(service.name.clone()).unwrap())
                .unwrap();
        }
        let before: Vec<_> = services.iter().map(|s| properties(&s.name)).collect();
        for unit in &before {
            assert_eq!(unit["ActiveState"], "active");
            assert_eq!(unit["InvocationID"].len(), 32);
            assert!(unit["ExecMainPID"].parse::<u32>().unwrap() > 1);
        }
        let stop_and_check = |original: &[BTreeMap<String, String>]| {
            checked(Command::new("/usr/bin/systemctl").args([
                "--user",
                "--job-mode=fail",
                "stop",
                &services[1].name,
            ]));
            let until = Instant::now() + Duration::from_secs(5);
            loop {
                let stopped: Vec<_> = services.iter().map(|s| properties(&s.name)).collect();
                if stopped.iter().all(|s| s["ActiveState"] == "inactive") {
                    for (unit, old) in stopped.iter().zip(original) {
                        assert_eq!(unit["LoadState"], "loaded");
                        assert_eq!(unit["InvocationID"], old["InvocationID"]);
                        assert_eq!(unit["ExecMainPID"], old["ExecMainPID"]);
                        assert_eq!(unit["ExecMainCode"], "1");
                        assert_eq!(unit["ExecMainStatus"], "0");
                        assert_eq!(unit["Result"], "success");
                    }
                    break;
                }
                assert!(
                    Instant::now() < until,
                    "complete service group did not retire"
                );
                std::thread::sleep(Duration::from_millis(20));
            }
        };
        stop_and_check(&before);
        for service in &services {
            fs::remove_file(service.directory.join("ready")).unwrap();
        }
        checked(Command::new("/usr/bin/systemctl").args([
            "--user",
            "--job-mode=fail",
            "start",
            &services[2].name,
        ]));
        wait_ready();
        let after: Vec<_> = services.iter().map(|s| properties(&s.name)).collect();
        for (unit, old) in after.iter().zip(&before) {
            assert_eq!(unit["ActiveState"], "active");
            assert_eq!(unit["InvocationID"].len(), 32);
            assert_ne!(unit["InvocationID"], old["InvocationID"]);
            assert!(unit["ExecMainPID"].parse::<u32>().unwrap() > 1);
        }
        stop_and_check(&after);
        println!("observed two complete normal retirements and three fresh invocation IDs");
        drop(held);
    }
}
