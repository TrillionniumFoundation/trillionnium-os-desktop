// SPDX-License-Identifier: MPL-2.0
//! Bounded synchronous Binder transactions and owned object references.
//!
//! Bounded actual threads per open, one outgoing call per thread, no nested
//! calls, FD arrays, oneway, or MAC labels.
//! The device node is root:root 0600. This is not Android boot qualification.
//!
//! Lock order: VMAR -> DOMAIN. DOMAIN never acquires VMAR/process locks or
//! copies userspace. Input is snapshotted first; output is prepared under the
//! domain lock and copied after releasing it. Mapping frames are owned, charged
//! UFrames, not user addresses. A failed output copy retains the prepared event.

mod death;
mod files;
mod objects;
mod uapi;
use core::time::Duration;

use death::{Delivery as DeathDelivery, Subscriptions};
use device_id::{DeviceId, MinorId};
use files::{Drain, FileObject, PendingFds, RetainedFile};
use objects::*;
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
const MAX_THREADS: usize = 8;
static DOMAIN: Once<Mutex<Domain>> = Once::new();
static WAKE: Once<WaitQueue> = Once::new();
static MAJOR: Once<char::MajorIdOwner> = Once::new();
fn domain() -> &'static Mutex<Domain> {
    DOMAIN.get().unwrap()
}

