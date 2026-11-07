//! Host-only tests for the production socket protocol and dispatcher adapter.
//!
//! The only injected authority is an owned temporary directory and ordinary
//! owned peer process in place of Android init/root. Transport, pidfds, peer
//! credentials, file identities, framing, deadlines and Daemon::handle stay real.

use super::*;
use std::cell::RefCell;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixListener;
use std::path::Path;

pub(in crate::control) const FIXTURE_DESCRIPTOR: &str = "DROIDLOOM_CATALOG_TEST_LISTENER";
pub(in crate::control) const FIXTURE_MODE: &str = "DROIDLOOM_CATALOG_TEST_MODE";

struct Fixture {
    owner: Process,
    root: File,
    path: PathBuf,
    root_object: Object,
    uid: u32,
    gid: u32,
    short_deadline: bool,
}

thread_local! {
    static FIXTURE: RefCell<Option<Fixture>> = const { RefCell::new(None) };
}

pub(in crate::control) struct FixtureGuard;

impl Drop for FixtureGuard {
    fn drop(&mut self) {
        FIXTURE.with(|slot| { slot.borrow_mut().take(); });
    }
}

pub(in crate::control) fn install_fixture(
    owner: u32, path: &Path, short_deadline: bool,
) -> FixtureGuard {
    let root = fs::OpenOptions::new().read(true)
        .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path).unwrap();
    let metadata = root.metadata().unwrap();
    let fixture = Fixture {
        owner: Process::open(owner).unwrap(),
        root_object: object(&root).unwrap(),
        root,
        path: path.to_owned(),
        uid: metadata.uid(),
        gid: metadata.gid(),
        short_deadline,
    };
    assert_eq!(fixture.owner.key.parent, std::process::id());
    FIXTURE.with(|slot| {
        let mut slot = slot.borrow_mut();
        assert!(slot.is_none(), "nested catalog authority override");
        *slot = Some(fixture);
    });
    FixtureGuard
}

pub(super) fn query_fixture(
    owner: u32, frame: &[u8], production_deadline: Instant,
) -> Option<Result<String, ControlError>> {
    FIXTURE.with(|slot| {
        let borrowed = slot.borrow();
        borrowed.as_ref().map(|fixture| {
            (|| {
                require(owner == fixture.owner.key.pid, "catalog fixture owner differs")?;
                let deadline = if fixture.short_deadline {
                    production_deadline.min(Instant::now() + Duration::from_millis(40))
                } else { production_deadline };
                let verify = || {
                    remaining(deadline)?;
                    fixture.owner.verify()?;
                    let named = fs::symlink_metadata(&fixture.path)
                        .map_err(|error| io_error("recheck owned fixture directory", error))?;
                    require(named.is_dir() && Object(named.dev(), named.ino()) == fixture.root_object
                            && object(&fixture.root)? == fixture.root_object,
                            "catalog fixture root changed")
                };
                let directory = socket_directory(&fixture.root, fixture.uid)?;
                query_endpoint(&directory, fixture.uid, fixture.gid, frame, deadline, |stream| {
                    let credential = credentials(stream)?;
                    require(credential.pid == fixture.owner.key.pid as i32
                            && credential.uid == fixture.uid && credential.gid == fixture.gid,
                            "catalog fixture peer is not its owned relistening process")?;
                    let peer = Process::open(credential.pid as u32)?;
                    require(peer.key == fixture.owner.key, "catalog fixture peer changed")?;
                    Ok(peer)
                }, verify)
            })()
        })
    })
}

fn write_frame(stream: &mut UnixStream, status: u8, payload: &[u8]) {
    stream.write_all(MAGIC).unwrap();
    stream.write_all(&[status]).unwrap();
    stream.write_all(&(payload.len() as u32).to_be_bytes()).unwrap();
    stream.write_all(payload).unwrap();
}

