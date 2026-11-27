//! Reused fixed read-only systemd FD decoder for owned application units.
//! Derived from exact production_unit_bus.rs SHA256 2b9174e372bf85c530ae3c45d27657cdfb9f1a64463c9dd4637f82f66ca07639.
//! The production endpoint and HostPeerIssuer remain unchanged.
use super::*;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{c_char, c_int, c_void};
use std::ptr::{self, NonNull};
use std::time::Instant;

#[repr(C)]
struct SdBus {
    _private: [u8; 0],
}
#[repr(C)]
struct SdMessage {
    _private: [u8; 0],
}

// Missing stable systemd SONAME/ABI is a build/install failure. There is no
// arbitrary command or numeric-PID fallback in this provider.
#[link(name = "libsystemd.so.0", kind = "dylib", modifiers = "+verbatim")]
unsafe extern "C" {
    fn sd_bus_new(bus: *mut *mut SdBus) -> c_int;
    fn sd_bus_unref(bus: *mut SdBus) -> *mut SdBus;
    fn sd_bus_set_fd(bus: *mut SdBus, input: c_int, output: c_int) -> c_int;
    fn sd_bus_set_bus_client(bus: *mut SdBus, value: c_int) -> c_int;
    fn sd_bus_set_exit_on_disconnect(bus: *mut SdBus, value: c_int) -> c_int;
    fn sd_bus_negotiate_fds(bus: *mut SdBus, value: c_int) -> c_int;
    fn sd_bus_start(bus: *mut SdBus) -> c_int;
    fn sd_bus_message_new_method_call(
        bus: *mut SdBus,
        message: *mut *mut SdMessage,
        destination: *const c_char,
        path: *const c_char,
        interface: *const c_char,
        member: *const c_char,
    ) -> c_int;
    fn sd_bus_message_unref(message: *mut SdMessage) -> *mut SdMessage;
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
    fn sd_bus_message_get_signature(message: *mut SdMessage, complete: c_int) -> *const c_char;
    fn sd_bus_message_read_basic(
        message: *mut SdMessage,
        kind: c_char,
        value: *mut c_void,
    ) -> c_int;
    fn sd_bus_message_read_array(
        message: *mut SdMessage,
        kind: c_char,
        value: *mut *const c_void,
        bytes: *mut usize,
    ) -> c_int;
    fn sd_bus_message_enter_container(
        message: *mut SdMessage,
        kind: c_char,
        contents: *const c_char,
    ) -> c_int;
    fn sd_bus_message_exit_container(message: *mut SdMessage) -> c_int;
    fn sd_bus_message_at_end(message: *mut SdMessage, complete: c_int) -> c_int;
    fn sd_bus_message_skip(message: *mut SdMessage, signature: *const c_char) -> c_int;
}

fn status(value: c_int) -> Result<c_int> {
    if value < 0 {
        Err(io::Error::from_raw_os_error(-value).into())
    } else {
        Ok(value)
    }
}
fn remaining(deadline: Instant) -> Result<u64> {
    let duration = deadline
        .checked_duration_since(Instant::now())
        .ok_or_else(|| io::Error::from_raw_os_error(libc::ETIMEDOUT))?;
    let micros =
        u64::try_from(duration.as_micros()).map_err(|_| invalid("systemd deadline overflow"))?;
    if micros == 0 {
        return Err(io::Error::from_raw_os_error(libc::ETIMEDOUT).into());
    }
    Ok(micros)
}

fn text(pointer: *const c_char, maximum: usize) -> Result<String> {
    require(!pointer.is_null(), "null fixed manager reply string")?;
    let mut size = 0;
    while size <= maximum && unsafe { *pointer.add(size) } != 0 {
        size += 1;
    }
    require(size <= maximum, "fixed manager reply string exceeds bound")?;
    let bytes = unsafe { std::slice::from_raw_parts(pointer.cast::<u8>(), size) };
    String::from_utf8(bytes.to_vec()).map_err(|_| invalid("non-UTF8 manager reply"))
}

