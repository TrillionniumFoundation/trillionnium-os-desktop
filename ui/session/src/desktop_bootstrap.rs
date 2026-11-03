//! Explicit new multi-target profile on the original inherited bootstrap pair.
//! Public Session IPC never enters this reservation or exports effect handles.
use std::io::{self, Read};
use std::net::Shutdown;
use std::os::fd::BorrowedFd;
use std::os::unix::net::{UnixDatagram, UnixStream};
use std::time::{Duration, Instant};
use trill_ui_core::calculator::CalculatorTargetIdentity;
use trill_ui_core::desktop_startup::{
    CalculatorBootstrapAck, CalculatorBootstrapOffer, CalculatorBootstrapStatus,
    DesktopStartupActivation, DesktopStartupReservation,
};
use trill_ui_core::notes::NotesTargetIdentity;
use trill_ui_core::notes_bootstrap::{
    NotesBootstrapAck, NotesBootstrapOffer, NotesBootstrapStatus,
};
use trill_ui_core::notes_private_unix::{require_private_datagram, send_channels};

pub struct CalculatorChannels {
    pub target: CalculatorTargetIdentity,
    pub effect: UnixStream,
    pub recovery: UnixDatagram,
}

pub struct DesktopBootstrap {
    channel: UnixDatagram,
}

impl DesktopBootstrap {
    pub fn from_inherited_stdin() -> io::Result<Self> {
        let descriptor = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
        Self::from_private_channel(UnixDatagram::from(descriptor))
    }
    pub fn from_private_channel(channel: UnixDatagram) -> io::Result<Self> {
        require_private_datagram(&channel)?;
        channel.set_nonblocking(false)?;
        Ok(Self { channel })
    }

    pub fn offer(
        self,
        notes: (NotesTargetIdentity, UnixStream, UnixDatagram),
        calculator: CalculatorChannels,
    ) -> io::Result<()> {
        let outcome = self.offer_inner(&notes, &calculator);
        if outcome.is_err() {
            // Closing our original endpoint aliases does not prove that an
            // attachment or an earlier concurrent operation was rolled back.
            let _ = notes.1.shutdown(Shutdown::Both);
            let _ = notes.2.shutdown(Shutdown::Both);
            let _ = calculator.effect.shutdown(Shutdown::Both);
            let _ = calculator.recovery.shutdown(Shutdown::Both);
        }
        outcome
    }

    fn offer_inner(
        &self,
        notes: &(NotesTargetIdentity, UnixStream, UnixDatagram),
        calculator: &CalculatorChannels,
    ) -> io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(30);
        let mut nonce = [0_u8; 16];
        std::fs::File::open("/dev/urandom")?.read_exact(&mut nonce)?;
        let nonce = nonce.iter().map(|byte| format!("{byte:02x}")).collect();
        let reservation =
            DesktopStartupReservation::new(notes.0.clone(), calculator.target.clone(), nonce)
                .map_err(io::Error::other)?;
        let raw = serde_json::to_vec(&reservation).map_err(io::Error::other)?;
        self.channel.set_write_timeout(Some(remaining(deadline)?))?;
        if self.channel.send(&raw)? != raw.len() {
            return Err(io::Error::other("Desktop reservation partial send"));
        }
        let raw = super::notes_bootstrap::receive_ack(&self.channel, deadline)?;
        let activation = DesktopStartupActivation::parse_exact(&raw).map_err(io::Error::other)?;
        if !activation.matches(&reservation) {
            return Err(io::Error::other(
                "Desktop activation differs from real reservation",
            ));
        }

        let offer = NotesBootstrapOffer::new(notes.0.clone()).map_err(io::Error::other)?;
        send_channels(
            &self.channel,
            &serde_json::to_vec(&offer).map_err(io::Error::other)?,
            &notes.1,
            &notes.2,
            remaining(deadline)?,
        )?;
        let ack = NotesBootstrapAck::parse_exact(&super::notes_bootstrap::receive_ack(
            &self.channel,
            deadline,
        )?)
        .map_err(io::Error::other)?;
        if !ack.matches(&offer) || ack.status != NotesBootstrapStatus::Attached {
            return Err(io::Error::other(
                "Desktop original Notes attachment rejected",
            ));
        }

        let offer =
            CalculatorBootstrapOffer::new(calculator.target.clone()).map_err(io::Error::other)?;
        send_channels(
            &self.channel,
            &serde_json::to_vec(&offer).map_err(io::Error::other)?,
            &calculator.effect,
            &calculator.recovery,
            remaining(deadline)?,
        )?;
        let ack = CalculatorBootstrapAck::parse_exact(&super::notes_bootstrap::receive_ack(
            &self.channel,
            deadline,
        )?)
        .map_err(io::Error::other)?;
        if !ack.matches(&offer) || ack.status != CalculatorBootstrapStatus::Attached {
            return Err(io::Error::other(
                "Desktop original Calculator attachment rejected",
            ));
        }
        remaining(deadline)?;
        Ok(())
    }
}

fn remaining(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|d| !d.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "Desktop bootstrap total deadline"))
}

#[cfg(test)]
#[path = "desktop_bootstrap_tests.rs"]
mod tests;
