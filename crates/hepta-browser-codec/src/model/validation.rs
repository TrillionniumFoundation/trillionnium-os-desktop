struct ObjectCursor {
    label: &'static str,
    fields: JsonObject,
}

impl ObjectCursor {
    fn new(value: JsonValue, label: &'static str) -> Result<Self, CodecError> {
        match value {
            JsonValue::Object(fields) => Ok(Self { label, fields }),
            _ => Err(CodecError::ExpectedType(label)),
        }
    }

    fn take(&mut self, field: &'static str) -> Result<JsonValue, CodecError> {
        self.fields
            .remove(field)
            .ok_or(CodecError::MissingField(field))
    }

    fn take_optional(&mut self, field: &'static str) -> Option<JsonValue> {
        self.fields.remove(field)
    }

    fn take_string(&mut self, field: &'static str) -> Result<String, CodecError> {
        expect_string(self.take(field)?, field)
    }

    fn take_optional_string(
        &mut self,
        field: &'static str,
    ) -> Result<Option<String>, CodecError> {
        self.take_optional(field)
            .map(|value| expect_string(value, field))
            .transpose()
    }

    fn take_u64(&mut self, field: &'static str) -> Result<u64, CodecError> {
        expect_u64(self.take(field)?, field)
    }

    fn take_optional_u64(&mut self, field: &'static str) -> Result<Option<u64>, CodecError> {
        self.take_optional(field)
            .map(|value| expect_u64(value, field))
            .transpose()
    }

    fn take_i64(&mut self, field: &'static str) -> Result<i64, CodecError> {
        match self.take(field)? {
            JsonValue::Integer(value) => Ok(value),
            _ => Err(CodecError::ExpectedType(field)),
        }
    }

    fn take_bool(&mut self, field: &'static str) -> Result<bool, CodecError> {
        match self.take(field)? {
            JsonValue::Bool(value) => Ok(value),
            _ => Err(CodecError::ExpectedType(field)),
        }
    }

    fn take_array(&mut self, field: &'static str) -> Result<Vec<JsonValue>, CodecError> {
        match self.take(field)? {
            JsonValue::Array(values) => Ok(values),
            _ => Err(CodecError::ExpectedType(field)),
        }
    }

    fn finish(self) -> Result<(), CodecError> {
        if self.fields.is_empty() {
            Ok(())
        } else {
            Err(CodecError::UnknownFields {
                object: self.label,
                fields: self.fields.into_keys().collect(),
            })
        }
    }
}

fn expect_string(value: JsonValue, field: &'static str) -> Result<String, CodecError> {
    match value {
        JsonValue::String(value) => Ok(value),
        _ => Err(CodecError::ExpectedType(field)),
    }
}

fn expect_u64(value: JsonValue, field: &'static str) -> Result<u64, CodecError> {
    match value {
        JsonValue::Integer(value) if value >= 0 => {
            u64::try_from(value).map_err(|_| CodecError::InvalidInteger(field))
        }
        _ => Err(CodecError::InvalidInteger(field)),
    }
}

fn insert_type(object: &mut JsonObject, kind: &'static str) {
    object.insert("type".to_owned(), JsonValue::String(kind.to_owned()));
}

fn integer_from_u64(value: u64, field: &'static str) -> Result<i64, CodecError> {
    i64::try_from(value).map_err(|_| CodecError::InvalidInteger(field))
}

fn validate_identifier(
    field: &'static str,
    value: &str,
    maximum: usize,
) -> Result<(), CodecError> {
    validate_text(field, value, 1, maximum)?;
    if value.bytes().all(|byte| {
        byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-')
    }) {
        Ok(())
    } else {
        Err(CodecError::InvalidIdentifier(field))
    }
}

fn validate_dns_label(field: &'static str, value: &str) -> Result<(), CodecError> {
    validate_text(field, value, 1, 63)?;
    let bytes = value.as_bytes();
    if !bytes[0].is_ascii_lowercase() && !bytes[0].is_ascii_digit() {
        return Err(CodecError::InvalidIdentifier(field));
    }
    if !bytes[bytes.len() - 1].is_ascii_lowercase()
        && !bytes[bytes.len() - 1].is_ascii_digit()
    {
        return Err(CodecError::InvalidIdentifier(field));
    }
    if bytes.iter().all(|byte| {
        byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'-'
    }) {
        Ok(())
    } else {
        Err(CodecError::InvalidIdentifier(field))
    }
}

fn validate_sha256(field: &'static str, value: &str) -> Result<(), CodecError> {
    if value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(CodecError::InvalidSha256(field))
    }
}

