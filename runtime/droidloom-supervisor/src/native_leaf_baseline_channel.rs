//! One private, check-only channel for the source-owned native leaf invocation.
//! Only a live NativeLeafBaselineObservation can create the production payload.
//! No pathname listener, command/PID/UID input or deserializable authority exists.
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::net::UnixDatagram;
use std::process::Command;
use std::time::{Duration, Instant};

// This is source-shared comparison identity, not a caller-selected member map.
const SOURCE_RECIPE: &[u8] =
    include_bytes!("../../../android/manifest/native-application-leaf-cohort-r2.json");
const COHORT_ROOT: &str =
    "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const HOST_ENTRIES: [&str; 5] = [
    "source/support/business_ui_entry.py",
    "source/clock-support/business_ui_entry.py",
    "source/clock/clock_entry.py",
    "source/ihg/app_entry.py",
    "source/camera-photo/camera_entry.py",
];
fn compiled_host_entries() -> io::Result<serde_json::Map<String, serde_json::Value>> {
    let recipe: serde_json::Value = serde_json::from_slice(SOURCE_RECIPE)
        .map_err(|_| invalid("compiled leaf recipe JSON differs"))?;
    if recipe["schema"] != "droidloom.native-leaf-cohort-source-recipe.v1"
        || recipe["canonical_root"] != COHORT_ROOT
        || recipe["cohort"] != "cp3a-20261126-apps-r2"
    {
        return Err(invalid("compiled leaf source recipe identity differs"));
    }
    let members = recipe["members"]
        .as_array()
        .ok_or_else(|| invalid("compiled leaf member table absent"))?;
    if members.len() > 512 || recipe["output_file_count"].as_u64() != Some(members.len() as u64) {
        return Err(invalid("compiled leaf source member count differs"));
    }
    let mut out = serde_json::Map::new();
    for name in HOST_ENTRIES {
        let rows = members
            .iter()
            .filter(|row| row["relative_path"] == name)
            .collect::<Vec<_>>();
        if rows.len() != 1 {
            return Err(invalid("compiled fixed host entry is not unique"));
        }
        let pin = &rows[0]["output"];
        let path = format!("{COHORT_ROOT}/{name}");
        let object = pin
            .as_object()
            .ok_or_else(|| invalid("compiled host entry pin absent"))?;
        if object.len() != 3
            || pin["path"] != path
            || !pin["bytes"]
                .as_u64()
                .is_some_and(|v| (1..=2 * 1024 * 1024).contains(&v))
            || !pin["sha256"].as_str().is_some_and(|s| {
                s.len() == 64
                    && s.bytes()
                        .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            })
        {
            return Err(invalid("compiled host entry full pin differs"));
        }
        out.insert(path, pin.clone());
    }
    Ok(out)
}

fn monotonic_end(end: Instant) -> io::Result<u64> {
    let mut clock: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut clock) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // Sample the monotonic clock first, so conversion cannot extend the budget.
    let remaining = end
        .checked_duration_since(Instant::now())
        .ok_or_else(|| invalid("native leaf original deadline expired"))?;
    if remaining.is_zero()
        || remaining > Duration::from_secs(7200)
        || clock.tv_sec < 0
        || !(0..1_000_000_000).contains(&clock.tv_nsec)
    {
        return Err(invalid(
            "native leaf original deadline is outside its bound",
        ));
    }
    let now = (clock.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(clock.tv_nsec as u64))
        .ok_or_else(|| invalid("monotonic clock overflow"))?;
    now.checked_add(
        u64::try_from(remaining.as_nanos())
            .map_err(|_| invalid("native leaf deadline overflow"))?,
    )
    .ok_or_else(|| invalid("native leaf deadline overflow"))
}

pub(crate) const FACTS_ENV: &str = "DROIDLOOM_NATIVE_LEAF_FACTS_FD";
pub(crate) const GUARD_ENV: &str = "DROIDLOOM_NATIVE_LEAF_GUARD_FD";
const MAX_FACTS: usize = 262144;
const MAX_CHECKS: usize = crate::native_leaf_engine::MAX_CHECKS;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum LeafCheck {
    Local,
    Engine,
}

