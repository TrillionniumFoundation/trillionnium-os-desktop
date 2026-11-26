//! Retain only the three capabilities required by the existing maintenance
//! child. The return role has no SELinux capability grants and has effective
//! capabilities zero; the exact maintenance exec may regain these three from
//! its unchanged permitted set even with no_new_privs set.
use std::io;

pub(crate) const MAINTENANCE: u64 = (1 << 5) | (1 << 6) | (1 << 7);
const LAST_CAP: u32 = 40;

#[repr(C)]
struct Header {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct Data {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Snapshot {
    pub(crate) effective: u64,
    pub(crate) permitted: u64,
    pub(crate) inheritable: u64,
    pub(crate) ambient: u64,
    pub(crate) bounding: u64,
    pub(crate) no_new_privs: bool,
}

fn denied(why: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
fn checked(value: libc::c_long) -> io::Result<libc::c_long> {
    if value < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(value)
    }
}

pub(crate) fn inspect() -> io::Result<Snapshot> {
    let header = Header {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut data = [Data::default(); 2];
    checked(unsafe { libc::syscall(libc::SYS_capget, &header, data.as_mut_ptr()) })?;
    let mut ambient = 0;
    let mut bounding = 0;
    for cap in 0..=LAST_CAP {
        let b = checked(unsafe { libc::prctl(libc::PR_CAPBSET_READ, cap, 0, 0, 0) } as _)?;
        let a = checked(unsafe {
            libc::prctl(libc::PR_CAP_AMBIENT, libc::PR_CAP_AMBIENT_IS_SET, cap, 0, 0)
        } as _)?;
        if ![0, 1].contains(&a) || ![0, 1].contains(&b) {
            return Err(denied("invalid capability bit observation"));
        }
        ambient |= (a as u64) << cap;
        bounding |= (b as u64) << cap;
    }
    // The selected 6.18 ABI ends at CAP_CHECKPOINT_RESTORE. Do not silently
    // omit a capability introduced by a different running kernel.
    let beyond = unsafe { libc::prctl(libc::PR_CAPBSET_READ, LAST_CAP + 1, 0, 0, 0) };
    if beyond != -1 || io::Error::last_os_error().raw_os_error() != Some(libc::EINVAL) {
        return Err(denied(
            "running capability ABI differs from the selected kernel",
        ));
    }
    let nnp = checked(unsafe { libc::prctl(libc::PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) } as _)?;
    if ![0, 1].contains(&nnp) {
        return Err(denied("invalid no_new_privs observation"));
    }
    Ok(Snapshot {
        effective: u64::from(data[0].effective) | (u64::from(data[1].effective) << 32),
        permitted: u64::from(data[0].permitted) | (u64::from(data[1].permitted) << 32),
        inheritable: u64::from(data[0].inheritable) | (u64::from(data[1].inheritable) << 32),
        ambient,
        bounding,
        no_new_privs: nnp == 1,
    })
}

fn expected(effective: u64, no_new_privs: bool) -> Snapshot {
    Snapshot {
        effective,
        permitted: MAINTENANCE,
        inheritable: 0,
        ambient: 0,
        bounding: MAINTENANCE,
        no_new_privs,
    }
}

pub(crate) fn seal() -> io::Result<Snapshot> {
    let mut ids = [1u32; 6];
    checked(unsafe { libc::getresuid(&mut ids[0], &mut ids[1], &mut ids[2]) } as _)?;
    checked(unsafe { libc::getresgid(&mut ids[3], &mut ids[4], &mut ids[5]) } as _)?;
    if ids != [0; 6] || inspect()? != expected(MAINTENANCE, false) {
        return Err(denied(
            "return service does not have its exact normal root capability contract",
        ));
    }
    let header = Header {
        version: 0x2008_0522,
        pid: 0,
    };
    let data = [
        Data {
            effective: 0,
            permitted: MAINTENANCE as u32,
            inheritable: 0,
        },
        Data::default(),
    ];
    checked(unsafe { libc::syscall(libc::SYS_capset, &header, data.as_ptr()) })?;
    checked(unsafe {
        libc::prctl(
            libc::PR_CAP_AMBIENT,
            libc::PR_CAP_AMBIENT_CLEAR_ALL,
            0,
            0,
            0,
        )
    } as _)?;
    checked(unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } as _)?;
    checked(unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } as _)?;
    let actual = inspect()?;
    if actual != expected(0, true) || unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) } != 0
    {
        return Err(denied(
            "return entry did not seal its effective capabilities and descriptors",
        ));
    }
    Ok(actual)
}

