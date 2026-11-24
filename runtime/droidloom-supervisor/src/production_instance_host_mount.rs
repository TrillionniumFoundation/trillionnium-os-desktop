//! Original host mount-namespace custody from the authenticated boot factory.
//! Linux forbids binding a mount namespace inside itself. The boot PID 1's
//! actual inherited namespace descriptor stays live in the original factory.
use super::*;

pub(super) const REQUEST: &[u8; 8] = b"DLHOST01";
unsafe extern "C" {
    fn droidloom_factory_host_mount() -> libc::c_int;
    fn droidloom_instance_host_mount(fd: libc::c_int) -> libc::c_int;
}

pub(super) struct HostMount {
    namespace: File,
    factory: (u64, u64),
}
impl HostMount {
    pub(super) fn acquire(channel: &File, peer: &Peer) -> io::Result<Self> {
        if peer.selinux != FACTORY_SELINUX || peer.apparmor != FACTORY_APPARMOR {
            return Err(invalid(
                "host namespace authority requires the original factory",
            ));
        }
        peer.revalidate()?;
        send(channel, REQUEST, &[])?;
        let Some((tag, mut descriptors)) = receive(channel, Duration::from_secs(5))? else {
            return Err(invalid("original host mount namespace was not returned"));
        };
        if &tag != REQUEST || descriptors.len() != 1 {
            return Err(invalid(
                "host mount authority is not one original namespace descriptor",
            ));
        }
        let value = Self {
            namespace: descriptors.remove(0),
            factory: identity(&peer.pidfd)?,
        };
        value.revalidate(peer)?;
        Ok(value)
    }
    pub(super) fn revalidate(&self, peer: &Peer) -> io::Result<()> {
        peer.revalidate()?;
        if identity(&peer.pidfd)? != self.factory {
            return Err(invalid(
                "host mount authority belongs to another factory process",
            ));
        }
        // Native NSFS/type and actual self-MNT inode checks join the current
        // UID, MAC, NNP and three immutable boot namespace-pin checks.
        cv(unsafe { droidloom_instance_host_mount(self.namespace.as_raw_fd()) })?;
        peer.revalidate()
    }
}
pub(super) fn serve(channel: &File) -> io::Result<()> {
    let raw = unsafe { droidloom_factory_host_mount() };
    cv(raw)?;
    let original = unsafe { File::from_raw_fd(raw) };
    // This is another reference to the actual boot PID 1-opened description.
    // Neither a JSON inode claim nor a replacement namespace is sent.
    send(channel, REQUEST, &[&original])
}