pub(crate) struct NativeLeafChannel {
    facts: File,
    server: UnixDatagram,
    child: UnixDatagram,
    deadline: Instant,
    checks: usize,
    engine_failure: Option<String>,
    package_failure: Option<String>,
    package_reads: Vec<crate::control::NativeLeafPackageReadObservation>,
    calendar_failure: Option<String>,
    calendar_reads: Vec<crate::control::NativeLeafCalendarCountsObservation>,
    apk_failure: Option<String>,
    fixture_required: bool,
    fixture: Option<crate::control::NativeFixtureObservation>,
    fixture_failure: Option<String>,
    fixture_guards: usize,
}
fn invalid(why: &'static str) -> io::Error {
    io::Error::other(why)
}
fn sealed(bytes: &[u8]) -> io::Result<File> {
    sealed_bounded(bytes,MAX_FACTS)
}
fn sealed_bounded(bytes:&[u8],limit:usize)->io::Result<File>{
    if bytes.is_empty() || bytes.len() > limit {
        return Err(invalid("native leaf facts bound"));
    }
    let raw = unsafe {
        libc::memfd_create(
            c"droidloom-native-leaf-facts".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut f = unsafe { File::from_raw_fd(raw) };
    f.write_all(bytes)?;
    let seals = libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE;
    if unsafe { libc::fcntl(f.as_raw_fd(), libc::F_ADD_SEALS, seals) } < 0 {
        return Err(io::Error::last_os_error());
    }
    // The pathname is the just-created descriptor, not an input name.
    let readonly = File::open(format!("/proc/self/fd/{}", f.as_raw_fd()))?;
    use std::os::unix::fs::MetadataExt;
    if readonly.metadata()?.ino() != f.metadata()?.ino()
        || readonly.metadata()?.dev() != f.metadata()?.dev()
        || unsafe { libc::fcntl(readonly.as_raw_fd(), libc::F_GET_SEALS) } != seals
    {
        return Err(invalid("native leaf sealed facts identity changed"));
    }
    Ok(readonly)
}

// Replies contain only source-owned comparison values in one sealed readonly
// memfd. The original APK descriptors are never passed through this channel.
fn send_comparison(socket: &UnixDatagram, token: u8, file: &File) -> io::Result<()> {
    let mut token = token;
    let mut iov = libc::iovec { iov_base: (&mut token as *mut u8).cast(), iov_len: 1 };
    let mut ancillary = [0usize; 4];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of::<RawFd>() as u32) } as usize;
    unsafe {
        let header = libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<RawFd>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<RawFd>(), file.as_raw_fd());
    }
    match unsafe { libc::sendmsg(socket.as_raw_fd(), &message, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) } {
        1 => Ok(()),
        -1 => Err(io::Error::last_os_error()),
        _ => Err(invalid("short fixed native leaf comparison reply")),
    }
}

// N is deliberately a different wire shape: comparison first, public APK
// snapshot second. The original file descriptors never leave their reader.
fn send_apk_copy(socket:&UnixDatagram,comparison:&File,copy:&File)->io::Result<()> {
    let mut token=b'N';
    let mut iov=libc::iovec{iov_base:(&mut token as *mut u8).cast(),iov_len:1};
    let mut ancillary=[0usize;8];
    let mut message:libc::msghdr=unsafe{std::mem::zeroed()};
    message.msg_iov=&mut iov;message.msg_iovlen=1;
    message.msg_control=ancillary.as_mut_ptr().cast();
    message.msg_controllen=unsafe{libc::CMSG_SPACE((2*std::mem::size_of::<RawFd>()) as u32)} as usize;
    unsafe{
        let header=libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level=libc::SOL_SOCKET;(*header).cmsg_type=libc::SCM_RIGHTS;
        (*header).cmsg_len=libc::CMSG_LEN((2*std::mem::size_of::<RawFd>()) as u32) as usize;
        let data=libc::CMSG_DATA(header).cast::<RawFd>();
        std::ptr::write_unaligned(data,comparison.as_raw_fd());
        std::ptr::write_unaligned(data.add(1),copy.as_raw_fd());
    }
    match unsafe{libc::sendmsg(socket.as_raw_fd(),&message,libc::MSG_DONTWAIT|libc::MSG_NOSIGNAL)}{
        1=>Ok(()),-1=>Err(io::Error::last_os_error()),
        _=>Err(invalid("short original APK two-descriptor reply")),
    }
}
fn apk_action_cap(opcode:u8)->Option<Duration>{
    use crate::production_application::apk_protocol::BODY_CAP;
    match opcode{
        b'A'|b'V'=>Some(Duration::from_secs(15)),
        b'N'=>Some(2*BODY_CAP),
        b'R'=>Some(BODY_CAP),
        _=>None,
    }
}

fn pending_opcode(socket: &UnixDatagram) -> io::Result<Option<u8>> {
    let mut bytes = [0u8; 2];
    let n = unsafe {
        libc::recv(socket.as_raw_fd(), bytes.as_mut_ptr().cast(), bytes.len(),
            libc::MSG_PEEK | libc::MSG_DONTWAIT)
    };
    if n < 0 {
        let error = io::Error::last_os_error();
        return if error.kind() == io::ErrorKind::WouldBlock { Ok(None) } else { Err(error) };
    }
    // The consuming reader below checks the complete payload and rejects FDs.
    Ok(bytes.first().copied().filter(|_| n > 0))
}
fn receive_private_request(socket:&UnixDatagram,expected:u8,role_ordinal:bool)->io::Result<u8>{
    let mut bytes = [0u8; 3];
    let mut iov = libc::iovec { iov_base: bytes.as_mut_ptr().cast(), iov_len: bytes.len() };
    let mut ancillary = [0usize; 8];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = ancillary.as_mut_ptr().cast();
    message.msg_controllen = std::mem::size_of_val(&ancillary);
    let n = unsafe {
        libc::recvmsg(socket.as_raw_fd(), &mut message, libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC)
    };
    if n < 0 { return Err(io::Error::last_os_error()); }
    let mut any_ancillary = false;
    unsafe {
        let mut header = libc::CMSG_FIRSTHDR(&message);
        while !header.is_null() {
            any_ancillary = true;
            let row = &*header;
            if row.cmsg_level == libc::SOL_SOCKET && row.cmsg_type == libc::SCM_RIGHTS {
                let base = libc::CMSG_LEN(0) as usize;
                if row.cmsg_len >= base {
                    for i in 0..(row.cmsg_len - base) / std::mem::size_of::<RawFd>() {
                        let fd = std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>().add(i));
                        libc::close(fd);
                    }
                }
            }
            header = libc::CMSG_NXTHDR(&message, header);
        }
    }
    if n<1 || n as usize>bytes.len() || bytes[0]!=expected || any_ancillary
        || message.msg_flags & !libc::MSG_CMSG_CLOEXEC != 0 {
        return Err(invalid("fixed native leaf request or input descriptors differ"));
    }
    if role_ordinal {
        let (_,ordinal)=crate::production_application::apk_protocol::PackageReadKind::request(&bytes[..n as usize])
            .map_err(|_|invalid("fixed package request is not I/P/L with its optional bounded ordinal"))?;
        Ok(ordinal)
    }else if n==1{Ok(0)}else{Err(invalid("fixed native leaf read accepts one opcode"))}
}
fn receive_fixed_opcode(socket:&UnixDatagram,expected:u8)->io::Result<()>{
    receive_private_request(socket,expected,false).map(|_|())
}

