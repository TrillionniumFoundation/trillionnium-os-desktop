//! Original fixed broker/loader/package inputs for one early host connection.
//! This owner is acquired before HostAdmission and has no guest namespace,
//! process adoption, policy installation, application or Ready operation.
use super::package::{PackageMacOwner, PackageMacRole};
use super::*;
use crate::production_execution::RuntimeMacOwner;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum HostPeerRole {
    Broker,
    Loader,
    Helper,
}
impl HostPeerRole {
    pub(super) fn context(self) -> &'static str {
        match self {
            Self::Broker => BROKER,
            Self::Loader => LOADER,
            Self::Helper => HOST,
        }
    }
    pub(super) fn apparmor(self) -> &'static [u8] {
        match self {
            Self::Broker => AA_BROKER,
            Self::Loader => AA_LOADER,
            Self::Helper => b"unconfined\n",
        }
    }
}

/// Equality binds to the same live in-process objects, not matching digests.
/// Neither original input can be deserialized or reacquired here; retaining an
/// existing Rc keeps the same original objects alive.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct HostPeerPair {
    loaded: usize,
    selection: usize,
    role: HostPeerRole,
}

struct LoaderInputs {
    selection: ProductionSelection,
    mac: LoaderMacWitness,
}

/// The loader owns exactly the selection moved into its fixed constructor and
/// the one real LoaderMacWitness acquired against it. Its Rc cannot create the
/// broker's RuntimeMacOwner or turn the loader into a MacPreflight.
#[derive(Clone)]
pub(crate) struct LoaderHostPeerOwner {
    original: Rc<LoaderInputs>,
}
impl std::fmt::Debug for LoaderHostPeerOwner {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("LoaderHostPeerOwner")
            .finish_non_exhaustive()
    }
}
impl LoaderHostPeerOwner {
    pub(crate) fn acquire(selection: ProductionSelection) -> Result<Self> {
        let mac = LoaderMacWitness::acquire(&selection)?;
        let value = Self {
            original: Rc::new(LoaderInputs { selection, mac }),
        };
        value.objects()?;
        Ok(value)
    }
    pub(crate) fn objects(&self) -> Result<(&LoaderMacWitness, &ProductionSelection)> {
        self.original.mac.revalidate(&self.original.selection)?;
        Ok((&self.original.mac, &self.original.selection))
    }
}

enum Issuer {
    Broker(RuntimeMacOwner),
    Loader(LoaderHostPeerOwner),
    Package(PackageMacOwner),
}
impl Issuer {
    fn retain_original(&self) -> Result<Self> {
        Ok(match self {
            Self::Broker(owner) => Self::Broker(owner.clone()),
            Self::Loader(owner) => Self::Loader(owner.clone()),
            Self::Package(owner) => Self::Package(owner.retain_original()?),
        })
    }
}

/// Each resource stores this original owner before making a namespace,
/// selector or socket. Cloning a preexisting Rc retains those exact objects.
pub(crate) struct HostPeerIssuer {
    original: Issuer,
}
impl std::fmt::Debug for HostPeerIssuer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("HostPeerIssuer").finish_non_exhaustive()
    }
}
impl HostPeerIssuer {
    pub(crate) fn broker(original: RuntimeMacOwner) -> Result<Self> {
        let value = Self {
            original: Issuer::Broker(original),
        };
        value.authority()?.revalidate()?;
        Ok(value)
    }
    pub(crate) fn loader(original: LoaderHostPeerOwner) -> Result<Self> {
        let value = Self {
            original: Issuer::Loader(original),
        };
        value.authority()?.revalidate()?;
        Ok(value)
    }
    pub(crate) fn package(original: PackageMacOwner) -> Result<Self> {
        let value = Self {
            original: Issuer::Package(original),
        };
        value.authority()?.revalidate()?;
        Ok(value)
    }
    pub(super) fn authority(&self) -> Result<HostPeerAuthority<'_>> {
        let (loaded, selection, role) = match &self.original {
            Issuer::Broker(original) => {
                let (mac, selection) = original
                    .objects()
                    .map_err(|e| MacError::Owner(e.to_string()))?;
                (mac.loaded_policy(), selection, HostPeerRole::Broker)
            }
            Issuer::Loader(original) => {
                let (mac, selection) = original.objects()?;
                (mac.loaded_policy(), selection, HostPeerRole::Loader)
            }
            Issuer::Package(original) => {
                let (loaded, selection) = original.objects()?;
                let role = match original.role() {
                    PackageMacRole::Helper => HostPeerRole::Helper,
                    PackageMacRole::Broker => HostPeerRole::Broker,
                };
                (loaded, selection, role)
            }
        };
        let value = HostPeerAuthority {
            original: self,
            loaded,
            selection,
            role,
        };
        value.revalidate()?;
        Ok(value)
    }
}

