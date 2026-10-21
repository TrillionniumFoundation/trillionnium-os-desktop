// SPDX-License-Identifier: MPL-2.0

use std::path::PathBuf;

use crate::arch::Arch;

mod action;
pub use action::*;
mod boot;
pub use boot::*;
mod grub;
pub use grub::*;
mod qemu;
pub use qemu::*;

/// All the configurable fields within a scheme.
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct Scheme {
    /// The working directory.
    ///
    /// The user is not allowed to set this field. However,
    /// the manifest loader set this and all actions such
    /// as running, testing, and building will use this field.
    pub work_dir: Option<PathBuf>,
    #[serde(default)]
    pub supported_archs: Vec<Arch>,
    /// The boot configs.
    ///
    /// Building, running, and testing would consult on these configs.
    pub boot: Option<BootScheme>,
    /// The GRUB configs.
    ///
    /// Building, running, and testing would consult on these configs.
    pub grub: Option<GrubScheme>,
    /// The QEMU configs.
    ///
    /// Building, running, and testing would consult on these configs.
    pub qemu: Option<QemuScheme>,
    /// Other build configs.
    ///
    /// Building, running, and testing would consult on these configs.
    pub build: Option<BuildScheme>,
    /// Running specific configs.
    ///
    /// These values, if exists, overrides global boot/GRUB/QEMU/build configs.
    pub run: Option<ActionScheme>,
    /// Testing specific configs.
    ///
    /// These values, if exists, overrides global boot/GRUB/QEMU/build configs.
    pub test: Option<ActionScheme>,
}

macro_rules! inherit_optional {
    ($from:ident, $to:ident, .$field:ident) => {
        if let Some(ref mut to_field) = $to.$field {
            if let Some(from_field) = &$from.$field {
                to_field.inherit(from_field);
            }
        } else {
            $to.$field = $from.$field.clone();
        }
    };
}
use inherit_optional;

impl Scheme {
    pub fn empty() -> Self {
        Scheme {
            work_dir: None,
            supported_archs: vec![],
            boot: None,
            grub: None,
            qemu: None,
            build: None,
            run: None,
            test: None,
        }
    }

    pub fn inherit(&mut self, from: &Self) {
        // Supported archs are not inherited
        inherit_optional!(from, self, .boot);
        inherit_optional!(from, self, .grub);
        inherit_optional!(from, self, .build);
        inherit_optional!(from, self, .run);
        inherit_optional!(from, self, .test);
        // The inheritance of `work_dir` depends on `qemu`, so
        // here is a special treatment.
        if let Some(qemu) = &mut self.qemu {
            if let Some(from_qemu) = &from.qemu {
                if qemu.args.is_none() {
                    qemu.args.clone_from(&from_qemu.args);
                    self.work_dir.clone_from(&from.work_dir);
                }
                if qemu.path.is_none() {
                    qemu.path.clone_from(&from_qemu.path);
                    self.work_dir.clone_from(&from.work_dir);
                }
                if qemu.monitor_transport.is_none() {
                    qemu.monitor_transport = from_qemu.monitor_transport;
                }
                if qemu.log_file.is_none() {
                    qemu.log_file.clone_from(&from_qemu.log_file);
                }
                if qemu.with_daemons.is_none() {
                    qemu.with_daemons.clone_from(&from_qemu.with_daemons);
                }
            }
        } else {
            self.qemu.clone_from(&from.qemu);
            self.work_dir.clone_from(&from.work_dir);
        }
    }

    /// Produces a scheme in which `run` and `test` action settings inherit
    /// from the default settings in the provided scheme.
    pub fn run_and_test_inherit_from_global(&mut self) {
        let old_scheme = self.clone();

        if let Some(run) = &mut self.run {
            inherit_optional!(old_scheme, run, .boot);
            inherit_optional!(old_scheme, run, .grub);
            inherit_optional!(old_scheme, run, .qemu);
            inherit_optional!(old_scheme, run, .build);
        } else {
            self.run = Some(ActionScheme {
                boot: self.boot.clone(),
                grub: self.grub.clone(),
                qemu: self.qemu.clone(),
                build: self.build.clone(),
            });
        }

        if let Some(test) = &mut self.test {
            inherit_optional!(old_scheme, test, .boot);
            inherit_optional!(old_scheme, test, .grub);
            inherit_optional!(old_scheme, test, .qemu);
            inherit_optional!(old_scheme, test, .build);
        } else {
            self.test = Some(ActionScheme {
                boot: self.boot.clone(),
                grub: self.grub.clone(),
                qemu: self.qemu.clone(),
                build: self.build.clone(),
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest_schemes(source: &str) -> (Scheme, Scheme) {
        let mut manifest: crate::config::manifest::TomlManifest = toml::from_str(source).unwrap();
        manifest.default_scheme.run_and_test_inherit_from_global();
        let mut named = manifest.map.remove("named").unwrap();
        named.run_and_test_inherit_from_global();
        named.inherit(&manifest.default_scheme);
        (manifest.default_scheme, named)
    }

    #[test]
    fn named_scheme_partial_qemu_inherits_monitor_transport_for_all_actions() {
        let (_, named) = manifest_schemes(
            r#"
            [qemu]
            monitor_transport = "tcp"
            [scheme.named.qemu]
            args = "-m 512M"
            [scheme.named.run.qemu]
            args = "-m 256M"
            [scheme.named.test.qemu]
            args = "-m 128M"
        "#,
        );
        assert_eq!(
            named.qemu.unwrap().monitor_transport,
            Some(MonitorTransport::Tcp)
        );
        assert_eq!(
            named.run.unwrap().qemu.unwrap().monitor_transport,
            Some(MonitorTransport::Tcp)
        );
        assert_eq!(
            named.test.unwrap().qemu.unwrap().monitor_transport,
            Some(MonitorTransport::Tcp)
        );
    }

    #[test]
    fn named_scheme_and_action_monitor_overrides_are_preserved() {
        let (_, named) = manifest_schemes(
            r#"
            [qemu]
            monitor_transport = "tcp"
            [scheme.named.qemu]
            monitor_transport = "unix"
            [scheme.named.run.qemu]
            args = "-m 256M"
            [scheme.named.test.qemu]
            monitor_transport = "tcp"
        "#,
        );
        assert_eq!(
            named.qemu.unwrap().monitor_transport,
            Some(MonitorTransport::Unix)
        );
        assert_eq!(
            named.run.unwrap().qemu.unwrap().monitor_transport,
            Some(MonitorTransport::Unix)
        );
        assert_eq!(
            named.test.unwrap().qemu.unwrap().monitor_transport,
            Some(MonitorTransport::Tcp)
        );
    }
}
