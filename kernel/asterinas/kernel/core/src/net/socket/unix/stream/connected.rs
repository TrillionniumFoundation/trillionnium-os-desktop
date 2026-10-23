// SPDX-License-Identifier: MPL-2.0

use core::{
    num::Wrapping,
    sync::atomic::{AtomicBool, Ordering},
};

use spin::Once;

use crate::{
    events::IoEvents,
    fs::utils::{Endpoint, EndpointState},
    net::socket::{
        unix::{
            UnixSocketAddr,
            addr::UnixSocketAddrBound,
            cred::SocketCred,
            ctrl_msg::AuxiliaryData,
            ownership::{Lease, Node},
        },
        util::{ControlMessage, RecvFlags, RecvOutput, SockShutdownCmd},
    },
    prelude::*,
    process::signal::Pollee,
    util::{
        MultiRead, MultiWrite,
        ring_buffer::{
            ProducerU8Ext, RingBufferU8Ext, UserRbConsumer, UserRbProducer, UserRingBuffer,
            new_user_ring_buffer,
        },
    },
};

/// Both directions are admitted before any socket state or backlog is changed.
/// Failure of the second allocation drops and refunds the first original segment.
pub(super) struct Buffers {
    outgoing: UserRingBuffer,
    incoming: UserRingBuffer,
    pub(super) ownership: Node,
}

impl Buffers {
    pub(super) fn new(owner: &crate::vm::user_memory::UserMemoryOwner) -> Result<Self> {
        Ok(Self {
            outgoing: new_user_ring_buffer(UNIX_STREAM_DEFAULT_BUF_SIZE, owner)?,
            incoming: new_user_ring_buffer(UNIX_STREAM_DEFAULT_BUF_SIZE, owner)?,
            ownership: Node::new()?,
        })
    }
}

pub(super) struct Connected {
    // `addr` should be dropped as soon as the socket file is closed,
    // so it must not belong to `Inner`.
    addr: Option<UnixSocketAddrBound>,
    inner: Endpoint<Inner>,
    ownership: Option<Lease>,
}

impl Connected {
    pub(super) fn new_pair(
        buffers: Buffers,
        addr: Option<UnixSocketAddrBound>,
        peer_addr: Option<UnixSocketAddrBound>,
        state: EndpointState,
        peer_state: EndpointState,
        cred: SocketCred,
        peer_cred: SocketCred,
    ) -> (Connected, Connected) {
        let ownership = buffers.ownership;
        let (this_writer, peer_reader) = buffers.outgoing.split();
        let (peer_writer, this_reader) = buffers.incoming.split();

        let this_inner = Inner {
            addr: Once::new(),
            state,
            reader: Mutex::new(this_reader),
            writer: Mutex::new(this_writer),
            all_aux: Mutex::new(VecDeque::new()),
            has_aux: AtomicBool::new(false),
            is_pass_cred: AtomicBool::new(false),
            cred,
            ownership: ownership.clone(),
        };
        let peer_inner = Inner {
            addr: Once::new(),
            state: peer_state,
            reader: Mutex::new(peer_reader),
            writer: Mutex::new(peer_writer),
            all_aux: Mutex::new(VecDeque::new()),
            has_aux: AtomicBool::new(false),
            is_pass_cred: AtomicBool::new(false),
            cred: peer_cred,
            ownership,
        };

        if let Some(addr) = addr.as_ref() {
            this_inner.addr.call_once(|| addr.clone().into());
        }
        if let Some(peer_addr) = peer_addr.as_ref() {
            peer_inner.addr.call_once(|| peer_addr.clone().into());
        }

        let (this_inner, peer_inner) = Endpoint::new_pair(this_inner, peer_inner);

        let this = Connected {
            addr,
            inner: this_inner,
            ownership: None,
        };
        let peer = Connected {
            addr: peer_addr,
            inner: peer_inner,
            ownership: None,
        };

        (this, peer)
    }

    pub(super) fn prepare_owner(&self, owner: &Node) -> Result<Lease> {
        Lease::single(owner, &self.inner.this_end().ownership)
    }

    pub(super) fn publish_owner(&mut self, ownership: Lease) {
        self.ownership = Some(ownership);
    }

    pub(super) fn addr(&self) -> Option<&UnixSocketAddrBound> {
        self.addr.as_ref()
    }

    pub(super) fn bytes_to_read(&self) -> usize {
        self.inner.this_end().reader.lock().len()
    }

    pub(super) fn peer_addr(&self) -> UnixSocketAddr {
        self.inner
            .peer_end()
            .addr
            .get()
            .cloned()
            .unwrap_or(UnixSocketAddr::Unnamed)
    }