struct Message(NonNull<SdMessage>);
impl Drop for Message {
    fn drop(&mut self) {
        unsafe {
            sd_bus_message_unref(self.0.as_ptr());
        }
    }
}
impl Message {
    fn signature(&self, expected: &str) -> Result<()> {
        require(
            text(
                unsafe { sd_bus_message_get_signature(self.0.as_ptr(), 1) },
                128,
            )? == expected,
            "fixed manager reply has another complete signature",
        )
    }
    fn basic<T: Default>(&mut self, kind: u8) -> Result<T> {
        let mut value = T::default();
        require(
            status(unsafe {
                sd_bus_message_read_basic(
                    self.0.as_ptr(),
                    kind as c_char,
                    (&mut value as *mut T).cast(),
                )
            })? > 0,
            "missing typed manager value",
        )?;
        Ok(value)
    }
    fn string(&mut self, kind: u8) -> Result<String> {
        text(self.basic::<*const c_char>(kind)?, 4096)
    }
    fn boolean(&mut self) -> Result<bool> {
        match self.basic::<c_int>(b'b')? {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(invalid("noncanonical manager boolean")),
        }
    }
    fn enter(&mut self, kind: u8, signature: &CStr) -> Result<bool> {
        Ok(status(unsafe {
            sd_bus_message_enter_container(self.0.as_ptr(), kind as c_char, signature.as_ptr())
        })? > 0)
    }
    fn exit(&mut self) -> Result<()> {
        require(
            status(unsafe { sd_bus_message_at_end(self.0.as_ptr(), 0) })? > 0,
            "unexpected remaining manager container value",
        )?;
        status(unsafe { sd_bus_message_exit_container(self.0.as_ptr()) })?;
        Ok(())
    }
    fn end(&self) -> Result<()> {
        require(
            status(unsafe { sd_bus_message_at_end(self.0.as_ptr(), 1) })? > 0,
            "unexpected trailing manager reply value",
        )
    }
    fn bytes(&mut self) -> Result<Vec<u8>> {
        let mut pointer = ptr::null();
        let mut size = 0;
        require(
            status(unsafe {
                sd_bus_message_read_array(self.0.as_ptr(), b'y' as c_char, &mut pointer, &mut size)
            })? > 0,
            "missing manager byte array",
        )?;
        require(
            size <= 4096 && (size == 0 || !pointer.is_null()),
            "manager byte array bound",
        )?;
        if size == 0 {
            return Ok(Vec::new());
        }
        Ok(unsafe { std::slice::from_raw_parts(pointer.cast::<u8>(), size) }.to_vec())
    }
    fn strings(&mut self) -> Result<Vec<String>> {
        require(self.enter(b'a', c"s")?, "missing manager string array")?;
        let mut values = Vec::new();
        while status(unsafe { sd_bus_message_at_end(self.0.as_ptr(), 0) })? == 0 {
            require(values.len() < 64, "manager string array bound")?;
            values.push(self.string(b's')?);
        }
        self.exit()?;
        Ok(values)
    }
}

pub(super) struct PrivateBus {
    bus: NonNull<SdBus>,
    _thread_bound: PhantomData<Rc<()>>,
}
impl Drop for PrivateBus {
    fn drop(&mut self) {
        unsafe {
            sd_bus_unref(self.bus.as_ptr());
        }
    }
}

#[derive(Debug, Clone, Eq, PartialEq)]
pub(super) struct Invocation {
    pub(super) path: String,
    pub(super) unit: String,
    pub(super) id: [u8; 16],
}

/// This object is minted only by a fresh fixed-name query on the already
/// authenticated original PID1 socket. It is never a deserialized Invocation.
#[derive(Debug, Eq, PartialEq)]
pub(super) struct WorkingParentObject {
    path: String,
}

