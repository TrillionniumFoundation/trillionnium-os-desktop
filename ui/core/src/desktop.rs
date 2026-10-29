//! Exact private X11 adapter wire. The identity covers a trusted display domain,
//! not window isolation. Input receipts acknowledge X server injection only.
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

use crate::notes::sha256_hex;

pub const REQUEST_MAX: usize = 8192;
pub const RESPONSE_MAX: usize = 2048;
pub const CAPTURE_MAX: usize = 8 * 1024 * 1024;
pub const MAX_WIDTH: u16 = 1024;
pub const MAX_HEIGHT: u16 = 768;
pub const MAX_EVENTS: usize = 32;
pub const MAX_RECEIPTS: usize = 128;
pub const PROFILE: &str = "trill.desktop.x11.v1";

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopTargetIdentity {
    pub session_instance: String,
    pub incarnation: String,
    pub display_epoch: String,
}

pub fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl DesktopTargetIdentity {
    pub fn validate(&self) -> Result<(), &'static str> {
        if [
            &self.session_instance,
            &self.incarnation,
            &self.display_epoch,
        ]
        .into_iter()
        .all(|s| lower_hex(s, 32))
        {
            Ok(())
        } else {
            Err("desktop identity")
        }
    }
    pub fn destination_id(&self) -> String {
        format!(
            "trill.desktop:{}:{}:{}",
            self.session_instance, self.incarnation, self.display_epoch
        )
    }
    pub fn scope_sha256(&self) -> String {
        sha256_hex(
            format!(
                "trill.desktop.scope.v1\0{}\0{}\0{}",
                self.session_instance, self.incarnation, self.display_epoch
            )
            .as_bytes(),
        )
    }
    pub fn predecessor_sha256(&self, sequence: u64) -> String {
        sha256_hex(
            format!(
                "trill.desktop.predecessor.v1\0{}\0{}\0{}\0{}",
                self.session_instance, self.incarnation, self.display_epoch, sequence
            )
            .as_bytes(),
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum InputEvent {
    PointerMove { x: u16, y: u16 },
    PointerButton { button: u8, pressed: bool },
    Key { keycode: u8, pressed: bool },
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InputAction {
    Input,
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopInput {
    pub schema_version: u16,
    pub action: InputAction,
    pub operation_id: String,
    pub destination_id: String,
    pub target: DesktopTargetIdentity,
    pub expected_sequence: u64,
    pub expected_window: u32,
    pub events: Vec<InputEvent>,
}

pub fn operation_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._:-/".contains(&b))
}

impl DesktopInput {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw, REQUEST_MAX)?;
        value.validate()?;
        Ok(value)
    }
    pub fn validate(&self) -> Result<(), &'static str> {
        self.target.validate()?;
        if self.schema_version != 1
            || self.destination_id != self.target.destination_id()
            || !operation_id(&self.operation_id)
            || self.expected_window == 0
            || self.events.is_empty()
            || self.events.len() > MAX_EVENTS
        {
            return Err("desktop input binding or bound");
        }
        let mut keys = BTreeSet::new();
        let mut buttons = BTreeSet::new();
        for event in &self.events {
            match *event {
                InputEvent::PointerMove { x, y }
                    if x <= i16::MAX as u16 && y <= i16::MAX as u16 => {}
                InputEvent::Key { keycode, pressed } if keycode >= 8 => {
                    if if pressed {
                        !keys.insert(keycode)
                    } else {
                        !keys.remove(&keycode)
                    } {
                        return Err("unbalanced key batch");
                    }
                }
                InputEvent::PointerButton { button, pressed } if (1..=5).contains(&button) => {
                    if if pressed {
                        !buttons.insert(button)
                    } else {
                        !buttons.remove(&button)
                    } {
                        return Err("unbalanced pointer batch");
                    }
                }
                _ => return Err("desktop event bound"),
            }
        }
        if keys.is_empty() && buttons.is_empty() {
            Ok(())
        } else {
            Err("batch leaves input held")
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InputSemantics {
    X11ServerInjected,
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NotInjectedReason {
    TargetMismatch,
    SequenceConflict,
    OperationConflict,
    ReceiptCapacity,
    WindowUnavailable,
    FocusMismatch,
    PointerOutside,
    InputAlreadyHeld,
    SequenceExhausted,
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum InputResult {
    Injected {
        effect_semantics: InputSemantics,
        previous_sequence: u64,
        sequence: u64,
    },
    NotInjected {
        reason: NotInjectedReason,
        current_sequence: u64,
    },
    Unknown {
        current_sequence: u64,
    },
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopReceipt {
    pub schema_version: u16,
    pub target: DesktopTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub result: InputResult,
}

impl DesktopReceipt {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw, RESPONSE_MAX)?;
        value.target.validate()?;
        if value.schema_version != 1
            || !operation_id(&value.operation_id)
            || !lower_hex(&value.payload_sha256, 64)
        {
            return Err("desktop receipt binding");
        }
        if let InputResult::Injected {
            previous_sequence,
            sequence,
            ..
        } = value.result
        {
            if previous_sequence.checked_add(1) != Some(sequence) {
                return Err("desktop receipt sequence");
            }
        }
        Ok(value)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(tag = "action", rename_all = "snake_case", deny_unknown_fields)]
pub enum DesktopObservationRequest {
    Observe {
        schema_version: u16,
        target: DesktopTargetIdentity,
        operation_id: String,
        payload_sha256: String,
    },
    Capture {
        schema_version: u16,
        target: DesktopTargetIdentity,
        request_id: String,
    },
}
impl DesktopObservationRequest {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw, REQUEST_MAX)?;
        match &value {
            Self::Observe {
                schema_version,
                target,
                operation_id: id,
                payload_sha256,
            } => {
                target.validate()?;
                if *schema_version != 1 || !operation_id(id) || !lower_hex(payload_sha256, 64) {
                    return Err("desktop observation binding");
                }
            }
            Self::Capture {
                schema_version,
                target,
                request_id,
            } => {
                target.validate()?;
                if *schema_version != 1 || !lower_hex(request_id, 32) {
                    return Err("desktop capture binding");
                }
            }
        }
        Ok(value)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopCapture {
    pub schema_version: u16,
    pub action: String,
    pub target: DesktopTargetIdentity,
    pub request_id: String,
    pub input_sequence: u64,
    pub window_id: u32,
    pub width: u16,
    pub height: u16,
    pub pixel_format: String,
    pub pixels_hex: String,
    pub sha256: String,
}
impl DesktopCapture {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let value: Self = parse(raw, CAPTURE_MAX)?;
        value.target.validate()?;
        if value.schema_version != 1
            || value.action != "capture"
            || !lower_hex(&value.request_id, 32)
            || value.window_id == 0
            || value.width == 0
            || value.height == 0
            || value.width > MAX_WIDTH
            || value.height > MAX_HEIGHT
            || value.pixel_format != "rgb8"
            || !lower_hex(
                &value.pixels_hex,
                usize::from(value.width) * usize::from(value.height) * 6,
            )
            || !lower_hex(&value.sha256, 64)
        {
            return Err("desktop capture bounds");
        }
        let bytes = decode_hex(&value.pixels_hex)?;
        if sha256_hex(&bytes) != value.sha256 {
            return Err("desktop capture digest");
        }
        Ok(value)
    }
}
pub fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        output.push(HEX[usize::from(b >> 4)] as char);
        output.push(HEX[usize::from(b & 15)] as char);
    }
    output
}
pub fn decode_hex(value: &str) -> Result<Vec<u8>, &'static str> {
    if value.len() % 2 != 0 || !lower_hex(value, value.len()) {
        return Err("invalid hex");
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|b| {
            u8::from_str_radix(std::str::from_utf8(b).map_err(|_| "invalid hex")?, 16)
                .map_err(|_| "invalid hex")
        })
        .collect()
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopBootstrapOffer {
    pub schema_version: u16,
    pub profile: String,
    pub target: DesktopTargetIdentity,
    pub destination_id: String,
    pub scope_sha256: String,
    pub expected_window: u32,
    pub screen_width: u16,
    pub screen_height: u16,
}
impl DesktopBootstrapOffer {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let v: Self = parse(raw, RESPONSE_MAX)?;
        v.target.validate()?;
        if v.schema_version != 1
            || v.profile != PROFILE
            || v.destination_id != v.target.destination_id()
            || v.scope_sha256 != v.target.scope_sha256()
            || v.expected_window == 0
            || v.screen_width == 0
            || v.screen_height == 0
            || v.screen_width > i16::MAX as u16
            || v.screen_height > i16::MAX as u16
        {
            return Err("desktop bootstrap binding");
        }
        Ok(v)
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DesktopBootstrapStatus {
    Attached,
    Rejected,
}
#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DesktopBootstrapAck {
    pub schema_version: u16,
    pub profile: String,
    pub target: DesktopTargetIdentity,
    pub status: DesktopBootstrapStatus,
}
impl DesktopBootstrapAck {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, &'static str> {
        let v: Self = parse(raw, RESPONSE_MAX)?;
        v.target.validate()?;
        if v.schema_version != 1 || v.profile != PROFILE {
            return Err("desktop ACK profile");
        }
        Ok(v)
    }
}
fn parse<T: serde::de::DeserializeOwned>(raw: &[u8], max: usize) -> Result<T, &'static str> {
    if raw.is_empty() || raw.len() > max {
        return Err("desktop frame bound");
    }
    serde_json::from_slice(raw).map_err(|_| "desktop schema")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wire_golden_uses_actual_parsers_and_hashes() {
        let g: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/ui/desktop-x11-v1.json")).unwrap();
        let raw = g["input_raw"].as_str().unwrap();
        let input = DesktopInput::parse_exact(raw.as_bytes()).unwrap();
        assert_eq!(input.target.scope_sha256(), g["scope_sha256"]);
        assert_eq!(input.target.predecessor_sha256(0), g["predecessor_sha256"]);
        let receipt_raw = g["receipt_raw"].as_str().unwrap();
        let receipt = DesktopReceipt::parse_exact(receipt_raw.as_bytes()).unwrap();
        assert_eq!(receipt.payload_sha256, sha256_hex(raw.as_bytes()));
        assert_eq!(sha256_hex(receipt_raw.as_bytes()), g["receipt_sha256"]);
        let offer = DesktopBootstrapOffer::parse_exact(g["offer_raw"].as_str().unwrap().as_bytes())
            .unwrap();
        let ack =
            DesktopBootstrapAck::parse_exact(g["ack_raw"].as_str().unwrap().as_bytes()).unwrap();
        assert_eq!(offer.target, ack.target);
        for field in ["observe_raw", "capture_request_raw"] {
            DesktopObservationRequest::parse_exact(g[field].as_str().unwrap().as_bytes()).unwrap();
        }
        DesktopCapture::parse_exact(g["capture_raw"].as_str().unwrap().as_bytes()).unwrap();
        let reencoded = serde_json::to_vec(&input).unwrap();
        assert_eq!(DesktopInput::parse_exact(&reencoded).unwrap(), input);
    }
    #[test]
    fn rejects_unbalanced_unknown_duplicate_and_oversized_input() {
        let g: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/ui/desktop-x11-v1.json")).unwrap();
        let raw = g["input_raw"].as_str().unwrap();
        let mut value = DesktopInput::parse_exact(raw.as_bytes()).unwrap();
        value.events = vec![InputEvent::Key {
            keycode: 38,
            pressed: true,
        }];
        assert!(value.validate().is_err());
        assert!(DesktopInput::parse_exact(
            raw.replace(
                "\"schema_version\":1",
                "\"schema_version\":1,\"schema_version\":1"
            )
            .as_bytes()
        )
        .is_err());
        assert!(DesktopInput::parse_exact(
            raw.replace(
                "\"schema_version\":1",
                "\"schema_version\":1,\"shell\":\"command\""
            )
            .as_bytes()
        )
        .is_err());
        assert!(DesktopInput::parse_exact(&vec![b' '; REQUEST_MAX + 1]).is_err());
    }
}
