//! Fixed early-service stop jobs on the already authenticated manager socket.
//! The only mutating call is StopUnit for this source-owned finite enum.
//! Private connections receive manager signals without Subscribe or RefUnit;
//! those unrelated methods require broader systemd authorization.
use super::*;
use std::cell::{Cell, RefCell};
use std::mem::ManuallyDrop;
use std::time::Duration;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(in super::super) enum EarlyActor {
    Factory,
    Launcher,
    Observer,
    #[cfg(test)]
    TestFactory,
    #[cfg(test)]
    TestLauncher,
    #[cfg(test)]
    TestObserver,
}
impl EarlyActor {
    pub(in super::super) fn name(self) -> &'static CStr {
        match self {
            Self::Factory => c"droidloom-instance-factory.service",
            Self::Launcher => c"droidloom-instance-launcher.service",
            Self::Observer => c"droidloom-early-observer.service",
            #[cfg(test)]
            Self::TestFactory => c"droidloom-ff1d-test-package-factory.service",
            #[cfg(test)]
            Self::TestLauncher => c"droidloom-ff1d-test-package-launcher.service",
            #[cfg(test)]
            Self::TestObserver => c"droidloom-ff1d-test-package-observer.service",
        }
    }
    pub(in super::super) fn text(self) -> &'static str {
        self.name().to_str().expect("fixed ASCII unit name")
    }
    pub(in super::super) fn path(self) -> &'static str {
        match self {
            Self::Factory => {
                "/org/freedesktop/systemd1/unit/droidloom_2dinstance_2dfactory_2eservice"
            }
            Self::Launcher => {
                "/org/freedesktop/systemd1/unit/droidloom_2dinstance_2dlauncher_2eservice"
            }
            Self::Observer => {
                "/org/freedesktop/systemd1/unit/droidloom_2dearly_2dobserver_2eservice"
            }
            #[cfg(test)]
            Self::TestFactory => {
                "/org/freedesktop/systemd1/unit/droidloom_2dff1d_2dtest_2dpackage_2dfactory_2eservice"
            }
            #[cfg(test)]
            Self::TestLauncher => {
                "/org/freedesktop/systemd1/unit/droidloom_2dff1d_2dtest_2dpackage_2dlauncher_2eservice"
            }
            #[cfg(test)]
            Self::TestObserver => {
                "/org/freedesktop/systemd1/unit/droidloom_2dff1d_2dtest_2dpackage_2dobserver_2eservice"
            }
        }
    }
    pub(in super::super) fn production(self) -> Self {
        #[cfg(test)]
        match self {
            Self::TestFactory => return Self::Factory,
            Self::TestLauncher => return Self::Launcher,
            Self::TestObserver => return Self::Observer,
            _ => {}
        }
        self
    }
    fn recognized(name: &str) -> bool {
        if [Self::Factory, Self::Launcher, Self::Observer]
            .iter()
            .any(|v| v.text() == name)
        {
            return true;
        }
        #[cfg(test)]
        if [Self::TestFactory, Self::TestLauncher, Self::TestObserver]
            .iter()
            .any(|v| v.text() == name)
        {
            return true;
        }
        false
    }
}

#[repr(C)]
struct SdSlot {
    _private: [u8; 0],
}
unsafe extern "C" {
    fn sd_bus_match_signal(
        bus: *mut SdBus,
        slot: *mut *mut SdSlot,
        sender: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
        callback: Option<unsafe extern "C" fn(*mut SdMessage, *mut c_void, *mut c_void) -> c_int>,
        userdata: *mut c_void,
    ) -> c_int;
    fn sd_bus_slot_unref(slot: *mut SdSlot) -> *mut SdSlot;
    fn sd_bus_process(bus: *mut SdBus, message: *mut *mut SdMessage) -> c_int;
    fn sd_bus_wait(bus: *mut SdBus, usec: u64) -> c_int;
}

#[derive(Debug, Clone, Eq, PartialEq)]
struct Removed {
    id: u32,
    path: String,
    unit: String,
    result: String,
}
impl Removed {
    fn parse(message: *mut SdMessage) -> Result<Self> {
        let pointer =
            NonNull::new(message).ok_or(CgroupError::Rejected("null manager job signal"))?;
        // The callback borrows the message. It must never unref sd-bus's owner.
        let mut message = ManuallyDrop::new(Message(pointer));
        message.signature("uoss")?;
        let value = Self {
            id: message.basic(b'u')?,
            path: message.string(b'o')?,
            unit: message.string(b's')?,
            result: message.string(b's')?,
        };
        message.end()?;
        require(
            value.id > 0 && value.path == format!("/org/freedesktop/systemd1/job/{}", value.id),
            "manager job signal has inconsistent original job identity",
        )?;
        Ok(value)
    }
}