impl PrivateBus {
    pub(super) fn working_parent(&self, deadline: Instant) -> Result<WorkingParentObject> {
        let request = self.request(
            c"/org/freedesktop/systemd1",
            c"org.freedesktop.systemd1.Manager",
            c"GetUnit",
        )?;
        status(unsafe {
            sd_bus_message_append_basic(
                request.0.as_ptr(),
                b's' as c_char,
                c"droidloom-working-qualification.service".as_ptr().cast(),
            )
        })?;
        let mut reply = self.call(request, deadline)?;
        reply.signature("o")?;
        let path = reply.string(b'o')?;
        reply.end()?;
        require(
            path == "/org/freedesktop/systemd1/unit/droidloom_2dworking_2dqualification_2eservice",
            "fixed working parent returned another manager object",
        )?;
        remaining(deadline)?;
        Ok(WorkingParentObject { path })
    }
    pub(super) fn working_parent_properties(
        &self,
        parent: &WorkingParentObject,
        interface: Interface,
        deadline: Instant,
    ) -> Result<Properties> {
        self.properties_at(&parent.path, interface, deadline)
    }
    pub(super) fn from_authenticated_socket(socket: &File, deadline: Instant) -> Result<Self> {
        remaining(deadline)?;
        let mut pointer = ptr::null_mut();
        status(unsafe { sd_bus_new(&mut pointer) })?;
        let value = Self {
            bus: NonNull::new(pointer).ok_or(invalid("manager bus allocation returned null"))?,
            _thread_bound: PhantomData,
        };
        status(unsafe { sd_bus_set_bus_client(pointer, 0) })?;
        status(unsafe { sd_bus_set_exit_on_disconnect(pointer, 0) })?;
        status(unsafe { sd_bus_negotiate_fds(pointer, 1) })?;
        let duplicate = socket.try_clone()?;
        status(unsafe { sd_bus_set_fd(pointer, duplicate.as_raw_fd(), duplicate.as_raw_fd()) })?;
        std::mem::forget(duplicate); // transferred only after successful set_fd
        status(unsafe { sd_bus_start(pointer) })?;
        remaining(deadline)?;
        Ok(value)
    }
    fn request(&self, path: &CStr, interface: &CStr, method: &CStr) -> Result<Message> {
        let mut pointer = ptr::null_mut();
        status(unsafe {
            sd_bus_message_new_method_call(
                self.bus.as_ptr(),
                &mut pointer,
                c"org.freedesktop.systemd1".as_ptr(),
                path.as_ptr(),
                interface.as_ptr(),
                method.as_ptr(),
            )
        })?;
        Ok(Message(
            NonNull::new(pointer).ok_or(invalid("null manager request"))?,
        ))
    }
    fn call(&self, request: Message, deadline: Instant) -> Result<Message> {
        let usec = remaining(deadline)?;
        let mut pointer = ptr::null_mut();
        let code = unsafe {
            sd_bus_call(
                self.bus.as_ptr(),
                request.0.as_ptr(),
                usec,
                ptr::null_mut(),
                &mut pointer,
            )
        };
        let reply = NonNull::new(pointer).map(Message);
        status(code)?;
        remaining(deadline)?;
        reply.ok_or(invalid("successful manager reply was null"))
    }
    pub(super) fn invocation(
        &self,
        broker: BorrowedFd<'_>,
        deadline: Instant,
    ) -> Result<Invocation> {
        let request = self.request(
            c"/org/freedesktop/systemd1",
            c"org.freedesktop.systemd1.Manager",
            c"GetUnitByPIDFD",
        )?;
        let descriptor = broker.as_raw_fd();
        status(unsafe {
            sd_bus_message_append_basic(
                request.0.as_ptr(),
                b'h' as c_char,
                (&descriptor as *const c_int).cast(),
            )
        })?;
        let mut reply = self.call(request, deadline)?;
        reply.signature("osay")?;
        let path = reply.string(b'o')?;
        let unit = reply.string(b's')?;
        let bytes = reply.bytes()?;
        require(
            bytes.len() == 16 && bytes.iter().any(|&b| b != 0),
            "actual manager invocation required",
        )?;
        reply.end()?;
        remaining(deadline)?;
        let mut id = [0; 16];
        id.copy_from_slice(&bytes);
        Ok(Invocation { path, unit, id })
    }
}

