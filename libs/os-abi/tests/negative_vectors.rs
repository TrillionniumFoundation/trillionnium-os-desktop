//! Rust-side malformed-input and bounded-output coverage.
//!
//! The valid frames are fixed bytes copied from the independently generated
//! golden file.  Each case mutates one field and calls the production decoder;
//! the Python oracle in `tests/abi` remains a separate implementation check.

use hos2_os_abi::{
    declared_response_len, decode_request, decode_response, decode_response_for,
    decode_response_prefix, decode_response_prefix_for, encode_request, encode_response,
    DeliveryRequest, Error, InstallBudgetRequest, Opcode, QueryAbiResponse, Request,
    RequestPayload, Response, ResponsePayload, Status, Transport, CPU_PERIOD_NS,
};

fn hex(input: &str) -> Vec<u8> {
    assert_eq!(input.len() % 2, 0);
    input
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| {
            let hi = (pair[0] as char).to_digit(16).unwrap() as u8;
            let lo = (pair[1] as char).to_digit(16).unwrap() as u8;
            (hi << 4) | lo
        })
        .collect()
}

fn query_request() -> Vec<u8> {
    hex("484f5332020000000100000040000000000000000000000011111111111111111111111111111111000000000000000000000000000000000000000000000000")
}

fn install_request() -> Vec<u8> {
    hex("484f53320200000003000000400000002000000000000000010000000000000000000000000000000700000000000000090000000000000000000000000000000a0000000000000000e1f50500000000005a6202000000000000000000000000")
}

fn install_success() -> Vec<u8> {
    hex("484f5352020000000300000040000000180000000000000001000000000000000000000000000000333333333333333333333333333333330b000000000000000a00000000000000003b580800000000408af70100000000")
}

fn cas_error() -> Vec<u8> {
    hex("484f5352020000000300050040000000000000000000000001000000000000000000000000000000333333333333333333333333333333330000000000000000")
}

fn query_abi_success() -> Vec<u8> {
    hex("484f535202000000010000004000000030000000000000001111111111111111111111111111111133333333333333333333333333333333000000000000000022222222222222222222222222222222001000000000010000000100000000003e000000000000000000000000000000")
}

fn query_delivery_terminal() -> Vec<u8> {
    hex("484f535202000000040000004000000040000000000000001111111111111111111111111111111133333333333333333333333333333333000000000000000001000000000000000100000000000000444444444444444444444444444444440b000000000000000a00000000000000003b580800000000408af70100000000")
}

fn assert_err<T: core::fmt::Debug>(result: Result<T, Error>, expected: Error) {
    assert_eq!(result.unwrap_err(), expected);
}

fn golden_frame(name: &str) -> Vec<u8> {
    let mut current = "";
    for line in include_str!("../../../tests/golden/hos2.json").lines() {
        if let Some((_, value)) = line.split_once("\"name\": \"") {
            current = value.split_once('"').unwrap().0;
        }
        if current == name {
            if let Some((_, value)) = line.split_once("\"hex\": \"") {
                return hex(value.split_once('"').unwrap().0);
            }
        }
    }
    panic!("missing independent golden frame: {name}")
}

#[test]
fn self_consistent_install_response_must_match_the_requested_revision() {
    let bytes = install_success();
    let response = decode_response(&bytes).unwrap();
    let mut request = decode_request(&install_request()).unwrap();
    response.validate_for(&request).unwrap();

    let RequestPayload::InstallBudget(ref mut budget) = request.payload else {
        panic!("expected installation request")
    };
    budget.expected_revision = 9; // Legal request, but the result applied revision 10.
    let mut encoded = [0; 96];
    assert_eq!(encode_request(&request, &mut encoded), Ok(96));
    assert!(response.matches_request(&request));
    assert_eq!(response.validate_for(&request), Err(Error::InvalidField));
    assert_eq!(
        decode_response_for(&bytes, &request),
        Err(Error::InvalidField)
    );
    let mut capacity = bytes;
    capacity.extend_from_slice(&[0xa5; 32]);
    assert_eq!(
        decode_response_prefix_for(&capacity, &request),
        Err(Error::InvalidField)
    );
}