/// Private fixture entry: the parent has already bound/listened on this FD.
/// Re-listen in this owned child models LocalServerSocket(FileDescriptor).
pub(in crate::control) fn serve_received_listener(
    descriptor: i32, mode: &str, ready: &[u8],
) {
    assert!(descriptor >= 3);
    assert!(["fresh", "no-relisten", "replace", "replace-directory", "replace-dev",
        "delayed", "backend-error", "bad-json"]
        .contains(&mode));
    // SAFETY: the fixture command explicitly inherited this one listener FD;
    // this child owns its copy, which was not previously wrapped in Rust.
    let listener = unsafe { UnixListener::from_raw_fd(descriptor) };
    if mode != "no-relisten" {
        // SAFETY: descriptor is the held AF_UNIX listener. Re-listen resets its
        // SO_PEERCRED to this child, matching Android's LocalServerSocket API.
        assert_eq!(unsafe { libc::listen(listener.as_raw_fd(), 50) }, 0);
    }
    listener.set_nonblocking(true).unwrap();
    let path = listener.local_addr().unwrap().as_pathname().unwrap().to_owned();
    std::io::stderr().write_all(ready).unwrap();
    let mut request_count = 0;
    let mut replacement = None;
    loop {
        let mut poll = libc::pollfd {
            fd: 0, events: libc::POLLIN | libc::POLLHUP, revents: 0,
        };
        // SAFETY: observe only the test-owned stdin pipe, without blocking.
        assert!(unsafe { libc::poll(&mut poll, 1, 0) } >= 0);
        if poll.revents & (libc::POLLIN | libc::POLLHUP) != 0 {
            let mut byte = [0_u8; 1];
            assert_eq!(std::io::stdin().read(&mut byte).unwrap(), 0);
            break;
        }
        let (mut stream, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(5));
                continue;
            }
            Err(error) => panic!("owned fixture accept failed: {error}"),
        };
        stream.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        stream.set_write_timeout(Some(Duration::from_secs(1))).unwrap();
        let mut frame = Vec::new();
        (&mut stream).take(531).read_to_end(&mut frame).unwrap();
        if frame.is_empty() { continue; } // A rejected peer sends no request.
        assert!(frame.len() >= 19 && frame.len() <= 530 && &frame[..8] == MAGIC);
        let size = u16::from_be_bytes([frame[17], frame[18]]) as usize;
        assert_eq!(frame.len(), 19 + size);
        request_count += 1;
        if mode == "delayed" { std::thread::sleep(Duration::from_millis(200)); }
        if ["replace", "replace-directory", "replace-dev"].contains(&mode) {
            if mode == "replace" {
                fs::remove_file(&path).unwrap();
            } else {
                let directory = path.parent().unwrap();
                let moved = if mode == "replace-dev" {
                    directory.parent().unwrap()
                } else { directory };
                fs::rename(moved, moved.with_file_name(if mode == "replace-dev" {
                    "dev-old"
                } else { "socket-old" })).unwrap();
                fs::create_dir_all(directory).unwrap();
                fs::set_permissions(directory.parent().unwrap(),
                    fs::Permissions::from_mode(0o700)).unwrap();
                fs::set_permissions(directory, fs::Permissions::from_mode(0o700)).unwrap();
            }
            replacement = Some(UnixListener::bind(&path).unwrap());
            fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        }
        if mode == "backend-error" {
            write_frame(&mut stream, 2, b"CATALOG_UNAVAILABLE");
        } else if mode == "bad-json" {
            write_frame(&mut stream, 0, b"[{\"name\":\"incomplete\"}]");
        } else if frame[8] == 1 {
            let payload = if request_count == 1 {
                r#"[{"name":"Before","package":"org.example.catalog","component":"org.example.catalog/.Main","icon_key":"1:2:3"}]"#
            } else {
                r#"[{"name":"After","package":"org.example.catalog","component":"org.example.catalog/.Main","icon_key":"2:3:4"},{"name":"New","package":"org.example.newapp","component":"org.example.newapp/.Main","icon_key":"1:1:1"}]"#
            };
            // A timed-out client may have closed; it is not a fixture leak.
            if mode == "delayed" {
                let _ = stream.write_all(MAGIC);
            } else {
                write_frame(&mut stream, 0, payload.as_bytes());
            }
        } else {
            assert_eq!(frame[8], 2);
            write_frame(&mut stream, 0, b"iVBORw0KGgo=");
        }
    }
    drop(replacement);
}

