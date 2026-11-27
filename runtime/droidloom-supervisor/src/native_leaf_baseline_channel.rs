//! One private, check-only channel for the source-owned native leaf invocation.
//! Only a live NativeLeafBaselineObservation can create the production payload.
//! No pathname listener, command/PID/UID input or deserializable authority exists.
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::net::UnixDatagram;
use std::process::Command;
use std::time::{Duration, Instant};

// This is source-shared comparison identity, not a caller-selected member map.
const SOURCE_RECIPE: &[u8] =
    include_bytes!("../../../android/manifest/native-application-leaf-cohort-r2.json");
const COHORT_ROOT: &str =
    "/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const HOST_ENTRIES: [&str; 5] = [
    "source/support/business_ui_entry.py",
    "source/clock-support/business_ui_entry.py",
    "source/clock/clock_entry.py",
    "source/ihg/app_entry.py",
    "source/camera-photo/camera_entry.py",
];
fn compiled_host_entries() -> io::Result<serde_json::Map<String, serde_json::Value>> {
    let recipe: serde_json::Value = serde_json::from_slice(SOURCE_RECIPE)
        .map_err(|_| invalid("compiled leaf recipe JSON differs"))?;
    if recipe["schema"] != "droidloom.native-leaf-cohort-source-recipe.v1"
        || recipe["canonical_root"] != COHORT_ROOT
        || recipe["cohort"] != "cp3a-20261126-apps-r2"
    {
        return Err(invalid("compiled leaf source recipe identity differs"));
    }
    let members = recipe["members"]
        .as_array()
        .ok_or_else(|| invalid("compiled leaf member table absent"))?;
    if members.len() > 512 || recipe["output_file_count"].as_u64() != Some(members.len() as u64) {
        return Err(invalid("compiled leaf source member count differs"));
    }
    let mut out = serde_json::Map::new();
    for name in HOST_ENTRIES {
        let rows = members
            .iter()
            .filter(|row| row["relative_path"] == name)
            .collect::<Vec<_>>();
        if rows.len() != 1 {
            return Err(invalid("compiled fixed host entry is not unique"));
        }
        let pin = &rows[0]["output"];
        let path = format!("{COHORT_ROOT}/{name}");
        let object = pin
            .as_object()
            .ok_or_else(|| invalid("compiled host entry pin absent"))?;
        if object.len() != 3
            || pin["path"] != path
            || !pin["bytes"]
                .as_u64()
                .is_some_and(|v| (1..=2 * 1024 * 1024).contains(&v))
            || !pin["sha256"].as_str().is_some_and(|s| {
                s.len() == 64
                    && s.bytes()
                        .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            })
        {
            return Err(invalid("compiled host entry full pin differs"));
        }
        out.insert(path, pin.clone());
    }
    Ok(out)
}

fn monotonic_end(end: Instant) -> io::Result<u64> {
    let mut clock: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut clock) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // Sample the monotonic clock first, so conversion cannot extend the budget.
    let remaining = end
        .checked_duration_since(Instant::now())
        .ok_or_else(|| invalid("native leaf original deadline expired"))?;
    if remaining.is_zero()
        || remaining > Duration::from_secs(7200)
        || clock.tv_sec < 0
        || !(0..1_000_000_000).contains(&clock.tv_nsec)
    {
        return Err(invalid(
            "native leaf original deadline is outside its bound",
        ));
    }
    let now = (clock.tv_sec as u64)
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(clock.tv_nsec as u64))
        .ok_or_else(|| invalid("monotonic clock overflow"))?;
    now.checked_add(
        u64::try_from(remaining.as_nanos())
            .map_err(|_| invalid("native leaf deadline overflow"))?,
    )
    .ok_or_else(|| invalid("native leaf deadline overflow"))
}

pub(crate) const FACTS_ENV: &str = "DROIDLOOM_NATIVE_LEAF_FACTS_FD";
pub(crate) const GUARD_ENV: &str = "DROIDLOOM_NATIVE_LEAF_GUARD_FD";
const MAX_FACTS: usize = 262144;
const MAX_CHECKS: usize = 4096;

