//! One monotonic I/O budget for a complete local Session exchange.
//!
//! A socket timeout alone applies to each syscall. Recompute its remaining
//! allowance before every read/write so successful partial I/O cannot renew
//! the request budget, including when `read_frame` buffers several reads.

use std::io::{self, Read, Write};
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant};

pub(super) struct DeadlineStream {
    stream: UnixStream,
    deadline: Instant,
}

impl DeadlineStream {
    pub(super) fn new(stream: UnixStream, deadline: Instant) -> Self {
        Self { stream, deadline }
    }

    pub(super) fn remaining(&self) -> io::Result<Duration> {
        remaining_at(self.deadline, Instant::now())
    }
}

fn remaining_at(deadline: Instant, now: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(now)
        .filter(|remaining| !remaining.is_zero())
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "Session exchange deadline exceeded",
            )
        })
}

impl Read for DeadlineStream {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        self.stream.set_read_timeout(Some(self.remaining()?))?;
        let count = self.stream.read(bytes)?;
        // A descheduled owner may resume after the deadline even when the
        // kernel delivered bytes. Do not admit a request from that late read.
        self.remaining()?;
        Ok(count)
    }
}

impl Write for DeadlineStream {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        self.stream.set_write_timeout(Some(self.remaining()?))?;
        let count = self.stream.write(bytes)?;
        self.remaining()?;
        Ok(count)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.remaining()?;
        self.stream.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_shared_monotonic_budget_never_renews_after_partial_io() {
        let started = Instant::now();
        let deadline = started + Duration::from_millis(500);
        assert_eq!(
            remaining_at(deadline, started).unwrap(),
            Duration::from_millis(500)
        );
        assert_eq!(
            remaining_at(deadline, started + Duration::from_millis(400)).unwrap(),
            Duration::from_millis(100)
        );
        for now in [deadline, deadline + Duration::from_millis(1)] {
            assert_eq!(
                remaining_at(deadline, now).unwrap_err().kind(),
                io::ErrorKind::TimedOut
            );
        }
    }

    #[test]
    fn completed_read_and_response_write_use_the_same_deadline() {
        let (mut peer, stream) = UnixStream::pair().unwrap();
        peer.write_all(b"a").unwrap();
        let mut stream = DeadlineStream::new(stream, Instant::now() + Duration::from_secs(1));
        let mut byte = [0];
        stream.read_exact(&mut byte).unwrap();
        assert_eq!(&byte, b"a");
        // Advance the fixed deadline deterministically; no wall-clock sleep
        // or peer traffic is needed to exercise expiry between operations.
        stream.deadline = Instant::now() - Duration::from_millis(1);
        assert_eq!(
            stream.read(&mut byte).unwrap_err().kind(),
            io::ErrorKind::TimedOut
        );
        assert_eq!(
            stream.write(b"response").unwrap_err().kind(),
            io::ErrorKind::TimedOut
        );
    }
}
