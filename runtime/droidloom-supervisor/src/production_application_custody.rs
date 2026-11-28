//! Preserve the original executor's actual query receipts while observing the
//! fixed image-installed Gallery. The original four-read API and identity Eq
//! remain unchanged; no install, launch, data read, or imported receipt runs.
use super::*;
use crate::control::application_custody::{
    CustodyRead, GALLERY_PACKAGE, GALLERY_PM_PATHS, ImageApplicationCustody,
};
use sha2::{Digest, Sha256};
use std::time::{Duration, Instant};

const SERIALIZED_CUSTODY_LIMIT: usize = 3 * 1024 * 1024;

pub(crate) struct ProductionInspection {
    pub(crate) application: ApplicationInspection,
    pub(crate) image_custody: Option<ImageApplicationCustody>,
}

struct GalleryProbe<'borrow, 'owner> {
    ready: Workflow<'borrow, 'owner>,
    framework: WorkflowFramework,
    reads: Vec<CustodyRead>,
    deadline: Instant,
    retirement_unproven: bool,
}

fn retired(read: &ReadReceipt, stdout: &str) -> Result<()> {
    require(
        read.successful_retirement()
            && read.query_waitid_code == libc::CLD_EXITED
            && read.query_waitid_status == 0
            && read.cgroup_removed
            && read.output_bytes == stdout.len()
            && read.output_sha256 == format!("{:x}", Sha256::digest(stdout.as_bytes())),
        "Gallery query output or original retirement is incomplete",
    )
}

fn gallery_query(query: &ApplicationRead) -> Result<()> {
    match query {
        ApplicationRead::PackageIdentity { package, user }
        | ApplicationRead::PackagePaths { package, user } => require(
            package == GALLERY_PACKAGE && *user == 0,
            "image custody only observes the original user-0 Gallery",
        ),
        ApplicationRead::ApkStat { path } | ApplicationRead::ApkSha256 { path } => require(
            GALLERY_PM_PATHS.contains(&path.as_str()),
            "image custody cannot inspect a replacement or arbitrary APK",
        ),
    }
}

fn gallery_paths(output: &str) -> Result<()> {
    let rows = output
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>();
    require(
        rows.len() == 1
            && rows[0]
                .strip_prefix("package:")
                .is_some_and(|path| GALLERY_PM_PATHS.contains(&path)),
        "Gallery PM source is not the original single image member",
    )
}

impl AndroidProbe for GalleryProbe<'_, '_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        if Instant::now() >= self.deadline {
            return Err("image custody inspection deadline".into());
        }
        let observed = self.ready.application_epoch(&self.framework);
        observed.map_err(|error| {
            self.retirement_unproven |= matches!(error, ApplicationError::RetirementUnproven);
            error.to_string()
        })
    }

    fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
        if Instant::now() >= self.deadline || self.reads.len() >= 7 {
            return Err("image custody exact query bound".into());
        }
        let query = ApplicationRead::from_command(args).map_err(|error| error.to_string())?;
        gallery_query(&query).map_err(|error| error.to_string())?;
        // This is the same authenticated descriptor/PIDFD worker, fixed MAC
        // role, stopped-exec observation and actual reap path as normal reads.
        let result = self
            .ready
            .run_application_read_before(&query, self.deadline);
        let result = result.map_err(|error| {
            self.retirement_unproven |= matches!(error, ApplicationError::RetirementUnproven);
            error.to_string()
        })?;
        retired(&result.receipt, &result.output).map_err(|error| error.to_string())?;
        if matches!(query, ApplicationRead::PackagePaths { .. }) {
            gallery_paths(&result.output).map_err(|error| error.to_string())?;
        }
        let receipt = serde_json::to_value(&result.receipt).map_err(|error| error.to_string())?;
        self.reads.push(CustodyRead {
            argv: args.to_vec(),
            stdout: result.output.clone(),
            receipt,
        });
        Ok(result.output)
    }
}

pub(crate) fn inspect_with_custody(
    ready: ReadyTreeWitness<'_>,
    package: &str,
    user: u32,
) -> Result<ProductionInspection> {
    if package != GALLERY_PACKAGE || user != 0 {
        return Ok(ProductionInspection {
            application: super::inspect(ready, package, user)?,
            image_custody: None,
        });
    }
    inspect_gallery(Workflow::Legacy(ready))
}

pub(crate) fn inspect_with_custody_early(
    authority: &crate::production_selection::early_generation::EarlyApplicationAuthority<'_>,
    package: &str,
    user: u32,
) -> Result<ProductionInspection> {
    if package != GALLERY_PACKAGE || user != 0 {
        return Ok(ProductionInspection {
            application: super::inspect_early(authority, package, user)?,
            image_custody: None,
        });
    }
    inspect_gallery(Workflow::Early(authority))
}

