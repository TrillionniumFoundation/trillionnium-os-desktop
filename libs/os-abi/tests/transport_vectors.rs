//! Independent fixed-byte x86_64 HOS2 ioctl transport golden tests.
//!
//! tests/golden/generate_transport32.py uses Python struct.pack, not the
//! Rust encoder. Pointer validity/copy faults remain the kernel's concern.

use hos2_os_abi::{Error, Opcode, Status, Transport, MAX_FRAME, TRANSPORT_LEN};

const GOLDEN: &str = include_str!("../../../tests/golden/transport32.hex");

fn fixture() -> [u8; TRANSPORT_LEN] {
    let ascii = GOLDEN.trim().as_bytes();
    assert_eq!(ascii.len(), TRANSPORT_LEN * 2);
    let mut output = [0u8; TRANSPORT_LEN];
    for (index, pair) in ascii.chunks_exact(2).enumerate() {
        let high = (pair[0] as char).to_digit(16).expect("fixed hex") as u8;
        let low = (pair[1] as char).to_digit(16).expect("fixed hex") as u8;
        output[index] = (high << 4) | low;
    }
    output
}

#[test]
fn decode_independent_transport32_bytes_and_reencode_exactly() {
    let raw = fixture();
    let transport = Transport::decode(&raw).unwrap();
    assert_eq!(transport.request_addr, 0x0102_0304_0506_0708);
    assert_eq!(transport.response_addr, 0x1112_1314_1516_1718);
    assert_eq!(transport.request_bytes, 96);
    assert_eq!(transport.response_capacity, 128);
    assert_eq!(transport.reserved, 0);
    let mut encoded = [0xa5; TRANSPORT_LEN];
    assert_eq!(transport.encode(&mut encoded), Ok(TRANSPORT_LEN));
    assert_eq!(encoded, raw);
}

#[test]
fn every_short_transport_descriptor_is_rejected() {
    let raw = fixture();
    for cut in 0..TRANSPORT_LEN {
        assert_eq!(Transport::decode(&raw[..cut]), Err(Error::Truncated));
    }
    let mut trailing = raw.to_vec();
    trailing.push(0x5a);
    assert_eq!(Transport::decode(&trailing), Err(Error::TrailingBytes));

    let mut output = [0xa5; TRANSPORT_LEN - 1];
    let original = Transport::decode(&raw).unwrap();
    assert_eq!(
        original.encode(&mut output),
        Err(Error::InsufficientCapacity)
    );
    assert_eq!(output, [0xa5; TRANSPORT_LEN - 1]);
}

#[test]
fn transport_rejects_reserved_overflow_and_invalid_request_byte_count() {
    let raw = fixture();
    let mut reserved = raw;
    reserved[24] = 1;
    assert_eq!(Transport::decode(&reserved), Err(Error::ReservedNonZero));

    let mut too_short = raw;
    too_short[16..20].copy_from_slice(&63u32.to_le_bytes());
    assert_eq!(Transport::decode(&too_short), Err(Error::InvalidTransport));

    let mut too_large = raw;
    too_large[16..20].copy_from_slice(&((MAX_FRAME as u32) + 1).to_le_bytes());
    assert_eq!(Transport::decode(&too_large), Err(Error::InvalidTransport));

    let mut wrapping_request = raw;
    wrapping_request[0..8].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(
        Transport::decode(&wrapping_request),
        Err(Error::IntegerOverflow)
    );

    let mut wrapping_response = raw;
    wrapping_response[8..16].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(
        Transport::decode(&wrapping_response),
        Err(Error::IntegerOverflow)
    );

    let mut max_request = raw;
    max_request[16..20].copy_from_slice(&(MAX_FRAME as u32).to_le_bytes());
    assert_eq!(
        Transport::decode(&max_request).unwrap().request_bytes,
        MAX_FRAME as u32
    );
}

#[test]
fn transport_reserves_success_capacity_before_processing_semantic_errors() {
    let full = Transport::decode(&fixture()).unwrap();
    for opcode in [
        Opcode::QueryAbi,
        Opcode::ReadUsage,
        Opcode::InstallBudget,
        Opcode::QueryDelivery,
        Opcode::RetireThrough,
    ] {
        assert_eq!(full.ensure_success_response_capacity(opcode), Ok(()));
    }

    let short = Transport::new(1, 2, 96, 64);
    assert_eq!(
        short.ensure_response_capacity(Opcode::InstallBudget, Status::Conflict),
        Err(Error::InsufficientCapacity)
    );
    assert_eq!(
        short.ensure_response_capacity(Opcode::InstallBudget, Status::Ok),
        Err(Error::InsufficientCapacity)
    );
}