struct Domain {
    next: u64,
    next_thread: u64,
    next_call: u64,
    next_node: u64,
    nodes: BTreeMap<u64, Weak<Node>>,
    manager: Option<u64>,
    endpoints: BTreeMap<u64, Endpoint>,
}
struct Endpoint {
    owner: Weak<Process>,
    threads: BTreeMap<u64, Participant>,
    pollee: Arc<Pollee>,
    mapping: Option<ReceiveArea>,
    queue: VecDeque<Queued>,
    prepared: Option<Prepared>,
    preparing: Option<Preparing>,
    nodes: BTreeMap<u64, Arc<Node>>,
    handles: Handles,
    deaths: Subscriptions,
}
struct Participant {
    owner: Weak<Thread>,
    outgoing: Option<Outgoing>,
    incoming: Option<Incoming>,
    looper: bool,
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct Route {
    endpoint: u64,
    thread: u64,
}
#[derive(Clone, Copy)]
struct Outgoing {
    call: u64,
    destination: u64,
}
#[derive(Clone, Copy, PartialEq, Eq)]
struct QueueKey {
    call: u64,
    kind: u8,
}
#[derive(Clone, Copy)]
struct Preparing {
    thread: u64,
    key: QueueKey,
}
#[derive(Clone)]
struct Queued {
    call: u64,
    recipient: Option<u64>,
    event: Event,
}
impl Queued {
    fn key(&self) -> QueueKey {
        QueueKey {
            call: self.call,
            kind: match &self.event {
                Event::Complete => 0,
                Event::Dead => 1,
                Event::Request { .. } => 2,
                Event::Reply { .. } => 3,
            },
        }
    }
}
struct ReceiveArea {
    base: usize,
    frames: Vec<UFrame>,
    used: Vec<Option<Vec<Arc<Reference>>>>,
}
struct Prepared {
    owner: Option<u64>,
    copying: bool,
    buffer: Option<usize>,
    bytes: Vec<u8>,
    action: ReadAction,
    fds: Option<Arc<PendingFds>>,
}
#[derive(Clone, Copy)]
enum ReadAction {
    Queue(QueueKey),
    Node,
    Death(DeathDelivery),
}
#[derive(Clone, Copy)]
struct Incoming {
    sender: Route,
    call: u64,
    accepts_fds: bool,
}
#[derive(Clone)]
enum Event {
    Complete,
    Dead,
    Request {
        sender: Route,
        transaction: Transaction,
        payload: Payload,
    },
    Reply {
        transaction: Transaction,
        payload: Payload,
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
                    .filter(|p| !p.status().is_zombie())
                    .is_none()
                    .then_some(id)
            })
            .collect();
        for id in dead {
            self.close(id);
        }
        let threads: Vec<_> = self
            .endpoints
            .iter()
            .flat_map(|(&id, endpoint)| {
                endpoint.threads.iter().filter_map(move |(&token, thread)| {
                    thread
                        .owner
                        .upgrade()
                        .filter(|t| !t.is_exited())
                        .is_none()
                        .then_some(Route {
                            endpoint: id,
                            thread: token,
                        })
                })
            })
            .collect();
        for route in threads {
            self.retire_thread(route);
        }
        for endpoint in self.endpoints.values_mut() {
            if endpoint.prepared.is_none() {
                endpoint.nodes.retain(|_, node| !node.idle());
            }
        }
        self.nodes.retain(|_, node| node.strong_count() > 0);
    }
    fn participant(&mut self, id: u64, owner: &Arc<Thread>) -> Result<u64> {
        let endpoint = self.endpoint(id)?;
        if let Some((&token, _)) = endpoint.threads.iter().find(|(_, t)| {
            t.owner
                .upgrade()
                .is_some_and(|t| Arc::ptr_eq(&t, owner) && !t.is_exited())
        }) {
            return Ok(token);
        }
        if endpoint.threads.len() >= MAX_THREADS {
            return_errno!(Errno::ENOSPC);
        }
        let token = self.next_thread;
        self.next_thread = token.checked_add(1).ok_or_else(|| {
            Error::with_message(Errno::ENOSPC, "Binder thread identity exhausted")
        })?;
        self.endpoint(id)?.threads.insert(
            token,
            Participant {
                owner: Arc::downgrade(owner),
                outgoing: None,
                incoming: None,
                looper: false,
            },
        );
        Ok(token)
    }
    fn live_call(&self, route: Route, call: u64, destination: u64) -> bool {
        self.endpoints
            .get(&route.endpoint)
            .and_then(|e| e.threads.get(&route.thread))
            .is_some_and(|thread| {
                thread.owner.upgrade().is_some_and(|t| !t.is_exited())
                    && thread
                        .outgoing
                        .is_some_and(|o| o.call == call && o.destination == destination)
            })
    }
    fn dead_reply(&mut self, route: Route, call: u64, destination: u64) {
        if !self.live_call(route, call, destination) {
            return;
        }
        let endpoint = self.endpoints.get_mut(&route.endpoint).unwrap();
        if !endpoint.terminal_queued(route.thread, call) {
            endpoint.queue.push_back(Queued {
                call,
                recipient: Some(route.thread),
                event: Event::Dead,
            });
            debug_assert!(endpoint.budget_used() <= MAX_QUEUE);
        }
    }
    fn retire_thread(&mut self, route: Route) {
        let Some(endpoint) = self.endpoints.get_mut(&route.endpoint) else {
            return;
        };
        let Some(old) = endpoint.threads.remove(&route.thread) else {
            return;
        };
        if endpoint.preparing.is_some_and(|p| p.thread == route.thread) {
            endpoint.preparing = None;
        }
        if endpoint
            .prepared
            .as_ref()
            .is_some_and(|p| p.owner == Some(route.thread))
        {
            if matches!(
                endpoint.prepared.as_ref().unwrap().action,
                ReadAction::Queue(_)
            ) {
                let prepared = endpoint.prepared.take().unwrap();
                if let ReadAction::Queue(key) = prepared.action {
                    endpoint.queue.retain(|q| q.key() != key);
                }
                if let Some(address) = prepared.buffer {
                    if !endpoint.discard_unpublished(address) {
                        self.close(route.endpoint);
                        return;
                    }
                }
            } else {
                // Ref/death work belongs to the process, not the exiting worker.
                // Keep its exact prepared bytes and pending acknowledgement.
                endpoint.prepared.as_mut().unwrap().owner = None;
            }
        }
        endpoint.queue.retain(|q| q.recipient != Some(route.thread));
        for peer in self.endpoints.values_mut() {
            let preserved = peer.preserved_key();
            peer.queue.retain(|q| {
                preserved == Some(q.key())
                    || !matches!(&q.event, Event::Request { sender, .. } if *sender == route)
            });
            for thread in peer.threads.values_mut() {
                if thread
                    .incoming
                    .is_some_and(|incoming| incoming.sender == route)
                {
                    thread.incoming = None;
                }
            }
        }
        if let Some(incoming) = old.incoming {
            self.dead_reply(incoming.sender, incoming.call, route.endpoint);
        }
        self.notify();
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
            endpoint.deaths.owner_closed(id);
            let preserved = endpoint.preserved_key();
            endpoint.queue.retain(|q| {
                preserved == Some(q.key())
                    || !matches!(&q.event, Event::Request { sender, .. } if sender.endpoint == id)
            });
            let dead: Vec<_> = endpoint
                .threads
                .iter_mut()
                .filter_map(|(&token, thread)| {
                    if thread
                        .incoming
                        .is_some_and(|incoming| incoming.sender.endpoint == id)
                    {
                        thread.incoming = None;
                    }
                    thread
                        .outgoing
                        .filter(|o| o.destination == id)
                        .map(|o| (token, o.call))
                })
                .collect();
            for (thread, call) in dead {
                if !endpoint.terminal_queued(thread, call) {
                    endpoint.queue.push_back(Queued {
                        call,
                        recipient: Some(thread),
                        event: Event::Dead,
                    });
                }
            }
            debug_assert!(endpoint.budget_used() <= MAX_QUEUE);
        }
        self.notify();
    }
    fn endpoint(&mut self, id: u64) -> Result<&mut Endpoint> {
        self.endpoints
            .get_mut(&id)
            .ok_or_else(|| Error::with_message(Errno::ECONNREFUSED, "Binder endpoint has closed"))
    }
    fn payload(
        &mut self,
        sender: u64,
        bytes: Vec<u8>,
        offsets: Vec<u64>,
        objects: Vec<(usize, FlatObject)>,
        files: Vec<FileObject>,
        target: Option<Arc<Node>>,
    ) -> Result<Payload> {
        let endpoint = self.endpoints.get(&sender).unwrap();
        let buffers = &endpoint.mapping.as_ref().unwrap().used;
        let mut new_nodes: BTreeMap<u64, Arc<Node>> = BTreeMap::new();
        let mut next = self.next_node;
        let mut translated = Vec::new();
        let mut deltas: BTreeMap<u64, (Arc<Node>, usize)> = BTreeMap::new();
        for (offset, object) in objects {
            let node = if matches!(object.kind, TYPE_BINDER | TYPE_WEAK_BINDER) {
                if let Some(node) = endpoint
                    .nodes
                    .get(&object.value)
                    .or_else(|| new_nodes.get(&object.value))
                {
                    if node.cookie != object.cookie || node.flags != object.flags {
                        return_errno!(Errno::EINVAL);
                    }
                    node.clone()
                } else {
                    if endpoint.nodes.len() + new_nodes.len() == MAX_LOCAL_NODES
                        || self.nodes.len() + new_nodes.len() == MAX_NODES
                    {
                        return_errno!(Errno::ENOSPC);
                    }
                    let node = Arc::new(Node::new(
                        next,
                        sender,
                        object.value,
                        object.cookie,
                        object.flags,
                    ));
                    next = next.checked_add(1).ok_or_else(|| {
                        Error::with_message(Errno::ENOSPC, "Binder node identity exhausted")
                    })?;
                    new_nodes.insert(object.value, node.clone());
                    node
                }
            } else {
                endpoint
                    .handles
                    .resolve(object.value, object.kind == TYPE_HANDLE, buffers)?
            };
            deltas.entry(node.id).or_insert((node.clone(), 0)).1 += 1;
            translated.push((
                offset,
                node,
                matches!(object.kind, TYPE_BINDER | TYPE_HANDLE),
            ));
        }
        if let Some(node) = &target {
            deltas.entry(node.id).or_insert((node.clone(), 0)).1 += 1;
        }
        for (node, count) in deltas.values() {
            node.preflight(*count)?;
        }
        // All protocol and admission errors precede publication. References
        // below are infallible and move with the queue/receive buffer.
        self.next_node = next;
        for (pointer, node) in new_nodes {
            self.nodes.insert(node.id, Arc::downgrade(&node));
            self.endpoints
                .get_mut(&sender)
                .unwrap()
                .nodes
                .insert(pointer, node);
        }
        Ok(Payload {
            bytes,
            offsets,
            files,
            objects: translated
                .into_iter()
                .map(|(offset, node, strong)| Object {
                    offset,
                    reference: Reference::new(node, strong),
                })
                .collect(),
            target: target.map(|node| Reference::new(node, true)),
        })
    }
}
fn close(id: u64) {
    domain().lock().close(id);
}