    pub(super) fn bind(&mut self, addr_to_bind: UnixSocketAddr) -> Result<()> {
        if self.addr.is_some() {
            return addr_to_bind.bind_unnamed();
        }

        let bound_addr = addr_to_bind.bind()?;
        self.inner
            .this_end()
            .addr
            .call_once(|| bound_addr.clone().into());
        self.addr = Some(bound_addr);

        Ok(())
    }

    pub(super) fn try_read(
        &self,
        writer: &mut dyn MultiWrite,
        is_seqpacket: bool,
        flags: RecvFlags,
    ) -> Result<(RecvOutput, Vec<ControlMessage>)> {
        let is_empty = writer.is_empty();
        if is_empty && !is_seqpacket {
            if self.inner.this_end().reader.lock().is_empty() {
                return_errno_with_message!(Errno::EAGAIN, "the channel is empty");
            }
            return Ok((RecvOutput::new_for_stream(0), Vec::new()));
        }

        let this_end = self.inner.this_end();
        let peer_end = self.inner.peer_end();

        let mut reader = this_end.reader.lock();
        // EOF must be decided from a shutdown observation made before the data
        // snapshot; the peer can write and shut down while this reader is locked.
        let read_snapshot = self.inner.read_snapshot();
        // `reader.len()` is an `Acquire` operation. So it can guarantee that the `has_aux`
        // check below sees the up-to-date value.
        let no_aux_len = reader.len();

        let is_pass_cred = this_end.is_pass_cred.load(Ordering::Relaxed);
        let behavior = flags.receive_behavior();

        // Fast path: There are no auxiliary data to receive.
        if !peer_end.has_aux.load(Ordering::Relaxed) {
            let read_len = read_snapshot.read_with(|| {
                let head = reader.head();
                let copy_range = head..head + Wrapping(no_aux_len);
                reader.ring_buffer().pick_fallible(copy_range, writer)
            })?;
            if behavior.will_consume_data() {
                reader.commit_read(read_len);
                if read_len > 0 {
                    self.inner.notify_read();
                }
            }

            let ctrl_msgs = if is_pass_cred {
                AuxiliaryData::default().generate_control(behavior, is_pass_cred)
            } else {
                Vec::new()
            };
            return Ok((RecvOutput::new_for_stream(read_len), ctrl_msgs));
        }

        let mut all_aux = peer_end.all_aux.lock();
        let mut aux_pos = 0;

        let read_base = reader.head();
        let mut read_tot_len = 0;
        let mut trunc_len = 0;

        loop {
            let read_snapshot = self.inner.read_snapshot();
            let read_start = read_base + Wrapping(read_tot_len);
            let (aux_len, aux_front) = if let Some(front) = all_aux.get(aux_pos) {
                if front.start == read_start {
                    ((front.end - read_start).0, Some(front))
                } else {
                    ((front.start - read_start).0, None)
                }
            } else {
                ((reader.tail() - read_start).0, None)
            };

            // Unless the auxiliary data we have already received is a subset of the current
            // auxiliary data, we cannot receive additional bytes.
            if read_tot_len > 0 {
                let is_subset = match (aux_pos.checked_sub(1), aux_front.as_ref()) {
                    (Some(prev_pos), Some(front)) => {
                        let prev = all_aux.get(prev_pos).unwrap();
                        prev.data.is_subset_of(&front.data, is_pass_cred)
                    }
                    (Some(prev_pos), None) => {
                        let prev = all_aux.get(prev_pos).unwrap();
                        prev.data
                            .is_subset_of(&AuxiliaryData::default(), is_pass_cred)
                    }
                    (None, Some(front)) => {
                        AuxiliaryData::default().is_subset_of(&front.data, is_pass_cred)
                    }
                    (None, None) => true,
                };
                if !is_subset {
                    break;
                }
            }

            // Read the payload bytes of the current auxiliary data.
            let read_res = if !is_empty && (aux_len > 0 || aux_front.is_none()) {
                read_snapshot.read_with(|| {
                    let copy_range = read_start..read_start + Wrapping(aux_len);
                    reader.ring_buffer().pick_fallible(copy_range, writer)
                })
            } else {
                Ok(0)
            };
            let read_len = match read_res {
                Ok(read_len) => read_len,
                Err(_) if read_tot_len > 0 => break,
                Err(err) => return Err(err),
            };

            read_tot_len += read_len;
            if aux_front.is_some() {
                aux_pos += 1;
            }

            // Record the current auxiliary data. Break if the read is incomplete or this is a
            // `SOCK_SEQPACKET` socket.
            if is_seqpacket {
                if read_len < aux_len {
                    warn!("setting MSG_TRUNC is not supported");
                    trunc_len = aux_len - read_len;
                }
                break;
            } else if read_len < aux_len || read_len == 0 {
                // A closed stream can exhaust the payload after auxiliary data
                // compatible with the default. Return the bytes and control
                // messages already read instead of repeating an empty range.
                break;
            }
        }

        // Consume the payload bytes that we've read.
        if behavior.will_consume_data() {
            let consume_tot_len = read_tot_len + trunc_len;
            reader.commit_read(consume_tot_len);
            if consume_tot_len > 0 {
                self.inner.notify_read();
            }
        }
        drop(reader);

        // Consume the auxiliary data that we've read.
        let ctrl_msgs = if aux_pos >= 1 {
            let aux_data = all_aux.get_mut(aux_pos - 1).unwrap();
            debug_assert!((aux_data.start - read_base).0 <= read_tot_len);

            let ctrl_msgs = aux_data.data.generate_control(behavior, is_pass_cred);
            if behavior.will_consume_data() {
                let previous_aux_count = all_aux.len();
                let remaining_aux_count = previous_aux_count - (aux_pos - 1);
                all_aux.retain_back(remaining_aux_count);
                let consume_len = read_tot_len + trunc_len;
                if (all_aux.front().unwrap().end - read_base).0 <= consume_len {
                    all_aux.pop_front();
                } else {
                    all_aux.front_mut().unwrap().start = read_base + Wrapping(consume_len);
                }
                peer_end
                    .has_aux
                    .store(!all_aux.is_empty(), Ordering::Relaxed);
                if all_aux.len() < previous_aux_count {
                    // Zero-length packets free a message slot without moving
                    // the byte head. Wake the original blocking sender too.
                    self.inner.notify_read();
                }
            }
            ctrl_msgs
        } else {
            let mut default_aux_data = AuxiliaryData::default();
            default_aux_data.generate_control(behavior, is_pass_cred)
        };

        let output = if is_seqpacket {
            let message_len = read_tot_len + trunc_len;
            RecvOutput::new_for_packet(flags, read_tot_len, message_len)
        } else {
            RecvOutput::new_for_stream(read_tot_len)
        };

        Ok((output, ctrl_msgs))
    }

