//! Fixed normal diagnostic client. Inputs are one source-owned official APK
//! and the current actual EMPTY Main; there is no caller path or package API.
use super::*;
use crate::{empty_meituan_contract as fixed, native_empty_meituan_install as wire};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fs::File, os::unix::fs::FileExt};

fn bad(e: impl std::fmt::Display) -> ControlError {
    ControlError::Invalid(e.to_string())
}
fn need(ok: bool, why: &str) -> Result<(), ControlError> {
    if ok { Ok(()) } else { Err(bad(why)) }
}
fn actual_node(fd: &File) -> Result<(u64, u64), ControlError> {
    live(fd).map_err(bad)?;
    let m = fd.metadata().map_err(bad)?;
    Ok((m.dev(), m.ino()))
}
// This comparison only permits another read. It never grants a Main token or
// retries a mutation. Other Starting failures (including an expired query),
// transport errors, changed peers and quarantine are terminal.
fn boot_completion_pending(response: &ControlResponse) -> bool {
    !response.ok
        && response.state == CellState::Starting
        && response.host_pid.is_some_and(|v| v > 1)
        && response.diagnostics.is_none()
        && response.runtime_vintf.is_none()
        && response.message
            == crate::production_namespace::NamespaceError::Rejected(
                "early application operation requires current Android boot completion",
            )
            .to_string()
}

