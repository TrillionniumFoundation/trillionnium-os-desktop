#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BrowserErrorCode {
    InvalidRequest,
    Unsupported,
    PolicyDenied,
    StaleSession,
    StaleDocument,
    StaleSnapshot,
    QueueFull,
    HumanControlActive,
    ImeCompositionActive,
    ModalBlocked,
    NavigationInProgress,
    CapabilityPending,
    Cancelled,
    DeadlineExceeded,
    BrowserCrashed,
    Indeterminate,
    Internal,
}

impl BrowserErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidRequest => "invalid_request",
            Self::Unsupported => "unsupported",
            Self::PolicyDenied => "policy_denied",
            Self::StaleSession => "stale_session",
            Self::StaleDocument => "stale_document",
            Self::StaleSnapshot => "stale_snapshot",
            Self::QueueFull => "queue_full",
            Self::HumanControlActive => "human_control_active",
            Self::ImeCompositionActive => "ime_composition_active",
            Self::ModalBlocked => "modal_blocked",
            Self::NavigationInProgress => "navigation_in_progress",
            Self::CapabilityPending => "capability_pending",
            Self::Cancelled => "cancelled",
            Self::DeadlineExceeded => "deadline_exceeded",
            Self::BrowserCrashed => "browser_crashed",
            Self::Indeterminate => "indeterminate",
            Self::Internal => "internal",
        }
    }

    pub const fn retry_policy(self) -> &'static str {
        match self {
            Self::InvalidRequest => "never",
            Self::Unsupported => "after_upgrade",
            Self::PolicyDenied => "after_explicit_policy_change",
            Self::StaleSession => "recreate_session",
            Self::StaleDocument | Self::StaleSnapshot => "observe_again",
            Self::QueueFull => "bounded_backoff",
            Self::HumanControlActive => "after_human_release",
            Self::ImeCompositionActive => "after_ime_end",
            Self::ModalBlocked => "after_modal_resolution",
            Self::NavigationInProgress => "after_navigation",
            Self::CapabilityPending => "after_capability_resolution",
            Self::Cancelled | Self::DeadlineExceeded => "caller_decides",
            Self::BrowserCrashed => "after_recovery",
            Self::Indeterminate => "never_automatic",
            Self::Internal => "after_diagnosis",
        }
    }

    fn parse(value: String) -> Result<Self, CodecError> {
        match value.as_str() {
            "invalid_request" => Ok(Self::InvalidRequest),
            "unsupported" => Ok(Self::Unsupported),
            "policy_denied" => Ok(Self::PolicyDenied),
            "stale_session" => Ok(Self::StaleSession),
            "stale_document" => Ok(Self::StaleDocument),
            "stale_snapshot" => Ok(Self::StaleSnapshot),
            "queue_full" => Ok(Self::QueueFull),
            "human_control_active" => Ok(Self::HumanControlActive),
            "ime_composition_active" => Ok(Self::ImeCompositionActive),
            "modal_blocked" => Ok(Self::ModalBlocked),
            "navigation_in_progress" => Ok(Self::NavigationInProgress),
            "capability_pending" => Ok(Self::CapabilityPending),
            "cancelled" => Ok(Self::Cancelled),
            "deadline_exceeded" => Ok(Self::DeadlineExceeded),
            "browser_crashed" => Ok(Self::BrowserCrashed),
            "indeterminate" => Ok(Self::Indeterminate),
            "internal" => Ok(Self::Internal),
            _ => Err(CodecError::InvalidError("unknown error code")),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrowserWireError {
    pub code: BrowserErrorCode,
    pub message: String,
    pub details: Option<JsonObject>,
}

impl BrowserWireError {
    pub fn retry_policy(&self) -> &'static str {
        self.code.retry_policy()
    }

    fn validate(&self) -> Result<(), CodecError> {
        validate_text(
            "error message",
            &self.message,
            1,
            MAX_ERROR_MESSAGE_BYTES,
        )
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "wire error")?;
        let code = BrowserErrorCode::parse(object.take_string("code")?)?;
        let message = object.take_string("message")?;
        let retry = object.take_string("retry")?;
        let details = match object.take_optional("details") {
            Some(JsonValue::Object(details)) => Some(details),
            Some(_) => return Err(CodecError::ExpectedType("error details object")),
            None => None,
        };
        object.finish()?;
        if retry != code.retry_policy() {
            return Err(CodecError::InvalidError(
                "retry policy does not match error code",
            ));
        }
        let error = Self {
            code,
            message,
            details,
        };
        error.validate()?;
        Ok(error)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        object.insert(
            "code".to_owned(),
            JsonValue::String(self.code.as_str().to_owned()),
        );
        object.insert(
            "message".to_owned(),
            JsonValue::String(self.message.clone()),
        );
        object.insert(
            "retry".to_owned(),
            JsonValue::String(self.code.retry_policy().to_owned()),
        );
        if let Some(details) = &self.details {
            object.insert("details".to_owned(), JsonValue::Object(details.clone()));
        }
        Ok(JsonValue::Object(object))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrowserResponse {
    pub request_id: String,
    pub session_id: Option<String>,
    pub session_generation: Option<u64>,
    pub outcome: Result<JsonObject, BrowserWireError>,
}

impl BrowserResponse {
    pub fn success(
        request_id: String,
        session_id: Option<String>,
        session_generation: Option<u64>,
        result: JsonObject,
    ) -> Result<Self, CodecError> {
        let response = Self {
            request_id,
            session_id,
            session_generation,
            outcome: Ok(result),
        };
        response.validate()?;
        Ok(response)
    }

    pub fn failure(
        request_id: String,
        session_id: Option<String>,
        session_generation: Option<u64>,
        error: BrowserWireError,
    ) -> Result<Self, CodecError> {
        let response = Self {
            request_id,
            session_id,
            session_generation,
            outcome: Err(error),
        };
        response.validate()?;
        Ok(response)
    }

    fn validate(&self) -> Result<(), CodecError> {
        validate_identifier("request_id", &self.request_id, MAX_IDENTIFIER_BYTES)?;
        match (&self.session_id, self.session_generation) {
            (Some(session_id), Some(generation)) if generation > 0 => {
                validate_identifier("session_id", session_id, MAX_IDENTIFIER_BYTES)?;
            }
            (None, None) => {}
            _ => {
                return Err(CodecError::SessionBinding(
                    "response session_id and session_generation must appear together",
                ));
            }
        }
        if let Err(error) = &self.outcome {
            error.validate()?;
        }
        Ok(())
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "response")?;
        let protocol = object.take_string("protocol")?;
        if protocol != BROWSER_API_PROTOCOL {
            return Err(CodecError::ProtocolMismatch);
        }
        let request_id = object.take_string("request_id")?;
        let session_id = object.take_optional_string("session_id")?;
        let session_generation = object.take_optional_u64("session_generation")?;
        let ok = object.take_bool("ok")?;
        let result = object.take_optional("result");
        let error = object.take_optional("error");
        object.finish()?;
        let outcome = match (ok, result, error) {
            (true, Some(JsonValue::Object(result)), None) => Ok(result),
            (false, None, Some(error)) => Err(BrowserWireError::from_json(error)?),
            _ => return Err(CodecError::InvalidResponseShape),
        };
        let response = Self {
            request_id,
            session_id,
            session_generation,
            outcome,
        };
        response.validate()?;
        Ok(response)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        object.insert("ok".to_owned(), JsonValue::Bool(self.outcome.is_ok()));
        object.insert(
            "protocol".to_owned(),
            JsonValue::String(BROWSER_API_PROTOCOL.to_owned()),
        );
        object.insert(
            "request_id".to_owned(),
            JsonValue::String(self.request_id.clone()),
        );
        if let Some(session_id) = &self.session_id {
            object.insert(
                "session_id".to_owned(),
                JsonValue::String(session_id.clone()),
            );
        }
        if let Some(generation) = self.session_generation {
            object.insert(
                "session_generation".to_owned(),
                JsonValue::Integer(integer_from_u64(generation, "session_generation")?),
            );
        }
        match &self.outcome {
            Ok(result) => {
                object.insert("result".to_owned(), JsonValue::Object(result.clone()));
            }
            Err(error) => {
                object.insert("error".to_owned(), error.to_json()?);
            }
        }
        Ok(JsonValue::Object(object))
    }
}
