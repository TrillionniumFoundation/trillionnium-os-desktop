//! Normal installation of the fixed original set before readonly source/PM
//! PLAN capture. This stage grants no business gate and never deletes app data.
use droidloom_supervisor::{
    control::{physical_qualification_channel::WorkingPreparationChannel, WorkingOriginalInstallObservation},
    native_working_install,
};
use droidloom_update::working_preparation_materials::WorkingApkMaterials;
use serde_json::{Value, json};
use std::{collections::BTreeSet, time::{Duration, Instant}};

const IMAGE_ONLY: &str = "com.android.gallery3d";
const SIGNER_CONFLICT_LAST: &str = "com.sankuai.meituan.takeoutnew";

fn order<'a>(names: &[&'a str]) -> Result<Vec<&'a str>, String> {
    let actual: BTreeSet<_> = names.iter().copied().collect();
    let expected: BTreeSet<_> = super::super::physical_gate_roster::PACKAGES.iter().map(|v| v.package).collect();
    if names.len() != 41 || actual != expected || actual.len() != names.len() {
        return Err("ordinary install source differs from the complete 41-app qualification roster".into());
    }
    let mut values: Vec<_> = names.iter().copied().filter(|v| *v != IMAGE_ONLY).collect();
    // The known old local signer is tried through normal PM after every other
    // original package. Failure preserves both pairs and is never a fourth
    // exception, a claimed update, or an instruction to uninstall.
    values.sort_by(|a, b| (*a == SIGNER_CONFLICT_LAST).cmp(&(*b == SIGNER_CONFLICT_LAST)).then(a.cmp(b)));
    if values.len() != 40 || values.last() != Some(&SIGNER_CONFLICT_LAST) {
        return Err("ordinary install queue is not the fixed 40-package source queue".into());
    }
    Ok(values)
}
pub(super) struct WorkingOriginalInstallations {
    completed: Vec<WorkingOriginalInstallObservation>,
    attempted: Vec<String>,
    failure: Option<Value>,
    source: Value,
}
impl WorkingOriginalInstallations {
    pub(super) fn run(channel: &mut WorkingPreparationChannel, sources: &WorkingApkMaterials<'_>) -> Result<Self, String> {
        channel.guard()?; sources.guard().map_err(|e| e.to_string())?;
        let applications = sources.applications();
        let names: Vec<_> = applications.iter().map(|a| a.package()).collect();
        let queue = order(&names)?;
        let mut result = Self { completed: Vec::new(), attempted: Vec::new(), failure: None, source: sources.comparison() };
        for package in queue {
            let source = applications.iter().find(|a| a.package() == package).ok_or("actual original source disappeared")?;
            let end = channel.deadline().min(Instant::now() + Duration::from_secs(native_working_install::PACKAGE_SECONDS));
            let installed = (|| {
                channel.guard()?; sources.guard().map_err(|e| e.to_string())?;
                result.attempted.push(package.into());
                let (inspector, main) = channel.observations();
                let observation = inspector.install_working_application_until(main, package, &source.files(), end)
                    .map_err(|e| e.to_string())?;
                observation.require_main(inspector, main, end).map_err(|e| e.to_string())?;
                sources.guard().map_err(|e| e.to_string())?;
                Ok::<_, String>(observation)
            })();
            match installed {
                Ok(observation) => result.completed.push(observation),
                Err(reason) => {
                    result.failure = Some(json!({"package":package,"reason":reason,
                        "automatic_retry":false,"uninstall_attempted":false,"data_clear_attempted":false,
                        "signature_bypass_attempted":false,"remaining_installations_stopped":true}));
                    break;
                }
            }
        }
        droidloom_supervisor::production_application::require_working_original_payload_retired()
            .map_err(|e|e.to_string())?;
        Ok(result)
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        Ok(json!({
            "schema":"droidloom.working-original-apk-installations.v1",
            "source_selection_sha256":native_working_install::SELECTION_SHA256,
            "actual_source_descriptors":self.source,
            "required_packages":41,"normal_pm_packages":40,"normal_pm_apk_files":66,
            "image_observation_only_package":IMAGE_ONLY,
            "attempted_packages":self.attempted,
            "normal_pm_commit_observations":self.completed.iter().map(|v|v.comparison()).collect::<Result<Vec<_>,_>>()?,
            "normal_pm_commit_count":self.completed.len(),
            "all_normal_pm_commits_observed":self.failure.is_none() && self.completed.len()==40,
            "failure":self.failure,
            "fresh_actual_pm_identity_readback_required":true,
            "business_acceptance_granted":false,"production_ready":false,
            "original_data_pair_modified":false,
            "working_copy_mutation_scope":"Android ordinary PackageInstaller -r original complete split sets",
            "uninstall_attempted":false,"data_clear_attempted":false,"account_operations_attempted":false,
            "outer_package_seconds":native_working_install::PACKAGE_SECONDS,
        }))
    }
    pub(super) fn guard(&self, channel: &mut WorkingPreparationChannel, sources: &WorkingApkMaterials<'_>) -> Result<(), String> {
        droidloom_supervisor::production_application::require_working_original_payload_retired()
            .map_err(|e|e.to_string())?;
        channel.guard()?; sources.guard().map_err(|e| e.to_string())?;
        let end = channel.deadline();
        let (inspector, main) = channel.observations();
        for observation in &self.completed {
            observation.require_main(inspector, main, end).map_err(|e| e.to_string())?;
        }
        Ok(())
    }
    pub(super) fn require_complete(&self) -> Result<(), String> {
        if let Some(failure) = &self.failure {
            return Err(format!("normal original APK installation remains blocked; original data retained: {failure}"));
        }
        if self.completed.len() != 40 {
            return Err("normal original APK installation did not complete the full required roster".into());
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_install_queue_keeps_all_required_packages_and_conflict_last() {
        let names: Vec<_> = super::super::super::physical_gate_roster::PACKAGES.iter().map(|v|v.package).collect();
        let queue = order(&names).unwrap();
        assert_eq!(queue.len(), 40); assert_eq!(queue.last(), Some(&SIGNER_CONFLICT_LAST));
        assert!(!queue.contains(&IMAGE_ONLY));
        assert!(queue.contains(&"com.ss.android.lark")); assert!(queue.contains(&"com.ss.android.article.news"));
        assert!(order(&names[..40]).is_err());
        let mut wrong = names.clone(); wrong[0] = "org.caller.arbitrary";
        assert!(order(&wrong).is_err());
        let mut duplicate = names.clone(); duplicate[0] = duplicate[1];
        assert!(order(&duplicate).is_err());
    }
}