fn inspect_gallery(mut ready: Workflow<'_, '_>) -> Result<ProductionInspection> {
    let started = Instant::now();
    let deadline = started + Duration::from_secs(300);
    let framework = ready.observe_application_framework()?;
    let first_epoch = ready.application_epoch(&framework)?;
    let (mut image, owner) = ready.observe_gallery_image(deadline)?;
    require(
        ready.application_epoch(&framework)? == first_epoch,
        "framework changed during whole-image observation",
    )?;
    let mut probe = GalleryProbe {
        ready,
        framework,
        reads: Vec::new(),
        deadline,
        retirement_unproven: false,
    };
    let observed = crate::control::application_probe::inspect(&mut probe, GALLERY_PACKAGE, 0);
    // A string-valued probe failure must not erase an actual failed retirement.
    // Check the original owner even when one of the seven reads failed.
    let after = probe.ready.revalidate_application();
    if probe.retirement_unproven || matches!(&after, Err(ApplicationError::RetirementUnproven)) {
        return Err(ApplicationError::RetirementUnproven);
    }
    after?;
    let application = observed.map_err(external)?;
    require(
        application.epoch == first_epoch,
        "Gallery inspection crossed a framework epoch",
    )?;
    // All workers/queries are already actually reaped. This one complete
    // after-byte read remains inside the original 300-second absolute limit.
    probe
        .ready
        .complete_gallery_image(&mut image, &owner, deadline)?;
    require(
        probe.ready.application_epoch(&probe.framework)? == first_epoch,
        "final Gallery epoch changed",
    )?;
    let (cohort, original_apk, after_cohort, after_original_apk) =
        image.evidence().map_err(external)?;
    let observed = ImageApplicationCustody {
        schema: "droidloom-image-application-custody-v1".into(),
        application: application.clone(),
        owner,
        cohort,
        original_apk,
        after_cohort,
        after_original_apk,
        reads: probe.reads,
        elapsed_millis: started
            .elapsed()
            .as_millis()
            .try_into()
            .map_err(|_| reject("image custody elapsed time overflow"))?,
        data_continuity_qualified: false,
        runtime_qualified: false,
        business_qualified: false,
        production_ready: false,
    };
    observed.validate(&application).map_err(external)?;
    require(
        serde_json::to_vec(&observed).map_err(external)?.len() <= SERIALIZED_CUSTODY_LIMIT,
        "complete custody response exceeds its 3 MiB transport budget",
    )?;
    // Source bytes cannot qualify a replacement mount or changed owner after
    // the transcript has been checked. This performs no second command run.
    probe
        .ready
        .revalidate_gallery_image(&image, &observed.owner, deadline)?;
    require(
        probe.ready.application_epoch(&probe.framework)? == first_epoch
            && Instant::now() < deadline,
        "Gallery source observation expired before return",
    )?;
    Ok(ProductionInspection {
        application,
        image_custody: Some(observed),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn image_gallery_never_adopts_an_installed_replacement() {
        assert!(gallery_paths("package:/product/app/Gallery2/Gallery2.apk\n").is_ok());
        assert!(gallery_paths("package:/system/product/app/Gallery2/Gallery2.apk\n").is_ok());
        for raw in [
            "package:/data/app/copied/base.apk\n",
            "package:/product/app/Gallery2/Gallery2.apk\npackage:/data/app/split.apk\n",
            "package:/product/app/Gallery2/../Gallery2.apk\n",
            "package:/apex/custom/Gallery2.apk\n",
            "",
        ] {
            assert!(gallery_paths(raw).is_err());
        }
    }

    #[test]
    fn image_gallery_query_scope_keeps_the_existing_finite_read_boundary() {
        assert!(
            gallery_query(&ApplicationRead::PackageIdentity {
                package: GALLERY_PACKAGE.into(),
                user: 0,
            })
            .is_ok()
        );
        assert!(
            gallery_query(&ApplicationRead::PackagePaths {
                package: GALLERY_PACKAGE.into(),
                user: 1,
            })
            .is_err()
        );
        assert!(
            gallery_query(&ApplicationRead::PackageIdentity {
                package: "com.android.contacts".into(),
                user: 0,
            })
            .is_err()
        );
        assert!(
            gallery_query(&ApplicationRead::ApkSha256 {
                path: "/data/app/Gallery2.apk".into(),
            })
            .is_err()
        );
    }
}
