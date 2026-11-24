use crate::model::Component;
use crate::{Result, ensure};

pub fn parts(path: &str) -> Result<Vec<&str>> {
    ensure(
        path.starts_with('/') && path != "/",
        "path must be an absolute in-root name",
    )?;
    ensure(
        !path.contains('\0') && !path.contains('\n') && !path.contains('\r'),
        "invalid path bytes",
    )?;
    let p: Vec<_> = path[1..].split('/').collect();
    ensure(
        p.iter().all(|x| !x.is_empty() && *x != "." && *x != ".."),
        "path has an empty, dot or parent component",
    )?;
    Ok(p)
}

fn beneath(p: &str, root: &str) -> bool {
    p == root || p.starts_with(&format!("{root}/"))
}

pub fn private(p: &str) -> bool {
    [
        "/home",
        "/root",
        "/run",
        "/proc",
        "/sys",
        "/dev",
        "/tmp",
        "/mnt",
        "/media",
        "/data",
        "/metadata",
        "/etc/NetworkManager/system-connections",
        "/etc/netplan",
        "/etc/wpa_supplicant",
        "/etc/sssd",
        "/etc/ssl/private",
        "/etc/credstore",
        "/etc/credstore.encrypted",
        "/etc/apt/auth.conf.d",
        "/usr/lib/ssl/private",
        "/usr/local",
        "/usr/lib/droidloom",
        "/var/lib/NetworkManager",
        "/var/lib/bluetooth",
        "/var/lib/AccountsService",
        "/var/lib/gdm3",
        "/var/lib/sss",
        "/var/lib/private",
        "/var/lib/droidloom",
        "/var/cache/droidloom",
        "/var/log",
        "/var/lib/snapd/auth",
        "/var/lib/snapd/device",
        "/var/lib/snapd/cookie",
        "/var/lib/snapd/credentials",
    ]
    .iter()
    .any(|x| beneath(p, x))
        || [
            "/etc/passwd",
            "/etc/group",
            "/etc/shadow",
            "/etc/gshadow",
            "/etc/subuid",
            "/etc/subgid",
            "/etc/passwd-",
            "/etc/group-",
            "/etc/shadow-",
            "/etc/gshadow-",
            "/etc/machine-id",
            "/etc/hostname",
            "/etc/hosts",
            "/etc/resolv.conf",
            "/etc/fstab",
            "/etc/crypttab",
            "/etc/ppp/chap-secrets",
            "/etc/ppp/pap-secrets",
            "/etc/security/opasswd",
            "/etc/apt/auth.conf",
            "/var/lib/snapd/state.json",
            "/var/lib/dbus/machine-id",
        ]
        .contains(&p)
        || p.starts_with("/etc/ssh/ssh_host_")
}

pub fn public_config(p: &str) -> bool {
    [
        "/etc/apparmor.d",
        "/etc/dbus-1",
        "/etc/pam.d",
        "/etc/fonts",
        "/etc/ld.so.conf.d",
        "/etc/alternatives",
        "/etc/dconf",
        "/etc/xdg",
        "/etc/glvnd",
        "/etc/gtk-3.0",
        "/etc/gtk-4.0",
        "/etc/pipewire",
        "/etc/wireplumber",
        "/etc/libnl-3",
        "/etc/alsa",
        "/etc/modprobe.d",
        "/etc/modules-load.d",
        "/etc/udev",
        "/etc/vulkan",
        "/etc/polkit-1",
        "/etc/X11/xinit",
        "/etc/X11/Xsession.d",
        "/etc/security/limits.d",
        "/etc/ssl/certs",
        "/etc/ca-certificates",
    ]
    .iter()
    .any(|x| beneath(p, x))
        || [
            "/etc/ld.so.conf",
            "/etc/nsswitch.conf",
            "/etc/host.conf",
            "/etc/gai.conf",
            "/etc/shells",
            "/etc/services",
            "/etc/protocols",
            "/etc/rpc",
            "/etc/os-release",
            "/etc/lsb-release",
            "/etc/login.defs",
            "/etc/debian_version",
            "/etc/issue",
            "/etc/issue.net",
            "/etc/ssl/openssl.cnf",
            "/etc/ca-certificates.conf",
            "/etc/ssh/sshd_config",
            "/etc/ssh/ssh_config",
            "/etc/ssh/moduli",
            "/etc/NetworkManager/NetworkManager.conf",
            "/etc/bluetooth/main.conf",
            "/etc/bluetooth/input.conf",
            "/etc/bluetooth/network.conf",
            "/etc/security/access.conf",
            "/etc/security/group.conf",
            "/etc/security/time.conf",
            "/etc/security/limits.conf",
            "/etc/security/pam_env.conf",
            "/etc/security/pwquality.conf",
            "/etc/security/faillock.conf",
            "/etc/security/sepermit.conf",
            "/etc/X11/Xsession",
            "/etc/X11/Xsession.options",
            "/etc/X11/Xwrapper.config",
        ]
        .contains(&p)
}

