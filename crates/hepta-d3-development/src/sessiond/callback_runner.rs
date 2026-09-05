//! Callback-capable service runner. This drives owner events, not Servo/winit.
//! Notification state is private: unrelated thread::park calls cannot consume it.
use super::ServiceStop;
use crate::{AnyError, invalid};
use hepta_browser_actor::engine_dispatch::EngineThreadRuntime;
use hepta_browser_actor::engine_dispatch::event_loop::{
    CallbackPageRuntime, CallbackPumpResult, callback_engine_pair,
};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::Instant;

#[derive(Default)]
struct WakeSignal {
    pending: Mutex<bool>,
    changed: Condvar,
}
impl WakeSignal {
    fn notify(&self) {
        // There is no user/backend code while this lock is held. A poison is
        // retained for the owner to reject, but must still wake a sleeping owner.
        let mut pending = self
            .pending
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        *pending = true;
        self.changed.notify_one();
    }

    fn begin_cycle(&self) -> Result<(), AnyError> {
        let mut pending = self
            .pending
            .lock()
            .map_err(|_| invalid("D3 callback wake state poisoned"))?;
        *pending = false;
        Ok(())
    }

    fn wait_until(&self, deadline: Option<Instant>) -> Result<(), AnyError> {
        let mut pending = self
            .pending
            .lock()
            .map_err(|_| invalid("D3 callback wake state poisoned"))?;
        while !*pending {
            pending = match deadline {
                None => self
                    .changed
                    .wait(pending)
                    .map_err(|_| invalid("D3 callback wake state poisoned"))?,
                Some(at) => {
                    let remaining = at.saturating_duration_since(Instant::now());
                    if remaining.is_zero() {
                        return Ok(());
                    }
                    let (state, _) = self
                        .changed
                        .wait_timeout(pending, remaining)
                        .map_err(|_| invalid("D3 callback wake state poisoned"))?;
                    state
                }
            };
        }
        Ok(())
    }
}

struct CompletionWake {
    finished: Arc<AtomicBool>,
    wake: Arc<WakeSignal>,
}
impl Drop for CompletionWake {
    fn drop(&mut self) {
        // is_finished() can still be false while a closure's final guard drops.
        // Publish our predicate BEFORE the wake; join handles the final unwind.
        self.finished.store(true, Ordering::Release);
        self.wake.notify();
    }
}

/// At most one scoped worker; the runtime and event driver stay on the caller.
/// `advance` services already-ready owner events and returns its next absolute
/// timer, if any. It must return promptly and never wait for the worker. The
/// current fixture uses no native timer. Notifications may coalesce or repeat.
/// Pending callbacks also honor the original request's cancellation deadline.
/// Error/panic retires the runtime before join. This cannot preempt arbitrary
/// backend code, I/O or worker destruction and is not a real-time guarantee.
pub(crate) fn run_callback_on_owner<R, A, F, T>(
    runtime: R,
    mut advance: A,
    work: F,
) -> Result<T, AnyError>
where
    R: CallbackPageRuntime,
    A: FnMut() -> Result<Option<Instant>, AnyError>,
    F: FnOnce(EngineThreadRuntime, &ServiceStop) -> Result<T, AnyError> + Send,
    T: Send,
{
    let wake = Arc::new(WakeSignal::default());
    let engine_wake = wake.clone();
    let (client, mut owner) = callback_engine_pair(runtime, Arc::new(move || engine_wake.notify()));
    let stop = ServiceStop::default();
    let finished = Arc::new(AtomicBool::new(false));
    thread::scope(|scope| {
        let worker_stop = stop.clone();
        let completion = CompletionWake {
            finished: finished.clone(),
            wake: wake.clone(),
        };
        let worker = thread::Builder::new()
            .name("hepta-d3-connections".to_owned())
            .spawn_scoped(scope, move || {
                let _completion = completion;
                work(client, &worker_stop)
            })?;
        let mut retired = false;
        let mut failure = None;
        while !finished.load(Ordering::Acquire) {
            let cycle = (|| -> Result<(), AnyError> {
                // Clear only notifications that precede the drain. Any later
                // enqueue/completion/worker exit remains latched until next cycle.
                wake.begin_cycle()?;
                if finished.load(Ordering::Acquire) {
                    return Ok(());
                }
                let mut deadline = None;
                if !retired {
                    let native_deadline = match catch_unwind(AssertUnwindSafe(&mut advance)) {
                        Ok(Ok(at)) => at,
                        Ok(Err(_)) => {
                            return Err(
                                invalid("D3 owner event driver failed; service stopped").into()
                            );
                        }
                        Err(_) => {
                            return Err(
                                invalid("D3 owner event driver panicked; service stopped").into()
                            );
                        }
                    };
                    match owner.pump_one() {
                        CallbackPumpResult::Retired => retired = true,
                        CallbackPumpResult::Replied => return Ok(()),
                        CallbackPumpResult::Idle | CallbackPumpResult::Pending => {}
                    }
                    deadline = earliest(owner.next_wake_deadline(), native_deadline);
                }
                if retired {
                    stop.retire();
                    worker.thread().unpark();
                    deadline = None;
                }
                if !finished.load(Ordering::Acquire) {
                    wake.wait_until(deadline)?;
                }
                Ok(())
            })();
            if let Err(error) = cycle {
                failure = Some(error);
                stop.retire();
                owner.retire();
                worker.thread().unpark();
                break;
            }
        }
        // Explicitly retire even after normal return. No native registration
        // or retained completion is allowed to survive service teardown.
        stop.retire();
        owner.retire();
        worker.thread().unpark();
        let joined = worker
            .join()
            .map_err(|_| invalid("D3 connection worker panicked; service stopped"))?;
        if let Some(error) = failure {
            return Err(error);
        }
        joined
    })
}

fn earliest(a: Option<Instant>, b: Option<Instant>) -> Option<Instant> {
    match (a, b) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (a, b) => a.or(b),
    }
}

#[cfg(test)]
#[path = "callback_runner_tests.rs"]
mod tests;
