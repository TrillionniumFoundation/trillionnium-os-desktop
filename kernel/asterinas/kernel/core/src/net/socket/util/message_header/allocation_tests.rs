// SPDX-License-Identifier: MPL-2.0

use ostd::{mm::HasPaddr, prelude::ktest};

use super::*;
use crate::vm::user_memory::{UserMemoryAccount, alloc_user_frame};

#[ktest]
fn failed_ancillary_reservation_keeps_original_frame_and_last_reference_refund() {
    let account = UserMemoryAccount::new(1);
    let frame = alloc_user_frame(&Some(account.clone()), false).unwrap();
    let alias = frame.clone();
    let mut items = vec![frame];
    let ptr = items.as_ptr();
    let capacity = items.capacity();
    let paddr = items[0].paddr();
    // A valid 16-TiB layout exceeds the original allocator's 8-TiB maximum
    // order and is rejected without consuming RAM. This tests the real heap
    // allocator error, not capacity overflow or global memory exhaustion.
    let additional = (1usize << 44) / size_of_val(&items[0]);
    assert_eq!(
        reserve_control_items(&mut items, additional)
            .unwrap_err()
            .error(),
        Errno::ENOMEM
    );
    assert_eq!(items.as_ptr(), ptr);
    assert_eq!(items.capacity(), capacity);
    assert_eq!(items.len(), 1);
    assert_eq!(items[0].paddr(), paddr);
    assert_eq!(account.current_pages(), 1);
    reserve_control_items(&mut items, 1).unwrap();
    items.push(alias.clone());
    assert_eq!(account.current_pages(), 1);
    drop(items);
    assert_eq!(account.current_pages(), 1);
    drop(alias);
    assert_eq!(account.current_pages(), 0);
}

#[ktest]
fn control_input_growth_retains_original_message_limit_and_empty_behavior() {
    let mut bytes = Vec::new();
    for _ in 0..33 {
        // SCM_CREDENTIALS parsing copies the supplied value but does not
        // authenticate it until the original send path merges controls.
        let header = CControlHeader::new(CSocketOptionLevel::SOL_SOCKET, 2, 12);
        bytes.extend_from_slice(header.as_bytes());
        bytes.extend_from_slice(&[0u8; 12]);
        bytes.resize(bytes.len() + header.padding_len(), 0);
    }
    let one = bytes.len() / 33;
    let mut reader = VmReader::from(&bytes[..32 * one]).to_fallible();
    assert_eq!(
        ControlMessage::read_all_from(&mut reader).unwrap().len(),
        32
    );
    assert_eq!(reader.remain(), 0);
    let mut reader = VmReader::from(&bytes[..]).to_fallible();
    assert_eq!(
        ControlMessage::read_all_from(&mut reader)
            .unwrap_err()
            .error(),
        Errno::E2BIG
    );
    assert_eq!(reader.remain(), one);
    assert!(
        ControlMessage::read_all_from(&mut VmReader::from(&[][..]).to_fallible())
            .unwrap()
            .is_empty()
    );
}
