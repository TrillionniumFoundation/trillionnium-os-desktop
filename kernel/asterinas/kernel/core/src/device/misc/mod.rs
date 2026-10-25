// SPDX-License-Identifier: MPL-2.0

//! Misc devices.
//!
//! Character device with major number 10.

use device_id::MajorId;
use spin::Once;

use super::registry::char::{MajorIdOwner, acquire_major};

mod hepta_control;
mod hwrng;
pub(crate) use hepta_control::boot_id as hepta_boot_id;
#[cfg(feature = "g1d-trusted-control")]
pub(crate) use hepta_control::image_space_id as hepta_image_space_id;
#[cfg(all(target_arch = "x86_64", feature = "cvm_guest"))]
pub(crate) mod tdxguest;

static MISC_MAJOR: Once<MajorIdOwner> = Once::new();

pub(super) fn init_in_first_kthread() {
    MISC_MAJOR.call_once(|| acquire_major(MajorId::new(10)).unwrap());

    hwrng::init_in_first_kthread();
    hepta_control::init_in_first_kthread();

    #[cfg(target_arch = "x86_64")]
    ostd::if_tdx_enabled!({
        tdxguest::init().unwrap();
    });
}
