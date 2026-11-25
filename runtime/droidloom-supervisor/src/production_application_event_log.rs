//! Decode only the stock CP3A logger_entry/event-list wire used by the bounded
//! lifecycle sample. Text-mode liblog probes the separately restricted dynamic
//! /dev/event-log-tags map. Binary mode avoids that probe; the normal publisher
//! verifies the immutable system event-map body that defines these seven tags.
use super::*;
use crate::production_execution_profile::query_inputs::LIFECYCLE_EVENT_TAGS;

pub(super) const RECORD_LIMIT: usize = 2000;
pub(super) const RECORD_BYTES: usize = 5 * 1024;
pub(super) const OUTPUT_BYTES: usize = RECORD_LIMIT * RECORD_BYTES;
const HEADER_BYTES: usize = 28;

fn take<'a>(bytes: &mut &'a [u8], count: usize) -> Result<&'a [u8]> {
    let value = bytes
        .get(..count)
        .ok_or_else(|| reject("incomplete fixed binary event record"))?;
    *bytes = &bytes[count..];
    Ok(value)
}
fn word(bytes: &mut &[u8]) -> Result<u32> {
    Ok(u32::from_le_bytes(take(bytes, 4)?.try_into().unwrap()))
}
fn string_field(text: &str) -> String {
    let mut value = String::new();
    for c in text.chars() {
        if c.is_control() || matches!(c, ',' | '[' | ']' | '\\') {
            use std::fmt::Write;
            let _ = write!(value, "\\u{{{:x}}}", u32::from(c));
        } else {
            value.push(c);
        }
    }
    value
}
fn field(bytes: &mut &[u8], kind: u8) -> Result<String> {
    let wire = take(bytes, 1)?[0];
    match (kind, wire) {
        (b'i', 0) => Ok((word(bytes)? as i32).to_string()),
        (b'l', 1) => Ok(i64::from_le_bytes(take(bytes, 8)?.try_into().unwrap()).to_string()),
        (b's', 2) => {
            let count = usize::try_from(word(bytes)?).map_err(external)?;
            let text = std::str::from_utf8(take(bytes, count)?).map_err(external)?;
            Ok(string_field(text))
        }
        _ => Err(reject(
            "lifecycle event field differs from its fixed source schema",
        )),
    }
}