pub fn validate(p: &str, component: &Component, release: &str) -> Result<()> {
    parts(p)?;
    ensure(
        !private(p),
        &format!("private or live path is forbidden: {p}"),
    )?;
    match component {
        Component::AncestorDirectory => {
            ensure(
                [
                    "/usr",
                    "/etc",
                    "/etc/ssh",
                    "/etc/NetworkManager",
                    "/etc/bluetooth",
                    "/etc/security",
                    "/etc/X11",
                    "/etc/ssl",
                    "/var",
                    "/var/lib",
                    "/var/lib/snapd",
                    "/var/lib/snapd/snaps",
                    "/usr/lib/modules",
                ]
                .contains(&p)
                    || p.starts_with("/usr/")
                    || public_config(p),
                "unapproved ancestor directory",
            )?;
            ensure(
                !beneath(p, "/usr/lib/modules")
                    || p == "/usr/lib/modules"
                    || beneath(p, &format!("/usr/lib/modules/{release}")),
                "other kernel directory is forbidden",
            )?;
        }
        Component::Native | Component::GeneratedPublicCache => {
            ensure(
                p == "/usr"
                    || p.starts_with("/usr/")
                    || ["/bin", "/sbin", "/lib", "/lib64"].contains(&p),
                "native inputs must be public usr files or usrmerge links",
            )?;
            ensure(
                !beneath(p, "/usr/lib/modules"),
                "kernel modules require separate target admission",
            )?;
        }
        Component::PublicConfig => ensure(
            public_config(p),
            &format!("configuration lacks an explicit public allowlist: {p}"),
        )?,
        Component::TargetModule => ensure(
            beneath(p, &format!("/usr/lib/modules/{release}")),
            "module path is not for the selected kernel release",
        )?,
        Component::SnapArchive => {
            let name = p
                .strip_prefix("/var/lib/snapd/snaps/")
                .ok_or("snap image outside explicit archive directory")?;
            ensure(
                !name.contains('/')
                    && name.ends_with(".snap")
                    && name.bytes().all(|b| {
                        b.is_ascii_lowercase() || b.is_ascii_digit() || b"-_.".contains(&b)
                    }),
                "invalid public snap archive name",
            )?;
        }
    }
    Ok(())
}

pub fn parent(p: &str) -> &str {
    p.rsplit_once('/')
        .map(|x| if x.0.is_empty() { "/" } else { x.0 })
        .unwrap_or("/")
}

pub fn normalize_link(path: &str, target: &str) -> Result<String> {
    ensure(
        !target.is_empty() && !target.contains('\0') && !target.contains('\n'),
        "invalid symlink target",
    )?;
    let mut out: Vec<&str> = if target.starts_with('/') {
        Vec::new()
    } else {
        parent(path).split('/').filter(|s| !s.is_empty()).collect()
    };
    for c in target.split('/') {
        match c {
            "" | "." => (),
            ".." => {
                ensure(out.pop().is_some(), "symlink escapes fixture root")?;
            }
            s => out.push(s),
        }
    }
    let p = format!("/{}", out.join("/"));
    let runtime = [
        "/dev/null",
        "/proc/mounts",
        "/proc/self/mounts",
        "/run",
        "/run/lock",
    ]
    .contains(&p.as_str());
    ensure(
        runtime || !private(&p),
        &format!("symlink reaches private/live data: {path}"),
    )?;
    let usrmerge = ["/lib", "/lib64", "/bin", "/sbin"]
        .iter()
        .any(|x| beneath(&p, x));
    ensure(
        runtime || usrmerge || p == "/usr" || p.starts_with("/usr/") || public_config(&p),
        &format!("symlink target is not a public input: {path}"),
    )?;
    Ok(p)
}
