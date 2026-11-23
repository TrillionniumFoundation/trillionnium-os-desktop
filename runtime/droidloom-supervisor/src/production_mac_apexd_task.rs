//! MAC observation of one actually issued original apexd task.
//! The namespace owner supplies the executable, original thread PIDFD and
//! approved default graph. This module cannot issue that task or a request,
//! choose a PID, adopt a namespace, or authorize a loop/mount operation.
use super::*;
use crate::production_execution::RuntimeMacOwner;
use crate::production_namespace::{ActualApexdGeneration, ActualApexdTask};

pub(super) const APEXD_CONTEXT: &str = "u:r:apexd:s0";

pub(super) fn fixed_apexd_identity(selinux: &[u8], apparmor: &[u8]) -> Result<()> {
    require(
        context_matches(selinux, APEXD_CONTEXT) && apparmor == AA_ANDROID,
        "original apexd must retain its exact SELinux and enforcing Android AppArmor roles",
    )
}

fn original_pair<'a>(
    owner: &'a RuntimeMacOwner,
    task: &ActualApexdTask,
) -> Result<(&'a MacPreflight, &'a ProductionSelection)> {
    original_owner(task.require_owner(owner))?;
    original_owner(task.revalidate_kernel())?;
    let selected = original_owner(task.selection())?;
    let (mac, selection) = owner
        .objects()
        .map_err(|error| MacError::Owner(error.to_string()))?;
    require(
        std::ptr::eq(selected, selection),
        "apexd task must borrow the same original selection object",
    )?;
    owner
        .require_pair(mac, selection)
        .map_err(|error| MacError::Owner(error.to_string()))?;
    mac.revalidate(selection)?;
    Ok((mac, selection))
}

fn observe(
    owner: &RuntimeMacOwner,
    task: &ActualApexdTask,
) -> Result<(
    ProviderBinding,
    ActualApexdGeneration,
    host_proc::ApexdThreadBinding,
)> {
    let (mac, selection) = original_pair(owner, task)?;
    let generation = original_owner(task.generation())?;
    require(
        mac.scoped_contexts(),
        "original apexd requires the actual selected host proc provider",
    )?;
    let view = mac.host_proc.as_ref().ok_or(MacError::Rejected(
        "original apexd lost its selected host proc view",
    ))?;
    let thread = view.for_apexd(&mac.loaded, task)?;
    // This also reads actual NNP and seccomp state from the original held
    // thread proc directory; it does not substitute a leader's status.
    process_confinement_state(task.proc_directory())?;
    original_owner(task.revalidate_kernel())?;
    original_owner(task.require_owner(owner))?;
    require(
        original_owner(task.generation())? == generation,
        "original apexd task/default graph generation changed across MAC observation",
    )?;
    let (again, selected_again) = original_pair(owner, task)?;
    require(
        std::ptr::eq(again, mac) && std::ptr::eq(selected_again, selection),
        "original apexd MAC/selection pair changed",
    )?;
    mac.loaded.stable_epoch()?;
    Ok((mac.binding(), generation, thread))
}

/// A same-thread observation, retaining the original provider/selection Rc.
/// Every later use requires the same opaque actual task again. Neither the
/// stored generation nor this value constructs a task, request or guest FD.
pub(crate) struct MacApexdTaskWitness {
    owner: RuntimeMacOwner,
    provider: ProviderBinding,
    generation: ActualApexdGeneration,
    thread: host_proc::ApexdThreadBinding,
}

impl MacApexdTaskWitness {
    pub(crate) fn observe(owner: &RuntimeMacOwner, task: &ActualApexdTask) -> Result<Self> {
        let (provider, generation, thread) = observe(owner, task)?;
        let value = Self {
            owner: owner.clone(),
            provider,
            generation,
            thread,
        };
        value.revalidate(task)?;
        Ok(value)
    }

    pub(crate) fn revalidate(&self, task: &ActualApexdTask) -> Result<()> {
        original_owner(task.require_owner(&self.owner))?;
        let (provider, generation, thread) = observe(&self.owner, task)?;
        require(
            provider == self.provider && generation == self.generation && thread == self.thread,
            "original apexd thread, namespaces, generation or policy provider changed",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apexd_task_label_gate_rejects_init_and_peer_substitution() {
        fixed_apexd_identity(b"u:r:apexd:s0\0", AA_ANDROID).unwrap();
        for (selinux, apparmor) in [
            (b"u:r:init:s0\0".as_slice(), AA_ANDROID),
            (b"u:r:apexd:s0\0".as_slice(), AA_BROKER),
            (b"u:r:apexd:s0extra\0".as_slice(), AA_ANDROID),
            (b"u:r:linkerconfig:s0\0".as_slice(), AA_ANDROID),
        ] {
            assert!(fixed_apexd_identity(selinux, apparmor).is_err());
        }
    }
}
