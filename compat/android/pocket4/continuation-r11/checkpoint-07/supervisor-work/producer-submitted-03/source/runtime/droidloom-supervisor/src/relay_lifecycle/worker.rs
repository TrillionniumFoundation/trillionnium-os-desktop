//! A join failure never consumes or silently releases lifecycle resources.
use super::domain;
use std::io;
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

pub(crate) struct Worker<T: Send + 'static> {
    resources: Arc<Mutex<T>>,
    handle: Option<JoinHandle<()>>,
    poison: Option<String>,
    joined: bool,
}
impl<T: Send + 'static> Worker<T> {
    pub(crate) fn new(resources: T) -> Self {
        Self { resources: Arc::new(Mutex::new(resources)), handle: None, poison: None, joined: false }
    }
    /// Ownership is already held by self before a thread can be created. A
    /// spawn error leaves that exact state recoverable, and permanently fails
    /// normal admission. The closure never takes the resources out of Mutex.
    pub(crate) fn start(&mut self, run: fn(&mut T)) -> io::Result<()> {
        if self.handle.is_some() || self.joined || self.poison.is_some() {
            return Err(domain::error("lifecycle worker is a single attempt"));
        }
        let resources = Arc::clone(&self.resources);
        match thread::Builder::new().name("droidloom-init-relay".into()).spawn(move || {
            // Poison is evidence of an unfinished owner, never a request to
            // manufacture an empty replacement state.
            let mut resources = resources.lock().expect("new lifecycle resource lock");
            run(&mut resources);
        }) {
            Ok(handle) => { self.handle = Some(handle); Ok(()) }
            Err(error) => { self.poison = Some(error.to_string()); Err(error) }
        }
    }
    pub(crate) fn finished(&self) -> bool {
        self.joined || self.handle.as_ref().is_some_and(JoinHandle::is_finished)
    }
    pub(crate) fn join(&mut self, timeout: Duration) -> io::Result<()> {
        if let Some(reason) = &self.poison { return Err(io::Error::other(format!("lifecycle worker is poisoned: {reason}"))); }
        if self.joined { return Ok(()); }
        let Some(handle) = self.handle.as_ref() else { return Err(domain::error("lifecycle worker was not started")); };
        let deadline = Instant::now() + timeout;
        while !handle.is_finished() {
            if Instant::now() >= deadline { return Err(domain::error("lifecycle worker join remains incomplete")); }
            thread::sleep(Duration::from_millis(2));
        }
        let handle = self.handle.take().expect("held finished worker");
        if handle.join().is_err() {
            self.poison = Some("worker panicked with retained resources".into());
            return Err(domain::error("lifecycle worker panic retained its generation"));
        }
        if self.resources.is_poisoned() {
            self.poison = Some("resource lock poisoned".into());
            return Err(domain::error("lifecycle resource lock poisoned"));
        }
        self.joined = true;
        Ok(())
    }
    pub(crate) fn resources(&self) -> io::Result<MutexGuard<'_, T>> {
        if !self.joined || self.poison.is_some() { return Err(domain::error("lifecycle worker has no verified join")); }
        self.resources.lock().map_err(|_| domain::error("lifecycle resources poisoned"))
    }
    /// Failure cleanup may inspect retained resources only after the actual
    /// thread finished. This does not create a join or retirement receipt.
    pub(crate) fn failed_resources(&self) -> io::Result<MutexGuard<'_, T>> {
        if self.handle.as_ref().is_some_and(|handle| !handle.is_finished()) {
            return Err(domain::error("failed worker still owns its resources"));
        }
        Ok(self.resources.lock().unwrap_or_else(std::sync::PoisonError::into_inner))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::{Child, Command};
    struct Owned(Child);
    impl Drop for Owned {
        fn drop(&mut self) { let _ = self.0.kill(); let _ = self.0.wait(); }
    }
    #[test]
    fn panic_and_second_join_never_release_owned_child() {
        let child = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let mut worker = Worker::new(Owned(child));
        worker.start(|_| panic!("injected owned worker panic")).unwrap();
        assert!(worker.join(Duration::from_secs(2)).is_err());
        assert!(worker.join(Duration::from_secs(2)).is_err());
        assert!(worker.resources().is_err());
        let mut retained = worker.failed_resources().unwrap();
        assert!(retained.0.try_wait().unwrap().is_none());
        retained.0.kill().unwrap(); retained.0.wait().unwrap();
    }
    #[test]
    fn incomplete_join_keeps_the_thread_and_owned_record() {
        let pair = Arc::new((Mutex::new(false), std::sync::Condvar::new()));
        let mut worker = Worker::new(Arc::clone(&pair));
        worker.start(|pair| {
            let (lock, condition) = &**pair;
            let mut ready = lock.lock().unwrap();
            while !*ready { ready = condition.wait(ready).unwrap(); }
        }).unwrap();
        assert!(worker.join(Duration::from_millis(1)).is_err());
        assert!(worker.resources().is_err());
        { let (lock, condition) = &*pair; *lock.lock().unwrap() = true; condition.notify_one(); }
        worker.join(Duration::from_secs(2)).unwrap();
        worker.join(Duration::from_secs(2)).unwrap();
        assert!(worker.start(|_| {}).is_err());
        assert!(worker.resources().is_ok());
    }
}