/// A borrow only from the original sealed runtime, loader or package issuer. No caller-supplied
/// LoadedPolicyWitness, role string, descriptor, PID or JSON constructs it.
pub(super) struct HostPeerAuthority<'a> {
    original: &'a HostPeerIssuer,
    loaded: &'a LoadedPolicyWitness,
    selection: &'a ProductionSelection,
    role: HostPeerRole,
}
impl HostPeerAuthority<'_> {
    /// Retain the existing sealed issuer and its exact original Rc objects.
    /// Namespace custody must own this before the caller can release its issuer.
    pub(super) fn retain_original(&self) -> Result<HostPeerIssuer> {
        self.revalidate()?;
        let pair = self.pair();
        let retained = HostPeerIssuer {
            original: self.original.original.retain_original()?,
        };
        {
            let authority = retained.authority()?;
            require(
                authority.pair() == pair,
                "retained host peer issuer changed the original inputs or role",
            )?;
            authority.revalidate()?;
        }
        self.revalidate()?;
        require(
            self.pair() == pair,
            "original host peer inputs changed while retaining custody",
        )?;
        Ok(retained)
    }
    /// Only the daemon's original startup RuntimeMacOwner may create its
    /// listener. A package broker has the same MAC role but a different issuer.
    pub(super) fn require_runtime_broker(&self) -> Result<()> {
        self.revalidate()?;
        let pair = self.pair();
        require(
            matches!(&self.original.original, Issuer::Broker(_))
                && self.role == HostPeerRole::Broker,
            "listener requires its original runtime broker issuer",
        )?;
        self.revalidate()?;
        require(
            self.pair() == pair,
            "runtime listener issuer changed during validation",
        )
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        let (loaded, selection, role) = match &self.original.original {
            Issuer::Broker(original) => {
                let (mac, selection) = original
                    .objects()
                    .map_err(|e| MacError::Owner(e.to_string()))?;
                (mac.loaded_policy(), selection, HostPeerRole::Broker)
            }
            Issuer::Loader(original) => {
                let (mac, selection) = original.objects()?;
                (mac.loaded_policy(), selection, HostPeerRole::Loader)
            }
            Issuer::Package(original) => {
                let (loaded, selection) = original.objects()?;
                let role = match original.role() {
                    PackageMacRole::Helper => HostPeerRole::Helper,
                    PackageMacRole::Broker => HostPeerRole::Broker,
                };
                (loaded, selection, role)
            }
        };
        require(
            std::ptr::eq(loaded, self.loaded)
                && std::ptr::eq(selection, self.selection)
                && role == self.role,
            "host peer cannot substitute either original input or fixed role",
        )?;
        require(
            self.loaded.declaration.scoped_contexts()?,
            "host peer namespace issuer requires explicit selected providers",
        )?;
        require(
            context_matches(&self_attr::selinux_current()?, role.context())
                && proc_attr(&loaded.own_proc, true)? == role.apparmor(),
            "host peer creator lost its exact actual two-LSM role",
        )?;
        self_attr::require_no_fscreate()?;
        loaded.stable_epoch()
    }
    pub(super) fn loaded(&self) -> &LoadedPolicyWitness {
        self.loaded
    }
    pub(super) fn selection(&self) -> &ProductionSelection {
        self.selection
    }
    pub(super) fn role(&self) -> HostPeerRole {
        self.role
    }
    pub(super) fn context(&self) -> &'static str {
        self.role.context()
    }
    pub(super) fn provider(&self) -> ProviderBinding {
        self.loaded.binding()
    }
    pub(super) fn pair(&self) -> HostPeerPair {
        HostPeerPair {
            loaded: self.loaded as *const _ as usize,
            selection: self.selection as *const _ as usize,
            role: self.role,
        }
    }
    pub(super) fn scoped_contexts(&self) -> Result<bool> {
        self.loaded.declaration.scoped_contexts()
    }
}
