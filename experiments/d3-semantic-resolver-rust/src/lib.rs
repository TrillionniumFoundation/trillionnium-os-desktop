//! Standalone Rust reference for the D3 atomic semantic resolver contract.
//!
//! This crate owns no Servo object and performs no external effect. It models
//! the required engine-owned critical section: resolve, retain, revalidate and
//! act at most once without yielding to another semantic-tree mutation.

#![forbid(unsafe_code)]

use std::error::Error;
use std::fmt;
use std::sync::Mutex;
use std::time::Instant;

const MAX_TEXT_BYTES: usize = 16 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Revisions {
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub mutation_epoch: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SemanticNode {
    pub frame_id: String,
    pub semantic_id: String,
    pub role: String,
    pub accessible_name: String,
    pub structural_fingerprint: String,
    pub value: String,
    pub checked: Option<bool>,
    pub enabled: bool,
    pub visible: bool,
}

impl SemanticNode {
    pub fn validate(&self) -> Result<(), ResolverError> {
        validate_text("frame_id", &self.frame_id)?;
        validate_text("semantic_id", &self.semantic_id)?;
        validate_text("role", &self.role)?;
        validate_text("accessible_name", &self.accessible_name)?;
        validate_text("structural_fingerprint", &self.structural_fingerprint)?;
        if self.value.len() > MAX_TEXT_BYTES {
            return Err(ResolverError::new(
                ErrorCode::InvalidSnapshot,
                "node value exceeds the configured bound",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SemanticSnapshot {
    pub session_id: String,
    pub revisions: Revisions,
    pub nodes: Vec<SemanticNode>,
}

impl SemanticSnapshot {
    pub fn validate(&self) -> Result<(), ResolverError> {
        validate_text("session_id", &self.session_id)?;
        for node in &self.nodes {
            node.validate()?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TargetBinding {
    pub session_id: String,
    pub revisions: Revisions,
    pub frame_id: String,
    pub semantic_id: String,
    pub role: String,
    pub accessible_name: String,
    pub structural_fingerprint: String,
}

impl TargetBinding {
    pub fn validate(&self) -> Result<(), ResolverError> {
        validate_text("session_id", &self.session_id)?;
        validate_text("frame_id", &self.frame_id)?;
        validate_text("semantic_id", &self.semantic_id)?;
        validate_text("role", &self.role)?;
        validate_text("accessible_name", &self.accessible_name)?;
        validate_text("structural_fingerprint", &self.structural_fingerprint)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActionKind {
    Click,
    Focus,
    SetValue,
    InsertText,
    SetChecked,
    SelectOption,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActionValue {
    None,
    Text(String),
    Checked(bool),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SemanticAction {
    pub kind: ActionKind,
    pub value: ActionValue,
}

impl SemanticAction {
    pub const fn click() -> Self {
        Self {
            kind: ActionKind::Click,
            value: ActionValue::None,
        }
    }

    pub const fn focus() -> Self {
        Self {
            kind: ActionKind::Focus,
            value: ActionValue::None,
        }
    }

    pub fn set_value(value: impl Into<String>) -> Self {
        Self {
            kind: ActionKind::SetValue,
            value: ActionValue::Text(value.into()),
        }
    }

    pub fn insert_text(value: impl Into<String>) -> Self {
        Self {
            kind: ActionKind::InsertText,
            value: ActionValue::Text(value.into()),
        }
    }

    pub const fn set_checked(value: bool) -> Self {
        Self {
            kind: ActionKind::SetChecked,
            value: ActionValue::Checked(value),
        }
    }

    pub fn select_option(value: impl Into<String>) -> Self {
        Self {
            kind: ActionKind::SelectOption,
            value: ActionValue::Text(value.into()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActionReceipt {
    pub session_id: String,
    pub frame_id: String,
    pub semantic_id: String,
    pub action: ActionKind,
    pub mutation_epoch_before: u64,
    pub mutation_epoch_after: u64,
    pub action_count: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorCode {
    InvalidRequest,
    InvalidSnapshot,
    SessionMismatch,
    StaleSessionGeneration,
    StaleDocumentGeneration,
    StaleSemanticSnapshot,
    StaleMutationEpoch,
    TargetNotFound,
    AmbiguousTarget,
    FrameMismatch,
    RoleDrift,
    AccessibleNameDrift,
    StructuralDrift,
    MutationRace,
    UnsupportedAction,
    Cancelled,
    DeadlineExceeded,
    RevisionExhausted,
    LockPoisoned,
}

impl ErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidRequest => "invalid_request",
            Self::InvalidSnapshot => "invalid_snapshot",
            Self::SessionMismatch => "session_mismatch",
            Self::StaleSessionGeneration => "stale_session_generation",
            Self::StaleDocumentGeneration => "stale_document_generation",
            Self::StaleSemanticSnapshot => "stale_semantic_snapshot",
            Self::StaleMutationEpoch => "stale_mutation_epoch",
            Self::TargetNotFound => "target_not_found",
            Self::AmbiguousTarget => "ambiguous_target",
            Self::FrameMismatch => "frame_mismatch",
            Self::RoleDrift => "role_drift",
            Self::AccessibleNameDrift => "accessible_name_drift",
            Self::StructuralDrift => "structural_drift",
            Self::MutationRace => "mutation_race",
            Self::UnsupportedAction => "unsupported_action",
            Self::Cancelled => "cancelled",
            Self::DeadlineExceeded => "deadline_exceeded",
            Self::RevisionExhausted => "revision_exhausted",
            Self::LockPoisoned => "lock_poisoned",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolverError {
    pub code: ErrorCode,
    pub detail: String,
}

impl ResolverError {
    fn new(code: ErrorCode, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for ResolverError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code.as_str(), self.detail)
    }
}

impl Error for ResolverError {}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NodeState {
    node: SemanticNode,
    action_count: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct EngineState {
    session_id: String,
    revisions: Revisions,
    nodes: Vec<NodeState>,
    focused_semantic_id: Option<String>,
}

impl TryFrom<SemanticSnapshot> for EngineState {
    type Error = ResolverError;

    fn try_from(snapshot: SemanticSnapshot) -> Result<Self, Self::Error> {
        snapshot.validate()?;
        Ok(Self {
            session_id: snapshot.session_id,
            revisions: snapshot.revisions,
            nodes: snapshot
                .nodes
                .into_iter()
                .map(|node| NodeState {
                    node,
                    action_count: 0,
                })
                .collect(),
            focused_semantic_id: None,
        })
    }
}

#[derive(Debug)]
pub struct AtomicSemanticResolver {
    state: Mutex<EngineState>,
}

impl AtomicSemanticResolver {
    pub fn new(snapshot: SemanticSnapshot) -> Result<Self, ResolverError> {
        Ok(Self {
            state: Mutex::new(snapshot.try_into()?),
        })
    }

    pub fn snapshot(&self) -> Result<SemanticSnapshot, ResolverError> {
        let state = self
            .state
            .lock()
            .map_err(|_| ResolverError::new(ErrorCode::LockPoisoned, "engine lock poisoned"))?;
        Ok(SemanticSnapshot {
            session_id: state.session_id.clone(),
            revisions: state.revisions,
            nodes: state.nodes.iter().map(|item| item.node.clone()).collect(),
        })
    }

    pub fn resolve_and_act(
        &self,
        target: &TargetBinding,
        action: &SemanticAction,
        deadline: Option<Instant>,
        cancelled: bool,
    ) -> Result<ActionReceipt, ResolverError> {
        self.resolve_and_act_inner(target, action, deadline, cancelled, |_| {})
    }

    fn resolve_and_act_inner<F>(
        &self,
        target: &TargetBinding,
        action: &SemanticAction,
        deadline: Option<Instant>,
        cancelled: bool,
        before_commit: F,
    ) -> Result<ActionReceipt, ResolverError>
    where
        F: FnOnce(&mut EngineState),
    {
        target.validate()?;
        validate_action_value(action)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| ResolverError::new(ErrorCode::LockPoisoned, "engine lock poisoned"))?;

        check_deadline_and_cancellation(deadline, cancelled)?;
        if state.session_id != target.session_id {
            return Err(ResolverError::new(
                ErrorCode::SessionMismatch,
                "target belongs to another PageOwner",
            ));
        }
        check_revisions(state.revisions, target.revisions)?;

        let retained_index = resolve_unique(&state, target)?;
        validate_role_action(&state.nodes[retained_index].node, action)?;
        let retained_node = state.nodes[retained_index].node.clone();
        let retained_count = state.nodes[retained_index].action_count;
        let retained_revisions = state.revisions;
        let retained_session = state.session_id.clone();

        // A production engine must not yield between these points. The hook is
        // private and exists only so the adversarial tests can prove that the
        // immediate revalidation fails closed if state nevertheless changes.
        before_commit(&mut state);

        check_deadline_and_cancellation(deadline, cancelled)?;
        if state.session_id != retained_session || state.revisions != retained_revisions {
            return Err(ResolverError::new(
                ErrorCode::MutationRace,
                "PageOwner identity or revisions changed before action",
            ));
        }
        let current_index = resolve_unique(&state, target)?;
        if current_index != retained_index
            || state.nodes[current_index].node != retained_node
            || state.nodes[current_index].action_count != retained_count
        {
            return Err(ResolverError::new(
                ErrorCode::MutationRace,
                "retained node changed before action",
            ));
        }

        let before = state.revisions.mutation_epoch;
        let after = before.checked_add(1).ok_or_else(|| {
            ResolverError::new(ErrorCode::RevisionExhausted, "mutation epoch exhausted")
        })?;
        apply_one(&mut state, current_index, action)?;
        if state.nodes[current_index].action_count != retained_count + 1 {
            return Err(ResolverError::new(
                ErrorCode::MutationRace,
                "action cardinality was not exactly one",
            ));
        }
        state.revisions.mutation_epoch = after;
        Ok(ActionReceipt {
            session_id: state.session_id.clone(),
            frame_id: state.nodes[current_index].node.frame_id.clone(),
            semantic_id: state.nodes[current_index].node.semantic_id.clone(),
            action: action.kind,
            mutation_epoch_before: before,
            mutation_epoch_after: after,
            action_count: 1,
        })
    }
}

fn validate_text(field: &'static str, value: &str) -> Result<(), ResolverError> {
    if value.is_empty() {
        return Err(ResolverError::new(
            ErrorCode::InvalidRequest,
            format!("{field} must be non-empty"),
        ));
    }
    if value.len() > MAX_TEXT_BYTES {
        return Err(ResolverError::new(
            ErrorCode::InvalidRequest,
            format!("{field} exceeds the configured bound"),
        ));
    }
    Ok(())
}

fn check_deadline_and_cancellation(
    deadline: Option<Instant>,
    cancelled: bool,
) -> Result<(), ResolverError> {
    if cancelled {
        return Err(ResolverError::new(
            ErrorCode::Cancelled,
            "operation was cancelled before action",
        ));
    }
    if deadline.is_some_and(|deadline| Instant::now() >= deadline) {
        return Err(ResolverError::new(
            ErrorCode::DeadlineExceeded,
            "operation deadline expired",
        ));
    }
    Ok(())
}

fn check_revisions(actual: Revisions, expected: Revisions) -> Result<(), ResolverError> {
    let checks = [
        (
            ErrorCode::StaleSessionGeneration,
            expected.session_generation,
            actual.session_generation,
        ),
        (
            ErrorCode::StaleDocumentGeneration,
            expected.document_generation,
            actual.document_generation,
        ),
        (
            ErrorCode::StaleSemanticSnapshot,
            expected.semantic_snapshot_revision,
            actual.semantic_snapshot_revision,
        ),
        (
            ErrorCode::StaleMutationEpoch,
            expected.mutation_epoch,
            actual.mutation_epoch,
        ),
    ];
    for (code, supplied, current) in checks {
        if supplied != current {
            return Err(ResolverError::new(
                code,
                format!("supplied={supplied} current={current}"),
            ));
        }
    }
    Ok(())
}

fn resolve_unique(state: &EngineState, target: &TargetBinding) -> Result<usize, ResolverError> {
    let same_id: Vec<usize> = state
        .nodes
        .iter()
        .enumerate()
        .filter_map(|(index, item)| {
            (item.node.semantic_id == target.semantic_id).then_some(index)
        })
        .collect();
    if same_id.is_empty() {
        return Err(ResolverError::new(
            ErrorCode::TargetNotFound,
            "semantic_id is absent from current snapshot",
        ));
    }
    let same_frame: Vec<usize> = same_id
        .into_iter()
        .filter(|index| state.nodes[*index].node.frame_id == target.frame_id)
        .collect();
    if same_frame.is_empty() {
        return Err(ResolverError::new(
            ErrorCode::FrameMismatch,
            "semantic_id exists only in another frame",
        ));
    }
    if same_frame.len() != 1 {
        return Err(ResolverError::new(
            ErrorCode::AmbiguousTarget,
            "semantic_id resolves to multiple nodes in frame",
        ));
    }
    let index = same_frame[0];
    let node = &state.nodes[index].node;
    if node.role != target.role {
        return Err(ResolverError::new(
            ErrorCode::RoleDrift,
            format!("supplied={:?} current={:?}", target.role, node.role),
        ));
    }
    if node.accessible_name != target.accessible_name {
        return Err(ResolverError::new(
            ErrorCode::AccessibleNameDrift,
            format!(
                "supplied={:?} current={:?}",
                target.accessible_name, node.accessible_name
            ),
        ));
    }
    if node.structural_fingerprint != target.structural_fingerprint {
        return Err(ResolverError::new(
            ErrorCode::StructuralDrift,
            "structural fingerprint changed",
        ));
    }
    if !node.enabled || !node.visible {
        return Err(ResolverError::new(
            ErrorCode::TargetNotFound,
            "resolved node is not actionable",
        ));
    }
    Ok(index)
}

fn validate_action_value(action: &SemanticAction) -> Result<(), ResolverError> {
    let valid = match action.kind {
        ActionKind::Click | ActionKind::Focus => matches!(action.value, ActionValue::None),
        ActionKind::SetValue | ActionKind::InsertText | ActionKind::SelectOption => {
            matches!(action.value, ActionValue::Text(_))
        }
        ActionKind::SetChecked => matches!(action.value, ActionValue::Checked(_)),
    };
    if valid {
        if let ActionValue::Text(value) = &action.value {
            if value.len() > MAX_TEXT_BYTES {
                return Err(ResolverError::new(
                    ErrorCode::InvalidRequest,
                    "action value exceeds the configured bound",
                ));
            }
        }
        Ok(())
    } else {
        Err(ResolverError::new(
            ErrorCode::InvalidRequest,
            "action value does not match action kind",
        ))
    }
}

fn validate_role_action(
    node: &SemanticNode,
    action: &SemanticAction,
) -> Result<(), ResolverError> {
    let allowed = match node.role.as_str() {
        "button" | "link" => matches!(action.kind, ActionKind::Click | ActionKind::Focus),
        "textbox" => matches!(
            action.kind,
            ActionKind::Focus | ActionKind::SetValue | ActionKind::InsertText
        ),
        "checkbox" | "radio" => matches!(
            action.kind,
            ActionKind::Click | ActionKind::SetChecked | ActionKind::Focus
        ),
        "combobox" => matches!(
            action.kind,
            ActionKind::Focus | ActionKind::SetValue | ActionKind::SelectOption
        ),
        "option" => matches!(action.kind, ActionKind::Click | ActionKind::SelectOption),
        "slider" => matches!(action.kind, ActionKind::Focus | ActionKind::SetValue),
        "generic" => matches!(action.kind, ActionKind::Focus),
        _ => false,
    };
    if allowed {
        Ok(())
    } else {
        Err(ResolverError::new(
            ErrorCode::UnsupportedAction,
            format!("{:?} is not allowed for role {:?}", action.kind, node.role),
        ))
    }
}

fn apply_one(
    state: &mut EngineState,
    index: usize,
    action: &SemanticAction,
) -> Result<(), ResolverError> {
    match action.kind {
        ActionKind::Focus => {
            state.focused_semantic_id = Some(state.nodes[index].node.semantic_id.clone());
        }
        ActionKind::Click => {
            if matches!(state.nodes[index].node.role.as_str(), "checkbox" | "radio") {
                let checked = !state.nodes[index].node.checked.unwrap_or(false);
                state.nodes[index].node.checked = Some(checked);
            }
        }
        ActionKind::SetChecked => {
            let ActionValue::Checked(checked) = action.value else {
                return Err(ResolverError::new(
                    ErrorCode::InvalidRequest,
                    "set_checked requires a boolean",
                ));
            };
            state.nodes[index].node.checked = Some(checked);
        }
        ActionKind::SetValue => {
            let ActionValue::Text(value) = &action.value else {
                return Err(ResolverError::new(
                    ErrorCode::InvalidRequest,
                    "set_value requires text",
                ));
            };
            state.nodes[index].node.value.clone_from(value);
        }
        ActionKind::InsertText => {
            let ActionValue::Text(value) = &action.value else {
                return Err(ResolverError::new(
                    ErrorCode::InvalidRequest,
                    "insert_text requires text",
                ));
            };
            let new_len = state.nodes[index]
                .node
                .value
                .len()
                .checked_add(value.len())
                .ok_or_else(|| {
                    ResolverError::new(ErrorCode::InvalidRequest, "text length overflowed")
                })?;
            if new_len > MAX_TEXT_BYTES {
                return Err(ResolverError::new(
                    ErrorCode::InvalidRequest,
                    "resulting text exceeds the configured bound",
                ));
            }
            state.nodes[index].node.value.push_str(value);
        }
        ActionKind::SelectOption => {
            let ActionValue::Text(value) = &action.value else {
                return Err(ResolverError::new(
                    ErrorCode::InvalidRequest,
                    "select_option requires text",
                ));
            };
            state.nodes[index].node.value.clone_from(value);
        }
    }
    state.nodes[index].action_count = state.nodes[index]
        .action_count
        .checked_add(1)
        .ok_or_else(|| ResolverError::new(ErrorCode::RevisionExhausted, "action count exhausted"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    fn node() -> SemanticNode {
        SemanticNode {
            frame_id: "frame-main".to_owned(),
            semantic_id: "submit-primary".to_owned(),
            role: "button".to_owned(),
            accessible_name: "Submit".to_owned(),
            structural_fingerprint: "sha256:button-v1".to_owned(),
            value: String::new(),
            checked: None,
            enabled: true,
            visible: true,
        }
    }

    fn snapshot() -> SemanticSnapshot {
        SemanticSnapshot {
            session_id: "session-1".to_owned(),
            revisions: Revisions {
                session_generation: 1,
                document_generation: 2,
                semantic_snapshot_revision: 3,
                mutation_epoch: 4,
            },
            nodes: vec![node()],
        }
    }

    fn target() -> TargetBinding {
        TargetBinding {
            session_id: "session-1".to_owned(),
            revisions: snapshot().revisions,
            frame_id: "frame-main".to_owned(),
            semantic_id: "submit-primary".to_owned(),
            role: "button".to_owned(),
            accessible_name: "Submit".to_owned(),
            structural_fingerprint: "sha256:button-v1".to_owned(),
        }
    }

    fn assert_code(result: Result<ActionReceipt, ResolverError>, code: ErrorCode) {
        assert_eq!(result.expect_err("operation must fail closed").code, code);
    }

    #[test]
    fn unique_current_node_is_acted_on_exactly_once() {
        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        let receipt = resolver
            .resolve_and_act(
                &target(),
                &SemanticAction::click(),
                Some(Instant::now() + Duration::from_secs(1)),
                false,
            )
            .expect("exact action");
        assert_eq!(receipt.action_count, 1);
        assert_eq!(receipt.mutation_epoch_before, 4);
        assert_eq!(receipt.mutation_epoch_after, 5);
        assert_eq!(resolver.snapshot().expect("snapshot").revisions.mutation_epoch, 5);
    }

    #[test]
    fn ambiguity_and_cross_frame_fallback_fail_closed() {
        let mut duplicate = snapshot();
        duplicate.nodes.push(node());
        let resolver = AtomicSemanticResolver::new(duplicate).expect("resolver");
        assert_code(
            resolver.resolve_and_act(&target(), &SemanticAction::click(), None, false),
            ErrorCode::AmbiguousTarget,
        );

        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        let mut wrong_frame = target();
        wrong_frame.frame_id = "frame-child".to_owned();
        assert_code(
            resolver.resolve_and_act(&wrong_frame, &SemanticAction::click(), None, false),
            ErrorCode::FrameMismatch,
        );
    }

    #[test]
    fn all_revision_layers_are_distinct_failures() {
        let cases = [
            (ErrorCode::StaleSessionGeneration, Revisions { session_generation: 0, ..target().revisions }),
            (ErrorCode::StaleDocumentGeneration, Revisions { document_generation: 1, ..target().revisions }),
            (ErrorCode::StaleSemanticSnapshot, Revisions { semantic_snapshot_revision: 2, ..target().revisions }),
            (ErrorCode::StaleMutationEpoch, Revisions { mutation_epoch: 3, ..target().revisions }),
        ];
        for (code, revisions) in cases {
            let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
            let mut stale = target();
            stale.revisions = revisions;
            assert_code(
                resolver.resolve_and_act(&stale, &SemanticAction::click(), None, false),
                code,
            );
        }
    }

    #[test]
    fn role_name_and_structure_drift_are_never_retargeted() {
        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        let mut drifted = target();
        drifted.role = "link".to_owned();
        assert_code(
            resolver.resolve_and_act(&drifted, &SemanticAction::click(), None, false),
            ErrorCode::RoleDrift,
        );

        let mut drifted = target();
        drifted.accessible_name = "Authorize transfer".to_owned();
        assert_code(
            resolver.resolve_and_act(&drifted, &SemanticAction::click(), None, false),
            ErrorCode::AccessibleNameDrift,
        );

        let mut drifted = target();
        drifted.structural_fingerprint = "sha256:attacker-node".to_owned();
        assert_code(
            resolver.resolve_and_act(&drifted, &SemanticAction::click(), None, false),
            ErrorCode::StructuralDrift,
        );
    }

    #[test]
    fn role_action_policy_blocks_generic_forwarding() {
        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        assert_code(
            resolver.resolve_and_act(
                &target(),
                &SemanticAction::set_value("not-a-button-operation"),
                None,
                false,
            ),
            ErrorCode::UnsupportedAction,
        );
    }

    #[test]
    fn cancellation_and_deadline_precede_action() {
        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        assert_code(
            resolver.resolve_and_act(&target(), &SemanticAction::click(), None, true),
            ErrorCode::Cancelled,
        );
        assert_code(
            resolver.resolve_and_act(
                &target(),
                &SemanticAction::click(),
                Some(Instant::now()),
                false,
            ),
            ErrorCode::DeadlineExceeded,
        );
        assert_eq!(resolver.snapshot().expect("snapshot").revisions.mutation_epoch, 4);
    }

    #[test]
    fn revision_change_at_commit_boundary_is_a_mutation_race() {
        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        let result = resolver.resolve_and_act_inner(
            &target(),
            &SemanticAction::click(),
            None,
            false,
            |state| state.revisions.mutation_epoch += 1,
        );
        assert_code(result, ErrorCode::MutationRace);
    }

    #[test]
    fn retained_node_replacement_is_rejected_before_action() {
        let resolver = AtomicSemanticResolver::new(snapshot()).expect("resolver");
        let result = resolver.resolve_and_act_inner(
            &target(),
            &SemanticAction::click(),
            None,
            false,
            |state| state.nodes[0].node.structural_fingerprint = "sha256:button-v2".to_owned(),
        );
        assert_code(result, ErrorCode::StructuralDrift);
        assert_eq!(resolver.snapshot().expect("snapshot").revisions.mutation_epoch, 4);
    }

    #[test]
    fn textbox_actions_are_typed_and_bounded() {
        let mut textbox = node();
        textbox.semantic_id = "query".to_owned();
        textbox.role = "textbox".to_owned();
        textbox.accessible_name = "Search".to_owned();
        textbox.structural_fingerprint = "sha256:textbox-v1".to_owned();
        let mut semantic_snapshot = snapshot();
        semantic_snapshot.nodes = vec![textbox];
        let resolver = AtomicSemanticResolver::new(semantic_snapshot).expect("resolver");
        let mut textbox_target = target();
        textbox_target.semantic_id = "query".to_owned();
        textbox_target.role = "textbox".to_owned();
        textbox_target.accessible_name = "Search".to_owned();
        textbox_target.structural_fingerprint = "sha256:textbox-v1".to_owned();
        resolver
            .resolve_and_act(
                &textbox_target,
                &SemanticAction::set_value("hepta"),
                None,
                false,
            )
            .expect("set value");
        assert_eq!(resolver.snapshot().expect("snapshot").nodes[0].value, "hepta");
    }

    #[test]
    fn mutation_epoch_exhaustion_writes_nothing() {
        let mut exhausted = snapshot();
        exhausted.revisions.mutation_epoch = u64::MAX;
        let mut exhausted_target = target();
        exhausted_target.revisions.mutation_epoch = u64::MAX;
        let resolver = AtomicSemanticResolver::new(exhausted).expect("resolver");
        assert_code(
            resolver.resolve_and_act(
                &exhausted_target,
                &SemanticAction::click(),
                None,
                false,
            ),
            ErrorCode::RevisionExhausted,
        );
        assert_eq!(
            resolver.snapshot().expect("snapshot").revisions.mutation_epoch,
            u64::MAX
        );
    }
}
