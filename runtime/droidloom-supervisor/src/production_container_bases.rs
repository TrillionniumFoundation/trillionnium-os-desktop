//! The namespace and mounted bases stay with their actual owner. Selecting an
//! entry happens after this boundary; it cannot create an execution identity.
use super::*;
use crate::production_execution::PreparedExecution;

pub(super) struct ContainerBases {
    tree: IsolatedNamespaces,
    preparation: PreparedExecution,
}

impl ContainerBases {
    pub(super) fn prepare(
        tree: IsolatedNamespaces,
        preparation: PreparedExecution,
        selection: &ProductionSelection,
        step: &impl Fn(&str) -> Result<()>,
    ) -> Result<Self> {
        step("Preparing the selected immutable Android bases...")?;
        let bases = {
            let owner = tree.witness().map_err(rejected)?;
            preparation
                .revalidate_tree(selection, &owner)
                .map_err(rejected)?;
            let verified = VerifiedCohort::load(&owner).map_err(rejected)?;
            PreparedMounts::prepare(&owner, verified).map_err(rejected)?
        };
        step("Preparing the selected original persistent data and metadata...")?;
        let data = PreparedPersistentData::prepare(
            &tree.witness().map_err(rejected)?,
            selection,
            &preparation,
        )
        .map_err(rejected)?;
        let tree = tree
            .attach_persistent_base(bases, data, selection, &preparation)
            .map_err(rejected)?;
        step("Preparing private device and process filesystems...")?;
        let devices = preparation
            .prepare_activation_devices(selection, &tree.witness().map_err(rejected)?)
            .map_err(rejected)?;
        let tree = tree
            .attach_activation_devices(devices, selection, &preparation)
            .map_err(rejected)?;
        let tree = tree.prepare_process_filesystems().map_err(rejected)?;
        let tree = tree.prepare_private_binder().map_err(rejected)?;
        let tree = tree.prepare_writable_proc().map_err(rejected)?;
        step("Checking the exact owned cgroup hierarchy...")?;
        tree.configure_cgroup_hierarchy().map_err(rejected)?;
        preparation
            .revalidate_tree(selection, &tree.witness().map_err(rejected)?)
            .map_err(rejected)?;
        Ok(Self { tree, preparation })
    }

    /// Transfer the existing tree only into the original stock-init backend.
    /// The other entry must obtain a matching real platform role and scope.
    pub(super) fn into_original(
        self,
        selection: &ProductionSelection,
    ) -> Result<(IsolatedNamespaces, PreparedExecution)> {
        if selection
            .host_managed_launcher()
            .map_err(rejected)?
            .is_some()
        {
            return Err(rejected(
                "the host-managed selection cannot execute the stock Android init",
            ));
        }
        self.preparation
            .revalidate_tree(selection, &self.tree.witness().map_err(rejected)?)
            .map_err(rejected)?;
        Ok((self.tree, self.preparation))
    }
}
