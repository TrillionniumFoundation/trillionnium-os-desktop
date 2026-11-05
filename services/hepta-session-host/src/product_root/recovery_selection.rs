//! Explicit original-record selectors. Inputs choose records; they confer no authority.
use super::{Result, config::Inputs};
use serde::Serialize;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub(crate) enum RecoverySelection {
    ExactOperation {
        operation_id: String,
    },
    LatestRecordedOriginalNotes,
    ExactDesktopOperations {
        notes_operation_id: String,
        calculator_operation_id: String,
    },
    LatestRecordedOriginalDesktop,
}

impl RecoverySelection {
    pub(crate) fn from_arguments(
        mut args: impl Iterator<Item = std::ffi::OsString>,
    ) -> Result<Self> {
        let selection = match args.next().as_deref().and_then(std::ffi::OsStr::to_str) {
            Some("--operation-id") => Self::ExactOperation {
                operation_id: next_text(&mut args, "original operation selector")?,
            },
            Some("--latest-original-notes") => Self::LatestRecordedOriginalNotes,
            _ => return Err("recovery requires an explicit original operation selector".into()),
        };
        if args.next().is_some() {
            return Err("unexpected or competing recovery selector".into());
        }
        selection.validate()?;
        Ok(selection)
    }

    /// A generation is a locator, not a claim of Current. Existing::open checks
    /// the original signed writer, physical retirement and Fleet spawn history.
    pub(crate) fn from_desktop_arguments(
        mut args: impl Iterator<Item = std::ffi::OsString>,
    ) -> Result<(u64, Self)> {
        if args.next().as_deref() != Some(std::ffi::OsStr::new("--previous-generation")) {
            return Err("joint recovery requires an explicit previous generation".into());
        }
        let generation: u64 = next_text(&mut args, "previous generation")?.parse()?;
        successor_generation(generation)?;
        let selection = match args.next().as_deref().and_then(std::ffi::OsStr::to_str) {
            Some("--latest-original-desktop") => Self::LatestRecordedOriginalDesktop,
            Some("--notes-operation-id") => {
                let notes_operation_id = next_text(&mut args, "original Notes operation")?;
                if args.next().as_deref() != Some(std::ffi::OsStr::new("--calculator-operation-id"))
                {
                    return Err("joint exact selection requires the Calculator operation".into());
                }
                Self::ExactDesktopOperations {
                    notes_operation_id,
                    calculator_operation_id: next_text(&mut args, "original Calculator operation")?,
                }
            }
            _ => {
                return Err("joint recovery requires its explicit original Desktop selector".into());
            }
        };
        if args.next().is_some() {
            return Err("unexpected or competing joint recovery selector".into());
        }
        selection.validate()?;
        Ok((generation, selection))
    }

    pub(super) fn validate(&self) -> Result<()> {
        let ids: Vec<&str> = match self {
            Self::ExactOperation { operation_id } => vec![operation_id],
            Self::ExactDesktopOperations {
                notes_operation_id,
                calculator_operation_id,
            } => {
                if notes_operation_id == calculator_operation_id {
                    return Err("distinct original App operations required".into());
                }
                vec![notes_operation_id, calculator_operation_id]
            }
            Self::LatestRecordedOriginalNotes | Self::LatestRecordedOriginalDesktop => Vec::new(),
        };
        for id in ids {
            codex_hepta_types::StableId::new(id)?;
        }
        Ok(())
    }

    pub(super) fn validate_for(&self, inputs: &Inputs) -> Result<()> {
        self.validate()?;
        let desktop = matches!(
            self,
            Self::ExactDesktopOperations { .. } | Self::LatestRecordedOriginalDesktop
        );
        if desktop != inputs.is_desktop() {
            return Err("recovery selector differs from the original target profile".into());
        }
        Ok(())
    }

    pub(super) fn notes(&self) -> codex_hepta_agentd::AgentdNotesRecoverySelector {
        use codex_hepta_agentd::AgentdNotesRecoverySelector as Selector;
        match self {
            Self::ExactOperation { operation_id } => Selector::ExactOperation {
                operation_id: operation_id.clone(),
            },
            Self::ExactDesktopOperations {
                notes_operation_id, ..
            } => Selector::ExactOperation {
                operation_id: notes_operation_id.clone(),
            },
            Self::LatestRecordedOriginalNotes | Self::LatestRecordedOriginalDesktop => {
                Selector::LatestRecordedOriginalNotes
            }
        }
    }

    pub(super) fn calculator(
        &self,
    ) -> Result<codex_hepta_agentd::AgentdCalculatorRecoverySelector> {
        use codex_hepta_agentd::AgentdCalculatorRecoverySelector as Selector;
        match self {
            Self::ExactDesktopOperations {
                calculator_operation_id,
                ..
            } => Ok(Selector::ExactOperation {
                operation_id: calculator_operation_id.clone(),
            }),
            Self::LatestRecordedOriginalDesktop => Ok(Selector::LatestRecordedOriginalCalculator),
            _ => Err("Notes-only selection has no Calculator recovery authority".into()),
        }
    }
}

pub(super) fn successor_generation(previous: u64) -> Result<u64> {
    if previous == 0 {
        return Err("original generation must be positive".into());
    }
    previous
        .checked_add(1)
        .ok_or_else(|| "original generation exhausted".into())
}

pub(super) fn generation_directory(
    admin: &std::path::Path,
    generation: u64,
) -> Result<std::path::PathBuf> {
    successor_generation(generation)?;
    Ok(if generation == 1 {
        admin.to_path_buf()
    } else {
        admin.join(format!("recovery-{generation}"))
    })
}

fn next_text(args: &mut impl Iterator<Item = std::ffi::OsString>, name: &str) -> Result<String> {
    args.next()
        .ok_or_else(|| format!("missing {name}"))?
        .into_string()
        .map_err(|_| format!("{name} must be UTF-8").into())
}

#[cfg(test)]
#[path = "recovery_selection_tests.rs"]
mod tests;
