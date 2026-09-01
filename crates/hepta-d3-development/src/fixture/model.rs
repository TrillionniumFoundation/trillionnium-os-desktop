use crate::{AnyError, invalid};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, JsonObject, JsonValue};

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

fn string_field<'a>(object: &'a JsonObject, key: &str) -> Result<&'a str, AnyError> {
    match object.get(key) {
        Some(JsonValue::String(value)) => Ok(value),
        _ => Err(invalid(format!("result field {key} is not a string")).into()),
    }
}

fn u64_field(object: &JsonObject, key: &str) -> Result<u64, AnyError> {
    match object.get(key) {
        Some(JsonValue::Integer(value)) if *value >= 0 => Ok(u64::try_from(*value)?),
        _ => Err(invalid(format!("result field {key} is not a non-negative integer")).into()),
    }
}
