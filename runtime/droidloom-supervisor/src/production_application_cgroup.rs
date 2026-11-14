//! One transient read worker leaf below the original production hard budget.
//! It is a root-owned sibling of the delegated guest payload. The guest cannot
//! move tasks into or out of it. No caller supplies a path, PID, or limit.
use super::*;
use crate::production_application::ApplicationRetired;
use std::mem::ManuallyDrop;
use std::time::{Duration, Instant};

const NAME: &CStr = c"application-read";
const WORKER_MEMORY: u64 = 512 * 1024 * 1024;
const WORKER_PIDS: &str = "64";
const WORKER_CPU: &str = "100000 100000";

pub(crate) struct ApplicationLeaf<'a> {
    owner: &'a PreparedCgroup,
    directory: ManuallyDrop<Directory>,
    lent: bool,
    retired: bool,
}

impl PreparedCgroup {
    pub(crate) fn application_leaf<'a>(
        &'a self,
        witness: &CgroupTreeReadyWitness<'_>,
    ) -> Result<ApplicationLeaf<'a>> {
        self.require_guest_active(witness)?;
        let r = self.get();
        require(
            !r.application_active.get(),
            "another application read owns the fixed leaf",
        )?;
        let existing = list_directories(&r.budget.file)?;
        require(
            existing
                == vec![
                    CString::new("keeper").unwrap(),
                    CString::new("payload").unwrap(),
                ],
            "production budget has an unexpected immediate child",
        )?;
        // Mark the attempt before the first mutation. An uncertain mkdir/open
        // cannot silently grant a second command or release the original lease.
        r.application_active.set(true);
        if let Err(error) = mkdir_at(&r.budget.file, NAME, 0o700) {
            r.application_quarantined.set(true);
            return Err(error);
        }
        let directory = match Directory::at(&r.budget.file, NAME) {
            Ok(value) => value,
            Err(error) => {
                r.application_quarantined.set(true);
                return Err(error);
            }
        };
        let leaf = ApplicationLeaf {
            owner: self,
            directory: ManuallyDrop::new(directory),
            lent: false,
            retired: false,
        };
        trusted_directory(&leaf.directory.file)?;
        write_control(
            &leaf.directory.file,
            c"memory.max",
            &WORKER_MEMORY.to_string(),
        )?;
        write_control(
            &leaf.directory.file,
            c"memory.high",
            &(384_u64 * 1024 * 1024).to_string(),
        )?;
        write_control(&leaf.directory.file, c"memory.swap.max", "0")?;
        write_control(&leaf.directory.file, c"cpu.max", WORKER_CPU)?;
        write_control(&leaf.directory.file, c"pids.max", WORKER_PIDS)?;
        leaf.check()?;
        require(
            !populated(&leaf.directory.file)? && read_pids(&leaf.directory.file)?.is_empty(),
            "new application leaf is occupied",
        )?;
        Ok(leaf)
    }
}

impl ApplicationLeaf<'_> {
    fn check(&self) -> Result<()> {
        let r = self.owner.get();
        require(
            !self.retired && r.application_active.get(),
            "application leaf is retired",
        )?;
        r.budget.check(&r.unit.file, &r.name)?;
        self.directory.check(&r.budget.file, NAME)?;
        trusted_directory(&self.directory.file)?;
        require(
            self.directory.file.metadata()?.mode() & 0o7777 == 0o700,
            "application leaf permissions changed",
        )?;
        require(
            read_control(&self.directory.file, c"cgroup.type")? == "domain"
                && read_control(&self.directory.file, c"cgroup.subtree_control")?.is_empty()
                && list_directories(&self.directory.file)?.is_empty(),
            "application leaf gained a child or changed type",
        )?;
        require(
            read_control(&self.directory.file, c"memory.max")? == WORKER_MEMORY.to_string()
                && read_control(&self.directory.file, c"memory.high")?
                    == (384_u64 * 1024 * 1024).to_string()
                && read_control(&self.directory.file, c"memory.swap.max")? == "0"
                && read_control(&self.directory.file, c"pids.max")? == WORKER_PIDS
                && read_control(&self.directory.file, c"cpu.max")? == WORKER_CPU,
            "application worker limits changed",
        )?;
        // No parent budget or CPU placement is relaxed to admit a read.
        check_limits(&r.budget.file)?;
        check_placement_masks(&r.budget.file, &r.mems)
    }

    pub(crate) fn clone_target(&mut self) -> Result<BorrowedFd<'_>> {
        self.check()?;
        require(!self.lent, "application initial clone is single use")?;
        self.lent = true;
        Ok(self.directory.file.as_fd())
    }

    pub(crate) fn identity(&self) -> Result<(u64, u64)> {
        self.check()?;
        Ok((self.directory.identity.dev, self.directory.identity.ino))
    }

    pub(crate) fn verify_member(&self, proc_directory: &File) -> Result<()> {
        self.check()?;
        check_task_cgroup(
            proc_directory,
            &format!("{UNIT_CGROUP}/cell-u1000/application-read"),
        )
    }

    pub(crate) fn kill(&self) -> Result<()> {
        // Retirement authority is the retained inode, not current admission
        // or a rediscovered name. Failure still quarantines this exact owner.
        self.directory.check(&self.owner.get().budget.file, NAME)?;
        write_control(&self.directory.file, c"cgroup.kill", "1")
    }

    pub(crate) fn wait_empty(&self, deadline: Instant) -> Result<()> {
        loop {
            self.directory.check(&self.owner.get().budget.file, NAME)?;
            if !populated(&self.directory.file)? && read_pids(&self.directory.file)?.is_empty() {
                return Ok(());
            }
            require(
                Instant::now() < deadline,
                "application leaf retirement deadline",
            )?;
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    pub(crate) fn retire(&mut self, proof: &ApplicationRetired<'_>) -> Result<()> {
        proof
            .verify_cgroup(&self.directory.file)
            .map_err(|error| CgroupError::Owner(error.to_string()))?;
        self.remove_empty()
    }

    fn remove_empty(&mut self) -> Result<()> {
        let r = self.owner.get();
        self.directory.check(&r.budget.file, NAME)?;
        require(
            !populated(&self.directory.file)?
                && read_pids(&self.directory.file)?.is_empty()
                && list_directories(&self.directory.file)?.is_empty(),
            "application leaf is not completely empty",
        )?;
        unlink_directory(&r.budget.file, NAME)?;
        match open_at(&r.budget.file, NAME, libc::O_RDONLY | libc::O_DIRECTORY) {
            Err(CgroupError::Io(error)) if error.raw_os_error() == Some(libc::ENOENT) => {}
            _ => {
                return Err(CgroupError::Rejected(
                    "application leaf removal was not confirmed",
                ));
            }
        }
        self.retired = true;
        r.application_active.set(false);
        Ok(())
    }
}

impl Drop for ApplicationLeaf<'_> {
    fn drop(&mut self) {
        if !self.retired && !self.lent {
            let _ = self.remove_empty();
        }
        if self.retired {
            unsafe {
                ManuallyDrop::drop(&mut self.directory);
            }
        } else {
            // Its open directory and the original admission stay retained.
            // Empty cgroup.procs alone is not a substitute for actual waitid.
            self.owner.get().application_quarantined.set(true);
        }
    }
}
