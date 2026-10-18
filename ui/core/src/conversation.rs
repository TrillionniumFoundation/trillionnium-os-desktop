//! Local chat context values. They carry no operation, permission or issuer data.
//! A saved quote is historical text/metadata, never a persisted live observation.

use crate::hepta::{HeptaConnectionState, HeptaProjection, HeptaRuntimeObservation};
use crate::{AppKind, TaskRecord, TaskState, Workspace};
use serde::{Deserialize, Serialize};

pub const MAX_LOCAL_DRAFTS: usize = 127;
pub const MAX_DRAFT_BYTES: usize = 16 * 1024;
pub const MAX_DRAFT_CONTEXTS: usize = 8;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostTaskKey {
    pub session_instance: String,
    pub task_id: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostTaskContext {
    pub key: HostTaskKey,
    pub workspace: Workspace,
    pub app: AppKind,
    pub quoted_state: TaskState,
    pub quoted_pid: Option<u32>,
    /// Full Session snapshot time, not the task's last lifecycle change.
    pub sampled_unix_ms: u64,
    pub task_updated_unix_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HeptaRuntimeContext {
    /// Identity of the observing Session, independent of host task IDs.
    pub session_instance: String,
    pub agent_id: String,
    pub spawn_generation: u64,
    pub process_id: u32,
    pub quoted_current_generation: u64,
    pub quoted_lifecycle: String,
    pub sampled_unix_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ContextRef {
    HostTask(HostTaskContext),
    HeptaRuntime(HeptaRuntimeContext),
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LocalDraft {
    pub workspace: Workspace,
    pub text: String,
    pub contexts: Vec<ContextRef>,
}

impl LocalDraft {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.text.trim().is_empty() || self.text.len() > MAX_DRAFT_BYTES {
            return Err("Draft exceeds 16 KiB or is empty");
        }
        if self.contexts.len() > MAX_DRAFT_CONTEXTS {
            return Err("Draft has more than 8 context references");
        }
        for (index, context) in self.contexts.iter().enumerate() {
            context.validate(self.workspace)?;
            if self.contexts[..index]
                .iter()
                .any(|old| old.same_source(context))
            {
                return Err("Duplicate context source in local draft");
            }
        }
        Ok(())
    }
}

fn valid_instance(instance: &str) -> bool {
    instance.len() == 32
        && instance
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

fn bounded_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
}

impl ContextRef {
    pub fn host_task(session_instance: &str, task: &TaskRecord, sampled_unix_ms: u64) -> Self {
        Self::HostTask(HostTaskContext {
            key: HostTaskKey {
                session_instance: session_instance.into(),
                task_id: task.id,
            },
            workspace: task.workspace,
            app: task.app,
            quoted_state: task.state,
            quoted_pid: task.pid,
            sampled_unix_ms,
            task_updated_unix_ms: task.updated_unix_ms,
        })
    }

    pub fn hepta_runtime(session_instance: &str, observation: &HeptaRuntimeObservation) -> Self {
        Self::HeptaRuntime(HeptaRuntimeContext {
            session_instance: session_instance.into(),
            agent_id: observation.agent_id.clone(),
            spawn_generation: observation.spawn_generation,
            process_id: observation.health.process_id,
            quoted_current_generation: observation.current_generation,
            quoted_lifecycle: observation.health.lifecycle.clone(),
            sampled_unix_ms: observation.sampled_unix_ms,
        })
    }

    pub fn same_source(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::HostTask(a), Self::HostTask(b)) => a.key == b.key,
            (Self::HeptaRuntime(a), Self::HeptaRuntime(b)) => {
                a.session_instance == b.session_instance
                    && a.agent_id == b.agent_id
                    && a.spawn_generation == b.spawn_generation
                    && a.process_id == b.process_id
            }
            _ => false,
        }
    }

    pub fn validate(&self, workspace: Workspace) -> Result<(), &'static str> {
        match self {
            Self::HostTask(context) => {
                if !valid_instance(&context.key.session_instance) || context.key.task_id == 0 {
                    return Err("Invalid host task source identity");
                }
                if context.workspace != workspace {
                    return Err("Host task context belongs to another workspace");
                }
                if context.quoted_pid == Some(0) {
                    return Err("Invalid quoted host PID");
                }
            }
            Self::HeptaRuntime(context) => {
                if !valid_instance(&context.session_instance)
                    || !bounded_identifier(&context.agent_id)
                    || !bounded_identifier(&context.quoted_lifecycle)
                    || context.process_id == 0
                    || context.quoted_current_generation < context.spawn_generation
                {
                    return Err("Invalid Hepta runtime source identity or quote");
                }
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ContextUnavailable {
    NotObserved,
    SessionChanged,
    SourceUnavailable,
    TaskNotInSnapshot,
    TaskMetadataChanged,
    RuntimeChanged,
}

impl ContextUnavailable {
    pub fn label(self) -> &'static str {
        match self {
            Self::NotObserved => "HISTORICAL QUOTE · source not observed in this Shell",
            Self::SessionChanged => "HISTORICAL QUOTE · Session changed; reference not rebound",
            Self::SourceUnavailable => "HISTORICAL QUOTE · current source state unknown",
            Self::TaskNotInSnapshot => {
                "HISTORICAL QUOTE · task absent from current snapshot; outcome unknown"
            }
            Self::TaskMetadataChanged => {
                "HISTORICAL QUOTE · task metadata does not match reference"
            }
            Self::RuntimeChanged => "HISTORICAL QUOTE · original runtime source changed",
        }
    }
}

/// `snapshot_current` must come from both source and local receipt ages of
/// the complete snapshot. An action response cannot renew this observation.
pub fn resolve_host_task<'a>(
    reference: &HostTaskContext,
    session_instance: Option<&str>,
    tasks: &'a [TaskRecord],
    snapshot_current: bool,
) -> Result<&'a TaskRecord, ContextUnavailable> {
    let Some(instance) = session_instance else {
        return Err(ContextUnavailable::NotObserved);
    };
    if instance != reference.key.session_instance {
        return Err(ContextUnavailable::SessionChanged);
    }
    if !snapshot_current {
        return Err(ContextUnavailable::SourceUnavailable);
    }
    let task = tasks
        .iter()
        .find(|task| task.id == reference.key.task_id)
        .ok_or(ContextUnavailable::TaskNotInSnapshot)?;
    if task.workspace != reference.workspace || task.app != reference.app {
        return Err(ContextUnavailable::TaskMetadataChanged);
    }
    Ok(task)
}

/// The Shell expires this projection before painting, using the same dual
/// age predicate as the detailed Hepta page. Never infer a host task link.
pub fn resolve_hepta_runtime<'a>(
    reference: &HeptaRuntimeContext,
    session_instance: Option<&str>,
    projection: &'a HeptaProjection,
) -> Result<&'a HeptaRuntimeObservation, ContextUnavailable> {
    let Some(instance) = session_instance else {
        return Err(ContextUnavailable::NotObserved);
    };
    if instance != reference.session_instance {
        return Err(ContextUnavailable::SessionChanged);
    }
    let Some(observed) = &projection.last_observation else {
        return Err(ContextUnavailable::NotObserved);
    };
    if observed.agent_id != reference.agent_id
        || observed.spawn_generation != reference.spawn_generation
        || observed.health.process_id != reference.process_id
    {
        return Err(ContextUnavailable::RuntimeChanged);
    }
    if projection.connection != HeptaConnectionState::Observed {
        return Err(ContextUnavailable::SourceUnavailable);
    }
    Ok(observed)
}

