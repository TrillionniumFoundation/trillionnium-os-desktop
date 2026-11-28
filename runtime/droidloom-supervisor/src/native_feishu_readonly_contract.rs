//! Bounded comparison data from the normal root-protected working material plan.
//! These values confer no account, UI, document, or completion authority. The
//! live working witness, Main/PM window and actual readonly UI must agree.
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, io};

pub const SCHEMA: &str = "droidloom.feishu-readonly-fixture.v1";
pub const IMAGE_CHANNELS: usize = 16 * 16 * 3;

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FeishuReadonlyFixture {
    pub schema: String,
    pub workspace_name: String,
    pub account_name: String,
    pub unicode_query: String,
    pub document_title: String,
    pub document_result_hint: String,
    pub before_body_markers: Vec<String>,
    pub scrolled_body_markers: Vec<String>,
    /// 16x16 RGB, sampled at cell centres from a declared document image.
    /// A comparison target, never pixels claimed to have been observed.
    pub expected_image_rgb_hex: String,
}

fn invalid() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "Feishu readonly comparison data is outside the fixed bounded contract",
    )
}
fn text(value: &str, min: usize, max: usize) -> bool {
    value.len() >= min
        && value.len() <= max
        && value.trim() == value
        && !value.chars().any(char::is_control)
}
fn markers(values: &[String]) -> bool {
    (2..=6).contains(&values.len())
        && values
            .iter()
            .all(|s| text(s, 8, 384) && s.chars().filter(|c| c.is_alphanumeric()).count() >= 4)
        && values.iter().collect::<BTreeSet<_>>().len() == values.len()
}
impl FeishuReadonlyFixture {
    pub fn validate(&self) -> io::Result<()> {
        if self.schema != SCHEMA
            || !text(&self.workspace_name, 1, 256)
            || !text(&self.account_name, 1, 256)
            || !text(&self.unicode_query, 4, 256)
            || self.unicode_query.is_ascii()
            || !self
                .unicode_query
                .chars()
                .any(|c| !c.is_ascii() && c.is_alphanumeric())
            || !text(&self.document_title, 2, 384)
            || !text(&self.document_result_hint, 2, 384)
            || self.document_title == self.document_result_hint
            || !markers(&self.before_body_markers)
            || !markers(&self.scrolled_body_markers)
            || self.before_body_markers == self.scrolled_body_markers
            || !self
                .scrolled_body_markers
                .iter()
                .any(|value| !self.before_body_markers.contains(value))
        {
            return Err(invalid());
        }
        let rgb = self.image_rgb()?;
        let lo = *rgb.iter().min().ok_or_else(invalid)?;
        let hi = *rgb.iter().max().ok_or_else(invalid)?;
        if hi - lo < 48
            || rgb
                .chunks_exact(3)
                .filter(|p| p.iter().any(|v| *v < 220))
                .count()
                < 8
            || !rgb.chunks_exact(3).any(|p| p.iter().any(|v| *v < 160))
        {
            return Err(invalid());
        }
        Ok(())
    }
    pub fn image_rgb(&self) -> io::Result<[u8; IMAGE_CHANNELS]> {
        let raw = self.expected_image_rgb_hex.as_bytes();
        if raw.len() != IMAGE_CHANNELS * 2
            || !raw
                .iter()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(c))
        {
            return Err(invalid());
        }
        let nibble = |c: u8| if c <= b'9' { c - b'0' } else { c - b'a' + 10 };
        let mut output = [0; IMAGE_CHANNELS];
        for (out, pair) in output.iter_mut().zip(raw.chunks_exact(2)) {
            *out = nibble(pair[0]) * 16 + nibble(pair[1]);
        }
        Ok(output)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> FeishuReadonlyFixture {
        FeishuReadonlyFixture {
            schema: SCHEMA.into(),
            workspace_name: "Declared test workspace".into(),
            account_name: "Declared test account".into(),
            unicode_query: "只读文档 Δ42".into(),
            document_title: "Readonly comparison document".into(),
            document_result_hint: "Declared document owner".into(),
            before_body_markers: vec![
                "First visible paragraph".into(),
                "Second visible paragraph".into(),
            ],
            scrolled_body_markers: vec![
                "Lower visible paragraph".into(),
                "Last visible paragraph".into(),
            ],
            expected_image_rgb_hex: (0..IMAGE_CHANNELS)
                .map(|i| format!("{:02x}", (i % 251) as u8))
                .collect(),
        }
    }
    #[test]
    fn normal_inline_comparison_roundtrips_without_creating_an_observation() {
        let value = fixture();
        value.validate().unwrap();
        let raw = serde_json::to_vec(&value).unwrap();
        assert!(raw.len() < 8192);
        assert_eq!(
            serde_json::from_slice::<FeishuReadonlyFixture>(&raw).unwrap(),
            value
        );
        assert_eq!(value.image_rgb().unwrap().len(), 768);
        for field in [
            "path",
            "uri",
            "argv",
            "selector",
            "authorized",
            "passed",
            "password",
            "production_ready",
        ] {
            let mut json = serde_json::to_value(&value).unwrap();
            json[field] = serde_json::json!(true);
            assert!(serde_json::from_value::<FeishuReadonlyFixture>(json).is_err());
        }
    }
    #[test]
    fn comparison_rejects_empty_ascii_unbounded_duplicate_or_blank_inputs() {
        for case in 0..12 {
            let mut value = fixture();
            match case {
                0 => value.schema.push('x'),
                1 => value.workspace_name.clear(),
                2 => value.account_name.push('\n'),
                3 => value.unicode_query = "ascii only".into(),
                4 => value.unicode_query = "字".repeat(100),
                5 => value.document_result_hint = value.document_title.clone(),
                6 => value.before_body_markers.truncate(1),
                7 => value
                    .before_body_markers
                    .push(value.before_body_markers[0].clone()),
                8 => value.scrolled_body_markers = value.before_body_markers.clone(),
                9 => value.expected_image_rgb_hex = "ff".repeat(IMAGE_CHANNELS),
                10 => value.expected_image_rgb_hex.push('0'),
                _ => value.expected_image_rgb_hex.replace_range(0..1, "G"),
            }
            assert!(value.validate().is_err(), "case {case}");
        }
    }
}
