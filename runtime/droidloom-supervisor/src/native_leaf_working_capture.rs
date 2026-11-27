//! The working preparation retains the exact live baseline and all source FDs.
//! It cannot reconstruct either owner from a comparison receipt or caller path.
use super::*;
use crate::control::physical_qualification_channel::{
    NATIVE_CASE_COUNT, QualificationCase, WorkingQualificationOwner,
};
use std::ffi::CString;
use std::os::fd::{AsRawFd, FromRawFd};
use std::path::PathBuf;

fn native_capture_name(package: &str) -> Result<String> {
    let packages = (0..NATIVE_CASE_COUNT)
        .map(|n| QualificationCase::from_ordinal(n as u8).map(|case| case.package()))
        .collect::<std::io::Result<std::collections::BTreeSet<_>>>()?;
    if packages.len() != 8 || !packages.contains(package) {
        return fail("working baseline requires an actual package in the compiled native roster");
    }
    Ok(format!("capture-{package}"))
}
fn capture_path(owner: &WorkingQualificationOwner, package: &str) -> Result<PathBuf> {
    Ok(owner
        .runtime_evidence_directory()?
        .join("native-baselines")
        .join(native_capture_name(package)?))
}
fn protected_directory(path: &Path) -> Result<File> {
    let file = crate::native_leaf_installed_cohort::open_absolute_directory(path)?;
    let m = file.metadata()?;
    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o7777 != 0o700 {
        return fail("working baseline directory is not the fixed root-owned private directory");
    }
    if directory_identity(&m) != directory_identity(&fs::symlink_metadata(path)?) {
        return fail("working baseline directory changed during protected open");
    }
    Ok(file)
}
struct WorkingCaptureDirectory {
    path: PathBuf,
    file: File,
    identity: [u64; 5],
    parent_path: PathBuf,
    parent: File,
    parent_identity: [u64; 5],
}
impl WorkingCaptureDirectory {
    fn create(owner: &WorkingQualificationOwner, package: &str) -> Result<Self> {
        owner.guard()?;
        let path = capture_path(owner, package)?;
        let parent_path = path
            .parent()
            .ok_or("working capture parent absent")?
            .to_path_buf();
        // The plan factory creates NativeBaselines exactly once using the owner.
        // This collector never creates or adopts an arbitrary ancestor.
        let parent = protected_directory(&parent_path)?;
        let parent_identity = directory_identity(&parent.metadata()?);
        let name = CString::new(native_capture_name(package)?)?;
        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        parent.sync_all()?;
        let raw = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(raw) };
        let identity = directory_identity(&file.metadata()?);
        let selected = Self {
            path,
            file,
            identity,
            parent_path,
            parent,
            parent_identity,
        };
        selected.guard(owner, package)?;
        Ok(selected)
    }
    fn guard(&self, owner: &WorkingQualificationOwner, package: &str) -> Result<()> {
        owner.guard()?;
        if self.path != capture_path(owner, package)?
            || directory_identity(&self.parent.metadata()?) != self.parent_identity
            || directory_identity(&protected_directory(&self.parent_path)?.metadata()?)
                != self.parent_identity
            || directory_identity(&self.file.metadata()?) != self.identity
            || directory_identity(&protected_directory(&self.path)?.metadata()?) != self.identity
        {
            return fail("working capture source-owned parent or directory changed");
        }
        Ok(())
    }
}

/// One actual baseline retained across this package's source-owned preparation.
/// The comparison receipt is separate from the borrowed live owner/Main/app.
/// This type has no Clone, Deserialize, public fields or unchecked constructor.
pub struct WorkingBusinessBaseline<'a> {
    owner: &'a WorkingQualificationOwner,
    observation: NativeLeafBaselineObservation<'a>,
    sources: InstalledCohort,
    directory: WorkingCaptureDirectory,
    receipt: Value,
}
impl<'a> WorkingBusinessBaseline<'a> {
    pub(crate) fn owner(&self) -> &'a WorkingQualificationOwner {
        self.owner
    }
    /// Comparison pins produced by the real fixed collector and held readback.
    pub fn comparison_receipt(&self) -> &Value {
        &self.receipt
    }
    /// Recheck the same original owner, source FDs and private output directory.
    pub fn recheck(&mut self) -> std::result::Result<(), String> {
        (|| -> Result<()> {
            self.directory
                .guard(self.owner, &self.observation.application().package)?;
            self.sources.recheck(self.owner.preparation_deadline())?;
            check_before(self.owner.preparation_deadline())?;
            Ok(())
        })()
        .map_err(|e| e.to_string())
    }
    /// Borrow the retained live observation; a saved comparison cannot create it.
    /// Each normal runner still performs all original Main/data/FD checks.
    pub fn observation_mut(
        &mut self,
    ) -> std::result::Result<&mut NativeLeafBaselineObservation<'a>, String> {
        self.recheck()?;
        Ok(&mut self.observation)
    }
}

