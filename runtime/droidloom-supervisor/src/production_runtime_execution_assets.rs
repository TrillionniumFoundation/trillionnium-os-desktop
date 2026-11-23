//! Explicit root-selected, exact-image policy for the final original init.

use super::*;
use crate::production_execution_profile as profile;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ExecutionDeclaration {
    scope: String,
}

impl ExecutionDeclaration {
    pub(super) fn validate(&self, runtime: &RuntimeDeclaration) -> Result<()> {
        self.validate_images(&runtime.source_system, &runtime.init)?;
        profile::apex_inputs::validate(&runtime.apexes).map_err(MountError::Rejected)
    }

    fn validate_images(&self, system: &ImageDeclaration, init: &ImageDeclaration) -> Result<()> {
        require(
            self.scope == profile::SCOPE
                && system.bytes == profile::SYSTEM_BYTES
                && system.sha256 == profile::SYSTEM_SHA256
                && init.bytes == profile::INIT_BYTES
                && init.sha256 == profile::INIT_SHA256,
            "scoped Android execution requires the exact original CP3A system and init",
        )
    }
}

/// Issued by the actual selected runtime owner, never from a caller mask,
/// namespace FD, PID or serialized qualification. It is neither Clone nor
/// Deserialize and must still be joined to the same owned namespace.
pub(crate) struct RuntimeExecProfile {
    userns: (u64, u64),
    host_uid: u32,
    cohort: String,
    runtime_manifest: String,
}

impl PreparedRuntime {
    pub(crate) fn execution_profile(
        &self,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<RuntimeExecProfile> {
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime already retired"))?;
        resources.matches_witness(owner)?;
        require(
            self.exported && resources.execution.is_some() && resources.activation_roots.is_some(),
            "original runtime was not transferred with a selected execution policy",
        )?;
        Ok(RuntimeExecProfile {
            userns: resources.userns_identity,
            host_uid: resources.host_uid,
            cohort: resources.cohort.clone(),
            runtime_manifest: resources.runtime_manifest_sha256.clone(),
        })
    }
}

impl RuntimeExecProfile {
    pub(crate) fn revalidate(
        &self,
        runtime: &PreparedRuntime,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        let actual = runtime.execution_profile(owner)?;
        require(
            self.userns == actual.userns
                && self.host_uid == actual.host_uid
                && self.cohort == actual.cohort
                && self.runtime_manifest == actual.runtime_manifest,
            "execution policy belongs to another original runtime or namespace",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn execution_scope_rejects_caller_masks_and_other_profile_names() {
        let parsed: ExecutionDeclaration =
            serde_json::from_value(serde_json::json!({"scope":profile::SCOPE})).unwrap();
        assert_eq!(parsed.scope, profile::SCOPE);
        for field in ["capabilities", "mask", "qualified", "host_sys_admin"] {
            let mut value = serde_json::json!({"scope":profile::SCOPE});
            value[field] = serde_json::json!(true);
            assert!(serde_json::from_value::<ExecutionDeclaration>(value).is_err());
        }
        let images = || {
            (
                ImageDeclaration {
                    file: "system.img".into(),
                    bytes: profile::SYSTEM_BYTES,
                    sha256: profile::SYSTEM_SHA256.into(),
                },
                ImageDeclaration {
                    file: "init".into(),
                    bytes: profile::INIT_BYTES,
                    sha256: profile::INIT_SHA256.into(),
                },
            )
        };
        let (system, init) = images();
        parsed.validate_images(&system, &init).unwrap();
        for scope in [
            "",
            "android_cp2a_scoped_capabilities_v1",
            "android_cp3a_scoped_capabilities_v2",
            "host_sys_admin",
        ] {
            assert!(
                ExecutionDeclaration {
                    scope: scope.into()
                }
                .validate_images(&system, &init)
                .is_err()
            );
        }
        for changed in 0..4 {
            let (mut system, mut init) = images();
            match changed {
                0 => system.bytes += 512,
                1 => system.sha256 = "0".repeat(64),
                2 => init.bytes += 1,
                _ => init.sha256 = "0".repeat(64),
            }
            assert!(parsed.validate_images(&system, &init).is_err());
        }
    }
}
