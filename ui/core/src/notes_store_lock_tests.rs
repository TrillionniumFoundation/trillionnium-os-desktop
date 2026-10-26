use super::*;
use std::os::fd::OwnedFd;
use std::path::PathBuf;
use std::time::SystemTime;

struct Directory(PathBuf);

impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

struct ForkedChild(libc::pid_t);

impl Drop for ForkedChild {
    fn drop(&mut self) {
        // Only this test's still-unreaped child is addressed. Killing and
        // reaping also releases its inherited descriptors after a panic.
        unsafe { libc::kill(self.0, libc::SIGKILL) };
        loop {
            if unsafe { libc::waitpid(self.0, std::ptr::null_mut(), 0) } >= 0
                || io::Error::last_os_error().kind() != io::ErrorKind::Interrupted
            {
                break;
            }
        }
    }
}

#[test]
fn forked_descriptor_does_not_extend_store_lock_or_unlock_its_parent() {
    let suffix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = Directory(std::env::temp_dir().join(format!(
        "trill-notes-fork-lock-{}-{suffix}",
        std::process::id()
    )));
    let target = NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 1,
        incarnation: "b".repeat(32),
    };
    let store = NotesStore::create(&root.0, target.clone()).unwrap();
    let mut descriptors = [-1; 2];
    assert_eq!(
        unsafe { libc::pipe2(descriptors.as_mut_ptr(), libc::O_CLOEXEC) },
        0
    );
    let reader = unsafe { OwnedFd::from_raw_fd(descriptors[0]) };
    let writer = unsafe { OwnedFd::from_raw_fd(descriptors[1]) };
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0, "fork: {}", io::Error::last_os_error());
    if pid == 0 {
        // The multithreaded Rust test runner has been forked. This branch
        // performs only async-signal-safe syscalls and the guard's PID check;
        // it does not allocate, unwind, take a Rust lock or run destructors.
        store._lock.release_if_owner();
        unsafe {
            libc::close(reader.as_raw_fd());
            let ready = b'R';
            if libc::write(writer.as_raw_fd(), (&ready as *const u8).cast(), 1) != 1 {
                libc::_exit(1);
            }
            libc::close(writer.as_raw_fd());
            loop {
                libc::pause();
            }
        }
    }
    let child = ForkedChild(pid);
    drop(writer);
    let mut poll = libc::pollfd {
        fd: reader.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    assert_eq!(unsafe { libc::poll(&mut poll, 1, 10_000) }, 1);
    let mut ready = 0_u8;
    assert_eq!(
        unsafe { libc::read(reader.as_raw_fd(), (&mut ready as *mut u8).cast(), 1) },
        1
    );
    assert_eq!(ready, b'R');
    assert!(matches!(
        NotesStore::recover(&root.0, &target),
        Err(error) if error.kind() == io::ErrorKind::WouldBlock
    ));

    // No sleep, retry, process exit or exec occurs between release and
    // recovery. The live child still holds the inherited open description.
    drop(store);
    let recovered = NotesStore::recover(&root.0, &target).unwrap();
    assert_eq!(recovered.revision(), 0);
    assert!(matches!(
        NotesStore::recover(&root.0, &target),
        Err(error) if error.kind() == io::ErrorKind::WouldBlock
    ));
    drop(recovered);
    drop(child);
}
