//! Rust-side malformed-input and bounded-output coverage.
//!
//! The valid frames are fixed bytes copied from the independently generated
//! golden file.  Each case mutates one field and calls the production decoder;
//! the Python oracle in `tests/abi` remains a separate implementation check.

use hos2_os_abi::{
    declared_response_len, decode_request, decode_response, decode_response_for,
    decode_response_prefix, decode_response_prefix_for, encode_response, DeliveryRequest, Error,
    InstallBudgetRequest, Opcode, QueryAbiResponse, Request, RequestPayload, Response,
    ResponsePayload, Status, Transport, CPU_PERIOD_NS,
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
    assert_eq!(encode_response(&parsed, &mut output), Err(Error::InvalidField));
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