#[cfg(test)]
mod tests {
    use super::*;
    const A: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const B: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    #[test]
    fn reused_task_number_in_new_session_never_rebinds_or_changes_quote() {
        let task = TaskRecord::new(1, Workspace::Research, AppKind::Notes);
        let quote = ContextRef::host_task(A, &task, 20_000);
        let ContextRef::HostTask(reference) = &quote else {
            unreachable!()
        };
        let mut new_task = task.clone();
        new_task.state = TaskState::Completed;
        assert_eq!(
            resolve_host_task(reference, Some(B), &[new_task], true).unwrap_err(),
            ContextUnavailable::SessionChanged
        );
        assert_eq!(reference.quoted_state, TaskState::Pending);
    }

    #[test]
    fn missing_task_is_unknown_and_only_matching_full_snapshot_resolves() {
        let task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        let ContextRef::HostTask(reference) = ContextRef::host_task(A, &task, 20_000) else {
            unreachable!()
        };
        assert_eq!(
            resolve_host_task(&reference, Some(A), &[], true).unwrap_err(),
            ContextUnavailable::TaskNotInSnapshot
        );
        assert_eq!(
            resolve_host_task(&reference, Some(A), &[task.clone()], false).unwrap_err(),
            ContextUnavailable::SourceUnavailable
        );
        let tasks = vec![task];
        assert_eq!(
            resolve_host_task(&reference, Some(A), &tasks, true)
                .unwrap()
                .id,
            1
        );
        let mut other = tasks[0].clone();
        other.workspace = Workspace::Build;
        assert_eq!(
            resolve_host_task(&reference, Some(A), &[other], true).unwrap_err(),
            ContextUnavailable::TaskMetadataChanged
        );
    }

