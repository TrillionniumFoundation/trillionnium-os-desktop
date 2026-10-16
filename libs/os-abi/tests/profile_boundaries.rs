//! Independently patched golden bytes exercise the documented N0 profiles.
//!
//! Encoding uses separately constructed public values, including invalid ones;
//! decoding never acts as the gatekeeper for an encoder rejection assertion.
//! These host codec checks do not establish kernel execution or authorization.

use hos2_os_abi::{
    decode_response, encode_response, Error, Opcode, QueryAbiResponse, ReadUsageResponse, Response,
    ResponsePayload, Status, CPU_PERIOD_NS,
};

// The seven masks follow NATIVE_ABI's bit dependencies. Keep this table
// independent of the production validator and its payload-size helpers.
const QUERY_PROFILES: [(u64, u32, u32); 7] = [
    (0x02, 0, 48),
    (0x06, 0, 64),
    (0x12, 40, 64),
    (0x16, 40, 64),
    (0x32, 40, 64),
    (0x36, 40, 64),
    (0x3e, 40, 64),
];

fn fixed(name: &str) -> Vec<u8> {
    let mut current = "";
    for line in include_str!("../../../tests/golden/hos2.json").lines() {
        if let Some((_, value)) = line.split_once("\"name\": \"") {
            current = value.split_once('"').unwrap().0;
        }
        if current == name {
            if let Some((_, value)) = line.split_once("\"hex\": \"") {
                return value
                    .split_once('"')
                    .unwrap()
                    .0
                    .as_bytes()
                    .chunks_exact(2)
                    .map(|pair| {
                        let hi = (pair[0] as char).to_digit(16).unwrap();
                        let lo = (pair[1] as char).to_digit(16).unwrap();
                        ((hi << 4) | lo) as u8
                    })
                    .collect();
            }
        }
    }
    panic!("missing fixed profile vector: {name}")
}

fn query_profile() -> QueryAbiResponse {
    QueryAbiResponse {
        space_id: [0x22; 16],
        page_size: 4096,
        max_request_payload: 65_536,
        max_response_payload: 65_536,
        supported_ops: 0x3e,
        features: 0,
    }
}

fn usage_profile() -> ReadUsageResponse {
    ReadUsageResponse {
        sample_boottime_ns: 150_000_000,
        cumulative_cpu_ns: 90_000_000,
        window_start_ns: 100_000_000,
        window_consumed_ns: 35_000_000,
        active_cap_ns: 20_000_000,
        active_period_ns: CPU_PERIOD_NS,
        event_sequence: 77,
        dropped_events: 2,
    }
}

fn assert_codec_response(
    response: Response,
    bytes: &[u8],
    expected: Result<(), Error>,
    case: &str,
) {
    let decoded = decode_response(bytes);
    let mut output = vec![0xa5; bytes.len() + 17];
    let encoded = encode_response(&response, &mut output);
    match expected {
        Ok(()) => {
            assert_eq!(decoded, Ok(response), "decode: {case}");
            assert_eq!(encoded, Ok(bytes.len()), "encode: {case}");
            assert_eq!(&output[..bytes.len()], bytes, "wire bytes: {case}");
            assert!(
                output[bytes.len()..].iter().all(|byte| *byte == 0xa5),
                "encoder changed unused capacity: {case}"
            );
        }
        Err(error) => {
            assert_eq!(decoded, Err(error), "decode: {case}");
            assert_eq!(encoded, Err(error), "encode: {case}");
            assert!(
                output.iter().all(|byte| *byte == 0xa5),
                "invalid public value partially wrote output: {case}"
            );
        }
    }
}

fn assert_query(golden: &[u8], value: QueryAbiResponse, expected: Result<(), Error>, case: &str) {
    // Patch fixed independent bytes at documented HOSR payload offsets.
    let mut bytes = golden.to_vec();
    bytes[64..80].copy_from_slice(&value.space_id);
    bytes[80..84].copy_from_slice(&value.page_size.to_le_bytes());
    bytes[84..88].copy_from_slice(&value.max_request_payload.to_le_bytes());
    bytes[88..92].copy_from_slice(&value.max_response_payload.to_le_bytes());
    bytes[96..104].copy_from_slice(&value.supported_ops.to_le_bytes());
    bytes[104..112].copy_from_slice(&value.features.to_le_bytes());
    let response = Response {
        opcode: Opcode::QueryAbi,
        status: Status::Ok,
        request_id: [0x11; 16],
        boot_id: [0x33; 16],
        revision: 0,
        payload: ResponsePayload::QueryAbi(value),
    };
    assert_codec_response(response, &bytes, expected, case);
}

