//! Local kernel resource fence for an already authenticated running App.
//! The fixed cgroup is the original production hard budget. No path, PID,
//! expected counter, or resource limit is accepted from an external caller.
use super::*;
use crate::engine_custody::EngineProcess;
use std::ffi::CStr;
use std::os::fd::{AsFd, FromRawFd};

const BUDGET: &str = "/sys/fs/cgroup/system.slice/droidloom-production.service/cell-u1000";
const PAYLOAD: &str = "/system.slice/droidloom-production.service/cell-u1000/payload/";
const CGROUP2: libc::c_long = 0x6367_7270;
const MAX_CONTROL: usize = 4096;

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub(super) struct ResourceSample {
    budget: MainNodeIdentity,
    memory_max: u64,
    memory_high: u64,
    swap_max: u64,
    cpu_max: String,
    pids_max: u64,
    cpus: String,
    cpus_effective: String,
    mems: String,
    mems_effective: String,
    memory_current: u64,
    swap_current: u64,
    pids_current: u64,
    memory_events: BTreeMap<String, u64>,
    pids_events: BTreeMap<String, u64>,
    cpu_stat: BTreeMap<String, u64>,
}
fn number(raw: &str) -> Result<u64, String> {
    let value = raw
        .parse::<u64>()
        .map_err(|_| "noncanonical kernel resource integer")?;
    need(
        value.to_string() == raw,
        "noncanonical kernel resource integer",
    )?;
    Ok(value)
}
fn counters(raw: &str, required: &[&str]) -> Result<BTreeMap<String, u64>, String> {
    need(
        !raw.is_empty() && raw.len() <= MAX_CONTROL,
        "kernel resource counters absent or oversized",
    )?;
    let mut rows = BTreeMap::new();
    for line in raw.lines() {
        let (key, value) = line
            .split_once(' ')
            .ok_or("kernel resource counter separator missing")?;
        need(
            !key.is_empty()
                && key.len() <= 64
                && key.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
                && rows.insert(key.to_string(), number(value)?).is_none(),
            "kernel resource counter repeats or has a noncanonical name",
        )?;
    }
    need(
        rows.len() <= 32 && required.iter().all(|key| rows.contains_key(*key)),
        "complete required kernel resource counters missing",
    )?;
    Ok(rows)
}
fn require_limits(row: &ResourceSample) -> Result<(), String> {
    need(
        row.memory_max == 8 * 1024 * 1024 * 1024
            && row.memory_high == 6 * 1024 * 1024 * 1024
            && row.swap_max == 0
            && row.swap_current == 0
            && row.cpu_max == "600000 100000"
            && row.pids_max == 32768
            && row.cpus == "2-23"
            && row.cpus_effective == "2-23"
            && !row.mems.is_empty()
            && row.mems == row.mems_effective
            && row.memory_current <= row.memory_max
            && row.pids_current <= row.pids_max,
        "original production resource limits, placement or current usage changed",
    )
}
pub(super) fn same_window(before: &ResourceSample, after: &ResourceSample) -> Result<(), String> {
    require_limits(before)?;
    require_limits(after)?;
    need(
        before.budget == after.budget && before.mems == after.mems,
        "original production cgroup inode or memory placement changed",
    )?;
    need(
        before.memory_events.keys().eq(after.memory_events.keys())
            && before.pids_events.keys().eq(after.pids_events.keys())
            && before.cpu_stat.keys().eq(after.cpu_stat.keys()),
        "kernel resource counter set changed during the reviewed window",
    )?;
    for (name, value) in &before.memory_events {
        let after = after.memory_events[name];
        // Reclaim and high-limit throttling are retained facts. No OOM,
        // hard-limit hit, kill, socket throttle, or unknown counter is forgiven.
        if name == "low" || name == "high" {
            need(after >= *value, "kernel resource counter went backwards")?;
        } else {
            need(
                after == *value,
                "production hard memory resource event occurred",
            )?;
        }
    }
    need(
        before.pids_events == after.pids_events,
        "production PID resource event occurred",
    )?;
    need(
        before
            .cpu_stat
            .iter()
            .all(|(name, value)| after.cpu_stat[name] >= *value),
        "production CPU accounting reset or went backwards",
    )
}
fn read_bounded(file: &File) -> Result<String, String> {
    let mut data = Vec::new();
    let mut offset = 0;
    loop {
        let mut buffer = [0_u8; 1024];
        let count = file
            .read_at(&mut buffer, offset)
            .map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        data.extend_from_slice(&buffer[..count]);
        need(
            data.len() <= MAX_CONTROL,
            "kernel control exceeded the fixed full-read bound",
        )?;
        offset += count as u64;
    }
    let raw = String::from_utf8(data).map_err(|_| "kernel control is not UTF-8")?;
    need(
        raw.ends_with('\n') && !raw.contains('\0') && !raw.contains('\r'),
        "kernel control has an incomplete or malformed record",
    )?;
    Ok(raw.trim_end_matches('\n').to_string())
}
fn opened(parent: &File, name: &CStr, flags: i32) -> Result<File, String> {
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().to_string());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
struct ControlFile {
    name: &'static CStr,
    file: File,
    identity: MainNodeIdentity,
    owner_mode: [u64; 4],
}
impl ControlFile {
    fn capture(parent: &File, name: &'static CStr) -> Result<Self, String> {
        let file = opened(parent, name, libc::O_RDONLY)?;
        let md = file.metadata().map_err(|e| e.to_string())?;
        need(
            md.is_file() && md.uid() == 0 && md.gid() == 0 && md.nlink() == 1,
            "resource control is not a normal root-owned cgroup file",
        )?;
        let identity = MainNodeIdentity::of(&md);
        let owner_mode = [
            u64::from(md.mode()),
            u64::from(md.uid()),
            u64::from(md.gid()),
            md.nlink(),
        ];
        Ok(Self {
            name,
            file,
            identity,
            owner_mode,
        })
    }
    fn read(&self, parent: &File) -> Result<String, String> {
        let named = opened(parent, self.name, libc::O_RDONLY)?;
        let owner = |file: &File| -> Result<[u64; 4], String> {
            let md = file.metadata().map_err(|e| e.to_string())?;
            Ok([
                u64::from(md.mode()),
                u64::from(md.uid()),
                u64::from(md.gid()),
                md.nlink(),
            ])
        };
        need(
            node(&named).map_err(|e| e.to_string())? == self.identity
                && node(&self.file).map_err(|e| e.to_string())? == self.identity
                && owner(&named)? == self.owner_mode
                && owner(&self.file)? == self.owner_mode,
            "held kernel resource control was replaced or changed owner/mode",
        )?;
        read_bounded(&self.file)
    }
}
pub(super) struct ResourceFence {
    app: BoundProcess,
    expected: EngineProcess,
    directory: File,
    identity: MainNodeIdentity,
    parents: Vec<Parent>,
    controls: Vec<ControlFile>,
}
impl ResourceFence {
    pub(super) fn capture(process: &EngineProcess) -> Result<Self, String> {
        let line = process.cgroup.strip_suffix('\n').unwrap_or(&process.cgroup);
        let relative = line
            .strip_prefix("0::")
            .ok_or("actual App cgroup is not unified")?;
        need(
            relative.starts_with(PAYLOAD)
                && !relative.contains("//")
                && relative.split('/').all(|p| p != "." && p != "..")
                && !relative.contains('\n'),
            "actual App does not belong to the fixed original production payload",
        )?;
        let app = BoundProcess::capture(process.host_pid).map_err(|e| e.to_string())?;
        let fd = File::from(
            app.pidfd
                .as_fd()
                .try_clone_to_owned()
                .map_err(|e| e.to_string())?,
        );
        need(
            app.identity.pid == process.host_pid
                && app.identity.start_ticks == process.start_ticks
                && node(&app.directory).map_err(|e| e.to_string())? == process.proc
                && node(&fd).map_err(|e| e.to_string())? == process.pidfd,
            "local App PIDFD or birth differs from the actual Engine owner",
        )?;
        let parents =
            protected_parents(&Path::new(BUDGET).join("memory.max")).map_err(|e| e.to_string())?;
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(BUDGET)
            .map_err(|e| e.to_string())?;
        let identity = node(&directory).map_err(|e| e.to_string())?;
        let mut st: libc::statfs = unsafe { std::mem::zeroed() };
        need(
            unsafe { libc::fstatfs(directory.as_raw_fd(), &mut st) } == 0 && st.f_type == CGROUP2,
            "resource fence is not the original cgroup2 filesystem",
        )?;
        let mut controls = Vec::new();
        for name in [
            c"memory.max",
            c"memory.high",
            c"memory.swap.max",
            c"cpu.max",
            c"pids.max",
            c"cpuset.cpus",
            c"cpuset.cpus.effective",
            c"cpuset.mems",
            c"cpuset.mems.effective",
            c"memory.current",
            c"memory.swap.current",
            c"pids.current",
            c"memory.events",
            c"pids.events",
            c"cpu.stat",
            c"cgroup.events",
        ] {
            controls.push(ControlFile::capture(&directory, name)?);
        }
        let fence = Self {
            app,
            expected: process.clone(),
            directory,
            identity,
            parents,
            controls,
        };
        fence.live()?;
        Ok(fence)
    }
    pub(super) fn live(&self) -> Result<(), String> {
        self.app.validate().map_err(|e| e.to_string())?;
        need(
            node(&self.app.directory).map_err(|e| e.to_string())? == self.expected.proc,
            "original App proc inode changed",
        )?;
        let cgroup = read_bounded(&self.app.open("cgroup", false).map_err(|e| e.to_string())?)?;
        need(
            cgroup == self.expected.cgroup.trim_end_matches('\n'),
            "original App moved outside its observed cgroup",
        )?;
        Ok(())
    }
    pub(super) fn sample(&self, require_live: bool) -> Result<ResourceSample, String> {
        if require_live {
            self.live()?;
        }
        verify_parents(&self.parents).map_err(|e| e.to_string())?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(BUDGET)
            .map_err(|e| e.to_string())?;
        need(
            node(&named).map_err(|e| e.to_string())? == self.identity
                && node(&self.directory).map_err(|e| e.to_string())? == self.identity,
            "original production budget inode changed",
        )?;
        let mut values = BTreeMap::new();
        for control in &self.controls {
            let key = control
                .name
                .to_str()
                .map_err(|_| "fixed resource name is invalid")?;
            values.insert(key, control.read(&self.directory)?);
        }
        let events = counters(&values["cgroup.events"], &["populated", "frozen"])?;
        need(
            events.len() == 2 && events["populated"] == 1 && events["frozen"] == 0,
            "original production budget became empty or frozen",
        )?;
        let row = ResourceSample {
            budget: self.identity.clone(),
            memory_max: number(&values["memory.max"])?,
            memory_high: number(&values["memory.high"])?,
            swap_max: number(&values["memory.swap.max"])?,
            cpu_max: values["cpu.max"].clone(),
            pids_max: number(&values["pids.max"])?,
            cpus: values["cpuset.cpus"].clone(),
            cpus_effective: values["cpuset.cpus.effective"].clone(),
            mems: values["cpuset.mems"].clone(),
            mems_effective: values["cpuset.mems.effective"].clone(),
            memory_current: number(&values["memory.current"])?,
            swap_current: number(&values["memory.swap.current"])?,
            pids_current: number(&values["pids.current"])?,
            memory_events: counters(
                &values["memory.events"],
                &["low", "high", "max", "oom", "oom_kill", "oom_group_kill"],
            )?,
            pids_events: counters(&values["pids.events"], &["max"])?,
            cpu_stat: counters(
                &values["cpu.stat"],
                &["usage_usec", "user_usec", "system_usec"],
            )?,
        };
        require_limits(&row)?;
        if require_live {
            self.live()?;
        }
        Ok(row)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn sample() -> ResourceSample {
        ResourceSample {
            budget: MainNodeIdentity {
                device: 4,
                inode: 7,
            },
            memory_max: 8 * 1024 * 1024 * 1024,
            memory_high: 6 * 1024 * 1024 * 1024,
            swap_max: 0,
            cpu_max: "600000 100000".into(),
            pids_max: 32768,
            cpus: "2-23".into(),
            cpus_effective: "2-23".into(),
            mems: "0".into(),
            mems_effective: "0".into(),
            memory_current: 1024,
            swap_current: 0,
            pids_current: 12,
            memory_events: counters(
                "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0",
                &["max"],
            )
            .unwrap(),
            pids_events: counters("max 0", &["max"]).unwrap(),
            cpu_stat: counters("usage_usec 1\nuser_usec 1\nsystem_usec 0", &["usage_usec"])
                .unwrap(),
        }
    }
    #[test]
    fn common_stability_resource_fence_rejects_limits_events_inode_and_counter_reset() {
        let before = sample();
        same_window(&before, &before).unwrap();
        for case in 0..8 {
            let mut after = before.clone();
            match case {
                0 => after.memory_max += 1,
                1 => after
                    .memory_events
                    .insert("oom_kill".into(), 1)
                    .map(|_| ())
                    .unwrap(),
                2 => after
                    .pids_events
                    .insert("max".into(), 1)
                    .map(|_| ())
                    .unwrap(),
                3 => after.budget.inode += 1,
                4 => after.swap_current = 1,
                5 => after
                    .cpu_stat
                    .insert("usage_usec".into(), 0)
                    .map(|_| ())
                    .unwrap(),
                6 => {
                    after.memory_events.remove("max");
                }
                _ => after.cpus_effective = "2-24".into(),
            }
            assert!(same_window(&before, &after).is_err(), "{case}");
        }
        let mut after = before.clone();
        after.memory_events.insert("high".into(), 1);
        after.cpu_stat.insert("usage_usec".into(), 2);
        same_window(&before, &after).unwrap();
    }
    #[test]
    fn common_stability_resource_parser_retains_complete_counter_sets() {
        for raw in [
            "oom 1\noom 2",
            "max 01",
            "max -1",
            "max 1 extra",
            "max 1\nbad-key 0",
            "",
        ] {
            assert!(counters(raw, &["max"]).is_err(), "{raw}");
        }
        assert!(counters("high 0", &["high", "oom"]).is_err());
        let before = sample();
        let mut after = before.clone();
        after.memory_events.insert("unknown".into(), 0);
        assert!(same_window(&before, &after).is_err());
    }
}