#[derive(Default)]
struct Events {
    rows: RefCell<Vec<Removed>>,
    failed: Cell<bool>,
}
unsafe extern "C" fn removed(
    message: *mut SdMessage,
    userdata: *mut c_void,
    _error: *mut c_void,
) -> c_int {
    if userdata.is_null() {
        return -libc::EINVAL;
    }
    let events = unsafe { &*(userdata.cast::<Events>()) };
    match Removed::parse(message) {
        Ok(value) if EarlyActor::recognized(&value.unit) => {
            let mut rows = events.rows.borrow_mut();
            if rows.len() >= 32 || rows.iter().any(|row| row.id == value.id) {
                events.failed.set(true);
            } else {
                rows.push(value);
            }
        }
        Ok(_) => {}
        Err(_) => events.failed.set(true),
    }
    1
}

pub(in super::super) struct CompletedStop {
    actor: EarlyActor,
    id: u32,
    path: String,
}
impl CompletedStop {
    pub(in super::super) fn verifies(&self, actor: EarlyActor) -> bool {
        self.actor == actor
            && self.id > 0
            && self.path == format!("/org/freedesktop/systemd1/job/{}", self.id)
    }
}

pub(in super::super) struct PackageJobs<'a> {
    bus: &'a PrivateBus,
    slot: NonNull<SdSlot>,
    events: Box<Events>,
}
impl Drop for PackageJobs<'_> {
    fn drop(&mut self) {
        // The held private manager connection is already subscribed by systemd.
        // Drop cannot start/stop a unit, signal a process, or grant retirement.
        unsafe {
            sd_bus_slot_unref(self.slot.as_ptr());
        }
    }
}

#[repr(C)]
struct BusError {
    name: *const c_char,
    message: *const c_char,
    need_free: c_int,
}
unsafe extern "C" {
    fn sd_bus_error_free(error: *mut BusError) -> *mut BusError;
}
impl Default for BusError {
    fn default() -> Self {
        Self {
            name: ptr::null(),
            message: ptr::null(),
            need_free: 0,
        }
    }
}
impl Drop for BusError {
    fn drop(&mut self) {
        unsafe {
            sd_bus_error_free(self);
        }
    }
}

impl PrivateBus {
    pub(in super::super) fn actor_is_loaded(
        &self,
        actor: EarlyActor,
        deadline: Instant,
    ) -> Result<bool> {
        let request = self.request(
            c"/org/freedesktop/systemd1",
            c"org.freedesktop.systemd1.Manager",
            c"GetUnit",
        )?;
        status(unsafe {
            sd_bus_message_append_basic(
                request.0.as_ptr(),
                b's' as c_char,
                actor.name().as_ptr().cast(),
            )
        })?;
        let mut error = BusError::default();
        let mut reply = ptr::null_mut();
        let code = unsafe {
            sd_bus_call(
                self.bus.as_ptr(),
                request.0.as_ptr(),
                remaining(deadline)?,
                (&mut error as *mut BusError).cast(),
                &mut reply,
            )
        };
        let reply = NonNull::new(reply).map(Message);
        remaining(deadline)?;
        if code < 0
            && !error.name.is_null()
            && text(error.name, 256)? == "org.freedesktop.systemd1.NoSuchUnit"
        {
            return Ok(false);
        }
        status(code)?;
        let mut reply = reply.ok_or(CgroupError::Rejected("GetUnit reply is absent"))?;
        reply.signature("o")?;
        require(
            reply.string(b'o')? == actor.path(),
            "GetUnit returned a different fixed actor object",
        )?;
        reply.end()?;
        Ok(true)
    }
    pub(in super::super) fn package_jobs(&self, deadline: Instant) -> Result<PackageJobs<'_>> {
        remaining(deadline)?;
        let mut events = Box::<Events>::default();
        let mut slot = ptr::null_mut();
        status(unsafe {
            sd_bus_match_signal(
                self.bus.as_ptr(),
                &mut slot,
                ptr::null(),
                c"/org/freedesktop/systemd1".as_ptr(),
                c"org.freedesktop.systemd1.Manager".as_ptr(),
                c"JobRemoved".as_ptr(),
                Some(removed),
                (&mut *events as *mut Events).cast(),
            )
        })?;
        let value = PackageJobs {
            bus: self,
            slot: NonNull::new(slot)
                .ok_or(CgroupError::Rejected("manager job subscription is null"))?,
            events,
        };
        remaining(deadline)?;
        Ok(value)
    }
}