#[test]
fn self_consistent_retirement_must_cover_the_requested_frontier() {
    let bytes = golden_frame("retire_through_ok");
    let response = decode_response(&bytes).unwrap();
    let mut request = decode_request(&golden_frame("retire_through")).unwrap();
    response.validate_for(&request).unwrap();

    let RequestPayload::RetireThrough(ref mut history) = request.payload else {
        panic!("expected retirement request")
    };
    history.sequence = 2; // Result retired through 1; next_sequence=2 is valid alone.
    let mut encoded = [0; 104];
    assert_eq!(encode_request(&request, &mut encoded), Ok(104));
    assert!(response.matches_request(&request));
    assert_eq!(response.validate_for(&request), Err(Error::InvalidField));
    assert_eq!(
        decode_response_for(&bytes, &request),
        Err(Error::InvalidField)
    );
    let mut capacity = bytes;
    capacity.extend_from_slice(&[0xa5; 32]);
    assert_eq!(
        decode_response_prefix_for(&capacity, &request),
        Err(Error::InvalidField)
    );
}

#[test]
fn public_request_payload_mismatches_never_write_output() {
    let requests = [
        "query_abi",
        "read_usage",
        "install_budget",
        "query_delivery_with_new_view",
        "retire_through",
    ]
    .map(|name| decode_request(&golden_frame(name)).unwrap());
    for (index, original) in requests.iter().enumerate() {
        for (other_index, other) in requests.iter().enumerate() {
            if index == other_index {
                continue;
            }
            let mut invalid = *original;
            // A canonical sequence ID is also a valid opaque correlation ID.
            invalid.request_id = hos2_os_abi::install_budget_request_id(1).unwrap();
            invalid.payload = other.payload;
            let mut output = [0xa5; 160];
            assert_eq!(
                encode_request(&invalid, &mut output),
                Err(Error::InvalidField),
                "{:?} with {:?}",
                invalid.opcode,
                invalid.payload
            );
            assert_eq!(output, [0xa5; 160]);
        }
    }
}

#[test]
fn public_response_payload_mismatches_never_write_output() {
    let responses = [
        "query_abi_ok",
        "read_usage_lowered_cap",
        "install_budget_ok",
        "query_delivery_terminal",
        "retire_through_ok",
    ]
    .map(|name| decode_response(&golden_frame(name)).unwrap());
    for (index, original) in responses.iter().enumerate() {
        for (other_index, other) in responses.iter().enumerate() {
            if index == other_index {
                continue;
            }
            let mut invalid = *original;
            invalid.request_id = hos2_os_abi::install_budget_request_id(1).unwrap();
            invalid.payload = other.payload;
            let mut output = [0xa5; 160];
            assert_eq!(
                encode_response(&invalid, &mut output),
                Err(Error::InvalidField),
                "{:?} with {:?}",
                invalid.opcode,
                invalid.payload
            );
            assert_eq!(output, [0xa5; 160]);
        }
    }
}

#[test]
fn malformed_frame_lengths_are_rejected_before_unknown_opcode_or_status() {
    // NATIVE_ABI §3: check the full snapshot's framing before dispatching an
    // opcode. Otherwise a malformed unknown operation gets EOPNOTSUPP instead
    // of a structural EINVAL from the driver's error mapping.
    for response in [false, true] {
        let mut frame = if response {
            cas_error()
        } else {
            query_request()
        };
        frame[8..10].copy_from_slice(&u16::MAX.to_le_bytes());
        let parse = |bytes: &[u8]| {
            if response {
                decode_response(bytes).map(|_| ())
            } else {
                decode_request(bytes).map(|_| ())
            }
        };
        assert_eq!(parse(&frame), Err(Error::UnknownOpcode));

        frame[16..20].copy_from_slice(&1u32.to_le_bytes());
        assert_eq!(parse(&frame), Err(Error::Truncated));
        frame[16..20].fill(0);
        frame.push(0);
        assert_eq!(parse(&frame), Err(Error::TrailingBytes));
        frame[16..20].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(parse(&frame), Err(Error::PayloadTooLarge));
    }

    let mut unknown_status = cas_error();
    unknown_status[10..12].copy_from_slice(&u16::MAX.to_le_bytes());
    assert_err(decode_response(&unknown_status), Error::InvalidStatus);
    unknown_status[16..20].copy_from_slice(&1u32.to_le_bytes());
    assert_err(decode_response(&unknown_status), Error::Truncated);
}

