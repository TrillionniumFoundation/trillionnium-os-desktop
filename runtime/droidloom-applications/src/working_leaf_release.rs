//! Explicit source binding for the legacy single-leaf path and the installed
//! H2 path. Choosing H2 requires the opaque authenticated channel handle;
//! there is no old-checkpoint fallback or pathname-based working constructor.
use super::FilePin;
use super::leaf_release::{self, Inputs};
use droidloom_supervisor::control::physical_qualification_channel::WorkingNativeSourceCustody;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

#[derive(Clone, Copy)]
pub(super) enum SourceContext<'a> {
    Legacy,
    Working(&'a Arc<WorkingNativeSourceCustody>),
}

pub(super) enum NativeSourceRelease {
    Legacy(leaf_release::NativeRelease),
    Working(WorkingRelease),
}
pub(super) struct WorkingRelease {
    custody: Arc<WorkingNativeSourceCustody>,
    inputs: Inputs,
    selection: FilePin,
    catalog: FilePin,
    preparation: FilePin,
    entry: FilePin,
}
fn require(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}
fn catalog_pin(catalog: &str) -> FilePin {
    let digest = hex::encode(Sha256::digest(catalog));
    FilePin {
        path: PathBuf::from(format!("{}/catalogs/{digest}.json", leaf_release::ROOT)),
        bytes: catalog.len() as u64,
        sha256: digest,
    }
}
fn installed_source(path: &Path) -> Result<(), String> {
    require(
        path.starts_with("/usr/libexec/droidloom/native-application-leaves/cohorts")
            && path.components().all(|part| {
                matches!(
                    part,
                    std::path::Component::RootDir | std::path::Component::Normal(_)
                )
            }),
        "working native source must be in its compiled installed cohort",
    )
}
impl NativeSourceRelease {
    pub(super) fn bind_current(
        selection: &FilePin,
        catalog: &str,
        preparation: &FilePin,
        entry: &FilePin,
    ) -> Result<Self, String> {
        leaf_release::NativeRelease::bind_current(selection, catalog, preparation, entry)
            .map(Self::Legacy)
    }
    pub(super) fn bind(
        reference: &FilePin,
        selection: &FilePin,
        catalog: &str,
        preparation: &FilePin,
        entry: &FilePin,
    ) -> Result<Self, String> {
        leaf_release::NativeRelease::bind(reference, selection, catalog, preparation, entry)
            .map(Self::Legacy)
    }
    pub(super) fn bind_working(
        custody: &Arc<WorkingNativeSourceCustody>,
        selection: &FilePin,
        catalog: &str,
        preparation: &FilePin,
        entry: &FilePin,
    ) -> Result<Self, String> {
        custody.guard().map_err(|e| e.to_string())?;
        // The actual running applications ELF is already pinned by admitted
        // WorkingReturnConfiguration. Its compiled selection/catalog select
        // these exact normal installed sources independently of any request.
        let _ = custody.applications_pin().map_err(|e| e.to_string())?;
        for pin in [selection, preparation, entry] {
            installed_source(&pin.path)?;
        }
        let mut inputs = Inputs::new();
        inputs.read(&selection.path, Some(selection), 1024 * 1024, true, false)?;
        let catalog_pin = catalog_pin(catalog);
        require(
            inputs.read(&catalog_pin.path, Some(&catalog_pin), 65536, true, false)?
                == catalog.as_bytes(),
            "working installed source catalog differs from compiled bytes",
        )?;
        inputs.read(
            &preparation.path,
            Some(preparation),
            1024 * 1024,
            true,
            false,
        )?;
        inputs.read(&entry.path, Some(entry), 262144, true, false)?;
        let result = Self::Working(WorkingRelease {
            custody: Arc::clone(custody),
            inputs,
            selection: selection.clone(),
            catalog: catalog_pin,
            preparation: preparation.clone(),
            entry: entry.clone(),
        });
        result.guard()?;
        Ok(result)
    }
    pub(super) fn guard(&self) -> Result<(), String> {
        match self {
            Self::Legacy(release) => release.guard(),
            Self::Working(release) => {
                release.custody.guard().map_err(|e| e.to_string())?;
                release.inputs.guard()
            }
        }
    }
    pub(super) fn cover_window(&self, seconds: u64) -> Result<(), String> {
        match self {
            Self::Legacy(release) => release.cover_window(seconds),
            Self::Working(release) => {
                self.guard()?;
                require(
                    release
                        .custody
                        .deadline()
                        .checked_duration_since(Instant::now())
                        .is_some_and(|left| left >= Duration::from_secs(seconds)),
                    "working source cannot extend its inherited suite window",
                )
            }
        }
    }
    pub(super) fn cover_until(&self, end: Instant) -> Result<(), String> {
        self.guard()?;
        let remaining = end
            .checked_duration_since(Instant::now())
            .ok_or("source work window already exhausted")?;
        match self {
            Self::Legacy(release) => release.cover_window(remaining.as_secs().saturating_add(1)),
            Self::Working(release) => require(
                end <= release.custody.deadline(),
                "working source end exceeds its authenticated original suite end",
            ),
        }
    }
    pub(super) fn working_comparison(&self) -> Result<Option<Value>, String> {
        match self {
            Self::Legacy(_) => Ok(None),
            Self::Working(release) => {
                self.guard()?;
                Ok(Some(release.comparison()?))
            }
        }
    }
    pub(super) fn seal_history_before(
        self,
        end: Instant,
    ) -> Result<HistoricalNativeSourceWitness, String> {
        match self {
            Self::Legacy(release) => release
                .seal_history_before(end)
                .map(HistoricalNativeSourceWitness::Legacy),
            Self::Working(release) => {
                require(
                    end <= release.custody.deadline() && Instant::now() < end,
                    "working case history cannot extend the original case or suite window",
                )?;
                release.custody.guard().map_err(|e| e.to_string())?;
                release.inputs.guard()?;
                let sealed_at = Instant::now();
                require(
                    sealed_at < end,
                    "working source sealing exhausted the case window",
                )?;
                Ok(HistoricalNativeSourceWitness::Working { release, sealed_at })
            }
        }
    }
}
impl WorkingRelease {
    fn guard_immutable(&self) -> Result<(), String> {
        self.custody.guard_immutable().map_err(|e| e.to_string())?;
        self.inputs.guard()
    }
    fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        Ok(
            json!({"schema":"droidloom.installed-working-native-sources.v1",
            "owner":self.custody.comparison().map_err(|e| e.to_string())?,
            "selection":self.selection, "catalog":self.catalog,
            "preparation":self.preparation, "entry":self.entry,
            "historical_current_adoption_claimed":false,
            "execution_or_lease_extension_authorized":false}),
        )
    }
}
pub(super) enum HistoricalNativeSourceWitness {
    Legacy(leaf_release::HistoricalSourceWitness),
    Working {
        release: WorkingRelease,
        sealed_at: Instant,
    },
}
impl HistoricalNativeSourceWitness {
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        match self {
            Self::Legacy(history) => history.guard_immutable(),
            Self::Working { release, sealed_at } => {
                require(
                    Instant::now() >= *sealed_at,
                    "working source clock moved before its seal",
                )?;
                release.guard_immutable()
            }
        }
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        match self {
            Self::Legacy(history) => history.comparison(),
            Self::Working { release, .. } => Ok(json!({
                "schema":"droidloom.historical-working-native-source-witness.v1",
                "installed_sources":release.comparison()?,
                "sealed_while_original_suite_live":true,
                "execution_or_lease_extension_authorized":false,
            })),
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_sources_require_installed_cohort_and_reject_old_workspace_and_traversal() {
        installed_source(Path::new(
            "/usr/libexec/droidloom/native-application-leaves/cohorts/c/source/main.py",
        ))
        .unwrap();
        for path in [
            "/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json",
            "/var/lib/droidloom-qualification/original/selection.json",
            "/usr/libexec/droidloom/native-application-leaves/cohorts/../outside.py",
            "relative/source.py",
        ] {
            assert!(installed_source(Path::new(path)).is_err());
        }
    }
    #[test]
    fn working_catalog_uses_the_compiled_body_commitment() {
        let first = catalog_pin("{\"source\":1}\n");
        let second = catalog_pin("{\"source\":2}\n");
        assert_ne!(first, second);
        assert_eq!(
            first.path,
            PathBuf::from(format!(
                "{}/catalogs/{}.json",
                leaf_release::ROOT,
                first.sha256
            ))
        );
        assert_eq!(first.bytes, 13);
    }
}