fn wait_for_empty_main(
    inspector: &mut NativeApplicationInspector,
    end: Instant,
) -> Result<(MainCustodyObservation, u32), ControlError> {
    // Reserve the existing birth (10), whole-APK fill/check (60), PM (110),
    // ordinary launch (250) and final Main/retirement (70) windows. Every stage
    // still consumes the one entry deadline; this is not a renewed lease.
    let startup_end = end
        .checked_sub(Duration::from_secs(500))
        .ok_or_else(|| bad("EMPTY startup has no reserved installation/launch tail"))?;
    let request = ControlRequest::ObserveCurrentRuntimeMain {};
    let mut observations = 0;
    loop {
        need(
            startup_end.saturating_duration_since(Instant::now())
                >= progress::response_timeout(&request),
            "EMPTY startup exhausted its original window before a complete Main read",
        )?;
        let response = inspector.request_fixed_until(&request, Some(startup_end))?;
        observations += 1;
        if response.ok {
            let facts = current_main_response(response, &inspector.boot_id)?;
            wire::require_main(&facts).map_err(bad)?;
            let peer = inspector.observation()?;
            let pidfd = inspector.pidfd.try_clone().map_err(bad)?;
            live(&pidfd).map_err(bad)?;
            inspector.revalidate()?;
            check_deadline(Some(startup_end))?;
            return Ok((
                MainCustodyObservation {
                    facts,
                    peer,
                    pidfd,
                    observed_at: Instant::now(),
                },
                observations,
            ));
        }
        need(
            boot_completion_pending(&response),
            &format!("normal Main observation failed: {}", response.message),
        )?;
        need(
            observations < 220,
            "EMPTY startup exceeded its fixed read count",
        )?;
        std::thread::sleep(Duration::from_secs(1));
    }
}
fn actor() -> Result<(), ControlError> {
    let args = std::env::args_os().collect::<Vec<_>>();
    need(
        args == [
            std::ffi::OsString::from(fixed::PROGRAM),
            std::ffi::OsString::from(fixed::ARGUMENT),
        ],
        "independent EMPTY diagnostic has only its exact installed no-argument invocation",
    )?;
    crate::control::package::EmptyMeituanPeer::require_installed_current().map_err(bad)?;
    for line in ["Uid:", "Gid:"] {
        let raw = std::fs::read_to_string("/proc/self/status").map_err(bad)?;
        let values = raw
            .lines()
            .filter_map(|v| v.strip_prefix(line))
            .collect::<Vec<_>>();
        need(
            values.len() == 1 && values[0].split_whitespace().collect::<Vec<_>>() == ["0"; 4],
            "independent EMPTY diagnostic requires all actual root credentials",
        )?;
    }
    need(
        crate::native_hardware_label::current(101).map_err(bad)?
            == b"u:system_r:p4_linux_working_privateprep_t:s0"
            && crate::native_hardware_label::current(104).map_err(bad)?
                == b"droidloom-working-privateprep (enforce)",
        "independent EMPTY diagnostic requires both exact enforcing normal preparation roles",
    )?;
    need(
        std::fs::read_to_string("/proc/self/cgroup").map_err(bad)?
            == format!("0::/system.slice/{}\n", fixed::UNIT),
        "independent EMPTY diagnostic must run in its own exact normal unit",
    )
}
fn stable_directory(node: &Node) -> [u64; 5] {
    [
        node.device,
        node.inode,
        u64::from(node.mode),
        u64::from(node.uid),
        u64::from(node.gid),
    ]
}
struct OfficialMaterial {
    parents: Vec<(File, Node)>,
    file: File,
    node: Node,
}
impl OfficialMaterial {
    fn capture(end: Instant) -> Result<Self, ControlError> {
        check_deadline(Some(end))?;
        let root = open_at(
            libc::AT_FDCWD,
            c"/",
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )
        .map_err(bad)?;
        let root_node = Node::of(&root).map_err(bad)?;
        let mut parents = vec![(root, root_node)];
        for name in [
            c"var",
            c"lib",
            c"droidloom-qualification",
            c"empty-meituan-diagnostic",
        ] {
            let file = open_at(
                parents.last().unwrap().0.as_raw_fd(),
                name,
                libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
            )
            .map_err(bad)?;
            let node = Node::of(&file).map_err(bad)?;
            need(
                node.mode & libc::S_IFMT == libc::S_IFDIR
                    && node.uid == 0
                    && node.gid == 0
                    && node.mode & 0o022 == 0,
                "fixed official material ancestry is not root controlled",
            )?;
            parents.push((file, node));
        }
        need(
            parents[0].1.uid == 0
                && parents[0].1.gid == 0
                && parents[0].1.mode & 0o022 == 0
                && parents[3].1.mode == libc::S_IFDIR | 0o700
                && parents[4].1.mode == libc::S_IFDIR | 0o700,
            "fixed EMPTY material root and private directories differ",
        )?;
        let file = open_at(
            parents.last().unwrap().0.as_raw_fd(),
            c"official.apk",
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_NOATIME | libc::O_NONBLOCK,
        )
        .map_err(bad)?;
        let node = Node::of(&file).map_err(bad)?;
        need(
            node.mode == libc::S_IFREG | 0o400
                && node.uid == 0
                && node.gid == 0
                && node.links == 1
                && node.bytes == fixed::APK_BYTES,
            "fixed official APK is not its whole root-private single-link source",
        )?;
        let value = Self {
            parents,
            file,
            node,
        };
        value.guard(end)?;
        Ok(value)
    }
    fn guard(&self, end: Instant) -> Result<(), ControlError> {
        check_deadline(Some(end))?;
        let mut named = open_at(
            libc::AT_FDCWD,
            c"/",
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )
        .map_err(bad)?;
        for (index, (held, prior)) in self.parents.iter().enumerate() {
            if index > 0 {
                named = open_at(
                    named.as_raw_fd(),
                    [
                        c"var",
                        c"lib",
                        c"droidloom-qualification",
                        c"empty-meituan-diagnostic",
                    ][index - 1],
                    libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW,
                )
                .map_err(bad)?;
            }
            need(
                stable_directory(&Node::of(held).map_err(bad)?) == stable_directory(prior)
                    && stable_directory(&Node::of(&named).map_err(bad)?) == stable_directory(prior),
                "fixed official APK named or held ancestor changed",
            )?;
        }
        let path = open_at(
            named.as_raw_fd(),
            c"official.apk",
            libc::O_PATH | libc::O_NOFOLLOW,
        )
        .map_err(bad)?;
        need(
            Node::of(&path).map_err(bad)? == self.node
                && Node::of(&self.file).map_err(bad)? == self.node,
            "fixed official APK named or held inode changed",
        )?;
        let mut hash = Sha256::new();
        let mut at = 0;
        let mut bytes = vec![0u8; 1024 * 1024];
        while at < fixed::APK_BYTES {
            check_deadline(Some(end))?;
            let count = bytes.len().min((fixed::APK_BYTES - at) as usize);
            self.file
                .read_exact_at(&mut bytes[..count], at)
                .map_err(bad)?;
            if at == 0 {
                need(
                    bytes[..4] == *b"PK\x03\x04",
                    "official APK ZIP header differs",
                )?;
            }
            hash.update(&bytes[..count]);
            at += count as u64;
        }
        need(
            self.file.read_at(&mut bytes[..1], at).map_err(bad)? == 0
                && format!("{:x}", hash.finalize()) == fixed::APK_SHA256
                && Node::of(&self.file).map_err(bad)? == self.node,
            "fixed original official APK whole bytes changed",
        )?;
        check_deadline(Some(end))
    }
}
struct Installed {
    reply: wire::Reply,
    peer_pidfd: File,
    peer: NativeInspectionPeer,
    birth: crate::production_application::working_payload_birth::Retirement,
}
impl Installed {
    fn guard(
        &self,
        inspector: &NativeApplicationInspector,
        main: &MainCustodyObservation,
        end: Instant,
    ) -> Result<(), ControlError> {
        self.birth.guard().map_err(bad)?;
        inspector.require_empty_main(main, end)?;
        need(
            actual_node(&self.peer_pidfd)? == actual_node(&main.pidfd)?
                && self.peer == main.peer
                && self.reply.main() == main.facts(),
            "EMPTY installation does not retain the same actual normal peer and Main",
        )
    }
}
impl NativeApplicationInspector {
    fn require_empty_main(
        &self,
        main: &MainCustodyObservation,
        end: Instant,
    ) -> Result<(), ControlError> {
        check_deadline(Some(end))?;
        crate::production_application::working_payload_birth::require_retired().map_err(bad)?;
        self.revalidate()?;
        wire::require_main(main.facts()).map_err(bad)?;
        need(
            actual_node(&self.pidfd)? == actual_node(&main.pidfd)?
                && main.peer == self.observation()?,
            "EMPTY Main belongs to another actual normal control owner",
        )
    }
    fn install_empty(
        &mut self,
        main: &MainCustodyObservation,
        material: &OfficialMaterial,
        end: Instant,
    ) -> Result<Installed, ControlError> {
        self.require_empty_main(main, end)?;
        material.guard(end)?;
        let (empty, birth) =
            crate::production_application::working_payload_birth::create(end).map_err(bad)?;
        let (payload, lengths) =
            super::super::apk_payload::prepare_born_held_set_until(&[&material.file], empty, end)?;
        birth.require_payload(&payload).map_err(bad)?;
        need(
            lengths == [fixed::APK_BYTES],
            "EMPTY original payload length differs",
        )?;
        wire::official()
            .require_payload(&payload, end)
            .map_err(bad)?;
        material.guard(end)?;
        self.require_empty_main(main, end)?;
        let request = wire::Request::from_owned(main, end).map_err(bad)?;
        let stream = progress::connect(Path::new(DEFAULT_CONTROL_SOCKET)).map_err(bad)?;
        let peer = peer_credentials_checked(&stream)?;
        let pidfd = peer_pidfd(&stream).map_err(bad)?;
        need(
            peer.pid as u32 == self.peer_pid && actual_node(&pidfd)? == actual_node(&self.pidfd)?,
            "EMPTY installation socket changed its actual owner",
        )?;
        let response = progress::request_on_with_file_until(
            stream,
            &ControlRequest::InstallEmptyMeituan {
                request: request.clone(),
            },
            Some(&payload),
            end,
        );
        let after = (|| {
            actual_node(&pidfd)?;
            material.guard(end)?;
            self.require_empty_main(main, end)
        })();
        let response = match (response, after) {
            (Ok(v), Ok(())) => v,
            (Err(e), Ok(())) | (Ok(_), Err(e)) => return Err(e),
            (Err(e), Err(post)) => {
                return Err(bad(format!("{e}; EMPTY custody postcheck: {post}")));
            }
        };
        need(
            response.ok
                && response.state == CellState::Running
                && response.host_pid == Some(main.facts().epoch.cell_host_pid),
            &format!(
                "normal EMPTY installation failed without retry/data deletion: {}",
                response.message
            ),
        )?;
        let raw = response
            .diagnostics
            .as_deref()
            .ok_or_else(|| bad("complete EMPTY actual receipt absent"))?;
        need(
            raw.len() <= wire::MAX_REPLY_BYTES,
            "EMPTY complete receipt exceeds bound",
        )?;
        let reply: wire::Reply = serde_json::from_str(raw)?;
        reply.validate(&request).map_err(bad)?;
        birth.require_payload(&payload).map_err(bad)?;
        let result = Installed {
            reply,
            peer_pidfd: pidfd,
            peer: self.observation()?,
            birth,
        };
        result.guard(self, main, end)?;
        Ok(result)
    }
}