pub(crate) fn revalidate() -> io::Result<()> {
    if inspect()? != expected(0, true)
        || unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) } != 0
    {
        return Err(denied("return entry capability custody changed"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;

    // The actual exec mechanism is exercised only in a new unprivileged user
    // and PID namespace. There is no test escape to physical initial root.
    #[test]
    #[ignore = "requires a protected root runner; all mutations occur inside fresh namespaces"]
    fn actual_root_exec_with_nnp_restores_only_the_original_three_permitted_caps() -> io::Result<()>
    {
        const TEST: &str = "native_once_capabilities::tests::actual_root_exec_with_nnp_restores_only_the_original_three_permitted_caps";
        let phase = std::env::var("DROIDLOOM_ONCE_CAP_EXEC_TEST").ok();
        if let Some(phase) = phase {
            if std::fs::read_link("/proc/self/ns/user")?
                == std::path::Path::new("user:[4026531837]")
                || unsafe { libc::getuid() } != 0
                || unsafe { libc::geteuid() } != 0
            {
                return Err(denied(
                    "capability exec test refuses the physical initial user namespace",
                ));
            }
            if phase == "observe" {
                let actual = inspect()?;
                assert_eq!(actual, expected(MAINTENANCE, true));
                println!("actual_exec_child={actual:?}");
                return Ok(());
            }
            assert_eq!(phase, "prepare");
            for cap in 0..=LAST_CAP {
                if MAINTENANCE & (1u64 << cap) == 0 {
                    checked(unsafe { libc::prctl(libc::PR_CAPBSET_DROP, cap, 0, 0, 0) } as _)?;
                }
            }
            let header = Header {
                version: 0x2008_0522,
                pid: 0,
            };
            let data = [
                Data {
                    effective: MAINTENANCE as u32,
                    permitted: MAINTENANCE as u32,
                    inheritable: 0,
                },
                Data::default(),
            ];
            checked(unsafe { libc::syscall(libc::SYS_capset, &header, data.as_ptr()) })?;
            let before = seal()?;
            assert_eq!(before.effective, 0);
            let child = Command::new(std::env::current_exe()?)
                .args(["--exact", TEST, "--ignored", "--nocapture"])
                .env("DROIDLOOM_ONCE_CAP_EXEC_TEST", "observe")
                .output()?;
            print!("{}", String::from_utf8_lossy(&child.stdout));
            eprint!("{}", String::from_utf8_lossy(&child.stderr));
            assert!(child.status.success());
            assert!(
                String::from_utf8_lossy(&child.stdout).contains("actual_exec_child=Snapshot"),
                "recursive test must actually execute the child observation"
            );
            revalidate()?;
            return Ok(());
        }
        let child = Command::new("/usr/bin/unshare")
            .args([
                "--user",
                "--map-root-user",
                "--mount",
                "--pid",
                "--fork",
                "--mount-proc",
            ])
            .arg(std::env::current_exe()?)
            .args(["--exact", TEST, "--ignored", "--nocapture"])
            .env("DROIDLOOM_ONCE_CAP_EXEC_TEST", "prepare")
            .output()?;
        print!("{}", String::from_utf8_lossy(&child.stdout));
        eprint!("{}", String::from_utf8_lossy(&child.stderr));
        assert!(
            child.status.success(),
            "isolated real credential exec did not complete"
        );
        assert!(
            String::from_utf8_lossy(&child.stdout).contains("actual_exec_child=Snapshot"),
            "namespace test must actually execute the child observation"
        );
        Ok(())
    }
}
