use std::collections::BTreeMap;
use std::fmt;

use crate::{
    MAX_CONTAINER_ITEMS, MAX_JSON_DEPTH, MAX_JSON_KEY_BYTES, MAX_JSON_STRING_BYTES,
    MAX_MESSAGE_BYTES,
};

pub type JsonObject = BTreeMap<String, JsonValue>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Integer(i64),
    String(String),
    Array(Vec<JsonValue>),
    Object(JsonObject),
}

impl JsonValue {
    pub fn canonical_bytes(&self) -> Result<Vec<u8>, JsonError> {
        let mut encoder = Encoder::new();
        encoder.write_value(self, 0)?;
        if encoder.output.is_empty() {
            return Err(JsonError::MessageSize {
                length: encoder.output.len(),
                maximum: MAX_MESSAGE_BYTES,
            });
        }
        Ok(encoder.output)
    }
}

struct Encoder {
    output: Vec<u8>,
    item_count: usize,
}

impl Encoder {
    fn new() -> Self {
        Self {
            output: Vec::new(),
            item_count: 0,
        }
    }

    fn write_value(&mut self, value: &JsonValue, depth: usize) -> Result<(), JsonError> {
        if depth > MAX_JSON_DEPTH {
            return Err(JsonError::NestingDepth {
                maximum: MAX_JSON_DEPTH,
            });
        }
        match value {
            JsonValue::Null => self.push_bytes(b"null")?,
            JsonValue::Bool(true) => self.push_bytes(b"true")?,
            JsonValue::Bool(false) => self.push_bytes(b"false")?,
            JsonValue::Integer(value) => {
                let encoded = value.to_string();
                self.push_bytes(encoded.as_bytes())?;
            }
            JsonValue::String(value) => self.write_string(value, MAX_JSON_STRING_BYTES)?,
            JsonValue::Array(values) => {
                self.push_byte(b'[')?;
                for (index, value) in values.iter().enumerate() {
                    if index != 0 {
                        self.push_byte(b',')?;
                    }
                    self.note_item()?;
                    self.write_value(value, depth + 1)?;
                }
                self.push_byte(b']')?;
            }
            JsonValue::Object(values) => {
                self.push_byte(b'{')?;
                for (index, (key, value)) in values.iter().enumerate() {
                    if index != 0 {
                        self.push_byte(b',')?;
                    }
                    self.note_item()?;
                    self.write_string(key, MAX_JSON_KEY_BYTES)?;
                    self.push_byte(b':')?;
                    self.write_value(value, depth + 1)?;
                }
                self.push_byte(b'}')?;
            }
        }

        Ok(())
    }

    fn write_string(&mut self, value: &str, maximum: usize) -> Result<(), JsonError> {
        if value.len() > maximum {
            return Err(JsonError::MessageSize {
                length: value.len(),
                maximum,
            });
        }
        self.push_byte(b'"')?;
        for character in value.chars() {
            match character {
                '"' => self.push_bytes(br#"\""#)?,
                '\\' => self.push_bytes(br#"\\"#)?,
                '\u{0008}' => self.push_bytes(br"\b")?,
                '\u{000c}' => self.push_bytes(br"\f")?,
                '\n' => self.push_bytes(br"\n")?,
                '\r' => self.push_bytes(br"\r")?,
                '\t' => self.push_bytes(br"\t")?,
                character if character <= '\u{001f}' => {
                    let escaped = format!("\\u{:04x}", character as u32);
                    self.push_bytes(escaped.as_bytes())?;
                }
                character => {
                    let mut encoded = [0_u8; 4];
                    self.push_bytes(character.encode_utf8(&mut encoded).as_bytes())?;
                }
            }
        }
        self.push_byte(b'"')
    }

    fn note_item(&mut self) -> Result<(), JsonError> {
        self.item_count = self
            .item_count
            .checked_add(1)
            .ok_or(JsonError::ContainerItems {
                maximum: MAX_CONTAINER_ITEMS,
            })?;
        if self.item_count > MAX_CONTAINER_ITEMS {
            return Err(JsonError::ContainerItems {
                maximum: MAX_CONTAINER_ITEMS,
            });
        }
        Ok(())
    }

    fn push_byte(&mut self, byte: u8) -> Result<(), JsonError> {
        self.push_bytes(std::slice::from_ref(&byte))
    }

    fn push_bytes(&mut self, bytes: &[u8]) -> Result<(), JsonError> {
        let length = self.output.len().saturating_add(bytes.len());
        if length > MAX_MESSAGE_BYTES {
            return Err(JsonError::MessageSize {
                length,
                maximum: MAX_MESSAGE_BYTES,
            });
        }
        self.output.extend_from_slice(bytes);
        Ok(())
    }
}

pub fn decode_unique(encoded: &[u8]) -> Result<JsonValue, JsonError> {
    if encoded.is_empty() || encoded.len() > MAX_MESSAGE_BYTES {
        return Err(JsonError::MessageSize {
            length: encoded.len(),
            maximum: MAX_MESSAGE_BYTES,
        });
    }
    if encoded.starts_with(&[0xef, 0xbb, 0xbf]) {
        return Err(JsonError::Utf8Bom);
    }
    std::str::from_utf8(encoded).map_err(|_| JsonError::InvalidUtf8)?;
    let mut parser = Parser::new(encoded);
    parser.skip_whitespace();
    let value = parser.parse_value(0)?;
    parser.skip_whitespace();
    if parser.position != encoded.len() {
        return Err(JsonError::TrailingData);
    }
    Ok(value)
}

struct Parser<'a> {
    input: &'a [u8],
    position: usize,
    item_count: usize,
}

impl<'a> Parser<'a> {
    const fn new(input: &'a [u8]) -> Self {
        Self {
            input,
            position: 0,
            item_count: 0,
        }
    }

