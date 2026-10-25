// SPDX-License-Identifier: MPL-2.0
//! Bounded synchronous Binder byte transactions to context-manager handle 0.
//!
//! One participating thread per open, one outgoing call per open, no nested
//! calls, objects, FD translation, death subscriptions, oneway, or MAC labels.
//! The device node is root:root 0600. This is not Android boot qualification.
//!
//! Lock order: VMAR -> DOMAIN. DOMAIN never acquires VMAR/process locks or
//! copies userspace. Input is snapshotted first; output is prepared under the
//! domain lock and copied after releasing it. Mapping frames are owned, charged
//! UFrames, not user addresses. A failed output copy retains the prepared event.

mod uapi;
use core::time::Duration;

use device_id::{DeviceId, MinorId};
use ostd::{
    mm::{UFrame, VmIo},
    sync::WaitQueue,
    task::Task,
};
use spin::Once;
use uapi::*;

use crate::{
    context::current_userspace,
    device::{Device, DeviceType, registry::char},
    events::IoEvents,
    fs::{
        devtmpfs::DevtmpfsNodeMeta,
        file::{Mappable, MappableObject, MappedObject, PerOpenFileOps, StatusFlags},
        vfs::{inode::FileOps, path::Path},
    },
    prelude::*,
    process::{
        Process, VmarSnapshot,
        posix_thread::AsPosixThread,
        signal::{PollHandle, Pollable, Pollee},
    },
    thread::Thread,
    util::ioctl::RawIoctl,
    vm::vmar::{FileMmapRequest, MapHandle},
};

const MAX_ENDPOINTS: usize = 64;
const MAX_QUEUE: usize = 16;
const MAX_STREAM: usize = 4096;
const MAX_MAPPING: usize = 1024 * 1024;
const MAX_BUFFERS: usize = 16;
static DOMAIN: Once<Mutex<Domain>> = Once::new();
static WAKE: Once<WaitQueue> = Once::new();
static MAJOR: Once<char::MajorIdOwner> = Once::new();
fn domain() -> &'static Mutex<Domain> {
    DOMAIN.get().unwrap()
}

struct Domain {
    next: u64,
    manager: Option<u64>,
    endpoints: BTreeMap<u64, Endpoint>,
}
struct Endpoint {
    owner: Weak<Thread>,
    pollee: Arc<Pollee>,
    mapping: Option<ReceiveArea>,
    queue: VecDeque<Event>,
    prepared: Option<Vec<u8>>,
    outgoing: Option<u64>,
    incoming: Option<u64>,
    looper: bool,
}
struct ReceiveArea {
    base: usize,
    frames: Vec<UFrame>,
    used: Vec<bool>,
}
#[derive(Clone)]
enum Event {
    Complete,
    Dead,
    Request {
        sender: u64,
        transaction: Transaction,
        bytes: Vec<u8>,
    },
    Reply {
        transaction: Transaction,
        bytes: Vec<u8>,
    },
}
impl Domain {
    fn notify(&self) {
        for endpoint in self.endpoints.values() {
            endpoint.pollee.notify(IoEvents::IN | IoEvents::OUT);
        }
        WAKE.get().unwrap().wake_all();
    }
    fn reap(&mut self) {
        let dead: Vec<_> = self
            .endpoints
            .iter()
            .filter_map(|(&id, e)| {
                e.owner
                    .upgrade()
                    .filter(|t| !t.is_exited())
                    .is_none()
                    .then_some(id)
            })
            .collect();
        for id in dead {
            self.close(id);
        }
    }
    fn close(&mut self, id: u64) {
        let Some(old) = self.endpoints.remove(&id) else {
            return;
        };
        old.pollee.notify(IoEvents::HUP | IoEvents::ERR);
        if self.manager == Some(id) {
            self.manager = None;
        }
        for endpoint in self.endpoints.values_mut() {
            // A prepared descriptor may currently be copied outside DOMAIN.
            // Keep its front event and buffer stable even if its sender exits;
            // removing it here would make the copyout commit pop another call.
            let preserve_front = endpoint.prepared.is_some();
            let mut first = true;
            endpoint.queue.retain(|event| {
                let preserve = first && preserve_front;
                first = false;
                preserve || !matches!(event, Event::Request {sender, ..} if *sender == id)
            });
            if endpoint.incoming == Some(id) {
                endpoint.incoming = None;
            }
            if endpoint.outgoing == Some(id)
                && !endpoint
                    .queue
                    .iter()
                    .any(|e| matches!(e, Event::Reply { .. }))
            {
                // This slot was reserved with the outgoing request; at most a
                // completion plus one terminal event can be pending for a caller.
                endpoint.queue.push_back(Event::Dead);
            }
        }
        self.notify();
    }
    fn endpoint(&mut self, id: u64) -> Result<&mut Endpoint> {
        self.endpoints
            .get_mut(&id)
            .ok_or_else(|| Error::with_message(Errno::ECONNREFUSED, "Binder endpoint has closed"))
    }
}
fn close(id: u64) {
    domain().lock().close(id);
}