#[derive(Debug, Clone, Eq, PartialEq)]
pub(super) struct ExecCommand {
    pub(super) path: String,
    pub(super) arguments: Vec<String>,
    pub(super) flags: Vec<String>,
    pub(super) started: [u64; 2],
    pub(super) exited: [u64; 2],
    pub(super) pid: u32,
    pub(super) code: i32,
    pub(super) status: i32,
}
#[derive(Debug, Clone, Eq, PartialEq)]
pub(super) enum Value {
    Text(String),
    Boolean(bool),
    U32(u32),
    I32(i32),
    U64(u64),
    Bytes(Vec<u8>),
    Strings(Vec<String>),
    Job(u32, String),
    Profile(bool, String),
    Commands(Vec<ExecCommand>),
}
pub(super) type Properties = BTreeMap<String, Value>;

impl PrivateBus {
    pub(super) fn properties(
        &self,
        invocation: &Invocation,
        interface: Interface,
        deadline: Instant,
    ) -> Result<Properties> {
        self.properties_at(&invocation.path, interface, deadline)
    }
    fn properties_at(
        &self,
        path: &str,
        interface: Interface,
        deadline: Instant,
    ) -> Result<Properties> {
        let path =
            CString::new(path.as_bytes()).map_err(|_| invalid("invalid manager unit object"))?;
        let request = self.request(&path, c"org.freedesktop.DBus.Properties", c"GetAll")?;
        status(unsafe {
            sd_bus_message_append_basic(
                request.0.as_ptr(),
                b's' as c_char,
                interface.name().as_ptr().cast(),
            )
        })?;
        let mut reply = self.call(request, deadline)?;
        reply.signature("a{sv}")?;
        require(
            reply.enter(b'a', c"{sv}")?,
            "missing manager property dictionary",
        )?;
        let mut seen = BTreeSet::new();
        let mut values = BTreeMap::new();
        while reply.enter(b'e', c"sv")? {
            remaining(deadline)?;
            let name = reply.string(b's')?;
            require(
                name.len() <= 128 && seen.len() < 1024 && seen.insert(name.clone()),
                "duplicate, oversized or excessive manager properties",
            )?;
            if let Some(signature) = interface.signature(&name) {
                values.insert(name, reply.property(signature)?);
            } else {
                require(
                    status(unsafe { sd_bus_message_skip(reply.0.as_ptr(), c"v".as_ptr()) })? > 0,
                    "cannot skip unrelated manager variant",
                )?;
            }
            reply.exit()?;
        }
        reply.exit()?;
        reply.end()?;
        remaining(deadline)?;
        Ok(values)
    }
}

