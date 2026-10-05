//! Single-use denial on the same connected socket. This supplies no Source,
//! action, report, read/write, new connection or request-clock authority.
use super::*;
use std::net::Shutdown;

/// Private clone of an original connected socket, usable only to shut it down.
/// Product callers must retain their actual immutable Source/creator and
/// independent original report clock around both methods.
///
/// ```compile_fail,E0616
/// use hepta_agent_transport::OriginalConnectedDenial;
/// fn raw(wake: OriginalConnectedDenial) { let _ = wake.stream; }
/// ```
/// ```compile_fail,E0277
/// use hepta_agent_transport::OriginalConnectedDenial;
/// fn clone_required<T: Clone>() {}
/// fn duplicate() { clone_required::<OriginalConnectedDenial>(); }
/// ```
pub struct OriginalConnectedDenial {
    stream: Option<UnixStream>,
    identity: SocketIdentity,
    peer: PeerIdentity,
    creator_pid: u32,
    creator_pair: [UnixStream; 2],
    creator_pair_identity: [SocketIdentity; 2],
    creator_peer: [PeerIdentity; 2],
}

impl OriginalConnectedDenial {
    pub fn capture_original(stream: &UnixStream) -> Result<Self, HandoffError> {
        let creator_pid = std::process::id();
        let (first, second) = UnixStream::pair().map_err(|_| HandoffError::Io)?;
        let creator_pair = [first, second];
        let creator_pair_identity = [
            socket_identity(creator_pair[0].as_raw_fd())?,
            socket_identity(creator_pair[1].as_raw_fd())?,
        ];
        let creator_peer = [
            PeerIdentity::from_stream(&creator_pair[0]).map_err(|_| HandoffError::PeerRefused)?,
            PeerIdentity::from_stream(&creator_pair[1]).map_err(|_| HandoffError::PeerRefused)?,
        ];
        if creator_peer
            .iter()
            .any(|peer| peer.pid != Some(creator_pid))
            || creator_pid == 0
        {
            return Err(HandoffError::ProcessChanged);
        }
        socket_shape(stream, libc::SOCK_STREAM)?;
        let identity = socket_identity(stream.as_raw_fd())?;
        let peer = PeerIdentity::from_stream(stream).map_err(|_| HandoffError::PeerRefused)?;
        if peer.pid.is_none_or(|pid| pid == 0) {
            return Err(HandoffError::PeerRefused);
        }
        let copied = stream.try_clone().map_err(|_| HandoffError::Io)?;
        let result = Self {
            stream: Some(copied),
            identity,
            peer,
            creator_pid,
            creator_pair,
            creator_pair_identity,
            creator_peer,
        };
        result.original_current()?;
        socket_shape(stream, libc::SOCK_STREAM)?;
        if socket_identity(stream.as_raw_fd())? != result.identity
            || PeerIdentity::from_stream(stream).map_err(|_| HandoffError::PeerRefused)?
                != result.peer
        {
            return Err(HandoffError::IdentityMismatch);
        }
        result.original_current()?;
        Ok(result)
    }

    pub fn shutdown_original(mut self) -> Result<(), HandoffError> {
        self.original_current()?;
        self.stream
            .as_ref()
            .ok_or(HandoffError::ChannelRetired)?
            .shutdown(Shutdown::Both)
            .map_err(|_| HandoffError::Io)?;
        // A physical shutdown cannot be rolled back if this post sample fails.
        self.original_current()?;
        self.stream.take();
        Ok(())
    }

    fn creator_current(&self) -> Result<(), HandoffError> {
        if self.creator_pid != std::process::id() {
            return Err(HandoffError::ProcessChanged);
        }
        for index in 0..2 {
            if socket_identity(self.creator_pair[index].as_raw_fd())?
                != self.creator_pair_identity[index]
                || PeerIdentity::from_stream(&self.creator_pair[index])
                    .map_err(|_| HandoffError::PeerRefused)?
                    != self.creator_peer[index]
                || self.creator_peer[index].pid != Some(self.creator_pid)
            {
                return Err(HandoffError::ProcessChanged);
            }
        }
        Ok(())
    }

    fn original_current(&self) -> Result<(), HandoffError> {
        self.creator_current()?;
        let stream = self.stream.as_ref().ok_or(HandoffError::ChannelRetired)?;
        socket_shape(stream, libc::SOCK_STREAM)?;
        if socket_identity(stream.as_raw_fd())? != self.identity
            || PeerIdentity::from_stream(stream).map_err(|_| HandoffError::PeerRefused)?
                != self.peer
        {
            return Err(HandoffError::IdentityMismatch);
        }
        self.creator_current()
    }
}

// No Drop shutdown: ordinary descriptor owners close only their own copies.

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};

    #[test]
    fn dropping_saved_copy_keeps_original_connection_live() {
        let (mut original, mut peer) = UnixStream::pair().unwrap();
        let saved = OriginalConnectedDenial::capture_original(&original).unwrap();
        saved.original_current().unwrap();
        drop(saved);
        original.write_all(b"x").unwrap();
        let mut byte = [0];
        peer.read_exact(&mut byte).unwrap();
        assert_eq!(byte, *b"x");
    }

    #[test]
    fn consumed_shutdown_ends_only_the_captured_connection() {
        let (original, mut peer) = UnixStream::pair().unwrap();
        let (mut unrelated, mut unrelated_peer) = UnixStream::pair().unwrap();
        OriginalConnectedDenial::capture_original(&original)
            .unwrap()
            .shutdown_original()
            .unwrap();
        assert_eq!(peer.read(&mut [0]).unwrap(), 0);
        unrelated.write_all(b"y").unwrap();
        let mut byte = [0];
        unrelated_peer.read_exact(&mut byte).unwrap();
        assert_eq!(byte, *b"y");
    }

    #[test]
    fn captured_cookie_drift_refuses_before_shutdown() {
        let (mut original, mut peer) = UnixStream::pair().unwrap();
        let mut saved = OriginalConnectedDenial::capture_original(&original).unwrap();
        saved.identity.cookie ^= 1;
        assert!(matches!(
            saved.shutdown_original(),
            Err(HandoffError::IdentityMismatch)
        ));
        original.write_all(b"z").unwrap();
        let mut byte = [0];
        peer.read_exact(&mut byte).unwrap();
        assert_eq!(byte, *b"z");
    }
}