/// Fixed normal unit entry; saved comparisons can neither resume it nor mint
/// an installation capability. Full progress, including an actual failure,
/// goes to the normal unit journal for collection by the ordinary producer.
pub fn run_empty_meituan_diagnostic() -> Value {
    let end = Instant::now() + wire::LIMIT;
    let mut report = json!({"schema":fixed::SCHEMA,"phase":"actor","ok":false,
        "production_ready":false,"original_data_migration":false,"business_acceptance":false});
    let attempted = (|| -> Result<(), ControlError> {
        actor()?;
        check_deadline(Some(end))?;
        let material = OfficialMaterial::capture(end)?;
        report["phase"] = "waiting_for_normal_main".into();
        let mut inspector =
            NativeApplicationInspector::acquire_until(Path::new(DEFAULT_CONTROL_SOCKET), end)?;
        let (main, observations) = wait_for_empty_main(&mut inspector, end)?;
        report["readonly_main_observations"] = observations.into();
        inspector.require_empty_main(&main, end)?;
        report["main"] = serde_json::to_value(main.facts())?;
        report["phase"] = "normal_create_only_install".into();
        let installed = inspector.install_empty(&main, &material, end)?;
        report["installation"] = installed.reply.comparison().map_err(bad)?;
        report["payload_birth"] = installed.birth.comparison().map_err(bad)?;
        report["phase"] = "actual_installed_bytes".into();
        let app = inspector.inspect_observed_until(fixed::PACKAGE, 0, end)?;
        inspector.require_observations_local(&main, &app, end)?;
        let facts = app.facts();
        need(
            facts.package == fixed::PACKAGE
                && facts.user == 0
                && facts.version_code == fixed::VERSION_CODE
                && facts.uid == installed.reply.installed_uid().map_err(bad)?
                && facts.epoch == main.facts().epoch
                && facts.apks.len() == 1
                && facts.apks[0].name == "base.apk"
                && facts.apks[0].bytes == fixed::APK_BYTES
                && facts.apks[0].sha256 == fixed::APK_SHA256,
            "actual PM whole installed APK differs from the complete fixed official package",
        )?;
        report["installed_identity"] = serde_json::to_value(facts)?;
        installed.guard(&inspector, &main, end)?;
        material.guard(end)?;
        inspector.revalidate_main_until(&main, end)?;
        report["phase"] = "normal_launch".into();
        let request = ControlRequest::Launch {
            spec: DEFAULT_CELL_SPEC.into(),
            package: fixed::PACKAGE.into(),
            component: None,
            resolution: None,
            user: 0,
        };
        need(
            end.saturating_duration_since(Instant::now())
                >= progress::response_timeout(&request) + Duration::from_secs(70),
            "original EMPTY deadline cannot fit one complete normal launch and Main postcheck",
        )?;
        let response = inspector.request_fixed_until(&request, Some(end))?;
        report["launch"] = serde_json::to_value(&response)?;
        inspector.revalidate_main_until(&main, end)?;
        installed.guard(&inspector, &main, end)?;
        material.guard(end)?;
        need(
            response.ok
                && response.state == CellState::Running
                && response.host_pid == Some(main.facts().epoch.cell_host_pid)
                && response.launch.is_some()
                && response.inspection.as_ref() == Some(facts),
            "normal official application launch did not retain the exact observed package and actual task binding",
        )?;
        report["phase"] = "normal_launch_observed_business_pending".into();
        report["ok"] = true.into();
        Ok(())
    })();
    if let Err(error) = attempted {
        report["error"] = error.to_string().into();
    }
    report
}

/// Same-image hidden child entry. The original birth ABI deliberately keeps
/// its fixed argv literal; the actual installed ctl inode is checked separately.
pub fn run_empty_meituan_payload_birth_worker() -> Result<(), ControlError> {
    crate::control::package::EmptyMeituanPeer::require_installed_current().map_err(bad)?;
    crate::production_application::run_working_original_payload_birth().map_err(bad)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_meituan_wait_rejects_other_starting_failures_and_quarantine() {
        let message = crate::production_namespace::NamespaceError::Rejected(
            "early application operation requires current Android boot completion",
        )
        .to_string();
        let mut value: ControlResponse = serde_json::from_value(
            json!({"ok":false,"state":"starting","message":message,"host_pid":42}),
        )
        .unwrap();
        assert!(boot_completion_pending(&value));
        value.message = "Permission denied".into();
        assert!(!boot_completion_pending(&value));
        value.message = message;
        value.state = CellState::Quarantined;
        assert!(!boot_completion_pending(&value));
        value.state = CellState::Starting;
        value.ok = true;
        assert!(!boot_completion_pending(&value));
        value.ok = false;
        value.diagnostics = Some("{}".into());
        assert!(!boot_completion_pending(&value));
    }
}
