//! Consume independent, committed boundary bytes and assert typed semantics.
//!
//! These are host codec checks. They do not demonstrate kernel execution,
//! capability authorization, or persistence of delivery history.

use hos2_os_abi::{
    decode_request, decode_response, encode_request, encode_response, install_budget_sequence,
    DeliveryState, Error, Opcode, QueryDeliveryResponse, RequestPayload, Response, ResponsePayload,
    Status, CPU_PERIOD_NS,
};

const GOLDEN: &str = include_str!("../../../tests/golden/hos2_edges.json");
const OPAQUE_ID: [u8; 16] = [
    0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10,
];
const NONTERMINAL: [(&str, DeliveryState); 4] = [
    ("delivery_reserved", DeliveryState::Reserved),
    ("delivery_retired", DeliveryState::Retired),
    ("delivery_not_seen", DeliveryState::NotSeen),
    ("delivery_history_lost", DeliveryState::HistoryLost),
];
const TERMINAL_ERROR_STATUSES: [Status; 9] = [
    Status::InvalidInput,
    Status::PermissionDenied,
    Status::StaleHandle,
    Status::Revoked,
    Status::Conflict,
    Status::ResourceExhausted,
    Status::Unsupported,
    Status::Indeterminate,
    Status::Busy,
];

fn quoted<'a>(line: &'a str, marker: &str) -> Option<&'a str> {
    line.split_once(marker)?.1.split_once('"').map(|v| v.0)
}

fn hex(input: &str) -> Vec<u8> {
    assert_eq!(input.len() % 2, 0);
    input
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| {
            let hi = (pair[0] as char).to_digit(16).expect("golden hex");
            let lo = (pair[1] as char).to_digit(16).expect("golden hex");
            ((hi << 4) | lo) as u8
        })
        .collect()
}

fn fixed(name: &str) -> Vec<u8> {
    let mut current = "";
    for line in GOLDEN.lines() {
        if let Some(value) = quoted(line, "\"name\": \"") {
            current = value;
        }
        if current == name {
            if let Some(value) = quoted(line, "\"hex\": \"") {
                return hex(value);
            }
        }
    }
    panic!("missing golden semantic vector: {name}")
}

fn delivery(name: &str) -> QueryDeliveryResponse {
    let response = decode_response(&fixed(name)).expect(name);
    assert_eq!(response.opcode, Opcode::QueryDelivery);
    assert_eq!(response.status, Status::Ok);
    assert_eq!(response.request_id, OPAQUE_ID);
    assert_eq!(response.boot_id, [0x33; 16]);
    assert_eq!(response.revision, 0);
    match response.payload {
        ResponsePayload::QueryDelivery(value) => value,
        other => panic!("wrong typed payload for {name}: {other:?}"),
    }
}

fn assert_zero_metadata(value: &QueryDeliveryResponse) {
    assert_eq!(value.stable_object_id, [0; 16]);
    assert_eq!(value.saved_revision, 0);
    assert_eq!(value.previous_revision, 0);
    assert_eq!(value.effective_ns, 0);
    assert_eq!(value.consumed_ns, 0);
}

#[test]
fn all_independent_semantic_edge_frames_decode() {
    let mut kind = "";
    let mut name = "";
    let mut count = 0;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted(line, "\"name\": \"") {
            name = value;
        }
        if let Some(value) = quoted(line, "\"kind\": \"") {
            kind = value;
        }
        if let Some(value) = quoted(line, "\"hex\": \"") {
            let bytes = hex(value);
            match kind {
                "request" => assert!(decode_request(&bytes).is_ok(), "{name}"),
                "response" => assert!(decode_response(&bytes).is_ok(), "{name}"),
                other => panic!("invalid fixture kind: {other}"),
            }
            count += 1;
        }
    }
    assert_eq!(count, 24, "update typed assertions when adding fixtures");
}

#[test]
fn every_semantic_edge_encoder_matches_fixed_bytes_and_preserves_unused_capacity() {
    let mut kind = "";
    let mut name = "";
    let mut count = 0;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted(line, "\"name\": \"") {
            name = value;
        }
        if let Some(value) = quoted(line, "\"kind\": \"") {
            kind = value;
        }
        if let Some(value) = quoted(line, "\"hex\": \"") {
            let bytes = hex(value);
            for unused_capacity in [0, 17] {
                let mut output = vec![0xa5; bytes.len() + unused_capacity];
                let encoded = match kind {
                    "request" => encode_request(&decode_request(&bytes).unwrap(), &mut output),
                    "response" => encode_response(&decode_response(&bytes).unwrap(), &mut output),
                    other => panic!("invalid fixture kind: {other}"),
                };
                assert_eq!(encoded, Ok(bytes.len()), "{name}");
                assert_eq!(&output[..bytes.len()], bytes.as_slice(), "{name}");
                assert!(
                    output[bytes.len()..].iter().all(|byte| *byte == 0xa5),
                    "{name}: encoder wrote beyond the frame"
                );
            }
            count += 1;
        }
    }
    assert_eq!(count, 24);
}

