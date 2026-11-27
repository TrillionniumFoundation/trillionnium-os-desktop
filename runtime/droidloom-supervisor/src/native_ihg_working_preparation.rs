//! IHG preparation under the actual working owner and its original deadline.
use super::*;
use crate::control::physical_qualification_channel::WorkingQualificationOwner;
use crate::native_leaf_business_capture::WorkingBusinessBaseline;
use std::ffi::CString;
use std::os::fd::AsRawFd;

#[derive(Clone, Copy)]
pub(super) enum ArtifactScope<'a> {
    Public,
    Working {
        owner: &'a WorkingQualificationOwner,
        directories: &'a WorkingDirectories,
    },
}
#[derive(Clone)]
struct WorkingPaths {
    root: PathBuf,
}
impl WorkingPaths {
    fn from_owner(owner: &WorkingQualificationOwner) -> Result<Self> {
        owner.guard()?;
        Ok(Self {
            root: owner.runtime_evidence_directory()?.to_path_buf(),
        })
    }
    fn inputs(&self) -> PathBuf {
        self.root.join("native-inputs/ihg-london")
    }
    fn baseline(&self, name: &str) -> PathBuf {
        self.root
            .join("native-baselines")
            .join(format!("capture-{TARGET}"))
            .join(name)
    }
    fn request(&self, mode: IhgPreparationMode) -> PathBuf {
        self.inputs().join(format!("{}.request.json", mode.name()))
    }
    fn evidence(&self, mode: IhgPreparationMode) -> PathBuf {
        self.inputs().join(format!("{}.evidence", mode.name()))
    }
    fn output(&self, mode: IhgPreparationMode) -> PathBuf {
        if mode == IhgPreparationMode::Plan {
            self.root.join("native-cases/ihg-london")
        } else {
            self.inputs().join(mode.name())
        }
    }
    fn result(&self, mode: IhgPreparationMode) -> PathBuf {
        self.output(mode).join(mode.output_name())
    }
    fn dependency(&self, key: &str) -> Result<PathBuf> {
        Ok(match key {
            "baseline" => self.baseline("BASELINE.json"),
            "qualification" => self.baseline("QUALIFICATION.json"),
            "target_identity" => self.result(IhgPreparationMode::TargetIdentity),
            "source" => self.result(IhgPreparationMode::HelperSource),
            "build" | "helper_build" => self.result(IhgPreparationMode::HelperBuild),
            "install" | "helper_install" => self.result(IhgPreparationMode::HelperInstall),
            "helper_identity" => self.result(IhgPreparationMode::HelperIdentity),
            _ => return Err("unlisted working IHG dependency".into()),
        })
    }
    fn uid1000_artifact(&self, path: &Path) -> bool {
        [
            "owned-ihg-qa.apk",
            "source/ActionRunner.java",
            "source/AndroidManifest.xml",
        ]
        .iter()
        .any(|name| path == self.output(IhgPreparationMode::HelperBuild).join(name))
    }
    fn artifact(&self, path: &Path) -> bool {
        if path == self.baseline("BASELINE.json")
            || path == self.baseline("QUALIFICATION.json")
            || self.uid1000_artifact(path)
        {
            return true;
        }
        if [
            IhgPreparationMode::TargetIdentity,
            IhgPreparationMode::HelperSource,
            IhgPreparationMode::HelperBuild,
            IhgPreparationMode::HelperInstall,
            IhgPreparationMode::HelperIdentity,
            IhgPreparationMode::Plan,
        ]
        .iter()
        .any(|mode| path == self.result(*mode))
        {
            return true;
        }
        let install = self.output(IhgPreparationMode::HelperInstall);
        if path == install.join("state-observation.json") {
            return true;
        }
        (1..=13).any(|n| {
            ["result.json", "transport.json", "stdout", "stderr"]
                .iter()
                .any(|suffix| {
                    path == install
                        .join("commands")
                        .join(format!("command-{n:03}.{suffix}"))
                })
        })
    }
    fn request_shape(&self, mode: IhgPreparationMode, value: &Value) -> Result<()> {
        require(
            exact(value, mode.keys()),
            "working IHG request mode fields differ",
        )?;
        for key in mode.keys() {
            require(
                pin_path(&value[key])? == self.dependency(key)?,
                "working IHG dependency is not this owner's exact predecessor",
            )?;
        }
        Ok(())
    }
}
fn directory_identity(m: &fs::Metadata) -> [u64; 5] {
    [
        m.dev(),
        m.ino(),
        m.mode() as u64,
        m.uid() as u64,
        m.gid() as u64,
    ]
}
struct HeldDirectory {
    path: PathBuf,
    file: File,
    identity: [u64; 5],
    uid: u32,
}
impl HeldDirectory {
    fn open(path: PathBuf, uid: u32) -> Result<Self> {
        let file = crate::native_leaf_installed_cohort::open_absolute_directory(&path)
            .map_err(|e| e.to_string())?;
        let m = file.metadata().map_err(|e| e.to_string())?;
        require(
            m.is_dir() && m.uid() == uid && m.gid() == uid && m.mode() & 0o7777 == 0o700,
            "working IHG directory ownership or private mode differs",
        )?;
        let value = Self {
            path,
            file,
            identity: directory_identity(&m),
            uid,
        };
        value.guard()?;
        Ok(value)
    }
    fn guard(&self) -> Result<()> {
        let named = crate::native_leaf_installed_cohort::open_absolute_directory(&self.path)
            .map_err(|e| e.to_string())?;
        let a = self.file.metadata().map_err(|e| e.to_string())?;
        let b = named.metadata().map_err(|e| e.to_string())?;
        require(
            directory_identity(&a) == self.identity
                && directory_identity(&b) == self.identity
                && a.uid() == self.uid,
            "working IHG held directory was replaced or relabelled by ownership",
        )?;
        Ok(())
    }
    fn create_child(&self, name: &str) -> Result<Self> {
        self.guard()?;
        require(
            !name.is_empty() && !name.contains('/') && name != "." && name != "..",
            "working IHG child name is not fixed",
        )?;
        let name_c = CString::new(name).map_err(|e| e.to_string())?;
        if unsafe { libc::mkdirat(self.file.as_raw_fd(), name_c.as_ptr(), 0o700) } != 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        self.file.sync_all().map_err(|e| e.to_string())?;
        self.guard()?;
        Self::open(self.path.join(name), 0)
    }
}
pub(super) struct WorkingDirectories {
    paths: WorkingPaths,
    held: Vec<HeldDirectory>,
}
impl WorkingDirectories {
    fn create(owner: &WorkingQualificationOwner, mode: IhgPreparationMode) -> Result<Self> {
        let paths = WorkingPaths::from_owner(owner)?;
        let mut held = Vec::new();
        for path in [
            paths.root.clone(),
            paths.root.join("native-inputs"),
            paths.root.join("native-cases"),
            paths.inputs(),
        ] {
            held.push(HeldDirectory::open(path, 0)?);
        }
        let evidence = held
            .last()
            .unwrap()
            .create_child(&format!("{}.evidence", mode.name()))?;
        held.push(evidence);
        let result = Self { paths, held };
        result.guard(owner.preparation_deadline())?;
        owner.guard()?;
        Ok(result)
    }
    pub(super) fn guard(&self, end: Instant) -> Result<()> {
        before(end)?;
        for directory in &self.held {
            directory.guard()?;
        }
        before(end)
    }
    fn retain_output(&mut self, mode: IhgPreparationMode, end: Instant) -> Result<()> {
        self.guard(end)?;
        self.held.push(HeldDirectory::open(
            self.paths.output(mode),
            if mode == IhgPreparationMode::HelperBuild {
                1000
            } else {
                0
            },
        )?);
        self.guard(end)
    }
}
impl ArtifactScope<'_> {
    pub(super) fn is_working(&self) -> bool {
        matches!(self, Self::Working { .. })
    }
    pub(super) fn guard(&self, end: Instant) -> Result<()> {
        before(end)?;
        if let Self::Working { owner, directories } = self {
            require(
                end <= owner.preparation_deadline(),
                "IHG deadline exceeds its original owner",
            )?;
            owner.guard()?;
            directories.guard(end)?;
            require(
                directories.paths.root == owner.runtime_evidence_directory()?,
                "working IHG runtime root changed",
            )?;
        }
        Ok(())
    }
    pub(super) fn artifact(&self, path: &Path) -> Result<()> {
        match self {
            Self::Public => public_artifact(path),
            Self::Working { directories, .. } => require(
                directories.paths.artifact(path),
                "working IHG artifact is outside the fixed roster",
            ),
        }
    }
    pub(super) fn uid1000_artifact(&self, path: &Path) -> bool {
        match self {
            Self::Public => path.starts_with("/home/alex/work"),
            Self::Working { directories, .. } => directories.paths.uid1000_artifact(path),
        }
    }
    pub(super) fn request_shape(&self, mode: IhgPreparationMode, v: &Value) -> Result<()> {
        match self {
            Self::Public => request_shape(mode, v),
            Self::Working { directories, .. } => directories.paths.request_shape(mode, v),
        }
    }
    pub(super) fn check_paths(
        &self,
        mode: IhgPreparationMode,
        request: &Path,
        output: &Path,
        evidence: &Path,
        end: Instant,
    ) -> Result<()> {
        self.guard(end)?;
        match self {
            Self::Public => {
                output_path(mode, output)?;
                let em = fs::symlink_metadata(evidence).map_err(|e| e.to_string())?;
                require(
                    evidence.parent() == Some(Path::new(QUAL))
                        && evidence
                            .file_name()
                            .and_then(|s| s.to_str())
                            .is_some_and(|n| n.starts_with("native-leaf-"))
                        && em.is_dir()
                        && em.uid() == 0
                        && em.gid() == 0
                        && em.mode() & 0o7777 == 0o700
                        && fs::canonicalize(evidence).map_err(|e| e.to_string())? == evidence,
                    "IHG evidence requires the fresh normal private capture directory",
                )?;
            }
            Self::Working { directories, .. } => {
                let paths = &directories.paths;
                require(
                    request == paths.request(mode)
                        && output == paths.output(mode)
                        && evidence == paths.evidence(mode),
                    "working IHG mode paths differ",
                )?;
                require(
                    fs::symlink_metadata(output)
                        .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound),
                    "working IHG output is not fresh; automatic retry is forbidden",
                )?;
            }
        }
        Ok(())
    }
}
fn check_working_arguments(
    c: &Command,
    mode: IhgPreparationMode,
    paths: &WorkingPaths,
) -> Result<()> {
    let argv = c
        .get_args()
        .map(|x| x.to_str())
        .collect::<Option<Vec<_>>>()
        .ok_or("working IHG argv is not UTF-8")?;
    let count = if matches!(
        mode,
        IhgPreparationMode::TargetIdentity
            | IhgPreparationMode::HelperIdentity
            | IhgPreparationMode::Plan
    ) {
        16
    } else {
        14
    };
    require(
        c.get_program() == "/usr/bin/python3" && argv.len() == count,
        "working IHG entry or argument count differs",
    )?;
    let recipe: Value = serde_json::from_str(RECIPE).map_err(|e| e.to_string())?;
    let rows = recipe["members"]
        .as_array()
        .ok_or("compiled members absent")?
        .iter()
        .filter(|v| v["relative_path"] == "preparations/ihg.json")
        .collect::<Vec<_>>();
    require(rows.len() == 1, "compiled IHG preparation is not unique")?;
    let expected = command(
        mode,
        &paths.request(mode),
        argv[11],
        &paths.output(mode),
        &rows[0]["output"],
    )?;
    require(
        c.get_program() == expected.get_program() && c.get_args().eq(expected.get_args()),
        "working IHG argv differs from this owner's fixed mode",
    )
}
pub(crate) fn check_working_command(
    c: &Command,
    mode: IhgPreparationMode,
    owner: &WorkingQualificationOwner,
) -> Result<()> {
    let paths = WorkingPaths::from_owner(owner)?;
    before(owner.preparation_deadline())?;
    check_working_arguments(c, mode, &paths)?;
    owner.guard()
}
/// The actual retained baseline supplies the owner, root and original end.
/// No caller-selected path, executable, argv or replacement deadline is accepted.
pub fn run_working(
    mode: IhgPreparationMode,
    request_sha: &str,
    inspector: &mut NativeApplicationInspector,
    capture: &mut WorkingBusinessBaseline<'_>,
) -> Result<IhgPreparationExecution> {
    capture.recheck()?;
    let owner = capture.owner();
    let end = owner.preparation_deadline();
    let mut directories = WorkingDirectories::create(owner, mode)?;
    let request = directories.paths.request(mode);
    let output = directories.paths.output(mode);
    let evidence = directories.paths.evidence(mode);
    let mut held_request = Held::open(&request, end, false)?;
    require(
        hash(&held_request.raw) == request_sha,
        "working IHG request digest differs",
    )?;
    let value = held_request.json()?;
    directories.paths.request_shape(mode, &value)?;
    for key in ["baseline", "qualification"] {
        if let Some(pin) = value.get(key) {
            require(
                *pin == capture.comparison_receipt()[key],
                "working IHG request is not the actual retained baseline capture",
            )?;
        }
    }
    let scope = ArtifactScope::Working {
        owner,
        directories: &directories,
    };
    let mut execution = run_scoped(
        mode,
        &request,
        request_sha,
        &output,
        &evidence,
        inspector,
        capture.observation_mut()?,
        end,
        scope,
    )?;
    capture.recheck()?;
    directories.retain_output(mode, end)?;
    owner.guard()?;
    held_request.recheck(end)?;
    execution.held.push(held_request);
    execution.working_directories = Some(directories);
    execution.recheck()?;
    Ok(execution)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> WorkingPaths {
        WorkingPaths {
            root: PathBuf::from(
                "/var/lib/droidloom/qualification/working-qualification-fixture/runtime-evidence",
            ),
        }
    }
    #[test]
    fn working_ihg_requests_bind_each_mode_to_its_exact_predecessors() {
        let paths = fixture();
        for mode in [
            IhgPreparationMode::TargetIdentity,
            IhgPreparationMode::HelperSource,
            IhgPreparationMode::HelperBuild,
            IhgPreparationMode::HelperInstall,
            IhgPreparationMode::HelperIdentity,
            IhgPreparationMode::Plan,
        ] {
            let mut value = serde_json::Map::new();
            for key in mode.keys() {
                value.insert(
                    (*key).into(),
                    json!({"path": paths.dependency(key).unwrap(),
                    "bytes": 1, "sha256": "a".repeat(64)}),
                );
            }
            let value = Value::Object(value);
            paths.request_shape(mode, &value).unwrap();
            for key in mode.keys() {
                let mut wrong = value.clone();
                wrong[key]["path"] = json!(paths.inputs().join("other/result.json"));
                assert!(paths.request_shape(mode, &wrong).is_err());
            }
            let mut extra = value.clone();
            extra["passed"] = json!(true);
            assert!(paths.request_shape(mode, &extra).is_err());
        }
    }
    #[test]
    fn working_ihg_artifacts_and_uid1000_scope_are_finite() {
        let paths = fixture();
        assert!(paths.artifact(&paths.result(IhgPreparationMode::Plan)));
        let install = paths.output(IhgPreparationMode::HelperInstall);
        assert!(paths.artifact(&install.join("commands/command-013.stdout")));
        assert!(!paths.artifact(&install.join("commands/command-014.stdout")));
        assert!(!paths.artifact(&install.join("commands/command-000.stdout")));
        assert!(!paths.artifact(Path::new(
            "/home/alex/work/pocket4-final-ihg-helper-build-other/owned-ihg-qa.apk"
        )));
        let build = paths.output(IhgPreparationMode::HelperBuild);
        for name in [
            "owned-ihg-qa.apk",
            "source/ActionRunner.java",
            "source/AndroidManifest.xml",
        ] {
            assert!(paths.uid1000_artifact(&build.join(name)));
        }
        for name in [
            "build-result.json",
            "private-signing/password.txt",
            "other.apk",
            "../owned-ihg-qa.apk",
        ] {
            assert!(!paths.uid1000_artifact(&build.join(name)));
        }
    }
    #[test]
    fn working_ihg_command_rejects_foreign_root_mode_and_extra_argv() {
        let paths = fixture();
        let recipe: Value = serde_json::from_str(RECIPE).unwrap();
        let prep = &recipe["members"]
            .as_array()
            .unwrap()
            .iter()
            .find(|v| v["relative_path"] == "preparations/ihg.json")
            .unwrap()["output"];
        for mode in [
            IhgPreparationMode::TargetIdentity,
            IhgPreparationMode::HelperSource,
            IhgPreparationMode::HelperBuild,
            IhgPreparationMode::HelperInstall,
            IhgPreparationMode::HelperIdentity,
            IhgPreparationMode::Plan,
        ] {
            let mut c = command(
                mode,
                &paths.request(mode),
                &"a".repeat(64),
                &paths.output(mode),
                prep,
            )
            .unwrap();
            check_working_arguments(&c, mode, &paths).unwrap();
            c.arg("--caller-passed");
            assert!(check_working_arguments(&c, mode, &paths).is_err());
            let foreign = command(
                mode,
                Path::new("/tmp/request.json"),
                &"a".repeat(64),
                &paths.output(mode),
                prep,
            )
            .unwrap();
            assert!(check_working_arguments(&foreign, mode, &paths).is_err());
        }
        assert!(
            check_working_arguments(&Command::new("/bin/sh"), IhgPreparationMode::Plan, &paths)
                .is_err()
        );
    }
}
