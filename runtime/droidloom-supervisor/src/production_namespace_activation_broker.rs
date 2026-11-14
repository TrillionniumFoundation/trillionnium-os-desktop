//! Fixed original-linkerconfig protocol on an actually owned init peer.
//!
//! AUTH and GO require live host MAC, actual init/peer and fixed original
//! input observations. Packets cannot choose an executable, path, environment,
//! namespace, numeric signal target or command line. Only the trampoline is
//! the child's parent: it performs waitid, while this broker independently
//! checks the same received PIDFD's retained kernel exit.
//!
//! This proves one command and its retirement, not active APEX mounts,
//! generated linkerconfig contents or Android Ready. The activation owner
//! must combine those separate providers before issuing a runtime witness.

use super::activation_channel::{Channel, Received, Rights, before, monotonic_ns};
use super::activation_peer::{ActivationChild, OriginalLinkerInput};
use super::*;
use crate::production_activation_protocol as wire;
use crate::production_mac::{MacError, MacHelperWitness, MacPreflight};

#[derive(Debug, thiserror::Error)]
pub(super) enum SessionError {
    #[error(transparent)]
    Namespace(#[from] NamespaceError),
    #[error(transparent)]
    Mac(#[from] MacError),
    #[error(
        "actual linkerconfig peer failed in stage {stage}, errno {errno}; parent-reported retirement={retired_reported}"
    )]
    PeerFailed {
        stage: u32,
        errno: i32,
        retired_reported: bool,
    },
    #[error("original linkerconfig exited with code {code}, status {status}")]
    Exit { code: i32, status: i32 },
}

type SessionResult<T> = std::result::Result<T, SessionError>;

/// Clean retirement cannot convert the original error to success. Retire the
/// whole init tree before returning control to a Start caller; a reaped leader
/// alone says nothing about its remaining descendants or private mounts.
#[must_use = "failed activation requires retirement of the entire original owned tree"]
pub(super) struct FailedSession {
    source: SessionError,
    diagnostics: Vec<u8>,
    child: Option<ActivationChild>,
}

#[must_use = "this remains the original activation failure even when retirement succeeds"]
pub(super) struct RetiredFailure {
    pub(super) source: SessionError,
    pub(super) diagnostics: Vec<u8>,
    pub(super) tree_retirement: Result<TreeExit>,
    pub(super) command_retirement: Option<Result<i32>>,
}

impl FailedSession {
    /// All peer/input borrows must be dropped before the actual tree can be
    /// moved here. Existing quarantine/reservation rules apply on failure.
    pub(super) fn retire_owned_tree(self, owner: ExecutedNamespaces) -> RetiredFailure {
        let tree_retirement = owner.retire();
        let command_retirement = self.child.as_ref().map(|child| {
            let deadline = monotonic_ns()?.checked_add(wire::RETIREMENT_NS).ok_or(
                NamespaceError::Rejected("retirement observation clock overflow"),
            )?;
            child.require_retired_after_tree(deadline)
        });
        RetiredFailure {
            source: self.source,
            diagnostics: self.diagnostics,
            tree_retirement,
            command_retirement,
        }
    }
}

/// Only real original exit zero and child/wrapper retirement construct this
/// result. It is deliberately not an APEX or runtime-Ready witness.
pub(super) struct CompletedLinkerconfig {
    child: ActivationChild,
    generation: ExecutedInitGeneration,
    diagnostics: Vec<u8>,
}

impl CompletedLinkerconfig {
    pub(super) fn revalidate(
        &self,
        init: &ExecutedInitWitness<'_>,
        observation_deadline: u64,
    ) -> Result<()> {
        before(observation_deadline)?;
        init.revalidate()?;
        if init.generation()? != self.generation {
            return Err(NamespaceError::Rejected(
                "completed linkerconfig belongs to another original init",
            ));
        }
        self.child
            .require_reaped(libc::CLD_EXITED, 0, observation_deadline)?;
        init.revalidate()?;
        before(observation_deadline)
    }

