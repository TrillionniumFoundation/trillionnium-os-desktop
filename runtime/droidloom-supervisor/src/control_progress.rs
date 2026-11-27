//! Opt-in progress frames and a wall-clock deadline for lifecycle clients.

use std::fs;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

use super::{
    ControlError, ControlRequest, ControlResponse, MAX_MESSAGE_BYTES, MAX_RESPONSE_BYTES, apk,
    io_error,
};

pub(super) const LOG_HINT: &str = "Check the logs with:\n  journalctl -b -u droidloomd.service -n 200 --no-pager\n  journalctl --user -b -u droidloom.service -n 100 --no-pager";
const REQUEST_TIMEOUT: Duration = Duration::from_secs(250);
const GALLERY_CUSTODY_RESPONSE_TIMEOUT: Duration = Duration::from_secs(330);
const UPDATE_INTERVAL: Duration = Duration::from_secs(10);

pub(super) fn response_timeout(request: &ControlRequest) -> Duration {
    match request {
        ControlRequest::InspectApplication { package, user: 0 }
            if package == super::application_custody::GALLERY_PACKAGE =>
        {
            // Client waiting only. The same production operation keeps its
            // original 300-second absolute deadline and real reap rules.
            GALLERY_CUSTODY_RESPONSE_TIMEOUT
        }
        // Transport allowance only; the Ready-owner operation has its own
        // absolute 60-second work-and-retirement budget.
        ControlRequest::ObserveRuntimeVintf { .. }
        | ControlRequest::ObserveRuntimeMain { .. }
        | ControlRequest::ObserveApplicationEngine { .. }
        | ControlRequest::ObserveUserZeroPackageInventory { .. }
        | ControlRequest::ObserveApplicationExitState { .. }
        | ControlRequest::ObserveApplicationPermissionState { .. } => Duration::from_secs(70),
        _ => REQUEST_TIMEOUT,
    }
}

// Legacy clients still send a bare ControlRequest and receive one JSON object.
// The envelope opts into newline-delimited progress followed by the same result.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ProgressRequest {
    pub request: ControlRequest,
}

#[derive(Deserialize)]
#[serde(untagged)]
pub(super) enum IncomingRequest {
    Progress(ProgressRequest),
    Legacy(ControlRequest),
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProgressFrame {
    progress: String,
}

#[derive(Default)]
pub(super) struct Reporter(Option<UnixStream>);

impl Reporter {
    pub fn new(stream: &UnixStream, enabled: bool) -> Result<Self, ControlError> {
        Ok(Self(if enabled {
            Some(
                stream
                    .try_clone()
                    .map_err(|e| io_error("open lifecycle progress stream", e))?,
            )
        } else {
            None
        }))
    }

