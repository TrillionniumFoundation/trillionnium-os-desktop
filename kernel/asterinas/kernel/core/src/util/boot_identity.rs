// SPDX-License-Identifier: MPL-2.0

//! One boot identity shared by procfs and the original HOS2 wire owner.
//! This public UUID is not an authorization token or an anti-rollback device.

use spin::Once;

static BOOT_ID: Once<[u8; 16]> = Once::new();

pub(crate) fn boot_id() -> [u8; 16] {
    *BOOT_ID.call_once(|| {
        let mut id = [0; 16];
        super::random::getrandom(&mut id);
        // UUID version 4 and RFC 4122 variant. These bits also make zero invalid.
        id[6] = (id[6] & 0x0f) | 0x40;
        id[8] = (id[8] & 0x3f) | 0x80;
        id
    })
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::boot_id;

    #[ktest]
    fn boot_identity_is_stable_and_has_uuid_v4_layout() {
        // Audit #257: original protected-clock consumers require a stable boot ID.
        let first = boot_id();
        assert_eq!(first, boot_id());
        assert_ne!(first, [0; 16]);
        assert_eq!(first[6] >> 4, 4);
        assert_eq!(first[8] >> 6, 2);
    }
}