    fn parse_value(&mut self, depth: usize) -> Result<JsonValue, JsonError> {
        if depth > MAX_JSON_DEPTH {
            return Err(JsonError::NestingDepth {
                maximum: MAX_JSON_DEPTH,
            });
        }
        self.skip_whitespace();
        match self.peek() {
            Some(b'n') => {
                self.expect_keyword(b"null")?;
                Ok(JsonValue::Null)
            }
            Some(b't') => {
                self.expect_keyword(b"true")?;
                Ok(JsonValue::Bool(true))
            }
            Some(b'f') => {
                self.expect_keyword(b"false")?;
                Ok(JsonValue::Bool(false))
            }
            Some(b'"') => {
                let value = self.parse_string()?;
                if value.len() > MAX_JSON_STRING_BYTES {
                    return Err(JsonError::MessageSize {
                        length: value.len(),
                        maximum: MAX_JSON_STRING_BYTES,
                    });
                }
                Ok(JsonValue::String(value))
            }
            Some(b'[') => self.parse_array(depth),
            Some(b'{') => self.parse_object(depth),
            Some(byte) if byte == b'-' || byte.is_ascii_digit() => self.parse_integer(),
            Some(_) => Err(JsonError::UnexpectedToken(self.position)),
            None => Err(JsonError::UnexpectedEof),
        }
    }

    fn parse_array(&mut self, depth: usize) -> Result<JsonValue, JsonError> {
        self.expect_byte(b'[')?;
        self.skip_whitespace();
        let mut output = Vec::new();
        if self.consume_if(b']') {
            return Ok(JsonValue::Array(output));
        }
        loop {
            self.note_item()?;
            output.push(self.parse_value(depth + 1)?);
            self.skip_whitespace();
            if self.consume_if(b']') {
                break;
            }
            self.expect_byte(b',')?;
            self.skip_whitespace();
        }
        Ok(JsonValue::Array(output))
    }

    fn parse_object(&mut self, depth: usize) -> Result<JsonValue, JsonError> {
        self.expect_byte(b'{')?;
        self.skip_whitespace();
        let mut output = BTreeMap::new();
        if self.consume_if(b'}') {
            return Ok(JsonValue::Object(output));
        }
        loop {
            self.note_item()?;
            if self.peek() != Some(b'"') {
                return Err(JsonError::ObjectKeyExpected(self.position));
            }
            let key = self.parse_string()?;
            if key.len() > MAX_JSON_KEY_BYTES {
                return Err(JsonError::MessageSize {
                    length: key.len(),
                    maximum: MAX_JSON_KEY_BYTES,
                });
            }
            self.skip_whitespace();
            self.expect_byte(b':')?;
            let value = self.parse_value(depth + 1)?;
            if output.insert(key.clone(), value).is_some() {
                return Err(JsonError::DuplicateMember(key));
            }
            self.skip_whitespace();
            if self.consume_if(b'}') {
                break;
            }
            self.expect_byte(b',')?;
            self.skip_whitespace();
        }
        Ok(JsonValue::Object(output))
    }

