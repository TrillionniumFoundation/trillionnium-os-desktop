//! Shared normal native-leaf preparation producers.
//!
//! The installed applications owner uses these exact functions in its fixed
//! private preparation child. This library does not expose the update CLI,
//! build command dispatcher, installation commands, or a saved Main authority.
//! All actual peer, Main, source, package and retirement gates remain in the
//! original producer modules.
mod native_leaf_baseline;
mod native_leaf_sources;
mod util;

pub use native_leaf_baseline::{
    BUSINESS_CAPTURE_SECONDS, IHG_PREPARATION_SECONDS,
    capture_business_until, prepare_ihg_until,
};
