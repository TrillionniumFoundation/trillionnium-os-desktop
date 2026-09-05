use crate::{AnyError, invalid};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, ElementReference, JsonObject, JsonValue,
};

#[derive(Debug, Clone)]
pub(crate) struct Coordinates {
    pub(crate) session_id: String,
    pub(crate) session_generation: u64,
    pub(crate) document_generation: u64,
    pub(crate) semantic_snapshot_revision: u64,
    pub(crate) mutation_epoch: u64,
}

impl Coordinates {
    pub(crate) fn from_result(result: &JsonObject) -> Result<Self, AnyError> {
        Ok(Self {
            session_id: string_field(result, "session_id")?.to_owned(),
            session_generation: u64_field(result, "session_generation")?,
            document_generation: u64_field(result, "document_generation")?,
            semantic_snapshot_revision: u64_field(result, "semantic_snapshot_revision")?,
            mutation_epoch: u64_field(result, "mutation_epoch")?,
        })
    }

    pub(crate) fn update(&mut self, result: &JsonObject) -> Result<(), AnyError> {
        if string_field(result, "session_id")? != self.session_id {
            return Err(invalid("PageOwner session ID changed").into());
        }
        self.session_generation = u64_field(result, "session_generation")?;
        self.document_generation = u64_field(result, "document_generation")?;
        self.semantic_snapshot_revision = u64_field(result, "semantic_snapshot_revision")?;
        self.mutation_epoch = u64_field(result, "mutation_epoch")?;
        Ok(())
    }

    pub(crate) fn request(&self, request_id: &str, operation: BrowserOperation) -> BrowserRequest {
        BrowserRequest {
            request_id: request_id.to_owned(),
            session_id: Some(self.session_id.clone()),
            session_generation: Some(self.session_generation),
            deadline_unix_ms: None,
            operation,
        }
    }
}

pub(crate) fn element_reference_field(
    object: &JsonObject,
    key: &str,
) -> Result<ElementReference, AnyError> {
    let value = match object.get(key) {
        Some(JsonValue::Object(value)) => value,
        _ => return Err(invalid(format!("result field {key} is not an object")).into()),
    };
    Ok(ElementReference {
        session_generation: u64_field(value, "session_generation")?,
        document_generation: u64_field(value, "document_generation")?,
        semantic_snapshot_revision: u64_field(value, "semantic_snapshot_revision")?,
        frame_id: string_field(value, "frame_id")?.to_owned(),
        backend_node_key: optional_string_field(value, "backend_node_key")?,
        role: optional_string_field(value, "role")?,
        accessible_name_sha256: optional_string_field(value, "accessible_name_sha256")?,
        structural_fingerprint: string_field(value, "structural_fingerprint")?.to_owned(),
    })
}

pub(crate) fn bool_field(object: &JsonObject, key: &str) -> Result<bool, AnyError> {
    match object.get(key) {
        Some(JsonValue::Bool(value)) => Ok(*value),
        _ => Err(invalid(format!("result field {key} is not a boolean")).into()),
    }
}

fn string_field<'a>(object: &'a JsonObject, key: &str) -> Result<&'a str, AnyError> {
    match object.get(key) {
        Some(JsonValue::String(value)) => Ok(value),
        _ => Err(invalid(format!("result field {key} is not a string")).into()),
    }
}

fn optional_string_field(object: &JsonObject, key: &str) -> Result<Option<String>, AnyError> {
    match object.get(key) {
        Some(JsonValue::String(value)) => Ok(Some(value.clone())),
        None | Some(JsonValue::Null) => Ok(None),
        _ => Err(invalid(format!("result field {key} is not an optional string")).into()),
    }
}

pub(crate) fn u64_field(object: &JsonObject, key: &str) -> Result<u64, AnyError> {
    match object.get(key) {
        Some(JsonValue::Integer(value)) if *value >= 0 => Ok(u64::try_from(*value)?),
        _ => Err(invalid(format!("result field {key} is not a non-negative integer")).into()),
    }
}