    pub(super) fn try_write(
        &self,
        reader: &mut dyn MultiRead,
        aux_data: &mut AuxiliaryData,
        is_seqpacket: bool,
    ) -> Result<usize> {
        let is_empty = reader.is_empty();
        if is_empty {
            if self.inner.is_shutdown() {
                return_errno_with_message!(Errno::EPIPE, "the channel is shut down");
            }
            if !is_seqpacket {
                return Ok(0);
            }
        }

        if is_seqpacket && reader.sum_lens() >= UNIX_STREAM_DEFAULT_BUF_SIZE {
            return_errno_with_message!(Errno::EMSGSIZE, "the message is too large");
        }

        let this_end = self.inner.this_end();
        let need_pass_cred = this_end.is_pass_cred.load(Ordering::Relaxed)
            || self.inner.peer_end().is_pass_cred.load(Ordering::Relaxed);

        // Fast path: There are no auxiliary data to transmit.
        if aux_data.is_empty() && !is_seqpacket && !need_pass_cred {
            let mut writer = this_end.writer.lock();
            let write_len = self
                .inner
                .write_with(move || writer.write_fallible(reader))?;
            self.inner.notify_write();
            return Ok(write_len);
        }

        let mut all_aux = this_end.all_aux.lock();
        // Empty seqpackets consume no ring-buffer bytes, but still own one
        // message boundary and auxiliary metadata. Bound that original queue
        // independently of byte capacity, before consuming any caller state.
        if is_seqpacket && all_aux.len() >= UNIX_SEQPACKET_MAX_QUEUED_MESSAGES {
            return_errno_with_message!(Errno::EAGAIN, "the ancillary queue has no message slots");
        }
        all_aux
            .try_reserve(1)
            .map_err(|_| Error::new(Errno::ENOMEM))?;

        let ownership = aux_data.prepare_ownership(&this_end.ownership)?;

        // No matter we succeed later or not, set the flag first to ensure that the auxiliary
        // data are always visible to `try_recv`.
        this_end.has_aux.store(true, Ordering::Relaxed);

        // Write the payload bytes.
        let (write_start, write_res) = if !is_empty {
            let mut writer = this_end.writer.lock();
            let write_start = writer.tail();
            let write_res = self.inner.write_with(move || {
                if is_seqpacket && writer.free_len() < reader.sum_lens() {
                    return Ok(0);
                }
                writer.write_fallible(reader)
            });
            (write_start, write_res)
        } else {
            (this_end.writer.lock().tail(), Ok(0))
        };
        let Ok(write_len) = write_res else {
            this_end
                .has_aux
                .store(!all_aux.is_empty(), Ordering::Relaxed);
            return write_res;
        };

        if need_pass_cred {
            aux_data.fill_cred();
        }

        aux_data.publish_ownership(ownership);

        // Store the auxiliary data.
        let aux_range = RangedAuxiliaryData {
            data: core::mem::take(aux_data),
            start: write_start,
            end: write_start + Wrapping(write_len),
        };
        all_aux.push_back(aux_range);

        self.inner.notify_write();

        Ok(write_len)
    }

