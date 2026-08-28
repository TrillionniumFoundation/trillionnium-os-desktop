#[derive(Debug)]
pub enum CodecError {
    Json(JsonError),
    NonCanonicalEncoding,
    ProtocolMismatch,
    ExpectedType(&'static str),
    MissingField(&'static str),
    UnknownFields {
        object: &'static str,
        fields: Vec<String>,
    },
    UnknownOperation(String),
    SessionBinding(&'static str),
    InvalidIdentifier(&'static str),
    InvalidInteger(&'static str),
    InvalidText {
        field: &'static str,
        length: usize,
        minimum: usize,
        maximum: usize,
    },
    InvalidSha256(&'static str),
    InvalidCollection(&'static str),
    InvalidOperation(&'static str),
    InvalidUrl(&'static str),
    InvalidResponseShape,
    InvalidError(&'static str),
    SelfCheckInvariant(&'static str),
}

impl fmt::Display for CodecError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(error) => write!(formatter, "Browser API JSON failed: {error}"),
            Self::NonCanonicalEncoding => {
                formatter.write_str("Browser API JSON is not canonical")
            }
            Self::ProtocolMismatch => formatter.write_str("Browser API protocol mismatch"),
            Self::ExpectedType(field) => write!(formatter, "Browser API {field} has wrong type"),
            Self::MissingField(field) => write!(formatter, "Browser API field {field} is missing"),
            Self::UnknownFields { object, fields } => {
                write!(formatter, "Browser API {object} has unknown fields {fields:?}")
            }
            Self::UnknownOperation(operation) => {
                write!(formatter, "Browser API operation {operation} is unknown")
            }
            Self::SessionBinding(reason) => {
                write!(formatter, "Browser API session binding is invalid: {reason}")
            }
            Self::InvalidIdentifier(field) => {
                write!(formatter, "Browser API identifier {field} is invalid")
            }
            Self::InvalidInteger(field) => {
                write!(formatter, "Browser API integer {field} is invalid")
            }
            Self::InvalidText {
                field,
                length,
                minimum,
                maximum,
            } => write!(
                formatter,
                "Browser API text {field} length {length} is outside {minimum}..={maximum}",
            ),
            Self::InvalidSha256(field) => {
                write!(formatter, "Browser API SHA-256 field {field} is invalid")
            }
            Self::InvalidCollection(field) => {
                write!(formatter, "Browser API collection {field} is invalid")
            }
            Self::InvalidOperation(reason) => {
                write!(formatter, "Browser API operation is invalid: {reason}")
            }
            Self::InvalidUrl(reason) => write!(formatter, "Browser API URL is invalid: {reason}"),
            Self::InvalidResponseShape => {
                formatter.write_str("Browser API response result/error shape is invalid")
            }
            Self::InvalidError(reason) => {
                write!(formatter, "Browser API error is invalid: {reason}")
            }
            Self::SelfCheckInvariant(reason) => {
                write!(formatter, "Browser API codec self-check failed: {reason}")
            }
        }
    }
}

impl std::error::Error for CodecError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Json(error) => Some(error),
            _ => None,
        }
    }
}

impl From<JsonError> for CodecError {
    fn from(error: JsonError) -> Self {
        Self::Json(error)
    }
}