pub(crate) struct NativeLeafChannel {
    facts: File,
    server: UnixDatagram,
    child: UnixDatagram,
    deadline: Instant,
    checks: usize,
}
fn invalid(why: &'static str) -> io::Error {
    io::Error::other(why)
}
fn sealed(bytes: &[u8]) -> io::Result<File> {
    if bytes.is_empty() || bytes.len() > MAX_FACTS {
        return Err(invalid("native leaf facts bound"));
    }
    let raw = unsafe {
        libc::memfd_create(
            c"droidloom-native-leaf-facts".as_ptr(),
            libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut f = unsafe { File::from_raw_fd(raw) };
    f.write_all(bytes)?;
    let seals = libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE;
    if unsafe { libc::fcntl(f.as_raw_fd(), libc::F_ADD_SEALS, seals) } < 0 {
        return Err(io::Error::last_os_error());
    }
    // The pathname is the just-created descriptor, not an input name.
    let readonly = File::open(format!("/proc/self/fd/{}", f.as_raw_fd()))?;
    use std::os::unix::fs::MetadataExt;
    if readonly.metadata()?.ino() != f.metadata()?.ino()
        || readonly.metadata()?.dev() != f.metadata()?.dev()
        || unsafe { libc::fcntl(readonly.as_raw_fd(), libc::F_GET_SEALS) } != seals
    {
        return Err(invalid("native leaf sealed facts identity changed"));
    }
    Ok(readonly)
}
impl NativeLeafChannel {
    pub(crate) fn new(
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &crate::control::NativeApplicationInspector,
        deadline: Instant,
    ) -> Result<Self, String> {
        observation
            .verify_local(inspector, deadline)
            .map_err(|e| e.to_string())?;
        let deadline = deadline.min(observation.deadline());
        let bytes = serde_json::to_vec(&serde_json::json!({
            "schema":"droidloom.native-leaf-channel.v1",
            "baseline":observation.facts(),
            "host_source_entries":compiled_host_entries().map_err(|e|e.to_string())?,
            "normal_source_recipe":{"bytes":SOURCE_RECIPE.len(),"sha256":format!("{:x}", Sha256::digest(SOURCE_RECIPE))},
            "deadline_monotonic_ns":monotonic_end(deadline).map_err(|e|e.to_string())?,
            "comparison_only":true
        })).map_err(|e|e.to_string())?;
        Self::from_bytes(&bytes, deadline).map_err(|e| e.to_string())
    }
    fn from_bytes(bytes: &[u8], deadline: Instant) -> io::Result<Self> {
        if Instant::now() >= deadline {
            return Err(invalid("native leaf channel deadline expired"));
        }
        let facts = sealed(bytes)?;
        let (server, child) = UnixDatagram::pair()?;
        server.set_nonblocking(true)?;
        // Socketpair has no filesystem address; only these two held endpoints
        // exist. Parent retains the server, fixed exec inherits only child.
        Ok(Self {
            facts,
            server,
            child,
            deadline,
            checks: 0,
        })
    }
    pub(crate) fn prepare(&self, command: &mut Command) -> [RawFd; 2] {
        let f = self.facts.as_raw_fd();
        let g = self.child.as_raw_fd();
        command
            .env(FACTS_ENV, f.to_string())
            .env(GUARD_ENV, g.to_string());
        [f, g]
    }
    fn serve_with(&mut self, mut check: impl FnMut() -> Result<(), String>) -> Result<(), String> {
        let mut request = [0u8; 2];
        match self.server.recv(&mut request) {
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
            Err(e) => return Err(format!("native leaf guard channel failed: {e}")),
            Ok(n) => {
                if n != 1
                    || request[0] != b'G'
                    || self.checks >= MAX_CHECKS
                    || Instant::now() >= self.deadline
                {
                    let _ = self.server.send(b"1");
                    return Err(
                        "native leaf guard accepts only bounded current-custody checks".into(),
                    );
                }
            }
        }
        let result = check();
        if result.is_err() || Instant::now() >= self.deadline {
            let _ = self.server.send(b"1");
            return result.and(Err(
                "native leaf custody check finished after its actual invocation budget".into(),
            ));
        }
        self.server
            .send(b"0")
            .map_err(|e| format!("native leaf guard reply failed: {e}"))?;
        self.checks += 1;
        Ok(())
    }
    pub(crate) fn serve(
        &mut self,
        observation: &NativeLeafBaselineObservation<'_>,
        inspector: &crate::control::NativeApplicationInspector,
    ) -> Result<(), String> {
        let deadline = self.deadline;
        self.serve_with(|| {
            observation
                .verify_local(inspector, deadline)
                .map_err(|e| e.to_string())
        })
    }
    pub(crate) fn finish(&self) -> Result<(), String> {
        if self.checks == 0 {
            return Err("native leaf never checked the actual retained owner".into());
        }
        if Instant::now() >= self.deadline {
            return Err("native leaf channel retirement exceeded invocation budget".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    #[test]
    fn native_leaf_monotonic_deadline_never_renews_original_budget() {
        let before = Instant::now();
        assert!(monotonic_end(before).is_err());
        assert!(monotonic_end(before + Duration::from_secs(7201)).is_err());
        let end = before + Duration::from_secs(2);
        let projected = monotonic_end(end).unwrap();
        let mut actual: libc::timespec = unsafe { std::mem::zeroed() };
        assert_eq!(
            unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut actual) },
            0
        );
        let actual = actual.tv_sec as u64 * 1_000_000_000 + actual.tv_nsec as u64;
        assert!(projected > actual && projected - actual <= 2_000_000_000);
    }
    #[test]
    fn native_leaf_channel_seals_real_payload_and_has_no_path_listener() {
        let mut ch = NativeLeafChannel::from_bytes(
            b"{\"comparison_only\":true}",
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        let mut value = String::new();
        ch.facts.read_to_string(&mut value).unwrap();
        assert_eq!(value, "{\"comparison_only\":true}");
        assert_eq!(
            unsafe { libc::fcntl(ch.facts.as_raw_fd(), libc::F_GETFL) } & libc::O_ACCMODE,
            libc::O_RDONLY
        );
        assert!(ch.facts.write_all(b"x").is_err());
        assert!(ch.server.local_addr().unwrap().is_unnamed());
        ch.child.send(b"G").unwrap();
        let mut called = 0;
        ch.serve_with(|| {
            called += 1;
            Ok(())
        })
        .unwrap();
        let mut reply = [0u8; 1];
        assert_eq!(ch.child.recv(&mut reply).unwrap(), 1);
        assert_eq!(reply[0], b'0');
        assert_eq!(called, 1);
        ch.finish().unwrap();
    }
    #[test]
    fn native_leaf_channel_rejects_foreign_requests_expiry_and_failed_actual_guard() {
        for request in [b"P".as_slice(), b"GG", b""] {
            let mut ch =
                NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3))
                    .unwrap();
            ch.child.send(request).unwrap();
            assert!(
                ch.serve_with(|| panic!("unvalidated request must not query owner"))
                    .is_err()
            );
            assert!(ch.finish().is_err());
        }
        let mut ch =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        ch.child.send(b"G").unwrap();
        assert!(
            ch.serve_with(|| Err("actual original owner changed".into()))
                .unwrap_err()
                .contains("owner changed")
        );
        let mut reply = [0u8; 1];
        ch.child.recv(&mut reply).unwrap();
        assert_eq!(reply[0], b'1');
        assert!(ch.finish().is_err());
        let mut expired =
            NativeLeafChannel::from_bytes(b"{}", Instant::now() + Duration::from_secs(3)).unwrap();
        expired.deadline = Instant::now() - Duration::from_millis(1);
        expired.child.send(b"G").unwrap();
        assert!(
            expired
                .serve_with(|| panic!("expired channel must not query owner"))
                .is_err()
        );
    }
}
