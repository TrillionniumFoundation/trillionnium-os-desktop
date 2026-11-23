//! Read-only MAC observation for a genuine apexd decompression request.
//! The original apexd owns its staging pathname and RestoreconPath. This
//! observer never relabels, reopens, writes, maps or executes that source.
use super::*;
use crate::production_execution::RuntimeMacOwner;
use crate::production_private_loop_owner::compressed::MatchedDecompressedCapex;

const STAGING: &str = "u:object_r:staging_data_file:s0";
const TMPFS: &str = "u:object_r:tmpfs:s0";
const APEXD: &str = "u:r:apexd:s0";

fn owner_objects(owner: &RuntimeMacOwner) -> Result<(&MacPreflight, &ProductionSelection)> {
    owner
        .objects()
        .map_err(|error| MacError::Owner(error.to_string()))
}
fn exact_file_context(file: &File, expected: &str) -> Result<()> {
    let before = Node::of(file)?;
    let mut bytes = [0_u8; 1024];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count > 0 && count as usize <= bytes.len(),
        "bounded actual CAPEX context",
    )?;
    let bytes = &bytes[..count as usize];
    require(
        bytes == expected.as_bytes() || bytes.strip_suffix(b"\0") == Some(expected.as_bytes()),
        "actual CAPEX source/output label differs from its fixed role",
    )?;
    require(
        Node::of(file)? == before,
        "CAPEX inode changed during the original label observation",
    )
}
fn decisions(mac: &MacPreflight) -> Result<()> {
    let root = &mac.loaded.root;
    let mut sequence = Some(mac.loaded.av_sequence);
    self_attr::require_no_fscreate()?;
    access(root, BROKER, APEXD, "fd", &["use"], true, &mut sequence)?;
    access(
        root,
        BROKER,
        APEXD,
        "process",
        &["ptrace"],
        true,
        &mut sequence,
    )?;
    access(
        root,
        BROKER,
        BROKER,
        "cap_userns",
        &["sys_ptrace"],
        true,
        &mut sequence,
    )?;
    access(
        root,
        BROKER,
        BROKER,
        "capability",
        &["sys_ptrace"],
        false,
        &mut sequence,
    )?;
    access(
        root,
        BROKER,
        BROKER,
        "process",
        &["setfscreate"],
        false,
        &mut sequence,
    )?;
    access(
        root,
        BROKER,
        STAGING,
        "file",
        &["read", "getattr"],
        true,
        &mut sequence,
    )?;
    for permission in [
        "open",
        "create",
        "write",
        "append",
        "setattr",
        "relabelfrom",
        "relabelto",
        "link",
        "unlink",
        "rename",
        "execute",
        "execute_no_trans",
        "entrypoint",
        "map",
        "ioctl",
    ] {
        access(
            root,
            BROKER,
            STAGING,
            "file",
            &[permission],
            false,
            &mut sequence,
        )?;
    }
    access(
        root,
        BROKER,
        TMPFS,
        "file",
        &["create", "open", "read", "write", "getattr", "setattr"],
        true,
        &mut sequence,
    )?;
    let class = class_number(root, "file")?;
    let query = format!("{BROKER} {TMPFS} {class}");
    require(
        context_matches(&transaction(root, "create", query.as_bytes())?, TMPFS),
        "automatic anonymous output context must be the original fixed tmpfs type",
    )?;
    mac.loaded.stable_epoch()
}

/// Same original RuntimeMacOwner, provider epoch, held staging label and
/// anonymous output label. This type does not issue an apexd task/request,
/// prove AVB cryptography, or authorize any dm-verity/namespace operation.
pub(crate) struct MacRequestedCapexWitness {
    owner: RuntimeMacOwner,
    matched: Rc<MatchedDecompressedCapex>,
    provider: ProviderBinding,
    requested_node: Node,
    output_node: Node,
}
impl MacRequestedCapexWitness {
    pub(crate) fn observe(
        owner: &RuntimeMacOwner,
        matched: Rc<MatchedDecompressedCapex>,
    ) -> Result<Self> {
        let (mac, selection) = owner_objects(owner)?;
        mac.revalidate(selection)?;
        decisions(mac)?;
        matched.revalidate()?;
        let provider = mac.binding();
        let requested = matched.requested_file()?;
        let requested_node = Node::of(requested)?;
        exact_file_context(requested, STAGING)?;
        let output = matched.sealed_backing()?.file()?;
        let output_node = Node::of(output)?;
        require(
            output_node.mode == libc::S_IFREG | 0o400
                && output_node.uid == 0
                && output_node.gid == 0
                && output_node.links == 0,
            "only the original broker-owned sealed anonymous output",
        )?;
        exact_file_context(output, TMPFS)?;
        let retained = owner.clone();
        retained
            .require_pair(mac, selection)
            .map_err(|error| MacError::Owner(error.to_string()))?;
        let value = Self {
            owner: retained,
            matched,
            provider,
            requested_node,
            output_node,
        };
        value.revalidate(owner)?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self, owner: &RuntimeMacOwner) -> Result<()> {
        let (mac, selection) = owner_objects(owner)?;
        self.owner
            .require_pair(mac, selection)
            .map_err(|error| MacError::Owner(error.to_string()))?;
        mac.revalidate(selection)?;
        require(
            mac.binding() == self.provider,
            "same CAPEX request MAC provider and epoch",
        )?;
        self.matched.revalidate()?;
        let source = self.matched.requested_file()?;
        let output = self.matched.sealed_backing()?.file()?;
        require(
            Node::of(source)? == self.requested_node && Node::of(output)? == self.output_node,
            "same held original source and separate sealed output full identities",
        )?;
        exact_file_context(source, STAGING)?;
        exact_file_context(output, TMPFS)?;
        decisions(mac)?;
        require(
            Node::of(source)? == self.requested_node && Node::of(output)? == self.output_node,
            "original CAPEX identities changed during MAC queries",
        )?;
        self.matched.revalidate()?;
        mac.revalidate(selection)?;
        require(
            mac.binding() == self.provider,
            "CAPEX request provider changed after queries",
        )
    }
    pub(crate) fn require_matched(
        &self,
        owner: &RuntimeMacOwner,
        matched: &Rc<MatchedDecompressedCapex>,
    ) -> Result<()> {
        require(
            Rc::ptr_eq(&self.matched, matched),
            "same complete original matched-source owner",
        )?;
        self.revalidate(owner)
    }
}
impl std::fmt::Debug for MacRequestedCapexWitness {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MacRequestedCapexWitness")
            .field("role_index", &self.matched.index())
            .finish_non_exhaustive()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn requested_capex_context_does_not_accept_an_unlabelled_host_copy() {
        let file = tempfile::tempfile().unwrap();
        assert!(exact_file_context(&file, STAGING).is_err());
        assert!(exact_file_context(&file, TMPFS).is_err());
    }
}
