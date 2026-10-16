//! Independent fixed-byte consumption test.
//!
//! The vectors are generated outside this crate (the repository JSON is
//! Python/struct generated).  This tiny scanner is deliberately dependency
//! free; it extracts only `kind` and `hex`, then feeds the bytes to the Rust
//! decoder.  It therefore does not turn an encoder round-trip into a golden
//! test.

use hos2_os_abi::{
    decode_request, decode_response, encode_request, encode_response, DeliveryRequest,
    DeliveryState, InstallBudgetRequest, InstallBudgetResponse, Opcode, QueryAbiResponse,
    QueryDeliveryResponse, ReadUsageResponse, Request, RequestPayload, Response, ResponsePayload,
    RetireThroughResponse, Status, CPU_PERIOD_NS,
};

const GOLDEN: &str = include_str!("../../../tests/golden/hos2.json");

fn quoted_value<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let marker = alloc_marker(key);
    let start = line.find(marker)? + marker.len();
    let rest = &line[start..];
    let end = rest.find('"')?;
    Some(&rest[..end])
}

// Keeping marker construction in a helper avoids an allocation in the test's
// parsing loop; the returned string is only used as a search literal.
fn alloc_marker(key: &str) -> &str {
    match key {
        "name" => "\"name\": \"",
        "kind" => "\"kind\": \"",
        "hex" => "\"hex\": \"",
        _ => "",
    }
}

fn vector_hex(name: &str) -> Vec<u8> {
    let mut current_name = "";
    for line in GOLDEN.lines() {
        if let Some(value) = quoted_value(line, "name") {
            current_name = value;
        }
        if current_name == name {
            if let Some(value) = quoted_value(line, "hex") {
                return decode_hex(value);
            }
        }
    }
    panic!("missing golden vector: {name}");
}

fn decode_hex(value: &str) -> Vec<u8> {
    assert_eq!(value.len() % 2, 0, "odd-length golden hex");
    let mut out = Vec::with_capacity(value.len() / 2);
    let bytes = value.as_bytes();
    for pair in bytes.as_chunks::<2>().0 {
        let hi = (pair[0] as char).to_digit(16).expect("golden hex") as u8;
        let lo = (pair[1] as char).to_digit(16).expect("golden hex") as u8;
        out.push((hi << 4) | lo);
    }
    out
}

#[test]
fn fixed_golden_vectors_are_consumed_by_rust_codec() {
    let mut kind = "";
    let mut count = 0usize;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted_value(line, "kind") {
            kind = value;
        }
        if let Some(value) = quoted_value(line, "hex") {
            let bytes = decode_hex(value);
            match kind {
                "request" => assert!(decode_request(&bytes).is_ok(), "request vector failed"),
                "response" => assert!(decode_response(&bytes).is_ok(), "response vector failed"),
                other => panic!("missing vector kind: {other}"),
            }
            count += 1;
        }
    }
    assert_eq!(
        count, 12,
        "golden vector count changed without updating this test"
    );
}

#[test]
fn encoders_match_independent_golden_bytes_for_all_operations() {
    let request_id = [0x11; 16];
    let sequence_id = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    let delivery = DeliveryRequest {
        history_boot: [0x33; 16],
        history_space: [0x22; 16],
        sequence: 1,
    };
    let requests = [
        (
            "query_abi",
            Request {
                opcode: Opcode::QueryAbi,
                request_id,
                target_slot: 0,
                target_generation: 0,
                payload: RequestPayload::QueryAbi,
            },
        ),
        (
            "read_usage",
            Request {
                opcode: Opcode::ReadUsage,
                request_id,
                target_slot: 7,
                target_generation: 9,
                payload: RequestPayload::ReadUsage,
            },
        ),
        (
            "install_budget",
            Request {
                opcode: Opcode::InstallBudget,
                request_id: sequence_id,
                target_slot: 7,
                target_generation: 9,
                payload: RequestPayload::InstallBudget(InstallBudgetRequest {
                    expected_revision: 10,
                    period_ns: CPU_PERIOD_NS,
                    cap_ns: 40_000_000,
                    reserved: 0,
                }),
            },
        ),
        (
            "query_delivery_with_new_view",
            Request {
                opcode: Opcode::QueryDelivery,
                request_id,
                target_slot: 80,
                target_generation: 3,
                payload: RequestPayload::QueryDelivery(delivery),
            },
        ),
        (
            "retire_through",
            Request {
                opcode: Opcode::RetireThrough,
                request_id,
                target_slot: 80,
                target_generation: 3,
                payload: RequestPayload::RetireThrough(delivery),
            },
        ),
    ];
    for (name, request) in requests {
        let mut output = vec![0; 128];
        let length = encode_request(&request, &mut output).unwrap();
        assert_eq!(&output[..length], vector_hex(name).as_slice(), "{name}");
    }

    let boot_id = [0x33; 16];
    let responses = [
        (
            "query_abi_ok",
            Response {
                opcode: Opcode::QueryAbi,
                status: Status::Ok,
                request_id,
                boot_id,
                revision: 0,
                payload: ResponsePayload::QueryAbi(QueryAbiResponse {
                    space_id: [0x22; 16],
                    page_size: 4096,
                    max_request_payload: 65536,
                    max_response_payload: 65536,
                    supported_ops: 62,
                    features: 0,
                }),
            },
        ),
        (
            "read_usage_lowered_cap",
            Response {
                opcode: Opcode::ReadUsage,
                status: Status::Ok,
                request_id,
                boot_id,
                revision: 11,
                payload: ResponsePayload::ReadUsage(ReadUsageResponse {
                    sample_boottime_ns: 150_000_000,
                    cumulative_cpu_ns: 90_000_000,
                    window_start_ns: 100_000_000,
                    window_consumed_ns: 35_000_000,
                    active_cap_ns: 20_000_000,
                    active_period_ns: CPU_PERIOD_NS,
                    event_sequence: 77,
                    dropped_events: 2,
                }),
            },
        ),
        (
            "install_budget_ok",
            Response {
                opcode: Opcode::InstallBudget,
                status: Status::Ok,
                request_id: sequence_id,
                boot_id,
                revision: 11,
                payload: ResponsePayload::InstallBudget(InstallBudgetResponse {
                    previous_revision: 10,
                    effective_boottime_ns: 140_000_000,
                    consumed_at_apply_ns: 33_000_000,
                }),
            },
        ),
        (
            "query_delivery_terminal",
            Response {
                opcode: Opcode::QueryDelivery,
                status: Status::Ok,
                request_id,
                boot_id,
                revision: 0,
                payload: ResponsePayload::QueryDelivery(QueryDeliveryResponse {
                    state: DeliveryState::Terminal,
                    saved_status: Status::Ok,
                    sequence: 1,
                    stable_object_id: [0x44; 16],
                    saved_revision: 11,
                    previous_revision: 10,
                    effective_ns: 140_000_000,
                    consumed_ns: 33_000_000,
                }),
            },
        ),
        (
            "query_delivery_retired",
            Response {
                opcode: Opcode::QueryDelivery,
                status: Status::Ok,
                request_id,
                boot_id,
                revision: 0,
                payload: ResponsePayload::QueryDelivery(QueryDeliveryResponse {
                    state: DeliveryState::Retired,
                    saved_status: Status::Ok,
                    sequence: 1,
                    stable_object_id: [0; 16],
                    saved_revision: 0,
                    previous_revision: 0,
                    effective_ns: 0,
                    consumed_ns: 0,
                }),
            },
        ),
        (
            "retire_through_ok",
            Response {
                opcode: Opcode::RetireThrough,
                status: Status::Ok,
                request_id,
                boot_id,
                revision: 0,
                payload: ResponsePayload::RetireThrough(RetireThroughResponse {
                    retired_through: 1,
                    next_sequence: 2,
                }),
            },
        ),
        (
            "install_cas_rejection",
            Response {
                opcode: Opcode::InstallBudget,
                status: Status::Conflict,
                request_id: sequence_id,
                boot_id,
                revision: 0,
                payload: ResponsePayload::Empty,
            },
        ),
    ];
    for (name, response) in responses {
        let mut output = vec![0; 128];
        let length = encode_response(&response, &mut output).unwrap();
        assert_eq!(&output[..length], vector_hex(name).as_slice(), "{name}");
    }
}