    pub(super) fn diagnostics(&self) -> &[u8] {
        &self.diagnostics
    }
}

struct Session<'a, 'owner> {
    init: &'a ExecutedInitWitness<'owner>,
    peer: &'a OwnedActivationPeer<'owner>,
    original: &'a OriginalLinkerInput<'owner>,
    mac: &'a MacPreflight,
    helper_mac: MacHelperWitness,
    channel: Channel<'a>,
    frame: wire::Packet,
    child: Option<ActivationChild>,
    diagnostics: Vec<u8>,
}

fn random_nonce(deadline: u64) -> Result<[u8; 32]> {
    let mut nonce = [0_u8; 32];
    let mut offset = 0;
    while offset < nonce.len() {
        before(deadline)?;
        let result = unsafe {
            libc::getrandom(
                nonce[offset..].as_mut_ptr().cast(),
                nonce.len() - offset,
                libc::GRND_NONBLOCK,
            )
        };
        if result < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        if result == 0 {
            return Err(NamespaceError::Rejected("empty kernel nonce read"));
        }
        offset += result as usize;
    }
    before(deadline)?;
    if nonce.iter().all(|byte| *byte == 0) {
        return Err(NamespaceError::Rejected("kernel nonce is empty"));
    }
    Ok(nonce)
}

fn hello(packet: &wire::Packet, peer_pid: u32) -> Result<()> {
    if !packet.header_is_fixed()
        || packet.phase != wire::HELLO
        || packet.nonce != [0; 32]
        || packet.owner_generation != [0; 32]
        || packet.deadline_ns != 0
        || packet.child_pid <= 1
        || packet.child_pid as u32 != peer_pid
        || packet.exit_code != 0
        || packet.exit_status != 0
        || packet.error != 0
        || packet.output_bytes != 0
        || packet.data_length != 0
        || packet.detail != 0
    {
        return Err(NamespaceError::Rejected(
            "fixed activation HELLO differs from the actual peer",
        ));
    }
    Ok(())
}

impl Session<'_, '_> {
    fn revalidate(&self) -> SessionResult<()> {
        before(self.frame.deadline_ns)?;
        self.init.revalidate()?;
        self.mac.revalidate(self.init.selection())?;
        self.peer.revalidate()?;
        self.original.revalidate()?;
        self.helper_mac.revalidate(self.mac, self.init, self.peer)?;
        self.helper_mac.revalidate_original(
            self.mac,
            self.init,
            self.peer,
            self.original.file(),
        )?;
        if self.init.generation()? != self.peer.generation() {
            return Err(NamespaceError::Rejected(
                "activation peer and actual init generation differ",
            )
            .into());
        }
        before(self.frame.deadline_ns)?;
        Ok(())
    }

    fn receive(&self, rights: Rights, phase: u32) -> SessionResult<Received> {
        self.revalidate()?;
        let received = self.channel.receive(rights, self.frame.deadline_ns)?;
        let p = &received.packet;
        if p.phase == wire::FAILED
            && p.header_is_fixed()
            && p.nonce == self.frame.nonce
            && p.owner_generation == self.frame.owner_generation
            && p.deadline_ns == self.frame.deadline_ns
            && (self.frame.child_pid == 0 || p.child_pid == self.frame.child_pid)
            && received.descriptor.is_none()
            && received.data.is_empty()
            && p.data_length == 0
            && (1..4096).contains(&p.error)
            && (wire::HELLO..=wire::CANCEL).contains(&(p.detail & 0x7fff_ffff))
        {
            // This retirement bit is diagnostic only, never a kernel proof.
            return Err(SessionError::PeerFailed {
                stage: p.detail & 0x7fff_ffff,
                errno: p.error,
                retired_reported: p.detail & 0x8000_0000 == 0,
            });
        }
        if p.phase != phase
            || !p.header_is_fixed()
            || p.error != 0
            || p.detail != 0
            || p.nonce != self.frame.nonce
            || p.owner_generation != self.frame.owner_generation
            || p.deadline_ns != self.frame.deadline_ns
            || (phase != wire::CHILD && p.child_pid != self.frame.child_pid)
        {
            return Err(
                NamespaceError::Rejected("activation original session or phase differs").into(),
            );
        }
        self.revalidate()?;
        Ok(received)
    }

