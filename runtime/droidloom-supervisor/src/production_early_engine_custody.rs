//! Engine observation borrowed only from the actual early owner.
//! Candidate PIDs are discovered through its held procfs and bound to PIDFDs;
//! no public request selects a process, path, context, image or namespace.
use super::*;
use crate::control::application_probe::ApplicationMetadata;
use crate::engine_custody::{
    EngineAbiComparison, EngineImageSource, EngineKind, EngineProcess, RuntimeEngineObservation,
};
use crate::main_custody::RuntimeMainCustody;
use crate::production_application::{EngineTarget, observe_engine};

pub(crate) struct HeldEngineObservation {
    pidfd: File,
    framework: EarlyFrameworkObservation,
    source: EngineImageSource,
    first: crate::production_application::EngineSample,
}
impl HeldEngineObservation {
    pub(crate) fn process(&self) -> &EngineProcess {
        &self.first.process
    }
}
fn observer_error(error: crate::production_application::ApplicationError) -> NamespaceError {
    match error {
        crate::production_application::ApplicationError::RetirementUnproven => {
            NamespaceError::RetirementUnproven
        }
        crate::production_application::ApplicationError::Io(error) => NamespaceError::Io(error),
        error => external(error),
    }
}
impl EarlyApplicationAuthority<'_> {
    pub(crate) fn begin_engine_observation(
        &self,
        application: &ApplicationMetadata,
        main: &RuntimeMainCustody,
        kind: EngineKind,
        deadline: Instant,
    ) -> Result<HeldEngineObservation> {
        require(
            self.request_deadline() == Some(deadline)
                && &application.epoch == &main.epoch
                && application.user == 0
                && crate::engine_custody::selected_package(&application.package)
                && crate::engine_custody::user_zero_app_uid(application.uid),
            "engine request does not match the fixed current application",
        )?;
        self.check_request_deadline()?;
        let framework = self.observe_framework()?;
        require(
            framework.epoch == main.epoch
                && framework.zygote.pid == main.zygote.host_pid
                && framework.zygote.start == main.zygote.start_ticks,
            "engine observation crossed the original Main epoch",
        )?;
        let source = self
            .images
            .observe_engine_origin_early(&self.base, kind, deadline, self.progress)
            .map_err(external)?;
        let (uids, gids) = self.base.identity_lease().broker_ranges();
        require(
            application.uid < uids.count && application.uid < gids.count,
            "engine UID is outside the held idmap",
        )?;
        let uid = uids
            .start
            .checked_add(application.uid)
            .ok_or(NamespaceError::Rejected("engine UID overflow"))?;
        let gid = gids
            .start
            .checked_add(application.uid)
            .ok_or(NamespaceError::Rejected("engine GID overflow"))?;
        let mut found = None;
        let mut count = 0usize;
        for entry in std::fs::read_dir(format!("/proc/self/fd/{}", self.proc_root.as_raw_fd()))? {
            self.check_request_deadline()?;
            let entry = entry?;
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            if name.is_empty() || !name.bytes().all(|v| v.is_ascii_digit()) {
                continue;
            }
            count += 1;
            require(count <= 131072, "engine process inventory bound")?;
            let pid = name.parse::<u32>().map_err(external)?;
            let candidate =
                (|| -> Result<Option<(File, crate::production_application::EngineSample)>> {
                    let fd = pidfd(i32::try_from(pid).map_err(external)?)?;
                    live(fd.as_fd())?;
                    let ids = info(fd.as_fd(), true)?;
                    if ids.pid != pid
                        || ids.tgid != pid
                        || ids.ppid != framework.zygote.pid
                        || [ids.ruid, ids.euid, ids.suid, ids.fsuid] != [uid; 4]
                        || [ids.rgid, ids.egid, ids.sgid, ids.fsgid] != [gid; 4]
                    {
                        return Ok(None);
                    }
                    let request = EngineTarget {
                        package: application.package.clone(),
                        uid: application.uid,
                        main: main.clone(),
                        source: source.clone(),
                    };
                    let observed =
                        observe_engine(request, &fd, self.base.user_namespace(), deadline)
                            .map_err(observer_error)?;
                    self.check_request_deadline()?;
                    match observed {
                        Some(observed) => Ok(Some((fd, observed))),
                        None => Ok(None),
                    }
                })();
            match request_checked(&self.base, candidate) {
                Ok(Some((fd, observed))) => {
                    require(found.is_none(), "multiple actual package main processes")?;
                    found = Some((fd, observed));
                }
                Ok(None) => {}
                Err(NamespaceError::Io(error))
                    if matches!(error.raw_os_error(), Some(libc::ENOENT | libc::ESRCH)) => {}
                Err(error) => return Err(error),
            }
        }
        let (pidfd, first) = found.ok_or(NamespaceError::Rejected(
            "the selected package has no live main process with its fixed engine",
        ))?;
        self.verify_framework_processes(&framework)?;
        live(pidfd.as_fd())?;
        Ok(HeldEngineObservation {
            pidfd,
            framework,
            source,
            first,
        })
    }
    pub(crate) fn complete_engine_observation(
        &self,
        held: HeldEngineObservation,
        application: ApplicationMetadata,
        main: RuntimeMainCustody,
        runtime_abi: EngineAbiComparison,
        deadline: Instant,
    ) -> Result<RuntimeEngineObservation> {
        self.check_request_deadline()?;
        self.verify_framework_processes(&held.framework)?;
        let request = EngineTarget {
            package: application.package.clone(),
            uid: application.uid,
            main: main.clone(),
            source: held.source.clone(),
        };
        let last = observe_engine(request, &held.pidfd, self.base.user_namespace(), deadline)
            .map_err(observer_error)?
            .ok_or(NamespaceError::Rejected(
                "original package process no longer matches",
            ))?;
        require(
            last.process == held.first.process
                && last.engine == held.first.engine
                && last.mappings == held.first.mappings
                && last.native_executable == held.first.native_executable,
            "original engine process or mappings changed during PM and Main bookends",
        )?;
        require(
            self.images
                .observe_engine_origin_early(
                    &self.base,
                    held.source.kind(),
                    deadline,
                    self.progress,
                )
                .map_err(external)?
                == held.source,
            "original immutable engine owner changed",
        )?;
        self.verify_framework_processes(&held.framework)?;
        live(held.pidfd.as_fd())?;
        self.check_request_deadline()?;
        let observed = RuntimeEngineObservation {
            schema: crate::engine_custody::SCHEMA.into(),
            application: application.clone(),
            apk_bytes_hashed_by_engine_observer: false,
            main: main.clone(),
            source: held.source,
            process: last.process,
            actual_engine: last.engine,
            mappings: last.mappings,
            native_executable: last.native_executable,
            runtime_abi,
            maps_before_sha256: held.first.maps_before_sha256,
            maps_after_sha256: last.maps_after_sha256,
            observed_monotonic_ns: last.observed_monotonic_ns,
            translation_business_success_verified: false,
        };
        observed
            .validate(&main, &application)
            .map_err(NamespaceError::RuntimeResource)?;
        live(held.pidfd.as_fd())?;
        Ok(observed)
    }
}
