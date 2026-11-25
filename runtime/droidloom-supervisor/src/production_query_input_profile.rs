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

// These additional original binaries are used only by the explicit kernel-first
// diagnostics declaration. Legacy runtimes retain the original four inputs.
pub(crate) const DIAGNOSTIC_INPUTS: [FixedQueryInput; 2] = [
    FixedQueryInput {
        source_path: "/system/bin/logcat",
        output_name: "diagnostics-logcat-original",
        bytes: 186_488,
        sha256: "73a4c21d53b9aac14fa07c7ea0bbf92dc56ac180b964d0d42179e0b093cd3203",
        original_mode: 0o100755,
        original_gid: 2000,
        original_label: b"u:object_r:logcat_exec:s0\0",
        interpreter: Some("/system/bin/linker64"),
    },
    FixedQueryInput {
        source_path: "/system/bin/dumpsys",
        output_name: "diagnostics-dumpsys-original",
        bytes: 68_848,
        sha256: "f2848aeb2dda2bc4fd4fe3d7867d1cdd30b7f36efe8f718f47a48b06dc810a2d",
        original_mode: 0o100755,
        original_gid: 2000,
        original_label: b"u:object_r:system_file:s0\0",
        interpreter: Some("/system/bin/linker64"),
    },
];
pub(crate) const ALL_INPUTS: [FixedQueryInput; 6] = [
    INPUTS[0],
    INPUTS[1],
    INPUTS[2],
    INPUTS[3],
    DIAGNOSTIC_INPUTS[0],
    DIAGNOSTIC_INPUTS[1],
];
pub(crate) fn selected_inputs(diagnostics: bool) -> &'static [FixedQueryInput] {
    if diagnostics { &ALL_INPUTS } else { &INPUTS }
}

// The normal producer reads this exact immutable map from the same system image.
// It is provenance for decoding; it is not a seventh executable/runtime input.
pub(crate) const EVENT_MAP_PATH: &str = "/system/etc/event-log-tags";
pub(crate) const EVENT_MAP_BYTES: u64 = 41_316;
pub(crate) const EVENT_MAP_SHA256: &str =
    "9bd293d01d01f257a93633d8f2e7cf6dcb812d1cfc7115ace85d8ebdad194091";
pub(crate) struct LifecycleEventTag {
    pub(crate) id: u32,
    pub(crate) name: &'static str,
    pub(crate) kinds: &'static [u8],
}
pub(crate) const LIFECYCLE_EVENT_TAGS: [LifecycleEventTag; 7] = [
    LifecycleEventTag {
        id: 30008,
        name: "am_anr",
        kinds: b"iisis",
    },
    LifecycleEventTag {
        id: 30010,
        name: "am_proc_bound",
        kinds: b"iis",
    },
    LifecycleEventTag {
        id: 30011,
        name: "am_proc_died",
        kinds: b"iisii",
    },
    LifecycleEventTag {
        id: 30014,
        name: "am_proc_start",
        kinds: b"iiisss",
    },
    LifecycleEventTag {
        id: 30023,
        name: "am_kill",
        kinds: b"iisisl",
    },
    LifecycleEventTag {
        id: 30035,
        name: "am_schedule_service_restart",
        kinds: b"isl",
    },
    LifecycleEventTag {
        id: 30039,
        name: "am_crash",
        kinds: b"iisisssii",
    },
];
