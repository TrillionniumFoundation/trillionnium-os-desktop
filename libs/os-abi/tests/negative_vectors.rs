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
        request_id: [1; 16],
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
