//! One committed Ubuntu PID 1 identity shared by the host producer and fixture.
use serde::{Deserialize, Serialize};

const BOARD_INPUTS: &[u8] = include_bytes!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);

/// The exact ELF and normal Debian package selected for the native manager.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeInit {
    pub path: String,
    pub size: u64,
    pub sha256: String,
    pub package_name: String,
    pub package_version: String,
    pub package_architecture: String,
    pub package_bytes: u64,
    pub package_sha256: String,
}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl NativeInit {
    /// Validate the fixed path and bounded, single-package identity.
    pub fn validate(&self) -> Result<(), String> {
        if self.path != "/usr/lib/systemd/systemd"
            || self.package_name != "systemd"
            || self.package_architecture != "amd64"
            || self.size == 0
            || self.size > 64 * 1024 * 1024
            || !digest(&self.sha256)
            || self.package_bytes == 0
            || self.package_bytes > 128 * 1024 * 1024
            || !digest(&self.package_sha256)
            || self.package_version.is_empty()
            || self.package_version.len() > 96
            || !self
                .package_version
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b".+:~-".contains(&b))
        {
            return Err("invalid committed native Ubuntu manager identity".into());
        }
        Ok(())
    }

    /// C initializer derived from the same digest; no second pin is maintained.
    pub fn sha256_c_initializer(&self) -> Result<String, String> {
        self.validate()?;
        let bytes = self
            .sha256
            .as_bytes()
            .chunks_exact(2)
            .map(|pair| format!("0x{}{}", char::from(pair[0]), char::from(pair[1])))
            .collect::<Vec<_>>()
            .join(", ");
        Ok(format!("{{{bytes}}}"))
    }
}

/// Read the one manager selected by the committed board input, not a caller list.
pub fn selected() -> Result<NativeInit, String> {
    #[derive(Deserialize)]
    struct Board {
        schema: String,
        native_init: NativeInit,
    }
    let board: Board = serde_json::from_slice(BOARD_INPUTS).map_err(|e| e.to_string())?;
    if board.schema != "droidloom-pocket4-joint-initramfs-inputs-v1" {
        return Err("unsupported committed board input".into());
    }
    board.native_init.validate()?;
    Ok(board.native_init)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn committed_native_init_has_one_exact_path_and_derived_c_bytes() {
        let selected = selected().unwrap();
        let c = selected.sha256_c_initializer().unwrap();
        let decoded = c
            .trim_matches(['{', '}'])
            .split(", ")
            .map(|s| u8::from_str_radix(s.trim_start_matches("0x"), 16).unwrap())
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        assert_eq!(decoded, selected.sha256);
        for (path, name, arch, version, size, sha) in [
            ("/usr/bin/other", "systemd", "amd64", "1", 1, "a".repeat(64)),
            (
                "/usr/lib/systemd/systemd",
                "other",
                "amd64",
                "1",
                1,
                "a".repeat(64),
            ),
            (
                "/usr/lib/systemd/systemd",
                "systemd",
                "arm64",
                "1",
                1,
                "a".repeat(64),
            ),
            (
                "/usr/lib/systemd/systemd",
                "systemd",
                "amd64",
                "../1",
                1,
                "a".repeat(64),
            ),
            (
                "/usr/lib/systemd/systemd",
                "systemd",
                "amd64",
                "1",
                0,
                "a".repeat(64),
            ),
            (
                "/usr/lib/systemd/systemd",
                "systemd",
                "amd64",
                "1",
                1,
                "A".repeat(64),
            ),
        ] {
            let mut bad = selected.clone();
            bad.path = path.into();
            bad.package_name = name.into();
            bad.package_architecture = arch.into();
            bad.package_version = version.into();
            bad.size = size;
            bad.sha256 = sha;
            assert!(bad.validate().is_err());
        }
    }
}
