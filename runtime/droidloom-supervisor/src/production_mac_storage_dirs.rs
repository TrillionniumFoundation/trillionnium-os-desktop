//! Same-epoch labels for the original CP3A's three storage directories.
//! /mnt/user has an exact original platform file-context entry. The other
//! two names have no such platform entry: their expected labels come from
//! actual fixed INIT/tmpfs/dir named-create queries in the enforcing kernel.
//! This observes an actual inode; it never sets fscreate or relabels it.
use super::*;

const TMPFS: &str = "u:object_r:tmpfs:s0";
const USER: &str = "u:object_r:mnt_user_file:s0";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum StorageDirectoryRole {
    User,
    Installer,
    AndroidWritable,
}
impl StorageDirectoryRole {
    pub(crate) const ALL: [Self; 3] = [Self::User, Self::Installer, Self::AndroidWritable];
}

fn canonical_creation(bytes: &[u8]) -> Result<String> {
    let body = bytes
        .strip_suffix(b"\0")
        .or_else(|| bytes.strip_suffix(b"\n"))
        .unwrap_or(bytes);
    let text = std::str::from_utf8(body)
        .map_err(|_| MacError::Rejected("non-text storage creation context"))?;
    let ty = text
        .strip_prefix("u:object_r:")
        .and_then(|s| s.strip_suffix(":s0"))
        .ok_or(MacError::Rejected(
            "storage creation context has another user, role or range",
        ))?;
    require(
        !ty.is_empty()
            && ty.len() <= 128
            && ty.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_'),
        "bounded canonical storage creation type",
    )?;
    Ok(text.to_owned())
}

fn automatic_contexts(mac: &MacPreflight) -> Result<[String; 2]> {
    let number = class_number(&mac.loaded.root, "dir")?;
    let mut contexts = Vec::with_capacity(2);
    for basename in ["installer", "androidwritable"] {
        let query = format!("{INIT} {TMPFS} {number} {basename}");
        contexts.push(canonical_creation(&transaction(
            &mac.loaded.root,
            "create",
            query.as_bytes(),
        )?)?);
    }
    Ok([contexts.remove(0), contexts.remove(0)])
}

fn inode_label(file: &File) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    require(
        before.mode & libc::S_IFMT == libc::S_IFDIR,
        "storage MAC observation requires an actual directory",
    )?;
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
        count > 0 && count as usize <= bytes.len() && Node::of(file)? == before,
        "storage inode changed during its actual label observation",
    )?;
    Ok(bytes[..count as usize].to_vec())
}

#[derive(Debug)]
pub(crate) struct MacStorageDirectoryWitness {
    provider: ProviderBinding,
    generation: ExecutedInitGeneration,
    automatic: [String; 2],
    _same_thread: PhantomData<Rc<()>>,
}

impl MacPreflight {
    pub(crate) fn original_storage_directories(
        &self,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<MacStorageDirectoryWitness> {
        let generation = self.actual_init(init)?;
        let automatic = automatic_contexts(self)?;
        require(
            self.actual_init(init)? == generation,
            "original storage init changed during named-create queries",
        )?;
        let value = MacStorageDirectoryWitness {
            provider: self.binding(),
            generation,
            automatic,
            _same_thread: PhantomData,
        };
        value.revalidate_init(self, init)?;
        Ok(value)
    }
}

impl MacStorageDirectoryWitness {
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        require(
            self.provider == mac.binding(),
            "storage directories belong to another provider or epoch",
        )?;
        mac.revalidate(selection)?;
        require(
            automatic_contexts(mac)? == self.automatic,
            "original storage automatic creation contexts changed",
        )?;
        mac.revalidate(selection)?;
        require(
            self.provider == mac.binding(),
            "storage directory provider changed during observation",
        )
    }
    pub(crate) fn revalidate_init(
        &self,
        mac: &MacPreflight,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<()> {
        self.revalidate(mac, init.selection())?;
        require(
            mac.actual_init(init)? == self.generation,
            "storage directories have another original init generation",
        )?;
        self.revalidate(mac, init.selection())
    }
    pub(crate) fn node(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
        role: StorageDirectoryRole,
    ) -> Result<()> {
        self.revalidate(mac, selection)?;
        let expected = match role {
            StorageDirectoryRole::User => USER,
            StorageDirectoryRole::Installer => &self.automatic[0],
            StorageDirectoryRole::AndroidWritable => &self.automatic[1],
        };
        let before = Node::of(file)?;
        require(
            context_matches(&inode_label(file)?, expected),
            "actual original storage directory label differs from its fixed policy derivation",
        )?;
        let mut sequence = Some(mac.loaded.av_sequence);
        access(
            &mac.loaded.root,
            BROKER,
            expected,
            "dir",
            &["getattr", "open", "read", "search", "mounton"],
            true,
            &mut sequence,
        )?;
        require(
            Node::of(file)? == before,
            "storage inode changed during current-epoch access decisions",
        )?;
        self.revalidate(mac, selection)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn storage_creation_context_parser_rejects_foreign_roles_ranges_and_ambiguous_suffixes() {
        for value in [
            b"u:object_r:init_tmpfs:s0".as_slice(),
            b"u:object_r:init_tmpfs:s0\0",
            b"u:object_r:init_tmpfs:s0\n",
        ] {
            assert_eq!(
                canonical_creation(value).unwrap(),
                "u:object_r:init_tmpfs:s0"
            );
        }
        for value in [
            b"u:r:init:s0".as_slice(),
            b"u:object_r::s0",
            b"u:object_r:tmpfs:s0:c1",
            b"u:object_r:tmpfs:s0\n\0",
            b"u:object_r:tmpfs:s0\0x",
            b"u:object_r:tmpfs other:s0",
            b"u:object_r:../tmpfs:s0",
        ] {
            assert!(canonical_creation(value).is_err());
        }
        let file = tempfile::tempfile().unwrap();
        assert!(inode_label(&file).is_err());
    }
}