/// Called after the actual Thread exit flag is published and TaskSet/cgroup
/// locks are released, before clear_child_tid can wake a joining sibling.
/// Retained Arcs cannot keep an exited participant or its caller suspended.
pub(crate) fn thread_exited(owner: &Arc<Thread>) {
    let _drain = Drain;
    let Some(domain) = DOMAIN.get() else {
        return;
    };
    let mut d = domain.lock();
    let routes: Vec<_> = d
        .endpoints
        .iter()
        .flat_map(|(&id, endpoint)| {
            endpoint
                .threads
                .iter()
                .filter_map(move |(&token, participant)| {
                    participant
                        .owner
                        .upgrade()
                        .is_some_and(|thread| Arc::ptr_eq(&thread, owner))
                        .then_some(Route {
                            endpoint: id,
                            thread: token,
                        })
                })
        })
        .collect();
    for route in routes {
        d.retire_thread(route);
    }
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
        let _drain = Drain;
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
                owner: Arc::downgrade(&process),
                threads: BTreeMap::new(),
                pollee: pollee.clone(),
                mapping: None,
                queue: VecDeque::new(),
                prepared: None,
                preparing: None,
                nodes: BTreeMap::new(),
                handles: Handles::default(),
                deaths: Subscriptions::default(),
            },
        );
        Ok(Box::new(BinderFile {
            id,
            process: Arc::downgrade(&process),
            image,
            pollee,
        }))
    }
}
struct BinderFile {
    id: u64,
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
            .process
            .upgrade()
            .is_some_and(|owner| Arc::ptr_eq(&owner, &current!()))
            || !self.image.ptr_eq(&current_userspace!().vmar_snapshot())
        {
            return_errno_with_message!(
                Errno::EPERM,
                "Binder file belongs to its original process and image"
            );
        }
        Ok(())
    }
    fn participant(&self, d: &mut Domain) -> Result<u64> {
        d.reap();
        d.participant(self.id, &current_thread!())
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
                    if tr.flags & !TF_ACCEPT_FDS != 0
                        || tr.cookie != 0
                        || (command == REPLY && tr.target != 0)
                    {
                        return_errno_with_message!(
                            Errno::EOPNOTSUPP,
                            "Binder flags or reply target unsupported"
                        );
                    }
                    if tr.data_size > PAGE_SIZE as u64 || tr.offsets_size > (MAX_OBJECTS * 8) as u64
                    {
                        return_errno!(Errno::EMSGSIZE);
                    }
                    if (tr.offsets_size != 0 && tr.data_size < size_of::<FlatObject>() as u64)
                        || tr.offsets_size % 8 != 0
                        || tr.data_size.next_multiple_of(8) + tr.offsets_size > PAGE_SIZE as u64
                    {
                        return_errno!(Errno::EINVAL);
                    }
                    let mut bytes = vec![0; tr.data_size as usize];
                    current_userspace!().read_bytes(tr.buffer as usize, &mut bytes)?;
                    let mut raw_offsets = vec![0; tr.offsets_size as usize];
                    current_userspace!().read_bytes(tr.offsets as usize, &mut raw_offsets)?;
                    let mut offsets = Vec::new();
                    let mut objects = Vec::new();
                    let mut files = Vec::new();
                    let mut cursor = 0;
                    let mut previous_end = 0;
                    while cursor < raw_offsets.len() {
                        let offset = read::<u64>(&raw_offsets, &mut cursor)?;
                        let offset_usize = usize::try_from(offset).map_err(|_| {
                            Error::with_message(Errno::EINVAL, "Binder object offset overflow")
                        })?;
                        if offset_usize % 8 != 0 || offset_usize < previous_end {
                            return_errno!(Errno::EINVAL);
                        }
                        let mut object_end = offset_usize;
                        let object = read::<FlatObject>(&bytes, &mut object_end)?;
                        if !matches!(
                            object.kind,
                            TYPE_BINDER
                                | TYPE_WEAK_BINDER
                                | TYPE_HANDLE
                                | TYPE_WEAK_HANDLE
                                | TYPE_FD
                        ) || object.flags & !ACCEPTS_FDS != 0
                        {
                            return_errno!(Errno::EOPNOTSUPP);
                        }
                        if matches!(object.kind, TYPE_HANDLE | TYPE_WEAK_HANDLE)
                            && (object.value > u32::MAX as u64 || object.cookie != 0)
                        {
                            return_errno!(Errno::EINVAL);
                        }
                        offsets.push(offset);
                        if object.kind == TYPE_FD {
                            if object.flags != 0
                                || object.cookie != 0
                                || object.value > u32::MAX as u64
                            {
                                return_errno!(Errno::EINVAL);
                            }
                            files.push(FileObject {
                                offset: offset_usize,
                                file: RetainedFile::snapshot(object.value)?,
                            });
                        } else {
                            objects.push((offset_usize, object));
                        }
                        previous_end = object_end;
                    }
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
                        offsets,
                        objects,
                        files,
                    }
                }
                INCREFS | ACQUIRE | RELEASE | DECREFS => Command::Reference {
                    command,
                    handle: read::<u32>(&input, &mut cursor)?,
                },
                INCREFS_DONE | ACQUIRE_DONE => Command::Done {
                    strong: command == ACQUIRE_DONE,
                    object: read::<PtrCookie>(&input, &mut cursor)?,
                },
                REQUEST_DEATH_NOTIFICATION | CLEAR_DEATH_NOTIFICATION => Command::Death {
                    request: command == REQUEST_DEATH_NOTIFICATION,
                    handle: read::<u32>(&input, &mut cursor)?,
                    cookie: read::<u64>(&input, &mut cursor)?,
                },
                DEAD_BINDER_DONE => Command::DeathDone(read::<u64>(&input, &mut cursor)?),
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
    fn wait_active_preparation(&self) -> Result<()> {
        match WAKE.get().unwrap().pause_until_or_timeout(
            || {
                let d = domain().lock();
                d.endpoints
                    .get(&self.id)
                    .is_none_or(|e| !e.active_preparation())
                    .then_some(())
            },
            &Duration::from_millis(50),
        ) {
            Err(error) if error.error() == Errno::ETIME => Ok(()),
            result => result,
        }
    }
    fn execute(&self, command: Command, nonblocking: bool) -> Result<()> {
        let (mut d, thread) = loop {
            let mut d = domain().lock();
            let thread = self.participant(&mut d)?;
            let e = d.endpoint(self.id)?;
            if e.active_preparation() {
                if nonblocking {
                    return_errno!(Errno::EAGAIN);
                }
                // Keep the original command unpublished while a sibling
                // finishes its active copy; no transaction is resent.
                drop(d);
                self.wait_active_preparation()?;
                continue;
            }
            if e.prepared.is_some() {
                return_errno!(Errno::EBUSY);
            }
            break (d, thread);
        };
        match command {
            Command::Enter => {
                let e = d.endpoint(self.id)?.threads.get_mut(&thread).unwrap();
                if e.looper {
                    return_errno!(Errno::EINVAL);
                }
                e.looper = true;
            }
            Command::Exit => {
                let e = d.endpoint(self.id)?.threads.get_mut(&thread).unwrap();
                if e.incoming.is_some() || e.outgoing.is_some() {
                    return_errno!(Errno::EBUSY);
                }
                e.looper = false;
            }
            Command::Death {
                request,
                handle,
                cookie,
            } => {
                let e = d.endpoint(self.id)?;
                let buffers = &e
                    .mapping
                    .as_ref()
                    .ok_or_else(|| Error::with_message(Errno::EINVAL, "Binder has no mapping"))?
                    .used;
                let node = e.handles.resolve(handle as u64, false, buffers)?;
                if request {
                    let alive = d.endpoints.contains_key(&node.owner);
                    d.endpoint(self.id)?
                        .deaths
                        .request(handle, node, cookie, alive)?;
                } else {
                    d.endpoint(self.id)?.deaths.clear(handle, cookie)?;
                }
            }
            Command::DeathDone(cookie) => d.endpoint(self.id)?.deaths.done(cookie)?,
            Command::Reference { command, handle } => {
                let e = d.endpoint(self.id)?;
                let buffers = &e
                    .mapping
                    .as_ref()
                    .ok_or_else(|| Error::with_message(Errno::EINVAL, "Binder has no mapping"))?
                    .used;
                // A weak-only handle cannot be promoted with BC_ACQUIRE.
                // Strong commands require an existing strong contribution.
                let node = e.handles.resolve(
                    handle as u64,
                    matches!(command, ACQUIRE | RELEASE),
                    buffers,
                )?;
                if command == ACQUIRE && !d.endpoints.contains_key(&node.owner) {
                    return_errno!(Errno::ECONNREFUSED);
                }
                let e = d.endpoint(self.id)?;
                e.handles.change(handle, command, node)?;
                e.prune_handles();
            }
            Command::Done { strong, object } => {
                let node = d
                    .endpoint(self.id)?
                    .nodes
                    .get(&object.pointer)
                    .ok_or_else(|| {
                        Error::with_message(Errno::EINVAL, "Unknown Binder owner pointer")
                    })?;
                node.acknowledge(strong, object.cookie)?;
            }
            Command::Free(address) => {
                let e = d.endpoint(self.id)?;
                let area = e
                    .mapping
                    .as_mut()
                    .ok_or_else(|| Error::with_message(Errno::EINVAL, "Binder has no mapping"))?;
                let offset = address.checked_sub(area.base).ok_or_else(|| {
                    Error::with_message(Errno::EINVAL, "Binder buffer is not owned")
                })?;
                if offset % PAGE_SIZE != 0
                    || offset / PAGE_SIZE >= area.used.len()
                    || area.used[offset / PAGE_SIZE].is_none()
                {
                    return_errno!(Errno::EINVAL);
                }
                area.frames[offset / PAGE_SIZE].write_bytes(0, &[0; PAGE_SIZE])?;
                area.used[offset / PAGE_SIZE] = None;
                e.prune_handles();
            }
            Command::Send {
                reply,
                mut transaction,
                bytes,
                offsets,
                objects,
                files,
            } => {
                let own = d.endpoint(self.id)?;
                if own.mapping.is_none() {
                    return_errno!(Errno::EAGAIN);
                }
                let participant = own.threads.get(&thread).unwrap();
                if reply {
                    let incoming = participant.incoming.ok_or_else(|| {
                        Error::with_message(
                            Errno::EINVAL,
                            "Binder reply has no incoming call on this thread",
                        )
                    })?;
                    if !files.is_empty() && !incoming.accepts_fds {
                        return_errno!(Errno::EPERM);
                    }
                    if !d.live_call(incoming.sender, incoming.call, self.id) {
                        return_errno!(Errno::EINVAL);
                    }
                    if d.endpoint(incoming.sender.endpoint)?
                        .terminal_queued(incoming.sender.thread, incoming.call)
                    {
                        return_errno!(Errno::EINVAL);
                    }
                    // Admission reserved both the caller's terminal slot and
                    // this receiver's completion slot. Publication consumes
                    // those reservations without a new capacity race.
                    let payload = d.payload(self.id, bytes, offsets, objects, files, None)?;
                    let peer = d.endpoint(incoming.sender.endpoint)?;
                    peer.queue.push_back(Queued {
                        call: incoming.call,
                        recipient: Some(incoming.sender.thread),
                        event: Event::Reply {
                            transaction,
                            payload,
                        },
                    });
                    debug_assert!(peer.budget_used() <= MAX_QUEUE);
                    let own = d.endpoint(self.id)?;
                    own.threads.get_mut(&thread).unwrap().incoming = None;
                    own.queue.push_back(Queued {
                        call: incoming.call,
                        recipient: Some(thread),
                        event: Event::Complete,
                    });
                    debug_assert!(own.budget_used() <= MAX_QUEUE);
                } else {
                    if participant.incoming.is_some() || participant.outgoing.is_some() {
                        return_errno!(Errno::EBUSY);
                    }
                    if own.budget_used() > MAX_QUEUE - 2 {
                        return_errno!(Errno::EAGAIN);
                    }
                    let target = if transaction.target == 0 {
                        None
                    } else {
                        Some(own.handles.resolve(
                            transaction.target,
                            true,
                            &own.mapping.as_ref().unwrap().used,
                        )?)
                    };
                    if !files.is_empty()
                        && !target
                            .as_ref()
                            .is_some_and(|node| node.flags & ACCEPTS_FDS != 0)
                    {
                        return_errno!(Errno::EPERM);
                    }
                    let call = d.next_call;
                    d.next_call = call.checked_add(1).ok_or_else(|| {
                        Error::with_message(Errno::ENOSPC, "Binder call identity exhausted")
                    })?;
                    let destination = if let Some(node) = &target {
                        if !d.endpoints.contains_key(&node.owner) {
                            let own = d.endpoint(self.id)?;
                            own.threads.get_mut(&thread).unwrap().outgoing = Some(Outgoing {
                                call,
                                destination: node.owner,
                            });
                            own.queue.push_back(Queued {
                                call,
                                recipient: Some(thread),
                                event: Event::Complete,
                            });
                            own.queue.push_back(Queued {
                                call,
                                recipient: Some(thread),
                                event: Event::Dead,
                            });
                            d.notify();
                            return Ok(());
                        }
                        transaction.target = node.pointer;
                        transaction.cookie = node.cookie;
                        node.owner
                    } else {
                        d.manager.ok_or_else(|| {
                            Error::with_message(
                                Errno::ECONNREFUSED,
                                "Binder has no context manager",
                            )
                        })?
                    };
                    if destination == self.id {
                        return_errno!(Errno::EOPNOTSUPP);
                    }
                    let peer = d.endpoint(destination)?;
                    if peer.mapping.is_none()
                        || !peer.threads.values().any(|t| t.looper)
                        || peer.budget_used() >= MAX_QUEUE - 1
                    {
                        return_errno!(Errno::EAGAIN);
                    }
                    let payload = d.payload(self.id, bytes, offsets, objects, files, target)?;
                    d.endpoint(destination)?.queue.push_back(Queued {
                        call,
                        recipient: None,
                        event: Event::Request {
                            sender: Route {
                                endpoint: self.id,
                                thread,
                            },
                            transaction,
                            payload,
                        },
                    });
                    let own = d.endpoint(self.id)?;
                    own.threads.get_mut(&thread).unwrap().outgoing =
                        Some(Outgoing { call, destination });
                    own.queue.push_back(Queued {
                        call,
                        recipient: Some(thread),
                        event: Event::Complete,
                    });
                    debug_assert!(own.budget_used() <= MAX_QUEUE);
                }
            }
        }
        d.notify();
        Ok(())
    }
    fn try_read(&self, pointer: usize, capacity: usize) -> Result<usize> {
        // One explicit endpoint-wide preparation slot remains in D1. Its
        // transaction descriptor and FD reservations never migrate to a sibling.
        let (thread, files) = {
            let mut d = domain().lock();
            let thread = self.participant(&mut d)?;
            let e = d.endpoint(self.id)?;
            if e.preparing.is_some() {
                return_errno!(Errno::EAGAIN);
            }
            if let Some(prepared) = e.prepared.as_mut() {
                if prepared.owner.is_some_and(|owner| owner != thread) {
                    if prepared.copying {
                        return_errno!(Errno::EAGAIN);
                    }
                    return_errno!(Errno::EBUSY);
                }
                prepared.owner = Some(thread);
                (thread, None)
            } else if e.nodes.values().any(|node| node.has_work()) || e.deaths.has_work() {
                (thread, None)
            } else {
                let files = e.read_index(thread).and_then(|index| {
                    let queued = &e.queue[index];
                    match &queued.event {
                        Event::Request { payload, .. } | Event::Reply { payload, .. }
                            if !payload.files.is_empty() =>
                        {
                            Some((queued.key(), payload.files.clone()))
                        }
                        _ => None,
                    }
                });
                if let Some((key, files)) = files {
                    if capacity < 68 {
                        return_errno!(Errno::ENOSPC);
                    }
                    e.preparing = Some(Preparing { thread, key });
                    (thread, Some(files))
                } else {
                    (thread, None)
                }
            }
        };
        let new_fds = if let Some(files) = files {
            match PendingFds::reserve(files) {
                Ok(fds) => Some(fds),
                Err(error) => {
                    let mut d = domain().lock();
                    if let Some(e) = d.endpoints.get_mut(&self.id) {
                        if e.preparing.is_some_and(|p| p.thread == thread) {
                            e.preparing = None;
                        }
                    }
                    d.notify();
                    return Err(error);
                }
            }
        } else {
            None
        };
        let (output, fds) = {
            let mut d = domain().lock();
            d.reap();
            let e = d.endpoint(self.id)?;
            if !e.threads.contains_key(&thread) {
                return_errno!(Errno::ECONNREFUSED);
            }
            let reserved_key = if new_fds.is_some() {
                let preparing = e.preparing.take().ok_or_else(|| {
                    Error::with_message(Errno::ECONNREFUSED, "Binder preparation retired")
                })?;
                // Wake on every completion/failure of the unlocked FD stage,
                // including a later receive-buffer admission failure.
                e.pollee.notify(IoEvents::IN | IoEvents::OUT);
                WAKE.get().unwrap().wake_all();
                if preparing.thread != thread {
                    return_errno!(Errno::EBUSY);
                }
                Some(preparing.key)
            } else {
                if e.preparing.is_some() {
                    return_errno!(Errno::EAGAIN);
                }
                None
            };
            if e.prepared
                .as_ref()
                .is_some_and(|p| p.owner.is_some_and(|owner| owner != thread))
            {
                if e.prepared.as_ref().unwrap().copying {
                    return_errno!(Errno::EAGAIN);
                }
                return_errno!(Errno::EBUSY);
            }
            if e.prepared.is_none() {
                if new_fds.is_none() && e.nodes.values().any(|node| node.has_work()) {
                    if capacity < 20 {
                        return_errno!(Errno::ENOSPC);
                    }
                    let (command, object) = e
                        .nodes
                        .values()
                        .find_map(|node| node.prepare_work())
                        .unwrap();
                    let mut bytes = command.to_ne_bytes().to_vec();
                    bytes.extend_from_slice(object.as_bytes());
                    e.prepared = Some(Prepared {
                        owner: Some(thread),
                        copying: false,
                        buffer: None,
                        bytes,
                        action: ReadAction::Node,
                        fds: None,
                    });
                } else if new_fds.is_none() && e.deaths.has_work() {
                    if capacity < 12 {
                        return_errno!(Errno::ENOSPC);
                    }
                    let delivery = e.deaths.prepare().unwrap();
                    let mut bytes = delivery.command().to_ne_bytes().to_vec();
                    bytes.extend_from_slice(&delivery.cookie.to_ne_bytes());
                    e.prepared = Some(Prepared {
                        owner: Some(thread),
                        copying: false,
                        buffer: None,
                        bytes,
                        action: ReadAction::Death(delivery),
                        fds: None,
                    });
                } else {
                    let index = if let Some(key) = reserved_key {
                        e.queue.iter().position(|queued| queued.key() == key)
                    } else {
                        e.read_index(thread)
                    }
                    .ok_or_else(|| {
                        Error::with_message(Errno::EAGAIN, "No Binder work for this actual thread")
                    })?;
                    let queued = e.queue[index].clone();
                    let key = queued.key();
                    let needed =
                        if matches!(&queued.event, Event::Request { .. } | Event::Reply { .. }) {
                            68
                        } else {
                            4
                        };
                    if capacity < needed {
                        return_errno!(Errno::ENOSPC);
                    }
                    let sender_alive = match &queued.event {
                        Event::Request { sender, .. } => d.live_call(*sender, queued.call, self.id),
                        _ => true,
                    };
                    let e = d.endpoint(self.id)?;
                    let mut output = Vec::with_capacity(needed);
                    let mut buffer = None;
                    match queued.event {
                        Event::Complete => {
                            output.extend_from_slice(&BR_TRANSACTION_COMPLETE.to_ne_bytes())
                        }
                        Event::Dead => output.extend_from_slice(&BR_DEAD_REPLY.to_ne_bytes()),
                        Event::Request {
                            sender,
                            mut transaction,
                            payload,
                        } => {
                            let participant = e.threads.get(&thread).unwrap();
                            if participant.incoming.is_some()
                                || participant.outgoing.is_some()
                                || !participant.looper
                            {
                                return_errno!(Errno::EBUSY);
                            }
                            if !payload.files.is_empty() && new_fds.is_none() {
                                return_errno!(Errno::EAGAIN);
                            }
                            let address = e.reserve(self.id, &payload, new_fds.as_deref())?;
                            buffer = Some(address);
                            transaction.buffer = address as u64;
                            transaction.offsets =
                                transaction.buffer + transaction.data_size.next_multiple_of(8);
                            e.threads.get_mut(&thread).unwrap().incoming =
                                sender_alive.then_some(Incoming {
                                    sender,
                                    call: queued.call,
                                    accepts_fds: transaction.flags & TF_ACCEPT_FDS != 0,
                                });
                            debug_assert!(e.budget_used() <= MAX_QUEUE);
                            output.extend_from_slice(&BR_TRANSACTION.to_ne_bytes());
                            output.extend_from_slice(transaction.as_bytes());
                        }
                        Event::Reply {
                            mut transaction,
                            payload,
                        } => {
                            if !e
                                .threads
                                .get(&thread)
                                .unwrap()
                                .outgoing
                                .is_some_and(|o| o.call == queued.call)
                            {
                                return_errno!(Errno::EINVAL);
                            }
                            if !payload.files.is_empty() && new_fds.is_none() {
                                return_errno!(Errno::EAGAIN);
                            }
                            let address = e.reserve(self.id, &payload, new_fds.as_deref())?;
                            buffer = Some(address);
                            transaction.buffer = address as u64;
                            transaction.offsets =
                                transaction.buffer + transaction.data_size.next_multiple_of(8);
                            output.extend_from_slice(&BR_REPLY.to_ne_bytes());
                            output.extend_from_slice(transaction.as_bytes());
                        }
                    }
                    e.prepared = Some(Prepared {
                        owner: Some(thread),
                        copying: false,
                        buffer,
                        bytes: output,
                        action: ReadAction::Queue(key),
                        fds: new_fds.clone(),
                    });
                }
            }
            let prepared = d.endpoint(self.id)?.prepared.as_mut().unwrap();
            if capacity < prepared.bytes.len() {
                return_errno!(Errno::ENOSPC);
            }
            prepared.owner = Some(thread);
            prepared.copying = true;
            (prepared.bytes.clone(), prepared.fds.clone())
        };
        if let Err(error) = current_userspace!().write_bytes(pointer, &output) {
            let mut d = domain().lock();
            if let Some(endpoint) = d.endpoints.get_mut(&self.id) {
                if let Some(prepared) = &mut endpoint.prepared {
                    if prepared.owner == Some(thread) {
                        prepared.copying = false;
                    }
                }
            }
            d.notify();
            return Err(error.into());
        }
        {
            let mut d = domain().lock();
            let e = d.endpoint(self.id)?;
            if !e.prepared.as_ref().is_some_and(|p| p.owner == Some(thread)) {
                return_errno!(Errno::ECONNREFUSED);
            }
            e.pollee.notify(IoEvents::IN | IoEvents::OUT);
            WAKE.get().unwrap().wake_all();
            match e.prepared.take().unwrap().action {
                ReadAction::Queue(key) => {
                    let index = e
                        .queue
                        .iter()
                        .position(|queued| queued.key() == key)
                        .ok_or_else(|| {
                            Error::with_message(
                                Errno::ECONNREFUSED,
                                "Prepared Binder event retired",
                            )
                        })?;
                    let queued = e.queue.remove(index).unwrap();
                    if matches!(queued.event, Event::Reply { .. } | Event::Dead) {
                        let participant = e.threads.get_mut(&thread).unwrap();
                        if participant.outgoing.is_some_and(|o| o.call == queued.call) {
                            participant.outgoing = None;
                        }
                    }
                }
                ReadAction::Death(delivery) => e.deaths.commit(delivery)?,
                ReadAction::Node => (),
            }
            d.notify();
        }
        if let Some(fds) = fds {
            fds.install();
        }
        Ok(output.len())
    }
    fn write_read(&self, pointer: usize, nonblocking: bool) -> Result<i32> {
        let _drain = Drain;
        let mut wire: WriteRead = current_userspace!().read_val(pointer)?;
        let commands = self.commands(&wire)?;
        let outcome = (|| {
            for (consumed, command) in commands {
                self.execute(command, nonblocking)?;
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
    fn active_preparation(&self) -> bool {
        self.preparing.is_some() || self.prepared.as_ref().is_some_and(|p| p.copying)
    }
    fn terminal_queued(&self, thread: u64, call: u64) -> bool {
        self.queue.iter().any(|q| {
            q.recipient == Some(thread)
                && q.call == call
                && matches!(q.event, Event::Reply { .. } | Event::Dead)
        })
    }
    fn budget_used(&self) -> usize {
        self.queue.len()
            + self
                .threads
                .iter()
                .map(|(&token, thread)| {
                    usize::from(thread.incoming.is_some())
                        + usize::from(
                            thread
                                .outgoing
                                .is_some_and(|call| !self.terminal_queued(token, call.call)),
                        )
                })
                .sum::<usize>()
    }
    fn read_index(&self, thread: u64) -> Option<usize> {
        let participant = self.threads.get(&thread)?;
        self.queue.iter().position(|queued| match queued.recipient {
            Some(recipient) => recipient == thread,
            None => {
                participant.looper
                    && participant.incoming.is_none()
                    && participant.outgoing.is_none()
                    && matches!(queued.event, Event::Request { .. })
            }
        })
    }
    fn preserved_key(&self) -> Option<QueueKey> {
        self.prepared
            .as_ref()
            .and_then(|p| match p.action {
                ReadAction::Queue(key) => Some(key),
                _ => None,
            })
            .or_else(|| self.preparing.map(|p| p.key))
    }
    fn discard_unpublished(&mut self, address: usize) -> bool {
        let Some(area) = &mut self.mapping else {
            return false;
        };
        let Some(offset) = address.checked_sub(area.base) else {
            return false;
        };
        let slot = offset / PAGE_SIZE;
        if offset % PAGE_SIZE != 0 || slot >= area.used.len() || area.used[slot].is_none() {
            return false;
        }
        if area.frames[slot].write_bytes(0, &[0; PAGE_SIZE]).is_err() {
            return false;
        }
        area.used[slot] = None;
        self.prune_handles();
        true
    }
    fn prune_handles(&mut self) {
        if let Some(area) = &self.mapping {
            let removed = self.handles.prune(&area.used);
            self.deaths.cancel_handles(&removed);
        }
    }
    fn reserve(&mut self, id: u64, payload: &Payload, fds: Option<&PendingFds>) -> Result<usize> {
        if !payload.files.is_empty() && fds.is_none() {
            return_errno!(Errno::EAGAIN);
        }
        let area = self.mapping.as_mut().ok_or_else(|| {
            Error::with_message(Errno::ECONNREFUSED, "Binder receive mapping gone")
        })?;
        let slot = area
            .used
            .iter()
            .position(Option::is_none)
            .ok_or_else(|| Error::with_message(Errno::ENOSPC, "Binder receive buffers full"))?;
        // Draft descriptor allocation makes malformed/full handle delivery
        // atomic. A failed prepare publishes neither descriptors nor refs.
        let mut handles = self.handles.clone();
        let mut bytes = payload.bytes.clone();
        for object in &payload.objects {
            let reference = &object.reference;
            let node = &reference.node;
            let local = node.owner == id;
            let flat = FlatObject {
                kind: match (local, reference.strong) {
                    (true, true) => TYPE_BINDER,
                    (true, false) => TYPE_WEAK_BINDER,
                    (false, true) => TYPE_HANDLE,
                    (false, false) => TYPE_WEAK_HANDLE,
                },
                flags: node.flags,
                value: if local {
                    node.pointer
                } else {
                    handles.descriptor(node)? as u64
                },
                cookie: if local { node.cookie } else { 0 },
            };
            bytes[object.offset..object.offset + size_of::<FlatObject>()]
                .copy_from_slice(flat.as_bytes());
        }
        if let Some(fds) = fds {
            fds.encode(&mut bytes);
        }
        bytes.resize(bytes.len().next_multiple_of(8), 0);
        for offset in &payload.offsets {
            bytes.extend_from_slice(&offset.to_ne_bytes());
        }
        area.frames[slot].write_bytes(0, &[0; PAGE_SIZE])?;
        area.frames[slot].write_bytes(0, &bytes)?;
        area.used[slot] = Some(payload.references());
        self.handles = handles;
        Ok(area.base + slot * PAGE_SIZE)
    }
}
enum Command {
    Enter,
    Exit,
    Free(usize),
    Death {
        request: bool,
        handle: u32,
        cookie: u64,
    },
    DeathDone(u64),
    Reference {
        command: u32,
        handle: u32,
    },
    Done {
        strong: bool,
        object: PtrCookie,
    },
    Send {
        reply: bool,
        transaction: Transaction,
        bytes: Vec<u8>,
        offsets: Vec<u64>,
        objects: Vec<(usize, FlatObject)>,
        files: Vec<FileObject>,
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
        let _drain = Drain;
        if self.check_owner().is_err() {
            return (IoEvents::ERR | IoEvents::HUP) & mask;
        }
        self.pollee.poll_with(mask, poller, || {
            let mut d = domain().lock();
            let thread = match self.participant(&mut d) {
                Ok(thread) => thread,
                Err(_) => return IoEvents::HUP | IoEvents::ERR,
            };
            match d.endpoints.get(&self.id) {
                None => IoEvents::HUP | IoEvents::ERR,
                Some(e) => {
                    IoEvents::OUT
                        | if e.preparing.is_none()
                            && match &e.prepared {
                                Some(p) => p.owner.is_none_or(|owner| owner == thread),
                                None => {
                                    e.read_index(thread).is_some()
                                        || e.nodes.values().any(|node| node.has_work())
                                        || e.deaths.has_work()
                                }
                            }
                        {
                            IoEvents::IN
                        } else {
                            IoEvents::empty()
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
                // D1 implements manually entered workers. An automatic pool
                // quota must not return success before spawn/register exists.
                if value != 0 {
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
                let mut d = domain().lock();
                let thread = self.participant(&mut d)?;
                d.retire_thread(Route {
                    endpoint: self.id,
                    thread,
                });
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
            used: vec![None; frames.len().min(MAX_BUFFERS)],
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
    files::init();
    DOMAIN.call_once(|| {
        Mutex::new(Domain {
            next: 1,
            next_thread: 1,
            next_call: 1,
            next_node: 1,
            nodes: BTreeMap::new(),
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