#[test]
fn every_semantic_edge_encoder_rejects_each_short_capacity_without_writing() {
    let mut kind = "";
    let mut name = "";
    let mut count = 0;
    let mut capacities = 0;
    for line in GOLDEN.lines() {
        if let Some(value) = quoted(line, "\"name\": \"") {
            name = value;
        }
        if let Some(value) = quoted(line, "\"kind\": \"") {
            kind = value;
        }
        if let Some(value) = quoted(line, "\"hex\": \"") {
            let bytes = hex(value);
            for capacity in 0..bytes.len() {
                let mut output = vec![0xa5; capacity];
                let encoded = match kind {
                    "request" => encode_request(&decode_request(&bytes).unwrap(), &mut output),
                    "response" => encode_response(&decode_response(&bytes).unwrap(), &mut output),
                    other => panic!("invalid fixture kind: {other}"),
                };
                assert_eq!(
                    encoded,
                    Err(Error::InsufficientCapacity),
                    "{name}: capacity {capacity}"
                );
                assert!(
                    output.iter().all(|byte| *byte == 0xa5),
                    "{name}: short capacity {capacity} received a partial frame"
                );
                capacities += 1;
            }
            count += 1;
        }
    }
    assert_eq!(count, 24);
    assert_eq!(capacities, 2_816);
}

#[test]
fn typed_terminal_rejection_encoders_match_all_independent_saved_status_bytes() {
    // Construct the encoder inputs independently of the decoder so a shared
    // status-mapping error cannot hide behind a decode/encode round trip.
    for (index, saved_status) in TERMINAL_ERROR_STATUSES.into_iter().enumerate() {
        let name = format!("delivery_terminal_error_{}", index + 1);
        let expected = fixed(&name);
        let response = Response {
            opcode: Opcode::QueryDelivery,
            status: Status::Ok,
            request_id: OPAQUE_ID,
            boot_id: [0x33; 16],
            revision: 0,
            payload: ResponsePayload::QueryDelivery(QueryDeliveryResponse {
                state: DeliveryState::Terminal,
                saved_status,
                sequence: 1,
                stable_object_id: [0; 16],
                saved_revision: 0,
                previous_revision: 0,
                effective_ns: 0,
                consumed_ns: 0,
            }),
        };
        let mut output = vec![0xa5; expected.len()];
        assert_eq!(encode_response(&response, &mut output), Ok(expected.len()));
        assert_eq!(output, expected, "{name}");
    }
}

#[test]
fn all_nonterminal_states_keep_only_the_history_sequence() {
    for (name, state) in NONTERMINAL {
        let value = delivery(name);
        assert_eq!(value.state, state, "{name}");
        assert_eq!(value.saved_status, Status::Ok);
        assert_eq!(value.sequence, 1);
        assert_zero_metadata(&value);
    }
}

#[test]
fn exhausted_history_sequence_is_only_unknown_or_lost() {
    for (name, state) in [
        ("delivery_not_seen_sequence_max", DeliveryState::NotSeen),
        (
            "delivery_history_lost_sequence_max",
            DeliveryState::HistoryLost,
        ),
    ] {
        let value = delivery(name);
        assert_eq!(value.state, state, "{name}");
        assert_eq!(value.sequence, u64::MAX, "{name}");
        assert_eq!(value.saved_status, Status::Ok, "{name}");
        assert_zero_metadata(&value);
    }
}

#[test]
fn impossible_terminal_history_statuses_are_rejected() {
    for status in [Status::OutOfOrder, Status::Retired] {
        let mut bytes = fixed("delivery_terminal_error_1");
        bytes[66..68].copy_from_slice(&status.as_u16().to_le_bytes());
        assert_eq!(
            decode_response(&bytes),
            Err(Error::InvalidSequence),
            "{status:?}"
        );

        let response = Response {
            opcode: Opcode::QueryDelivery,
            status: Status::Ok,
            request_id: OPAQUE_ID,
            boot_id: [0x33; 16],
            revision: 0,
            payload: ResponsePayload::QueryDelivery(QueryDeliveryResponse {
                state: DeliveryState::Terminal,
                saved_status: status,
                sequence: 1,
                stable_object_id: [0; 16],
                saved_revision: 0,
                previous_revision: 0,
                effective_ns: 0,
                consumed_ns: 0,
            }),
        };
        let mut output = vec![0xa5; 128];
        assert_eq!(
            encode_response(&response, &mut output),
            Err(Error::InvalidSequence)
        );
    }
}

