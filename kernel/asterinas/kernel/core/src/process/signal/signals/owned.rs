// SPDX-License-Identifier: MPL-2.0

//! The original signal owner, including bounded inline fault/fatal signals.

use core::ops::Deref;

use super::{Signal, fault::FaultSignal, kernel::KernelSignal, user::UserSignal};
use crate::{prelude::*, process::signal::constants::SIGKILL};

/// Keeps the same owner through pending queues, ptrace stops and signal reads.
///
/// Only the closed standard-signal variants below can be inline. Dynamic
/// callers retain their original box, including every real-time signal.
#[derive(Debug)]
pub(crate) struct OwnedSignal(Storage);

#[derive(Debug)]
enum Storage {
    Fault(FaultSignal),
    KernelKill(KernelSignal),
    UserKill(UserSignal),
    Dynamic(Box<dyn Signal>),
}

impl OwnedSignal {
    /// Accepts a concrete signal before any box is allocated. Copying these
    /// closed types preserves all their signal information; all other signal
    /// implementations, including raw/custom siginfo, retain the dynamic path.
    pub(crate) fn new<S: Signal>(signal: S) -> Self {
        let concrete = &signal as &dyn Any;
        if signal.num().is_std()
            && let Some(fault) = concrete.downcast_ref::<FaultSignal>()
        {
            return Self(Storage::Fault(*fault));
        }
        if signal.num() == SIGKILL {
            if let Some(kernel) = concrete.downcast_ref::<KernelSignal>() {
                return Self(Storage::KernelKill(*kernel));
            }
            if let Some(user) = concrete.downcast_ref::<UserSignal>() {
                return Self(Storage::UserKill(*user));
            }
        }
        Self::from_box(Box::new(signal))
    }

    pub(crate) fn from_box(signal: Box<dyn Signal>) -> Self {
        Self(Storage::Dynamic(signal))
    }

    /// The real-time queue retains its original boxed element representation.
    /// `new` admits only standard signals to inline storage; `from_box` always
    /// retains a box. No caller can construct the private storage variants.
    pub(in crate::process::signal) fn into_realtime(self) -> Box<dyn Signal> {
        match self.0 {
            Storage::Dynamic(signal) => signal,
            _ => unreachable!("inline signals are always standard signals"),
        }
    }

    #[cfg(ktest)]
    pub(crate) fn is_inline(&self) -> bool {
        !matches!(self.0, Storage::Dynamic(_))
    }
}

impl AsRef<dyn Signal> for OwnedSignal {
    fn as_ref(&self) -> &(dyn Signal + 'static) {
        match &self.0 {
            Storage::Fault(signal) => signal,
            Storage::KernelKill(signal) => signal,
            Storage::UserKill(signal) => signal,
            Storage::Dynamic(signal) => signal.as_ref(),
        }
    }
}

impl Deref for OwnedSignal {
    type Target = dyn Signal;

    fn deref(&self) -> &Self::Target {
        self.as_ref()
    }
}