/// Capture once for one of the eight compiled native packages. The caller's
/// existing actual Main/app tokens and owner's original preparation end are
/// retained; no output path, command, alternate deadline or success is accepted.
pub fn capture_working_business_from_observed<'a>(
    owner: &'a WorkingQualificationOwner,
    inspector: &mut NativeApplicationInspector,
    main: &'a MainCustodyObservation,
    application: &'a ActualApplicationObservation,
) -> std::result::Result<WorkingBusinessBaseline<'a>, String> {
    (|| -> Result<WorkingBusinessBaseline<'a>> {
        owner.guard()?;
        let end = owner.preparation_deadline();
        check_before(end)?;
        native_capture_name(&application.facts().package)?;
        let mut observation = NativeLeafBaselineObservation::capture_from_observed(
            inspector,
            main,
            application,
            end,
        )?;
        observation.attach_preparation_owner(owner)?;
        if application.facts().package == crate::native_ihg_preparation::TARGET {
            let inventory =
                inspector.observe_user_zero_package_inventory_until(main, application, end)?;
            observation.attach_user_zero_inventory(inspector, inventory)?;
        }
        let mut sources = InstalledCohort::capture(end)?;
        let directory = WorkingCaptureDirectory::create(owner, &application.facts().package)?;
        let receipt = capture_at(
            inspector,
            &mut observation,
            &mut sources,
            &directory.path,
            &directory.file,
            directory.identity,
            end,
        )?;
        observation.verify_local(inspector, end)?;
        let mut result = WorkingBusinessBaseline {
            owner,
            observation,
            sources,
            directory,
            receipt,
        };
        result.recheck()?;
        Ok(result)
    })()
    .map_err(|e| e.to_string())
}

fn check_arguments(command: &std::process::Command, expected: &Path) -> Result<()> {
    const COLLECTOR: &str = "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/main/kernel_native_observation.py";
    let args = command
        .get_args()
        .map(|v| v.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("working baseline collector argv is not UTF-8")?;
    if command.get_program() != "/usr/bin/python3"
        || args.len() != 6
        || args[..5] != ["-I", "-B", COLLECTOR, "--collect", "--output-directory"]
        || Path::new(args[5]) != expected
    {
        return fail(
            "working baseline requires this owner's exact source collector and package directory",
        );
    }
    Ok(())
}
pub(crate) fn check_working_collector(
    command: &std::process::Command,
    owner: &WorkingQualificationOwner,
    package: &str,
) -> std::result::Result<(), String> {
    (|| -> Result<()> {
        owner.guard()?;
        let expected = capture_path(owner, package)?;
        check_arguments(command, &expected)?;
        protected_directory(&expected)?;
        check_before(owner.preparation_deadline())
    })()
    .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn baseline_roster_deduplicates_native_cases_and_excludes_family_packages() {
        let packages = (0..NATIVE_CASE_COUNT)
            .map(|n| QualificationCase::from_ordinal(n as u8).unwrap().package())
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(packages.len(), 8);
        for package in packages {
            assert_eq!(
                native_capture_name(package).unwrap(),
                format!("capture-{package}")
            );
        }
        for package in [
            "com.android.dialer",
            "com.tencent.mm",
            "../escape",
            "com.android.settings/other",
        ] {
            assert!(native_capture_name(package).is_err());
        }
    }
    #[test]
    fn working_collector_comparison_rejects_other_paths_modes_and_arguments() {
        // This parser fixture does not create any WorkingQualificationOwner.
        let expected = Path::new(
            "/var/lib/droidloom/qualification/working-qualification-fixture/runtime-evidence/native-baselines/capture-com.android.settings",
        );
        let make = || {
            let mut c = std::process::Command::new("/usr/bin/python3");
            c.args(["-I", "-B", "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2/source/main/kernel_native_observation.py", "--collect", "--output-directory"]);
            c.arg(expected);
            c
        };
        check_arguments(&make(), expected).unwrap();
        let mut extra = make();
        extra.arg("--caller-passed");
        assert!(check_arguments(&extra, expected).is_err());
        assert!(check_arguments(&make(), Path::new("/tmp/foreign")).is_err());
        assert!(check_arguments(&std::process::Command::new("/bin/sh"), expected).is_err());
        let mut mode = std::process::Command::new("/usr/bin/python3");
        mode.args(["-I", "-B", "unknown.py", "--collect", "--output-directory"])
            .arg(expected);
        assert!(check_arguments(&mode, expected).is_err());
    }
}
