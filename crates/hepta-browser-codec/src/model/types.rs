#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfilePersistence {
    Ephemeral,
    Persistent,
}

impl ProfilePersistence {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Ephemeral => "ephemeral",
            Self::Persistent => "persistent",
        }
    }

    fn parse(value: String) -> Result<Self, CodecError> {
        match value.as_str() {
            "ephemeral" => Ok(Self::Ephemeral),
            "persistent" => Ok(Self::Persistent),
            _ => Err(CodecError::InvalidOperation("invalid profile persistence")),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProfileSpec {
    pub profile_id: String,
    pub persistence: ProfilePersistence,
}

impl ProfileSpec {
    fn validate(&self) -> Result<(), CodecError> {
        validate_identifier("profile_id", &self.profile_id, MAX_IDENTIFIER_BYTES)
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "profile")?;
        let profile_id = object.take_string("profile_id")?;
        let persistence = ProfilePersistence::parse(object.take_string("persistence")?)?;
        object.finish()?;
        let profile = Self {
            profile_id,
            persistence,
        };
        profile.validate()?;
        Ok(profile)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        Ok(JsonValue::Object(BTreeMap::from([
            (
                "persistence".to_owned(),
                JsonValue::String(self.persistence.as_str().to_owned()),
            ),
            (
                "profile_id".to_owned(),
                JsonValue::String(self.profile_id.clone()),
            ),
        ])))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NavigationTarget {
    TrustedShell,
    TrustedApp { publisher: String, app_id: String },
    ExternalHttps { url: String },
    LocalHttpFixture { url: String },
}

impl NavigationTarget {
    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::TrustedShell => Ok(()),
            Self::TrustedApp { publisher, app_id } => {
                validate_dns_label("publisher", publisher)?;
                validate_dns_label("app_id", app_id)
            }
            Self::ExternalHttps { url } => validate_url(url, UrlPolicy::ExternalHttps),
            Self::LocalHttpFixture { url } => validate_url(url, UrlPolicy::LoopbackHttp),
        }
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "navigation target")?;
        let kind = object.take_string("type")?;
        let target = match kind.as_str() {
            "trusted_shell" => {
                object.finish()?;
                Self::TrustedShell
            }
            "trusted_app" => {
                let publisher = object.take_string("publisher")?;
                let app_id = object.take_string("app_id")?;
                object.finish()?;
                Self::TrustedApp { publisher, app_id }
            }
            "external_https" => {
                let url = object.take_string("url")?;
                object.finish()?;
                Self::ExternalHttps { url }
            }
            "local_http_fixture" => {
                let url = object.take_string("url")?;
                object.finish()?;
                Self::LocalHttpFixture { url }
            }
            _ => return Err(CodecError::InvalidUrl("unknown navigation target")),
        };
        target.validate()?;
        Ok(target)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        match self {
            Self::TrustedShell => insert_type(&mut object, "trusted_shell"),
            Self::TrustedApp { publisher, app_id } => {
                insert_type(&mut object, "trusted_app");
                object.insert(
                    "publisher".to_owned(),
                    JsonValue::String(publisher.clone()),
                );
                object.insert("app_id".to_owned(), JsonValue::String(app_id.clone()));
            }
            Self::ExternalHttps { url } => {
                insert_type(&mut object, "external_https");
                object.insert("url".to_owned(), JsonValue::String(url.clone()));
            }
            Self::LocalHttpFixture { url } => {
                insert_type(&mut object, "local_http_fixture");
                object.insert("url".to_owned(), JsonValue::String(url.clone()));
            }
        }
        Ok(JsonValue::Object(object))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ObservationField {
    Role,
    Name,
    Text,
    Href,
    Bounds,
}

impl ObservationField {
    const fn as_str(self) -> &'static str {
        match self {
            Self::Role => "role",
            Self::Name => "name",
            Self::Text => "text",
            Self::Href => "href",
            Self::Bounds => "bounds",
        }
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let value = expect_string(value, "observation field")?;
        match value.as_str() {
            "role" => Ok(Self::Role),
            "name" => Ok(Self::Name),
            "text" => Ok(Self::Text),
            "href" => Ok(Self::Href),
            "bounds" => Ok(Self::Bounds),
            _ => Err(CodecError::InvalidCollection("observation fields")),
        }
    }

    fn to_json(self) -> JsonValue {
        JsonValue::String(self.as_str().to_owned())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ElementReference {
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub frame_id: String,
    pub backend_node_key: Option<String>,
    pub role: Option<String>,
    pub accessible_name_sha256: Option<String>,
    pub structural_fingerprint: String,
}

impl ElementReference {
    fn validate(&self) -> Result<(), CodecError> {
        require_nonzero(self.session_generation, "reference session_generation")?;
        require_nonzero(self.document_generation, "reference document_generation")?;
        require_nonzero(
            self.semantic_snapshot_revision,
            "reference semantic_snapshot_revision",
        )?;
        validate_identifier("frame_id", &self.frame_id, 64)?;
        if let Some(value) = &self.backend_node_key {
            validate_identifier("backend_node_key", value, MAX_IDENTIFIER_BYTES)?;
        }
        if let Some(value) = &self.role {
            validate_text("role", value, 1, 128)?;
        }
        if let Some(value) = &self.accessible_name_sha256 {
            validate_sha256("accessible_name_sha256", value)?;
        }
        validate_sha256("structural_fingerprint", &self.structural_fingerprint)
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "element reference")?;
        let reference = Self {
            session_generation: object.take_u64("session_generation")?,
            document_generation: object.take_u64("document_generation")?,
            semantic_snapshot_revision: object.take_u64("semantic_snapshot_revision")?,
            frame_id: object.take_string("frame_id")?,
            backend_node_key: object.take_optional_string("backend_node_key")?,
            role: object.take_optional_string("role")?,
            accessible_name_sha256: object.take_optional_string("accessible_name_sha256")?,
            structural_fingerprint: object.take_string("structural_fingerprint")?,
        };
        object.finish()?;
        reference.validate()?;
        Ok(reference)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        object.insert(
            "document_generation".to_owned(),
            JsonValue::Integer(integer_from_u64(
                self.document_generation,
                "document_generation",
            )?),
        );
        object.insert(
            "frame_id".to_owned(),
            JsonValue::String(self.frame_id.clone()),
        );
        object.insert(
            "semantic_snapshot_revision".to_owned(),
            JsonValue::Integer(integer_from_u64(
                self.semantic_snapshot_revision,
                "semantic_snapshot_revision",
            )?),
        );
        object.insert(
            "session_generation".to_owned(),
            JsonValue::Integer(integer_from_u64(
                self.session_generation,
                "session_generation",
            )?),
        );
        object.insert(
            "structural_fingerprint".to_owned(),
            JsonValue::String(self.structural_fingerprint.clone()),
        );
        if let Some(value) = &self.backend_node_key {
            object.insert(
                "backend_node_key".to_owned(),
                JsonValue::String(value.clone()),
            );
        }
        if let Some(value) = &self.role {
            object.insert("role".to_owned(), JsonValue::String(value.clone()));
        }
        if let Some(value) = &self.accessible_name_sha256 {
            object.insert(
                "accessible_name_sha256".to_owned(),
                JsonValue::String(value.clone()),
            );
        }
        Ok(JsonValue::Object(object))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PageAction {
    Click,
    Type { text: String },
    Press { key: String },
    Scroll { delta_x: i64, delta_y: i64 },
    Select { value: String },
}

impl PageAction {
    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::Click => Ok(()),
            Self::Type { text } => validate_text("typed text", text, 0, MAX_TYPED_TEXT_BYTES),
            Self::Press { key } => validate_text("key", key, 1, 128),
            Self::Scroll { delta_x, delta_y } => {
                require_signed_range(*delta_x, -1_000_000, 1_000_000, "delta_x")?;
                require_signed_range(*delta_y, -1_000_000, 1_000_000, "delta_y")
            }
            Self::Select { value } => {
                validate_text("selection value", value, 0, MAX_SELECT_BYTES)
            }
        }
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "page action")?;
        let kind = object.take_string("type")?;
        let action = match kind.as_str() {
            "click" => {
                object.finish()?;
                Self::Click
            }
            "type" => {
                let text = object.take_string("text")?;
                object.finish()?;
                Self::Type { text }
            }
            "press" => {
                let key = object.take_string("key")?;
                object.finish()?;
                Self::Press { key }
            }
            "scroll" => {
                let delta_x = object.take_i64("delta_x")?;
                let delta_y = object.take_i64("delta_y")?;
                object.finish()?;
                Self::Scroll { delta_x, delta_y }
            }
            "select" => {
                let value = object.take_string("value")?;
                object.finish()?;
                Self::Select { value }
            }
            _ => return Err(CodecError::InvalidOperation("unknown page action")),
        };
        action.validate()?;
        Ok(action)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        match self {
            Self::Click => insert_type(&mut object, "click"),
            Self::Type { text } => {
                insert_type(&mut object, "type");
                object.insert("text".to_owned(), JsonValue::String(text.clone()));
            }
            Self::Press { key } => {
                insert_type(&mut object, "press");
                object.insert("key".to_owned(), JsonValue::String(key.clone()));
            }
            Self::Scroll { delta_x, delta_y } => {
                insert_type(&mut object, "scroll");
                object.insert("delta_x".to_owned(), JsonValue::Integer(*delta_x));
                object.insert("delta_y".to_owned(), JsonValue::Integer(*delta_y));
            }
            Self::Select { value } => {
                insert_type(&mut object, "select");
                object.insert("value".to_owned(), JsonValue::String(value.clone()));
            }
        }
        Ok(JsonValue::Object(object))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WaitCondition {
    DocumentReady,
    UrlEquals { url: String },
    ElementPresent { target: ElementReference },
    TextPresent { text: String },
    NetworkIdle { quiet_window_ms: u64 },
}

impl WaitCondition {
    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::DocumentReady => Ok(()),
            Self::UrlEquals { url } => validate_text("wait URL", url, 1, MAX_URL_BYTES),
            Self::ElementPresent { target } => target.validate(),
            Self::TextPresent { text } => {
                validate_text("wait text", text, 0, MAX_WAIT_TEXT_BYTES)
            }
            Self::NetworkIdle { quiet_window_ms } => {
                require_range(*quiet_window_ms, 1, 60_000, "quiet_window_ms")
            }
        }
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "wait condition")?;
        let kind = object.take_string("type")?;
        let condition = match kind.as_str() {
            "document_ready" => {
                object.finish()?;
                Self::DocumentReady
            }
            "url_equals" => {
                let url = object.take_string("url")?;
                object.finish()?;
                Self::UrlEquals { url }
            }
            "element_present" => {
                let target = ElementReference::from_json(object.take("target")?)?;
                object.finish()?;
                Self::ElementPresent { target }
            }
            "text_present" => {
                let text = object.take_string("text")?;
                object.finish()?;
                Self::TextPresent { text }
            }
            "network_idle" => {
                let quiet_window_ms = object.take_u64("quiet_window_ms")?;
                object.finish()?;
                Self::NetworkIdle { quiet_window_ms }
            }
            _ => return Err(CodecError::InvalidOperation("unknown wait condition")),
        };
        condition.validate()?;
        Ok(condition)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        match self {
            Self::DocumentReady => insert_type(&mut object, "document_ready"),
            Self::UrlEquals { url } => {
                insert_type(&mut object, "url_equals");
                object.insert("url".to_owned(), JsonValue::String(url.clone()));
            }
            Self::ElementPresent { target } => {
                insert_type(&mut object, "element_present");
                object.insert("target".to_owned(), target.to_json()?);
            }
            Self::TextPresent { text } => {
                insert_type(&mut object, "text_present");
                object.insert("text".to_owned(), JsonValue::String(text.clone()));
            }
            Self::NetworkIdle { quiet_window_ms } => {
                insert_type(&mut object, "network_idle");
                object.insert(
                    "quiet_window_ms".to_owned(),
                    JsonValue::Integer(integer_from_u64(
                        *quiet_window_ms,
                        "quiet_window_ms",
                    )?),
                );
            }
        }
        Ok(JsonValue::Object(object))
    }
}