#[test]
fn request_structure_mutations_are_rejected() {
    let valid = query_request();
    assert_err(decode_request(&valid[..63]), Error::Truncated);

    let mut frame = valid.clone();
    frame[0] = b'X';
    assert_err(decode_request(&frame), Error::InvalidMagic);

    let mut frame = valid.clone();
    frame[4] = 3;
    assert_err(decode_request(&frame), Error::UnknownVersion);

    let mut frame = valid.clone();
    frame[8] = 0xff;
    frame[9] = 0xff;
    assert_err(decode_request(&frame), Error::UnknownOpcode);

    let mut frame = valid.clone();
    frame[10] = 1;
    assert_err(decode_request(&frame), Error::InvalidFlags);

    let mut frame = valid.clone();
    frame[20] = 1;
    assert_err(decode_request(&frame), Error::ReservedNonZero);

    let mut frame = valid.clone();
    frame[56] = 1;
    assert_err(decode_request(&frame), Error::ReservedNonZero);

    let mut frame = install_request();
    frame[16] = 31;
    assert_err(decode_request(&frame), Error::TrailingBytes);

    let mut frame = install_request();
    frame[16] = 33;
    assert_err(decode_request(&frame), Error::Truncated);

    let mut frame = query_request();
    frame[16] = 1;
    frame[17] = 0;
    frame[18] = 1;
    frame[19] = 0;
    assert_err(decode_request(&frame), Error::PayloadTooLarge);

    let mut frame = query_request();
    frame[24..40].fill(0);
    assert_err(decode_request(&frame), Error::InvalidRequestId);

    let mut frame = query_request();
    frame[40] = 1;
    assert_err(decode_request(&frame), Error::InvalidTarget);

    let mut frame = install_request();
    frame[48..56].fill(0);
    assert_err(decode_request(&frame), Error::InvalidGeneration);

    let mut frame = install_request();
    frame[32] = 1;
    assert_err(decode_request(&frame), Error::SequenceHighBytesNonZero);

    let mut frame = install_request();
    frame[24..32].fill(0xff);
    assert_err(decode_request(&frame), Error::InvalidSequence);
}

#[test]
fn response_structure_mutations_are_rejected() {
    let mut frame = install_success();
    frame[10] = 0xff;
    frame[11] = 0xff;
    assert_err(decode_response(&frame), Error::InvalidStatus);

    let mut frame = install_success();
    frame[10] = 5;
    assert_err(decode_response(&frame), Error::MalformedErrorResponse);

    let mut frame = cas_error();
    frame[16] = 1;
    assert_err(decode_response(&frame), Error::Truncated);

    let mut frame = install_success();
    frame.push(0);
    assert_err(decode_response(&frame), Error::TrailingBytes);

    let mut frame = query_abi_success();
    frame[96..104].copy_from_slice(&0x22u64.to_le_bytes());
    assert_err(decode_response(&frame), Error::InvalidField);

    let mut frame = query_delivery_terminal();
    frame[96..104].copy_from_slice(&1u64.to_le_bytes());
    frame[104..112].fill(0);
    assert_err(decode_response(&frame), Error::InvalidField);
}

