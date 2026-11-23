//! Fixed original CP3A linkerconfig bytes and the reproducibly built helper.
//! These pins select input code; they are never evidence of actual activation.

pub(crate) const INPUT_SCOPE: &str = "cp3a_original_linkerconfig_inputs_v1";
pub(crate) const ORIGINAL_SOURCE_PATH: &str = "/apex/com.android.runtime/bin/linkerconfig";
pub(crate) const ORIGINAL_IMAGE_PATH: &str = "/bin/linkerconfig";
pub(crate) const ORIGINAL_INTERPRETER: &str = "/system/bin/linker64";
pub(crate) const ORIGINAL_BYTES: u64 = 512_120;
pub(crate) const ORIGINAL_SHA256: &str =
    "40105456e35de393c382d5ec9794a2cd30370291a0502e58bb24d6ae2b417ede";
pub(crate) const RUNTIME_PAYLOAD_BYTES: u64 = 11_452_416;
pub(crate) const RUNTIME_PAYLOAD_SHA256: &str =
    "f97a0b03fb4b5dc91ddc71b02fc1f9831749d4a2e3f7cd6db47e3378f31a6345";
pub(crate) const TRAMPOLINE_BYTES: u64 = 24_384;
pub(crate) const TRAMPOLINE_SHA256: &str =
    "71ea5a2f70f4674ff2028dcdfe2ca6ee0d5ab1968ec21c5a3b0ee7be4d555e70";
pub(crate) const TRAMPOLINE_SOURCE_SHA256: &str =
    "d9368ae085d216091e2228a01206309b4e58022087115001a3744fb2f0a51e15";
pub(crate) const PROTOCOL_SOURCE_SHA256: &str =
    "75a6c01c9e7f482df64931f23c0219251312fa2afe15fd2e055a72ac196f9db3";
pub(crate) const RUST_CHANNEL_SHA256: &str =
    "beb6ba4e41c84e9c11c80e6804a007497d0c8ba0810cd403fabc8f4a9c45b1f8";
