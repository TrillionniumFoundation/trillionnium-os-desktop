//! Same-owner coordinator for the fixed original linkerconfig command.
//!
//! The listener, original input roles, init, MAC provider and peer are borrowed
//! from one actual executed tree. Failure retires that whole tree, not merely
//! the command leader. A completed command is retained for final admission;
//! it is not proof of APEX mounts, generated files, guest profiles or Ready.

use super::activation_broker::{CompletedLinkerconfig, FailedSession};
use super::activation_peer::{OriginalLinkerInput, TrampolineInput};
use super::*;
use crate::production_activation_protocol as wire;

enum AttemptFailure {
    Before(NamespaceError),
    Protocol(FailedSession),
}

impl From<NamespaceError> for AttemptFailure {
    fn from(value: NamespaceError) -> Self {
        Self::Before(value)
    }
}

fn command_budget(
    clock_ns: u64,
    now: Instant,
    original_deadline: Instant,
) -> Result<(Instant, u64)> {
    let remaining = original_deadline
        .checked_duration_since(now)
        .filter(|left| !left.is_zero())
        .ok_or(NamespaceError::Rejected(
            "activation preparation deadline expired",
        ))?
        .min(Duration::from_nanos(wire::MAX_COMMAND_NS));
    let budget = u64::try_from(remaining.as_nanos())
        .map_err(|_| NamespaceError::Rejected("activation budget overflow"))?;
    let deadline_ns = clock_ns
        .checked_add(budget)
        .ok_or(NamespaceError::Rejected("activation clock overflow"))?;
    Ok((now + remaining, deadline_ns))
}

impl ExecutedNamespaces {
    /// Run only the original selected linkerconfig through the original
    /// private listener. There is no external socket, command, PID or elapsed
    /// success argument. Preparation's deadline is never extended.
    pub(crate) fn activate_linkerconfig(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted = (|| -> std::result::Result<CompletedLinkerconfig, AttemptFailure> {
            if self.linkerconfig.is_some() {
                return Err(
                    NamespaceError::Rejected("original linkerconfig was already executed").into(),
                );
            }
            self.verify_prepared_exec(selection, prepared)?;
            // Read the monotonic wire clock first. The later Instant read
            // makes the converted deadline conservative by the read latency.
            let clock_ns = activation_channel::monotonic_ns()?;
            let (deadline, deadline_ns) =
                command_budget(clock_ns, Instant::now(), prepared.deadline())?;
            let init = self.original_init_witness(selection)?;
            let owner = init.namespace_witness()?;
            let devices = match self.tree.devices.as_ref() {
                Some(DeviceMounts::Activation(value)) => value,
                _ => {
                    return Err(NamespaceError::Rejected(
                        "executed tree has no original activation DEV",
                    )
                    .into());
                }
            };
            let listener = devices
                .executed_listener(&owner, &init, deadline)
                .map_err(|error| NamespaceError::DeviceResource(error.to_string()))?;
            let mac = prepared
                .activation_mac(&init)
                .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
            let runtime = init.runtime_owner()?;
            let (trampoline, original) = runtime
                .linkerconfig_inputs(&init)
                .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?
                .into_roles();
            let trampoline = TrampolineInput::observe(&init, trampoline, deadline_ns)?;
            let original = OriginalLinkerInput::observe(&init, original, deadline_ns)?;
            let connection = listener
                .accept(mac, deadline)
                .map_err(|error| NamespaceError::DeviceResource(error.to_string()))?;
            let peer = OwnedActivationPeer::observe(&init, &connection, &trampoline)?;
            let completed = activation_broker::run(&init, &peer, &original, mac, deadline_ns)
                .map_err(AttemptFailure::Protocol)?;
            completed.revalidate(&init, deadline_ns)?;
            if Instant::now() >= deadline {
                return Err(NamespaceError::Rejected(
                    "original linkerconfig completion exceeded its deadline",
                )
                .into());
            }
            Ok(completed)
        })();

        match attempted {
            Ok(completed) => {
                self.linkerconfig = Some(completed);
                Ok(self)
            }
            Err(AttemptFailure::Before(error)) => {
                // All transient borrows have ended. The same owner consumes
                // retirement; a failed retirement retains its existing quarantine.
                match self.retire() {
                    Ok(_) => Err(error),
                    Err(retirement) => Err(NamespaceError::RuntimeResource(format!(
                        "activation failed: {error}; whole-tree retirement unproven: {retirement}"
                    ))),
                }
            }
            Err(AttemptFailure::Protocol(failed)) => {
                let retired = failed.retire_owned_tree(self);
                let tree = match retired.tree_retirement {
                    Ok(_) => "retired".to_owned(),
                    Err(error) => format!("unproven: {error}"),
                };
                let command = match retired.command_retirement {
                    Some(Ok(status)) => format!("retired with raw status {status}"),
                    Some(Err(error)) => format!("unproven: {error}"),
                    None => "not received".to_owned(),
                };
                Err(NamespaceError::RuntimeResource(format!(
                    "original linkerconfig failed: {}; whole tree {tree}; command {command}; diagnostic bytes {}",
                    retired.source,
                    retired.diagnostics.len()
                )))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn activation_owner_preserves_original_deadline_and_fixed_command_limit() {
        let now = Instant::now();
        for nanos in [1_u64, 50_000_000, wire::MAX_COMMAND_NS, 120_000_000_000] {
            let outer = now + Duration::from_nanos(nanos);
            let (deadline, wire_deadline) = command_budget(91, now, outer).unwrap();
            assert!(deadline <= outer);
            assert_eq!(
                deadline.duration_since(now).as_nanos(),
                nanos.min(wire::MAX_COMMAND_NS) as u128
            );
            assert_eq!(wire_deadline, 91 + nanos.min(wire::MAX_COMMAND_NS));
        }
        assert!(command_budget(91, now, now).is_err());
        assert!(command_budget(91, now, now - Duration::from_nanos(1)).is_err());
        assert!(command_budget(u64::MAX, now, now + Duration::from_nanos(1)).is_err());
    }
}
