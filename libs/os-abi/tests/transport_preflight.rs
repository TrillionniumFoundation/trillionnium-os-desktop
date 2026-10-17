//! Host tests for the A05 copyin-to-admission boundary; no user memory access.

use hos2_os_abi::{
    decode_request, response_frame_len, Error, RequestPayload, Status, Transport, MAX_FRAME,
};

const GOLDEN: &str = include_str!("../../../tests/golden/hos2.json");
const REQUESTS: [&str; 5] = [
    "query_abi",
    "read_usage",
    "install_budget",
    "query_delivery_with_new_view",
    "retire_through",
];

fn fixture(name: &str) -> Vec<u8> {
    let mut current = "";
    for line in GOLDEN.lines() {
        let text = line.trim();
        if let Some(value) = text.strip_prefix("\"name\": \"") {
            current = value.trim_end_matches([',', '"']);
        }
        if current == name {
            if let Some(value) = text.strip_prefix("\"hex\": \"") {
                let hex = value.trim_end_matches([',', '"']);
                return hex
                    .as_bytes()
                    .as_chunks::<2>()
                    .0
                    .iter()
                    .map(|pair| {
                        u8::from_str_radix(core::str::from_utf8(pair).unwrap(), 16).unwrap()
                    })
                    .collect();
            }
        }
    }
    panic!("missing independent golden request {name}");
}

fn descriptor(snapshot: &[u8]) -> Transport {
    Transport::new(0x1000, 0x2000, snapshot.len() as u32, 128)
}

#[test]
fn all_five_fixed_requests_pass_the_combined_preflight() {
    for name in REQUESTS {
        let snapshot = fixture(name);
        assert_eq!(
            descriptor(&snapshot).decode_request_snapshot(&snapshot),
            decode_request(&snapshot),
            "{name}"
        );
    }
}

#[test]
fn every_opcode_requires_success_capacity_before_admission() {
    for name in REQUESTS {
        let snapshot = fixture(name);
        let expected = decode_request(&snapshot).unwrap();
        let capacity = response_frame_len(expected.opcode, Status::Ok) as u32;
        let mut transport = descriptor(&snapshot);
        transport.response_capacity = capacity;
        assert_eq!(transport.decode_request_snapshot(&snapshot), Ok(expected));
        // An eventual semantic error would fit in 64 bytes, but preflight
        // cannot admit a request that could not receive its success result.
        for short in [0, 64, capacity - 1] {
            transport.response_capacity = short;
            assert_eq!(
                transport.decode_request_snapshot(&snapshot),
                Err(Error::InsufficientCapacity),
                "{name}, capacity {short}"
            );
        }
    }
}

#[test]
fn descriptor_lengths_must_match_even_otherwise_valid_snapshots() {
    let query = fixture("query_abi");
    let install = fixture("install_budget");
    assert!(decode_request(&query).is_ok());
    assert!(decode_request(&install).is_ok());
    for (snapshot, declared) in [(&query, 65), (&query, 96), (&install, 64)] {
        let mut transport = descriptor(snapshot);
        transport.request_bytes = declared;
        assert_eq!(
            transport.decode_request_snapshot(snapshot),
            Err(Error::InvalidTransport)
        );
    }
    let transport = descriptor(&install);
    assert_eq!(
        transport.decode_request_snapshot(&install[..95]),
        Err(Error::InvalidTransport)
    );
    let mut extra = install;
    extra.push(0);
    assert_eq!(
        transport.decode_request_snapshot(&extra),
        Err(Error::InvalidTransport)
    );
}

#[test]
fn public_descriptor_fields_cannot_bypass_validation() {
    let snapshot = fixture("install_budget");
    let valid = descriptor(&snapshot);
    let mut reserved = valid;
    reserved.reserved = 1;
    let mut request_overflow = valid;
    request_overflow.request_addr = u64::MAX - 95;
    let mut response_overflow = valid;
    response_overflow.response_addr = u64::MAX - 127;
    let mut too_short = valid;
    too_short.request_bytes = 63;
    let mut too_large = valid;
    too_large.request_bytes = MAX_FRAME as u32 + 1;
    for (invalid, error) in [
        (reserved, Error::ReservedNonZero),
        (request_overflow, Error::IntegerOverflow),
        (response_overflow, Error::IntegerOverflow),
        (too_short, Error::InvalidTransport),
        (too_large, Error::InvalidTransport),
    ] {
        assert_eq!(invalid.validate(), Err(error));
        assert_eq!(invalid.decode_request_snapshot(&snapshot), Err(error));
    }

    // These ranges end exactly at MAX. Mapping validity is deliberately not
    // inferred here; only arithmetic is checked by the codec.
    let exact = Transport::new(u64::MAX - 96, u64::MAX - 128, 96, 128);
    assert_eq!(exact.validate(), Ok(()));
    assert_eq!(
        exact.decode_request_snapshot(&snapshot),
        decode_request(&snapshot)
    );
}

#[test]
fn malformed_snapshot_is_rejected_before_short_output_capacity() {
    let mut snapshot = fixture("install_budget");
    let mut transport = descriptor(&snapshot);
    transport.response_capacity = 0;
    snapshot[0] = b'X';
    assert_eq!(
        transport.decode_request_snapshot(&snapshot),
        Err(Error::InvalidMagic)
    );

    snapshot[0] = b'H';
    snapshot[8..10].copy_from_slice(&u16::MAX.to_le_bytes());
    assert_eq!(
        transport.decode_request_snapshot(&snapshot),
        Err(Error::UnknownOpcode)
    );

    snapshot[8..10].copy_from_slice(&3u16.to_le_bytes());
    snapshot[16..20].copy_from_slice(&33u32.to_le_bytes());
    assert_eq!(
        transport.decode_request_snapshot(&snapshot),
        Err(Error::Truncated)
    );
}

#[test]
fn overlapping_ranges_are_accepted_and_request_owns_the_snapshot_values() {
    let mut snapshot = fixture("install_budget");
    let expected = decode_request(&snapshot).unwrap();
    for response_addr in [0x1000, 0x1001, 0x105f] {
        let transport = Transport::new(0x1000, response_addr, 96, 128);
        assert_eq!(transport.decode_request_snapshot(&snapshot), Ok(expected));
    }
    let parsed = descriptor(&snapshot)
        .decode_request_snapshot(&snapshot)
        .unwrap();
    snapshot.fill(0);
    drop(snapshot);
    assert_eq!(parsed, expected);
    let RequestPayload::InstallBudget(budget) = parsed.payload else {
        panic!("expected fixed InstallBudget payload");
    };
    assert_eq!(budget.expected_revision, 10);
    assert_eq!(budget.cap_ns, 40_000_000);
}