#[test]
fn read_usage_rejects_impossible_prior_window_prefix() {
    let mut bytes = fixed("read_opaque_id_ok");
    bytes[72..80].copy_from_slice(&140_000_000u64.to_le_bytes());
    bytes[80..88].copy_from_slice(&100_000_000u64.to_le_bytes());
    bytes[88..96].copy_from_slice(&35_000_000u64.to_le_bytes());
    assert_eq!(decode_response(&bytes), Err(Error::InvalidField));
}

#[test]
fn all_saved_terminal_rejections_preserve_status_without_success_metadata() {
    for (index, status) in TERMINAL_ERROR_STATUSES.into_iter().enumerate() {
        let name = format!("delivery_terminal_error_{}", index + 1);
        let value = delivery(&name);
        assert_eq!(value.state, DeliveryState::Terminal);
        assert_eq!(value.saved_status, status, "{name}");
        assert_eq!(value.sequence, 1);
        assert_zero_metadata(&value);
    }
}

#[test]
fn last_write_sequence_and_revision_increment_to_max_are_valid() {
    let request = decode_request(&fixed("install_last_sequence")).unwrap();
    assert_eq!(request.opcode, Opcode::InstallBudget);
    assert_eq!(request.target_slot, 7);
    assert_eq!(request.target_generation, 9);
    assert_eq!(
        install_budget_sequence(&request.request_id),
        Ok(u64::MAX - 1)
    );
    let RequestPayload::InstallBudget(budget) = request.payload else {
        panic!("expected typed InstallBudget request")
    };
    assert_eq!(budget.expected_revision, u64::MAX - 1);
    assert_eq!(budget.period_ns, CPU_PERIOD_NS);
    assert_eq!(budget.cap_ns, 20_000_000);
    assert_eq!(budget.reserved, 0);

    let response = decode_response(&fixed("install_revision_max")).unwrap();
    response.validate_for(&request).unwrap();
    assert_eq!(response.status, Status::Ok);
    assert_eq!(response.revision, u64::MAX);
    let ResponsePayload::InstallBudget(applied) = response.payload else {
        panic!("expected typed InstallBudget result")
    };
    assert_eq!(applied.previous_revision, u64::MAX - 1);
    assert_eq!(applied.effective_boottime_ns, 150_000_000);
    assert_eq!(applied.consumed_at_apply_ns, 35_000_000);
    assert!(applied.consumed_at_apply_ns > budget.cap_ns);
    assert!(applied.consumed_at_apply_ns <= applied.effective_boottime_ns % CPU_PERIOD_NS);

    let query = decode_request(&fixed("query_last_write_sequence")).unwrap();
    let history_response = decode_response(&fixed("delivery_revision_max")).unwrap();
    history_response.validate_for(&query).unwrap();
    let saved = delivery("delivery_revision_max");
    assert_eq!(saved.state, DeliveryState::Terminal);
    assert_eq!(saved.saved_status, Status::Ok);
    assert_eq!(saved.sequence, u64::MAX - 1);
    assert_eq!(saved.stable_object_id, [0x44; 16]);
    assert_eq!(saved.saved_revision, response.revision);
    assert_eq!(saved.previous_revision, applied.previous_revision);
    assert_eq!(saved.effective_ns, applied.effective_boottime_ns);
    assert_eq!(saved.consumed_ns, applied.consumed_at_apply_ns);
}