#[test]
fn encoders_report_insufficient_output_capacity() {
    let response = Response {
        opcode: Opcode::QueryAbi,
        status: Status::Ok,
        request_id: [1; 16],
        boot_id: [2; 16],
        revision: 0,
        payload: ResponsePayload::QueryAbi(QueryAbiResponse {
            space_id: [3; 16],
            page_size: 4096,
            max_request_payload: 65536,
            max_response_payload: 65536,
            supported_ops: 0x3e,
            features: 0,
        }),
    };
    let mut output = [0u8; 111];
    assert_eq!(
        encode_response(&response, &mut output),
        Err(Error::InsufficientCapacity)
    );

    let error_response = Response {
        opcode: Opcode::InstallBudget,
        status: Status::Conflict,
        request_id: [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        boot_id: [2; 16],
        revision: 0,
        payload: ResponsePayload::Empty,
    };
    let mut output = [0u8; 64];
    assert_eq!(encode_response(&error_response, &mut output), Ok(64));
}

#[test]
fn correlation_and_capacity_helpers_are_stable() {
    let request = Request {
        opcode: Opcode::InstallBudget,
        request_id: [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        target_slot: 7,
        target_generation: 9,
        payload: RequestPayload::InstallBudget(InstallBudgetRequest {
            expected_revision: 10,
            period_ns: CPU_PERIOD_NS,
            cap_ns: 40_000_000,
            reserved: 0,
        }),
    };
    let response = decode_response(&install_success()).unwrap();
    assert!(response.matches_request(&request));
    assert!(response.validate_for(&request).is_ok());
    assert!(decode_response_for(&install_success(), &request).is_ok());
    let mut with_capacity = install_success();
    with_capacity.extend_from_slice(&[0; 16]);
    assert_eq!(declared_response_len(&with_capacity), Ok(88));
    assert!(decode_response(&with_capacity[..88]).is_ok());
    let (_, prefix_len) = decode_response_prefix(&with_capacity).unwrap();
    assert_eq!(prefix_len, 88);
    let (_, prefix_len) = decode_response_prefix_for(&with_capacity, &request).unwrap();
    assert_eq!(prefix_len, 88);

    let mut wrong_id = request;
    wrong_id.request_id[0] = 2;
    assert_eq!(response.validate_for(&wrong_id), Err(Error::InvalidField));
    let mut invalid_request = request;
    invalid_request.payload = RequestPayload::ReadUsage;
    assert_eq!(
        response.validate_for(&invalid_request),
        Err(Error::InvalidField)
    );

    let transport = Transport::new(0, 0, 96, 88);
    assert_eq!(
        transport.ensure_response_capacity(Opcode::InstallBudget, Status::Ok),
        Ok(())
    );
    assert_eq!(
        transport.ensure_response_capacity(Opcode::InstallBudget, Status::Conflict),
        Ok(())
    );
    let insufficient = Transport::new(0, 0, 96, 64);
    assert_eq!(
        insufficient.ensure_response_capacity(Opcode::InstallBudget, Status::Conflict),
        Err(Error::InsufficientCapacity)
    );
    assert_eq!(
        insufficient.ensure_success_response_capacity(Opcode::InstallBudget),
        Err(Error::InsufficientCapacity)
    );
    let short = Transport::new(0, 0, 96, 87);
    assert_eq!(
        short.ensure_response_capacity(Opcode::InstallBudget, Status::Ok),
        Err(Error::InsufficientCapacity)
    );
    assert_eq!(
        hos2_os_abi::required_response_frame_len(Opcode::InstallBudget, Status::Ok),
        88
    );

    // Delivery request IDs remain opaque to this correlation helper.
    let _history = DeliveryRequest {
        history_boot: [3; 16],
        history_space: [4; 16],
        sequence: u64::MAX,
    };
}

#[test]
fn transport_rejects_wrapping_pointer_ranges_without_access_checks() {
    // A valid user address is a kernel/OS property. The ABI layer only
    // rejects arithmetic overflow before a copy attempt.
    let mut raw = [0u8; 32];
    raw[0..8].copy_from_slice(&(u64::MAX - 63).to_le_bytes());
    raw[16..20].copy_from_slice(&64u32.to_le_bytes());
    raw[20..24].copy_from_slice(&88u32.to_le_bytes());
    assert_err(Transport::decode(&raw), Error::IntegerOverflow);

    raw[0..8].copy_from_slice(&(u64::MAX - 64).to_le_bytes());
    raw[8..16].copy_from_slice(&(u64::MAX - 87).to_le_bytes());
    assert_err(Transport::decode(&raw), Error::IntegerOverflow);

    raw[8..16].copy_from_slice(&(u64::MAX - 88).to_le_bytes());
    assert_eq!(Transport::decode(&raw).unwrap().response_capacity, 88);

    let bad = Transport::new(u64::MAX, 0, 64, 88);
    let mut output = [0x5a; 32];
    assert_eq!(bad.encode(&mut output), Err(Error::IntegerOverflow));
    assert_eq!(output, [0x5a; 32]);
    assert!(Transport::new(0, 0, 64, 88).encode(&mut output).is_ok());
}

#[test]
fn install_response_echo_rejects_unordered_ids_in_success_and_failure() {
    for original in [install_success(), cas_error()] {
        let mut high = original.clone();
        high[32] = 1;
        assert_err(decode_response(&high), Error::SequenceHighBytesNonZero);

        let mut exhausted = original.clone();
        exhausted[24..32].fill(0xff);
        assert_err(decode_response(&exhausted), Error::InvalidSequence);

        let mut zero = original.clone();
        zero[24..32].fill(0);
        assert_err(decode_response(&zero), Error::InvalidRequestId);

        let mut parsed = decode_response(&original).unwrap();
        parsed.request_id[8] = 1;
        let mut output = [0u8; 128];
        assert_eq!(
            encode_response(&parsed, &mut output),
            Err(Error::SequenceHighBytesNonZero)
        );
    }
}

#[test]
fn install_previous_revision_must_be_a_valid_existing_revision() {
    let mut frame = install_success();
    frame[64..72].fill(0);
    frame[56..64].copy_from_slice(&1u64.to_le_bytes());
    assert_err(decode_response(&frame), Error::InvalidField);

    let mut parsed = decode_response(&install_success()).unwrap();
    parsed.revision = 1;
    if let ResponsePayload::InstallBudget(ref mut payload) = parsed.payload {
        payload.previous_revision = 0;
    } else {
        panic!("fixed InstallBudget fixture decoded to wrong payload");
    }
    let mut output = [0u8; 128];
    assert_eq!(
        encode_response(&parsed, &mut output),
        Err(Error::InvalidField)
    );
}

#[test]
fn fixed_golden_budget_mutations_preserve_delivery_id_but_change_canonical_request() {
    let original_bytes = install_request();
    let original = decode_request(&original_bytes).unwrap();
    for (offset, value) in [(64usize, 11u64), (80usize, 39_000_000u64)] {
        let mut changed = original_bytes.clone();
        changed[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        let mutation = decode_request(&changed).unwrap();
        assert_eq!(original.request_id, mutation.request_id);
        assert_eq!(original.target_slot, mutation.target_slot);
        assert_eq!(original.target_generation, mutation.target_generation);
        assert_ne!(original.payload, mutation.payload);
        assert_ne!(original, mutation, "mutation must conflict, not be a retry");
    }
}

#[test]
fn budget_cpu_time_cannot_exceed_elapsed_window_time() {
    // A lower cap does not erase previously consumed CPU:
    // the fixture remains > 20ms after lowering.
    let usage = hex("484f5352020000000200000040000000400000000000000011111111111111111111111111111111333333333333333333333333333333330b0000000000000080d1f00800000000804a5d050000000000e1f50500000000c00e160200000000002d31010000000000e1f505000000004d000000000000000200000000000000");
    let valid = decode_response(&usage).unwrap();
    if let ResponsePayload::ReadUsage(snapshot) = valid.payload {
        assert!(snapshot.window_consumed_ns > snapshot.active_cap_ns);
        assert_eq!(
            snapshot.sample_boottime_ns - snapshot.window_start_ns,
            50_000_000
        );
    } else {
        panic!("golden ReadUsage should decode");
    }
    let mut impossible = usage;
    impossible[88..96].copy_from_slice(&51_000_000u64.to_le_bytes());
    assert_err(decode_response(&impossible), Error::InvalidField);

    let mut impossible = install_success();
    impossible[80..88].copy_from_slice(&41_000_000u64.to_le_bytes());
    assert_err(decode_response(&impossible), Error::InvalidField);

    let mut impossible = query_delivery_terminal();
    impossible[120..128].copy_from_slice(&41_000_000u64.to_le_bytes());
    assert_err(decode_response(&impossible), Error::InvalidField);
}

#[test]
fn unknown_minor_and_exact_wire_lengths_are_rejected() {
    let mut request = query_request();
    request[6] = 1;
    assert_err(decode_request(&request), Error::UnknownVersion);

    let mut response = install_success();
    response[6] = 1;
    assert_err(decode_response(&response), Error::UnknownVersion);

    let mut request = install_request();
    request.truncate(88);
    request[16..20].copy_from_slice(&24u32.to_le_bytes());
    assert_err(decode_request(&request), Error::PayloadLengthMismatch);

    let mut response = install_success();
    response.truncate(87);
    response[16..20].copy_from_slice(&23u32.to_le_bytes());
    assert_err(decode_response(&response), Error::PayloadLengthMismatch);

    let mut descriptor = [0u8; 32];
    Transport::new(0, 0, 64, 112)
        .encode(&mut descriptor)
        .unwrap();
    assert_err(Transport::decode(&descriptor[..31]), Error::Truncated);
    let mut trailing = descriptor.to_vec();
    trailing.push(0);
    assert_err(Transport::decode(&trailing), Error::TrailingBytes);
    descriptor[24] = 1;
    assert_err(Transport::decode(&descriptor), Error::ReservedNonZero);
}
#[test]
fn ordered_sequence_helpers_provide_canonical_little_endian_ids() {
    use hos2_os_abi::{install_budget_request_id, install_budget_sequence};
    assert_eq!(install_budget_request_id(0), Err(Error::InvalidSequence));
    assert_eq!(
        install_budget_request_id(u64::MAX),
        Err(Error::InvalidSequence)
    );
    assert_eq!(
        install_budget_sequence(&[0; 16]),
        Err(Error::InvalidRequestId)
    );

    for sequence in [1, 255, 256, 0x0102_0304_0506_0708, u64::MAX - 1] {
        let id = install_budget_request_id(sequence).unwrap();
        assert_eq!(&id[..8], &sequence.to_le_bytes());
        assert_eq!(&id[8..], &[0; 8]);
        assert_eq!(install_budget_sequence(&id), Ok(sequence));
    }

    let mut bad = install_budget_request_id(1).unwrap();
    bad[15] = 1;
    assert_eq!(
        install_budget_sequence(&bad),
        Err(Error::SequenceHighBytesNonZero)
    );
}

#[test]
fn install_revision_mismatch_is_not_an_integer_overflow() {
    let valid = install_success();
    let mut mismatched = valid.clone();
    mismatched[56..64].copy_from_slice(&12u64.to_le_bytes());
    assert_err(decode_response(&mismatched), Error::InvalidField);

    let mut encoding_mismatch = decode_response(&valid).unwrap();
    encoding_mismatch.revision = 12;
    let mut out = [0x5a; 88];
    assert_eq!(
        encode_response(&encoding_mismatch, &mut out),
        Err(Error::InvalidField)
    );
    assert_eq!(out, [0x5a; 88]);

    let mut overflow = valid.clone();
    overflow[64..72].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_err(decode_response(&overflow), Error::IntegerOverflow);

    let mut encoding_overflow = decode_response(&valid).unwrap();
    if let ResponsePayload::InstallBudget(ref mut installed) = encoding_overflow.payload {
        installed.previous_revision = u64::MAX;
    } else {
        panic!("expected golden InstallBudget result");
    }
    assert_eq!(
        encode_response(&encoding_overflow, &mut out),
        Err(Error::IntegerOverflow)
    );
    assert_eq!(out, [0x5a; 88]);
}

#[test]
fn query_abi_capability_table_rejects_unsupported_feature_combinations() {
    let golden = query_abi_success();

    for (offset, value, expected) in [
        (80usize, 0u32, Error::InvalidField),
        (80, 3, Error::InvalidField),
        (84, 65_537, Error::PayloadTooLarge),
        (88, 65_537, Error::PayloadTooLarge),
        (88, 47, Error::InvalidField),
    ] {
        let mut frame = golden.clone();
        frame[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        assert_err(decode_response(&frame), expected);
    }

    let mut invalid = golden.clone();
    invalid[92] = 1;
    assert_err(decode_response(&invalid), Error::InvalidField);

    let mut invalid = golden.clone();
    invalid[96..104].copy_from_slice(&0u64.to_le_bytes());
    assert_err(decode_response(&invalid), Error::InvalidField);

    let mut invalid = golden.clone();
    invalid[96..104].copy_from_slice(&0x0au64.to_le_bytes());
    assert_err(decode_response(&invalid), Error::InvalidField);

    let mut invalid = golden.clone();
    invalid[104..112].copy_from_slice(&1u64.to_le_bytes());
    assert_err(decode_response(&invalid), Error::InvalidField);

    // HOS2 also permits a QueryAbi-only implementation. The operations
    // mask is a format advertisement, not a grant of resource authority.
    let mut limited = golden;
    limited[96..104].copy_from_slice(&2u64.to_le_bytes());
    limited[84..88].copy_from_slice(&0u32.to_le_bytes());
    limited[88..92].copy_from_slice(&48u32.to_le_bytes());
    let decoded = decode_response(&limited).unwrap();
    let mut out = [0u8; 112];
    assert_eq!(encode_response(&decoded, &mut out), Ok(112));
    assert_eq!(out.as_slice(), limited.as_slice());
}

#[test]
fn install_budget_request_rejects_revision_period_cap_and_reserved_mutations() {
    let golden = install_request();
    for (offset, value) in [
        (64usize, 0u64),
        (64, u64::MAX),
        (72, CPU_PERIOD_NS - 1),
        (72, CPU_PERIOD_NS + 1),
        (80, CPU_PERIOD_NS + 1),
        (88, 1),
    ] {
        let mut invalid = golden.clone();
        invalid[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        assert_err(decode_request(&invalid), Error::InvalidField);
    }
    let mut request = decode_request(&golden).unwrap();
    if let RequestPayload::InstallBudget(ref mut budget) = request.payload {
        budget.cap_ns = CPU_PERIOD_NS + 1;
    }
    let mut out = [0xa5; 96];
    assert_eq!(
        hos2_os_abi::encode_request(&request, &mut out),
        Err(Error::InvalidField)
    );
    assert_eq!(out, [0xa5; 96]);
}

#[test]
fn query_delivery_terminal_metadata_and_historical_request_are_checked() {
    let golden = query_delivery_terminal();

    let mut invalid = golden.clone();
    invalid[68] = 1; // nested QueryDelivery reserved:u32
    assert_err(decode_response(&invalid), Error::ReservedNonZero);

    let mut invalid = golden.clone();
    invalid[64..66].copy_from_slice(&5u16.to_le_bytes());
    assert_err(decode_response(&invalid), Error::InvalidField);

    let mut invalid = golden.clone();
    invalid[66..68].copy_from_slice(&Status::Conflict.as_u16().to_le_bytes());
    assert_err(decode_response(&invalid), Error::MalformedErrorResponse);

    let mut invalid = golden.clone();
    invalid[80..96].fill(0);
    assert_err(decode_response(&invalid), Error::InvalidField);

    let mut invalid = golden.clone();
    invalid[96..104].copy_from_slice(&12u64.to_le_bytes());
    assert_err(decode_response(&invalid), Error::InvalidField);

    let query = hex("484f533202000000040000004000000028000000000000001111111111111111111111111111111150000000000000000300000000000000000000000000000033333333333333333333333333333333222222222222222222222222222222220100000000000000");
    let request = decode_request(&query).unwrap();
    assert!(decode_response_for(&golden, &request).is_ok());

    let mut wrong_sequence = golden.clone();
    wrong_sequence[72..80].copy_from_slice(&2u64.to_le_bytes());
    assert!(decode_response(&wrong_sequence).is_ok());
    assert_err(
        decode_response_for(&wrong_sequence, &request),
        Error::InvalidField,
    );

    let mut zero_history_boot = query.clone();
    zero_history_boot[64..80].fill(0);
    assert_err(decode_request(&zero_history_boot), Error::InvalidField);
    let mut zero_history_space = query.clone();
    zero_history_space[80..96].fill(0);
    assert_err(decode_request(&zero_history_space), Error::InvalidField);
    let mut zero_history_sequence = query;
    zero_history_sequence[96..104].fill(0);
    assert_err(decode_request(&zero_history_sequence), Error::InvalidField);
}

#[test]
fn read_usage_and_retire_through_reject_impossible_semantic_values() {
    let usage = hex("484f5352020000000200000040000000400000000000000011111111111111111111111111111111333333333333333333333333333333330b0000000000000080d1f00800000000804a5d050000000000e1f50500000000c00e160200000000002d31010000000000e1f505000000004d000000000000000200000000000000");
    assert!(decode_response(&usage).is_ok());

    for (offset, value) in [
        (72usize, 34_999_999u64), // cumulative less than window consumed
        (80, 101_000_000),        // wrong 100ms window start
        (88, 50_000_001),         // impossible single-CPU consumption
        (96, CPU_PERIOD_NS + 1),  // cap exceeds period
        (104, CPU_PERIOD_NS - 1), // unsupported period
        (120, 78),                // dropped_events > event_sequence
    ] {
        let mut invalid = usage.clone();
        invalid[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        assert_err(decode_response(&invalid), Error::InvalidField);
    }

    let retirement = hex("484f535202000000050000004000000010000000000000001111111111111111111111111111111133333333333333333333333333333333000000000000000001000000000000000200000000000000");
    assert!(decode_response(&retirement).is_ok());
    let mut invalid = retirement.clone();
    invalid[72..80].copy_from_slice(&1u64.to_le_bytes());
    assert_err(decode_response(&invalid), Error::InvalidField);
    let mut invalid = retirement;
    invalid[72..80].fill(0);
    assert_err(decode_response(&invalid), Error::InvalidField);
}