pub(super) fn decode(bytes: &[u8]) -> Result<String> {
    require(
        bytes.len() <= OUTPUT_BYTES,
        "binary event snapshot exceeds its complete-output bound",
    )?;
    let mut remaining = bytes;
    let mut count = 0;
    let mut output = Vec::new();
    while !remaining.is_empty() {
        count += 1;
        require(
            count <= RECORD_LIMIT,
            "binary event snapshot exceeds the fixed record count",
        )?;
        let header = take(&mut remaining, HEADER_BYTES)?;
        let length = usize::from(u16::from_le_bytes(header[..2].try_into().unwrap()));
        require(
            usize::from(u16::from_le_bytes(header[2..4].try_into().unwrap())) == HEADER_BYTES
                && (5..=RECORD_BYTES - HEADER_BYTES).contains(&length),
            "binary event header or payload length differs from stock CP3A",
        )?;
        let mut words = &header[4..];
        let pid = word(&mut words)? as i32;
        let tid = word(&mut words)?;
        let sec = word(&mut words)?;
        let nsec = word(&mut words)?;
        let lid = word(&mut words)?;
        let uid = word(&mut words)?;
        require(
            pid > 0
                && tid > 0
                && tid <= i32::MAX as u32
                && nsec < 1_000_000_000
                && lid == 2
                && uid <= i32::MAX as u32,
            "binary event process, clock or buffer identity is invalid",
        )?;
        let mut payload = take(&mut remaining, length)?;
        let id = word(&mut payload)?;
        let Some(tag) = LIFECYCLE_EVENT_TAGS.iter().find(|tag| tag.id == id) else {
            // This report explicitly samples only the seven known lifecycle
            // event tags. Unknown tags are never reinterpreted by their text.
            continue;
        };
        require(
            take(&mut payload, 1)?[0] == 3
                && usize::from(take(&mut payload, 1)?[0]) == tag.kinds.len(),
            "lifecycle event is not its fixed flat typed list",
        )?;
        let mut values = Vec::with_capacity(tag.kinds.len());
        for kind in tag.kinds {
            values.push(field(&mut payload, *kind)?);
        }
        require(
            payload.is_empty(),
            "lifecycle event has trailing untyped data",
        )?;
        let line = format!(
            "unix={sec}.{nsec:09} pid={pid} tid={tid} uid={uid} I {}: [{}]\n",
            tag.name,
            values.join(",")
        );
        output.extend_from_slice(line.as_bytes());
        if output.len() > super::diagnostics::TAIL_BYTES + 1 {
            output.drain(..output.len() - (super::diagnostics::TAIL_BYTES + 1));
        }
    }
    Ok(super::diagnostics::tail_text(
        &output,
        super::diagnostics::TAIL_BYTES,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn record(id: u32, kinds: &[u8], name: &str) -> Vec<u8> {
        let mut payload = id.to_le_bytes().to_vec();
        payload.extend([3, kinds.len() as u8]);
        for kind in kinds {
            match kind {
                b'i' => {
                    payload.push(0);
                    payload.extend(123_i32.to_le_bytes());
                }
                b'l' => {
                    payload.push(1);
                    payload.extend((-456_i64).to_le_bytes());
                }
                b's' => {
                    payload.push(2);
                    payload.extend((name.len() as u32).to_le_bytes());
                    payload.extend(name.as_bytes());
                }
                _ => unreachable!(),
            }
        }
        let mut bytes = (payload.len() as u16).to_le_bytes().to_vec();
        bytes.extend((HEADER_BYTES as u16).to_le_bytes());
        for value in [111_u32, 112, 1_795_000_000, 123_000_000, 2, 1000] {
            bytes.extend(value.to_le_bytes());
        }
        bytes.extend(payload);
        bytes
    }
    #[test]
    fn diagnostics_binary_events_preserve_only_fixed_typed_records_and_actual_clock() {
        let mut bytes = Vec::new();
        for tag in LIFECYCLE_EVENT_TAGS {
            bytes.extend(record(tag.id, tag.kinds, "org.example.app"));
        }
        bytes.extend(record(999999, b"s", "am_crash: [org.example.app]"));
        let text = decode(&bytes).unwrap();
        assert_eq!(text.lines().count(), LIFECYCLE_EVENT_TAGS.len());
        assert!(text.contains("unix=1795000000.123000000 pid=111 tid=112 uid=1000"));
        for tag in LIFECYCLE_EVENT_TAGS {
            assert_eq!(text.matches(&format!(" I {}: [", tag.name)).count(), 1);
        }
        assert!(text.contains("-456"));
        assert!(!text.contains("999999"));
        assert_eq!(decode(&[]).unwrap(), "");
    }
    #[test]
    fn diagnostics_binary_events_reject_partial_wrong_buffer_schema_and_excess_records() {
        let valid = record(30010, b"iis", "org.example.app");
        for end in 1..valid.len() {
            assert!(
                decode(&valid[..end]).is_err(),
                "accepted incomplete record {end}"
            );
        }
        for (index, value) in [(2, 24), (20, 3), (32, 0), (33, 2), (34, 2)] {
            let mut bad = valid.clone();
            bad[index] = value;
            assert!(decode(&bad).is_err(), "accepted invalid field at {index}");
        }
        let mut bad = valid.clone();
        bad[16..20].copy_from_slice(&1_000_000_000_u32.to_le_bytes());
        assert!(decode(&bad).is_err());
        let mut bad = valid.clone();
        bad.push(0);
        let length = u16::from_le_bytes(bad[..2].try_into().unwrap()) + 1;
        bad[..2].copy_from_slice(&length.to_le_bytes());
        assert!(decode(&bad).is_err());
        assert!(decode(&valid.repeat(RECORD_LIMIT + 1)).is_err());
    }
    #[test]
    fn diagnostics_binary_event_strings_cannot_forge_fields_or_add_lines() {
        let text = decode(&record(
            30010,
            b"iis",
            "org.example.app,other]\nI am_crash: [",
        ))
        .unwrap();
        assert_eq!(text.lines().count(), 1);
        assert!(text.contains("org.example.app\\u{2c}other\\u{5d}\\u{a}"));
        assert_eq!(text.matches(",").count(), 2);
        assert_eq!(text.matches("]").count(), 1);
        assert_eq!(text.matches("[").count(), 1);
    }
}
