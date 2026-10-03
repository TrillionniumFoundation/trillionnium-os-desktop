//! Long-lived root-selected service policy and original current Owner identity.
//! This proof grants neither a request/effect permit nor a health observation.
//! Per-request Control/Agent deadlines remain separate and unchanged.
use super::*;
use crate::PeerRequestCustody;

pub const DEFAULT_APPROVED_SERVICE_POLICY_PATH: &str = "/etc/hepta/approved-mechanisms.v2.conf";
pub const MAX_APPROVED_SERVICE_POLICY_BYTES: usize = 8192;
const SERVICE_SCHEMA: &str = "trillionnium.approved-mechanisms.v2";

mod creator_context;
use creator_context::CreatorContext;

fn parse_service(bytes: &[u8]) -> Result<[Entry; 3], ApprovedPolicyError> {
    let bad = || ApprovedPolicyError::InvalidConfiguration;
    if bytes.is_empty()
        || bytes.len() > MAX_APPROVED_SERVICE_POLICY_BYTES
        || !bytes.is_ascii()
        || !bytes.ends_with(b"\n")
    {
        return Err(bad());
    }
    let text = std::str::from_utf8(bytes).map_err(|_| bad())?;
    let mut fields = BTreeMap::new();
    for line in text.split_terminator('\n') {
        let (k, v) = line.split_once('=').ok_or_else(bad)?;
        if k.is_empty() || v.is_empty() || v.contains('=') || fields.insert(k, v).is_some() {
            return Err(bad());
        }
    }
    let mut expected = vec!["schema".to_owned()];
    for role in ["control", "agent", "owner"] {
        for key in ["uid", "gid", "unit", "cgroup", "elf_sha256", "principal_id"] {
            expected.push(format!("{role}.{key}"))
        }
    }
    if fields.len() != 19
        || expected.iter().any(|k| !fields.contains_key(k.as_str()))
        || fields["schema"] != SERVICE_SCHEMA
    {
        return Err(bad());
    }
    let mut values = Vec::new();
    for role in ["control", "agent", "owner"] {
        let field = |name: &str| fields[format!("{role}.{name}").as_str()];
        let number = |name: &str| -> Result<u32, ApprovedPolicyError> {
            let v = field(name);
            if v.is_empty()
                || !v.bytes().all(|b| b.is_ascii_digit())
                || (v.len() > 1 && v.starts_with('0'))
            {
                return Err(bad());
            }
            let n: u32 = v.parse().map_err(|_| bad())?;
            if n == u32::MAX {
                return Err(bad());
            }
            Ok(n)
        };
        let unit = field("unit");
        if unit.len() > 128
            || crate::validate_unit_name(unit).is_err()
            || !unit
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"@_.:-".contains(&b))
        {
            return Err(bad());
        }
        let cgroup = field("cgroup");
        if cgroup.len() > 512
            || !cgroup.starts_with('/')
            || cgroup.split('/').skip(1).any(|p| {
                p.is_empty()
                    || p == "."
                    || p == ".."
                    || p.len() > 128
                    || !p
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"@_.:-".contains(&b))
            })
            || cgroup.rsplit('/').next() != Some(unit)
        {
            return Err(bad());
        }
        let pin = field("elf_sha256");
        if pin.len() != 64
            || !pin
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err(bad());
        }
        let principal = field("principal_id");
        if principal.len() > 64
            || !principal
                .bytes()
                .next()
                .is_some_and(|b| b.is_ascii_alphanumeric())
            || !principal
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
        {
            return Err(bad());
        }
        values.push(Entry {
            uid: number("uid")?,
            gid: number("gid")?,
            unit: unit.into(),
            cgroup: cgroup.into(),
            pin: pin.into(),
            principal: principal.into(),
        });
    }
    for first in 0..3 {
        for second in first + 1..3 {
            if values[first].principal == values[second].principal {
                return Err(bad());
            }
        }
    }
    values.try_into().map_err(|_| bad())
}
struct ServiceState {
    creator: CreatorContext,
    namespace: [(u64, u64); 3],
    directories: Vec<Directory>,
    leaf: CString,
    file: File,
    identity: Identity,
    digest: [u8; 32],
    entries: [Entry; 3],
    retired: AtomicBool,
    owner_selected: AtomicBool,
}
impl ServiceState {
    fn creator_current(&self) -> Result<(), ApprovedPolicyError> {
        let checked = self.creator.verify();
        if checked.is_err() && self.creator.pid == std::process::id() {
            self.retired.store(true, Ordering::SeqCst);
        }
        checked
    }
    fn inspect(&self) -> Result<(), ApprovedPolicyError> {
        self.creator_current()?;
        if self.retired.load(Ordering::SeqCst) {
            return Err(ApprovedPolicyError::Changed);
        }
        let checked = (|| {
            if namespace()? != self.namespace
                || !self.directories[0]
                    .identity
                    .same_directory(&Identity::named(libc::AT_FDCWD, &self.directories[0].name)?)
            {
                return Err(ApprovedPolicyError::Changed);
            }
            for (i, dir) in self.directories.iter().enumerate() {
                if !dir
                    .identity
                    .same_directory(&Identity::file(dir.fd.as_raw_fd())?)
                {
                    return Err(ApprovedPolicyError::Changed);
                }
                if i > 0
                    && !dir.identity.same_directory(&Identity::named(
                        self.directories[i - 1].fd.as_raw_fd(),
                        &dir.name,
                    )?)
                {
                    return Err(ApprovedPolicyError::Changed);
                }
            }
            let parent = self
                .directories
                .last()
                .ok_or(ApprovedPolicyError::SourceRefused)?;
            if Identity::file(self.file.as_raw_fd())? != self.identity
                || Identity::named(parent.fd.as_raw_fd(), &self.leaf)? != self.identity
            {
                return Err(ApprovedPolicyError::Changed);
            }
            let data = read(&self.file)?;
            if <[u8; 32]>::from(Sha256::digest(&data)) != self.digest
                || Identity::file(self.file.as_raw_fd())? != self.identity
                || Identity::named(parent.fd.as_raw_fd(), &self.leaf)? != self.identity
                || namespace()? != self.namespace
            {
                return Err(ApprovedPolicyError::Changed);
            }
            for (i, dir) in self.directories.iter().enumerate() {
                if !dir
                    .identity
                    .same_directory(&Identity::file(dir.fd.as_raw_fd())?)
                    || i > 0
                        && !dir.identity.same_directory(&Identity::named(
                            self.directories[i - 1].fd.as_raw_fd(),
                            &dir.name,
                        )?)
                {
                    return Err(ApprovedPolicyError::Changed);
                }
            }
            if !self.directories[0]
                .identity
                .same_directory(&Identity::named(libc::AT_FDCWD, &self.directories[0].name)?)
            {
                return Err(ApprovedPolicyError::Changed);
            }
            self.creator_current()
        })();
        if self.creator.pid != std::process::id() {
            return Err(ApprovedPolicyError::ProcessChanged);
        }
        if checked.is_err() {
            self.retired.store(true, Ordering::SeqCst)
        }
        checked
    }
}
/// Root-owned nineteen-field policy retained in its original namespaces.
/// Its lifetime is policy continuity only; it is not request authority.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedServicePolicyDocument;
/// let forged = ApprovedServicePolicyDocument { state: () };
/// ```
pub struct ApprovedServicePolicyDocument {
    state: Arc<ServiceState>,
}
impl ApprovedServicePolicyDocument {
    pub fn open_default() -> Result<Self, ApprovedPolicyError> {
        Self::open_root_owned(Path::new(DEFAULT_APPROVED_SERVICE_POLICY_PATH))
    }
    pub fn open_root_owned(path: &Path) -> Result<Self, ApprovedPolicyError> {
        let creator = CreatorContext::capture()?;
        creator.verify()?;
        if !path.is_absolute()
            || path.as_os_str().as_bytes().len() > 1024
            || path.components().count() > 32
            || path.as_os_str().as_bytes().contains(&0)
        {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        let parts: Vec<_> = path.components().collect();
        if parts.len() < 2
            || parts
                .iter()
                .skip(1)
                .any(|c| !matches!(c, Component::Normal(_)))
        {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        // Component iteration normalizes '.', so reject raw aliases before walking.
        if path
            .as_os_str()
            .as_bytes()
            .split(|b| *b == b'/')
            .skip(1)
            .any(|p| p.is_empty() || p == b"." || p == b"..")
        {
            return Err(ApprovedPolicyError::InvalidConfiguration);
        }
        let ns = namespace()?;
        let name = CString::new("/").unwrap();
        let fd = open_at(libc::AT_FDCWD, &name, libc::O_PATH | libc::O_DIRECTORY)?;
        let identity = Identity::file(fd.as_raw_fd())?;
        if !identity.directory() {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        let mut dirs = vec![Directory { fd, name, identity }];
        for part in &parts[1..parts.len() - 1] {
            let name = CString::new(part.as_os_str().as_bytes())
                .map_err(|_| ApprovedPolicyError::InvalidConfiguration)?;
            let fd = open_at(
                dirs.last().unwrap().fd.as_raw_fd(),
                &name,
                libc::O_PATH | libc::O_DIRECTORY,
            )?;
            let identity = Identity::file(fd.as_raw_fd())?;
            if !identity.directory() {
                return Err(ApprovedPolicyError::SourceRefused);
            }
            dirs.push(Directory { fd, name, identity });
            creator.verify()?;
        }
        let leaf = CString::new(parts.last().unwrap().as_os_str().as_bytes())
            .map_err(|_| ApprovedPolicyError::InvalidConfiguration)?;
        let fd = open_at(
            dirs.last().unwrap().fd.as_raw_fd(),
            &leaf,
            libc::O_RDONLY | libc::O_NONBLOCK,
        )?;
        let identity = Identity::file(fd.as_raw_fd())?;
        if !identity.regular() {
            return Err(ApprovedPolicyError::SourceRefused);
        }
        let file = File::from(fd);
        let bytes = read(&file)?;
        let entries = parse_service(&bytes)?;
        let state = Arc::new(ServiceState {
            creator,
            namespace: ns,
            directories: dirs,
            leaf,
            file,
            identity,
            digest: Sha256::digest(&bytes).into(),
            entries,
            retired: AtomicBool::new(false),
            owner_selected: AtomicBool::new(false),
        });
        state.inspect()?;
        Ok(Self { state })
    }
    pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.state.inspect()
    }
    /// Select once, only the actual creating process, using a private socketpair,
    /// fixed default procfs attestation and the root-selected Owner entry.
    pub fn select_current_owner(&self) -> Result<ApprovedServiceOwnerBinding, ApprovedPolicyError> {
        self.state.creator_current()?;
        self.state.inspect()?;
        if self
            .state
            .owner_selected
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return Err(ApprovedPolicyError::PeerRefused);
        }
        let checked = (|| {
            let (socket, _other) =
                UnixStream::pair().map_err(|_| ApprovedPolicyError::PeerRefused)?;
            let peer =
                PeerIdentity::from_stream(&socket).map_err(|_| ApprovedPolicyError::PeerRefused)?;
            if peer.pid != Some(self.state.creator.pid) {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            let entry = &self.state.entries[2];
            let attested = ProcfsPeerAttestor::default()
                .attest(peer, &entry.runtime())
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            if attested.snapshot().executable_sha256 != entry.pin {
                return Err(ApprovedPolicyError::PeerRefused);
            }
            let original = attested
                .request_custody()
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            self.state.inspect()?;
            let binding = ApprovedServiceOwnerBinding {
                state: Arc::clone(&self.state),
                original,
            };
            binding.ensure_current()?;
            Ok(binding)
        })();
        if checked.is_err() {
            self.state.retired.store(true, Ordering::SeqCst);
        }
        checked
    }
}

/// Non-cloneable current Owner binding. Dropping it revokes every issued
/// verifier through the original pidfd custody. It grants no native authority.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedServiceOwnerBinding;
/// fn needs_clone<T: Clone>() {}
/// needs_clone::<ApprovedServiceOwnerBinding>();
/// ```
pub struct ApprovedServiceOwnerBinding {
    state: Arc<ServiceState>,
    original: PeerRequestCustody,
}
impl ApprovedServiceOwnerBinding {
    pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.state.creator_current()?;
        self.verifier().map(|_| ())
    }
    pub fn verifier(&self) -> Result<ApprovedServiceOwnerVerifier, ApprovedPolicyError> {
        self.state.creator_current()?;
        self.state.inspect()?;
        let verifier = ApprovedServiceOwnerVerifier {
            state: Arc::clone(&self.state),
            original: self.original.verifier(),
        };
        verifier.ensure_current()?;
        Ok(verifier)
    }
}

/// Read-only original Owner/source continuity. It cannot create a replacement
/// process, export approval fields or mint a request/effect/health permit.
///
/// ```compile_fail
/// use hepta_peer_attestation::ApprovedServiceOwnerVerifier;
/// let forged = ApprovedServiceOwnerVerifier { state: (), original: () };
/// ```
pub struct ApprovedServiceOwnerVerifier {
    state: Arc<ServiceState>,
    original: crate::PeerRequestVerifier,
}
impl ApprovedServiceOwnerVerifier {
    pub fn ensure_current(&self) -> Result<(), ApprovedPolicyError> {
        self.state.creator_current()?;
        let checked = (|| {
            self.state.inspect()?;
            self.original
                .verify_current()
                .map_err(|_| ApprovedPolicyError::PeerRefused)?;
            self.state.inspect()
        })();
        if checked.is_err() {
            self.state.retired.store(true, Ordering::SeqCst);
        }
        checked
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn golden() -> String {
        let legacy = std::str::from_utf8(include_bytes!(
            "../../../../contracts/fixtures/approved-mechanisms.v1.conf"
        ))
        .unwrap();
        let value = legacy.replace("trillionnium.approved-mechanisms.v1", SERVICE_SCHEMA);
        let mut fields = String::new();
        for line in legacy.lines().filter(|line| line.starts_with("control.")) {
            let line = line.replacen("control.", "owner.", 1);
            if line.starts_with("owner.principal_id=") {
                fields.push_str("owner.principal_id=fixture-owner\n");
            } else {
                fields.push_str(&line);
                fields.push('\n');
            }
        }
        value + &fields
    }
    #[test]
    fn third_owner_is_explicit_and_legacy_schema_is_refused() {
        let value = parse_service(golden().as_bytes()).unwrap();
        assert_eq!(value[2].principal, "fixture-owner");
        assert!(
            parse_service(include_bytes!(
                "../../../../contracts/fixtures/approved-mechanisms.v1.conf"
            ))
            .is_err()
        );
        assert!(
            parse_service(
                golden()
                    .replace(SERVICE_SCHEMA, "trillionnium.approved-mechanisms.v1")
                    .as_bytes()
            )
            .is_err()
        );
    }
    #[test]
    fn every_missing_duplicate_and_unknown_service_field_refuses() {
        let value = golden();
        assert_eq!(value.lines().count(), 19);
        for line in value.lines() {
            assert!(parse_service(value.replace(&format!("{line}\n"), "").as_bytes()).is_err());
            assert!(parse_service(format!("{value}{line}\n").as_bytes()).is_err());
        }
        assert!(parse_service(format!("{value}owner.action_permit=true\n").as_bytes()).is_err());
    }
    #[test]
    fn owner_numeric_and_role_collision_inputs_refuse() {
        let value = golden();
        for key in ["owner.uid", "owner.gid"] {
            let original = value
                .lines()
                .find(|line| line.starts_with(&format!("{key}=")))
                .unwrap();
            for bad in [
                "+0",
                "00",
                "-1",
                "true",
                "0.0",
                "4294967295",
                "4294967296",
                " 0",
            ] {
                assert!(
                    parse_service(value.replace(original, &format!("{key}={bad}")).as_bytes())
                        .is_err()
                );
            }
        }
        for role in ["control", "agent"] {
            let principal = value
                .lines()
                .find_map(|line| line.strip_prefix(&format!("{role}.principal_id=")))
                .unwrap();
            assert!(
                parse_service(
                    value
                        .replace(
                            "owner.principal_id=fixture-owner",
                            &format!("owner.principal_id={principal}")
                        )
                        .as_bytes()
                )
                .is_err()
            );
        }
    }
    #[test]
    fn owner_unit_cgroup_pin_and_principal_syntax_refuse() {
        let value = golden();
        for (key, bad) in [
            ("owner.unit", "escaped/name.service"),
            ("owner.cgroup", "/system.slice/../escaped.service"),
            ("owner.elf_sha256", "uppercaseBAD"),
            ("owner.principal_id", " space"),
        ] {
            let original = value
                .lines()
                .find(|line| line.starts_with(&format!("{key}=")))
                .unwrap();
            assert!(
                parse_service(value.replace(original, &format!("{key}={bad}")).as_bytes()).is_err()
            );
        }
    }
    #[test]
    fn service_bytes_are_bounded_canonical_ascii_lines() {
        let value = golden();
        for bad in [
            vec![],
            vec![0xff],
            value[..value.len() - 1].as_bytes().to_vec(),
            value.replace('\n', "\r\n").into_bytes(),
            vec![b'x'; MAX_APPROVED_SERVICE_POLICY_BYTES + 1],
        ] {
            assert!(parse_service(&bad).is_err());
        }
    }
}