impl NativeLeafChannel {
    pub(crate) fn new(
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &crate::control::NativeApplicationInspector,
        deadline: Instant,
    ) -> Result<Self, String> {
        observation
            .verify_local(inspector, deadline)
            .map_err(|e| e.to_string())?;
        let deadline = deadline.min(observation.deadline());
        let bytes = serde_json::to_vec(&serde_json::json!({
            "schema":"droidloom.native-leaf-channel.v1",
            "baseline":observation.facts(),
            "user_zero_package_inventory":observation.inventory_facts(),
            "working_source_owner":observation.working_source_owner(),
            "host_source_entries":compiled_host_entries().map_err(|e|e.to_string())?,
            "normal_source_recipe":{"bytes":SOURCE_RECIPE.len(),"sha256":format!("{:x}", Sha256::digest(SOURCE_RECIPE))},
            "deadline_monotonic_ns":monotonic_end(deadline).map_err(|e|e.to_string())?,
            "comparison_only":true
        })).map_err(|e|e.to_string())?;
        let mut value=Self::from_bytes(&bytes, deadline).map_err(|e| e.to_string())?;
        value.fixture_required=observation.owned_fixture_route().map_err(|e|e.to_string())?.is_some();
        Ok(value)
    }
    fn from_bytes(bytes: &[u8], deadline: Instant) -> io::Result<Self> {
        if Instant::now() >= deadline {
            return Err(invalid("native leaf channel deadline expired"));
        }
        let facts = sealed(bytes)?;
        let (server, child) = UnixDatagram::pair()?;
        server.set_nonblocking(true)?;
        // Socketpair has no filesystem address; only these two held endpoints
        // exist. Parent retains the server, fixed exec inherits only child.
        Ok(Self {
            facts,
            server,
            child,
            deadline,
            checks: 0,
            engine_failure: None,
            package_failure: None,
            package_reads: Vec::new(),
            calendar_failure: None,
            calendar_reads: Vec::new(),
            apk_failure: None,
            fixture_required: false,
            fixture: None,
            fixture_failure: None,
            fixture_guards: 0,
        })
    }
    pub(crate) fn prepare(&self, command: &mut Command) -> [RawFd; 2] {
        let f = self.facts.as_raw_fd();
        let g = self.child.as_raw_fd();
        command
            .env(FACTS_ENV, f.to_string())
            .env(GUARD_ENV, g.to_string());
        [f, g]
    }
    fn serve_with(
        &mut self,
        engine_enabled: bool,
        mut check: impl FnMut(LeafCheck) -> Result<(), String>,
    ) -> Result<(), String> {
        let mut request = [0u8; 2];
        let check_kind = match self.server.recv(&mut request) {
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(e) => return Err(format!("native leaf guard channel failed: {e}")),
            Ok(n) => {
                if n != 1
                    || !(request[0] == b'G' || (request[0] == b'E' && engine_enabled))
                    || self.checks >= MAX_CHECKS
                    || Instant::now() >= self.deadline
                {
                    let _ = self.server.send(b"1");
                    return Err(
                        "native leaf guard accepts only bounded current-custody checks".into(),
                    );
                }
                if request[0] == b'G' {
                    LeafCheck::Local
                } else {
                    LeafCheck::Engine
                }
            }
        };
        // An E failure must not kill the fixed Python flow before its existing
        // finally path can close the already-recorded owned task. Keep G local
        // and available for that cleanup, but remember the failure permanently
        // and never perform another E in this invocation.
        if check_kind == LeafCheck::Engine && self.engine_failure.is_some() {
            self.server
                .send(b"1")
                .map_err(|e| format!("engine failure reply failed: {e}"))?;
            self.checks += 1;
            return Ok(());
        }
        let result = check(check_kind);
        if check_kind == LeafCheck::Engine {
            if let Err(error) = &result {
                self.engine_failure = Some(error.clone());
                if Instant::now() < self.deadline {
                    self.server
                        .send(b"1")
                        .map_err(|e| format!("engine failure reply failed: {e}"))?;
                    self.checks += 1;
                    return Ok(());
                }
            }
        }
        if result.is_err() || Instant::now() >= self.deadline {
            let _ = self.server.send(b"1");
            return result.and(Err(
                "native leaf custody check finished after its actual invocation budget".into(),
            ));
        }
        self.server
            .send(if check_kind == LeafCheck::Local {
                b"0"
            } else {
                b"E"
            })
            .map_err(|e| format!("native leaf guard reply failed: {e}"))?;
        self.checks += 1;
        Ok(())
    }

