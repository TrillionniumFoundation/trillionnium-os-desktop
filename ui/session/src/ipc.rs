//! Bounded nonblocking host IPC. Session remains the only process-state owner.
//! Deadlines span the complete frame, including small incremental reads.
use super::{parse_host_request, require_same_uid_peer, write_frame, Response, Session};
use std::io::{self, Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::time::{Duration, Instant};
use trill_ui_core::MAX_FRAME;

pub const FRAME_DEADLINE: Duration = Duration::from_millis(500);
pub const MAX_CONNECTIONS: usize = 32;
const ACCEPTS_PER_TICK: usize = 8;
const BYTES_PER_TICK: usize = 8192;

struct Connection {
    stream: UnixStream,
    input: Vec<u8>,
    output: Option<Vec<u8>>,
    written: usize,
    expires: Instant,
}

impl Connection {
    fn new(stream: UnixStream) -> io::Result<Self> {
        require_same_uid_peer(&stream)?;
        stream.set_nonblocking(true)?;
        Ok(Self {
            stream,
            input: Vec::new(),
            output: None,
            written: 0,
            expires: Instant::now() + FRAME_DEADLINE,
        })
    }

    /// One bounded read and one bounded write per turn; false closes this peer.
    fn step(&mut self, session: &mut Session) -> io::Result<bool> {
        if Instant::now() >= self.expires {
            return Ok(false);
        }
        if self.output.is_none() {
            let mut bytes = [0; BYTES_PER_TICK];
            let remaining = (MAX_FRAME + 1 - self.input.len()).min(bytes.len());
            match self.stream.read(&mut bytes[..remaining]) {
                Ok(0) => return Ok(false),
                Ok(count) => self.input.extend_from_slice(&bytes[..count]),
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => return Ok(true),
                Err(error) if error.kind() == io::ErrorKind::Interrupted => return Ok(true),
                Err(error) => return Err(error),
            }
            let newline = self.input.iter().position(|byte| *byte == b'\n');
            if newline.is_none() && self.input.len() <= MAX_FRAME {
                return Ok(true);
            }
            let response = match newline {
                Some(end) if end < MAX_FRAME => match parse_host_request(&self.input[..=end]) {
                    Ok(request) => session.handle(request),
                    Err(error) => Response::Error {
                        message: format!("Invalid IPC request: {error}"),
                        session_instance: session.instance.clone(),
                    },
                },
                _ => Response::Error {
                    message: "Invalid or oversized IPC frame".into(),
                    session_instance: session.instance.clone(),
                },
            };
            let mut output = Vec::new();
            if write_frame(&mut output, &response).is_err() {
                output.clear();
                write_frame(
                    &mut output,
                    &Response::Error {
                        message: "Session snapshot is too large; no task state is being asserted"
                            .into(),
                        session_instance: session.instance.clone(),
                    },
                )?;
            }
            self.output = Some(output);
            // The reply has its own total deadline, never a per-write renewal.
            self.expires = Instant::now() + FRAME_DEADLINE;
        }
        let output = self.output.as_ref().expect("prepared response");
        let end = output.len().min(self.written + BYTES_PER_TICK);
        match self.stream.write(&output[self.written..end]) {
            Ok(0) => return Ok(false),
            Ok(count) => self.written += count,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => return Ok(true),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => return Ok(true),
            Err(error) => return Err(error),
        }
        Ok(self.written < output.len())
    }
}

#[derive(Default)]
pub struct Server {
    connections: Vec<Connection>,
}

impl Server {
    pub fn tick(&mut self, listener: &UnixListener, session: &mut Session) -> io::Result<()> {
        // Reaping and observation advance even with continuous malformed traffic.
        session.refresh();
        self.connections
            .retain_mut(|connection| connection.step(session).unwrap_or_default());
        for _ in 0..ACCEPTS_PER_TICK {
            if self.connections.len() >= MAX_CONNECTIONS {
                break; // bounded kernel backlog; existing peers expire within 500ms
            }
            match listener.accept() {
                Ok((stream, _)) => match Connection::new(stream) {
                    Ok(connection) => self.connections.push(connection),
                    Err(error) => eprintln!("session request error: {error}"),
                },
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => break,
                Err(error) if error.kind() == io::ErrorKind::Interrupted => break,
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }
}

#[cfg(test)]
pub(super) fn serve_one(stream: UnixStream, session: &mut Session) -> io::Result<()> {
    let mut connection = Connection::new(stream)?;
    loop {
        session.refresh();
        if !connection.step(session)? {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(1));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use trill_ui_core::{AppKind, TaskState, Workspace};

    #[test]
    fn drip_peer_does_not_block_other_requests_or_child_reaping_and_expires() {
        let mut session = Session::new(PathBuf::from("/bin/true")).unwrap();
        let Response::Task { task, .. } = session.launch(Workspace::Build, AppKind::Calculator)
        else {
            panic!()
        };
        let (mut slow_client, slow_server) = UnixStream::pair().unwrap();
        let mut slow = Connection::new(slow_server).unwrap();
        let expires = slow.expires;
        slow_client.write_all(b"{").unwrap();
        assert!(slow.step(&mut session).unwrap());
        let started = Instant::now();
        let mut completed = false;
        while started.elapsed() < Duration::from_millis(400) {
            slow_client.write_all(b" ").unwrap();
            assert!(slow.step(&mut session).unwrap());
            assert_eq!(
                slow.expires, expires,
                "partial input must never renew deadline"
            );
            let (mut client, server) = UnixStream::pair().unwrap();
            client.write_all(b"{\"type\":\"snapshot\"}\n").unwrap();
            serve_one(server, &mut session).unwrap();
            client
                .set_read_timeout(Some(Duration::from_millis(100)))
                .unwrap();
            let mut response = String::new();
            client.read_to_string(&mut response).unwrap();
            assert!(response.contains("snapshot"));
            completed |= session.tasks[&task.id].state == TaskState::Completed;
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(completed, "real child must be reaped during slow input");
        while Instant::now() < expires {
            std::thread::sleep(Duration::from_millis(1));
        }
        slow_client.write_all(b" ").unwrap();
        assert!(!slow.step(&mut session).unwrap());
    }
}