    #[test]
    fn typed_draft_round_trip_preserves_unicode_and_source_and_rejects_cross_workspace() {
        let task = TaskRecord::new(42, Workspace::Research, AppKind::Notes);
        let mut draft = LocalDraft {
            workspace: Workspace::Research,
            text: "你好，研究这份笔记 📝".into(),
            contexts: vec![ContextRef::host_task(A, &task, 20_000)],
        };
        draft.validate().unwrap();
        let bytes = serde_json::to_vec(&draft).unwrap();
        assert_eq!(serde_json::from_slice::<LocalDraft>(&bytes).unwrap(), draft);
        draft.workspace = Workspace::Build;
        assert!(draft.validate().is_err());
    }

    #[test]
    fn runtime_context_tracks_one_original_source_independently_of_host_tasks() {
        use crate::hepta::HeptaHealthObservation;
        let observation = HeptaRuntimeObservation {
            sampled_unix_ms: 20_000,
            agent_id: "11111111-1111-4111-8111-111111111111".into(),
            spawn_generation: 1,
            current_generation: 2,
            health: HeptaHealthObservation {
                ready: true,
                promotion_ready: true,
                fenced: false,
                lifecycle: "running".into(),
                process_id: 42,
            },
            capabilities: vec![],
            capabilities_truncated: false,
            events: vec![],
            events_omitted_from_view: 0,
            next_cursor: 0,
            latest_cursor: 0,
            history_gap: false,
            source_changed: false,
        };
        let ContextRef::HeptaRuntime(reference) = ContextRef::hepta_runtime(A, &observation) else {
            unreachable!()
        };
        let mut projection = HeptaProjection {
            connection: HeptaConnectionState::Observed,
            last_attempt_unix_ms: Some(20_000),
            error_code: None,
            last_observation: Some(observation),
            run: None,
        };
        projection
            .last_observation
            .as_mut()
            .unwrap()
            .current_generation = 3;
        assert_eq!(
            resolve_hepta_runtime(&reference, Some(A), &projection)
                .unwrap()
                .current_generation,
            3
        );
        projection.mark_unavailable("unavailable");
        assert_eq!(
            resolve_hepta_runtime(&reference, Some(A), &projection).unwrap_err(),
            ContextUnavailable::SourceUnavailable
        );
        projection.connection = HeptaConnectionState::Observed;
        projection
            .last_observation
            .as_mut()
            .unwrap()
            .spawn_generation = 5;
        assert_eq!(
            resolve_hepta_runtime(&reference, Some(A), &projection).unwrap_err(),
            ContextUnavailable::RuntimeChanged
        );
        assert_eq!(
            resolve_hepta_runtime(&reference, Some(B), &projection).unwrap_err(),
            ContextUnavailable::SessionChanged
        );
        assert_eq!(reference.spawn_generation, 1);
    }

    #[test]
    fn serialized_local_context_cannot_add_authority_fields() {
        let json = r#"{"workspace":"personal","text":"draft","contexts":[],"objective":"execute"}"#;
        assert!(serde_json::from_str::<LocalDraft>(json).is_err());
        let task = TaskRecord::new(1, Workspace::Personal, AppKind::Notes);
        let mut context = serde_json::to_value(ContextRef::host_task(A, &task, 20_000)).unwrap();
        context
            .as_object_mut()
            .unwrap()
            .insert("grant".into(), serde_json::json!(true));
        assert!(serde_json::from_value::<ContextRef>(context).is_err());
    }
}
