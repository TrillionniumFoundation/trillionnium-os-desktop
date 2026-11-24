//! Fixed companion endpoints adopted from the original owner. No Android process
//! can reach the desktop user's runtime directory.
use crate::production::{
    Registration,
    wire::{self, Role},
};
use std::{
    fs,
    io::{self, Read, Write},
    net::Shutdown,
    os::{
        fd::{AsFd, AsRawFd, BorrowedFd, RawFd},
        unix::{
            fs::{FileTypeExt, MetadataExt, PermissionsExt},
            net::{UnixDatagram, UnixListener, UnixStream},
        },
    },
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, TryRecvError},
    },
    thread::JoinHandle,
    time::Duration,
};

#[derive(Clone)]
struct Authority {
    grant: Arc<Registration>,
    original: Arc<Registration>,
}
impl Authority {
    fn check(&self) -> io::Result<()> {
        let result = self.original.check().and_then(|()| self.grant.check());
        if result.is_err() {
            self.grant.revoke();
        }
        result
    }
}
pub(crate) struct Stream {
    socket: UnixStream,
    authority: Option<Authority>,
}
impl Stream {
    pub(crate) fn check(&self) -> io::Result<()> {
        if let Some(a) = &self.authority {
            a.check()?;
        }
        Ok(())
    }
    pub(crate) fn try_clone(&self) -> io::Result<Self> {
        self.check()?;
        Ok(Self {
            socket: self.socket.try_clone()?,
            authority: self.authority.clone(),
        })
    }
    pub(crate) fn set_nonblocking(&self, value: bool) -> io::Result<()> {
        self.socket.set_nonblocking(value)
    }
    pub(crate) fn shutdown(&self, how: Shutdown) -> io::Result<()> {
        self.socket.shutdown(how)
    }
    #[cfg(test)]
    pub(crate) fn test_socket(socket: UnixStream) -> Self {
        Self {
            socket,
            authority: None,
        }
    }
}
impl AsRawFd for Stream {
    fn as_raw_fd(&self) -> RawFd {
        self.socket.as_raw_fd()
    }
}
impl AsFd for Stream {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.socket.as_fd()
    }
}
impl Read for &Stream {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        self.check()?;
        let n = (&self.socket).read(bytes)?;
        self.check()?;
        Ok(n)
    }
}
impl Read for Stream {
    fn read(&mut self, b: &mut [u8]) -> io::Result<usize> {
        Read::read(&mut &*self, b)
    }
}
impl Write for &Stream {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.check()?;
        let n = (&self.socket).write(bytes)?;
        self.check()?;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.check()?;
        (&self.socket).flush()
    }
}
impl Write for Stream {
    fn write(&mut self, b: &[u8]) -> io::Result<usize> {
        Write::write(&mut &*self, b)
    }
    fn flush(&mut self) -> io::Result<()> {
        Write::flush(&mut &*self)
    }
}
enum Source {
    Development {
        listener: UnixListener,
        path: PathBuf,
        node: wire::Node,
        uid: u32,
    },
    Production {
        wake: UnixDatagram,
        receiver: Receiver<Stream>,
        stopped: Arc<AtomicBool>,
        terminal: Arc<Mutex<Option<String>>>,
        worker: Option<JoinHandle<()>>,
    },
}
pub(crate) struct Listener {
    source: Source,
}
impl Listener {
    pub(crate) fn new(
        path: PathBuf,
        role: Role,
        original: Option<Arc<Registration>>,
        uid: u32,
    ) -> io::Result<Self> {
        if let Some(original) = original {
            return Self::production(role, original);
        }
        match fs::symlink_metadata(&path) {
            Ok(m) if m.file_type().is_socket() => fs::remove_file(&path)?,
            Ok(_) => return Err(io::ErrorKind::AlreadyExists.into()),
            Err(e) if e.kind() == io::ErrorKind::NotFound => (),
            Err(e) => return Err(e),
        }
        let listener = UnixListener::bind(&path)?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
        listener.set_nonblocking(true)?;
        let m = fs::symlink_metadata(&path)?;
        Ok(Self {
            source: Source::Development {
                listener,
                path,
                node: wire::Node(m.dev(), m.ino()),
                uid,
            },
        })
    }
    fn production(role: Role, original: Arc<Registration>) -> io::Result<Self> {
        wire::check(role != Role::Composer, "Composer is not a stream bridge")?;
        original.check()?;
        let (wake, notify) = UnixDatagram::pair()?;
        wake.set_nonblocking(true)?;
        notify.set_nonblocking(true)?;
        let stopped = Arc::new(AtomicBool::new(false));
        let terminal = Arc::new(Mutex::new(None));
        let (tx, receiver) = mpsc::sync_channel(1);
        let stop = stopped.clone();
        let done = terminal.clone();
        let worker = std::thread::Builder::new()
            .name(format!("dl-{:?}-owner", role))
            .spawn(move || {
                droidloom_cpu_placement::current(droidloom_cpu_placement::Role::Background);
                let result = (|| -> io::Result<()> {
                    while !stop.load(Ordering::Acquire) {
                        original.check()?;
                        let grant = match Registration::connect_role(
                            role,
                            Some(&original),
                            Some(&stop),
                        ) {
                            Ok(value) => Arc::new(value),
                            Err(e) => {
                                if stop.load(Ordering::Acquire) {
                                    break;
                                }
                                original.check()?;
                                eprintln!(
                                    "Droidloom {:?}: waiting for original Android endpoint: {e}",
                                    role
                                );
                                for _ in 0..10 {
                                    if stop.load(Ordering::Acquire) {
                                        break;
                                    }
                                    std::thread::sleep(Duration::from_millis(50));
                                }
                                continue;
                            }
                        };
                        let socket = UnixStream::from(grant.endpoint()?);
                        // Each consumer selects blocking/async operation on this
                        // endpoint, which the owner only retains for revocation.
                        socket.set_nonblocking(false)?;
                        let stream = Stream {
                            socket,
                            authority: Some(Authority {
                                grant: grant.clone(),
                                original: original.clone(),
                            }),
                        };
                        if tx.try_send(stream).is_err() {
                            return Err(io::Error::other("companion consumer disappeared"));
                        }
                        let _ = notify.send(&[1]);
                        loop {
                            if stop.load(Ordering::Acquire) {
                                break;
                            }
                            if let Err(e) = original.check() {
                                grant.revoke();
                                return Err(e);
                            }
                            if Arc::strong_count(&grant) == 1 || grant.check().is_err() {
                                break;
                            }
                            std::thread::sleep(Duration::from_millis(100));
                        }
                        grant.revoke();
                        drop(grant);
                    }
                    Ok(())
                })();
                if let Err(e) = result {
                    *done.lock().unwrap() = Some(e.to_string());
                }
                let _ = notify.send(&[1]);
            })?;
        Ok(Self {
            source: Source::Production {
                wake,
                receiver,
                stopped,
                terminal,
                worker: Some(worker),
            },
        })
    }
    pub(crate) fn accept(&self) -> io::Result<Stream> {
        match &self.source {
            Source::Development { listener, uid, .. } => {
                let (socket, _) = listener.accept()?;
                let peer = wire::credentials(&socket)?;
                wire::check(peer.uid == *uid, "development bridge peer UID differs")?;
                Ok(Stream {
                    socket,
                    authority: None,
                })
            }
            Source::Production {
                wake,
                receiver,
                terminal,
                ..
            } => {
                let mut byte = [0; 32];
                while wake.recv(&mut byte).is_ok() {}
                match receiver.try_recv() {
                    Ok(stream) => {
                        stream.check()?;
                        Ok(stream)
                    }
                    Err(TryRecvError::Empty) => {
                        if let Some(error) = terminal.lock().unwrap().as_ref() {
                            Err(io::Error::other(error.clone()))
                        } else {
                            Err(io::ErrorKind::WouldBlock.into())
                        }
                    }
                    Err(TryRecvError::Disconnected) => {
                        Err(io::Error::other("original companion owner worker stopped"))
                    }
                }
            }
        }
    }
}
impl AsRawFd for Listener {
    fn as_raw_fd(&self) -> RawFd {
        match &self.source {
            Source::Development { listener, .. } => listener.as_raw_fd(),
            Source::Production { wake, .. } => wake.as_raw_fd(),
        }
    }
}
impl AsFd for Listener {
    fn as_fd(&self) -> BorrowedFd<'_> {
        match &self.source {
            Source::Development { listener, .. } => listener.as_fd(),
            Source::Production { wake, .. } => wake.as_fd(),
        }
    }
}
impl Drop for Listener {
    fn drop(&mut self) {
        match &mut self.source {
            Source::Development { path, node, .. } => {
                if fs::symlink_metadata(&*path).is_ok_and(|m| wire::Node(m.dev(), m.ino()) == *node)
                {
                    let _ = fs::remove_file(path);
                }
            }
            Source::Production {
                stopped, worker, ..
            } => {
                stopped.store(true, Ordering::Release);
                if let Some(worker) = worker.take() {
                    let _ = worker.join();
                }
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn frontend_development_listener_keeps_replacement_and_rejects_wrong_uid() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("clip");
        let owner = Listener::new(
            path.clone(),
            Role::Clipboard,
            None,
            unsafe { libc::getuid() }.wrapping_add(1),
        )
        .unwrap();
        let _client = UnixStream::connect(&path).unwrap();
        assert!(owner.accept().is_err());
        fs::remove_file(&path).unwrap();
        fs::write(&path, b"replacement").unwrap();
        drop(owner);
        assert_eq!(fs::read(&path).unwrap(), b"replacement");
    }
    #[test]
    fn frontend_stream_wrapper_preserves_existing_bounded_protocol_io() {
        let (a, mut b) = UnixStream::pair().unwrap();
        let mut a = Stream::test_socket(a);
        b.write_all(b"hello").unwrap();
        let mut value = [0; 5];
        a.read_exact(&mut value).unwrap();
        assert_eq!(&value, b"hello");
        a.write_all(b"reply").unwrap();
        b.read_exact(&mut value).unwrap();
        assert_eq!(&value, b"reply");
    }
}
