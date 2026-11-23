//! The one original bootstrap bind between initial namespace restoration and
//! the later activation phases. It is not an APEX payload activation receipt.
use super::*;

impl ExecutedNamespaces {
    pub(crate) fn service_original_init_bootstrap_apex_bind(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted = (|| -> Result<()> {
            self.verify_prepared_exec(selection, prepared)?;
            {
                let init = self.original_init_witness(selection)?;
                let child = self
                    .tree
                    .init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?;
                let listener =
                    self.tree
                        .apex_notifications
                        .as_ref()
                        .ok_or(NamespaceError::Rejected(
                            "bootstrap bind original listener absent",
                        ))?;
                let mount_owner = self.tree.witness()?;
                let mount_actors = self
                    .tree
                    .runtime
                    .as_ref()
                    .ok_or(NamespaceError::Rejected(
                        "bootstrap bind original runtime absent",
                    ))?
                    .native_mount_actor_guard(&mount_owner)
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                let request = listener.original_init_bootstrap_bind(
                    child,
                    &init,
                    prepared.deadline(),
                    mount_owner,
                    mount_actors,
                )?;
                let mac = prepared
                    .activation_mac(&init)
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                request.execute(&init, mac)?;
                let errno = request.complete(&init)?;
                if errno != 0 {
                    return Err(io::Error::from_raw_os_error(errno).into());
                }
            }
            self.verify_prepared_exec(selection, prepared)?;
            Ok(())
        })();
        match attempted {
            Ok(()) => Ok(self),
            Err(error) => {
                if self.retire().is_err() {
                    Err(NamespaceError::RetirementUnproven)
                } else {
                    Err(error)
                }
            }
        }
    }
}
