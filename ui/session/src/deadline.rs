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

    #[test]
    fn successful_fragment_reads_cannot_extend_the_frame_deadline() {
        use std::sync::{
            atomic::{AtomicBool, Ordering},
            Arc,
        };

        let (mut peer, stream) = UnixStream::pair().unwrap();
        peer.set_write_timeout(Some(Duration::from_millis(100)))
            .unwrap();
        let stopped = Arc::new(AtomicBool::new(false));
        let sender_stopped = stopped.clone();
        let sender = std::thread::spawn(move || {
            let stop_at = Instant::now() + Duration::from_secs(1);
            while !sender_stopped.load(Ordering::Relaxed) && Instant::now() < stop_at {
                if peer.write_all(b" ").is_err() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(20));
            }
        });
        let started = Instant::now();
        let mut stream = DeadlineStream::new(stream, started + Duration::from_millis(120));
        let result = trill_ui_core::read_frame(&mut stream);
        stopped.store(true, Ordering::Relaxed);
        sender.join().unwrap();
        assert!(
            result.is_err(),
            "an unterminated drip must never become a request"
        );
        assert!(
            started.elapsed() < Duration::from_secs(1),
            "partial reads renewed the budget"
        );
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn successful_partial_writes_cannot_extend_the_response_deadline() {
        use std::os::fd::AsRawFd;
        use std::sync::{
            atomic::{AtomicBool, Ordering},
            Arc,
        };

        let (mut peer, stream) = UnixStream::pair().unwrap();
        let buffer_bytes: libc::c_int = 4096;
        // A deliberately small real kernel send buffer makes a bounded frame
        // encounter backpressure even while the peer slowly consumes bytes.
        let result = unsafe {
            libc::setsockopt(
                stream.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_SNDBUF,
                (&buffer_bytes as *const libc::c_int).cast(),
                std::mem::size_of_val(&buffer_bytes) as libc::socklen_t,
            )
        };
        assert_eq!(result, 0, "{}", io::Error::last_os_error());
        peer.set_read_timeout(Some(Duration::from_millis(100)))
            .unwrap();
        let stopped = Arc::new(AtomicBool::new(false));
        let reader_stopped = stopped.clone();
        let reader = std::thread::spawn(move || {
            let mut received = 0;
            while !reader_stopped.load(Ordering::Relaxed) {
                match peer.read(&mut [0; 512]) {
                    Ok(0) | Err(_) => break,
                    Ok(count) => received += count,
                }
                std::thread::sleep(Duration::from_millis(20));
            }
            received
        });
        let started = Instant::now();
        let mut stream = DeadlineStream::new(stream, started + Duration::from_millis(120));
        let result = stream.write_all(&vec![b'x'; trill_ui_core::MAX_FRAME]);
        stopped.store(true, Ordering::Relaxed);
        let received = reader.join().unwrap();
        assert!(
            result.is_err(),
            "slow consumption must not extend a response budget"
        );
        assert!(received < trill_ui_core::MAX_FRAME);
        assert!(
            started.elapsed() < Duration::from_secs(1),
            "partial writes renewed the budget"
        );
    }
}
