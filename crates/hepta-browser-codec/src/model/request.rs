#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EffectClass {
    Observation,
    LocalInteraction,
    PotentialExternalEffect,
}

impl EffectClass {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Observation => "observation",
            Self::LocalInteraction => "local_interaction",
            Self::PotentialExternalEffect => "potential_external_effect",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrowserRequest {
    pub request_id: String,
    pub session_id: Option<String>,
    pub session_generation: Option<u64>,
    pub deadline_unix_ms: Option<u64>,
    pub operation: BrowserOperation,
}

impl BrowserRequest {
    pub fn effect_class(&self) -> EffectClass {
        self.operation.effect_class()
    }

    pub fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate_binding()?;
        let mut object = JsonObject::new();
        object.insert("operation".to_owned(), self.operation.to_json()?);
        object.insert(
            "protocol".to_owned(),
            JsonValue::String(BROWSER_API_PROTOCOL.to_owned()),
        );
        object.insert(
            "request_id".to_owned(),
            JsonValue::String(self.request_id.clone()),
        );
        if let Some(deadline) = self.deadline_unix_ms {
            object.insert(
                "deadline_unix_ms".to_owned(),
                JsonValue::Integer(integer_from_u64(deadline, "deadline_unix_ms")?),
            );
        }
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
        Ok(JsonValue::Object(object))
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "request")?;
        let protocol = object.take_string("protocol")?;
        if protocol != BROWSER_API_PROTOCOL {
            return Err(CodecError::ProtocolMismatch);
        }
        let request_id = object.take_string("request_id")?;
        validate_identifier("request_id", &request_id, MAX_IDENTIFIER_BYTES)?;
        let session_id = object.take_optional_string("session_id")?;
        let session_generation = object.take_optional_u64("session_generation")?;
        let deadline_unix_ms = object.take_optional_u64("deadline_unix_ms")?;
        let operation = BrowserOperation::from_json(object.take("operation")?)?;
        object.finish()?;
        let request = Self {
            request_id,
            session_id,
            session_generation,
            deadline_unix_ms,
            operation,
        };
        request.validate_binding()?;
        Ok(request)
    }

    fn validate_binding(&self) -> Result<(), CodecError> {
        validate_identifier("request_id", &self.request_id, MAX_IDENTIFIER_BYTES)?;
        match (&self.session_id, self.session_generation) {
            (Some(session_id), Some(generation)) if generation > 0 => {
                validate_identifier("session_id", session_id, MAX_IDENTIFIER_BYTES)?;
                if self.operation.is_unbound() {
                    return Err(CodecError::SessionBinding(
                        "health and session_create must not carry a session binding",
                    ));
                }
            }
            (None, None) => {
                if !self.operation.is_unbound() {
                    return Err(CodecError::SessionBinding(
                        "operation requires paired session_id and session_generation",
                    ));
                }
            }
            _ => {
                return Err(CodecError::SessionBinding(
                    "session_id and session_generation must appear together and generation must be non-zero",
                ));
            }
        }
        self.operation.validate()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BrowserOperation {
    Health,
    SessionCreate {
        profile: ProfileSpec,
        ui_mode: String,
    },
    SessionSnapshot,
    SessionClose,
    PageNavigate {
        target: NavigationTarget,
        expected_document_generation: u64,
    },
    PageObserve {
        fields: Vec<ObservationField>,
    },
    PageAct {
        target: ElementReference,
        action: PageAction,
    },
    PageWait {
        condition: WaitCondition,
        timeout_ms: u64,
    },
    PageExtract {
        schema_id: String,
    },
}

impl BrowserOperation {
    pub const fn effect_class(&self) -> EffectClass {
        match self {
            Self::Health
            | Self::SessionSnapshot
            | Self::PageObserve { .. }
            | Self::PageWait { .. }
            | Self::PageExtract { .. } => EffectClass::Observation,
            Self::SessionCreate { .. } | Self::SessionClose => EffectClass::LocalInteraction,
            Self::PageNavigate { .. } => EffectClass::PotentialExternalEffect,
            Self::PageAct {
                action: PageAction::Scroll { .. },
                ..
            } => EffectClass::LocalInteraction,
            Self::PageAct { .. } => EffectClass::PotentialExternalEffect,
        }
    }

    const fn is_unbound(&self) -> bool {
        matches!(self, Self::Health | Self::SessionCreate { .. })
    }

    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::Health | Self::SessionSnapshot | Self::SessionClose => Ok(()),
            Self::SessionCreate { profile, ui_mode } => {
                profile.validate()?;
                if ui_mode != "headed" {
                    return Err(CodecError::InvalidOperation("ui_mode must be headed"));
                }
                Ok(())
            }
            Self::PageNavigate {
                target,
                expected_document_generation,
            } => {
                target.validate()?;
                require_nonzero(*expected_document_generation, "expected_document_generation")
            }
            Self::PageObserve { fields } => {
                if fields.is_empty() {
                    return Err(CodecError::InvalidCollection("observation fields"));
                }
                let unique: BTreeSet<_> = fields.iter().copied().collect();
                if unique.len() != fields.len() {
                    return Err(CodecError::InvalidCollection("observation fields"));
                }
                Ok(())
            }
            Self::PageAct { target, action } => {
                target.validate()?;
                action.validate()
            }
            Self::PageWait {
                condition,
                timeout_ms,
            } => {
                require_range(*timeout_ms, 1, 300_000, "wait timeout_ms")?;
                condition.validate()
            }
            Self::PageExtract { schema_id } => {
                validate_identifier("schema_id", schema_id, MAX_IDENTIFIER_BYTES)
            }
        }
    }

    fn from_json(value: JsonValue) -> Result<Self, CodecError> {
        let mut object = ObjectCursor::new(value, "operation")?;
        let kind = object.take_string("type")?;
        let operation = match kind.as_str() {
            "health" => {
                object.finish()?;
                Self::Health
            }
            "session_create" => {
                let profile = ProfileSpec::from_json(object.take("profile")?)?;
                let ui_mode = object.take_string("ui_mode")?;
                object.finish()?;
                Self::SessionCreate { profile, ui_mode }
            }
            "session_snapshot" => {
                object.finish()?;
                Self::SessionSnapshot
            }
            "session_close" => {
                object.finish()?;
                Self::SessionClose
            }
            "page_navigate" => {
                let target = NavigationTarget::from_json(object.take("target")?)?;
                let expected_document_generation =
                    object.take_u64("expected_document_generation")?;
                object.finish()?;
                Self::PageNavigate {
                    target,
                    expected_document_generation,
                }
            }
            "page_observe" => {
                let values = object.take_array("fields")?;
                let mut fields = Vec::with_capacity(values.len());
                for value in values {
                    fields.push(ObservationField::from_json(value)?);
                }
                object.finish()?;
                Self::PageObserve { fields }
            }
            "page_act" => {
                let target = ElementReference::from_json(object.take("target")?)?;
                let action = PageAction::from_json(object.take("action")?)?;
                object.finish()?;
                Self::PageAct { target, action }
            }
            "page_wait" => {
                let condition = WaitCondition::from_json(object.take("condition")?)?;
                let timeout_ms = object.take_u64("timeout_ms")?;
                object.finish()?;
                Self::PageWait {
                    condition,
                    timeout_ms,
                }
            }
            "page_extract" => {
                let schema_id = object.take_string("schema_id")?;
                object.finish()?;
                Self::PageExtract { schema_id }
            }
            _ => return Err(CodecError::UnknownOperation(kind)),
        };
        operation.validate()?;
        Ok(operation)
    }

    fn to_json(&self) -> Result<JsonValue, CodecError> {
        self.validate()?;
        let mut object = JsonObject::new();
        match self {
            Self::Health => insert_type(&mut object, "health"),
            Self::SessionCreate { profile, ui_mode } => {
                insert_type(&mut object, "session_create");
                object.insert("profile".to_owned(), profile.to_json()?);
                object.insert("ui_mode".to_owned(), JsonValue::String(ui_mode.clone()));
            }
            Self::SessionSnapshot => insert_type(&mut object, "session_snapshot"),
            Self::SessionClose => insert_type(&mut object, "session_close"),
            Self::PageNavigate {
                target,
                expected_document_generation,
            } => {
                insert_type(&mut object, "page_navigate");
                object.insert("target".to_owned(), target.to_json()?);
                object.insert(
                    "expected_document_generation".to_owned(),
                    JsonValue::Integer(integer_from_u64(
                        *expected_document_generation,
                        "expected_document_generation",
                    )?),
                );
            }
            Self::PageObserve { fields } => {
                insert_type(&mut object, "page_observe");
                object.insert(
                    "fields".to_owned(),
                    JsonValue::Array(fields.iter().map(|field| (*field).to_json()).collect()),
                );
            }
            Self::PageAct { target, action } => {
                insert_type(&mut object, "page_act");
                object.insert("target".to_owned(), target.to_json()?);
                object.insert("action".to_owned(), action.to_json()?);
            }
            Self::PageWait {
                condition,
                timeout_ms,
            } => {
                insert_type(&mut object, "page_wait");
                object.insert("condition".to_owned(), condition.to_json()?);
                object.insert(
                    "timeout_ms".to_owned(),
                    JsonValue::Integer(integer_from_u64(*timeout_ms, "timeout_ms")?),
                );
            }
            Self::PageExtract { schema_id } => {
                insert_type(&mut object, "page_extract");
                object.insert(
                    "schema_id".to_owned(),
                    JsonValue::String(schema_id.clone()),
                );
            }
        }
        Ok(JsonValue::Object(object))
    }
}
