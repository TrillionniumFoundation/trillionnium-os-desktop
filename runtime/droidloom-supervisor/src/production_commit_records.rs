//! Exact fixed records written by the live production commit actor.
//! Reopening these creates historical comparisons, never Complete.
use super::*;
use std::collections::{BTreeMap, BTreeSet};
const COMMIT_NAMES: [&str; 7] = [
    "PLAN.json",
    "SUMMARY.json",
    "MAIN.json",
    "STDERR.log",
    "COMMIT.json",
    "TRIAL.json",
    "REQUEST.json",
];
const ACTIVE: &str = "ACTIVE.json";
const DIRECTORY_LABEL: &[u8] = b"u:object_r:p4_linux_production_record_dir_t:s0";
const RECORD_LABEL: &[u8] = b"u:object_r:p4_linux_production_record_t:s0";
const ACTIVE_LABEL: &[u8] = b"u:object_r:p4_linux_production_activation_t:s0";
fn label(name: &str) -> &'static [u8] {
    if name == ACTIVE {
        ACTIVE_LABEL
    } else {
        RECORD_LABEL
    }
}
fn bound(name: &str) -> io::Result<u64> {
    Ok(match name {
        "PLAN.json" => 64 * 1024 * 1024,
        "SUMMARY.json" => SUMMARY_LIMIT as u64,
        "MAIN.json" => BINDING_LIMIT as u64,
        "STDERR.log" => 0,
        "COMMIT.json" | "TRIAL.json" | "REQUEST.json" | ACTIVE => 1024 * 1024,
        _ => return Err(error("unreviewed production record member")),
    })
}
fn names(root: &Path) -> io::Result<BTreeSet<String>> {
    let mut out = BTreeSet::new();
    for e in fs::read_dir(root)? {
        let e = e?;
        let name = e
            .file_name()
            .into_string()
            .map_err(|_| error("record name is not UTF-8"))?;
        bound(&name)?;
        if !e.file_type()?.is_file() || !out.insert(name) {
            return Err(error("production record member type differs"));
        }
    }
    Ok(out)
}
pub(super) struct Records {
    root: PathBuf,
    directory: File,
    identity: [u64; 5],
    held: BTreeMap<String, pio::Input>,
}
impl Records {
    fn directory(s: &Sources) -> io::Result<Self> {
        s.guard()?;
        let root = s.config.directory()?;
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&root)?;
        let id = f9(&directory)?;
        if id[2] != 0o040700
            || id[3..5] != [0, 0]
            || crate::native_hardware_label::label(&directory)? != DIRECTORY_LABEL
        {
            return Err(error(
                "production records do not have their fixed root/MAC directory",
            ));
        }
        Ok(Self {
            root,
            directory,
            identity: id[..5].try_into().unwrap(),
            held: BTreeMap::new(),
        })
    }
    pub(super) fn new_commit(s: &Sources) -> io::Result<Self> {
        if s.actor != Actor::Commit {
            return Err(error("only actual live commit can create history"));
        }
        let value = Self::directory(s)?;
        if !names(&value.root)?.is_empty() {
            return Err(error(
                "production commit history already exists; no replay permitted",
            ));
        }
        value.guard()?;
        Ok(value)
    }
    pub(super) fn reopen(s: &Sources) -> io::Result<Self> {
        if s.actor != Actor::Verify {
            return Err(error(
                "only a fresh normal verifier reopens historical records",
            ));
        }
        let mut value = Self::directory(s)?;
        let entries = names(&value.root)?;
        let required = COMMIT_NAMES
            .into_iter()
            .map(String::from)
            .collect::<BTreeSet<_>>();
        if entries != required
            && entries
                != required
                    .union(&BTreeSet::from([ACTIVE.into()]))
                    .cloned()
                    .collect()
        {
            return Err(error("complete production history roster differs"));
        }
        for name in entries {
            let path = value.root.join(&name);
            let meta = fs::symlink_metadata(&path)?;
            if meta.len() > bound(&name)? {
                return Err(error("production historical record exceeds source bound"));
            }
            let f = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&path)?;
            let pin = c::BytesPin {
                bytes: meta.len(),
                sha256: pio::whole(&f, meta.len())?,
            };
            let held = pio::Input::open(&path, &pin, 0o600, Some(label(&name)))?;
            value.held.insert(name, held);
        }
        value.guard()?;
        Ok(value)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.root)?;
        if f9(&named)?[..5] != self.identity
            || f9(&self.directory)?[..5] != self.identity
            || crate::native_hardware_label::label(&self.directory)? != DIRECTORY_LABEL
            || names(&self.root)? != self.held.keys().cloned().collect()
        {
            return Err(error("production record namespace changed"));
        }
        for v in self.held.values() {
            v.guard()?;
        }
        Ok(())
    }
    pub(super) fn write(&mut self, name: &str, bytes: &[u8]) -> io::Result<c::BytesPin> {
        self.guard()?;
        if bytes.len() as u64 > bound(name)? || self.held.contains_key(name) {
            return Err(error("production record is oversized or already published"));
        }
        let path = self.root.join(name);
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        let id = f9(&file)?;
        if id[2] != 0o100600
            || id[3..7] != [0, 0, 1, 0]
            || crate::native_hardware_label::label(&file)? != label(name)
        {
            return Err(error(
                "production output did not receive its fixed named MAC transition",
            ));
        }
        file.write_all(bytes)?;
        file.sync_all()?;
        self.directory.sync_all()?;
        let pin = c::BytesPin {
            bytes: bytes.len() as u64,
            sha256: sha(bytes),
        };
        let input = pio::Input::open(&path, &pin, 0o600, Some(label(name)))?;
        if f9(&file)? != input.identity {
            return Err(error("new production record was replaced before retention"));
        }
        self.held.insert(name.into(), input);
        self.guard()?;
        if unsafe { libc::syncfs(self.directory.as_raw_fd()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(pin)
    }
    pub(super) fn write_json(&mut self, name: &str, value: &Value) -> io::Result<c::BytesPin> {
        let mut body = serde_json::to_vec(value)?;
        body.push(b'\n');
        self.write(name, &body)
    }
    pub(super) fn pins(&self) -> Value {
        let mut map = serde_json::Map::new();
        for (name, file) in &self.held {
            map.insert(name.clone(), json!(file.pin));
        }
        Value::Object(map)
    }
    pub(super) fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        self.guard()?;
        self.held
            .get(name)
            .ok_or_else(|| error("production record missing"))?
            .bytes(bound(name)?)
    }
    pub(super) fn pin(&self, name: &str) -> io::Result<&c::BytesPin> {
        Ok(&self
            .held
            .get(name)
            .ok_or_else(|| error("production record missing"))?
            .pin)
    }
    pub(super) fn has_active(&self) -> bool {
        self.held.contains_key(ACTIVE)
    }
}
// Comparison data only. Neither this value nor a saved request intent can
// grant a reboot or create a Complete. The actual private parent acknowledges
// the held intent before the one fixed request can be invoked.
fn request_comparison(
    config: &c::Configuration,
    configuration: &c::BytesPin,
    boot: &str,
    pid: u32,
    commit: &c::BytesPin,
    trial: &c::BytesPin,
    end_ns: u64,
) -> Value {
    json!({"schema":c::REBOOT_INTENT_SCHEMA,"candidate_id":config.candidate_id,
        "configuration":configuration,"boot_id":boot,"commit_pid":pid,
        "commit":commit,"trial":trial,"original_end_ns":end_ns,
        "normal_program":{"path":c::SYSTEMCTL,"whole_bytes":config.systemctl},
        "arguments":c::REBOOT_ARGUMENTS,"private_parent_acknowledgement_required":true,
        "request_execution_observed":false,"normal_shutdown_observed":false})
}
pub(super) fn request_intent(
    s: &Sources,
    commit: &c::BytesPin,
    trial: &c::BytesPin,
    end_ns: u64,
) -> io::Result<Value> {
    s.guard()?;
    let now = monotonic_ns()?;
    if s.actor != Actor::Commit || end_ns <= now || end_ns - now > c::COMMIT_SECONDS * 1_000_000_000
    {
        return Err(error(
            "normal reboot intent has no original live commit window",
        ));
    }
    commit.validate(128 * 1024 * 1024)?;
    trial.validate(128 * 1024 * 1024)?;
    Ok(request_comparison(
        &s.config,
        &s.config_input.pin,
        &s.boot_id,
        std::process::id(),
        commit,
        trial,
        end_ns,
    ))
}
pub(super) struct History {
    pub boot_id: String,
    pub commit_pid: u32,
    pub digest: String,
    pub main: RuntimeMainCustody,
}
impl History {
    pub(super) fn observe(s: &Sources, records: &Records) -> io::Result<Self> {
        s.guard()?;
        records.guard()?;
        let raw = records.read("COMMIT.json")?;
        let v: Value = serde_json::from_slice(&raw)?;
        let boot = v["boot_id"]
            .as_str()
            .ok_or_else(|| error("complete history boot missing"))?
            .to_owned();
        let pid = v["commit_pid"]
            .as_u64()
            .and_then(|v| u32::try_from(v).ok())
            .filter(|v| *v > 1)
            .ok_or_else(|| error("complete history process missing"))?;
        if v["schema"] != "droidloom.live-production-complete-history.v1"
            || v["candidate_id"] != s.config.candidate_id
            || v["configuration"] != json!(s.config_input.pin)
            || !crate::native_working_contract::uuid(&boot)
            || boot == s.boot_id
        {
            return Err(error(
                "historical Complete differs from this fresh normal source",
            ));
        }
        let end = v["original_end_ns"]
            .as_u64()
            .filter(|v| *v > 0)
            .ok_or_else(|| error("historical commit omitted its original live end"))?;
        let request: Value = serde_json::from_slice(&records.read("REQUEST.json")?)?;
        if request
            != request_comparison(
                &s.config,
                &s.config_input.pin,
                &boot,
                pid,
                records.pin("COMMIT.json")?,
                records.pin("TRIAL.json")?,
                end,
            )
        {
            return Err(error(
                "historical request intent differs from the actual held commit and trial",
            ));
        }
        let docs = v["documents"]
            .as_object()
            .ok_or_else(|| error("whole Complete documents absent"))?;
        let required = ["PLAN.json", "SUMMARY.json", "MAIN.json", "STDERR.log"];
        if docs.len() != required.len() {
            return Err(error("historical document roster differs"));
        }
        for name in required {
            if docs.get(name) != Some(&json!(records.pin(name)?)) {
                return Err(error("historical Complete full document differs"));
            }
        }
        if !records.read("STDERR.log")?.is_empty() {
            return Err(error("historical actual child had stderr"));
        }
        let main: RuntimeMainCustody = serde_json::from_slice(&records.read("MAIN.json")?)?;
        main.validate(&main.epoch)
            .map_err(|e| error(&e.to_string()))?;
        if main.epoch.boot_id != boot || main.persistent_data.fresh_diagnostic_origin.is_some() {
            return Err(error(
                "historical Main belongs to a different or diagnostic boot",
            ));
        }
        let summary: Value = serde_json::from_slice(&records.read("SUMMARY.json")?)?;
        if summary["schema"] != "droidloom.physical-application-run.v1"
            || summary["selected_applications"] != 41
            || summary["accepted_applications"] != 41
            || summary["required_gates"] != 401
            || summary["accepted_gates"] != 401
            || summary["observed_cases"] != CASE_COUNT
            || summary["runtime_qualified"] != true
            || summary["production_ready"] != true
            || summary["automatic_retry"] != false
            || !summary["retained_failure"].is_null()
        {
            return Err(error("historical complete normal suite differs"));
        }
        Ok(Self {
            boot_id: boot,
            commit_pid: pid,
            digest: sha(&raw),
            main,
        })
    }
    pub(super) fn same_selected_pair(&self, current: &RuntimeMainCustody) -> io::Result<()> {
        if self.main.epoch.boot_id == current.epoch.boot_id
            || self.main.owner.host_uid != current.owner.host_uid
            || self.main.owner.base_cohort_sha256 != current.owner.base_cohort_sha256
            || self.main.owner.runtime_manifest_sha256 != current.owner.runtime_manifest_sha256
            || self.main.owner.selection_binding_sha256 != current.owner.selection_binding_sha256
            || self.main.normal_host_release != current.normal_host_release
            || self.main.persistent_data.original_copy_origin
                != current.persistent_data.original_copy_origin
            || self
                .main
                .persistent_data
                .backings
                .iter()
                .map(|v| v.backing.stable7())
                .collect::<Vec<_>>()
                != current
                    .persistent_data
                    .backings
                    .iter()
                    .map(|v| v.backing.stable7())
                    .collect::<Vec<_>>()
        {
            return Err(error(
                "fresh normal Main is not the historically qualified same pair and normal release",
            ));
        }
        Ok(())
    }
}