fn validate_text(
    field: &'static str,
    value: &str,
    minimum: usize,
    maximum: usize,
) -> Result<(), CodecError> {
    let length = value.len();
    if length < minimum || length > maximum || value.contains('\0') {
        Err(CodecError::InvalidText {
            field,
            length,
            minimum,
            maximum,
        })
    } else {
        Ok(())
    }
}

fn require_nonzero(value: u64, field: &'static str) -> Result<(), CodecError> {
    if value == 0 {
        Err(CodecError::InvalidInteger(field))
    } else {
        Ok(())
    }
}

fn require_range(
    value: u64,
    minimum: u64,
    maximum: u64,
    field: &'static str,
) -> Result<(), CodecError> {
    if (minimum..=maximum).contains(&value) {
        Ok(())
    } else {
        Err(CodecError::InvalidInteger(field))
    }
}

fn require_signed_range(
    value: i64,
    minimum: i64,
    maximum: i64,
    field: &'static str,
) -> Result<(), CodecError> {
    if (minimum..=maximum).contains(&value) {
        Ok(())
    } else {
        Err(CodecError::InvalidInteger(field))
    }
}

#[derive(Debug, Clone, Copy)]
enum UrlPolicy {
    ExternalHttps,
    LoopbackHttp,
}

fn validate_url(value: &str, policy: UrlPolicy) -> Result<(), CodecError> {
    validate_text("url", value, 1, MAX_URL_BYTES)?;
    if value
        .chars()
        .any(|character| character <= '\u{001f}' || character == '\u{007f}')
    {
        return Err(CodecError::InvalidUrl("URL contains a control character"));
    }
    let (expected_scheme, remainder) = match policy {
        UrlPolicy::ExternalHttps => ("https", value.strip_prefix("https://")),
        UrlPolicy::LoopbackHttp => ("http", value.strip_prefix("http://")),
    };
    let remainder = remainder.ok_or(CodecError::InvalidUrl(match expected_scheme {
        "https" => "external URL must use https",
        _ => "fixture URL must use http",
    }))?;
    let authority_end = remainder
        .find(|character: char| matches!(character, '/' | '?' | '#'))
        .unwrap_or(remainder.len());
    let authority = &remainder[..authority_end];
    if authority.is_empty() || authority.contains('@') || authority.contains('\\') {
        return Err(CodecError::InvalidUrl("URL authority is invalid"));
    }
    let host = parse_authority_host(authority)?;
    if matches!(policy, UrlPolicy::LoopbackHttp)
        && !matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1")
    {
        return Err(CodecError::InvalidUrl(
            "fixture URL must target localhost, 127.0.0.1, or ::1",
        ));
    }
    Ok(())
}

fn parse_authority_host(authority: &str) -> Result<String, CodecError> {
    if let Some(rest) = authority.strip_prefix('[') {
        let close = rest
            .find(']')
            .ok_or(CodecError::InvalidUrl("unterminated IPv6 host"))?;
        let host = &rest[..close];
        Ipv6Addr::from_str(host).map_err(|_| CodecError::InvalidUrl("invalid IPv6 host"))?;
        validate_port_suffix(&rest[close + 1..])?;
        return Ok(host.to_ascii_lowercase());
    }
    if authority.matches(':').count() > 1 {
        return Err(CodecError::InvalidUrl("IPv6 host must use brackets"));
    }
    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port)) => (host, Some(port)),
        None => (authority, None),
    };
    if host.is_empty()
        || host
            .chars()
            .any(|character| character.is_whitespace() || matches!(character, '/' | '?' | '#'))
    {
        return Err(CodecError::InvalidUrl("URL host is invalid"));
    }
    if let Some(port) = port {
        validate_port(port)?;
    }
    Ok(host.to_ascii_lowercase())
}

fn validate_port_suffix(suffix: &str) -> Result<(), CodecError> {
    if suffix.is_empty() {
        Ok(())
    } else if let Some(port) = suffix.strip_prefix(':') {
        validate_port(port)
    } else {
        Err(CodecError::InvalidUrl("invalid authority suffix"))
    }
}

fn validate_port(port: &str) -> Result<(), CodecError> {
    if port.is_empty() || port.len() > 5 || !port.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(CodecError::InvalidUrl("invalid URL port"));
    }
    port.parse::<u16>()
        .map(|_| ())
        .map_err(|_| CodecError::InvalidUrl("URL port is out of range"))
}

fn sha256_hex(value: &[u8]) -> String {
    let digest = Sha256::digest(value);
    let mut output = String::with_capacity(64);
    for byte in digest {
        use std::fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}
