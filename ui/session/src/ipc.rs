//! Bounded nonblocking host IPC; Session remains the only process-state owner.
//!
//! Every accepted peer keeps the existing single exchange deadline. Neither
//! partial input, dispatch nor partial output creates a fresh I/O allowance.

use super::{deadline::DeadlineStream, Session, EXCHANGE_BUDGET};
use std::io::{self, Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::time::Instant;
use trill_ui_core::host_peer::require_same_uid_peer;
use trill_ui_core::{parse_host_request, write_frame, Response, MAX_FRAME};

const MAX_CONNECTIONS: usize = 32;
const ACCEPTS_PER_TICK: usize = 8;
const BYTES_PER_TICK: usize = 8192;

struct Connection {
    stream: DeadlineStream,
    input: Vec<u8>,
    output: Option<Vec<u8>>,
    written: usize,
}

impl Connection {
    fn new(stream: UnixStream, deadline: Instant) -> io::Result<Self> {
        require_same_uid_peer(&stream)?;
        stream.set_nonblocking(true)?;
        Ok(Self {
            stream: DeadlineStream::new(stream, deadline),
            input: Vec::new(),
            output: None,
            written: 0,
        })
    }

    /// At most one bounded read and one bounded write; false closes this peer.
    fn step(&mut self, session: &mut Session) -> io::Result<bool> {
        self.stream.remaining()?;
        if self.output.is_none() {
            let mut bytes = [0; BYTES_PER_TICK];
            let remaining = (MAX_FRAME + 1 - self.input.len()).min(bytes.len());
            let count = match self.stream.read(&mut bytes[..remaining]) {
                Ok(count) => count,
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) =>
                {
                    return Ok(true);
                }
                Err(error) => return Err(error),
            };
            self.input.extend_from_slice(&bytes[..count]);
            let newline = self.input.iter().position(|byte| *byte == b'\n');
            if count != 0 && newline.is_none() && self.input.len() <= MAX_FRAME {
                return Ok(true);
            }
            let response = match newline {
                Some(end) if end < MAX_FRAME => match parse_host_request(&self.input[..=end]) {
                    Ok(request) => {
                        // A successful read or parse can finish after a
                        // descheduled owner exhausts its original allowance.
                        self.stream.remaining()?;
                        session.handle(request)
                    }
                    Err(error) => Response::Error {
                        message: format!("Invalid IPC request: {error}"),
                        session_instance: session.instance.clone(),
                    },
                },
                _ => Response::Error {
                    message: "Invalid IPC frame: invalid or oversized IPC frame".into(),
                    session_instance: session.instance.clone(),
                },
            };
            let mut output = Vec::new();
            match write_frame(&mut output, &response) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::InvalidData => {
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
                Err(error) => return Err(error),
            }
            // Retain the response, never the command: backpressure cannot
            // redispatch a launch, cancellation or original-owner request.
            self.output = Some(output);
        }
        let output = self.output.as_ref().expect("prepared response");
        let end = output.len().min(self.written + BYTES_PER_TICK);
        match self.stream.write(&output[self.written..end]) {
            Ok(0) => return Err(io::ErrorKind::WriteZero.into()),
            Ok(count) => self.written += count,
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) =>
            {
                return Ok(true);
            }
            Err(error) => return Err(error),
        }
        Ok(self.written < output.len())
    }
}

#[derive(Default)]
pub(super) struct Server {
    connections: Vec<Connection>,
}

impl Server {
    fn advance(&mut self, session: &mut Session) {
        session.refresh();
        self.connections
            .retain_mut(|connection| connection.step(session).unwrap_or(false));
        // Dispatch or response generation may outlive an unrelated child.
        // Reap on all transport return paths, including expiry and EOF.
        session.refresh();
    }