    pub fn report(&self, message: &str) {
        if let Some(mut stream) = self.0.as_ref() {
            let mut encoded = serde_json::to_vec(&ProgressFrame {
                progress: message.into(),
            })
            .expect("progress strings serialize");
            encoded.push(b'\n');
            // A disconnected client must not tear down Android. The socket's
            // write timeout also bounds clients that stop reading progress.
            let _ = stream.write_all(&encoded);
        }
    }
}

pub(super) fn request(
    socket: &Path,
    request: &ControlRequest,
    file: Option<&fs::File>,
    progress: Option<&mut dyn FnMut(&str)>,
) -> Result<ControlResponse, ControlError> {
    let started = Instant::now();
    let stream = connect(socket).map_err(|source| io_error("connect to droidloomd", source))?;
    request_on(stream, started, request, file, progress)
}

pub(super) fn request_on(
    mut stream: UnixStream,
    started: Instant,
    request: &ControlRequest,
    file: Option<&fs::File>,
    progress: Option<&mut dyn FnMut(&str)>,
) -> Result<ControlResponse, ControlError> {
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .map_err(|e| io_error("set lifecycle request write timeout", e))?;
    let encoded = if progress.is_some() {
        serde_json::to_vec(&serde_json::json!({"request": request}))?
    } else {
        serde_json::to_vec(request)?
    };
    if encoded.len() as u64 > MAX_MESSAGE_BYTES {
        return Err(ControlError::Invalid(
            "lifecycle request is too large".into(),
        ));
    }
    let remaining = if let Some(file) = file {
        apk::send_file(&stream, encoded[0], file)?;
        &encoded[1..]
    } else {
        &encoded[..]
    };
    stream
        .write_all(remaining)
        .and_then(|()| stream.shutdown(std::net::Shutdown::Write))
        .map_err(|e| io_error("send lifecycle request", e))?;
    read_response(
        &mut stream,
        started,
        response_timeout(request),
        UPDATE_INTERVAL,
        progress,
    )
}


/// Bound the existing transport by the original caller's absolute deadline.
/// This is an in-process bound; it grants no operation or wire authority.
pub(super) fn request_on_until(
    mut stream: UnixStream,
    request: &ControlRequest,
    deadline: Instant,
) -> Result<ControlResponse, ControlError> {
    let started=Instant::now();
    let end=deadline.min(started+response_timeout(request));
    let remaining=|| end.checked_duration_since(Instant::now())
        .filter(|v|!v.is_zero()).ok_or_else(||ControlError::Invalid(
            "original native leaf deadline expired".into()));
    let encoded=serde_json::to_vec(request)?;
    if encoded.len() as u64>MAX_MESSAGE_BYTES {
        return Err(ControlError::Invalid("lifecycle request is too large".into()));
    }
    let mut pending=encoded.as_slice();
    while !pending.is_empty() {
        stream.set_write_timeout(Some(remaining()?.min(Duration::from_secs(2))))
            .map_err(|e|io_error("bound original request write",e))?;
        match stream.write(pending) {
            Ok(0)=>return Err(ControlError::Invalid("fixed lifecycle request write returned zero".into())),
            Ok(n)=>pending=&pending[n..],
            Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
            Err(e)=>return Err(io_error("write bounded fixed lifecycle request",e)),
        }
    }
    remaining()?;
    stream.shutdown(std::net::Shutdown::Write).map_err(|e|io_error("finish bounded request write",e))?;
    let result=read_response(&mut stream,started,end.saturating_duration_since(started),
        UPDATE_INTERVAL,None)?;
    remaining()?;
    Ok(result)
}

pub(super) fn connect(path: &Path) -> io::Result<UnixStream> {
    // Blocking connect can wait indefinitely when a busy daemon's accept queue
    // fills. A nonblocking AF_UNIX connect reports that condition as EAGAIN.
    // SAFETY: zero initializes a valid sockaddr_un. The pathname is bounded
    // and NUL terminated below before passing the address to connect.
    let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
    let bytes = path.as_os_str().as_bytes();
    if bytes.is_empty() || bytes.len() >= address.sun_path.len() || bytes.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid lifecycle socket path",
        ));
    }
    address.sun_family =
        libc::sa_family_t::try_from(libc::AF_UNIX).expect("AF_UNIX fits sa_family_t");
    for (target, byte) in address.sun_path.iter_mut().zip(bytes) {
        *target = libc::c_char::from_ne_bytes([*byte]);
    }
    // SAFETY: these constants create a new owned Unix stream descriptor.
    let fd = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: fd is newly created and ownership moves into this stream.
    let stream = unsafe { UnixStream::from_raw_fd(fd) };
    let length = libc::socklen_t::try_from(
        std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1,
    )
    .expect("bounded Unix socket address fits socklen_t");
    // SAFETY: address and length describe the initialized pathname above; the
    // descriptor remains owned by stream throughout the call.
    if unsafe {
        libc::connect(
            stream.as_raw_fd(),
            std::ptr::from_ref(&address).cast(),
            length,
        )
    } != 0
    {
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::WouldBlock {
            return Err(io::Error::new(
                io::ErrorKind::WouldBlock,
                format!("Droidloom is busy and its request queue is full.\n{LOG_HINT}"),
            ));
        }
        return Err(error);
    }
    stream.set_nonblocking(false)?;
    Ok(stream)
}