fn assert_usage(golden: &[u8], value: ReadUsageResponse, expected: Result<(), Error>, case: &str) {
    let mut bytes = golden.to_vec();
    for (index, field) in [
        value.sample_boottime_ns,
        value.cumulative_cpu_ns,
        value.window_start_ns,
        value.window_consumed_ns,
        value.active_cap_ns,
        value.active_period_ns,
        value.event_sequence,
        value.dropped_events,
    ]
    .into_iter()
    .enumerate()
    {
        let offset = 64 + index * 8;
        bytes[offset..offset + 8].copy_from_slice(&field.to_le_bytes());
    }
    let response = Response {
        opcode: Opcode::ReadUsage,
        status: Status::Ok,
        request_id: [0x11; 16],
        boot_id: [0x33; 16],
        revision: 11,
        payload: ResponsePayload::ReadUsage(value),
    };
    assert_codec_response(response, &bytes, expected, case);
}

#[test]
fn query_abi_supported_operation_masks_match_documented_table() {
    let golden = fixed("query_abi_ok");
    for mask in 0..=0x7f {
        let value = QueryAbiResponse {
            supported_ops: mask,
            ..query_profile()
        };
        let expected = if QUERY_PROFILES.iter().any(|profile| profile.0 == mask) {
            Ok(())
        } else {
            Err(Error::InvalidField)
        };
        assert_query(
            &golden,
            value,
            expected,
            &format!("supported mask {mask:#x}"),
        );
    }
    for (mask, _, _) in QUERY_PROFILES {
        for unknown_bit in 7..64 {
            let value = QueryAbiResponse {
                supported_ops: mask | (1u64 << unknown_bit),
                ..query_profile()
            };
            assert_query(
                &golden,
                value,
                Err(Error::InvalidField),
                &format!("mask {mask:#x} with unknown bit {unknown_bit}"),
            );
        }
    }
    assert_query(
        &golden,
        QueryAbiResponse {
            supported_ops: u64::MAX,
            ..query_profile()
        },
        Err(Error::InvalidField),
        "all supported-op bits set",
    );
}

#[test]
fn query_abi_advertised_payload_minima_match_each_supported_profile() {
    let golden = fixed("query_abi_ok");
    for (mask, min_request, min_response) in QUERY_PROFILES {
        for request_limit in 0..=41 {
            for response_limit in 0..=65 {
                let value = QueryAbiResponse {
                    supported_ops: mask,
                    max_request_payload: request_limit,
                    max_response_payload: response_limit,
                    ..query_profile()
                };
                let expected = if request_limit >= min_request && response_limit >= min_response {
                    Ok(())
                } else {
                    Err(Error::InvalidField)
                };
                assert_query(
                    &golden,
                    value,
                    expected,
                    &format!("mask {mask:#x}, request {request_limit}, response {response_limit}"),
                );
            }
        }
    }
}

#[test]
fn query_abi_advertised_payload_limits_include_exact_maximum() {
    let golden = fixed("query_abi_ok");
    for (mask, min_request, min_response) in QUERY_PROFILES {
        for request_limit in [min_request, 65_536, 65_537, u32::MAX] {
            for response_limit in [min_response, 65_536, 65_537, u32::MAX] {
                let value = QueryAbiResponse {
                    supported_ops: mask,
                    max_request_payload: request_limit,
                    max_response_payload: response_limit,
                    ..query_profile()
                };
                let expected = if request_limit <= 65_536 && response_limit <= 65_536 {
                    Ok(())
                } else {
                    Err(Error::PayloadTooLarge)
                };
                assert_query(
                    &golden,
                    value,
                    expected,
                    &format!("mask {mask:#x}, request {request_limit}, response {response_limit}"),
                );
            }
        }
    }
}

