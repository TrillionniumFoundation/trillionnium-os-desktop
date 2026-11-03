//! The same public-type cases run against the original source/lock during
//! compatibility review. Host load is observation data, never task authority.
use trill_ui_core::HostResources;

fn load_bits(value: Option<&str>) -> Result<Option<u32>, serde_json::Error> {
    let field = value
        .map(|value| format!(",\"load_average_1m\":{value}"))
        .unwrap_or_default();
    let json = format!(
        "{{\"sampled_unix_ms\":3,\"mem_total_kib\":null,\"mem_available_kib\":null,\"source\":\"compatibility\"{field}}}"
    );
    serde_json::from_str::<HostResources>(&json)
        .map(|resources| resources.load_average_1m.map(f32::to_bits))
}

#[test]
fn legacy_load_rounding_and_finite_boundaries_are_preserved() {
    for (number, bits) in [
        ("0", 0x0000_0000),
        ("-0.0", 0x8000_0000),
        ("0.1", 0x3dcc_cccd),
        ("1", 0x3f80_0000),
        ("42", 0x4228_0000),
        ("1e-100", 0x0000_0000),
        ("-1e-100", 0x8000_0000),
        ("1.401298464324817e-45", 0x0000_0001),
        ("3.4028234663852886e38", 0x7f7f_ffff),
        ("1.000000059604644775390625", 0x3f80_0000),
        ("1.000000059604644775390626", 0x3f80_0000),
    ] {
        assert_eq!(load_bits(Some(number)).unwrap(), Some(bits), "{number}");
    }
}

#[test]
fn integer_negative_zero_remains_zero_across_json_feature_sets() {
    // serde_json/arbitrary_precision normalizes the integer token -0 before
    // invoking a field visitor. The original wire serializer writes -0.0 for
    // negative f32 zero; that spelling retains its exact bits above.
    assert_eq!(load_bits(Some("-0")).unwrap().unwrap() & 0x7fff_ffff, 0);
}

#[test]
fn legacy_load_f32_overflow_keeps_the_original_accepted_observation() {
    for (number, bits) in [
        ("3.4028236e38", 0x7f80_0000),
        ("-3.4028236e38", 0xff80_0000),
        ("1e100", 0x7f80_0000),
        ("-1e100", 0xff80_0000),
    ] {
        assert_eq!(load_bits(Some(number)).unwrap(), Some(bits), "{number}");
    }
}

#[test]
fn legacy_load_missing_and_null_remain_optional() {
    assert_eq!(load_bits(None).unwrap(), None);
    assert_eq!(load_bits(Some("null")).unwrap(), None);
}

#[test]
fn legacy_load_non_numeric_or_json_overflow_remain_rejected() {
    for value in [
        "true", "false", "\"0.1\"", "[]", "{}", "1e400", "-1e400", "NaN",
    ] {
        assert!(load_bits(Some(value)).is_err(), "{value}");
    }
}

#[test]
fn native_graph_numeric_observation_roundtrips_through_value() {
    let json = r#"{"sampled_unix_ms":3,"mem_total_kib":null,"mem_available_kib":null,"source":"real snapshot","load_average_1m":0.43}"#;
    let resources: HostResources = serde_json::from_str(json).unwrap();
    let restored: HostResources =
        serde_json::from_value(serde_json::to_value(&resources).unwrap()).unwrap();
    assert_eq!(
        restored.load_average_1m.map(f32::to_bits),
        resources.load_average_1m.map(f32::to_bits)
    );
    let snapshot = format!(
        r#"{{"type":"snapshot","tasks":[],"resources":{json},"session_instance":"original"}}"#
    );
    let response: trill_ui_core::Response = serde_json::from_str(&snapshot).unwrap();
    let trill_ui_core::Response::Snapshot {
        resources: restored,
        ..
    } = response
    else {
        panic!("original snapshot variant changed");
    };
    assert_eq!(
        restored.load_average_1m.map(f32::to_bits),
        resources.load_average_1m.map(f32::to_bits)
    );
}

#[test]
fn legacy_load_large_unsigned_integer_is_not_double_rounded() {
    assert_eq!(
        load_bits(Some("9223372586610589697")).unwrap(),
        Some(0x5f00_0001)
    );
}

#[test]
fn legacy_load_large_signed_integer_is_not_double_rounded() {
    assert_eq!(
        load_bits(Some("-4611686293305294849")).unwrap(),
        Some(0xde80_0001)
    );
}