    fn send_control(&self, phase: u32) -> SessionResult<()> {
        if ![wire::GO, wire::REAP].contains(&phase) {
            return Err(NamespaceError::Rejected("invalid nonterminal broker phase").into());
        }
        self.revalidate()?;
        let mut packet = self.frame;
        packet.phase = phase;
        self.channel.send(&packet, None, self.frame.deadline_ns)?;
        self.revalidate()
    }

    fn send_ack(&self) -> SessionResult<()> {
        self.revalidate()?;
        let mut packet = self.frame;
        packet.phase = wire::ACK;
        self.channel.send(&packet, None, self.frame.deadline_ns)?;
        // ACK releases the original peer to exit. A new live-peer check here
        // would race its correct exit; the next observation must be retirement.
        before(self.frame.deadline_ns)?;
        Ok(())
    }

    fn perform(&mut self) -> SessionResult<()> {
        self.revalidate()?;
        let handshake = monotonic_ns()?
            .checked_add(wire::HANDSHAKE_NS)
            .ok_or(NamespaceError::Rejected(
                "activation handshake clock overflow",
            ))?
            .min(self.frame.deadline_ns);
        let first = self.channel.receive(Rights::None, handshake)?;
        hello(&first.packet, self.peer.namespace_pid())?;
        self.revalidate()?;
        self.channel
            .send(&self.frame, Some(self.original.descriptor()), handshake)?;

        let child = self.receive(Rights::Optional, wire::CHILD)?;
        let p = child.packet;
        if p.child_pid <= 1
            || p.child_pid as u32 == self.peer.namespace_pid()
            || p.exit_code != 0
            || p.exit_status != 0
            || p.output_bytes != 0
            || p.data_length != 0
            || !child.data.is_empty()
        {
            return Err(NamespaceError::Rejected("activation CHILD shape differs").into());
        }
        let pidfd = child
            .descriptor
            .ok_or(NamespaceError::Rejected("atomic child PIDFD absent"))?;
        // Only kernel PIDFD info supplies a host proc key. The packet number
        // is compared with actual NSpid and is never a syscall target.
        self.child = Some(ActivationChild::observe(
            self.peer,
            pidfd,
            p.child_pid as u32,
        )?);
        self.frame.child_pid = p.child_pid;
        self.child
            .as_ref()
            .unwrap()
            .revalidate_before_go(self.peer)?;
        self.send_control(wire::GO)?;

        let exited = self.receive(Rights::None, wire::EXITED)?;
        let p = exited.packet;
        if wire::raw_wait_status(p.exit_code, p.exit_status).is_none()
            || p.output_bytes > wire::OUTPUT_LIMIT as u64
            || p.data_length != 0
            || !exited.data.is_empty()
        {
            return Err(
                NamespaceError::Rejected("original linkerconfig EXITED shape differs").into(),
            );
        }
        self.child
            .as_ref()
            .unwrap()
            .require_exited_unreaped(self.frame.deadline_ns)?;
        self.frame.exit_code = p.exit_code;
        self.frame.exit_status = p.exit_status;
        self.frame.output_bytes = p.output_bytes;
        self.send_control(wire::REAP)?;

        let reaped = self.receive(Rights::None, wire::REAPED)?;
        let p = reaped.packet;
        if p.exit_code != self.frame.exit_code
            || p.exit_status != self.frame.exit_status
            || p.output_bytes != self.frame.output_bytes
            || p.data_length != 0
            || !reaped.data.is_empty()
        {
            return Err(NamespaceError::Rejected(
                "original linkerconfig reap differs from observed exit",
            )
            .into());
        }
        self.child.as_ref().unwrap().require_reaped(
            p.exit_code,
            p.exit_status,
            self.frame.deadline_ns,
        )?;
        while self.diagnostics.len() < self.frame.output_bytes as usize {
            let received = self.receive(Rights::None, wire::DIAGNOSTIC)?;
            let p = received.packet;
            if p.exit_code != self.frame.exit_code
                || p.exit_status != self.frame.exit_status
                || p.output_bytes != self.diagnostics.len() as u64
                || received.data.is_empty()
                || received.data.len() > self.frame.output_bytes as usize - self.diagnostics.len()
            {
                return Err(NamespaceError::Rejected(
                    "post-reap linkerconfig diagnostics sequence differs",
                )
                .into());
            }
            self.diagnostics.extend_from_slice(&received.data);
        }
        // ACK also returns an authenticated actual nonzero exit to stock init.
        // Refusing Ready must not replace exit 17 with protocol-failure 127.
        self.send_ack()?;
        self.peer.require_retired(
            self.frame.exit_code,
            self.frame.exit_status,
            self.frame.deadline_ns,
        )?;
        self.mac.revalidate(self.init.selection())?;
        self.init.revalidate()?;
        self.original.revalidate()?;
        self.child.as_ref().unwrap().require_reaped(
            self.frame.exit_code,
            self.frame.exit_status,
            self.frame.deadline_ns,
        )?;
        before(self.frame.deadline_ns)?;
        if self.frame.exit_code != libc::CLD_EXITED || self.frame.exit_status != 0 {
            return Err(SessionError::Exit {
                code: self.frame.exit_code,
                status: self.frame.exit_status,
            });
        }
        Ok(())
    }
}

