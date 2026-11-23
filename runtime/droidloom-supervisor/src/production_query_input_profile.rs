//! Exact ordinary query members of the original CP3A system filesystem.
//! These pins identify inputs, not successful queries or application admission.

pub(crate) const INPUT_SCOPE: &str = "cp3a_fixed_application_query_inputs_v1";
pub(crate) const SYSTEM_BYTES: u64 = 2_294_853_632;
pub(crate) const SYSTEM_SHA256: &str =
    "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4";

#[derive(Clone, Copy, Debug)]
pub(crate) struct FixedQueryInput {
    pub(crate) source_path: &'static str,
    pub(crate) output_name: &'static str,
    pub(crate) bytes: u64,
    pub(crate) sha256: &'static str,
    pub(crate) original_mode: u32,
    pub(crate) original_gid: u32,
    pub(crate) original_label: &'static [u8],
    pub(crate) interpreter: Option<&'static str>,
}

impl FixedQueryInput {
    pub(crate) fn installed_mode(self) -> u32 {
        if self.interpreter.is_some() {
            0o555
        } else {
            0o444
        }
    }
}

// The three original executables are root:shell (0:2000), not root:root.
// New sealed input copies and private query projections have their own root
// ownership. That must never be substituted for the original image metadata.
pub(crate) const INPUTS: [FixedQueryInput; 4] = [
    FixedQueryInput {
        source_path: "/system/bin/cmd",
        output_name: "cmd-original",
        bytes: 52_160,
        sha256: "237410b6f4bfb9586a9a1135feaa4e75c189288483575890447aa5d492c56984",
        original_mode: 0o100755,
        original_gid: 2000,
        original_label: b"u:object_r:system_file:s0\0",
        interpreter: Some("/system/bin/linker64"),
    },
    FixedQueryInput {
        source_path: "/system/bin/toybox",
        output_name: "toybox-original",
        bytes: 611_248,
        sha256: "5c2b46686560564967fb5c1cb4ec633c42f658c347831c1d8c788ecf66e1774b",
        original_mode: 0o100755,
        original_gid: 2000,
        original_label: b"u:object_r:toolbox_exec:s0\0",
        interpreter: Some("/system/bin/linker64"),
    },
    FixedQueryInput {
        source_path: "/system/bin/app_process64",
        output_name: "contacts-app-process64-original",
        bytes: 51_616,
        sha256: "bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2",
        original_mode: 0o100755,
        original_gid: 2000,
        original_label: b"u:object_r:zygote_exec:s0\0",
        interpreter: Some("/system/bin/linker64"),
    },
    FixedQueryInput {
        source_path: "/system/framework/content.jar",
        output_name: "contacts-content-jar-original",
        bytes: 20_158,
        sha256: "c0ee6290243eda4a6dd95292c28274dd199b82b57466e00a83e1bb1a50eae8b3",
        original_mode: 0o100644,
        original_gid: 0,
        original_label: b"u:object_r:system_file:s0\0",
        interpreter: None,
    },
];