#[test]
fn history_and_read_ids_remain_opaque_including_nonzero_high_bytes() {
    assert_ne!(&OPAQUE_ID[8..], &[0; 8]);
    for (name, sequence, opcode) in [
        (
            "query_last_write_sequence",
            u64::MAX - 1,
            Opcode::QueryDelivery,
        ),
        (
            "query_history_sequence_max",
            u64::MAX,
            Opcode::QueryDelivery,
        ),
        (
            "retire_last_write_sequence",
            u64::MAX - 1,
            Opcode::RetireThrough,
        ),
    ] {
        let request = decode_request(&fixed(name)).expect(name);
        assert_eq!(request.request_id, OPAQUE_ID, "{name}");
        assert_eq!(request.opcode, opcode);
        assert_eq!(request.target_slot, 80);
        assert_eq!(request.target_generation, 3);
        let history = match request.payload {
            RequestPayload::QueryDelivery(value) | RequestPayload::RetireThrough(value) => value,
            other => panic!("wrong typed history payload: {other:?}"),
        };
        assert_eq!(history.history_boot, [0x33; 16]);
        assert_eq!(history.history_space, [0x22; 16]);
        assert_eq!(history.sequence, sequence);
    }

    let request = decode_request(&fixed("read_opaque_id")).unwrap();
    assert_eq!(request.request_id, OPAQUE_ID);
    assert_eq!(request.opcode, Opcode::ReadUsage);
    assert_eq!(request.target_slot, 7);
    assert_eq!(request.target_generation, 9);
    assert_eq!(request.payload, RequestPayload::ReadUsage);
    let response = decode_response(&fixed("read_opaque_id_ok")).unwrap();
    response.validate_for(&request).unwrap();
    assert_eq!(response.revision, u64::MAX);
    assert_eq!(response.boot_id, [0x33; 16]);
    let ResponsePayload::ReadUsage(usage) = response.payload else {
        panic!("expected typed ReadUsage result")
    };
    assert_eq!(usage.sample_boottime_ns, 150_000_000);
    assert_eq!(usage.cumulative_cpu_ns, 90_000_000);
    assert_eq!(usage.window_start_ns, 100_000_000);
    assert_eq!(usage.window_consumed_ns, 35_000_000);
    assert_eq!(usage.active_cap_ns, 20_000_000);
    assert_eq!(usage.active_period_ns, CPU_PERIOD_NS);
    assert_eq!(usage.event_sequence, 77);
    assert_eq!(usage.dropped_events, 2);
    assert!(usage.window_consumed_ns > usage.active_cap_ns);
    assert!(usage.window_consumed_ns <= usage.sample_boottime_ns - usage.window_start_ns);
}

#[test]
fn retired_frontier_can_reach_last_write_and_leave_next_sequence_max() {
    let request = decode_request(&fixed("retire_last_write_sequence")).unwrap();
    let response = decode_response(&fixed("retire_next_sequence_max")).unwrap();
    response.validate_for(&request).unwrap();
    assert_eq!(response.status, Status::Ok);
    assert_eq!(response.request_id, OPAQUE_ID);
    assert_eq!(response.boot_id, [0x33; 16]);
    assert_eq!(response.revision, 0);
    let ResponsePayload::RetireThrough(frontier) = response.payload else {
        panic!("expected typed RetireThrough result")
    };
    assert_eq!(frontier.retired_through, u64::MAX - 1);
    assert_eq!(frontier.next_sequence, u64::MAX);
}

#[test]
fn nonterminal_states_reject_saved_status_and_each_success_metadata_field() {
    // HOSR header is 64 bytes. Offsets refer to the fixed QueryDelivery payload.
    for (name, _) in NONTERMINAL {
        for offset in [66, 80, 96, 104, 112, 120] {
            let mut bytes = fixed(name);
            bytes[offset] = 1;
            assert_eq!(
                decode_response(&bytes),
                Err(Error::InvalidField),
                "{name}@{offset}"
            );
        }
        let mut bytes = fixed(name);
        bytes[72..80].fill(0);
        assert_eq!(
            decode_response(&bytes),
            Err(Error::InvalidSequence),
            "{name}"
        );
    }
}

#[test]
fn every_terminal_error_rejects_each_nonzero_success_metadata_field() {
    for (index, _) in TERMINAL_ERROR_STATUSES.into_iter().enumerate() {
        let name = format!("delivery_terminal_error_{}", index + 1);
        for offset in [80, 96, 104, 112, 120] {
            let mut bytes = fixed(&name);
            bytes[offset] = 1;
            assert_eq!(
                decode_response(&bytes),
                Err(Error::MalformedErrorResponse),
                "{name}@{offset}"
            );
        }
    }
}

#[test]
fn one_step_beyond_accepted_write_and_retire_boundaries_is_rejected() {
    let mut bytes = fixed("install_last_sequence");
    bytes[24..32].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(decode_request(&bytes), Err(Error::InvalidSequence));

    let mut bytes = fixed("install_last_sequence");
    bytes[64..72].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(decode_request(&bytes), Err(Error::InvalidField));

    let mut bytes = fixed("install_revision_max");
    bytes[64..72].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(decode_response(&bytes), Err(Error::IntegerOverflow));

    let mut bytes = fixed("retire_next_sequence_max");
    bytes[64..72].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(decode_response(&bytes), Err(Error::InvalidField));
}
