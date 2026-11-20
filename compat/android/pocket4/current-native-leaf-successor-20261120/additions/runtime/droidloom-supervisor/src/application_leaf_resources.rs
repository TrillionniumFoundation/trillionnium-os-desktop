//! Real ancestor limits for the native Gallery leaf's nested owned group.
//!
//! A cgroup v2 parent containing the dispatcher cannot enable memory below
//! itself. Its held local hard limits nevertheless bound all descendants.
//! Keep the original nested retirement scope; never create an outside sibling,
//! enable shared controllers or turn a child `max` into an invented limit.
use super::{current_cgroup_parent, invalid, open_at};
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{self, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt};
use std::path::{Path, PathBuf};

const GALLERY_LIMITS: [(&std::ffi::CStr, &str); 4] = [
    (c"cpu.max", "200000 100000"),
    (c"memory.max", "2147483648"),
    (c"memory.swap.max", "0"),
    (c"pids.max", "64"),
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum Profile { Gallery, CalendarReminder }
impl Profile {
    fn limits(self) -> [(&'static std::ffi::CStr, &'static str); 4] {
        match self {
            Self::Gallery => GALLERY_LIMITS,
            Self::CalendarReminder => [(c"cpu.max", "50000 100000"),
                (c"memory.max", "536870912"), (c"memory.swap.max", "0"), (c"pids.max", "64")],
        }
    }
    pub(super) fn prefix(self) -> &'static str {
        match self { Self::Gallery => "droidloom-app-gallery-leaf", Self::CalendarReminder => "droidloom-app-calendar-reminder-leaf" }
    }
}

fn identity(file: &File) -> io::Result<[u64; 6]> {
    let m = file.metadata()?;
    Ok([m.dev(), m.ino(), u64::from(m.mode()), u64::from(m.uid()), u64::from(m.gid()), m.nlink()])
}

fn text(file: &File) -> io::Result<String> {
    let mut raw = [0_u8; 4097];
    let n = file.read_at(&mut raw, 0)?;
    if n > 4096 {
        return Err(invalid("Gallery ancestor metadata exceeds its bound"));
    }
    std::str::from_utf8(&raw[..n]).map(str::trim).map(str::to_owned)
        .map_err(|_| invalid("Gallery ancestor metadata is not UTF-8"))
}

fn valid_limits(values: &[String], profile: Profile) -> io::Result<()> {
    if values.len() != 4 { return Err(invalid("complete ancestor limits required")); }
    let cpu: Vec<_> = values[0].split_ascii_whitespace().collect();
    let quota = cpu.first().and_then(|x| x.parse::<u64>().ok());
    let period = cpu.get(1).and_then(|x| x.parse::<u64>().ok());
    let expected=profile.limits();
    let cpu_ok=matches!((quota,period),(Some(q),Some(p)) if q>0 && p>0 && match profile {
        Profile::Gallery => u128::from(q)<=2*u128::from(p),
        Profile::CalendarReminder => 2*u128::from(q)<=u128::from(p),
    });
    if cpu.len() != 2 || !cpu_ok
        || values[1] != expected[1].1 || values[2] != "0" || values[3] != "64"
    {
        return Err(invalid("native leaf requires its original numeric CPU/memory/no-swap/64-PID ancestor limits"));
    }
    Ok(())
}

fn no_oom(raw: &str) -> io::Result<()> {
    let mut events = BTreeMap::new();
    for line in raw.lines() {
        let words: Vec<_> = line.split_ascii_whitespace().collect();
        let [key, value] = words.as_slice() else { return Err(invalid("invalid ancestor memory events")); };
        let value = value.parse::<u64>().map_err(|_| invalid("invalid ancestor memory event number"))?;
        if events.insert(*key, value).is_some() { return Err(invalid("duplicate ancestor memory event")); }
    }
    if ["oom", "oom_kill", "oom_group_kill"].iter().any(|key| events.get(key) != Some(&0)) {
        return Err(invalid("Gallery ancestor has an OOM event"));
    }
    Ok(())
}

struct Control {
    name: &'static std::ffi::CStr,
    file: File,
    identity: [u64; 6],
}

impl Control {
    fn capture(parent: &File, name: &'static std::ffi::CStr) -> io::Result<Self> {
        let file = open_at(parent.as_raw_fd(), name, libc::O_RDONLY | libc::O_NOFOLLOW)?;
        let identity = identity(&file)?;
        if identity[3..5] != [0, 0] || identity[2] & 0o022 != 0 {
            return Err(invalid("root-owned ancestor resource control required"));
        }
        Ok(Self { name, file, identity })
    }

    fn validate(&self, parent: &File) -> io::Result<String> {
        let named = open_at(parent.as_raw_fd(), self.name, libc::O_RDONLY | libc::O_NOFOLLOW)?;
        if identity(&self.file)? != self.identity || identity(&named)? != self.identity {
            return Err(invalid("held ancestor resource control replaced"));
        }
        text(&self.file)
    }
}

pub(super) struct Scope {
    profile: Profile,
    path: PathBuf,
    parent: File,
    identity: [u64; 6],
    limits: Vec<Control>,
    values: Vec<String>,
    events: Control,
    swap: Control,
}

