//! Transport-bound response parsing, using immutable Python-generated HOS2
//! golden bytes. These tests exercise a *consumer* boundary, not another wire
//! codec, user memory accessor or delivery state machine.

use hos2_os_abi::{
    decode_request, decode_response_for, decode_response_prefix_for, response_frame_len, Error,
    Status, Transport, MAX_FRAME,
};

fn fixed(name: &str) -> Vec<u8> {
    let mut current_name = "";
    for line in include_str!("../../../tests/golden/hos2.json").lines() {
        if let Some((_, value)) = line.split_once("\"name\": \"") {
            current_name = value.split('"').next().unwrap();
        }
        if current_name == name {
            if let Some((_, value)) = line.split_once("\"hex\": \"") {
                let raw = value.split('"').next().unwrap();
                return raw
                    .as_bytes()
                    .as_chunks::<2>()
                    .0
                    .iter()
                    .map(|pair| {
                        let high = (pair[0] as char).to_digit(16).unwrap() as u8;
                        let low = (pair[1] as char).to_digit(16).unwrap() as u8;
                        (high << 4) | low
                    })
                    .collect();
            }
        }
    }
    panic!("unknown independent golden frame: {name}");
}

fn descriptor(request_len: usize, capacity: usize) -> Transport {
    // The aliases are intentional: overlapping copyin/copyout is legal once
    // the input has been copied into an owned request snapshot.
    Transport::new(0x1000, 0x1000, request_len as u32, capacity as u32)
}

#[test]
fn every_fixed_success_and_error_response_accepts_its_own_transport_bounds() {
    let cases = [
        ("query_abi", "query_abi_ok"),
        ("read_usage", "read_usage_lowered_cap"),
        ("install_budget", "install_budget_ok"),
        ("install_budget", "install_cas_rejection"),
        ("query_delivery_with_new_view", "query_delivery_terminal"),
        ("query_delivery_with_new_view", "query_delivery_retired"),
        ("retire_through", "retire_through_ok"),
    ];
    for (request_name, response_name) in cases {
        let request_bytes = fixed(request_name);
        let request = decode_request(&request_bytes).unwrap();
        let response_bytes = fixed(response_name);
        let expected = decode_response_for(&response_bytes, &request).unwrap();

        // A caller may own the full response buffer even when copyout wrote
        // only the declared HOSR frame.
        let mut copied = response_bytes.clone();
        let required = response_frame_len(request.opcode, Status::Ok);
        copied.resize((response_bytes.len() + 17).max(required), 0xa5);
        let transport = descriptor(request_bytes.len(), copied.len());
        let (decoded, length) = transport
            .decode_response_snapshot_for(&copied, &request)
            .unwrap();
        assert_eq!(decoded, expected, "{response_name}");
        assert_eq!(length, response_bytes.len(), "{response_name}");
        assert!(
            copied[length..].iter().all(|byte| *byte == 0xa5),
            "{response_name}"
        );

        // Errors still need capacity for the opcode's successful result,
        // though the actual copied frame is only a 64-byte HOSR header.
        let minimal_capacity = response_frame_len(request.opcode, Status::Ok);
        let exact = descriptor(request_bytes.len(), minimal_capacity);
        assert_eq!(
            exact.decode_response_snapshot_for(&response_bytes, &request),
            Ok((expected, response_bytes.len())),
            "{response_name}"
        );
    }
}

#[test]
fn short_success_capacity_rejects_even_a_complete_64_byte_error_response() {
    let request_bytes = fixed("install_budget");
    let request = decode_request(&request_bytes).unwrap();
    let error = fixed("install_cas_rejection");
    assert_eq!(error.len(), 64);
    assert_eq!(response_frame_len(request.opcode, Status::Ok), 88);
    for capacity in [0usize, 63, 64, 87] {
        let transport = descriptor(request_bytes.len(), capacity);
        let visible = &error[..error.len().min(capacity)];
        assert_eq!(
            transport.decode_response_snapshot_for(visible, &request),
            Err(Error::InsufficientCapacity),
            "capacity {capacity}"
        );
    }
}

#[test]
fn unbounded_prefix_mutant_accepts_bytes_outside_advertised_copyout_capacity() {
    let request_bytes = fixed("query_abi");
    let request = decode_request(&request_bytes).unwrap();
    let response = fixed("query_abi_ok");
    assert_eq!(response.len(), 112);
    let mut outside_copyout = response.clone();
    outside_copyout.push(0x5a);

    // Known-bad consumer: the standalone prefix decoder cannot see ioctl
    // response_capacity. A forged overlong buffer therefore passes it.
    assert!(decode_response_prefix_for(&outside_copyout, &request).is_ok());
    let bounded = descriptor(request_bytes.len(), response.len());
    assert_eq!(
        bounded.decode_response_snapshot_for(&outside_copyout, &request),
        Err(Error::InvalidTransport)
    );

    // Even valid frame bytes are not admissible when the descriptor could
    // have copied one fewer byte than this successful response requires.
    let too_short = descriptor(request_bytes.len(), response.len() - 1);
    assert_eq!(
        too_short.decode_response_snapshot_for(&response, &request),
        Err(Error::InvalidTransport)
    );
}

#[test]
fn transport_descriptor_and_typed_request_must_describe_the_same_frame() {
    let request_bytes = fixed("query_abi");
    let request = decode_request(&request_bytes).unwrap();
    let response = fixed("query_abi_ok");

    let wrong_input_length = descriptor(request_bytes.len() + 1, response.len());
    assert_eq!(
        wrong_input_length.decode_response_snapshot_for(&response, &request),
        Err(Error::InvalidTransport)
    );

    let mut reserved = descriptor(request_bytes.len(), response.len());
    reserved.reserved = 1;
    assert_eq!(
        reserved.decode_response_snapshot_for(&response, &request),
        Err(Error::ReservedNonZero)
    );

    let mut wraparound = descriptor(request_bytes.len(), response.len());
    wraparound.response_addr = u64::MAX - 3;
    assert_eq!(
        wraparound.decode_response_snapshot_for(&response, &request),
        Err(Error::IntegerOverflow)
    );

    let mut oversized_input = descriptor(request_bytes.len(), response.len());
    oversized_input.request_bytes = (MAX_FRAME + 1) as u32;
    assert_eq!(
        oversized_input.decode_response_snapshot_for(&response, &request),
        Err(Error::InvalidTransport)
    );
}

#[test]
fn malformed_truncated_and_mismatched_responses_remain_rejected() {
    let request_bytes = fixed("query_abi");
    let request = decode_request(&request_bytes).unwrap();
    let response = fixed("query_abi_ok");
    let transport = descriptor(request_bytes.len(), response.len());

    assert_eq!(
        transport.decode_response_snapshot_for(&response[..63], &request),
        Err(Error::Truncated)
    );

    let mut invalid_magic = response.clone();
    invalid_magic[0] = b'X';
    assert_eq!(
        transport.decode_response_snapshot_for(&invalid_magic, &request),
        Err(Error::InvalidMagic)
    );

    let mut overdeclared = response.clone();
    overdeclared[16..20].copy_from_slice(&49u32.to_le_bytes());
    assert_eq!(
        transport.decode_response_snapshot_for(&overdeclared, &request),
        Err(Error::Truncated)
    );

    let mut other_request = request;
    other_request.request_id[0] = 0x12;
    assert_eq!(
        transport.decode_response_snapshot_for(&response, &other_request),
        Err(Error::InvalidField)
    );
}