#[derive(Clone, Copy)]
pub(super) enum Interface {
    Unit,
    Service,
}
impl Interface {
    fn name(self) -> &'static CStr {
        match self {
            Self::Unit => c"org.freedesktop.systemd1.Unit",
            Self::Service => c"org.freedesktop.systemd1.Service",
        }
    }
    fn signature(self, name: &str) -> Option<&'static CStr> {
        match self {
            Self::Unit => match name {
                "Id" | "LoadState" | "ActiveState" | "SubState" | "FragmentPath" | "SourcePath"
                | "OnSuccessJobMode" | "OnFailureJobMode" => Some(c"s"),
                "Transient" | "NeedDaemonReload" => Some(c"b"),
                "DropInPaths" | "OnSuccess" | "OnFailure" => Some(c"as"),
                "InvocationID" => Some(c"ay"),
                "StateChangeTimestampMonotonic" => Some(c"t"),
                "Job" => Some(c"(uo)"),
                _ => None,
            },
            Self::Service => match name {
                "Type"
                | "Result"
                | "ExitType"
                | "Restart"
                | "KillMode"
                | "User"
                | "Group"
                | "DelegateSubgroup"
                | "ControlGroup"
                | "Slice"
                | "TimeoutStopFailureMode"
                | "RootDirectory"
                | "RootImage"
                | "WorkingDirectory" => Some(c"s"),
                "RemainAfterExit" | "SendSIGKILL" | "SendSIGHUP" | "NoNewPrivileges"
                | "PrivateMounts" | "Delegate" | "DynamicUser" => Some(c"b"),
                "MainPID" | "ControlPID" | "ExecMainPID" | "NRestarts" | "UMask" => Some(c"u"),
                "KillSignal" | "RestartKillSignal" | "FinalKillSignal" | "ExecMainCode"
                | "ExecMainStatus" => Some(c"i"),
                "RuntimeMaxUSec"
                | "LimitCORE"
                | "TimeoutStopUSec"
                | "ExecMainStartTimestampMonotonic"
                | "ExecMainExitTimestampMonotonic"
                | "ControlGroupId"
                | "MemoryMax"
                | "MemoryHigh"
                | "MemorySwapMax"
                | "TasksMax"
                | "CPUQuotaPerSecUSec"
                | "CPUQuotaPeriodUSec"
                | "AmbientCapabilities"
                | "CapabilityBoundingSet" => Some(c"t"),
                "DelegateControllers" => Some(c"as"),
                "CPUAffinity" => Some(c"ay"),
                "AppArmorProfile" | "SELinuxContext" => Some(c"(bs)"),
                "ExecConditionEx" | "ExecStartPreEx" | "ExecStartEx" | "ExecStartPostEx"
                | "ExecReloadEx" | "ExecStopEx" | "ExecStopPostEx" => Some(c"a(sasasttttuii)"),
                _ => None,
            },
        }
    }
}

impl Message {
    fn commands(&mut self) -> Result<Vec<ExecCommand>> {
        require(
            self.enter(b'a', c"(sasasttttuii)")?,
            "missing manager command array",
        )?;
        let mut values = Vec::new();
        while self.enter(b'r', c"sasasttttuii")? {
            require(values.len() < 8, "manager command array bound")?;
            let value = ExecCommand {
                path: self.string(b's')?,
                arguments: self.strings()?,
                flags: self.strings()?,
                started: [self.basic(b't')?, self.basic(b't')?],
                exited: [self.basic(b't')?, self.basic(b't')?],
                pid: self.basic(b'u')?,
                code: self.basic(b'i')?,
                status: self.basic(b'i')?,
            };
            self.exit()?;
            values.push(value);
        }
        self.exit()?;
        Ok(values)
    }
    fn property(&mut self, signature: &CStr) -> Result<Value> {
        require(
            self.enter(b'v', signature)?,
            "missing typed manager property variant",
        )?;
        let value = match signature.to_bytes() {
            b"s" => Value::Text(self.string(b's')?),
            b"b" => Value::Boolean(self.boolean()?),
            b"u" => Value::U32(self.basic(b'u')?),
            b"i" => Value::I32(self.basic(b'i')?),
            b"t" => Value::U64(self.basic(b't')?),
            b"ay" => Value::Bytes(self.bytes()?),
            b"as" => Value::Strings(self.strings()?),
            b"(uo)" => {
                require(self.enter(b'r', c"uo")?, "missing manager job tuple")?;
                let result = Value::Job(self.basic(b'u')?, self.string(b'o')?);
                self.exit()?;
                result
            }
            b"(bs)" => {
                require(self.enter(b'r', c"bs")?, "missing manager profile tuple")?;
                let result = Value::Profile(self.boolean()?, self.string(b's')?);
                self.exit()?;
                result
            }
            b"a(sasasttttuii)" => Value::Commands(self.commands()?),
            _ => {
                return Err(invalid("non-fixed manager property signature"));
            }
        };
        self.exit()?;
        Ok(value)
    }
}