    pub(super) fn tick(
        &mut self,
        listener: &UnixListener,
        session: &mut Session,
    ) -> io::Result<()> {
        self.advance(session);
        for _ in 0..ACCEPTS_PER_TICK {
            if self.connections.len() >= MAX_CONNECTIONS {
                break;
            }
            match listener.accept() {
                Ok((stream, _)) => {
                    match Connection::new(stream, Instant::now() + EXCHANGE_BUDGET) {
                        Ok(connection) => self.connections.push(connection),
                        Err(error) => eprintln!("session request error: {error}"),
                    }
                }
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                    ) =>
                {
                    break;
                }
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }
}

#[cfg(test)]
pub(super) fn serve_one(stream: UnixStream, session: &mut Session) -> io::Result<()> {
    serve_one_until(stream, session, Instant::now() + EXCHANGE_BUDGET)
}

#[cfg(test)]
pub(super) fn serve_one_until(
    stream: UnixStream,
    session: &mut Session,
    deadline: Instant,
) -> io::Result<()> {
    session.refresh();
    let result = (|| {
        let mut connection = Connection::new(stream, deadline)?;
        loop {
            session.refresh();
            if !connection.step(session)? {
                return Ok(());
            }
            std::thread::sleep(std::time::Duration::from_millis(1));
        }
    })();
    session.refresh();
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Shutdown;
    use std::path::PathBuf;
    use std::time::Duration;
    use trill_ui_core::{read_frame, AppKind, Request, TaskState, Workspace};

    fn session() -> Session {
        Session::new(PathBuf::from("/bin/true")).unwrap()
    }

    fn launch(session: &Session) -> Request {
        Request::Launch {
            workspace: Workspace::Build,
            app: AppKind::Calculator,
            expected_instance: session.instance.clone(),
        }
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn stalled_input_and_output_allow_another_snapshot_and_child_reaping() {
        use std::os::fd::AsRawFd;

        let mut session = session();
        let Response::Task { task, .. } = session.handle(launch(&session)) else {
            panic!("expected an owned child");
        };
        // Observe exit without projecting it into TaskRecord: the shared
        // production tick must perform that projection and retire the child.
        session.children.get_mut(&task.id).unwrap().wait().unwrap();
        for id in 2..26 {
            let mut padding = task.clone();
            padding.id = id;
            padding.detail = "x".repeat(1000);
            session.tasks.insert(id, padding);
        }
        let (mut slow, slow_stream) = UnixStream::pair().unwrap();
        slow.write_all(b"{\"type\":").unwrap();
        let (mut blocked, blocked_stream) = UnixStream::pair().unwrap();
        let buffer_bytes: libc::c_int = 4096;
        assert_eq!(
            unsafe {
                libc::setsockopt(
                    blocked_stream.as_raw_fd(),
                    libc::SOL_SOCKET,
                    libc::SO_SNDBUF,
                    (&buffer_bytes as *const libc::c_int).cast(),
                    std::mem::size_of_val(&buffer_bytes) as libc::socklen_t,
                )
            },
            0
        );
        write_frame(&mut blocked, &Request::Snapshot).unwrap();
        let (mut fast, fast_stream) = UnixStream::pair().unwrap();
        write_frame(&mut fast, &Request::Snapshot).unwrap();
        fast.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut server = Server {
            connections: [slow_stream, blocked_stream, fast_stream]
                .into_iter()
                .map(|stream| Connection::new(stream, deadline).unwrap())
                .collect(),
        };
        for _ in 0..16 {
            server.advance(&mut session);
        }
        let response: Response = serde_json::from_slice(&read_frame(&mut fast).unwrap()).unwrap();
        let Response::Snapshot { tasks, .. } = response else {
            panic!("the ready client must receive its snapshot");
        };
        assert_eq!(tasks[0].state, TaskState::Completed);
        assert!(session.children.is_empty());
        assert_eq!(server.connections.len(), 2);
        assert!(server.connections[0].output.is_none());
        assert!(server.connections[1].output.is_some());
    }

    #[test]
    fn preparing_a_reply_does_not_renew_the_request_budget() {
        let mut session = session();
        let (mut peer, stream) = UnixStream::pair().unwrap();
        write_frame(&mut peer, &Request::Snapshot).unwrap();
        let mut connection =
            Connection::new(stream, Instant::now() + Duration::from_millis(400)).unwrap();
        let before = connection.stream.remaining().unwrap();
        assert!(!connection.step(&mut session).unwrap());
        assert!(connection.stream.remaining().unwrap() <= before);
    }

    #[test]
    fn eof_cannot_complete_a_mutating_frame_without_its_newline() {
        let mut session = session();
        let (mut peer, stream) = UnixStream::pair().unwrap();
        peer.write_all(&serde_json::to_vec(&launch(&session)).unwrap())
            .unwrap();
        peer.shutdown(Shutdown::Write).unwrap();
        serve_one(stream, &mut session).unwrap();
        let response: Response = serde_json::from_slice(&read_frame(&mut peer).unwrap()).unwrap();
        assert!(matches!(response, Response::Error { .. }));
        assert!(session.tasks.is_empty());
        assert_eq!(session.next_id, 1);
    }

    #[test]
    fn bytes_after_the_first_frame_cannot_dispatch_a_second_effect() {
        let mut session = session();
        let (mut peer, stream) = UnixStream::pair().unwrap();
        let request = launch(&session);
        write_frame(&mut peer, &request).unwrap();
        write_frame(&mut peer, &request).unwrap();
        serve_one(stream, &mut session).unwrap();
        assert_eq!(session.next_id, 2);
        assert_eq!(session.tasks.len(), 1);
        if let Some(child) = session.children.get_mut(&1) {
            child.wait().unwrap();
        }
        session.refresh();
        assert!(session.children.is_empty());
    }

    #[test]
    fn oversized_incremental_frame_is_refused_without_dispatch() {
        let mut session = session();
        let (mut peer, stream) = UnixStream::pair().unwrap();
        peer.write_all(&vec![b' '; MAX_FRAME + 1]).unwrap();
        serve_one(stream, &mut session).unwrap();
        let response: Response = serde_json::from_slice(&read_frame(&mut peer).unwrap()).unwrap();
        assert!(matches!(response, Response::Error { .. }));
        assert!(session.tasks.is_empty());
        assert_eq!(session.next_id, 1);
    }
}
