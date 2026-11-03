// SPDX-License-Identifier: MPL-2.0

use core::sync::atomic::{AtomicBool, Ordering};

use aster_rights::ReadOp;

use super::{
    connected::{Buffers, Connected},
    listener::Listener,
    socket::{SHUT_READ_EVENTS, SHUT_WRITE_EVENTS},
};
use crate::{
    events::IoEvents,
    fs::utils::EndpointState,
    net::socket::{
        unix::{
            addr::{UnixSocketAddr, UnixSocketAddrBound},
            cred::SocketCred,
            ownership::{Lease, Node},
        },
        util::SockShutdownCmd,
    },
    prelude::*,
    process::signal::Pollee,
};

pub(super) struct Init {
    addr: Option<UnixSocketAddrBound>,
    is_read_shutdown: AtomicBool,
    is_write_shutdown: AtomicBool,
}

impl Init {
    pub(super) fn new() -> Self {
        Self {
            addr: None,
            is_read_shutdown: AtomicBool::new(false),
            is_write_shutdown: AtomicBool::new(false),
        }
    }

    pub(super) fn bind(&mut self, addr_to_bind: UnixSocketAddr) -> Result<()> {
        if self.addr.is_some() {
            return addr_to_bind.bind_unnamed();
        }

        let bound_addr = addr_to_bind.bind()?;
        self.addr = Some(bound_addr);

        Ok(())
    }

    pub(super) fn into_connected(
        self,
        peer_addr: UnixSocketAddrBound,
        pollee: Pollee,
        peer_cred: SocketCred,
        owner: &Node,
        peer_owner: &Node,
    ) -> Result<(Connected, Connected), (Error, Self)> {
        let (init, buffers) = self.prepare_buffers()?;
        let edges = (|| {
            Ok((
                Lease::single(owner, &buffers.ownership)?,
                Lease::single(peer_owner, &buffers.ownership)?,
            ))
        })();
        let (edge, peer_edge) = match edges {
            Ok(edges) => edges,
            Err(error) => return Err((error, init)),
        };
        let Init {
            addr,
            is_read_shutdown,
            is_write_shutdown,
        } = init;

        pollee.invalidate();

        let cred = SocketCred::<ReadOp>::new_current();
        let (mut this_conn, mut peer_conn) = Connected::new_pair(
            buffers,
            addr,
            Some(peer_addr),
            EndpointState::new(pollee, is_read_shutdown.into_inner()),
            EndpointState::new(Pollee::new(), is_write_shutdown.into_inner()),
            cred,
            peer_cred,
        );

        this_conn.publish_owner(edge);
        peer_conn.publish_owner(peer_edge);
        Ok((this_conn, peer_conn))
    }

    /// Preserve the original bound/half-closed state if frame admission fails.
    fn prepare_buffers(self) -> Result<(Self, Buffers), (Error, Self)> {
        let owner = crate::vm::user_memory::current_owner();
        match Buffers::new(&owner) {
            Ok(buffers) => Ok((self, buffers)),
            Err(err) => Err((err, self)),
        }
    }

    pub(super) fn listen(
        self,
        backlog: usize,
        pollee: Pollee,
        is_seqpacket: bool,
        owner: &Node,
    ) -> Result<Listener, (Error, Self)> {
        if self.addr.is_none() {
            return Err((
                Error::with_message(Errno::EINVAL, "the socket is not bound"),
                self,
            ));
        }
        let admission = (|| {
            let node = Node::new()?;
            let edge = Lease::single(owner, &node)?;
            Ok((node, edge))
        })();
        let (node, edge) = match admission {
            Ok(pair) => pair,
            Err(error) => return Err((error, self)),
        };
        let Some(addr) = self.addr else {
            return Err((
                Error::with_message(Errno::EINVAL, "the socket is not bound"),
                self,
            ));
        };

        pollee.invalidate();

        Ok(Listener::new(
            addr,
            backlog,
            self.is_read_shutdown.into_inner(),
            self.is_write_shutdown.into_inner(),
            pollee,
            is_seqpacket,
            (node, edge),
        ))
    }

    pub(super) fn shutdown(&self, cmd: SockShutdownCmd, pollee: &Pollee) {
        if cmd.shut_read() {
            self.is_read_shutdown.store(true, Ordering::Relaxed);
            pollee.notify(SHUT_READ_EVENTS);
        }

        if cmd.shut_write() {
            self.is_write_shutdown.store(true, Ordering::Relaxed);
            pollee.notify(SHUT_WRITE_EVENTS);
        }
    }

    pub(super) fn addr(&self) -> Option<&UnixSocketAddrBound> {
        self.addr.as_ref()
    }

    pub(super) fn is_read_shutdown(&self) -> bool {
        self.is_read_shutdown.load(Ordering::Relaxed)
    }

    pub(super) fn is_write_shutdown(&self) -> bool {
        self.is_write_shutdown.load(Ordering::Relaxed)
    }

    pub(super) fn check_io_events(&self) -> IoEvents {
        // According to the Linux implementation, we always have `IoEvents::HUP` and
        // `IoEvents::HUP` in this state.
        IoEvents::OUT | IoEvents::HUP
    }
}

#[cfg(ktest)]
mod memory_tests {
    use ostd::prelude::*;

    use super::*;
    use crate::vm::user_memory::{UserMemoryAccount, test_with_current_owner};

    #[ktest]
    fn denied_connection_keeps_original_bound_and_shutdown_state() {
        let account = UserMemoryAccount::new(31);
        let observed = account.clone();
        test_with_current_owner(Some(account.clone()), move || {
            let name =
                UnixSocketAddr::Abstract(Arc::from(&b"ipc-frame-account-denied-connect"[..]));
            let mut init = Init::new();
            init.bind(name.clone()).unwrap();
            let bound = init.addr.as_ref().unwrap().to_key();
            init.is_read_shutdown.store(true, Ordering::Relaxed);
            init.is_write_shutdown.store(true, Ordering::Relaxed);
            let (error, init) = init.prepare_buffers().err().unwrap();
            assert!(error.is_user_frame_limit());
            assert_eq!(observed.current_pages(), 0);
            assert_eq!(init.addr.as_ref().unwrap().to_key(), bound);
            assert!(init.is_read_shutdown.load(Ordering::Relaxed));
            assert!(init.is_write_shutdown.load(Ordering::Relaxed));
            assert_eq!(name.connect().unwrap(), bound);
            drop(bound);
            drop(init);
            assert!(name.connect().is_err());
        });
        assert_eq!(account.current_pages(), 0);
    }
}
