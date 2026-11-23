//! Immutable SELinux selection on the original owned Android netns.
//! Read-only prepare must be retained before activate mutates its exclusively
//! owned private control filesystem or attempts SET. No host /dev fallback,
//! caller namespace FD, imported selection or retried SET can issue authority.
use super::netns_control::{PrivateNetnsControl, SetOutcome};
use super::*;
use crate::production_namespace::OwnedNamespaceWitness;

const NSFS: u64 = 0x6e73_6673;
const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_USERNS: libc::c_ulong = 0xb701;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const FIXED: u32 = 1;
const USED: u32 = 2;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct NamespaceIdentity {
    pub(super) node: Node,
    pub(super) id: u64,
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct OwnerIdentity {
    keeper_pidfd: DescriptorIdentity,
    keeper_proc: Node,
    keeper_start: u64,
    init_pidfd: DescriptorIdentity,
    user: NamespaceIdentity,
    network: NamespaceIdentity,
}
fn duplicate(fd: BorrowedFd<'_>) -> Result<File> {
    let raw = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn context(file: &File, expected: &str) -> Result<()> {
    let before = Node::of(file)?;
    let mut value = [0_u8; 1024];
    let size = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            value.as_mut_ptr().cast(),
            value.len(),
        )
    };
    if size < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        size > 0
            && size as usize <= value.len()
            && context_matches(&value[..size as usize], expected)
            && Node::of(file)? == before,
        "actual fixed provider inode SELinux context differs",
    )
}
pub(super) fn namespace(file: &File, expected: i32) -> Result<NamespaceIdentity> {
    let node = Node::of(file)?;
    require(
        kind(file)? == NSFS && node.mode & libc::S_IFMT == libc::S_IFREG,
        "actual held namespace inode",
    )?;
    let ty = unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) };
    if ty < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut id = 0_u64;
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_ID, &mut id) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        ty == expected && id > 0 && Node::of(file)? == node,
        "original namespace type/ID changed",
    )?;
    context(file, "u:object_r:droidloom_nsfs:s0")?;
    Ok(NamespaceIdentity { node, id })
}
fn namespace_user(network: &File) -> Result<File> {
    let raw = unsafe { libc::ioctl(network.as_raw_fd(), NS_GET_USERNS, 0 as libc::c_ulong) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    let flags = unsafe { libc::fcntl(raw, libc::F_GETFD) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::FD_CLOEXEC != 0,
        "actual namespace owner descriptor CLOEXEC",
    )?;
    Ok(file)
}
fn owner_identity(
    owner: &OwnedNamespaceWitness<'_>,
    selection: &ProductionSelection,
) -> Result<OwnerIdentity> {
    original_owner(owner.revalidate_live_admission())?;
    let lease = original_owner(owner.identity_lease())?;
    require(
        selection.spec().host_uid == lease.host_uid()
            && selection.base_cohort() == lease.broker_cohort(),
        "network provider and original selected namespace owner differ",
    )?;
    let network = original_owner(owner.network_namespace())?;
    let net = namespace(network, libc::CLONE_NEWNET)?;
    let user = namespace(owner.user_namespace(), libc::CLONE_NEWUSER)?;
    require(
        user.id != 3,
        "Android network must belong to the original noninitial user namespace",
    )?;
    let actual_user = namespace_user(network)?;
    require(
        namespace(&actual_user, libc::CLONE_NEWUSER)? == user,
        "original network user-namespace owner differs",
    )?;
    let init = owner.descendant_pidfd().ok_or(MacError::Rejected(
        "network provider lacks original tree PIDFD",
    ))?;
    let value = OwnerIdentity {
        keeper_pidfd: descriptor_identity(owner.pidfd())?,
        keeper_proc: Node::of(owner.proc_directory())?,
        keeper_start: owner.start_ticks(),
        init_pidfd: descriptor_identity(init)?,
        user,
        network: net,
    };
    original_owner(owner.revalidate_live_admission())?;
    Ok(value)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Stage {
    Prepared,
    Activating,
    Selected,
    Failed,
    Retired,
}
pub(crate) struct SelectedAndroidNetwork {
    provider: ProviderBinding,
    owner: OwnerIdentity,
    control: Option<PrivateNetnsControl>,
    network: Option<File>,
    stage: Stage,
    last_set: SetOutcome,
    _same_thread: PhantomData<Rc<()>>,
}
impl std::fmt::Debug for SelectedAndroidNetwork {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SelectedAndroidNetwork")
            .field("stage", &self.stage)
            .field("set_outcome", &self.last_set)
            .finish_non_exhaustive()
    }
}
impl SelectedAndroidNetwork {
    /// Read-only: pin original owner/target and prepare the empty control guard.
    /// DeviceResources must retain this value before activate_private().
    pub(crate) fn prepare_private(
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<Self> {
        mac.revalidate(selection)?;
        require(
            mac.scoped_contexts(),
            "private Android network requires the actual explicit v4 provider",
        )?;
        let original = owner_identity(owner, selection)?;
        let network = duplicate(original_owner(owner.network_namespace())?.as_fd())?;
        require(
            namespace(&network, libc::CLONE_NEWNET)? == original.network,
            "duplicated original network identity",
        )?;
        let control = PrivateNetnsControl::prepare(mac, selection, &network, original.network)?;
        let value = Self {
            provider: mac.binding(),
            owner: original,
            control: Some(control),
            network: Some(network),
            stage: Stage::Prepared,
            last_set: SetOutcome::NotAttempted,
            _same_thread: PhantomData,
        };
        value.original(mac, selection, owner)?;
        Ok(value)
    }
    fn original(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        mac.revalidate(selection)?;
        require(
            self.stage != Stage::Retired
                && mac.scoped_contexts()
                && mac.binding() == self.provider
                && owner_identity(owner, selection)? == self.owner,
            "original private network MAC/tree owner changed",
        )?;
        require(
            namespace(self.network()?, libc::CLONE_NEWNET)? == self.owner.network,
            "original selected network descriptor changed",
        )?;
        mac.revalidate(selection)
    }
    pub(crate) fn activate_private(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        require(
            self.stage == Stage::Prepared,
            "private network activation cannot retry any previous mutation",
        )?;
        self.original(mac, selection, owner)?;
        self.stage = Stage::Activating;
        let result = (|| {
            self.control
                .as_mut()
                .ok_or(MacError::Rejected(
                    "original private selector custody absent",
                ))?
                .create(mac, selection)?;
            let state = self.control.as_ref().unwrap().get(mac, selection)?;
            require(
                state.lsm_id == 0 && state.flags == 0,
                "selection requires original unused and unselected Android netns",
            )?;
            self.original(mac, selection, owner)?;
            // Control records Entered and then the native Applied/Rejected result
            // before any post-syscall check. A failed GET never loses successful SET.
            self.control.as_mut().unwrap().set(mac, selection)?;
            let state = self.control.as_ref().unwrap().get(mac, selection)?;
            require(
                state.lsm_id == 101 && state.flags == FIXED,
                "actual new selector must be fixed and still unused",
            )?;
            self.original(mac, selection, owner)
        })();
        self.last_set = self
            .control
            .as_ref()
            .map_or(self.last_set, PrivateNetnsControl::set_outcome);
        self.stage = if result.is_ok() {
            Stage::Selected
        } else {
            Stage::Failed
        };
        result
    }
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        require(
            self.stage == Stage::Selected && self.last_set == SetOutcome::Applied,
            "private network lacks its original actual SET",
        )?;
        self.original(mac, selection, owner)?;
        let state = self
            .control
            .as_ref()
            .ok_or(MacError::Rejected("private selected control retired"))?
            .get(mac, selection)?;
        require(
            state.lsm_id == 101 && (state.flags == FIXED || state.flags == FIXED | USED),
            "actual original Android netns lost immutable SELinux representation",
        )?;
        self.original(mac, selection, owner)
    }
    pub(super) fn require_unused(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        self.revalidate(mac, selection, owner)?;
        let state = self.control.as_ref().unwrap().get(mac, selection)?;
        require(
            state.lsm_id == 101 && state.flags == FIXED,
            "first selected socket requires original unused network",
        )
    }
    pub(super) fn require_used(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        owner: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        self.revalidate(mac, selection, owner)?;
        let state = self.control.as_ref().unwrap().get(mac, selection)?;
        require(
            state.lsm_id == 101 && state.flags == FIXED | USED,
            "selected socket must leave actual immutable used state",
        )
    }
    pub(super) fn network(&self) -> Result<&File> {
        self.network
            .as_ref()
            .ok_or(MacError::Rejected("original network descriptor retired"))
    }
    pub(super) fn network_identity(&self) -> NamespaceIdentity {
        self.owner.network
    }
    /// Closes this owner's control and namespace FDs only. Existing selector
    /// state is never reset; the original tree and any sockets still require
    /// their separate actual retirement before global namespace disappearance.
    pub(crate) fn retire(&mut self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.provider.tid as i64,
            "network retirement requires original creator thread",
        )?;
        if self.stage == Stage::Retired {
            return Ok(());
        }
        if let Some(control) = self.control.as_mut() {
            self.last_set = control.set_outcome();
            control.retire()?;
        }
        self.control.take();
        self.network.take();
        self.stage = Stage::Retired;
        Ok(())
    }
}
impl Drop for SelectedAndroidNetwork {
    fn drop(&mut self) {
        if self.stage != Stage::Prepared && self.stage != Stage::Retired {
            if let Some(control) = self.control.take() {
                std::mem::forget(control);
            }
            if let Some(network) = self.network.take() {
                std::mem::forget(network);
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::super::netns_control::{parse_device, request_for_test};
    use super::*;
    #[test]
    fn provider_device_number_rejects_unrelated_and_noncanonical_records() {
        assert_eq!(parse_device(b"10:255\n").unwrap(), 255);
        assert_eq!(parse_device(b"10:0\n").unwrap(), 0);
        for bad in [
            b"1:255\n".as_slice(),
            b"10:0255\n",
            b"10:+1\n",
            b"10:1048576\n",
            b"10:255",
            b"10:255\n\n",
            b"10:255:1\n",
        ] {
            assert!(parse_device(bad).is_err(), "{bad:?}");
        }
    }
    #[test]
    fn regular_file_cannot_become_selected_namespace_from_supplied_numbers() {
        let file = tempfile::tempfile().unwrap();
        assert!(namespace(&file, libc::CLONE_NEWNET).is_err());
        assert!(namespace_user(&file).is_err());
        let request = request_for_test(file.as_raw_fd(), 123);
        assert_eq!(std::mem::size_of_val(&request), 32);
        // A correct wire request is still not a SelectedAndroidNetwork.
    }
}
