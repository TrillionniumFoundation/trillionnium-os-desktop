//! A read-only Main resource observation from the actual early owner.
//! The expected epoch is a comparison only; no argument selects an owner,
//! process, path, descriptor, image, private transaction, or command.
use super::*;
use crate::control::application_custody::CustodyNamespace;
use crate::main_custody::{MainNodeIdentity, MainProcessCustody, RuntimeMainCustody, SCHEMA};

fn process_custody(
    process: Process,
    pidfd: &File,
    root: &File,
    executable: &File,
) -> Result<MainProcessCustody> {
    live(pidfd.as_fd())?;
    Ok(MainProcessCustody {
        host_pid: process.pid,
        parent_host_pid: process.parent,
        start_ticks: process.start,
        pidfd: MainNodeIdentity::of(&pidfd.metadata()?),
        root: MainNodeIdentity::of(&root.metadata()?),
        executable: MainNodeIdentity::of(&executable.metadata()?),
    })
}
impl EarlyApplicationAuthority<'_> {
    pub(crate) fn observe_main_custody(
        &self,
        expected: &RuntimeEpoch,
        deadline: Instant,
    ) -> Result<RuntimeMainCustody> {
        require(
            self.request_deadline() == Some(deadline),
            "Main observation requires the admitted private absolute deadline",
        )?;
        self.check_request_deadline()?;
        let held = self.observe_framework()?;
        require(
            &held.epoch == expected,
            "Main comparison epoch differs from the actual original framework",
        )?;
        let owner = self.image_custody_owner(deadline)?;
        let data_admission =
            crate::production_mounts::persistent_data::EarlyStorageAdmission::acquire(
                &self.base, self.group, self.owner,
            )
            .map_err(external)?;
        let persistent_data = self
            .data
            .observe_main_custody(&data_admission, &held.framework_metadata.root)
            .map_err(external)?;
        let init = process_custody(
            self.init,
            self.base.board().pidfd(),
            self.root,
            &self.init_program,
        )?;
        let zygote = process_custody(
            held.zygote,
            &held.zygote_pidfd,
            &held.zygote_metadata.root,
            &held.zygote_metadata.executable,
        )?;
        let framework = process_custody(
            held.framework,
            &held.framework_pidfd,
            &held.framework_metadata.root,
            &held.framework_metadata.executable,
        )?;
        let mut framework_namespaces = Vec::new();
        for (name, file) in ["user", "pid", "mount", "ipc", "uts", "net", "cgroup"]
            .into_iter()
            .zip(&held.framework_metadata.namespaces)
        {
            let node = file.metadata()?;
            framework_namespaces.push(CustodyNamespace {
                name: name.into(),
                device: node.dev(),
                inode: node.ino(),
            });
        }
        framework_namespaces.sort_by(|a, b| a.name.cmp(&b.name));
        self.verify_framework_processes(&held)?;
        require(
            self.data
                .observe_main_custody(&data_admission, &held.framework_metadata.root)
                .map_err(external)?
                == persistent_data,
            "Main persistent resources changed across the actual observation",
        )?;
        require(
            self.image_custody_owner(deadline)? == owner,
            "Main selection or namespace owner changed across the observation",
        )?;
        self.verify_framework_processes(&held)?;
        self.check_request_deadline()?;
        let result = RuntimeMainCustody {
            schema: SCHEMA.into(),
            epoch: held.epoch.clone(),
            owner,
            init,
            zygote,
            framework,
            framework_namespaces,
            persistent_data,
        };
        result
            .validate(expected)
            .map_err(|why| NamespaceError::RuntimeResource(why))?;
        Ok(result)
    }
}