#[derive(Debug)]
struct BinderDevice {
    id: DeviceId,
}
impl Device for BinderDevice {
    fn type_(&self) -> DeviceType {
        DeviceType::Char
    }
    fn id(&self) -> DeviceId {
        self.id
    }
    fn devtmpfs_meta(&self) -> Option<DevtmpfsNodeMeta> {
        Some(DevtmpfsNodeMeta::new("binder").unwrap())
    }
    fn open(&self) -> Result<Box<dyn PerOpenFileOps>> {
        let owner = current_thread!();
        let process = current!();
        let image = current_userspace!().vmar_snapshot();
        let pollee = Arc::new(Pollee::new());
        let mut d = domain().lock();
        d.reap();
        if d.endpoints.len() >= MAX_ENDPOINTS {
            return_errno!(Errno::ENOSPC);
        }
        let id = d.next;
        d.next = id
            .checked_add(1)
            .ok_or_else(|| Error::with_message(Errno::ENOSPC, "Binder identity space exhausted"))?;
        d.endpoints.insert(
            id,
            Endpoint {
                owner: Arc::downgrade(&owner),
                pollee: pollee.clone(),
                mapping: None,
                queue: VecDeque::new(),
                prepared: None,
                outgoing: None,
                incoming: None,
                looper: false,
            },
        );
        Ok(Box::new(BinderFile {
            id,
            owner: Arc::downgrade(&owner),
            process: Arc::downgrade(&process),
            image,
            pollee,
        }))
    }
}
struct BinderFile {
    id: u64,
    owner: Weak<Thread>,
    process: Weak<Process>,
    image: VmarSnapshot,
    pollee: Arc<Pollee>,
}
impl Drop for BinderFile {
    fn drop(&mut self) {
        close(self.id);
    }
}
impl BinderFile {
    fn check_owner(&self) -> Result<()> {
        if !self
            .owner
            .upgrade()
            .is_some_and(|owner| Arc::ptr_eq(&owner, &current_thread!()))
            || !self
                .process
                .upgrade()
                .is_some_and(|owner| Arc::ptr_eq(&owner, &current!()))
            || !self.image.ptr_eq(&current_userspace!().vmar_snapshot())
        {
            return_errno_with_message!(
                Errno::EPERM,
                "Binder file belongs to its original thread and image"
            );
        }
        Ok(())
    }
    fn commands(&self, wire: &WriteRead) -> Result<Vec<(usize, Command)>> {
        if wire.write_consumed > wire.write_size
            || wire.write_size > MAX_STREAM as u64
            || wire.read_size > MAX_STREAM as u64
            || wire.read_consumed != 0
        {
            return_errno!(Errno::EINVAL);
        }
        let start = wire.write_consumed as usize;
        let size = wire.write_size as usize - start;
        let pointer = (wire.write_buffer as usize)
            .checked_add(start)
            .ok_or_else(|| Error::with_message(Errno::EFAULT, "Binder stream overflow"))?;
        let mut input = vec![0; size];
        current_userspace!().read_bytes(pointer, &mut input)?;
        let mut cursor = 0;
        let mut commands = Vec::new();
        while cursor < input.len() {
            let command = read::<u32>(&input, &mut cursor)?;
            let command = match command {
                TRANSACTION | REPLY => {
                    let mut tr = read::<Transaction>(&input, &mut cursor)?;
                    if tr.offsets_size != 0 || tr.flags != 0 || tr.target != 0 || tr.cookie != 0 {
                        return_errno_with_message!(
                            Errno::EOPNOTSUPP,
                            "Binder objects, flags and nonzero handles unsupported"
                        );
                    }
                    if tr.data_size > PAGE_SIZE as u64 {
                        return_errno!(Errno::EMSGSIZE);
                    }
                    let mut bytes = vec![0; tr.data_size as usize];
                    current_userspace!().read_bytes(tr.buffer as usize, &mut bytes)?;
                    let task = Task::current().unwrap();
                    // Linux synchronous replies have no caller transaction
                    // parent and expose sender_pid=0; effective UID still names
                    // the responding credentials.
                    tr.sender_pid = if command == REPLY {
                        0
                    } else {
                        current!().pid() as i32
                    };
                    tr.sender_euid = task.as_posix_thread().unwrap().credentials().euid().into();
                    tr.buffer = 0;
                    tr.offsets = 0;
                    Command::Send {
                        reply: command == REPLY,
                        transaction: tr,
                        bytes,
                    }
                }
                FREE_BUFFER => Command::Free(read::<u64>(&input, &mut cursor)? as usize),
                ENTER_LOOPER => Command::Enter,
                EXIT_LOOPER => Command::Exit,
                _ => {
                    return_errno_with_message!(Errno::EOPNOTSUPP, "Binder command not implemented")
                }
            };
            if commands.len() == 32 {
                return_errno!(Errno::EMSGSIZE);
            }
            commands.push((start + cursor, command));
        }
        Ok(commands)
    }
    fn execute(&self, command: Command) -> Result<()> {
        let mut d = domain().lock();
        d.reap();
        if d.endpoint(self.id)?.prepared.is_some() {
            return_errno!(Errno::EBUSY);
        }
        match command {
            Command::Enter => {
                let e = d.endpoint(self.id)?;
                if e.looper {
                    return_errno!(Errno::EINVAL);
                }
                e.looper = true;
            }
            Command::Exit => {
                let e = d.endpoint(self.id)?;
                if e.incoming.is_some() || e.outgoing.is_some() {
                    return_errno!(Errno::EBUSY);
                }
                e.looper = false;
            }
            Command::Free(address) => {
                let area =
                    d.endpoint(self.id)?.mapping.as_mut().ok_or_else(|| {
                        Error::with_message(Errno::EINVAL, "Binder has no mapping")
                    })?;
                let offset = address.checked_sub(area.base).ok_or_else(|| {
                    Error::with_message(Errno::EINVAL, "Binder buffer is not owned")
                })?;
                if offset % PAGE_SIZE != 0
                    || offset / PAGE_SIZE >= area.used.len()
                    || !area.used[offset / PAGE_SIZE]
                {
                    return_errno!(Errno::EINVAL);
                }
                area.frames[offset / PAGE_SIZE].write_bytes(0, &[0; PAGE_SIZE])?;
                area.used[offset / PAGE_SIZE] = false;
            }
            Command::Send {
                reply,
                transaction,
                bytes,
            } => {
                let own = d.endpoint(self.id)?;
                if own.mapping.is_none() || own.queue.len() >= MAX_QUEUE {
                    return_errno!(Errno::EAGAIN);
                }
                if reply {
                    let destination = own.incoming.ok_or_else(|| {
                        Error::with_message(Errno::EINVAL, "Binder reply has no incoming call")
                    })?;
                    let peer = d.endpoint(destination)?;
                    if peer.outgoing != Some(self.id) {
                        return_errno!(Errno::EINVAL);
                    }
                    if peer.queue.len() >= MAX_QUEUE {
                        return_errno!(Errno::EAGAIN);
                    }
                    peer.queue.push_back(Event::Reply { transaction, bytes });
                    // The reply is already owned by the caller's queue. Closing
                    // the server now must not append a contradictory dead reply.
                    let own = d.endpoint(self.id)?;
                    own.incoming = None;
                    own.queue.push_back(Event::Complete);
                } else {
                    if own.incoming.is_some() || own.outgoing.is_some() {
                        return_errno!(Errno::EBUSY);
                    }
                    let destination = d.manager.ok_or_else(|| {
                        Error::with_message(Errno::ECONNREFUSED, "Binder has no context manager")
                    })?;
                    if destination == self.id {
                        return_errno!(Errno::EOPNOTSUPP);
                    }
                    let peer = d.endpoint(destination)?;
                    if peer.mapping.is_none() || !peer.looper || peer.queue.len() >= MAX_QUEUE - 1 {
                        return_errno!(Errno::EAGAIN);
                    }
                    peer.queue.push_back(Event::Request {
                        sender: self.id,
                        transaction,
                        bytes,
                    });
                    let own = d.endpoint(self.id)?;
                    own.outgoing = Some(destination);
                    own.queue.push_back(Event::Complete);
                }
            }
        }
        d.notify();
        Ok(())
    }
    fn try_read(&self, pointer: usize, capacity: usize) -> Result<usize> {
        let output = {
            let mut d = domain().lock();
            d.reap();
            let e = d.endpoint(self.id)?;
            if let Some(prepared) = &e.prepared {
                prepared.clone()
            } else {
                let Some(event) = e.queue.front().cloned() else {
                    return_errno!(Errno::EAGAIN);
                };
                let needed = if matches!(event, Event::Request { .. } | Event::Reply { .. }) {
                    68
                } else {
                    4
                };
                if capacity < needed {
                    return_errno!(Errno::ENOSPC);
                }
                let mut output = Vec::with_capacity(needed);
                match event {
                    Event::Complete => {
                        output.extend_from_slice(&BR_TRANSACTION_COMPLETE.to_ne_bytes())
                    }
                    Event::Dead => output.extend_from_slice(&BR_DEAD_REPLY.to_ne_bytes()),
                    Event::Request {
                        sender,
                        mut transaction,
                        bytes,
                    } => {
                        if e.incoming.is_some() {
                            return_errno!(Errno::EBUSY);
                        }
                        let address = e.reserve(&bytes)?;
                        e.incoming = Some(sender);
                        transaction.buffer = address as u64;
                        transaction.offsets =
                            transaction.buffer + transaction.data_size.next_multiple_of(8);
                        output.extend_from_slice(&BR_TRANSACTION.to_ne_bytes());
                        output.extend_from_slice(transaction.as_bytes());
                    }
                    Event::Reply {
                        mut transaction,
                        bytes,
                    } => {
                        transaction.buffer = e.reserve(&bytes)? as u64;
                        transaction.offsets =
                            transaction.buffer + transaction.data_size.next_multiple_of(8);
                        output.extend_from_slice(&BR_REPLY.to_ne_bytes());
                        output.extend_from_slice(transaction.as_bytes());
                    }
                }
                e.prepared = Some(output.clone());
                output
            }
        };
        if capacity < output.len() {
            return_errno!(Errno::ENOSPC);
        }
        current_userspace!().write_bytes(pointer, &output)?;
        let mut d = domain().lock();
        let e = d.endpoint(self.id)?;
        e.prepared = None;
        if matches!(e.queue.pop_front(), Some(Event::Reply { .. } | Event::Dead)) {
            e.outgoing = None;
        }
        d.notify();
        Ok(output.len())
    }
    fn write_read(&self, pointer: usize, nonblocking: bool) -> Result<i32> {
        let mut wire: WriteRead = current_userspace!().read_val(pointer)?;
        let commands = self.commands(&wire)?;
        let outcome = (|| {
            for (consumed, command) in commands {
                self.execute(command)?;
                wire.write_consumed = consumed as u64;
            }
            if wire.read_size > 0 && nonblocking {
                wire.read_consumed =
                    self.try_read(wire.read_buffer as usize, wire.read_size as usize)? as u64;
            } else if wire.read_size > 0 {
                loop {
                    let result = WAKE.get().unwrap().pause_until_or_timeout(
                        || match self.try_read(wire.read_buffer as usize, wire.read_size as usize) {
                            Err(err) if err.error() == Errno::EAGAIN => None,
                            result => Some(result),
                        },
                        &Duration::from_millis(50),
                    );
                    match result {
                        Err(err) if err.error() == Errno::ETIME => continue,
                        Err(err) => return Err(err),
                        Ok(result) => {
                            wire.read_consumed = result? as u64;
                            break;
                        }
                    }
                }
            }
            Ok(0)
        })();
        // Commands already consumed are never repeated by the driver. Even on
        // EINTR/EFAULT, publish progress when the transport remains writable.
        current_userspace!().write_val(pointer, &wire)?;
        outcome
    }
}
impl Endpoint {
    fn reserve(&mut self, bytes: &[u8]) -> Result<usize> {
        let area = self.mapping.as_mut().ok_or_else(|| {
            Error::with_message(Errno::ECONNREFUSED, "Binder receive mapping gone")
        })?;
        let slot = area
            .used
            .iter()
            .position(|used| !used)
            .ok_or_else(|| Error::with_message(Errno::ENOSPC, "Binder receive buffers full"))?;
        area.frames[slot].write_bytes(0, &[0; PAGE_SIZE])?;
        area.frames[slot].write_bytes(0, bytes)?;
        area.used[slot] = true;
        Ok(area.base + slot * PAGE_SIZE)
    }
}
enum Command {
    Enter,
    Exit,
    Free(usize),
    Send {
        reply: bool,
        transaction: Transaction,
        bytes: Vec<u8>,
    },
}
fn read<T: Pod>(input: &[u8], cursor: &mut usize) -> Result<T> {
    let end = cursor
        .checked_add(size_of::<T>())
        .ok_or_else(|| Error::with_message(Errno::EINVAL, "Binder command overflow"))?;
    let value = input
        .get(*cursor..end)
        .map(T::from_bytes)
        .ok_or_else(|| Error::with_message(Errno::EINVAL, "Binder command truncated"))?;
    *cursor = end;
    Ok(value)
}
impl Pollable for BinderFile {
    fn poll(&self, mask: IoEvents, poller: Option<&mut PollHandle>) -> IoEvents {
        if self.check_owner().is_err() {
            return (IoEvents::ERR | IoEvents::HUP) & mask;
        }
        self.pollee.poll_with(mask, poller, || {
            let mut d = domain().lock();
            d.reap();
            match d.endpoints.get(&self.id) {
                None => IoEvents::HUP | IoEvents::ERR,
                Some(e) => {
                    IoEvents::OUT
                        | if e.queue.is_empty() {
                            IoEvents::empty()
                        } else {
                            IoEvents::IN
                        }
                }
            }
        })
    }
}
impl FileOps for BinderFile {
    fn read_at(&self, _: usize, _: &mut VmWriter, _: StatusFlags) -> Result<usize> {
        return_errno!(Errno::EINVAL);
    }
    fn write_at(&self, _: usize, _: &mut VmReader, _: StatusFlags) -> Result<usize> {
        return_errno!(Errno::EINVAL);
    }
}
impl PerOpenFileOps for BinderFile {
    fn check_seekable(&self) -> Result<()> {
        return_errno!(Errno::ESPIPE);
    }
    fn is_offset_aware(&self) -> bool {
        false
    }
    fn mappable(&self, _: FileMmapRequest) -> Result<MappableObject<'_>> {
        self.check_owner()?;
        Ok(MappableObject::Device(self))
    }
    fn ioctl_with_status(&self, path: &Path, raw: RawIoctl, flags: StatusFlags) -> Result<i32> {
        if raw.cmd() != WRITE_READ {
            return self.ioctl(path, raw);
        }
        self.check_owner()?;
        domain().lock().endpoint(self.id)?;
        self.write_read(raw.arg(), flags.contains(StatusFlags::O_NONBLOCK))
    }
    fn ioctl(&self, _: &Path, raw: RawIoctl) -> Result<i32> {
        self.check_owner()?;
        domain().lock().endpoint(self.id)?;
        match raw.cmd() {
            VERSION => {
                current_userspace!().write_val(raw.arg(), &8i32)?;
                Ok(0)
            }
            SET_MAX_THREADS => {
                let value: u32 = current_userspace!().read_val(raw.arg())?;
                if value > 1 {
                    return_errno!(Errno::EOPNOTSUPP);
                }
                Ok(0)
            }
            SET_CONTEXT_MGR => {
                // The legacy ioctl ignores arg (Linux callers commonly pass
                // literal zero), unlike SET_CONTEXT_MGR_EXT's object pointer.
                let task = Task::current().unwrap();
                if !task
                    .as_posix_thread()
                    .unwrap()
                    .credentials()
                    .euid()
                    .is_root()
                {
                    return_errno!(Errno::EPERM);
                }
                let mut d = domain().lock();
                d.reap();
                if d.manager.is_some() {
                    return_errno!(Errno::EBUSY);
                }
                if d.endpoint(self.id)?.mapping.is_none() {
                    return_errno!(Errno::EINVAL);
                }
                d.manager = Some(self.id);
                Ok(0)
            }
            THREAD_EXIT => {
                close(self.id);
                Ok(0)
            }
            WRITE_READ => self.write_read(raw.arg(), false),
            SET_CONTEXT_MGR_EXT => return_errno!(Errno::EOPNOTSUPP),
            _ => return_errno!(Errno::ENOTTY),
        }
    }
}
impl Mappable for BinderFile {
    fn supports_private_mapping(&self) -> bool {
        true
    }
    fn read_only_mapping(&self) -> bool {
        true
    }
    fn map(&self, offset: usize, mut handle: MapHandle) -> Result<Box<dyn MappedObject>> {
        self.check_owner()?;
        if offset != 0 || handle.size() > MAX_MAPPING {
            return_errno!(Errno::EINVAL);
        }
        let mut frames = Vec::new();
        for _ in 0..handle.size() / PAGE_SIZE {
            frames.push(crate::fs::cgroupfs::alloc_anon_frame(true)?);
        }
        let mut d = domain().lock();
        let e = d.endpoint(self.id)?;
        if e.mapping.is_some() {
            return_errno!(Errno::EBUSY);
        }
        for (index, frame) in frames.iter().enumerate() {
            // Do not publish a receive area after fallible page-table
            // admission failed. VMAR removes any mapped prefix on this error;
            // the endpoint stays available for a later successful mmap.
            handle.map_frame(index * PAGE_SIZE, frame.clone())?;
        }
        e.mapping = Some(ReceiveArea {
            base: handle.address(),
            used: vec![false; frames.len().min(MAX_BUFFERS)],
            frames,
        });
        Ok(Box::new(BinderMapping { id: self.id }))
    }
}
#[derive(Debug)]
struct BinderMapping {
    id: u64,
}
impl MappedObject for BinderMapping {
    fn inherit_on_fork(&self) -> bool {
        false
    }
    fn can_remap(&self) -> bool {
        false
    }
    fn on_unmap(&self) {
        close(self.id);
    }
    fn dup_at_offset(&self, _: usize) -> Box<dyn MappedObject> {
        Box::new(Self { id: self.id })
    }
}
pub(super) fn init_in_first_kthread() {
    DOMAIN.call_once(|| {
        Mutex::new(Domain {
            next: 1,
            manager: None,
            endpoints: BTreeMap::new(),
        })
    });
    WAKE.call_once(WaitQueue::new);
    let major = MAJOR.call_once(|| char::allocate_major().unwrap()).get();
    char::register(Arc::new(BinderDevice {
        id: DeviceId::new(major, MinorId::new(0)),
    }))
    .expect("register bounded Binder device");
}