/// Sole fixed-command protocol entry. The production coordinator must drop
/// its input/peer borrows and consume FailedSession::retire_owned_tree on Err.
/// There is no production caller until selected input roles, the listener and
/// typed init mount transition are wired; this does not bypass those gates.
pub(super) fn run<'a, 'owner>(
    init: &'a ExecutedInitWitness<'owner>,
    peer: &'a OwnedActivationPeer<'owner>,
    original: &'a OriginalLinkerInput<'owner>,
    mac: &'a MacPreflight,
    absolute_deadline: u64,
) -> std::result::Result<CompletedLinkerconfig, FailedSession> {
    let prepare = (|| -> SessionResult<Session<'a, 'owner>> {
        before(absolute_deadline)?;
        let now = monotonic_ns()?;
        if absolute_deadline
            .checked_sub(now)
            .is_none_or(|left| left > wire::MAX_COMMAND_NS)
        {
            return Err(NamespaceError::Rejected(
                "activation command budget exceeds its fixed bound",
            )
            .into());
        }
        init.revalidate()?;
        mac.revalidate(init.selection())?;
        peer.revalidate()?;
        original.revalidate()?;
        let helper_mac = mac.observe_linkerconfig_peer(init, peer)?;
        helper_mac.revalidate_original(mac, init, peer, original.file())?;
        let channel = Channel::observe(peer.control())?;
        let mut frame = wire::Packet::empty(wire::AUTH);
        frame.nonce = random_nonce(absolute_deadline)?;
        frame.owner_generation = init.generation()?.protocol_bytes();
        frame.deadline_ns = absolute_deadline;
        if !frame.nonempty_session() {
            return Err(
                NamespaceError::Rejected("activation session lacks actual correlation").into(),
            );
        }
        before(absolute_deadline)?;
        Ok(Session {
            init,
            peer,
            original,
            mac,
            helper_mac,
            channel,
            frame,
            child: None,
            diagnostics: Vec::new(),
        })
    })();
    let mut session = match prepare {
        Ok(value) => value,
        Err(source) => {
            return Err(FailedSession {
                source,
                diagnostics: Vec::new(),
                child: None,
            });
        }
    };
    match session.perform() {
        Ok(()) => Ok(CompletedLinkerconfig {
            child: session.child.take().unwrap(),
            generation: peer.generation(),
            diagnostics: session.diagnostics,
        }),
        Err(source) => Err(FailedSession {
            source,
            diagnostics: session.diagnostics,
            child: session.child,
        }),
    }
}