    pub(super) fn shutdown(&self, cmd: SockShutdownCmd) {
        if cmd.shut_read() {
            self.inner.peer_shutdown();
        }

        if cmd.shut_write() {
            self.inner.shutdown();
        }
    }

    pub(super) fn is_read_shutdown(&self) -> bool {
        self.inner.is_peer_shutdown()
    }

    pub(super) fn is_write_shutdown(&self) -> bool {
        self.inner.is_shutdown()
    }

    pub(super) fn set_pass_cred(&self, is_pass_cred: bool) {
        self.inner
            .this_end()
            .is_pass_cred
            .store(is_pass_cred, Ordering::Relaxed);
    }

    pub(super) fn is_pass_cred(&self) -> bool {
        self.inner.this_end().is_pass_cred.load(Ordering::Relaxed)
    }

    pub(super) fn check_io_events(&self, is_seqpacket: bool) -> IoEvents {
        let this_end = self.inner.this_end();
        let mut events = IoEvents::empty();

        if !this_end.reader.lock().is_empty()
            || (is_seqpacket && !self.inner.peer_end().all_aux.lock().is_empty())
        {
            events |= IoEvents::IN;
        }

        let has_message_slot =
            !is_seqpacket || this_end.all_aux.lock().len() < UNIX_SEQPACKET_MAX_QUEUED_MESSAGES;
        if has_message_slot && !this_end.writer.lock().is_full() {
            events |= IoEvents::OUT;
        }

        events
    }

    pub(super) fn cloned_pollee(&self) -> Pollee {
        self.inner.this_end().state.cloned_pollee()
    }

    pub(super) fn peer_cred(&self) -> &SocketCred {
        &self.inner.peer_end().cred
    }
}

impl Drop for Connected {
    fn drop(&mut self) {
        self.inner.shutdown();
        self.inner.peer_shutdown();
    }
}

struct Inner {
    addr: Once<UnixSocketAddr>,
    state: EndpointState,
    // Lock order: `reader` -> `all_aux` & `all_aux` -> `writer`
    reader: Mutex<UserRbConsumer>,
    writer: Mutex<UserRbProducer>,
    all_aux: Mutex<VecDeque<RangedAuxiliaryData>>,
    has_aux: AtomicBool,
    is_pass_cred: AtomicBool,
    cred: SocketCred,
    ownership: Node,
}

impl AsRef<EndpointState> for Inner {
    fn as_ref(&self) -> &EndpointState {
        &self.state
    }
}

struct RangedAuxiliaryData {
    data: AuxiliaryData,
    start: Wrapping<usize>, // inclusive
    end: Wrapping<usize>,   // exclusive
}

pub(in crate::net) const UNIX_STREAM_DEFAULT_BUF_SIZE: usize = 65536;

// Local bounded-metadata policy, independent of the unchanged 64-KiB byte ring.
const UNIX_SEQPACKET_MAX_QUEUED_MESSAGES: usize = 128;

#[cfg(ktest)]
mod queue_tests;

#[cfg(ktest)]
mod memory_tests {
    use ostd::prelude::*;

    use super::*;
    use crate::vm::user_memory::UserMemoryAccount;

    #[ktest]
    fn unix_pair_admits_both_directions_or_refunds_the_first() {
        for pages in [0, 15, 16, 31] {
            let account = UserMemoryAccount::new(pages);
            assert!(
                Buffers::new(&Some(account.clone()))
                    .err()
                    .unwrap()
                    .is_user_frame_limit()
            );
            assert_eq!(account.current_pages(), 0);
        }
        let account = UserMemoryAccount::new(32);
        let buffers = Buffers::new(&Some(account.clone())).unwrap();
        assert_eq!(account.current_pages(), 32);
        let (mut writer, mut reader) = buffers.outgoing.split();
        assert!(writer.push_slice(&[1, 2, 3]).is_some());
        let mut bytes = [0; 3];
        assert!(reader.pop_slice(&mut bytes).is_some());
        assert_eq!(bytes, [1, 2, 3]);
        drop(writer);
        assert_eq!(account.current_pages(), 32);
        drop(reader);
        assert_eq!(account.current_pages(), 16);
        drop(buffers.incoming);
        assert_eq!(account.current_pages(), 0);
    }
}