    fn parse_integer(&mut self) -> Result<JsonValue, JsonError> {
        let start = self.position;
        let negative = self.consume_if(b'-');
        match self.peek() {
            Some(b'0') => {
                self.position += 1;
                if matches!(self.peek(), Some(b'0'..=b'9')) {
                    return Err(JsonError::InvalidNumber(start));
                }
            }
            Some(b'1'..=b'9') => {
                self.position += 1;
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.position += 1;
                }
            }
            _ => return Err(JsonError::InvalidNumber(start)),
        }
        if matches!(self.peek(), Some(b'.' | b'e' | b'E')) {
            return Err(JsonError::FloatingPointForbidden(start));
        }
        let text = std::str::from_utf8(&self.input[start..self.position])
            .map_err(|_| JsonError::InvalidUtf8)?;
        let parsed = text
            .parse::<i128>()
            .map_err(|_| JsonError::IntegerOutOfRange(start))?;
        let value = i64::try_from(parsed).map_err(|_| JsonError::IntegerOutOfRange(start))?;
        if negative && value == 0 {
            return Err(JsonError::NonCanonicalNegativeZero);
        }
        Ok(JsonValue::Integer(value))
    }

    fn parse_string(&mut self) -> Result<String, JsonError> {
        self.expect_byte(b'"')?;
        let mut output = String::new();
        loop {
            let byte = self.peek().ok_or(JsonError::UnexpectedEof)?;
            match byte {
                b'"' => {
                    self.position += 1;
                    return Ok(output);
                }
                b'\\' => {
                    self.position += 1;
                    let escaped = self.peek().ok_or(JsonError::UnexpectedEof)?;
                    self.position += 1;
                    match escaped {
                        b'"' => output.push('"'),
                        b'\\' => output.push('\\'),
                        b'/' => output.push('/'),
                        b'b' => output.push('\u{0008}'),
                        b'f' => output.push('\u{000c}'),
                        b'n' => output.push('\n'),
                        b'r' => output.push('\r'),
                        b't' => output.push('\t'),
                        b'u' => self.push_unicode_escape(&mut output)?,
                        _ => return Err(JsonError::InvalidEscape(self.position - 1)),
                    }
                }
                0x00..=0x1f => return Err(JsonError::ControlCharacter(self.position)),
                0x20..=0x7f => {
                    output.push(byte as char);
                    self.position += 1;
                }
                _ => {
                    let tail = std::str::from_utf8(&self.input[self.position..])
                        .map_err(|_| JsonError::InvalidUtf8)?;
                    let character = tail.chars().next().ok_or(JsonError::UnexpectedEof)?;
                    output.push(character);
                    self.position += character.len_utf8();
                }
            }
        }
    }

    fn push_unicode_escape(&mut self, output: &mut String) -> Result<(), JsonError> {
        let first = self.parse_hex_quad()?;
        let scalar = if (0xd800..=0xdbff).contains(&first) {
            if !self.consume_if(b'\\') || !self.consume_if(b'u') {
                return Err(JsonError::InvalidSurrogate(self.position));
            }
            let second = self.parse_hex_quad()?;
            if !(0xdc00..=0xdfff).contains(&second) {
                return Err(JsonError::InvalidSurrogate(self.position));
            }
            0x1_0000 + (((first - 0xd800) as u32) << 10) + (second - 0xdc00) as u32
        } else if (0xdc00..=0xdfff).contains(&first) {
            return Err(JsonError::InvalidSurrogate(self.position));
        } else {
            first as u32
        };
        let character = char::from_u32(scalar).ok_or(JsonError::InvalidSurrogate(self.position))?;
        output.push(character);
        Ok(())
    }

    fn parse_hex_quad(&mut self) -> Result<u16, JsonError> {
        if self.input.len().saturating_sub(self.position) < 4 {
            return Err(JsonError::UnexpectedEof);
        }
        let mut value = 0_u16;
        for _ in 0..4 {
            let byte = self.peek().ok_or(JsonError::UnexpectedEof)?;
            self.position += 1;
            let digit = match byte {
                b'0'..=b'9' => (byte - b'0') as u16,
                b'a'..=b'f' => (byte - b'a' + 10) as u16,
                b'A'..=b'F' => (byte - b'A' + 10) as u16,
                _ => return Err(JsonError::InvalidUnicodeEscape(self.position - 1)),
            };
            value = value * 16 + digit;
        }
        Ok(value)
    }

