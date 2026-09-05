//! Main-thread fixture owner and exactly one scoped connection worker.
//!
//! This is the development daemon's actual runner, not a Servo event loop.
//! Immediate fixture operations use the callback runner bridge; no Servo runs.
//! No runtime, BrowserActor or Rc-owned receipt observer is moved between threads.

use crate::{AnyError, invalid};
use hepta_browser_actor::PageRuntime;
use hepta_browser_actor::engine_dispatch::EngineThreadRuntime;
use hepta_browser_actor::engine_dispatch::event_loop::ImmediateCallbacks;

#[path = "callback_runner.rs"]
mod callbacks;
pub(crate) use callbacks::run_callback_on_owner;
use std::io;
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;

pub(crate) const SERVICE_POLL: Duration = Duration::from_millis(5);

/// A private, one-way service retirement signal. It cannot revive an endpoint.
#[derive(Clone, Default)]
pub(crate) struct ServiceStop(Arc<AtomicBool>);
impl ServiceStop {
    pub(crate) fn ensure_active(&self) -> Result<(), AnyError> {
        if self.0.load(Ordering::SeqCst) {
            Err(invalid("D3 engine retired; service must stop").into())
        } else {
            Ok(())
        }
    }
    fn retire(&self) {
        self.0.store(true, Ordering::SeqCst);
    }
}

/// Keep R (which may be !Send) on this thread and build the actor inside work.
/// This returns only after the one connection worker has been joined. All I/O
/// in work must be bounded/cooperative; this cannot preempt a blocked backend.
pub(crate) fn run_on_owner<R, F, T>(runtime: R, work: F) -> Result<T, AnyError>
where
    R: PageRuntime,
    F: FnOnce(EngineThreadRuntime, &ServiceStop) -> Result<T, AnyError> + Send,
    T: Send,
{
    run_callback_on_owner(ImmediateCallbacks::new(runtime), || Ok(None), work)
}

/// Caller sets only the inherited listener nonblocking before spawning work.
/// Accepted streams are explicitly blocking so AgentPort's existing absolute
/// connection/request deadlines, not EAGAIN spinning, continue to bound I/O.
pub(crate) fn accept_next(
    listener: &UnixListener,
    stop: &ServiceStop,
) -> Result<UnixStream, AnyError> {
    loop {
        stop.ensure_active()?;
        match listener.accept() {
            Ok((stream, _)) => {
                stop.ensure_active()?;
                stream.set_nonblocking(false)?;
                return Ok(stream);
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::WouldBlock | io::ErrorKind::Interrupted
                ) =>
            {
                stop.ensure_active()?;
                thread::park_timeout(SERVICE_POLL);
            }
            Err(error) => return Err(error.into()),
        }
    }
}

#[cfg(test)]
#[path = "engine_tests.rs"]
mod tests;
