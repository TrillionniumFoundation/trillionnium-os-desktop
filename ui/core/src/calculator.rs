//! Bounded Calculator protocol. The original Hepta writer owns authority and
//! operation history; this app model owns state and one bounded causal receipt.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const CALCULATOR_SCHEMA_VERSION: u16 = 1;
pub const CALCULATOR_TOPIC: &str = "trill.calculator.evaluate.v1";
pub const MAX_CALCULATOR_REQUEST_BYTES: usize = 4096;
pub const MAX_CALCULATOR_RESPONSE_BYTES: usize = 4096;
pub const MAX_CALCULATOR_VALUE_BYTES: usize = 64;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorChannelObservation {
    PrivateChannelPrepared,
    AppLayoutObserved,
    ChildExited,
}

/// Read-only projection: a historical attachment ACK is not a current grant.
#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorDestinationObservation {
    pub incarnation: String,
    pub channel: CalculatorChannelObservation,
    pub original_owner_registered: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorTargetIdentity {
    pub session_instance: String,
    pub task_id: u64,
    pub incarnation: String,
}

impl CalculatorTargetIdentity {
    pub fn validate(&self) -> Result<(), CalculatorProtocolError> {
        if self.task_id == 0
            || !lower_hex(&self.session_instance, 32)
            || !lower_hex(&self.incarnation, 32)
        {
            return Err(CalculatorProtocolError::Target);
        }
        Ok(())
    }
    pub fn destination_id(&self) -> String {
        format!(
            "trill.calculator:{}:{}:{}",
            self.session_instance, self.task_id, self.incarnation
        )
    }
    pub fn scope_sha256(&self) -> String {
        sha256_hex(
            format!(
                "trill.calculator.scope.v1\0{}\0{}\0{}",
                self.session_instance, self.task_id, self.incarnation
            )
            .as_bytes(),
        )
    }
    pub fn predecessor_sha256(&self, revision: u64) -> String {
        sha256_hex(
            format!(
                "trill.calculator.predecessor.v1\0{}\0{}\0{}\0{}",
                self.session_instance, self.task_id, self.incarnation, revision
            )
            .as_bytes(),
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorOperator {
    Add,
    Subtract,
    Multiply,
    Divide,
}

impl CalculatorOperator {
    pub fn name(self) -> &'static str {
        match self {
            Self::Add => "add",
            Self::Subtract => "subtract",
            Self::Multiply => "multiply",
            Self::Divide => "divide",
        }
    }
}

#[derive(Clone, Debug, Default, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorValueState {
    pub left: String,
    pub operator: Option<CalculatorOperator>,
    pub right: String,
    pub result: String,
}

impl CalculatorValueState {
    pub fn validate(&self) -> Result<(), CalculatorProtocolError> {
        if [&self.left, &self.right, &self.result]
            .iter()
            .any(|s| s.len() > MAX_CALCULATOR_VALUE_BYTES)
        {
            return Err(CalculatorProtocolError::ValueBound);
        }
        Ok(())
    }
    pub fn sha256(&self) -> String {
        let mut hash = Sha256::new();
        hash.update(b"trill.calculator.state.v1\0");
        for field in [
            self.left.as_str(),
            self.operator.map(CalculatorOperator::name).unwrap_or(""),
            self.right.as_str(),
            self.result.as_str(),
        ] {
            hash.update((field.len() as u64).to_be_bytes());
            hash.update(field.as_bytes());
        }
        hash.finalize()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorEvaluateAction {
    Evaluate,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorEvaluate {
    pub schema_version: u16,
    pub action: CalculatorEvaluateAction,
    pub operation_id: String,
    pub destination_id: String,
    pub target: CalculatorTargetIdentity,
    pub expected_revision: u64,
    pub left: String,
    pub operator: CalculatorOperator,
    pub right: String,
}

impl CalculatorEvaluate {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, CalculatorProtocolError> {
        let value: Self = parse(raw, MAX_CALCULATOR_REQUEST_BYTES)?;
        version(value.schema_version)?;
        value.target.validate()?;
        if !valid_operation_id(&value.operation_id) {
            return Err(CalculatorProtocolError::Operation);
        }
        if value.destination_id != value.target.destination_id() {
            return Err(CalculatorProtocolError::Destination);
        }
        if value.left.len() > MAX_CALCULATOR_VALUE_BYTES
            || value.right.len() > MAX_CALCULATOR_VALUE_BYTES
        {
            return Err(CalculatorProtocolError::ValueBound);
        }
        Ok(value)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorNotAppliedReason {
    RevisionConflict,
    OperationConflict,
    RevisionExhausted,
    TargetMismatch,
    UiDeadlineElapsed,
    ReceiptPending,
    InvalidOperand,
    Overflow,
    DivisionByZero,
    NonIntegralDivision,
}

pub fn checked_calculation(
    left: &str,
    operator: CalculatorOperator,
    right: &str,
) -> Result<String, CalculatorNotAppliedReason> {
    use CalculatorNotAppliedReason::*;
    let operand = |text: &str| {
        let value = text.parse::<i64>().map_err(|_| InvalidOperand)?;
        if value.to_string() != text {
            return Err(InvalidOperand);
        }
        Ok(value)
    };
    let a = operand(left)?;
    let b = operand(right)?;
    let result = match operator {
        CalculatorOperator::Add => a.checked_add(b),
        CalculatorOperator::Subtract => a.checked_sub(b),
        CalculatorOperator::Multiply => a.checked_mul(b),
        CalculatorOperator::Divide => {
            if b == 0 {
                return Err(DivisionByZero);
            }
            if a.checked_rem(b).ok_or(Overflow)? != 0 {
                return Err(NonIntegralDivision);
            }
            a.checked_div(b)
        }
    }
    .ok_or(Overflow)?;
    Ok(result.to_string())
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum CalculatorResult {
    Applied {
        previous_revision: u64,
        revision: u64,
        state: CalculatorValueState,
        state_sha256: String,
    },
    NotApplied {
        reason: CalculatorNotAppliedReason,
        current_revision: u64,
    },
    Unknown {
        current_revision: u64,
    },
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorResponse {
    pub schema_version: u16,
    pub target: CalculatorTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub result: CalculatorResult,
}

impl CalculatorResponse {
    pub fn parse_exact(raw: &[u8]) -> Result<Self, CalculatorProtocolError> {
        let value: Self = parse(raw, MAX_CALCULATOR_RESPONSE_BYTES)?;
        version(value.schema_version)?;
        value.target.validate()?;
        operation_digest(&value.operation_id, &value.payload_sha256)?;
        if let CalculatorResult::Applied {
            previous_revision,
            revision,
            state,
            state_sha256,
        } = &value.result
        {
            state.validate()?;
            if previous_revision.checked_add(1) != Some(*revision)
                || state.sha256() != *state_sha256
                || state
                    .operator
                    .and_then(|op| checked_calculation(&state.left, op, &state.right).ok())
                    .as_deref()
                    != Some(state.result.as_str())
            {
                return Err(CalculatorProtocolError::Receipt);
            }
        }
        Ok(value)
    }
    pub fn matches(
        &self,
        target: &CalculatorTargetIdentity,
        operation_id: &str,
        payload_sha256: &str,
    ) -> bool {
        &self.target == target
            && self.operation_id == operation_id
            && self.payload_sha256 == payload_sha256
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorReadAction {
    ReadCalculator,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorRead {
    pub schema_version: u16,
    pub action: CalculatorReadAction,
    pub target: CalculatorTargetIdentity,
    pub observation_id: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorStateAction {
    CalculatorState,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorStateObservation {
    pub schema_version: u16,
    pub action: CalculatorStateAction,
    pub target: CalculatorTargetIdentity,
    pub observation_id: String,
    pub revision: u64,
    pub state: CalculatorValueState,
    pub state_sha256: String,
    pub receipt_pending: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorObserveAction {
    Observe,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorObserve {
    pub schema_version: u16,
    pub action: CalculatorObserveAction,
    pub target: CalculatorTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorAcknowledgeAction {
    Acknowledge,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorAcknowledge {
    pub schema_version: u16,
    pub action: CalculatorAcknowledgeAction,
    pub target: CalculatorTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub receipt_sha256: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorAcknowledgedAction {
    Acknowledged,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CalculatorAcknowledgementStatus {
    Retired,
    AlreadyRetired,
    NotRetired,
}

#[derive(Clone, Debug, Eq, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CalculatorAcknowledged {
    pub schema_version: u16,
    pub action: CalculatorAcknowledgedAction,
    pub target: CalculatorTargetIdentity,
    pub operation_id: String,
    pub payload_sha256: String,
    pub receipt_sha256: String,
    pub status: CalculatorAcknowledgementStatus,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CalculatorProtocolError {
    FrameBound,
    Schema,
    Version,
    Target,
    Destination,
    Operation,
    Digest,
    ValueBound,
    Receipt,
}

impl std::fmt::Display for CalculatorProtocolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Calculator protocol {self:?}")
    }
}
impl std::error::Error for CalculatorProtocolError {}

/// Owned by one application-state worker. Recovery uses the exact checkpoint,
/// never infers an old operation from current values or another target.
#[derive(Clone)]
pub struct CalculatorDocument {
    target: CalculatorTargetIdentity,
    state: CalculatorValueState,
    revision: u64,
    pending: Option<CalculatorResponse>,
    retired: Option<CalculatorAcknowledge>,
}

impl CalculatorDocument {
    pub fn new(target: CalculatorTargetIdentity) -> Result<Self, CalculatorProtocolError> {
        target.validate()?;
        Ok(Self {
            target,
            state: CalculatorValueState::default(),
            revision: 0,
            pending: None,
            retired: None,
        })
    }
    pub fn target(&self) -> &CalculatorTargetIdentity {
        &self.target
    }
    pub fn state(&self) -> &CalculatorValueState {
        &self.state
    }
    pub fn revision(&self) -> u64 {
        self.revision
    }
    pub fn receipt_pending(&self) -> bool {
        self.pending.is_some()
    }

    pub fn local_edit(
        &mut self,
        next: CalculatorValueState,
    ) -> Result<(), CalculatorProtocolError> {
        next.validate()?;
        if next != self.state {
            self.revision = self
                .revision
                .checked_add(1)
                .ok_or(CalculatorProtocolError::Receipt)?;
            self.state = next;
        }
        Ok(())
    }

    pub fn deadline_refusal(
        &self,
        raw: &[u8],
    ) -> Result<CalculatorResponse, CalculatorProtocolError> {
        let request = CalculatorEvaluate::parse_exact(raw)?;
        let digest = sha256_hex(raw);
        if request.target != self.target {
            return Ok(self.refusal(&request, digest, CalculatorNotAppliedReason::TargetMismatch));
        }
        if let Some(retained) = self.retained_response(&request, &digest) {
            return Ok(retained);
        }
        Ok(self.refusal(
            &request,
            digest,
            CalculatorNotAppliedReason::UiDeadlineElapsed,
        ))
    }

    fn refusal(
        &self,
        request: &CalculatorEvaluate,
        digest: String,
        reason: CalculatorNotAppliedReason,
    ) -> CalculatorResponse {
        CalculatorResponse {
            schema_version: 1,
            target: self.target.clone(),
            operation_id: request.operation_id.clone(),
            payload_sha256: digest,
            result: CalculatorResult::NotApplied {
                reason,
                current_revision: self.revision,
            },
        }
    }

    // A deadline can prevent a new mutation, never negate an already known
    // causal result. Retired exact bytes are Unknown here; the original writer
    // retains their terminal result. This is a bounded cache, not a ledger.
    fn retained_response(
        &self,
        request: &CalculatorEvaluate,
        digest: &str,
    ) -> Option<CalculatorResponse> {
        if let Some(previous) = self
            .pending
            .as_ref()
            .filter(|r| r.operation_id == request.operation_id)
        {
            return Some(if previous.payload_sha256 == digest {
                previous.clone()
            } else {
                self.refusal(
                    request,
                    digest.into(),
                    CalculatorNotAppliedReason::OperationConflict,
                )
            });
        }
        if let Some(retired) = self
            .retired
            .as_ref()
            .filter(|r| r.operation_id == request.operation_id)
        {
            return Some(if retired.payload_sha256 == digest {
                CalculatorResponse {
                    schema_version: 1,
                    target: self.target.clone(),
                    operation_id: request.operation_id.clone(),
                    payload_sha256: digest.into(),
                    result: CalculatorResult::Unknown {
                        current_revision: self.revision,
                    },
                }
            } else {
                self.refusal(
                    request,
                    digest.into(),
                    CalculatorNotAppliedReason::OperationConflict,
                )
            });
        }
        None
    }

    pub fn apply_exact(
        &mut self,
        raw: &[u8],
    ) -> Result<CalculatorResponse, CalculatorProtocolError> {
        use CalculatorNotAppliedReason::*;
        let request = CalculatorEvaluate::parse_exact(raw)?;
        let digest = sha256_hex(raw);
        if request.target != self.target {
            return Ok(self.refusal(&request, digest, TargetMismatch));
        }
        if let Some(retained) = self.retained_response(&request, &digest) {
            return Ok(retained);
        }
        if request.expected_revision != self.revision {
            return Ok(self.refusal(&request, digest, RevisionConflict));
        }
        if self.pending.is_some() {
            return Ok(self.refusal(&request, digest, ReceiptPending));
        }
        let Some(revision) = self.revision.checked_add(1) else {
            return Ok(self.refusal(&request, digest, RevisionExhausted));
        };
        let result = match checked_calculation(&request.left, request.operator, &request.right) {
            Ok(value) => value,
            Err(reason) => return Ok(self.refusal(&request, digest, reason)),
        };
        let state = CalculatorValueState {
            left: request.left.clone(),
            operator: Some(request.operator),
            right: request.right.clone(),
            result,
        };
        let response = CalculatorResponse {
            schema_version: 1,
            target: self.target.clone(),
            operation_id: request.operation_id,
            payload_sha256: digest,
            result: CalculatorResult::Applied {
                previous_revision: self.revision,
                revision,
                state_sha256: state.sha256(),
                state: state.clone(),
            },
        };
        self.state = state;
        self.revision = revision;
        self.pending = Some(response.clone());
        Ok(response)
    }

    pub fn recovery_exact(&mut self, raw: &[u8]) -> Result<Vec<u8>, CalculatorProtocolError> {
        let value: serde_json::Value = parse(raw, MAX_CALCULATOR_REQUEST_BYTES)?;
        let bytes = match value.get("action").and_then(serde_json::Value::as_str) {
            Some("read_calculator") => {
                let request: CalculatorRead = parse(raw, MAX_CALCULATOR_REQUEST_BYTES)?;
                self.require_target(request.schema_version, &request.target)?;
                if !lower_hex(&request.observation_id, 32)
                    || request.observation_id.bytes().all(|b| b == b'0')
                {
                    return Err(CalculatorProtocolError::Digest);
                }
                serde_json::to_vec(&CalculatorStateObservation {
                    schema_version: 1,
                    action: CalculatorStateAction::CalculatorState,
                    target: self.target.clone(),
                    observation_id: request.observation_id,
                    revision: self.revision,
                    state: self.state.clone(),
                    state_sha256: self.state.sha256(),
                    receipt_pending: self.pending.is_some(),
                })
            }
            Some("observe") => {
                let request: CalculatorObserve = parse(raw, MAX_CALCULATOR_REQUEST_BYTES)?;
                self.require_target(request.schema_version, &request.target)?;
                operation_digest(&request.operation_id, &request.payload_sha256)?;
                let response = self
                    .pending
                    .as_ref()
                    .filter(|r| {
                        r.matches(&self.target, &request.operation_id, &request.payload_sha256)
                    })
                    .cloned()
                    .unwrap_or(CalculatorResponse {
                        schema_version: 1,
                        target: self.target.clone(),
                        operation_id: request.operation_id,
                        payload_sha256: request.payload_sha256,
                        result: CalculatorResult::Unknown {
                            current_revision: self.revision,
                        },
                    });
                serde_json::to_vec(&response)
            }
            Some("acknowledge") => {
                let request: CalculatorAcknowledge = parse(raw, MAX_CALCULATOR_REQUEST_BYTES)?;
                self.require_target(request.schema_version, &request.target)?;
                operation_digest(&request.operation_id, &request.payload_sha256)?;
                if !lower_hex(&request.receipt_sha256, 64) {
                    return Err(CalculatorProtocolError::Digest);
                }
                let status = if self.retired.as_ref() == Some(&request) {
                    CalculatorAcknowledgementStatus::AlreadyRetired
                } else if self.pending.as_ref().is_some_and(|receipt| {
                    receipt.matches(&self.target, &request.operation_id, &request.payload_sha256)
                        && serde_json::to_vec(receipt)
                            .is_ok_and(|bytes| sha256_hex(&bytes) == request.receipt_sha256)
                }) {
                    self.pending = None;
                    self.retired = Some(request.clone());
                    CalculatorAcknowledgementStatus::Retired
                } else {
                    CalculatorAcknowledgementStatus::NotRetired
                };
                serde_json::to_vec(&CalculatorAcknowledged {
                    schema_version: 1,
                    action: CalculatorAcknowledgedAction::Acknowledged,
                    target: self.target.clone(),
                    operation_id: request.operation_id,
                    payload_sha256: request.payload_sha256,
                    receipt_sha256: request.receipt_sha256,
                    status,
                })
            }
            _ => return Err(CalculatorProtocolError::Schema),
        }
        .map_err(|_| CalculatorProtocolError::Receipt)?;
        if bytes.len() > MAX_CALCULATOR_RESPONSE_BYTES {
            return Err(CalculatorProtocolError::FrameBound);
        }
        Ok(bytes)
    }

    fn require_target(
        &self,
        schema_version: u16,
        target: &CalculatorTargetIdentity,
    ) -> Result<(), CalculatorProtocolError> {
        version(schema_version)?;
        target.validate()?;
        if target != &self.target {
            return Err(CalculatorProtocolError::Target);
        }
        Ok(())
    }
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
pub fn lower_hex(value: &str, count: usize) -> bool {
    value.len() == count
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
pub fn valid_operation_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-' | b':'))
}
fn operation_digest(operation: &str, digest: &str) -> Result<(), CalculatorProtocolError> {
    if !valid_operation_id(operation) {
        return Err(CalculatorProtocolError::Operation);
    }
    if !lower_hex(digest, 64) {
        return Err(CalculatorProtocolError::Digest);
    }
    Ok(())
}
fn version(value: u16) -> Result<(), CalculatorProtocolError> {
    if value == 1 {
        Ok(())
    } else {
        Err(CalculatorProtocolError::Version)
    }
}
fn parse<T: for<'de> Deserialize<'de>>(
    raw: &[u8],
    limit: usize,
) -> Result<T, CalculatorProtocolError> {
    if raw.is_empty() || raw.len() > limit {
        return Err(CalculatorProtocolError::FrameBound);
    }
    serde_json::from_slice(raw).map_err(|_| CalculatorProtocolError::Schema)
}

#[path = "calculator_checkpoint.rs"]
mod checkpoint;

#[cfg(test)]
#[path = "calculator_tests.rs"]
mod tests;
