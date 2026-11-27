//! Thread-local filesystem credentials for the one normal UID-1000 public
//! material directory. Real/effective/saved IDs and the original capability
//! snapshot remain unchanged; this supplies no filesystem policy permission.
use std::{fs, marker::PhantomData, rc::Rc};
type Result<T> = std::result::Result<T, String>;
fn ids() -> (u32, u32) {
    // Linux's invalid all-ones ID queries without changing either credential.
    unsafe {
        (
            libc::setfsuid(u32::MAX) as u32,
            libc::setfsgid(u32::MAX) as u32,
        )
    }
}
fn snapshot() -> Result<Vec<String>> {
    let text = fs::read_to_string("/proc/thread-self/status").map_err(|e| e.to_string())?;
    let names = [
        "Uid:", "Gid:", "Groups:", "CapInh:", "CapPrm:", "CapEff:", "CapBnd:", "CapAmb:",
    ];
    let mut result = Vec::new();
    for name in names {
        let lines = text
            .lines()
            .filter(|l| l.starts_with(name))
            .collect::<Vec<_>>();
        if lines.len() != 1 {
            return Err("working filesystem identity snapshot is incomplete".into());
        }
        if matches!(name, "Uid:" | "Gid:")
            && lines[0].split_whitespace().skip(1).collect::<Vec<_>>() != ["0"; 4]
        {
            return Err(
                "working public material scope requires the original root identities".into(),
            );
        }
        result.push(lines[0].to_owned());
    }
    Ok(result)
}
struct Scope {
    before: Vec<String>,
    tid: libc::pid_t,
    active: bool,
    _local: PhantomData<Rc<()>>,
}
impl Scope {
    fn enter() -> Result<Self> {
        let before = snapshot()?;
        if ids() != (0, 0) {
            return Err("working filesystem scope did not begin at root".into());
        }
        let mut result = Self {
            before,
            tid: unsafe { libc::syscall(libc::SYS_gettid) as libc::pid_t },
            active: true,
            _local: PhantomData,
        };
        // These syscalls change only this thread's filesystem access identity.
        unsafe {
            libc::setfsgid(1000);
            libc::setfsuid(1000);
        }
        if ids() != (1000, 1000) {
            result.restore()?;
            return Err("normal fixed UID-1000 filesystem transition was refused".into());
        }
        Ok(result)
    }
    fn restore(&mut self) -> Result<()> {
        if !self.active {
            return Ok(());
        }
        if unsafe { libc::syscall(libc::SYS_gettid) as libc::pid_t } != self.tid {
            return Err("working filesystem scope moved to another thread".into());
        }
        unsafe {
            libc::setfsuid(0);
            libc::setfsgid(0);
        }
        if ids() != (0, 0) || snapshot()? != self.before {
            return Err(
                "working root filesystem credentials/capabilities did not restore exactly".into(),
            );
        }
        self.active = false;
        Ok(())
    }
}
impl Drop for Scope {
    fn drop(&mut self) {
        if self.active && self.restore().is_err() {
            // Never continue the owner or an Android effect with changed IDs.
            std::process::abort();
        }
    }
}
pub(super) fn with_public_source<T>(action: impl FnOnce() -> Result<T>) -> Result<T> {
    let mut scope = Scope::enter()?;
    let result = action();
    scope.restore()?;
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_source_credentials_are_fixed_and_restore_or_reject_before_the_action() {
        let before = ids();
        if unsafe { libc::geteuid() } == 0 {
            let original = snapshot().unwrap();
            with_public_source(|| {
                assert_eq!(ids(), (1000, 1000));
                Ok(())
            })
            .unwrap();
            assert_eq!(ids(), before);
            assert_eq!(snapshot().unwrap(), original);
        } else {
            let mut called = false;
            assert!(
                with_public_source(|| {
                    called = true;
                    Ok(())
                })
                .is_err()
            );
            assert!(!called);
            assert_eq!(ids(), before);
        }
    }
}