    fn expect_keyword(&mut self, keyword: &[u8]) -> Result<(), JsonError> {
        if self.input.get(self.position..self.position + keyword.len()) == Some(keyword) {
            self.position += keyword.len();
            Ok(())
        } else {
            Err(JsonError::UnexpectedToken(self.position))
        }
    }

    fn note_item(&mut self) -> Result<(), JsonError> {
        self.item_count = self
            .item_count
            .checked_add(1)
            .ok_or(JsonError::ContainerItems {
                maximum: MAX_CONTAINER_ITEMS,
            })?;
        if self.item_count > MAX_CONTAINER_ITEMS {
            return Err(JsonError::ContainerItems {
                maximum: MAX_CONTAINER_ITEMS,
            });
        }
        Ok(())
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\n' | b'\r' | b'\t')) {
            self.position += 1;
        }
    }

    fn consume_if(&mut self, expected: u8) -> bool {
        if self.peek() == Some(expected) {
            self.position += 1;
            true
        } else {
            false
        }
    }

    fn expect_byte(&mut self, expected: u8) -> Result<(), JsonError> {
        if self.consume_if(expected) {
            Ok(())
        } else {
            Err(JsonError::ExpectedByte {
                expected,
                position: self.position,
            })
        }
    }

    fn peek(&self) -> Option<u8> {
        self.input.get(self.position).copied()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JsonError {
    MessageSize { length: usize, maximum: usize },
    Utf8Bom,
    InvalidUtf8,
    UnexpectedEof,
    UnexpectedToken(usize),
    TrailingData,
    ExpectedByte { expected: u8, position: usize },
    ObjectKeyExpected(usize),
    DuplicateMember(String),
    InvalidNumber(usize),
    FloatingPointForbidden(usize),
    IntegerOutOfRange(usize),
    NonCanonicalNegativeZero,
    InvalidEscape(usize),
    InvalidUnicodeEscape(usize),
    InvalidSurrogate(usize),
    ControlCharacter(usize),
    NestingDepth { maximum: usize },
    ContainerItems { maximum: usize },
}

impl fmt::Display for JsonError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MessageSize { length, maximum } => {
                write!(
                    formatter,
                    "JSON message length {length} exceeds bound {maximum}"
                )
            }
            Self::Utf8Bom => formatter.write_str("UTF-8 BOM is forbidden"),
            Self::InvalidUtf8 => formatter.write_str("JSON message is not valid UTF-8"),
            Self::UnexpectedEof => formatter.write_str("JSON message ended unexpectedly"),
            Self::UnexpectedToken(position) => {
                write!(formatter, "unexpected JSON token at byte {position}")
            }
            Self::TrailingData => formatter.write_str("JSON message has trailing data"),
            Self::ExpectedByte { expected, position } => write!(
                formatter,
                "expected JSON byte 0x{expected:02x} at byte {position}",
            ),
            Self::ObjectKeyExpected(position) => {
                write!(formatter, "JSON object key expected at byte {position}")
            }
            Self::DuplicateMember(member) => {
                write!(formatter, "duplicate JSON member {member}")
            }
            Self::InvalidNumber(position) => {
                write!(formatter, "invalid JSON integer at byte {position}")
            }
            Self::FloatingPointForbidden(position) => {
                write!(
                    formatter,
                    "floating-point JSON number at byte {position} is forbidden"
                )
            }
            Self::IntegerOutOfRange(position) => {
                write!(formatter, "JSON integer at byte {position} is out of range")
            }
            Self::NonCanonicalNegativeZero => formatter.write_str("negative zero is not canonical"),
            Self::InvalidEscape(position) => {
                write!(formatter, "invalid JSON escape at byte {position}")
            }
            Self::InvalidUnicodeEscape(position) => {
                write!(formatter, "invalid Unicode escape at byte {position}")
            }
            Self::InvalidSurrogate(position) => {
                write!(formatter, "invalid Unicode surrogate at byte {position}")
            }
            Self::ControlCharacter(position) => {
                write!(formatter, "unescaped control character at byte {position}")
            }
            Self::NestingDepth { maximum } => {
                write!(formatter, "JSON nesting exceeds maximum {maximum}")
            }
            Self::ContainerItems { maximum } => {
                write!(
                    formatter,
                    "JSON container item count exceeds maximum {maximum}"
                )
            }
        }
    }
}

impl std::error::Error for JsonError {}