    fn serve_package(
        &mut self,
        kind: crate::control::NativeLeafPackageReadKind,
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &crate::control::NativeApplicationInspector,
    ) -> Result<(), String> {
        let ordinal=receive_private_request(&self.server,kind.opcode(),true).map_err(|e|e.to_string())?;
        if self.checks >= MAX_CHECKS || Instant::now() >= self.deadline {
            let _ = self.server.send(b"1");
            return Err("fixed package read exceeded the original channel count or end".into());
        }
        self.checks += 1;
        if self.package_failure.is_some() {
            self.server.send(b"1").map_err(|e| e.to_string())?;
            return Ok(());
        }
        let end=self.deadline.min(Instant::now()+crate::production_application::apk_protocol::PACKAGE_READ_CAP);
        let actual = (|| {
            observation.verify_local(inspector,end).map_err(|e|e.to_string())?;
            let (value,successful,standalone)=if observation.has_apk_scope(){
                let actual_kind=crate::production_application::apk_protocol::PackageReadKind::from_opcode(kind.opcode())
                    .ok_or("fixed PM opcode is absent")?;
                let (value,successful)=observation.apk_package_read_until(inspector,actual_kind,ordinal,end)
                    .map_err(|e|e.to_string())?;
                (value,successful,None)
            }else{
                if ordinal!=0{return Err("non-primary PM ordinal requires its actual fixed APK group".into());}
                // Existing physical-only primary path remains available to its
                // original callers. Preparation cannot use this peer route.
                let read=inspector.read_native_leaf_package_until(
                    observation.main(),observation.actual_application(),kind,end)
                    .map_err(|e|e.to_string())?;
                let value=read.comparison(inspector,observation.main(),observation.actual_application(),end)
                    .map_err(|e|e.to_string())?;
                let successful=read.output().status.success() && read.output().stderr.is_empty();
                (value,successful,Some(read))
            };
            observation.verify_local(inspector,end).map_err(|e|e.to_string())?;
            let raw=serde_json::to_vec(&value).map_err(|e|e.to_string())?;
            let file=sealed(&raw).map_err(|e|e.to_string())?;
            if Instant::now()>=end{return Err("fixed package reply exceeded its original 15-second end".into());}
            send_comparison(&self.server,kind.opcode(),&file).map_err(|e|e.to_string())?;
            if !successful{
                self.package_failure=Some("actual fixed package query exited nonzero or emitted diagnostics".into());
            }
            if let Some(read)=standalone{self.package_reads.push(read);}
            Ok(())
        })();
        if let Err(error) = actual {
            self.package_failure = Some(error);
            if Instant::now() >= self.deadline {
                return Err("fixed package read failed at the original invocation end".into());
            }
            // Preserve the first failed read. G remains a purely local custody
            // check for the existing finally path; no failed query is retried.
            self.server.send(b"1").map_err(|e| e.to_string())?;
        }
        Ok(())
    }