impl Scope {
    pub(super) fn capture(path: &Path, parent: &File, profile: Profile) -> io::Result<Self> {
        if path == Path::new("/sys/fs/cgroup") || current_cgroup_parent()? != path {
            return Err(invalid("Gallery requires the dispatcher's actual nonroot owned parent"));
        }
        let parent = parent.try_clone()?;
        let identity = identity(&parent)?;
        if identity[3..5] != [0, 0] || identity[2] & 0o022 != 0 {
            return Err(invalid("root-owned native Gallery parent required"));
        }
        let limits = profile.limits().iter().map(|(name, _)| Control::capture(&parent, name)).collect::<io::Result<Vec<_>>>()?;
        let values = limits.iter().map(|item| text(&item.file)).collect::<io::Result<Vec<_>>>()?;
        valid_limits(&values,profile)?;
        let events = Control::capture(&parent, c"memory.events")?;
        let swap = Control::capture(&parent, c"memory.swap.current")?;
        let result = Self { profile, path: path.into(), parent, identity, limits, values, events, swap };
        result.validate()?;
        Ok(result)
    }

    pub(super) fn configure_child(&self,child: &File) -> io::Result<()> {
        configure_child(child,self.profile)
    }

    pub(super) fn validate(&self) -> io::Result<()> {
        let named = fs::symlink_metadata(&self.path)?;
        let observed = [named.dev(), named.ino(), u64::from(named.mode()), u64::from(named.uid()), u64::from(named.gid())];
        // Creating/removing owned child directories can change link count;
        // dev/inode/type/mode/owner remain the held ancestor's exact identity.
        if current_cgroup_parent()? != self.path || identity(&self.parent)?[..5] != self.identity[..5]
            || observed != self.identity[..5]
        { return Err(invalid("native Gallery ancestor changed")); }
        let values = self.limits.iter().map(|item| item.validate(&self.parent)).collect::<io::Result<Vec<_>>>()?;
        if values != self.values { return Err(invalid("pinned native Gallery ancestor limits changed")); }
        valid_limits(&values,self.profile)?;
        no_oom(&self.events.validate(&self.parent)?)?;
        if self.swap.validate(&self.parent)? != "0" { return Err(invalid("native Gallery ancestor used swap")); }
        Ok(())
    }
}

/// Set only controls already exposed in this exclusively created empty child.
/// An absent local controller is covered by the held ancestor's real limit.
pub(super) fn configure_child(child: &File, profile: Profile) -> io::Result<()> {
    for (name, value) in profile.limits() {
        let mut file = match open_at(child.as_raw_fd(), name, libc::O_RDWR | libc::O_NOFOLLOW) {
            Ok(file) => file,
            Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
            Err(error) => return Err(error),
        };
        file.write_all(value.as_bytes())?;
        if text(&file)? != value { return Err(invalid("new Gallery child local limit readback differs")); }
    }
    Ok(())
}

pub(super) fn require_original_cpu_available() -> io::Result<()> {
    let mut mask = std::mem::MaybeUninit::<libc::cpu_set_t>::zeroed();
    // SAFETY: mask points to correctly sized writable cpu_set_t storage.
    if unsafe { libc::sched_getaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), mask.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: sched_getaffinity succeeded; CPU 20 is in cpu_set_t's range.
    if !unsafe { libc::CPU_ISSET(20, &mask.assume_init()) } {
        return Err(invalid("original Gallery CPU 20 is outside dispatcher affinity"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn effective_limits_require_actual_numeric_original_ancestor_bounds() {
        let good: Vec<_> = GALLERY_LIMITS.iter().map(|(_, x)| (*x).to_owned()).collect();
        valid_limits(&good,Profile::Gallery).unwrap();
        for (index, value) in [(0, "max 100000"), (0, "200001 100000"), (0, "1 0"),
            (1, "max"), (1, "2147483649"), (2, "1"), (3, "65")] {
            let mut changed = good.clone(); changed[index] = value.into();
            assert!(valid_limits(&changed,Profile::Gallery).is_err(), "{index}: {value}");
        }
    }

    #[test]
    fn missing_or_nonzero_oom_counters_are_not_resource_evidence() {
        no_oom("low 0\nhigh 0\nmax 12\noom 0\noom_kill 0\noom_group_kill 0\n").unwrap();
        for raw in ["oom 0\noom_kill 0\n", "oom 1\noom_kill 0\noom_group_kill 0\n",
            "oom 0\noom 0\noom_kill 0\noom_group_kill 0\n"] {
            assert!(no_oom(raw).is_err());
        }
    }

    #[test]
    fn calendar_reminder_preserves_half_cpu_and_exact_512_mib() {
        let good:Vec<_>=Profile::CalendarReminder.limits().iter().map(|(_,v)|(*v).to_owned()).collect();
        valid_limits(&good,Profile::CalendarReminder).unwrap();
        assert!(valid_limits(&good,Profile::Gallery).is_err());
        for (index,value) in [(0,"50001 100000"),(0,"max 100000"),(1,"2147483648"),(2,"1"),(3,"65")] {
            let mut changed=good.clone();changed[index]=value.into();
            assert!(valid_limits(&changed,Profile::CalendarReminder).is_err());
        }
    }
}