fn completed(actor: EarlyActor, id: u32, path: &str, value: &Removed) -> Result<CompletedStop> {
    require(
        value.id == id
            && value.path == path
            && value.unit == actor.text()
            && value.result == "done",
        "original manager stop job did not complete normally",
    )?;
    Ok(CompletedStop {
        actor,
        id,
        path: path.into(),
    })
}
impl PackageJobs<'_> {
    pub(in super::super) fn stop(
        &self,
        actor: EarlyActor,
        deadline: Instant,
        progress: &impl Fn() -> Result<()>,
    ) -> Result<CompletedStop> {
        progress()?;
        remaining(deadline)?;
        let request = self.bus.request(
            c"/org/freedesktop/systemd1",
            c"org.freedesktop.systemd1.Manager",
            c"StopUnit",
        )?;
        for text in [actor.name(), c"fail"] {
            status(unsafe {
                sd_bus_message_append_basic(
                    request.0.as_ptr(),
                    b's' as c_char,
                    text.as_ptr().cast(),
                )
            })?;
        }
        // The match is installed before this call; even a no-op stop can emit
        // JobRemoved before the method reply. Its genuine signal is retained.
        let mut reply = self.bus.call(request, deadline)?;
        reply.signature("o")?;
        let path = reply.string(b'o')?;
        reply.end()?;
        let id = path
            .strip_prefix("/org/freedesktop/systemd1/job/")
            .and_then(|id| id.parse::<u32>().ok())
            .filter(|id| *id > 0 && path == format!("/org/freedesktop/systemd1/job/{id}"))
            .ok_or(CgroupError::Rejected("noncanonical returned stop job"))?;
        loop {
            progress()?;
            remaining(deadline)?;
            require(
                !self.events.failed.get(),
                "malformed or excessive manager job signals",
            )?;
            let observed_index = self.events.rows.borrow().iter().position(|v| v.id == id);
            if let Some(value) = observed_index {
                let observed = self.events.rows.borrow_mut().remove(value);
                return completed(actor, id, &path, &observed);
            }
            let processed = unsafe { sd_bus_process(self.bus.bus.as_ptr(), ptr::null_mut()) };
            match status(processed) {
                Err(CgroupError::Io(error)) if error.kind() == io::ErrorKind::Interrupted => {
                    continue;
                }
                Err(error) => return Err(error),
                Ok(0) => {
                    let tick = deadline.min(Instant::now() + Duration::from_millis(100));
                    match status(unsafe { sd_bus_wait(self.bus.bus.as_ptr(), remaining(tick)?) }) {
                        Err(CgroupError::Io(error))
                            if error.kind() == io::ErrorKind::Interrupted => {}
                        Err(error) => return Err(error),
                        Ok(_) => {}
                    }
                }
                Ok(_) => {}
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_the_exact_completed_original_job_is_accepted() {
        let actor = EarlyActor::Factory;
        let row = Removed {
            id: 7,
            path: "/org/freedesktop/systemd1/job/7".into(),
            unit: actor.text().into(),
            result: "done".into(),
        };
        assert!(
            completed(actor, 7, &row.path, &row)
                .unwrap()
                .verifies(actor)
        );
        for result in ["canceled", "timeout", "failed", "dependency", "skipped", ""] {
            assert!(
                completed(
                    actor,
                    7,
                    &row.path,
                    &Removed {
                        result: result.into(),
                        ..row.clone()
                    }
                )
                .is_err()
            );
        }
        assert!(completed(EarlyActor::Launcher, 7, &row.path, &row).is_err());
        assert!(completed(actor, 8, &row.path, &row).is_err());
        assert!(completed(actor, 7, "/org/freedesktop/systemd1/job/8", &row).is_err());
    }
}
