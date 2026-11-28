//! Actual fixed PM reads for the source-owned legacy identity observer.
//!
//! The enum selects only three old readonly commands. The result has no public
//! fields, deserializer or constructor; it can only follow an authenticated
//! broker request and actual instance-factory query retirement.
use super::*;
use crate::native_application_ui_gateway::{GatewayCommand, GatewayReply, GatewayRequest};
use std::process::Output;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum NativeLeafPackageReadKind {
    Identity,
    Paths,
    Launcher,
}
impl NativeLeafPackageReadKind {
    pub(crate) fn from_opcode(value: u8) -> Option<Self> {
        match value {
            b'I' => Some(Self::Identity),
            b'P' => Some(Self::Paths),
            b'L' => Some(Self::Launcher),
            _ => None,
        }
    }
    pub(crate) fn opcode(self) -> u8 {
        match self {
            Self::Identity => b'I',
            Self::Paths => b'P',
            Self::Launcher => b'L',
        }
    }
    fn name(self) -> &'static str {
        match self {
            Self::Identity => "identity",
            Self::Paths => "paths",
            Self::Launcher => "launcher",
        }
    }
    fn command(self, package: &str) -> GatewayCommand {
        let package = package.to_owned();
        match self {
            Self::Identity => GatewayCommand::PackageIdentity { package },
            Self::Paths => GatewayCommand::PackagePaths { package },
            Self::Launcher => GatewayCommand::PackageLauncher { package },
        }
    }
}

pub(crate) struct NativeLeafPackageReadObservation {
    kind: NativeLeafPackageReadKind,
    request: GatewayRequest,
    reply: GatewayReply,
    output: Output,
    peer: NativeInspectionPeer,
    pidfd: fs::File,
    observed_at: Instant,
}
impl NativeLeafPackageReadObservation {
    pub(crate) fn output(&self) -> &Output {
        &self.output
    }

    /// A comparison envelope for this invocation's private sealed FD. It does
    /// not expose a way to reconstruct this observation or APK custody.
    pub(crate) fn comparison(
        &self,
        inspector: &NativeApplicationInspector,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        end: Instant,
    ) -> Result<serde_json::Value, ControlError> {
        inspector.require_observations_local(main, application, end)?;
        live(&self.pidfd).map_err(|e| io_error("check fixed package observer peer", e))?;
        let original = self.pidfd.metadata()
            .map_err(|e| io_error("stat fixed package observer peer", e))?;
        let current = inspector.pidfd.metadata()
            .map_err(|e| io_error("stat current fixed package observer peer", e))?;
        if self.peer != inspector.observation()?
            || (original.dev(), original.ino()) != (current.dev(), current.ino())
            || self.request.main() != main.facts()
            || self.request.application() != application.facts()
            || self.request.command() != &self.kind.command(&application.facts().package)
            || self.observed_at < application.observed_at()
            || self.observed_at < main.observed_at()
            || self.observed_at >= end
        {
            return Err(ControlError::Invalid(
                "fixed package read differs from its actual original peer/Main/PM".into(),
            ));
        }
        // output_for was checked while the actual command end was live. This
        // historical encoding does not renew that command or invoke it again.
        let value = serde_json::json!({
            "schema": "droidloom.native-leaf-package-read.v1",
            "kind": self.kind.name(),
            "gateway": &self.reply,
            "comparison_only": true,
            "business_actions_admitted": false,
        });
        if serde_json::to_vec(&value)?.len() > 262144 {
            return Err(ControlError::Invalid(
                "fixed package comparison exceeds the private channel bound".into(),
            ));
        }
        inspector.require_observations_local(main, application, end)?;
        Ok(value)
    }
}

impl NativeApplicationInspector {
    pub(crate) fn read_native_leaf_package_until(
        &self,
        main: &MainCustodyObservation,
        application: &ActualApplicationObservation,
        kind: NativeLeafPackageReadKind,
        end: Instant,
    ) -> Result<NativeLeafPackageReadObservation, ControlError> {
        self.require_observations_local(main, application, end)?;
        let command = kind.command(&application.facts().package);
        let literal = command.literal_arguments().map_err(ControlError::Invalid)?;
        let (request, reply, output) =
            self.execute_native_ui_observed_until(main, application, &literal, true, end)?;
        // A nonzero result remains the actual retired result. The consumer must
        // journal and reject it; this transport never invents empty output or a
        // successful application/identity fact.
        let peer = self.observation()?;
        let pidfd = self.pidfd.try_clone()
            .map_err(|e| io_error("retain fixed package observer peer", e))?;
        live(&pidfd).map_err(|e| io_error("check fixed package observer peer", e))?;
        self.require_observations_local(main, application, end)?;
        Ok(NativeLeafPackageReadObservation {
            kind, request, reply, output, peer, pidfd, observed_at: Instant::now(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_leaf_package_opcodes_cannot_choose_subject_uid_or_command() {
        for (opcode, expected) in [
            (b'I', NativeLeafPackageReadKind::Identity),
            (b'P', NativeLeafPackageReadKind::Paths),
            (b'L', NativeLeafPackageReadKind::Launcher),
        ] {
            assert_eq!(NativeLeafPackageReadKind::from_opcode(opcode), Some(expected));
            assert_eq!(expected.opcode(), opcode);
            let command = expected.command("com.android.contacts");
            let args = command.literal_arguments().unwrap();
            assert_eq!(args.last().unwrap(), "com.android.contacts");
            assert_eq!(command.guest_uid(), 2000);
        }
        // C belongs to the independently source-owned Calendar observer.
        for rejected in [0, b'G', b'E', b'C', b'U', b'D', b'B', b' ', 255] {
            assert!(NativeLeafPackageReadKind::from_opcode(rejected).is_none());
        }
    }
}