#[test]
fn each_golden_cut_is_rejected_not_just_selected_truncations() {
    let mut kind = "";
    let mut count = 0;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted_value(line, "kind") {
            kind = value;
        }
        if let Some(value) = quoted_value(line, "hex") {
            let frame = decode_hex(value);
            for cut in 0..frame.len() {
                let accepted = match kind {
                    "request" => decode_request(&frame[..cut]).is_ok(),
                    "response" => decode_response(&frame[..cut]).is_ok(),
                    other => panic!("unknown golden kind: {other}"),
                };
                assert!(
                    !accepted,
                    "{kind} accepted truncated length {cut} of {}",
                    frame.len()
                );
            }
            let mut trailing = frame;
            trailing.push(0xa5);
            let accepted = match kind {
                "request" => decode_request(&trailing).is_ok(),
                "response" => decode_response(&trailing).is_ok(),
                other => panic!("unknown golden kind: {other}"),
            };
            assert!(!accepted, "{kind} accepted trailing bytes");
            count += 1;
        }
    }
    assert_eq!(count, 12);
}

#[test]
fn every_golden_encoder_checks_capacity_before_writing() {
    let mut kind = "";
    let mut count = 0;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted_value(line, "kind") {
            kind = value;
        }
        if let Some(value) = quoted_value(line, "hex") {
            let frame = decode_hex(value);
            let mut output = vec![0xa5; frame.len() - 1];
            let encoded = match kind {
                "request" => encode_request(&decode_request(&frame).unwrap(), &mut output),
                "response" => encode_response(&decode_response(&frame).unwrap(), &mut output),
                other => panic!("unknown golden kind: {other}"),
            };
            assert_eq!(encoded, Err(hos2_os_abi::Error::InsufficientCapacity));
            assert!(
                output.iter().all(|v| *v == 0xa5),
                "short encode wrote partial output"
            );
            count += 1;
        }
    }
    assert_eq!(count, 12);
}

#[test]
fn every_golden_header_refuses_version_reserved_or_zero_id_mutation() {
    let mut kind = "";
    let mut count = 0;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted_value(line, "kind") {
            kind = value;
        }
        if let Some(value) = quoted_value(line, "hex") {
            let frame = decode_hex(value);
            for (offset, replacement) in [(4usize, 3u8), (6, 1), (20, 1)] {
                let mut invalid = frame.clone();
                invalid[offset] = replacement;
                let accepted = match kind {
                    "request" => decode_request(&invalid).is_ok(),
                    "response" => decode_response(&invalid).is_ok(),
                    other => panic!("unknown golden kind: {other}"),
                };
                assert!(
                    !accepted,
                    "{kind} accepted corrupted header offset {offset}"
                );
            }
            let mut invalid_id = frame;
            invalid_id[24..40].fill(0);
            let accepted = match kind {
                "request" => decode_request(&invalid_id).is_ok(),
                "response" => decode_response(&invalid_id).is_ok(),
                other => panic!("unknown golden kind: {other}"),
            };
            assert!(!accepted, "{kind} accepted zero request ID");
            count += 1;
        }
    }
    assert_eq!(count, 12);
}