fn socket_case(status: u8, payload: Vec<u8>, declared: usize, extra: &[u8])
        -> Result<String, ControlError> {
    let (mut client, mut server) = UnixStream::pair().unwrap();
    client.set_nonblocking(true).unwrap();
    server.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
    server.set_write_timeout(Some(Duration::from_secs(1))).unwrap();
    let extra = extra.to_vec();
    let task = std::thread::spawn(move || {
        let mut request = Vec::new();
        server.read_to_end(&mut request).unwrap();
        assert_eq!(request, encode(Query::List { user: 0 }).unwrap());
        server.write_all(MAGIC).unwrap();
        server.write_all(&[status]).unwrap();
        server.write_all(&(declared as u32).to_be_bytes()).unwrap();
        // The receiver may reject the header and close before the rest. These
        // are deliberately malformed responses, not production I/O results.
        let _ = server.write_all(&payload);
        let _ = server.write_all(&extra);
    });
    let result = exchange(&mut client, &encode(Query::List { user: 0 }).unwrap(),
        Instant::now() + Duration::from_secs(1));
    drop(client);
    task.join().expect("owned socket responder joined");
    result
}

#[test]
fn wire_encoding_is_bounded_and_compatible_with_the_java_request() {
    let list = encode(Query::List { user: 0 }).unwrap();
    assert_eq!(list, [b"DLCAT001".as_slice(), &[1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]].concat());
    let icon = encode(Query::Icon {
        user: 10, component: "org.example.catalog/.Main", size: 128,
    }).unwrap();
    assert_eq!(&icon[..9], b"DLCAT001\x02");
    assert_eq!(&icon[9..13], &10_u32.to_be_bytes());
    assert_eq!(&icon[13..17], &128_u32.to_be_bytes());
    assert_eq!(u16::from_be_bytes([icon[17], icon[18]]) as usize, icon.len() - 19);
    assert_eq!(&icon[19..], b"org.example.catalog/.Main");
    for request in [
        Query::List { user: u32::MAX },
        Query::Icon { user: 0, component: "org.example/Bad-Name", size: 128 },
        Query::Icon { user: 0, component: "org.example/.Main", size: 15 },
        Query::Icon { user: 0, component: "org.example/.Main", size: 513 },
    ] { assert!(encode(request).is_err()); }
}

#[test]
fn real_socket_responses_reject_limits_truncation_utf8_tail_and_open_errors() {
    assert_eq!(socket_case(0, b"[]".to_vec(), 2, b"").unwrap(), "[]");
    for (status, payload, declared, extra, expected) in [
        (5, b"x".to_vec(), 1, b"".as_slice(), "declared bound"),
        (0, b"".to_vec(), MAX_RESPONSE + 1, b"".as_slice(), "declared bound"),
        (0, b"x".to_vec(), 2, b"".as_slice(), "truncated"),
        (0, vec![0xff], 1, b"".as_slice(), "not UTF-8"),
        (0, b"[]".to_vec(), 2, b"x".as_slice(), "trailing data"),
        (2, b"PRIVATE_ERROR".to_vec(), 13, b"".as_slice(), "closed vocabulary"),
        (2, b"CATALOG_UNAVAILABLE".to_vec(), 19, b"".as_slice(), "catalog unavailable"),
    ] {
        let error = socket_case(status, payload, declared, extra).unwrap_err().to_string();
        assert!(error.contains(expected), "{error}");
    }
}

#[test]
fn bounded_socket_deadline_has_no_late_success() {
    let (mut client, mut server) = UnixStream::pair().unwrap();
    client.set_nonblocking(true).unwrap();
    server.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
    let task = std::thread::spawn(move || {
        let mut request = Vec::new();
        server.read_to_end(&mut request).unwrap();
        assert_eq!(request, encode(Query::List { user: 0 }).unwrap());
        std::thread::sleep(Duration::from_millis(100));
    });
    let result = exchange(&mut client, &encode(Query::List { user: 0 }).unwrap(),
        Instant::now() + Duration::from_millis(30));
    drop(client);
    task.join().unwrap();
    assert!(result.unwrap_err().to_string().contains("timed out"));
}
