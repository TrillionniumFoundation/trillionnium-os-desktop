//! Owned subprocess lifetime for qualification commands. No external PID is accepted.
use std::{
    io,
    os::unix::process::CommandExt,
    process::{Child, Command, ExitStatus},
};

pub struct OwnedChild {
    child: Child,
    reaped: bool,
}

impl OwnedChild {
    pub fn spawn(command: &mut Command) -> io::Result<Self> {
        // A separate group also contains ordinary helper children. The unreaped
        // leader reserves this PID until cleanup has finished.
        command.process_group(0);
        Ok(Self {
            child: command.spawn()?,
            reaped: false,
        })
    }

    pub fn id(&self) -> u32 {
        self.child.id()
    }

    pub fn try_wait(&mut self) -> io::Result<Option<ExitStatus>> {
        let result = self.child.try_wait()?;
        if result.is_some() {
            self.reaped = true;
        }
        Ok(result)
    }

    pub fn stop_and_reap(&mut self) -> io::Result<ExitStatus> {
        if !self.reaped {
            let raw = i32::try_from(self.child.id())
                .map_err(|_| io::Error::other("owned child PID outside native range"))?;
            let pid = rustix::process::Pid::from_raw(raw)
                .ok_or_else(|| io::Error::other("invalid owned child PID"))?;
            // Only this object's newly created group is signalled, and never
            // after wait/try_wait has released its leader's PID.
            let group = rustix::process::kill_process_group(pid, rustix::process::Signal::KILL);
            let direct = self.child.kill();
            if let Err(error) = group {
                if error != rustix::io::Errno::SRCH && direct.is_err() {
                    return Err(error.into());
                }
            }
        }
        let status = self.child.wait()?;
        self.reaped = true;
        Ok(status)
    }
}

impl Drop for OwnedChild {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = self.stop_and_reap();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn early_return_stops_and_reaps_owned_process() -> io::Result<()> {
        let mut command = Command::new("/usr/bin/sleep");
        command.arg("60");
        let child = OwnedChild::spawn(&mut command)?;
        let pid = rustix::process::Pid::from_raw(child.id() as i32).unwrap();
        assert!(rustix::process::test_kill_process(pid).is_ok());
        drop(child);
        assert_eq!(
            rustix::process::test_kill_process(pid),
            Err(rustix::io::Errno::SRCH)
        );
        Ok(())
    }

    #[test]
    fn normal_completion_is_reaped_without_later_signalling() -> io::Result<()> {
        let mut command = Command::new("/usr/bin/true");
        let mut child = OwnedChild::spawn(&mut command)?;
        let status = loop {
            if let Some(status) = child.try_wait()? {
                break status;
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        };
        assert!(status.success());
        assert!(child.reaped);
        assert!(child.stop_and_reap()?.success());
        Ok(())
    }
}
