//! Finite VINTF observation in the original Ready framework namespace.
//! No public argument selects a process, namespace, file, command or property.
//! Real factory execution, stopped-exec admission and retirement are unchanged.
use super::*;
use crate::control::runtime_vintf as wire;
use crate::production_selection::early_generation::{
    EarlyApplicationAuthority, EarlyFrameworkObservation,
};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::time::{Duration, Instant};

const WORKFLOW: Duration = Duration::from_secs(60);
// An exec-stop metadata observer can first spend one retirement interval,
// followed by factory retirement, leaf-empty waiting and the client's final
// retirement retry. Reserve all four unchanged three-second phases inside
// this workflow, rather than extending its limit for every command.
const RETIRE_RESERVE: Duration = Duration::from_secs(12);
const MAX_QUERIES: usize = 64;
const STAT_FORMAT: &str = "%n|%f|%u|%g|%h|%d|%i|%s|%y|%z";

/// Constructed by the admitted transport before acquiring its original owner.
/// No wire field, shared cell or other request can reset or extend this budget.
#[derive(Clone, Copy)]
pub(crate) struct RuntimeVintfBudget {
    started: Instant,
    deadline: Instant,
    work_deadline: Instant,
}
impl RuntimeVintfBudget {
    pub(crate) fn start() -> Self {
        let started = Instant::now();
        Self {
            started,
            deadline: started + WORKFLOW,
            work_deadline: started + (WORKFLOW - RETIRE_RESERVE),
        }
    }
    pub(super) fn operation_deadline(&self) -> Instant { self.deadline }
    pub(crate) fn work_deadline(&self) -> Instant {
        self.work_deadline
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "read", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum VintfRead {
    Property { index: u8 },
    KernelRelease,
    Machine,
    Stat { paths: Vec<String> },
    Canonical { paths: Vec<String> },
    OdmLink { path: String },
    List { roots: Vec<String> },
    Bytes { paths: Vec<String> },
}
fn paths_valid(paths: &[String]) -> bool {
    !paths.is_empty()
        && paths.len() <= wire::MAX_NODES
        && paths.iter().all(|p| wire::metadata_path(p))
        && paths.iter().map(String::len).sum::<usize>() <= wire::MAX_PATH_BYTES
        && paths.iter().collect::<BTreeSet<_>>().len() == paths.len()
}
impl VintfRead {
    pub(super) fn validate(&self) -> Result<()> {
        require(
            match self {
                Self::Property { index } => usize::from(*index) < wire::PROPERTIES.len(),
                Self::KernelRelease | Self::Machine => true,
                Self::OdmLink { path } => wire::ODM_LINKS.contains(&path.as_str()),
                Self::Stat { paths } | Self::Canonical { paths } => paths_valid(paths),
                Self::List { roots } => {
                    paths_valid(roots)
                        && roots.len() <= wire::MAX_APEX + 5
                        && roots.iter().all(|p| p.ends_with("/etc/vintf"))
                }
                Self::Bytes { paths } => {
                    paths_valid(paths)
                        && paths.len() <= wire::MAX_FILES
                        && paths.iter().all(|p| p.ends_with(".xml"))
                }
            },
            "VINTF read is outside the finite public metadata contract",
        )
    }
    pub(super) fn binary(&self) -> &'static CStr {
        if matches!(self, Self::Property { .. }) {
            c"toolbox"
        } else {
            c"toybox"
        }
    }
    pub(super) const fn output_limit(&self) -> usize {
        match self {
            Self::Property { .. } => 512,
            Self::KernelRelease | Self::Machine | Self::OdmLink { .. } => 1024,
            Self::Stat { .. } => 256 * 1024,
            Self::Canonical { .. } | Self::List { .. } => 64 * 1024,
            Self::Bytes { .. } => wire::MAX_BYTES,
        }
    }
    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        self.validate()?;
        let mut args: Vec<String> = match self {
            // The exact original toolbox dispatches its getprop applet by
            // argv[0]. Toybox's actual 213-entry dispatcher has no getprop.
            Self::Property { index } => vec![
                "/system/bin/getprop".into(),
                wire::PROPERTIES[usize::from(*index)].0.into(),
            ],
            Self::KernelRelease => vec!["/system/bin/toybox".into(), "uname".into(), "-r".into()],
            Self::Machine => vec!["/system/bin/toybox".into(), "uname".into(), "-m".into()],
            Self::Stat { .. } => vec![
                "/system/bin/toybox".into(),
                "stat".into(),
                "-c".into(),
                STAT_FORMAT.into(),
                "--".into(),
            ],
            Self::Canonical { .. } => vec![
                "/system/bin/toybox".into(),
                "realpath".into(),
                "-e".into(),
                "--".into(),
            ],
            Self::OdmLink { path } => vec![
                "/system/bin/toybox".into(),
                "readlink".into(),
                "--".into(),
                path.clone(),
            ],
            Self::List { .. } => vec!["/system/bin/toybox".into(), "find".into()],
            Self::Bytes { .. } => vec!["/system/bin/toybox".into(), "cat".into(), "--".into()],
        };
        match self {
            Self::Stat { paths } | Self::Canonical { paths } | Self::Bytes { paths } => {
                args.extend(paths.clone())
            }
            Self::List { roots } => {
                args.extend(roots.clone());
                args.push("-print0".into());
            }
            _ => {}
        }
        args.into_iter()
            .map(|a| CString::new(a).map_err(|_| reject("NUL in finite metadata command")))
            .collect()
    }
}
fn namespace_error(error: crate::production_namespace::NamespaceError) -> ApplicationError {
    match error {
        crate::production_namespace::NamespaceError::RetirementUnproven => {
            ApplicationError::RetirementUnproven
        }
        error => observation_authority_error(error),
    }
}
fn pure_expiry(error: &ApplicationError, expected: Instant) -> bool {
    crate::production_host_admission::observation_expiry(error) == Some(expected)
        && Instant::now() >= expected
}
/// Preserve the first substantive failure. A later clock observation cannot
/// erase it; a real failure to retire always takes precedence in either branch.
pub(super) fn finish_vintf<T>(
    result: Result<T>,
    postcheck: impl FnOnce() -> Result<()>,
    work_deadline: Instant,
    deadline: Instant,
) -> Result<T> {
    let after = postcheck();
    if matches!(&result, Err(ApplicationError::RetirementUnproven))
        || matches!(&after, Err(ApplicationError::RetirementUnproven))
    {
        return Err(ApplicationError::RetirementUnproven);
    }
    if result
        .as_ref()
        .is_err_and(|error| !pure_expiry(error, work_deadline))
    {
        return result;
    }
    after?;
    if Instant::now() >= deadline {
        return Err(
            crate::production_host_admission::observation_expired_error(work_deadline).into(),
        );
    }
    result
}
struct Capture {
    output: Vec<u8>,
    error: Vec<u8>,
    code: i32,
}
struct Session<'a, 'owner> {
    owner: &'a EarlyApplicationAuthority<'owner>,
    framework: EarlyFrameworkObservation,
    epoch: RuntimeEpoch,
    deadline: Instant,
    work_deadline: Instant,
    receipts: Vec<serde_json::Value>,
}
impl Session<'_, '_> {
    fn check(&self) -> Result<()> {
        self.owner
            .check_request_deadline()
            .map_err(namespace_error)?;
        crate::production_host_admission::check_observation_before(self.work_deadline)?;
        self.owner
            .progress_inherited_native(self.work_deadline)
            .map_err(namespace_error)?;
        self.owner.ready().map_err(namespace_error)?;
        require(
            self.owner.epoch(&self.framework).map_err(namespace_error)? == self.epoch,
            "VINTF original framework epoch changed",
        )
    }
    fn read(&mut self, value: VintfRead) -> Result<Capture> {
        self.check()?;
        require(
            self.receipts.len() < MAX_QUERIES,
            "VINTF finite query count",
        )?;
        let query_deadline = self.work_deadline;
        crate::production_host_admission::check_observation_before(query_deadline)?;
        let result = factory_query::run(
            self.owner,
            &ApplicationOperation::Vintf {
                value: value.clone(),
            },
            query_deadline,
        );
        let result = finish_vintf(result, || self.check(), self.work_deadline, self.deadline)?;
        let code = result
            .output
            .status
            .code()
            .ok_or_else(|| reject("VINTF query terminated by signal"))?;
        require(
            result.receipt.retired_with_exit(code)
                && result.receipt.query_waitid_code == libc::CLD_EXITED
                && result.receipt.output_bytes == result.output.stdout.len()
                && result.receipt.output_sha256
                    == format!("{:x}", Sha256::digest(&result.output.stdout))
                && result.stderr_bytes == result.output.stderr.len()
                && result.stderr_sha256 == format!("{:x}", Sha256::digest(&result.output.stderr)),
            "VINTF actual output/exit/retirement mismatch",
        )?;
        if !matches!(value, VintfRead::Stat { .. }) {
            require(
                code == 0 && result.output.stderr.is_empty(),
                "VINTF original query failed or emitted stderr",
            )?;
        }
        require(
            result.output.stdout.len() <= value.output_limit(),
            "VINTF query output bound",
        )?;
        let small_stdout = if matches!(value, VintfRead::Bytes { .. }) {
            None
        } else {
            // NUL-delimited find remains valid UTF-8 JSON; no shell interprets it.
            Some(
                String::from_utf8(result.output.stdout.clone())
                    .map_err(|_| reject("VINTF text query encoding"))?,
            )
        };
        let error = String::from_utf8(result.output.stderr.clone())
            .map_err(|_| reject("VINTF query stderr encoding"))?;
        self.receipts.push(serde_json::json!({
            "operation":value,"stdout":small_stdout,"stderr":error,
            "stderr_bytes":result.stderr_bytes,"stderr_sha256":result.stderr_sha256,
            "actual_exit":code,"retirement":result.receipt,
        }));
        self.check()?;
        Ok(Capture {
            output: result.output.stdout,
            error: result.output.stderr,
            code,
        })
    }
    fn text(&mut self, value: VintfRead) -> Result<String> {
        let raw = self.read(value)?.output;
        let value = std::str::from_utf8(&raw).map_err(|_| reject("VINTF scalar encoding"))?;
        let line = value
            .strip_suffix('\n')
            .ok_or_else(|| reject("VINTF scalar lacks final newline"))?;
        require(
            !line.is_empty() && line.len() <= 512 && !line.bytes().any(|b| b.is_ascii_control()),
            "VINTF scalar framing",
        )?;
        Ok(line.into())
    }
    fn properties(&mut self) -> Result<Vec<wire::RuntimeProperty>> {
        (0..wire::PROPERTIES.len())
            .map(|i| {
                let value = self.read(VintfRead::Property { index: i as u8 })?;
                wire::property(i, &value.output).map_err(external)
            })
            .collect()
    }
    fn stats(
        &mut self,
        paths: &[String],
    ) -> Result<(BTreeMap<String, wire::PublicStat>, Vec<wire::MissingPath>)> {
        let value = self.read(VintfRead::Stat {
            paths: paths.to_vec(),
        })?;
        wire::stat_output(paths, &value.output, &value.error, value.code).map_err(external)
    }
    fn canonical(
        &mut self,
        paths: &[String],
        apex: &[wire::ActiveApex],
    ) -> Result<BTreeMap<String, String>> {
        if paths.is_empty() {
            return Ok(BTreeMap::new());
        }
        let raw = self
            .read(VintfRead::Canonical {
                paths: paths.to_vec(),
            })?
            .output;
        let text =
            std::str::from_utf8(&raw).map_err(|_| reject("VINTF canonical path encoding"))?;
        require(
            text.ends_with('\n'),
            "truncated VINTF canonical path output",
        )?;
        let actual: Vec<_> = text.lines().collect();
        require(
            actual.len() == paths.len(),
            "VINTF canonical path cardinality",
        )?;
        let mut result = BTreeMap::new();
        for (original, resolved) in paths.iter().zip(actual) {
            require(
                wire::canonical_for(original, resolved),
                "VINTF path resolved outside its fixed public tree",
            )?;
            if let Some(rest) = resolved.strip_prefix("/apex/") {
                let name = rest
                    .split('/')
                    .next()
                    .ok_or_else(|| reject("APEX canonical component absent"))?;
                if let Some((module, version)) = name.split_once('@') {
                    require(
                        apex.iter().any(|a| {
                            a.module_name == module
                                && a.attributes
                                    .get("versionCode")
                                    .is_some_and(|v| v == version)
                        }),
                        "APEX canonical version differs from active inventory",
                    )?;
                }
            }
            result.insert(original.clone(), resolved.into());
        }
        Ok(result)
    }
    fn roster(&mut self, roots: &[String]) -> Result<Vec<String>> {
        require(!roots.is_empty(), "VINTF has no actual metadata directory")?;
        let raw = self
            .read(VintfRead::List {
                roots: roots.to_vec(),
            })?
            .output;
        wire::directory_roster(&raw, roots).map_err(external)
    }
    fn odm_links(
        &mut self,
        stats: &BTreeMap<String, wire::PublicStat>,
    ) -> Result<Vec<wire::PublicLink>> {
        let mut result = Vec::new();
        for path in wire::ODM_LINKS {
            if let Some(stat) = stats.get(path) {
                if stat.mode & libc::S_IFMT == libc::S_IFLNK {
                    let target = self.text(VintfRead::OdmLink { path: path.into() })?;
                    require(
                        target.len() <= 256 && target.is_ascii(),
                        "ODM link target bound",
                    )?;
                    result.push(wire::PublicLink {
                        stat: stat.clone(),
                        target,
                    });
                }
            }
        }
        Ok(result)
    }
}
fn document(path: &str, stat: &wire::PublicStat, raw: &[u8]) -> Result<wire::VintfDocument> {
    require(
        stat.path == path
            && stat.mode & libc::S_IFMT == libc::S_IFREG
            && stat.uid == 0
            && stat.mode & 0o022 == 0
            && stat.bytes == raw.len() as u64
            && raw.len() <= wire::MAX_FILE_BYTES,
        "VINTF public document metadata mismatch",
    )?;
    let text = std::str::from_utf8(raw).map_err(|_| reject("VINTF XML encoding"))?;
    require(!text.contains('\0'), "VINTF XML contains NUL")?;
    Ok(wire::VintfDocument {
        path: path.into(),
        bytes: raw.len(),
        sha256: format!("{:x}", Sha256::digest(raw)),
        stat: stat.clone(),
        utf8: text.into(),
    })
}