fn read_response(
    stream: &mut UnixStream,
    started: Instant,
    timeout: Duration,
    update_interval: Duration,
    mut progress: Option<&mut dyn FnMut(&str)>,
) -> Result<ControlResponse, ControlError> {
    let mut last_progress =
        "Waiting for Droidloom to respond; another request may be in progress".to_owned();
    if let Some(report) = progress.as_mut() {
        report(&format!(
            "{last_progress} (up to {} seconds).",
            timeout.as_secs()
        ));
    }
    let mut next_update = started + update_interval;
    let deadline = started + timeout;
    let mut pending = Vec::new();
    let mut total_bytes = 0_u64;
    let mut buffer = [0; 8192];
    loop {
        let now = Instant::now();
        if now >= deadline {
            return Err(ControlError::Invalid(format!(
                "Droidloom did not finish within {} seconds. Android or the lifecycle service may be stuck.\nLast progress: {last_progress}.\n{LOG_HINT}\nThe operation may still finish in the background; check its result before retrying.",
                timeout.as_secs()
            )));
        }
        if now >= next_update {
            if let Some(report) = progress.as_mut() {
                report(&format!(
                    "{last_progress} ({} seconds elapsed; {} seconds remaining).",
                    started.elapsed().as_secs(),
                    deadline.saturating_duration_since(now).as_secs()
                ));
            }
            next_update = now + update_interval;
        }
        stream
            .set_read_timeout(Some(
                deadline.saturating_duration_since(now).min(update_interval),
            ))
            .map_err(|e| io_error("set lifecycle response timeout", e))?;
        let count = match stream.read(&mut buffer) {
            Ok(count) => count,
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::WouldBlock
                        | io::ErrorKind::TimedOut
                        | io::ErrorKind::Interrupted
                ) =>
            {
                continue;
            }
            Err(e) => return Err(io_error("read lifecycle response", e)),
        };
        total_bytes += count as u64;
        if total_bytes > MAX_RESPONSE_BYTES {
            return Err(ControlError::Invalid(
                "lifecycle response is too large".into(),
            ));
        }
        pending.extend_from_slice(&buffer[..count]);
        while let Some(end) = pending
            .iter()
            .position(|byte| *byte == b'\n')
            .or_else(|| (count == 0 && !pending.is_empty()).then_some(pending.len()))
        {
            let frame: Vec<_> = pending.drain(..end).collect();
            if pending.first() == Some(&b'\n') {
                pending.remove(0);
            }
            if let Ok(frame) = serde_json::from_slice::<ProgressFrame>(&frame) {
                last_progress = frame.progress;
                if let Some(report) = progress.as_mut() {
                    report(&last_progress);
                }
                next_update = Instant::now() + update_interval;
            } else {
                let response: ControlResponse = serde_json::from_slice(&frame)?;
                if !response.ok && response.message.contains("missing field `command`") {
                    return Err(ControlError::Invalid("The running Droidloom daemon does not support boot progress. Update the runtime package and run `droidloomctl restart` to load the matching daemon.".into()));
                }
                return Ok(response);
            }
        }
        if count == 0 {
            return Err(ControlError::Invalid(format!(
                "Droidloom disconnected before reporting a result.\n{LOG_HINT}"
            )));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_leaf_absolute_budget_never_restarts_the_regular_response_timeout() {
        let (client,mut server)=UnixStream::pair().unwrap();
        let worker=thread::spawn(move|| {
            let mut request=Vec::new();server.read_to_end(&mut request).unwrap();
            let v:serde_json::Value=serde_json::from_slice(&request).unwrap();
            assert_eq!(v["command"],"status");
            thread::sleep(Duration::from_millis(200));
        });
        let started=Instant::now();
        assert!(request_on_until(client,&ControlRequest::Status,
            started+Duration::from_millis(40)).is_err());
        assert!(started.elapsed()<Duration::from_secs(1));
        worker.join().unwrap();
    }
    #[test]
    fn native_leaf_expired_budget_sends_nothing_and_live_budget_reads_real_response() {
        let (client,mut server)=UnixStream::pair().unwrap();
        assert!(request_on_until(client,&ControlRequest::Status,
            Instant::now()-Duration::from_millis(1)).is_err());
        let mut raw=Vec::new();server.read_to_end(&mut raw).unwrap();assert!(raw.is_empty());
        let (client,mut server)=UnixStream::pair().unwrap();
        let worker=thread::spawn(move|| {
            let mut request=Vec::new();server.read_to_end(&mut request).unwrap();
            assert!(!request.is_empty());server.write_all(SUCCESS).unwrap();
            server.write_all(b"\n").unwrap();
        });
        let value=request_on_until(client,&ControlRequest::Status,Instant::now()+Duration::from_secs(2)).unwrap();
        assert!(value.ok);worker.join().unwrap();
    }


    #[test]
    fn only_exact_user_zero_gallery_inspection_gets_the_longer_response_wait() {
        assert_eq!(response_timeout(&ControlRequest::InspectApplication {
            package: "com.android.gallery3d".into(), user: 0,
        }), Duration::from_secs(330));
        for request in [
            ControlRequest::InspectApplication { package: "com.android.gallery3d".into(), user: 1 },
            ControlRequest::InspectApplication { package: "com.android.contacts".into(), user: 0 },
            ControlRequest::InspectApplication { package: "com.android.gallery3d.other".into(), user: 0 },
            ControlRequest::Status,
            ControlRequest::Stop,
            ControlRequest::Install { user: 0 },
        ] {
            assert_eq!(response_timeout(&request), Duration::from_secs(250));
        }
    }

    #[test]
    fn complete_three_mib_response_uses_the_unchanged_four_mib_bound() {
        let (mut client, mut server) = UnixStream::pair().unwrap();
        let expected = "x".repeat(3 * 1024 * 1024);
        let mut raw = serde_json::to_vec(&serde_json::json!({
            "ok": true, "state": "running", "message": &expected,
        })).unwrap();
        raw.push(b'\n');
        assert!(raw.len() as u64 > MAX_MESSAGE_BYTES);
        assert!((raw.len() as u64) < MAX_RESPONSE_BYTES);
        let writer = std::thread::spawn(move || server.write_all(&raw));
        let observed = read_response(
            &mut client, Instant::now(), Duration::from_secs(5), Duration::from_millis(50), None,
        );
        drop(client);
        writer.join().unwrap().unwrap();
        assert_eq!(observed.unwrap().message, expected);
    }
    use std::os::unix::net::UnixListener;
    use std::thread;

    const SUCCESS: &[u8] = br#"{"ok":true,"state":"running","message":"Android is ready"}"#;

    #[test]
    fn container_readiness_uses_the_same_authenticated_connection() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("control.sock");
        let listener = UnixListener::bind(&path).unwrap();
        let server = thread::spawn(move || {
            // A different process must not receive even the readiness request.
            let (mut rejected, _) = listener.accept().unwrap();
            let mut bytes = Vec::new();
            rejected.read_to_end(&mut bytes).unwrap();
            assert!(bytes.is_empty());
            let (mut accepted, _) = listener.accept().unwrap();
            accepted.read_to_end(&mut bytes).unwrap();
            let frame: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
            assert_eq!(frame["request"]["command"], "wait_ready");
            accepted.write_all(SUCCESS).unwrap();
            accepted.write_all(b"\n").unwrap();
        });
        let pid = std::process::id();
        let error = crate::control::container_entry_readiness(&path, pid + 1, true, &mut |_| {}).unwrap_err();
        assert!(error.to_string().contains("different service process"));
        let response = crate::control::container_entry_readiness(&path, pid, true, &mut |_| {}).unwrap();
        assert!(response.ok);
        assert_eq!(response.state, crate::control::CellState::Running);
        server.join().unwrap();
    }

    #[test]
    fn progress_envelope_preserves_strict_request_validation() {
        for invalid in [
            r#"{"request":{"command":"install","user":0,"user":10}}"#,
            r#"{"request":{"command":"wait_ready"},"request":{"command":"stop"}}"#,
            r#"{"request":{"command":"wait_ready"},"unexpected":true}"#,
            r#"{"request":{"command":"install","user":0,"unexpected":true}}"#,
        ] {
            assert!(
                serde_json::from_str::<IncomingRequest>(invalid).is_err(),
                "{invalid}"
            );
        }
    }

    #[test]
    fn fragmented_progress_and_result_are_delivered_before_disconnect() {
        let (mut client, mut server) = UnixStream::pair().unwrap();
        let worker = thread::spawn(move || {
            for part in [
                b"{\"pro".as_slice(),
                b"gress\":\"Android boot phase: input service\"}\n",
                SUCCESS,
                b"\n",
            ] {
                server.write_all(part).unwrap();
            }
            // The final newline is enough; the client need not wait for EOF.
            thread::sleep(Duration::from_millis(100));
        });
        let mut messages = Vec::new();
        let response = read_response(
            &mut client,
            Instant::now(),
            Duration::from_secs(1),
            Duration::from_millis(10),
            Some(&mut |message| messages.push(message.to_owned())),
        )
        .unwrap();
        assert!(response.ok);
        assert!(
            messages
                .iter()
                .any(|message| message == "Android boot phase: input service")
        );
        worker.join().unwrap();
    }

    #[test]
    fn legacy_result_without_newline_still_works() {
        let (mut client, mut server) = UnixStream::pair().unwrap();
        server.write_all(SUCCESS).unwrap();
        drop(server);
        assert!(
            read_response(
                &mut client,
                Instant::now(),
                Duration::from_secs(1),
                UPDATE_INTERVAL,
                None
            )
            .unwrap()
            .ok
        );
    }

    #[test]
    fn silent_and_chatty_daemons_both_have_a_wall_clock_deadline() {
        for chatty in [false, true] {
            let (mut client, mut server) = UnixStream::pair().unwrap();
            let worker = thread::spawn(move || {
                let until = Instant::now() + Duration::from_millis(200);
                while Instant::now() < until {
                    if chatty
                        && server
                            .write_all(b"{\"progress\":\"waiting for Android boot\"}\n")
                            .is_err()
                    {
                        break;
                    }
                    thread::sleep(Duration::from_millis(5));
                }
            });
            let started = Instant::now();
            let mut messages = Vec::new();
            let error = read_response(
                &mut client,
                started,
                Duration::from_millis(60),
                Duration::from_millis(10),
                Some(&mut |message| messages.push(message.to_owned())),
            )
            .unwrap_err()
            .to_string();
            assert!(started.elapsed() < Duration::from_secs(1));
            assert!(error.contains("may be stuck"));
            assert!(error.contains("journalctl -b -u droidloomd.service"));
            assert!(error.contains("may still finish in the background"));
            if !chatty {
                assert!(
                    messages
                        .iter()
                        .any(|message| message.contains("seconds remaining"))
                );
            }
            drop(client);
            worker.join().unwrap();
        }
    }

    #[test]
    fn partial_response_and_progress_only_disconnect_do_not_report_success() {
        for bytes in [b"{\"ok\":true".as_slice(), b"{\"progress\":\"booting\"}\n"] {
            let (mut client, mut server) = UnixStream::pair().unwrap();
            server.write_all(bytes).unwrap();
            drop(server);
            assert!(
                read_response(
                    &mut client,
                    Instant::now(),
                    Duration::from_secs(1),
                    UPDATE_INTERVAL,
                    None
                )
                .is_err()
            );
        }
    }

    #[test]
    fn full_accept_queue_is_reported_without_blocking_connect() {
        let directory = tempfile::tempdir().unwrap();
        let socket = directory.path().join("busy.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        // SAFETY: listener owns an open socket; a zero backlog allows one
        // queued Linux connection, which is kept alive below.
        assert_eq!(unsafe { libc::listen(listener.as_raw_fd(), 0) }, 0);
        let _queued = connect(&socket).unwrap();
        let started = Instant::now();
        let error = connect(&socket).unwrap_err().to_string();
        assert!(started.elapsed() < Duration::from_secs(1));
        assert!(error.contains("request queue is full"));
    }
}
