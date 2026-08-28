use std::collections::BTreeMap;

use super::*;

const GOLDEN_HEALTH: &[u8] =
    include_bytes!("../../../contracts/golden/golden-health-1.wire.json");
const GOLDEN_CREATE: &[u8] =
    include_bytes!("../../../contracts/golden/golden-create-1.wire.json");
const GOLDEN_NAVIGATE: &[u8] =
    include_bytes!("../../../contracts/golden/golden-navigate-1.wire.json");
const GOLDEN_CLICK: &[u8] =
    include_bytes!("../../../contracts/golden/golden-click-1.wire.json");
const GOLDEN_RESPONSE_OK: &[u8] =
    include_bytes!("../../../contracts/golden/golden-response-ok-1.wire.json");
const GOLDEN_RESPONSE_ERROR: &[u8] =
    include_bytes!("../../../contracts/golden/golden-response-error-1.wire.json");

#[test]
fn canonical_golden_requests_round_trip_byte_exactly() {
    for encoded in [GOLDEN_HEALTH, GOLDEN_CREATE, GOLDEN_NAVIGATE, GOLDEN_CLICK] {
        let decoded = decode_request(encoded).expect("golden request must decode");
        assert_eq!(encode_request(&decoded.value).unwrap(), encoded);
        assert_eq!(decoded.canonical_sha256.len(), 64);
    }
}

#[test]
fn canonical_golden_responses_round_trip_byte_exactly() {
    for encoded in [GOLDEN_RESPONSE_OK, GOLDEN_RESPONSE_ERROR] {
        let decoded = decode_response(encoded).expect("golden response must decode");
        assert_eq!(encode_response(&decoded.value).unwrap(), encoded);
        assert_eq!(decoded.canonical_sha256.len(), 64);
    }
}

#[test]
fn navigation_and_click_are_potential_external_effects() {
    assert_eq!(
        decode_request(GOLDEN_NAVIGATE).unwrap().value.effect_class(),
        EffectClass::PotentialExternalEffect
    );
    assert_eq!(
        decode_request(GOLDEN_CLICK).unwrap().value.effect_class(),
        EffectClass::PotentialExternalEffect
    );
}

#[test]
fn noncanonical_whitespace_is_rejected() {
    let mut encoded = b" ".to_vec();
    encoded.extend_from_slice(GOLDEN_HEALTH);
    assert!(matches!(
        decode_request(&encoded),
        Err(CodecError::NonCanonicalEncoding)
    ));
}

#[test]
fn duplicate_members_are_rejected_recursively() {
    let encoded = br#"{"operation":{"type":"health","type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"duplicate:1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::Json(JsonError::DuplicateMember(_)))
    ));
}

#[test]
fn booleans_are_not_integers() {
    let encoded = br#"{"operation":{"type":"session_snapshot"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"bool:1","session_generation":true,"session_id":"session-1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::InvalidInteger("session_generation"))
    ));
}

#[test]
fn floating_point_values_are_forbidden_before_typed_dispatch() {
    let encoded = br#"{"operation":{"type":"session_snapshot"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"float:1","session_generation":1.0,"session_id":"session-1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::Json(JsonError::FloatingPointForbidden(_)))
    ));
}

#[test]
fn bound_operations_require_paired_session_identity() {
    let encoded = br#"{"operation":{"type":"session_snapshot"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"binding:1","session_id":"session-1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::SessionBinding(_))
    ));
}

#[test]
fn semantic_reference_requires_a_published_snapshot() {
    let encoded = br#"{"operation":{"action":{"type":"click"},"target":{"document_generation":1,"frame_id":"main","semantic_snapshot_revision":0,"session_generation":1,"structural_fingerprint":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"type":"page_act"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"stale:1","session_generation":1,"session_id":"session-1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::InvalidInteger(
            "reference semantic_snapshot_revision"
        ))
    ));
}

#[test]
fn unsafe_external_url_userinfo_is_rejected() {
    let encoded = br#"{"operation":{"expected_document_generation":1,"target":{"type":"external_https","url":"https://user@example.test/"},"type":"page_navigate"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"url:1","session_generation":1,"session_id":"session-1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::InvalidUrl(_))
    ));
}

#[test]
fn fixture_url_is_loopback_only() {
    let encoded = br#"{"operation":{"expected_document_generation":1,"target":{"type":"local_http_fixture","url":"http://192.168.1.1/"},"type":"page_navigate"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"fixture:1","session_generation":1,"session_id":"session-1"}"#;
    assert!(matches!(
        decode_request(encoded),
        Err(CodecError::InvalidUrl(_))
    ));
}

#[test]
fn error_retry_policy_is_code_bound() {
    let encoded = br#"{"error":{"code":"indeterminate","message":"unknown after disconnect","retry":"caller_decides"},"ok":false,"protocol":"trillionnium.desktop.browser-api.v1","request_id":"error:1"}"#;
    assert!(matches!(
        decode_response(encoded),
        Err(CodecError::InvalidError(_))
    ));
}

#[test]
fn response_handler_cannot_emit_non_object_success_result() {
    let encoded = br#"{"ok":true,"protocol":"trillionnium.desktop.browser-api.v1","request_id":"result:1","result":true}"#;
    assert!(matches!(
        decode_response(encoded),
        Err(CodecError::InvalidResponseShape)
    ));
}

#[test]
fn encoder_sorts_object_keys_recursively() {
    let response = BrowserResponse::success(
        "sort:1".to_owned(),
        None,
        None,
        BTreeMap::from([
            ("z".to_owned(), JsonValue::Integer(2)),
            ("a".to_owned(), JsonValue::Integer(1)),
        ]),
    )
    .unwrap();
    let encoded = String::from_utf8(encode_response(&response).unwrap()).unwrap();
    assert!(encoded.contains(r#""result":{"a":1,"z":2}"#));
}

#[test]
fn full_self_check_passes() {
    self_check().unwrap();
}