    fn serve_calendar(
        &mut self,
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &mut crate::control::NativeApplicationInspector,
        business_enabled: bool,
    ) -> Result<(), String> {
        receive_fixed_opcode(&self.server, b'C').map_err(|e| e.to_string())?;
        if self.checks >= MAX_CHECKS || Instant::now() >= self.deadline {
            let _ = self.server.send(b"1");
            return Err("Calendar read exceeded the original channel count or end".into());
        }
        self.checks += 1;
        if self.calendar_failure.is_some() {
            self.server.send(b"1").map_err(|e| e.to_string())?;
            return Ok(());
        }
        let actual = (|| {
            // Calendar C is only part of the fixed owned business invocation.
            // Baseline capture/private preparation cannot acquire this route.
            if !business_enabled {
                return Err("preparation cannot invoke Calendar counts".to_owned());
            }
            observation.verify_local(inspector, self.deadline).map_err(|e| e.to_string())?;
            let read = inspector.read_native_leaf_calendar_counts_until(
                observation.main(), observation.actual_application(), self.deadline,
            ).map_err(|e| e.to_string())?;
            observation.verify_local(inspector, self.deadline).map_err(|e| e.to_string())?;
            if let Some(prior) = self.calendar_reads.last() {
                read.require_same_database(prior).map_err(|e| e.to_string())?;
            }
            let value = read.comparison(
                inspector, observation.main(), observation.actual_application(), self.deadline,
            ).map_err(|e| e.to_string())?;
            let file = sealed(&serde_json::to_vec(&value).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
            if Instant::now() >= self.deadline {
                return Err("Calendar comparison exceeded the original invocation end".into());
            }
            // Retain the real observation before publishing its comparison.
            self.calendar_reads.push(read);
            send_comparison(&self.server, b'C', &file).map_err(|e| e.to_string())?;
            Ok(())
        })();
        if let Err(error) = actual {
            self.calendar_failure = Some(error);
            if Instant::now() >= self.deadline {
                return Err("Calendar read failed at the original invocation end".into());
            }
            // Keep G available for the original finally path, remember this
            // failure for finish, and never replay a failed Calendar request.
            self.server.send(b"1").map_err(|e| e.to_string())?;
        }
        Ok(())
    }

    fn serve_apk_with(
        &mut self,opcode:u8,
        mut action:impl FnMut(Instant)->Result<(serde_json::Value,Option<crate::control::NativeLeafApkCopy>),String>,
    )->Result<(),String>{
        receive_fixed_opcode(&self.server,opcode).map_err(|e|e.to_string())?;
        let cap=apk_action_cap(opcode).ok_or("unknown original APK opcode")?;
        if self.checks>=MAX_CHECKS || Instant::now()>=self.deadline{
            let _=self.server.send(b"1");
            return Err("original APK operation exceeded the original channel count/end".into());
        }
        self.checks+=1;
        if self.apk_failure.is_some(){
            self.server.send(b"1").map_err(|e|e.to_string())?;
            return Ok(());
        }
        let end=self.deadline.min(Instant::now()+cap);
        let actual=(||{
            let (value,copy)=action(end)?;
            let raw=serde_json::to_vec(&value).map_err(|e|e.to_string())?;
            let comparison=sealed(&raw).map_err(|e|e.to_string())?;
            if Instant::now()>=end{return Err("original APK reply exceeded its fixed operation end".into());}
            match (opcode,copy){
                (b'N',Some(copy))=>{
                    copy.verify(end).map_err(|e|e.to_string())?;
                    send_apk_copy(&self.server,&comparison,copy.file()).map_err(|e|e.to_string())?;
                }
                (b'A'|b'V'|b'R',None)=>{
                    send_comparison(&self.server,opcode,&comparison).map_err(|e|e.to_string())?;
                }
                _=>return Err("original APK opcode/descriptor shape differs".into()),
            }
            // There is no fallible action after sending the sole reply.
            Ok(())
        })();
        if let Err(error)=actual{
            self.apk_failure=Some(error);
            if Instant::now()>=self.deadline{
                return Err("original APK observation failed at the original invocation end".into());
            }
            self.server.send(b"1").map_err(|e|e.to_string())?;
        }
        Ok(())
    }
    fn serve_apk(&mut self,opcode:u8,observation:&NativeLeafBaselineObservation<'_>,
        inspector:&crate::control::NativeApplicationInspector)->Result<(),String>{
        self.serve_apk_with(opcode,|end|{
            observation.verify_local(inspector,end).map_err(|e|e.to_string())?;
            let result=match opcode{
                b'A'=>(observation.apk_begin_until(inspector,end).map_err(|e|e.to_string())?,None),
                b'N'=>{
                    let copy=observation.apk_next_copy_until(inspector,end).map_err(|e|e.to_string())?;
                    let value=serde_json::json!({"schema":"droidloom.native-leaf-apk-copy.v1",
                        "main":observation.main().facts(),
                        "application":observation.actual_application().facts(),
                        "copy":copy.comparison(),"comparison_only":true,
                        "original_apk_descriptors_on_host":false});
                    (value,Some(copy))
                }
                b'V'|b'R'=>(observation.apk_guard_until(inspector,opcode==b'R',end)
                    .map_err(|e|e.to_string())?,None),
                _=>return Err("unknown source-owned APK operation".into()),
            };
            observation.verify_local(inspector,end).map_err(|e|e.to_string())?;
            Ok(result)
        })
    }

    fn serve_fixture(&mut self,opcode:u8,observation:&NativeLeafBaselineObservation<'_>,
        inspector:&crate::control::NativeApplicationInspector,business:bool)->Result<(),String>{
        use crate::native_leaf_fixture::{self as wire,FixtureAction};
        receive_fixed_opcode(&self.server,opcode).map_err(|e|e.to_string())?;
        if self.checks>=MAX_CHECKS || Instant::now()>=self.deadline {
            let _=self.server.send(b"1");return Err("fixture request exceeded the original invocation count/end".into());
        }
        self.checks+=1;
        if self.fixture_failure.is_some() {self.server.send(b"1").map_err(|e|e.to_string())?;return Ok(());}
        let action=match opcode {b'B'=>FixtureAction::Begin,b'H'=>FixtureAction::Guard,b'S'=>FixtureAction::State,b'D'=>FixtureAction::Retire,
            _=>return Err("unknown source fixture opcode".into())};
        let end=self.deadline.min(Instant::now()+action.cap());
        let result=(|| {
            if !business || !self.fixture_required {return Err("preparation or this business route has no late-born fixture authority".into());}
            observation.verify_local(inspector,end).map_err(|e|e.to_string())?;
            let value=if action==FixtureAction::Begin {
                if self.fixture.is_some(){return Err("the same source leaf cannot retry a fixture installation".into());}
                let actual=inspector.begin_native_fixture_until(observation,end).map_err(|e|e.to_string())?;
                let comparison=actual.begin_comparison().map_err(|e|e.to_string())?;
                self.fixture=Some(actual);comparison
            } else {
                if matches!(action,FixtureAction::Guard|FixtureAction::State) {
                    if self.fixture_guards>=128{return Err("source fixture guard/state count exceeded".into());}
                    self.fixture_guards+=1;
                }
                self.fixture.as_mut().ok_or("fixture has no actual begin in this leaf")?
                    .continue_until(inspector,observation,action,end).map_err(|e|e.to_string())?
            };
            observation.verify_local(inspector,end).map_err(|e|e.to_string())?;
            let raw=serde_json::to_vec(&value).map_err(|e|e.to_string())?;
            let file=sealed_bounded(&raw,wire::MAX_RESPONSE_BYTES).map_err(|e|e.to_string())?;
            if Instant::now()>=end{return Err("fixture complete reply exceeded its original operation end".into());}
            send_comparison(&self.server,opcode,&file).map_err(|e|e.to_string())
        })();
        if let Err(error)=result {
            self.fixture_failure=Some(error);
            if Instant::now()>=self.deadline{return Err("actual fixture request failed at the original leaf end".into());}
            // Preserve original G for the leaf's local finally checks, without
            // retrying an uncertain installation, guard, or retirement.
            self.server.send(b"1").map_err(|e|e.to_string())?;
        }
        Ok(())
    }

    pub(crate) fn serve(
        &mut self,
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &mut crate::control::NativeApplicationInspector,
        mut engines: Option<&mut crate::native_leaf_engine::PendingLeafEngines>,
    ) -> Result<(), String> {
        let pending = pending_opcode(&self.server).map_err(|e| e.to_string())?;
        if let Some(opcode)=pending.filter(|v|matches!(v,b'B'|b'H'|b'S'|b'D')) {
            return self.serve_fixture(opcode,observation,inspector,engines.is_some());
        }
        if pending == Some(b'C') {
            return self.serve_calendar(observation, inspector, engines.is_some());
        }
        if let Some(opcode) = pending.filter(|v| apk_action_cap(*v).is_some()) {
            return self.serve_apk(opcode, observation, inspector);
        }
        if let Some(kind) = pending.and_then(crate::control::NativeLeafPackageReadKind::from_opcode) {
            return self.serve_package(kind, observation, inspector);
        }
        let deadline = self.deadline;
        let engine_enabled = engines.is_some();
        self.serve_with(engine_enabled, |kind| match kind {
            LeafCheck::Local => observation
                .verify_local(inspector, deadline)
                .map_err(|e| e.to_string()),
            LeafCheck::Engine => engines
                .as_deref_mut()
                .ok_or_else(|| {
                    "capture/preparation does not support engine observation".to_owned()
                })?
                .capture(observation, inspector, deadline),
        })
    }
    pub(crate) fn finish(&self) -> Result<(), String> {
        if let Some(error)=&self.fixture_failure {return Err(format!("actual late-born fixture failed: {error}"));}
        if self.fixture_required {
            self.fixture.as_ref().ok_or("required source fixture transaction was never executed")?.require_retired()?;
        }
        if let Some(error) = &self.engine_failure {
            return Err(format!(
                "running-engine checkpoint failed; no engine/identity credit: {error}"
            ));
        }
        if let Some(error) = &self.package_failure {
            return Err(format!("actual package metadata read failed: {error}"));
        }
        if let Some(error) = &self.calendar_failure {
            return Err(format!("actual Calendar counts failed: {error}"));
        }
        if let Some(error)=&self.apk_failure{
            return Err(format!("actual original APK custody failed: {error}"));
        }
        if self.checks == 0 {
            return Err("native leaf never checked the actual retained owner".into());
        }
        if Instant::now() >= self.deadline {
            return Err("native leaf channel retirement exceeded invocation budget".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;


    #[test]
    fn native_leaf_apk_copy_reply_has_two_ordered_real_descriptors(){
        let (sender,receiver)=UnixDatagram::pair().unwrap();
        let comparison=sealed(b"{\"comparison_only\":true}").unwrap();
        let copy=sealed(b"public snapshot fixture").unwrap();
        send_apk_copy(&sender,&comparison,&copy).unwrap();
        let mut bytes=[0u8;2];let mut iov=libc::iovec{iov_base:bytes.as_mut_ptr().cast(),iov_len:2};
        let mut ancillary=[0usize;8];let mut message:libc::msghdr=unsafe{std::mem::zeroed()};
        message.msg_iov=&mut iov;message.msg_iovlen=1;message.msg_control=ancillary.as_mut_ptr().cast();
        message.msg_controllen=std::mem::size_of_val(&ancillary);
        assert_eq!(unsafe{libc::recvmsg(receiver.as_raw_fd(),&mut message,libc::MSG_CMSG_CLOEXEC)},1);
        assert_eq!(bytes[0],b'N');assert_eq!(message.msg_flags&!libc::MSG_CMSG_CLOEXEC,0);
        let header=unsafe{libc::CMSG_FIRSTHDR(&message)};assert!(!header.is_null());
        assert_eq!(unsafe{(*header).cmsg_level},libc::SOL_SOCKET);
        assert_eq!(unsafe{(*header).cmsg_type},libc::SCM_RIGHTS);
        assert_eq!(unsafe{(*header).cmsg_len},unsafe{libc::CMSG_LEN((2*std::mem::size_of::<RawFd>())as u32)}as usize);
        assert!(unsafe{libc::CMSG_NXTHDR(&message,header)}.is_null());
        use std::os::unix::fs::MetadataExt;
        for (index,expected) in [&comparison,&copy].into_iter().enumerate(){
            let fd=unsafe{std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>().add(index))};
            let actual=unsafe{File::from_raw_fd(fd)};
            assert_eq!((actual.metadata().unwrap().dev(),actual.metadata().unwrap().ino()),
                (expected.metadata().unwrap().dev(),expected.metadata().unwrap().ino()));
            assert_eq!(unsafe{libc::fcntl(fd,libc::F_GETFL)}&libc::O_ACCMODE,libc::O_RDONLY);
            assert_eq!(unsafe{libc::fcntl(fd,libc::F_GETFD)}&libc::FD_CLOEXEC,libc::FD_CLOEXEC);
        }
    }
    #[test]
    fn native_leaf_apk_first_failure_is_permanent_without_disabling_local_cleanup(){
        let mut channel=NativeLeafChannel::from_bytes(b"{}",Instant::now()+Duration::from_secs(3)).unwrap();
        channel.child.send(b"A").unwrap();
        channel.serve_apk_with(b'A',|_|Err("actual reader custody failed".into())).unwrap();
        let mut reply=[0u8;2];assert_eq!(channel.child.recv(&mut reply).unwrap(),1);assert_eq!(reply[0],b'1');
        channel.child.send(b"G").unwrap();
        channel.serve_with(false,|kind|{assert_eq!(kind,LeafCheck::Local);Ok(())}).unwrap();
        assert_eq!(channel.child.recv(&mut reply).unwrap(),1);assert_eq!(reply[0],b'0');
        channel.child.send(b"R").unwrap();
        channel.serve_apk_with(b'R',|_|panic!("failed original APK owner must never be retried")).unwrap();
        assert_eq!(channel.child.recv(&mut reply).unwrap(),1);assert_eq!(reply[0],b'1');
        assert!(channel.finish().unwrap_err().contains("actual reader custody failed"));
        assert_eq!(apk_action_cap(b'N'),Some(Duration::from_secs(120)));
        for opcode in [b'B',b'F',b'C',0]{assert!(apk_action_cap(opcode).is_none());}
    }

    #[test]
    fn native_leaf_package_comparison_uses_one_real_readonly_sealed_fd() {
        let (sender, receiver) = UnixDatagram::pair().unwrap();
        let file = sealed(b"{\"comparison_only\":true}").unwrap();
        send_comparison(&sender, b'I', &file).unwrap();
        let mut bytes = [0u8; 2];
        let mut iov = libc::iovec { iov_base: bytes.as_mut_ptr().cast(), iov_len: bytes.len() };
        let mut ancillary = [0usize; 4];
        let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = ancillary.as_mut_ptr().cast();
        message.msg_controllen = std::mem::size_of_val(&ancillary);
        assert_eq!(unsafe {
            libc::recvmsg(receiver.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC)
        }, 1);
        assert_eq!(bytes[0], b'I');
        assert_eq!(message.msg_flags & !libc::MSG_CMSG_CLOEXEC, 0);
        let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        assert!(!header.is_null());
        assert_eq!(unsafe { (*header).cmsg_level }, libc::SOL_SOCKET);
        assert_eq!(unsafe { (*header).cmsg_type }, libc::SCM_RIGHTS);
        assert_eq!(unsafe { (*header).cmsg_len },
            unsafe { libc::CMSG_LEN(std::mem::size_of::<RawFd>() as u32) } as usize);
        assert!(unsafe { libc::CMSG_NXTHDR(&message, header) }.is_null());
        let fd = unsafe {
            std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>())
        };
        let mut actual = unsafe { File::from_raw_fd(fd) };
        use std::os::unix::fs::MetadataExt;
        assert_eq!((actual.metadata().unwrap().dev(), actual.metadata().unwrap().ino()),
            (file.metadata().unwrap().dev(), file.metadata().unwrap().ino()));
        assert_eq!(unsafe { libc::fcntl(fd, libc::F_GETFL) } & libc::O_ACCMODE, libc::O_RDONLY);
        assert_eq!(unsafe { libc::fcntl(fd, libc::F_GETFD) } & libc::FD_CLOEXEC, libc::FD_CLOEXEC);
        assert_eq!(unsafe { libc::fcntl(fd, libc::F_GET_SEALS) },
            libc::F_SEAL_WRITE | libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL);
        let mut raw = Vec::new();
        actual.read_to_end(&mut raw).unwrap();
        assert_eq!(raw, b"{\"comparison_only\":true}");
        assert!(actual.write_all(b"x").is_err());
    }

    #[test]
    fn native_leaf_apk_package_request_receives_only_closed_ordinal_without_input_fd(){
        let (child,server)=UnixDatagram::pair().unwrap();
        for bytes in [b"I".as_slice(),b"I\0",b"I\x02"]{
            child.send(bytes).unwrap();
            assert_eq!(receive_private_request(&server,b'I',true).unwrap(),
                if bytes.len()==1{0}else{bytes[1]});
        }
        for bytes in [b"P".as_slice(),b"I\x03",b"I\0\0",b"I more",b""]{
            child.send(bytes).unwrap();
            assert!(receive_private_request(&server,b'I',true).is_err());
        }
        let unexpected=sealed(b"not an input authority").unwrap();
        send_comparison(&child,b'I',&unexpected).unwrap();
        assert!(receive_private_request(&server,b'I',true).is_err());
        child.send(b"G\0").unwrap();
        assert!(receive_private_request(&server,b'G',false).is_err());
        child.send(b"I").unwrap();
        assert_eq!(receive_private_request(&server,b'I',true).unwrap(),0);
    }
    #[test]
    fn native_leaf_package_request_rejects_payload_wrong_opcode_and_input_fds() {
        let (child, server) = UnixDatagram::pair().unwrap();
        for bytes in [b"I extra".as_slice(), b"", b"P"] {
            child.send(bytes).unwrap();
            assert!(receive_fixed_opcode(&server, b'I').is_err());
        }
        let unexpected = sealed(b"no input authority").unwrap();
        send_comparison(&child, b'I', &unexpected).unwrap();
        assert!(receive_fixed_opcode(&server, b'I').is_err());
        child.send(b"I").unwrap();
        assert_eq!(pending_opcode(&server).unwrap(), Some(b'I'));
        receive_fixed_opcode(&server, b'I').unwrap();
        assert_eq!(pending_opcode(&server).unwrap(), None);
    }
    #[test]
    fn native_leaf_monotonic_deadline_never_renews_original_budget() {
        let before = Instant::now();
        assert!(monotonic_end(before).is_err());
        assert!(monotonic_end(before + Duration::from_secs(7201)).is_err());
        let end = before + Duration::from_secs(2);
        let projected = monotonic_end(end).unwrap();
        let mut actual: libc::timespec = unsafe { std::mem::zeroed() };
        assert_eq!(
            unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut actual) },
            0
        );
        let actual = actual.tv_sec as u64 * 1_000_000_000 + actual.tv_nsec as u64;
        assert!(projected > actual && projected - actual <= 2_000_000_000);
    }
    #[test]
    fn native_leaf_channel_seals_real_payload_and_has_no_path_listener() {
        let mut ch = NativeLeafChannel::from_bytes(
            b"{\"comparison_only\":true}",
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        let mut value = String::new();
        ch.facts.read_to_string(&mut value).unwrap();
        assert_eq!(value, "{\"comparison_only\":true}");
        assert_eq!(
            unsafe { libc::fcntl(ch.facts.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE,
            libc::O_RDONLY
        );
        assert!(ch.facts.write_all(b"x").is_err());
        assert!(ch.server.local_addr().unwrap().is_unnamed());
        ch.child.send(b"G").unwrap();
        let mut called = 0;
        ch.serve_with(false, |_| {
            called += 1;
            Ok(())
        })
        .unwrap();
        let mut reply = [0u8; 1];
        assert_eq!(ch.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'0');
        assert_eq!(called, 1);
        ch.finish().unwrap();
    }
    #[test]
    fn native_leaf_channel_rejects_foreign_requests_expiry_and_failed_actual_guard() {
        for request in [b"P".as_slice(), b"GG", b""] {
            let mut ch =
                NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3))
                    .unwrap();
            ch.child.send(request).unwrap();
            assert!(
                ch.serve_with(false, |_| panic!(
                    "unvalidated request must not query owner"
                ))
                .is_err()
            );
            assert!(ch.finish().is_err());
        }
        let mut ch =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        ch.child.send(b"G").unwrap();
        assert!(
            ch.serve_with(false, |_| Err("actual original owner changed".into()))
                .unwrap_err()
                .contains("owner changed")
        );
        let mut reply = [0u8; 1];
        ch.child.recv(&mut reply).unwrap();
        assert_eq!(reply[0], b'1');
        assert!(ch.finish().is_err());
        let mut expired =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        expired.deadline = Instant::now() - Duration::from_millis(1);
        expired.child.send(b"G").unwrap();
        assert!(
            expired
                .serve_with(false, |_| panic!("expired channel must not query owner"))
                .is_err()
        );
    }
    #[test]
    fn native_leaf_engine_checkpoint_is_distinct_and_disabled_for_old_runner() {
        let mut disabled =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        disabled.child.send(b"E").unwrap();
        assert!(
            disabled
                .serve_with(false, |_| panic!("preparation cannot invoke E"))
                .is_err()
        );
        assert!(disabled.finish().is_err());

        let mut active =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        active.child.send(b"E").unwrap();
        let mut requested = Vec::new();
        active
            .serve_with(true, |kind| {
                requested.push(kind);
                Ok(())
            })
            .unwrap();
        let mut reply = [0u8; 2];
        assert_eq!(active.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'E');
        active.child.send(b"G").unwrap();
        active
            .serve_with(true, |kind| {
                requested.push(kind);
                Ok(())
            })
            .unwrap();
        assert_eq!(active.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'0');
        assert_eq!(requested, [LeafCheck::Engine, LeafCheck::Local]);
        active.finish().unwrap();
        // This is a protocol model, not an EngineMappingObservation constructor.
    }

    #[test]
    fn native_leaf_engine_checkpoint_rejects_payload_failure_and_late_reply() {
        for request in [b"EE".as_slice(), b"E package", b"P"] {
            let mut channel =
                NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3))
                    .unwrap();
            channel.child.send(request).unwrap();
            assert!(
                channel
                    .serve_with(true, |_| panic!("payload cannot select an engine"))
                    .is_err()
            );
        }
        let mut failed =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        failed.child.send(b"E").unwrap();
        assert!(
            failed
                .serve_with(true, |_| Err("actual observer retirement failed".into()))
                .is_ok()
        );
        let mut reply = [0u8; 2];
        assert_eq!(failed.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'1');
        failed.child.send(b"G").unwrap();
        assert!(
            failed
                .serve_with(true, |kind| {
                    assert_eq!(kind, LeafCheck::Local);
                    Ok(())
                })
                .is_ok()
        );
        assert_eq!(failed.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'0');
        failed.child.send(b"E").unwrap();
        assert!(
            failed
                .serve_with(true, |_| panic!("failed E cannot be retried"))
                .is_ok()
        );
        assert_eq!(failed.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'1');
        assert!(
            failed
                .finish()
                .unwrap_err()
                .contains("actual observer retirement failed")
        );
        let mut expired =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        expired.deadline = Instant::now() - Duration::from_millis(1);
        expired.child.send(b"E").unwrap();
        assert!(
            expired
                .serve_with(true, |_| panic!("expired E cannot start"))
                .is_err()
        );
    }
}