pub(crate) fn observe_runtime_vintf(
    owner: &EarlyApplicationAuthority<'_>,
    expected: &RuntimeEpoch,
    budget: &RuntimeVintfBudget,
) -> Result<wire::RuntimeVintfObservation> {
    let RuntimeVintfBudget {
        started,
        deadline,
        work_deadline,
    } = *budget;
    owner.check_request_deadline().map_err(namespace_error)?;
    require(
        owner.request_deadline() == Some(work_deadline),
        "VINTF requires its own admitted immutable absolute budget",
    )?;
    owner.ready().map_err(namespace_error)?;
    let framework = owner.observe_framework().map_err(namespace_error)?;
    let epoch = owner.epoch(&framework).map_err(namespace_error)?;
    // These numeric observations never open/select a proc entry or namespace.
    require(
        &epoch == expected,
        "VINTF expected epoch differs from the actual Ready owner",
    )?;
    let binding = owner
        .runtime_vintf_binding(&framework, work_deadline)
        .map_err(namespace_error)?;
    let mut session = Session {
        owner,
        framework,
        epoch: epoch.clone(),
        deadline,
        work_deadline,
        receipts: Vec::new(),
    };
    let result = (|| -> Result<wire::RuntimeVintfObservation> {
        let properties = session.properties()?;
        let kernel_release = session.text(VintfRead::KernelRelease)?;
        let machine = session.text(VintfRead::Machine)?;
        let inventory = session
            .read(VintfRead::Bytes {
                paths: vec![wire::APEX_INVENTORY.into()],
            })?
            .output;
        require(
            inventory.len() <= wire::MAX_FILE_BYTES,
            "actual APEX inventory byte bound",
        )?;
        let apex = wire::active_apex(&inventory).map_err(external)?;
        let mut requested_roots: Vec<String> =
            wire::VINTF_ROOTS.iter().map(|s| (*s).into()).collect();
        requested_roots.extend(
            apex.iter()
                .map(|a| format!("/apex/{}/etc/vintf", a.module_name)),
        );
        let mut legacy: Vec<String> = wire::LEGACY.iter().map(|s| (*s).into()).collect();
        if !properties[1].value.is_empty() {
            legacy.push(format!("/odm/etc/manifest_{}.xml", properties[1].value));
        }
        let initial: Vec<_> = requested_roots
            .iter()
            .chain(&legacy)
            .cloned()
            .chain(wire::ODM_LINKS.iter().map(|s| (*s).into()))
            .chain(std::iter::once(wire::APEX_INVENTORY.into()))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let (initial_stats, missing) = session.stats(&initial)?;
        require(
            initial_stats.contains_key(wire::APEX_INVENTORY),
            "actual APEX inventory disappeared",
        )?;
        let odm_links = session.odm_links(&initial_stats)?;
        let existing: Vec<_> = requested_roots
            .iter()
            .chain(&legacy)
            .filter(|p| initial_stats.contains_key(*p))
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let mapping = session.canonical(&existing, &apex)?;
        let roots: Vec<_> = requested_roots
            .iter()
            .filter_map(|p| mapping.get(p))
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let roster = session.roster(&roots)?;
        let all_paths: Vec<_> = roster
            .iter()
            .cloned()
            .chain(legacy.iter().filter_map(|p| mapping.get(p)).cloned())
            .chain(std::iter::once(wire::APEX_INVENTORY.into()))
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        require(all_paths.len() <= wire::MAX_NODES, "VINTF full node bound")?;
        let (stats, unresolved) = session.stats(&all_paths)?;
        require(
            unresolved.is_empty(),
            "metadata disappeared after directory enumeration",
        )?;
        let mut files = Vec::new();
        let mut directories = Vec::new();
        let mut total = 0usize;
        for (path, node) in &stats {
            require(
                node.uid == 0 && node.mode & 0o022 == 0,
                "VINTF metadata has a writable public owner",
            )?;
            match node.mode & libc::S_IFMT {
                libc::S_IFDIR => {
                    directories.push(node.clone());
                }
                libc::S_IFREG => {
                    require(
                        path.ends_with(".xml") && node.bytes <= wire::MAX_FILE_BYTES as u64,
                        "VINTF directory contains a non-XML or oversized file",
                    )?;
                    total = total
                        .checked_add(node.bytes as usize)
                        .ok_or_else(|| reject("VINTF total byte overflow"))?;
                    files.push(path.clone());
                }
                _ => return Err(reject("VINTF tree contains a symlink or special inode")),
            }
        }
        require(
            roots.iter().all(|p| {
                stats
                    .get(p)
                    .is_some_and(|s| s.mode & libc::S_IFMT == libc::S_IFDIR)
            }) && files.len() <= wire::MAX_FILES
                && total <= wire::MAX_BYTES,
            "VINTF root/file/total bound",
        )?;
        let bytes = session
            .read(VintfRead::Bytes {
                paths: files.clone(),
            })?
            .output;
        require(
            bytes.len() == total,
            "concatenated metadata length differs from complete stat roster",
        )?;
        let mut offset = 0;
        let mut docs = Vec::new();
        let mut inventory_doc = None;
        for path in &files {
            let stat = &stats[path];
            let next = offset + stat.bytes as usize;
            let doc = document(path, stat, &bytes[offset..next])?;
            if path == wire::APEX_INVENTORY {
                require(
                    bytes[offset..next] == inventory,
                    "actual APEX inventory changed during collection",
                )?;
                inventory_doc = Some(doc);
            } else {
                docs.push(doc);
            }
            offset = next;
        }
        // A second complete byte pass, full directory enumeration and all
        // non-atime identities must agree in the same held framework epoch.
        require(
            session.read(VintfRead::Bytes { paths: files })?.output == bytes,
            "VINTF complete body bookend changed",
        )?;
        require(
            session.stats(&all_paths)? == (stats, Vec::new()),
            "VINTF stat bookend changed",
        )?;
        require(
            session.roster(&roots)? == roster,
            "VINTF full directory roster changed",
        )?;
        let (after_initial, after_missing) = session.stats(&initial)?;
        require(
            after_initial == initial_stats && after_missing == missing,
            "VINTF presence/absence bookend changed",
        )?;
        require(
            session.odm_links(&after_initial)? == odm_links,
            "ODM link bookend changed",
        )?;
        require(
            session.canonical(&existing, &apex)? == mapping,
            "VINTF canonical mapping changed",
        )?;
        require(
            session.properties()? == properties,
            "VINTF property bookend changed",
        )?;
        require(
            session.text(VintfRead::KernelRelease)? == kernel_release
                && session.text(VintfRead::Machine)? == machine,
            "VINTF UTS bookend changed",
        )?;
        session.check()?;
        let after = owner
            .runtime_vintf_binding(&session.framework, work_deadline)
            .map_err(namespace_error)?;
        require(
            after == binding,
            "VINTF original image/mount/namespace binding changed",
        )?;
        let after_epoch = owner.epoch(&session.framework).map_err(namespace_error)?;
        require(
            after_epoch == epoch,
            "VINTF framework changed at final bookend",
        )?;
        let observed = wire::RuntimeVintfObservation {
            schema: "droidloom.runtime-vintf-observation.v1".into(),
            expected_epoch: expected.clone(),
            epoch_before: epoch.clone(),
            epoch_after: after_epoch,
            binding_before: binding.clone(),
            binding_after: after,
            kernel_release,
            machine,
            properties,
            apex_inventory: inventory_doc
                .ok_or_else(|| reject("actual APEX inventory document absent"))?,
            active_apex: apex,
            root_mappings: mapping,
            missing,
            odm_links,
            directories,
            documents: docs,
            query_receipts: std::mem::take(&mut session.receipts),
            elapsed_millis: started
                .elapsed()
                .as_millis()
                .try_into()
                .map_err(|_| reject("VINTF timing overflow"))?,
            compatibility_checked: false,
            application_acceptance: false,
        };
        require(
            serde_json::to_vec(&observed).map_err(external)?.len() <= 3 * 1024 * 1024,
            "VINTF observation exceeds reserved control response budget",
        )?;
        Ok(observed)
    })();
    finish_vintf(result, || session.check(), work_deadline, deadline)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vintf_finish_keeps_causal_failures_over_later_expiry() {
        let end = Instant::now() - Duration::from_millis(1);
        let outer = end + RETIRE_RESERVE;
        let expired = || {
            ApplicationError::Io(crate::production_host_admission::observation_expired_error(
                end,
            ))
        };
        let result: Result<()> = finish_vintf(
            Err(reject("original owner changed")),
            || Err(expired()),
            end,
            outer,
        );
        assert!(
            matches!(result, Err(ApplicationError::Rejected(ref why)) if why == "original owner changed")
        );
        let result: Result<()> = finish_vintf(
            Err(expired()),
            || Err(reject("custody changed at bookend")),
            end,
            outer,
        );
        assert!(
            matches!(result, Err(ApplicationError::Rejected(ref why)) if why == "custody changed at bookend")
        );
        for (first, last) in [
            (ApplicationError::RetirementUnproven, expired()),
            (expired(), ApplicationError::RetirementUnproven),
        ] {
            let result: Result<()> = finish_vintf(Err(first), || Err(last), end, outer);
            assert!(matches!(result, Err(ApplicationError::RetirementUnproven)));
        }
        let result = finish_vintf(Ok(7u8), || Err(expired()), end, outer);
        assert!(result.is_err_and(|e| pure_expiry(&e, end)));
        let fake: Result<()> = finish_vintf(
            Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "original request observation deadline reached",
            )
            .into()),
            || Err(expired()),
            end,
            outer,
        );
        assert!(fake.is_err_and(|e| !pure_expiry(&e, end)));
    }
    #[test]
    fn vintf_private_operation_has_no_shell_or_process_selector() {
        for raw in [
            r#"{"read":"property","index":0,"pid":12}"#,
            r#"{"read":"bytes","paths":["/data/user/0/private"]}"#,
            r#"{"read":"command","argv":["sh","-c","true"]}"#,
        ] {
            match serde_json::from_str::<VintfRead>(raw) {
                Ok(r) => assert!(r.validate().is_err()),
                Err(_) => {}
            }
        }
        let property = VintfRead::Property { index: 0 };
        assert_eq!(property.binary(), c"toolbox");
        assert_eq!(
            property.arguments().unwrap(),
            vec![
                CString::new("/system/bin/getprop").unwrap(),
                CString::new(wire::PROPERTIES[0].0).unwrap()
            ]
        );
        let op = ApplicationOperation::Vintf { value: property };
        assert_eq!(op.domain(), OperationDomain::Query);
        assert_eq!(op.descriptor_count(), 15);
        assert!(!op.uses_app_process());
    }
    #[test]
    fn vintf_input_limits_are_fixed_before_factory_execution() {
        assert!(VintfRead::Property { index: 4 }.validate().is_err());
        assert!(VintfRead::Bytes { paths: vec![] }.validate().is_err());
        assert!(
            VintfRead::Bytes {
                paths: vec!["/system/etc/vintf/manifest.xml".into(); 2]
            }
            .validate()
            .is_err()
        );
        assert!(
            VintfRead::OdmLink {
                path: "/apex/com.android.art".into()
            }
            .validate()
            .is_err()
        );
        assert!(
            VintfRead::List {
                roots: vec!["/system/etc".into()]
            }
            .validate()
            .is_err()
        );
        assert!(
            VintfRead::Bytes {
                paths: vec!["/system/etc/vintf".into()]
            }
            .validate()
            .is_err()
        );
    }
}
