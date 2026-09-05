//! Explicit bridge for an existing immediate runtime. It does not make a
//! blocking backend asynchronous; only genuinely immediate backends belong here.
use super::{CallbackPageRuntime, EngineCompletion};
use crate::{BrowserActorMessage, PageOwnerSnapshot, PageRuntime, RuntimeFailure};
use hepta_browser_codec::{ElementReference, PageAction};

/// Adapt an immediate backend without synthesizing a new request control.
/// Calls remain on the callback owner's thread and use the original deadline,
/// cancellation and request peer custody. An eventual native adapter must
/// implement CallbackPageRuntime directly, not block this bridge for a callback.
/// Retirement drops the backend exactly once on the owner thread. It is not
/// evidence of external-effect rollback or completed native shutdown.
pub struct ImmediateCallbacks<R> {
    runtime: Option<R>,
}

impl<R: PageRuntime> ImmediateCallbacks<R> {
    pub fn new(runtime: R) -> Self {
        Self {
            runtime: Some(runtime),
        }
    }
}

impl<R: PageRuntime> CallbackPageRuntime for ImmediateCallbacks<R> {
    fn start(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        completion: EngineCompletion,
    ) {
        let result = completion.ensure_current_peer().and_then(|()| {
            if matches!(message, BrowserActorMessage::Act { .. }) {
                return Err(RuntimeFailure::Unsupported(
                    "generic Act cannot enter the immediate bridge",
                ));
            }
            self.runtime
                .as_mut()
                .ok_or(RuntimeFailure::BrowserCrashed)?
                .dispatch(owner, message, &completion.control)
        });
        let _ = completion.complete(result);
    }

    fn start_page_act(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        target: ElementReference,
        action: PageAction,
        completion: EngineCompletion,
    ) {
        let result = completion.ensure_current_peer().and_then(|()| {
            self.runtime
                .as_mut()
                .ok_or(RuntimeFailure::BrowserCrashed)?
                .dispatch_page_act(owner, target, action, &completion.control)
        });
        let _ = completion.complete(result);
    }

    fn retire(&mut self) {
        drop(self.runtime.take());
    }
}