#[test]
fn query_abi_page_sizes_accept_every_nonzero_power_of_two() {
    let golden = fixed("query_abi_ok");
    for shift in 0..32 {
        let power = 1u32 << shift;
        assert_query(
            &golden,
            QueryAbiResponse {
                page_size: power,
                ..query_profile()
            },
            Ok(()),
            &format!("valid page size 2^{shift}"),
        );
        for neighbor in [power - 1, power + 1] {
            if neighbor != 0 && neighbor.is_power_of_two() {
                continue;
            }
            assert_query(
                &golden,
                QueryAbiResponse {
                    page_size: neighbor,
                    ..query_profile()
                },
                Err(Error::InvalidField),
                &format!("invalid page size {neighbor}"),
            );
        }
    }
    assert_query(
        &golden,
        QueryAbiResponse {
            page_size: u32::MAX,
            ..query_profile()
        },
        Err(Error::InvalidField),
        "page size u32::MAX",
    );
}

#[test]
fn read_usage_accepts_zero_full_caps_and_exact_elapsed_consumption() {
    let golden = fixed("read_usage_lowered_cap");
    for cap in [0, 1, CPU_PERIOD_NS] {
        for consumed in [0, 1, 50_000_000] {
            let value = ReadUsageResponse {
                active_cap_ns: cap,
                window_consumed_ns: consumed,
                cumulative_cpu_ns: consumed,
                ..usage_profile()
            };
            // cap=0 with consumed>0 preserves actual usage after lowering.
            // No cap field is allowed to rewrite this independent statistic.
            assert_usage(
                &golden,
                value,
                Ok(()),
                &format!("cap {cap}, consumed {consumed}"),
            );
        }
    }
    for event_sequence in [0, u64::MAX] {
        assert_usage(
            &golden,
            ReadUsageResponse {
                event_sequence,
                dropped_events: event_sequence,
                ..usage_profile()
            },
            Ok(()),
            &format!("event/drop counters both {event_sequence}"),
        );
    }
}

#[test]
fn read_usage_accepts_aligned_windows_through_u64_max() {
    let golden = fixed("read_usage_lowered_cap");
    for sample in [
        0,
        1,
        CPU_PERIOD_NS - 1,
        CPU_PERIOD_NS,
        CPU_PERIOD_NS + 1,
        u64::MAX,
    ] {
        // Compute expected start independently using remainder subtraction.
        let elapsed = sample % CPU_PERIOD_NS;
        let value = ReadUsageResponse {
            sample_boottime_ns: sample,
            cumulative_cpu_ns: elapsed,
            window_start_ns: sample - elapsed,
            window_consumed_ns: elapsed,
            active_cap_ns: 0,
            event_sequence: 0,
            dropped_events: 0,
            ..usage_profile()
        };
        assert_usage(&golden, value, Ok(()), &format!("sample {sample}"));
    }
}

#[test]
fn read_usage_rejects_impossible_or_misaligned_cpu_snapshots() {
    let golden = fixed("read_usage_lowered_cap");
    for (name, value, expected) in [
        (
            "window begins one nanosecond before aligned origin",
            ReadUsageResponse {
                window_start_ns: 99_999_999,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "window begins one nanosecond after aligned origin",
            ReadUsageResponse {
                window_start_ns: 100_000_001,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "window starts after the sample",
            ReadUsageResponse {
                window_start_ns: 150_000_001,
                ..usage_profile()
            },
            Error::IntegerOverflow,
        ),
        (
            "window consumption exceeds elapsed time by one",
            ReadUsageResponse {
                window_consumed_ns: 50_000_001,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "cumulative CPU is smaller than current-window consumption",
            ReadUsageResponse {
                cumulative_cpu_ns: 34_999_999,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "cap exceeds the fixed period",
            ReadUsageResponse {
                active_cap_ns: CPU_PERIOD_NS + 1,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "period is one nanosecond too short",
            ReadUsageResponse {
                active_period_ns: CPU_PERIOD_NS - 1,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "period is one nanosecond too long",
            ReadUsageResponse {
                active_period_ns: CPU_PERIOD_NS + 1,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
        (
            "dropped events exceed the event sequence",
            ReadUsageResponse {
                dropped_events: 78,
                ..usage_profile()
            },
            Error::InvalidField,
        ),
    ] {
        assert_usage(&golden, value, Err(expected), name);
    }
    for sample in [0, CPU_PERIOD_NS, u64::MAX] {
        let elapsed = sample % CPU_PERIOD_NS;
        assert_usage(
            &golden,
            ReadUsageResponse {
                sample_boottime_ns: sample,
                cumulative_cpu_ns: elapsed + 1,
                window_start_ns: sample - elapsed,
                window_consumed_ns: elapsed + 1,
                ..usage_profile()
            },
            Err(Error::InvalidField),
            &format!("sample {sample}, consumed one beyond elapsed"),
        );
    }
}
