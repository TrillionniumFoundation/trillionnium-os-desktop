//! Exact native runtime members of the selected immutable CP3A inputs.
//! These pins are comparisons only. The live owner/helper must separately
//! prove the current Main, file bytes, readonly filesystem and actual VMAs.
use super::{EngineFile, NativeArtInput};
pub(crate) const EXECUTABLE_PATH: &str = "/system/bin/app_process64";
pub(crate) const EXECUTABLE_RELATIVE: &str = "system/bin/app_process64";
pub(crate) const ART_PATH: &str = "/apex/com.android.art/lib64/libart.so";
pub(crate) const ART_VERSIONED_PATH: &str = "/apex/com.android.art@371899999/lib64/libart.so";
pub(crate) const ART_RELATIVE: &str = "apex/com.android.art/lib64/libart.so";
pub(crate) const ART_BYTES: u64 = 14_884_360;
pub(crate) const ART_SHA256: &str =
    "38849876d2101a7bac548d3438e3effff01e38f13f3b5740a2364b762fc229d3";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum NativeFileKind {
    Executable,
    Art,
}
impl NativeFileKind {
    pub(crate) fn paths(self) -> &'static [&'static str] {
        match self {
            Self::Executable => &[EXECUTABLE_PATH],
            Self::Art => &[ART_PATH, ART_VERSIONED_PATH],
        }
    }
    pub(crate) fn basename(self) -> &'static [u8] {
        match self {
            Self::Executable => b"app_process64",
            Self::Art => b"libart.so",
        }
    }
    pub(crate) fn expected(self) -> (u64, &'static str, u32, u32, u32) {
        match self {
            Self::Executable => {
                let row = crate::production_execution_profile::query_inputs::INPUTS[2];
                (
                    row.bytes,
                    row.sha256,
                    row.original_mode,
                    0,
                    row.original_gid,
                )
            }
            Self::Art => (ART_BYTES, ART_SHA256, 0o100644, 1000, 1000),
        }
    }
    pub(crate) fn validate(self, file: &EngineFile) -> bool {
        let (bytes, sha256, mode, uid, gid) = self.expected();
        let n = &file.identity;
        n.device > 0
            && n.inode > 0
            && n.mode == mode
            && n.uid == uid
            && n.gid == gid
            && n.links == 1
            && n.bytes == bytes
            && file.sha256 == sha256
    }
}
pub(crate) fn art_input() -> Result<NativeArtInput, &'static str> {
    let query = crate::production_execution_profile::query_inputs::INPUTS[2];
    if query.source_path != EXECUTABLE_PATH
        || query.bytes != 51_616
        || query.sha256 != "bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2"
        || query.original_mode != 0o100755
        || query.original_gid != 2000
        || query.original_label != b"u:object_r:zygote_exec:s0\0"
    {
        return Err("selected original app_process64 source differs");
    }
    let fixed = crate::production_execution_profile::apex_inputs::original_inputs()?
        .into_iter()
        .find(|row| row.input.name == "com.android.art")
        .ok_or("selected original ART input absent")?;
    let a = fixed.input;
    if fixed.filesystem != crate::production_execution_profile::apex_inputs::PayloadFilesystem::Ext4
        || a.version != 371_899_999
        || a.container_file != "com.android.art.capex"
        || a.container_bytes != 20_357_120
        || a.container_sha256 != "5d0e18b7e2ff241989323c1d0d1695c97921ba85b617ba12e5aa69775b7bd5c0"
        || a.original_apex_bytes != 49_065_984
        || a.original_apex_sha256
            != "5ace9ff8a8ab73aa64b63901fe18782028d5c61c452a35b8ad07fb0b711247d0"
        || a.payload_bytes != 48_865_280
        || a.payload_sha256 != "8dd4693cf110e6d69fdd34868c337cd94e4251151466b799d95762c7bf150bb4"
    {
        return Err("selected original ART source differs");
    }
    Ok(NativeArtInput {
        name: a.name,
        version: a.version,
        container_bytes: a.container_bytes,
        container_sha256: a.container_sha256,
        original_apex_bytes: a.original_apex_bytes,
        original_apex_sha256: a.original_apex_sha256,
        payload_bytes: a.payload_bytes,
        payload_sha256: a.payload_sha256,
        member_path: "/lib64/libart.so".into(),
        member_bytes: ART_BYTES,
        member_sha256: ART_SHA256.into(),
    })
}
