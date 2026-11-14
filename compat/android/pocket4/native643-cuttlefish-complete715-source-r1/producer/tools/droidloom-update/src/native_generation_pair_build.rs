//! One explicit build-only route for the complete ordinary-app generation pair.
//! The old ART-library and disabled framework commands retain their scopes.
//! This records actual engine/APEX pairing; it neither installs nor grants a
//! private AppZygote role, and it does not replace Android runtime qualification.
use crate::util::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

pub const TARGETS: &[&str] = &["libberberis_arm64", "com.android.art"];
const ENGINE: &str = "frameworks/libs/binary_translation";
const INPUTS: &str = "android/native-generation-pair";
const ENGINE_HEAD: &str = "a9496d886a85752ba407b76509952c06cd79ddb8";
const ENGINE_FILES_SHA: &str = "6633fee76068fa421d5cfd3fd6f3d2440b2fa8d04b92223a1b1b9e7f9eba4139";
const ENGINE_FILES_BYTES: usize = 110809;
const ENGINE_BP_SHA: &str = "bfd8ee63943b331ff09c67879065f9794bae7c7b897ba049961cbe47cd2d97e7";
const ENGINE_BP_BYTES: usize = 25403;
const BASE_SOURCE_LOCK_SHA: &str = "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d";
const PAIR_SOURCE_LOCK: &str = "android/native-generation-pair/source-lock.json";
const SOURCE_LOCK_BYTES: usize = 369279;
const SOURCE_LOCK_SHA: &str = "e4bc640833bbdee16a1e84bd8314cc81c44351e4b03c03e6439bc31318d0a5bf";
// Exact original additions from frozen manifest SHA-256 d88549bc89076017baffcc28e39695431993cc12516238278e015f23325d9596.
// Closure qualification remains separate from this source attestation.
const PAIR_ADDITIONS_JSON: &str = r#"[
  {
    "commit": "6e219320253dcd5c0a6f19b2785f1d37bc8edcf0",
    "name": "platform/external/kotlinx.serialization",
    "path": "external/kotlinx.serialization",
    "purpose": "Exact Android 17 serialization implementation required by the real AndroidX savedstate and lifecycle libraries",
    "sparse_paths": [
      "core",
      "formats/json",
      "rules"
    ]
  },
  {
    "commit": "d678d8ab3fb3602f46f33801190df2abb4eaca39",
    "name": "platform/prebuilts/module_sdk/SdkExtensions",
    "path": "prebuilts/module_sdk/SdkExtensions",
    "purpose": "Exact Android 17 official SDK snapshot providing framework-sdkextensions stubs required by AndroidX core",
    "sparse_paths": [
      "current"
    ]
  },
  {
    "commit": "4d155d6c08932904384ba2f5198dcc984e32501b",
    "name": "platform/sdk",
    "path": "sdk",
    "purpose": "Exact Android 17 original android.annotation.SuppressLint provider required by the coroutine host implementation",
    "sparse_paths": [
      "annotations"
    ]
  },
  {
    "commit": "e6ad60074cdb730af563c2d1553f472dc6115bf5",
    "name": "platform/external/FP16",
    "path": "external/FP16",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "include",
      "test"
    ]
  },
  {
    "commit": "45acb237cd13c19708f963247c732250cd43a4a5",
    "name": "platform/external/XMP-Toolkit-SDK",
    "path": "external/XMP-Toolkit-SDK",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "XMPCore",
      "XMPFiles",
      "XMPFilesPlugins",
      "public",
      "source",
      "third-party",
      "XMPCommon",
      "build",
      "samples"
    ]
  },
  {
    "commit": "79791945c2f1db4a6b2a1443524f3f5d19338609",
    "name": "platform/external/bcc",
    "path": "external/bcc",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "src",
      "examples/cpp",
      "examples/usdt_sample",
      "libbpf-tools",
      "tests/cc",
      "tests/python"
    ]
  },
  {
    "commit": "a927860e79169483cd0ae4f8ad52937bd2c6d377",
    "name": "platform/external/brotli",
    "path": "external/brotli",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "c",
      "java",
      "research"
    ]
  },
  {
    "commit": "ec47c0df8cf593f6a4c1708bf87100e70d433daa",
    "name": "platform/external/dng_sdk",
    "path": "external/dng_sdk",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "source",
      "ubsan-replacement"
    ]
  },
  {
    "commit": "fa0ad63f8b666836f56a823de546390a6e4ff4b6",
    "name": "platform/external/fft2d",
    "path": "external/fft2d",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "src"
    ]
  },
  {
    "commit": "358ad23f2a144ad0f43b0300a252f692a191de1b",
    "name": "platform/external/freetype",
    "path": "external/freetype",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "builds",
      "docs",
      "include",
      "src",
      "devel",
      "devel-teeui"
    ]
  },
  {
    "commit": "9fc55623d7fec25b699eab680041798de98f5c86",
    "name": "platform/external/giflib",
    "path": "external/giflib",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "31e11a7283dce4ffc573fc8d249b3483988f8bde",
    "name": "platform/external/harfbuzz_ng",
    "path": "external/harfbuzz_ng",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "perf",
      "src",
      "test",
      "util"
    ]
  },
  {
    "commit": "581886c43a33d47101cae26c447ed7be07a8b626",
    "name": "platform/external/image_io",
    "path": "external/image_io",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "includes",
      "src"
    ]
  },
  {
    "commit": "8ec969cea971fe25ff2d3933a5a9f8504f8e86c9",
    "name": "platform/external/libgsm",
    "path": "external/libgsm",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "inc",
      "src",
      "tls"
    ]
  },
  {
    "commit": "90930aa281c8655a54fffafb9d16714c74c650a5",
    "name": "platform/external/libjxl",
    "path": "external/libjxl",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "gen",
      "lib",
      "plugins",
      "third_party",
      "tools/args.h",
      "tools/benchmark/benchmark_args.h",
      "tools/benchmark/benchmark_codec.h",
      "tools/benchmark/benchmark_codec_avif.h",
      "tools/benchmark/benchmark_codec_custom.h",
      "tools/benchmark/benchmark_codec_jpeg.h",
      "tools/benchmark/benchmark_codec_jxl.h",
      "tools/benchmark/benchmark_codec_png.h",
      "tools/benchmark/benchmark_codec_webp.h",
      "tools/benchmark/benchmark_file_io.h",
      "tools/benchmark/benchmark_stats.h",
      "tools/benchmark/benchmark_utils.h",
      "tools/cmdline.h",
      "tools/codec_config.h",
      "tools/comparison_viewer",
      "tools/fast_lossless",
      "tools/file_io.h",
      "tools/flicker_test",
      "tools/gauss_blur.h",
      "tools/hdr",
      "tools/icc_detect",
      "tools/jni",
      "tools/no_memory_manager.h",
      "tools/speed_stats.h",
      "tools/ssimulacra.h",
      "tools/ssimulacra2.h",
      "tools/thread_pool_internal.h",
      "tools/tool_version.h",
      "tools/tracking_memory_manager.h",
      "tools/viewer",
      "tools/wasm_demo"
    ]
  },
  {
    "commit": "f3997b4b299d808f122ab1d999556d57abf5540d",
    "name": "platform/external/libpng",
    "path": "external/libpng",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "arm",
      "contrib",
      "intel",
      "scripts"
    ]
  },
  {
    "commit": "4a5906659019f5b73b211759d0bfca0375fc6300",
    "name": "platform/external/libultrahdr",
    "path": "external/libultrahdr",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "lib",
      "adobe-hdr-gain-map-license",
      "java",
      "third_party"
    ]
  },
  {
    "commit": "95f225c116d2ce3f099277bbdb2dad3afc7d9050",
    "name": "platform/external/nist-sip",
    "path": "external/nist-sip",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "java",
      "licenses"
    ]
  },
  {
    "commit": "aac15c2e18a72f66df14f08b93492fd0c493aa77",
    "name": "platform/external/pdfium",
    "path": "external/pdfium",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "constants",
      "core/fdrm",
      "core/fpdfapi/cmaps",
      "core/fpdfapi/edit",
      "core/fpdfapi/font",
      "core/fpdfapi/page",
      "core/fpdfapi/parser",
      "core/fpdfapi/render",
      "core/fpdfdoc",
      "core/fpdftext",
      "core/fxcodec",
      "core/fxcrt",
      "core/fxge",
      "fpdfsdk",
      "fxjs",
      "public",
      "third_party",
      "build",
      "fxbarcode",
      "skia",
      "testing",
      "xfa"
    ]
  },
  {
    "commit": "ece66975738007dd0978b911d8a2077e49b8f31e",
    "name": "platform/external/perfetto",
    "path": "external/perfetto",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "include",
      "protos",
      "python",
      "src",
      "test",
      "tools",
      "buildtools",
      "contrib/rust-sdk/perfetto-sys",
      "examples"
    ]
  },
  {
    "commit": "c7c1d44ab9b98e9e51baf1e5d02f65ba03fbed28",
    "name": "platform/external/piex",
    "path": "external/piex",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "src"
    ]
  },
  {
    "commit": "db5cb0db8513b2598ae7c1fa8a6441ff7f8808b5",
    "name": "platform/external/pigweed",
    "path": "external/pigweed",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "pw_allocator",
      "pw_assert",
      "pw_assert_log",
      "pw_base64",
      "pw_build_android",
      "pw_bytes",
      "pw_chrono",
      "pw_chrono_stl",
      "pw_containers",
      "pw_function",
      "pw_log",
      "pw_log_android",
      "pw_log_tokenized",
      "pw_memory",
      "pw_metric",
      "pw_numeric",
      "pw_polyfill",
      "pw_preprocessor",
      "pw_result",
      "pw_span",
      "pw_status",
      "pw_stream",
      "pw_string",
      "pw_sync",
      "pw_sync_stl",
      "pw_thread",
      "pw_thread_stl",
      "pw_tokenizer",
      "pw_toolchain",
      "pw_varint",
      "third_party/Android.bp",
      "third_party/fuchsia/repo/sdk/lib/fit/include",
      "third_party/fuchsia/repo/sdk/lib/stdcompat/include",
      "pw_elf",
      "pw_protobuf",
      "pw_protobuf_compiler",
      "pw_rpc",
      "pw_sync_baremetal",
      "pw_async2",
      "pw_bluetooth",
      "pw_bluetooth_proxy",
      "pw_checksum",
      "pw_intrusive_ptr",
      "pw_multibuf",
      "third_party"
    ]
  },
  {
    "commit": "1b18ee77492041f7f0a7063ad8e02b5694aa6683",
    "name": "platform/external/regex-re2",
    "path": "external/regex-re2",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "re2",
      "util"
    ]
  },
  {
    "commit": "c718caf5bc658d3f806a442666800781c66a5274",
    "name": "platform/external/rust/crabbyavif",
    "path": "external/rust/crabbyavif",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "include",
      "src",
      "sys",
      "c_api_tests"
    ]
  },
  {
    "commit": "c165d6b0f1a1be9ddd2f904e8f87a4c1d9b38c43",
    "name": "platform/external/ruy",
    "path": "external/ruy",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "ruy"
    ]
  },
  {
    "commit": "958140511cebc42a79e9eec852a4f7dfa2bd2755",
    "name": "platform/external/scrypt",
    "path": "external/scrypt",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "lib",
      "sources.bp",
      "tests"
    ]
  },
  {
    "commit": "d6bfb0bfab3e7565df0be176c3ebaa45ff9000ec",
    "name": "platform/external/tensorflow",
    "path": "external/tensorflow",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "tensorflow",
      "third_party"
    ]
  },
  {
    "commit": "e39d7f63945d02f6e2f8262f57e74a38172e72fd",
    "name": "platform/external/webp",
    "path": "external/webp",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "sharpyuv",
      "src",
      "cmake",
      "examples",
      "extras",
      "imageio",
      "tests"
    ]
  },
  {
    "commit": "11c7df296d76dc00991111c1aebd9dfb48b8812e",
    "name": "platform/external/wuffs-mirror-release-c",
    "path": "external/wuffs-mirror-release-c",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "release"
    ]
  },
  {
    "commit": "915f1232cff2f38be1ed2273769c5ffd00928dff",
    "name": "platform/frameworks/minikin",
    "path": "frameworks/minikin",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "app",
      "include",
      "libs",
      "rust",
      "tests"
    ]
  },
  {
    "commit": "314c843f3627f936c46c9e6d61cb30017bd71fd3",
    "name": "platform/frameworks/opt/net/ims",
    "path": "frameworks/opt/net/ims",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "src",
      "tests"
    ]
  },
  {
    "commit": "cf87c6f8a075fc7544a7e3bae57f992c1db243ff",
    "name": "platform/frameworks/opt/net/voip",
    "path": "frameworks/opt/net/voip",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "src"
    ]
  },
  {
    "commit": "aef289516bea6118d88cd45c63742cd4abe2c596",
    "name": "platform/frameworks/opt/telephony",
    "path": "frameworks/opt/telephony",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "flags",
      "proto",
      "src",
      "testing",
      "tests"
    ]
  },
  {
    "commit": "d55c713a4867986bb8f0ae322207d6e8c35355a1",
    "name": "platform/packages/modules/CellBroadcastService",
    "path": "packages/modules/CellBroadcastService",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "res",
      "src",
      "sysconfig",
      "tests"
    ]
  },
  {
    "commit": "02451209cebd4648fd54ad3757f1a85ee9cd628b",
    "name": "platform/packages/modules/CrashRecovery",
    "path": "packages/modules/CrashRecovery",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "flags",
      "framework/Android.bp",
      "framework/api",
      "framework/java",
      "service/Android.bp",
      "service/api",
      "service/java",
      "apex"
    ]
  },
  {
    "commit": "7c9e03046ff41cc28cf794cc2eda306fbc40279e",
    "name": "platform/packages/modules/Uwb",
    "path": "packages/modules/Uwb",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "ranging/flags",
      "apex",
      "flags",
      "framework/Android.bp",
      "framework/api",
      "framework/jarjar-rules.txt",
      "framework/java",
      "framework/lint-baseline.xml",
      "libuwb-uci",
      "ranging/framework/Android.bp",
      "ranging/framework/api",
      "ranging/framework/jarjar-rules.txt",
      "ranging/framework/java",
      "ranging/framework/lint-baseline.xml",
      "service/Android.bp",
      "service/ServiceUwbResources",
      "service/fusion_lib/Android.bp",
      "service/fusion_lib/src",
      "service/java",
      "service/multichip-parser",
      "service/proguard.flags",
      "service/proto",
      "service/support_lib/Android.bp",
      "service/support_lib/lint-baseline.xml",
      "service/support_lib/lint-baseline2.xml",
      "service/support_lib/src",
      "service/uci",
      "tests/cts/hostsidetests",
      "androidx_backend",
      "ranging/rtt_backend",
      "ranging/service",
      "ranging/tests/multidevices/snippet/bluetooth",
      "ranging/uwb_backend"
    ]
  },
  {
    "commit": "4a3830d926a5a84a6f5f7aab8d27e245e7880a68",
    "name": "platform/packages/services/Telephony",
    "path": "packages/services/Telephony",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "ecc/conversion_toolset_v1/proto",
      "assets",
      "ecc",
      "res",
      "src",
      "testapps/TestRcsApp/aosp_test_rcsclient",
      "tests",
      "utils/satellite/s2storage"
    ]
  },
  {
    "commit": "17b4a35a8c2b9f27e7f1b382b7d714aced928ce4",
    "name": "platform/system/chre",
    "path": "system/chre",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "apps",
      "chre_api",
      "core",
      "data_flow",
      "external",
      "host",
      "pal",
      "platform",
      "test",
      "util",
      "variant",
      "api_parser",
      "chpp/include",
      "chpp/include_public",
      "chpp/platform",
      "chpp/test/app_test_base.h",
      "chpp/test/app_timeout_test.h",
      "chpp/test/fake_link.h",
      "chpp/test/fake_link_client.h",
      "chpp/test/include",
      "chpp/test/message_service_test.h",
      "chpp/test/packet_util.h",
      "chpp/test/transport_test.h",
      "chpp/test/transport_util.h",
      "java/chre_ap",
      "java/test/chdts/app",
      "std_overrides",
      "java/test/audio_concurrency",
      "java/test/ble_concurrency",
      "java/test/chqts",
      "java/test/chre_concurrency",
      "java/test/cross_validation",
      "java/test/endpoint",
      "java/test/permissions",
      "java/test/rpc_service",
      "java/test/settings",
      "java/test/stress",
      "java/test/utils",
      "java/utils/pigweed",
      "java/test/chdts"
    ]
  },
  {
    "commit": "6b853f9e5703a8c90648f82850a3a01d9763e619",
    "name": "platform/system/incremental_delivery",
    "path": "system/incremental_delivery",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "incfs",
      "libdataloader",
      "sysprop"
    ]
  },
  {
    "commit": "2f9196be89b3851049b565b6c338f707e50440ba",
    "name": "platform/system/memory/libion",
    "path": "system/memory/libion",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "include",
      "kernel-headers",
      "original-kernel-headers"
    ]
  },
  {
    "commit": "25ee95c80f9be933f4d0a2f399db1b98195f384d",
    "name": "platform/system/memory/libmemtrack",
    "path": "system/memory/libmemtrack",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "Android.bp",
      "include"
    ]
  },
  {
    "commit": "c24023080df0bdb5988c1e0c641d494574a97c40",
    "name": "platform/system/zygote",
    "path": "system/zygote",
    "purpose": "Exact Android 17 original providers required by the ordinary engine and complete ART APEX source dependency closure",
    "sparse_paths": [
      "zygote-messages",
      "zygote-proc-macros",
      "zygote-sys"
    ]
  },
  {
    "commit": "11c0a81eb894486d883f0543b23d0cdab9f9d5ec",
    "name": "platform/external/nanopb-c",
    "path": "external/nanopb-c",
    "purpose": "Exact Android 17 original nanopb generator and C runtime required by the retained Pigweed RPC Blueprint siblings",
    "sparse_paths": [
      "Android.bp",
      "generator",
      "examples",
      "extra",
      "spm_headers",
      "tests"
    ]
  },
  {
    "commit": "080f671785c84ae1ac38797fe1fa7364d158fab4",
    "name": "platform/bootable/recovery",
    "path": "bootable/recovery",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bootloader_message",
      "etc",
      "fastboot",
      "fuse_sideload",
      "install",
      "minadbd",
      "minui",
      "otautil",
      "recovery_ui",
      "recovery_utils",
      "res-hdpi",
      "res-mdpi",
      "res-xhdpi",
      "res-xxhdpi",
      "res-xxxhdpi",
      "tests/Android.bp",
      "tests/common",
      "tests/fuzz",
      "tests/manual",
      "tests/testdata",
      "tests/unit",
      "update_verifier"
    ]
  },
  {
    "commit": "5013071e756f89aa2cea97b437af12aacb8d4485",
    "name": "platform/dalvik",
    "path": "dalvik",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "dx/Android.bp",
      "dx/NOTICE",
      "dx/etc",
      "dx/src",
      "tools/dexdeps",
      "tools/hprof-conv"
    ]
  },
  {
    "commit": "4dafd114fab3c3d9543a5aff0ad097f479915176",
    "name": "platform/development",
    "path": "development",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apps/Development",
      "apps/GestureBuilder",
      "apps/WidgetPreview",
      "build",
      "docs",
      "host",
      "python-packages",
      "samples/AccelerometerPlay",
      "samples/AconfigDemo/Android.bp",
      "samples/AconfigDemo/AndroidManifest.xml",
      "samples/AconfigDemo/aconfig_demo_flags.aconfig",
      "samples/AconfigDemo/lib",
      "samples/AconfigDemo/proguard.flags",
      "samples/AconfigDemo/res",
      "samples/AconfigDemo/src",
      "samples/ApiDemos",
      "samples/AppNavigation",
      "samples/BackupRestore",
      "samples/BasicGLSurfaceView",
      "samples/BusinessCard",
      "samples/ContactManager",
      "samples/CrossCompatibility",
      "samples/CubeLiveWallpaper",
      "samples/HelloEffects",
      "samples/Home",
      "samples/HoneycombGallery",
      "samples/JetBoy",
      "samples/KeyChainDemo",
      "samples/LceDemo",
      "samples/LunarLander",
      "samples/MultiResolution",
      "samples/NotePad",
      "samples/SampleSyncAdapter",
      "samples/SceneTransitionLayoutDemo/Android.bp",
      "samples/SceneTransitionLayoutDemo/AndroidManifest.xml",
      "samples/SceneTransitionLayoutDemo/app",
      "samples/SceneTransitionLayoutDemo/res",
      "samples/SceneTransitionLayoutDemo/src",
      "samples/SearchableDictionary",
      "samples/SipDemo",
      "samples/SkeletonApp",
      "samples/Snake",
      "samples/SoftKeyboard",
      "samples/SpellChecker",
      "samples/Spinner",
      "samples/SpinnerTest",
      "samples/TicTacToeLib",
      "samples/TicTacToeMain",
      "samples/ToyVpn",
      "samples/TtsEngine",
      "samples/USB",
      "samples/UiAutomator",
      "samples/VoiceRecognitionService",
      "samples/VoicemailProviderDemo",
      "samples/WeatherListWidget",
      "samples/WiFiDirectDemo",
      "samples/WiFiDirectServiceDiscovery",
      "samples/Wiktionary",
      "samples/WiktionarySimple",
      "samples/XmlAdapters",
      "samples/samples_source.prop_template",
      "scripts",
      "sdk",
      "tools/etc1tool"
    ]
  },
  {
    "commit": "296e55aa0244e8929e393e00e34471fef2a5d662",
    "name": "device/generic/goldfish",
    "path": "device/generic/goldfish",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "build/tools"
    ]
  },
  {
    "commit": "d890e0a3dd30d5e26280b1e340d8dd7b6164612c",
    "name": "device/generic/trusty",
    "path": "device/generic/trusty",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "283645aacf6cdb56cc31a9362f54d412dbc132a1",
    "name": "device/google/cuttlefish",
    "path": "device/google/cuttlefish",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex/keys",
      "common",
      "guest/commands/bt_vhci_forwarder",
      "guest/commands/v4l2_streamer",
      "guest/commands/vkms_controller",
      "guest/hals/camera",
      "guest/hals/confirmationui",
      "guest/hals/gatekeeper",
      "guest/hals/identity",
      "guest/hals/keymint/remote",
      "guest/hals/oemlock",
      "guest/hals/secure_element",
      "guest/libs",
      "host/commands/assemble_cvd",
      "host/commands/casimir_control_server",
      "host/commands/control_env_proxy_server",
      "host/commands/cvd_send_id_disclosure",
      "host/commands/cvd_send_sms",
      "host/commands/cvd_update_security_algorithm",
      "host/commands/echo_server",
      "host/commands/gnss_grpc_proxy",
      "host/commands/kernel_log_monitor",
      "host/commands/metrics",
      "host/commands/modem_simulator",
      "host/commands/openwrt_control_server",
      "host/commands/process_restarter",
      "host/commands/process_sandboxer",
      "host/commands/run_cvd",
      "host/commands/screen_recording_server",
      "host/commands/secure_env",
      "host/commands/sensors_simulator",
      "host/commands/snapshot_util_cvd",
      "host/commands/start",
      "host/commands/vhal_proxy_server/Android.bp",
      "host/commands/vhal_proxy_server/vhal_proxy_server.cpp",
      "host/commands/vhal_proxy_server/vsockinfo.h",
      "host/frontend/adb_connector",
      "host/frontend/webrtc/Android.bp",
      "host/frontend/webrtc/adb_handler.cpp",
      "host/frontend/webrtc/adb_handler.h",
      "host/frontend/webrtc/audio_handler.cpp",
      "host/frontend/webrtc/audio_handler.h",
      "host/frontend/webrtc/audio_mixer.cpp",
      "host/frontend/webrtc/audio_mixer.h",
      "host/frontend/webrtc/audio_settings.h",
      "host/frontend/webrtc/bluetooth_handler.cpp",
      "host/frontend/webrtc/bluetooth_handler.h",
      "host/frontend/webrtc/client_server.cpp",
      "host/frontend/webrtc/client_server.h",
      "host/frontend/webrtc/connection_observer.cpp",
      "host/frontend/webrtc/connection_observer.h",
      "host/frontend/webrtc/cvd_video_frame_buffer.cpp",
      "host/frontend/webrtc/cvd_video_frame_buffer.h",
      "host/frontend/webrtc/display_handler.cpp",
      "host/frontend/webrtc/display_handler.h",
      "host/frontend/webrtc/gpx_locations_handler.cpp",
      "host/frontend/webrtc/gpx_locations_handler.h",
      "host/frontend/webrtc/kernel_log_events_handler.cpp",
      "host/frontend/webrtc/kernel_log_events_handler.h",
      "host/frontend/webrtc/kml_locations_handler.cpp",
      "host/frontend/webrtc/kml_locations_handler.h",
      "host/frontend/webrtc/libcommon",
      "host/frontend/webrtc/libdevice",
      "host/frontend/webrtc/location_handler.cpp",
      "host/frontend/webrtc/location_handler.h",
      "host/frontend/webrtc/main.cpp",
      "host/frontend/webrtc/screenshot_handler.cpp",
      "host/frontend/webrtc/screenshot_handler.h",
      "host/frontend/webrtc/sensors_handler.cpp",
      "host/frontend/webrtc/sensors_handler.h",
      "host/frontend/webrtc/webrtc_command_channel.cpp",
      "host/frontend/webrtc/webrtc_command_channel.h",
      "host/frontend/webrtc/webrtc_commands.proto",
      "host/frontend/webrtc_operator",
      "host/libs",
      "shared/minidroid",
      "tests/graphics/Android.bp",
      "tests/graphics/src",
      "tests/graphics/vulkan",
      "tests/ril",
      "tests/src",
      "tests/tombstone-transmit-tests.xml",
      "tests/utils",
      "tests/wifi"
    ]
  },
  {
    "commit": "035858697891c2e1079255ef33656663618037a1",
    "name": "device/sample",
    "path": "device/sample",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "etc"
    ]
  },
  {
    "commit": "560f529230274a871c00993a42740e7515a645af",
    "name": "platform/external/FXdiv",
    "path": "external/FXdiv",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "test"
    ]
  },
  {
    "commit": "cdaa76f6e0cc1f4dc0e1174d8497f9694c794a32",
    "name": "platform/external/MPAndroidChart",
    "path": "external/MPAndroidChart",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "MPChartLib"
    ]
  },
  {
    "commit": "b75c2e2a9e7db7557cf66f9b33d66e9d3b1ed501",
    "name": "platform/external/XNNPACK",
    "path": "external/XNNPACK",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bench",
      "include",
      "models",
      "src",
      "test"
    ]
  },
  {
    "commit": "41f344ffc0bacea87cac5bb1756bd40761265d1e",
    "name": "platform/external/aac",
    "path": "external/aac",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "cpp/Android.bp",
      "cpp/libAACdec",
      "cpp/libAACenc",
      "cpp/libArithCoding",
      "cpp/libDRCdec",
      "cpp/libFDK",
      "cpp/libMpegTPDec",
      "cpp/libMpegTPEnc",
      "cpp/libPCMutils",
      "cpp/libSACdec",
      "cpp/libSACenc",
      "cpp/libSBRdec",
      "cpp/libSBRenc",
      "cpp/libSYS",
      "rust",
      "xhe-aac"
    ]
  },
  {
    "commit": "c56129fcdf507265b54b7c0c9247aceb3a4c7478",
    "name": "platform/external/accessibility-test-framework",
    "path": "external/accessibility-test-framework",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src",
      "tests"
    ]
  },
  {
    "commit": "12a35b34784196d729e27f05e2ba9de7fa8fdb44",
    "name": "platform/external/android_onboarding",
    "path": "external/android_onboarding",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "java/com/android/onboarding/common",
      "java/com/android/onboarding/compatibility",
      "java/com/android/onboarding/contracts/ActivityLauncher.kt",
      "java/com/android/onboarding/contracts/Android.bp",
      "java/com/android/onboarding/contracts/ArgumentFreeOnboardingActivityApiContract.kt",
      "java/com/android/onboarding/contracts/ArgumentFreeVoidOnboardingActivityApiContract.kt",
      "java/com/android/onboarding/contracts/ArgumentValidator.kt",
      "java/com/android/onboarding/contracts/AttachedResult.kt",
      "java/com/android/onboarding/contracts/ContractResult.kt",
      "java/com/android/onboarding/contracts/DefaultActivityLauncher.kt",
      "java/com/android/onboarding/contracts/ExternalOnboardingActivityContract.kt",
      "java/com/android/onboarding/contracts/IdentifyExecutingContract.kt",
      "java/com/android/onboarding/contracts/IntentSerializer.kt",
      "java/com/android/onboarding/contracts/NodeAwareIntentScope.kt",
      "java/com/android/onboarding/contracts/OnboardingActivity.kt",
      "java/com/android/onboarding/contracts/OnboardingActivityApiContract.kt",
      "java/com/android/onboarding/contracts/ResultRedirectionConfig.kt",
      "java/com/android/onboarding/contracts/Results.kt",
      "java/com/android/onboarding/contracts/SuccessFail.kt",
      "java/com/android/onboarding/contracts/VoidOnboardingActivityApiContract.kt",
      "java/com/android/onboarding/contracts/annotations",
      "java/com/android/onboarding/contracts/proguard.pgcfg",
      "java/com/android/onboarding/contracts/provisioning",
      "java/com/android/onboarding/contracts/setupwizard/Android.bp",
      "java/com/android/onboarding/contracts/setupwizard/SuwArguments.kt",
      "java/com/android/onboarding/contracts/setupwizard/SuwArgumentsSerializer.kt",
      "java/com/android/onboarding/control",
      "java/com/android/onboarding/datastore",
      "java/com/android/onboarding/encoding",
      "java/com/android/onboarding/flags/Android.bp",
      "java/com/android/onboarding/flags/DefaultOnboardingFlagsProvider.kt",
      "java/com/android/onboarding/flags/OnboardingFlagsProvider.kt",
      "java/com/android/onboarding/flags/OnboardingFlagsUpdater.kt",
      "java/com/android/onboarding/metadata",
      "java/com/android/onboarding/nodes",
      "java/com/android/onboarding/pending",
      "java/com/android/onboarding/process",
      "java/com/android/onboarding/shim",
      "java/com/android/onboarding/tasks",
      "java/com/android/onboarding/utils",
      "java/com/android/onboarding/versions"
    ]
  },
  {
    "commit": "e67b5c11b0a39d07706faa2f5faf820db3848005",
    "name": "platform/external/androidplot",
    "path": "external/androidplot",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "AndroidPlot-Core",
      "Examples"
    ]
  },
  {
    "commit": "3579bbb782f7142cb626fb1b2c2897fc44d126c0",
    "name": "platform/external/anonymous-counting-tokens",
    "path": "external/anonymous-counting-tokens",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "act"
    ]
  },
  {
    "commit": "65f18cb2abd2963bf5663e1f35d6aca08504f79d",
    "name": "platform/external/apache-commons-compress",
    "path": "external/apache-commons-compress",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "1925eace5c3c652318a9262a45a1289daf1a55bd",
    "name": "platform/external/apache-commons-io",
    "path": "external/apache-commons-io",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "1d59c3c747e15d6bbb09d564e474eaaf43beb828",
    "name": "platform/external/apache-commons-lang",
    "path": "external/apache-commons-lang",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "5b1a8fb3a14fdd9516c27236b1b48637e0a25423",
    "name": "platform/external/apache-commons-math",
    "path": "external/apache-commons-math",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "41f08cad2cddba0acfe40c9f5d9c63863f561c49",
    "name": "platform/external/apache-harmony",
    "path": "external/apache-harmony",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "beans",
      "jdwp",
      "logging",
      "luni",
      "sql",
      "support"
    ]
  },
  {
    "commit": "81a10899890a8351a6a0ea46f6692b03a2a08632",
    "name": "platform/external/apache-velocity-engine",
    "path": "external/apache-velocity-engine",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "generated-sources",
      "velocity-engine-core"
    ]
  },
  {
    "commit": "dd21df2f7c701a04e4d8699dd15cad5fe1b7c008",
    "name": "platform/external/bazelbuild-remote-apis",
    "path": "external/bazelbuild-remote-apis",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "build"
    ]
  },
  {
    "commit": "707a2f3848c4b87b1b37890da1f4ca5d22390ee0",
    "name": "platform/external/bpftool",
    "path": "external/bpftool",
    "purpose": "Pinned complete original source of a retained native pair literal provider project read in r20/r21",
    "sparse_paths": []
  },
  {
    "commit": "6bbcf65f3b25bd09fc39d8166070f9adea325089",
    "name": "platform/external/bsdiff",
    "path": "external/bsdiff",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include"
    ]
  },
  {
    "commit": "3395226d307f42172f7f2350f1f54a62ca394353",
    "name": "platform/external/bzip2",
    "path": "external/bzip2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "d7bb09dccd464969498584337b0e68a9347b4d40",
    "name": "platform/external/caliper",
    "path": "external/caliper",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "caliper",
      "examples",
      "lib"
    ]
  },
  {
    "commit": "15c79d2eeb7903cf4f730df9871968c055319bd8",
    "name": "platform/external/cblas",
    "path": "external/cblas",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "src",
      "testing"
    ]
  },
  {
    "commit": "48f4d31b8c1944862c63151515585973cbd91c36",
    "name": "platform/external/cbor-java",
    "path": "external/cbor-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "bdc4d062dc4550869e0825da19fe8fa720db860a",
    "name": "platform/external/clang",
    "path": "external/clang",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bindings",
      "include",
      "lib/ARCMigrate",
      "lib/AST",
      "lib/ASTMatchers",
      "lib/Analysis",
      "lib/Android.bp",
      "lib/Basic",
      "lib/CodeGen",
      "lib/Driver",
      "lib/Edit",
      "lib/Format",
      "lib/Frontend",
      "lib/Headers",
      "lib/Index",
      "lib/Lex",
      "lib/Parse",
      "lib/Rewrite",
      "lib/Sema",
      "lib/Serialization",
      "lib/StaticAnalyzer",
      "lib/Tooling",
      "test/ARCMT",
      "test/ASTMerge",
      "test/Analysis",
      "test/CXX",
      "test/CodeCompletion",
      "test/CodeGen",
      "test/CodeGenCUDA",
      "test/CodeGenCXX",
      "test/CodeGenObjC",
      "test/CodeGenObjCXX",
      "test/Coverage",
      "test/CoverageMapping",
      "test/Driver/Inputs/header0.h",
      "test/Driver/Inputs/header1.h",
      "test/Driver/Inputs/header2.h",
      "test/Driver/Inputs/header3.h",
      "test/Driver/Inputs/header4.h",
      "test/Driver/Inputs/module",
      "test/Driver/Inputs/pchfile.h",
      "test/Driver/clang_f_opts.h",
      "test/Driver/crash-report-header.h",
      "test/Driver/split-debug.h",
      "test/FixIt",
      "test/Frontend",
      "test/Headers",
      "test/Index",
      "test/Lexer",
      "test/Misc",
      "test/Modules",
      "test/PCH",
      "test/Parser",
      "test/Preprocessor",
      "test/Profile",
      "test/Sema",
      "test/SemaCUDA",
      "test/SemaCXX",
      "test/SemaObjC",
      "test/SemaObjCXX",
      "test/TableGen",
      "test/Tooling",
      "test/VFS",
      "tools",
      "unittests",
      "utils",
      "soong"
    ]
  },
  {
    "commit": "5a89860ea70dab6d2c01c6c8bca6167e6763744f",
    "name": "platform/external/cn-cbor",
    "path": "external/cn-cbor",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "src",
      "test"
    ]
  },
  {
    "commit": "a892af49f8b58ef4631a1c050516053f831c0b20",
    "name": "platform/external/connectedappssdk",
    "path": "external/connectedappssdk",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "annotations",
      "processor",
      "sdk",
      "testing",
      "tests"
    ]
  },
  {
    "commit": "b6372c1f38d5cda04a74685271e7233bb180841d",
    "name": "platform/external/cpuinfo",
    "path": "external/cpuinfo",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "deps",
      "include",
      "src",
      "test"
    ]
  },
  {
    "commit": "c7dd8d6950912fa5e6fde7ec2d1616e0ddc090f8",
    "name": "platform/external/crosvm",
    "path": "external/crosvm",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "aarch64",
      "aarch64_sys_reg",
      "acpi_tables",
      "android_audio",
      "arch",
      "argh_helpers",
      "audio_util",
      "base",
      "bit_field",
      "common",
      "cros_async",
      "cros_fdt",
      "cros_tracing",
      "cros_tracing_types",
      "crosvm_cli",
      "crosvm_control",
      "devices",
      "disk",
      "ext2",
      "fuse",
      "gpu_display",
      "hypervisor",
      "infra",
      "io_uring",
      "jail/Android.bp",
      "jail/src",
      "kernel_cmdline",
      "kernel_loader",
      "kvm_sys",
      "libcras_stub",
      "linux_input_sys",
      "media",
      "metrics",
      "metrics_events",
      "net_sys",
      "net_util",
      "power_monitor",
      "proc_init",
      "protos",
      "resources",
      "riscv64",
      "serde_keyvalue",
      "snapshot",
      "src",
      "swap",
      "third_party",
      "usb_sys",
      "usb_util",
      "vendor/generic/crypto",
      "vendor/generic/metrics",
      "vendor/generic/metrics_events",
      "vendor/generic/proc_init",
      "vendor/generic/vm_control",
      "vfio_sys",
      "vhost",
      "virtio_sys",
      "vm_control",
      "vm_memory",
      "x86_64"
    ]
  },
  {
    "commit": "8db9a00c327b7cf77fe43f2b6ca6137b5cacabfc",
    "name": "platform/external/curl",
    "path": "external/curl",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "docs",
      "include",
      "lib",
      "packages",
      "plan9",
      "src",
      "tests"
    ]
  },
  {
    "commit": "57aa7c004b11466c0154144865e937b9a46a4688",
    "name": "platform/external/dagger2",
    "path": "external/dagger2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android-annotation-stubs",
      "dagger-compiler",
      "dagger-producers",
      "dagger-runtime",
      "dagger-spi",
      "hilt-android",
      "hilt-android-testing",
      "hilt-compiler",
      "hilt-core"
    ]
  },
  {
    "commit": "eae519aaa6980b2a34ec07141bb19de3f6ddf69e",
    "name": "platform/external/deqp",
    "path": "external/deqp",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android/cts/main",
      "android/openglcts/AndroidManifest.xml",
      "android/openglcts/src",
      "android/package",
      "data",
      "execserver",
      "executor",
      "external",
      "framework",
      "modules",
      "android/cts"
    ]
  },
  {
    "commit": "d425c460bde47239483e36ccbec5674cf39eb431",
    "name": "platform/external/deqp-deps/SPIRV-Headers",
    "path": "external/deqp-deps/SPIRV-Headers",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include"
    ]
  },
  {
    "commit": "4e0aa7940f17b47e67f7be80442d526b4fc54142",
    "name": "platform/external/deqp-deps/SPIRV-Tools",
    "path": "external/deqp-deps/SPIRV-Tools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "source",
      "test",
      "tools",
      "utils"
    ]
  },
  {
    "commit": "e2217d1616b410dc65f72d0cdd0b73f0b72a860d",
    "name": "platform/external/deqp-deps/amber",
    "path": "external/deqp-deps/amber",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android_sample",
      "include",
      "samples/config_helper.h",
      "samples/config_helper_dawn.h",
      "samples/config_helper_vulkan.h",
      "samples/log.h",
      "samples/png.h",
      "samples/ppm.h",
      "samples/timestamp.h",
      "src",
      "tools"
    ]
  },
  {
    "commit": "14422bdc57fb93221192a0c542dde144980dfb69",
    "name": "platform/external/deqp-deps/glslang",
    "path": "external/deqp-deps/glslang",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "SPIRV",
      "StandAlone",
      "Test",
      "glslang",
      "gtests"
    ]
  },
  {
    "commit": "e476b06efb29b9a8e70a63ec23a3bb7f6208cfaa",
    "name": "platform/external/dexmaker",
    "path": "external/dexmaker",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "dexmaker",
      "dexmaker-mockito",
      "dexmaker-mockito-inline",
      "dexmaker-mockito-inline-dispatcher",
      "dexmaker-mockito-inline-extended",
      "dexmaker-mockito-inline-extended-tests",
      "dexmaker-mockito-inline-tests",
      "dexmaker-mockito-tests",
      "dexmaker-tests",
      "lib"
    ]
  },
  {
    "commit": "d1eefb5e4345307e4c591d340f51951236f55f31",
    "name": "platform/external/double-conversion",
    "path": "external/double-conversion",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "double-conversion",
      "test"
    ]
  },
  {
    "commit": "8ed02f3b4f3393e617141a55f9d80a0e8b1ef57a",
    "name": "platform/external/downloader",
    "path": "external/downloader",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "a723797020a551c75726e8d91e068087ea489757",
    "name": "platform/external/dynamic_depth",
    "path": "external/dynamic_depth",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "includes",
      "internal"
    ]
  },
  {
    "commit": "06a9728c3609f856e87db38a6602196cec3ab727",
    "name": "platform/external/easymock",
    "path": "external/easymock",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "e06f586857f7f7a814a4621deba91a9f586d930c",
    "name": "platform/external/emboss",
    "path": "external/emboss",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "compiler",
      "integration",
      "runtime",
      "testdata"
    ]
  },
  {
    "commit": "20cd76af5d2d1ea8b4c210ab012518b1b10f66fd",
    "name": "platform/external/ethtool",
    "path": "external/ethtool",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "libmnl",
      "netlink",
      "uapi"
    ]
  },
  {
    "commit": "36366ad807e842c4a523cc15bdb28acfcb807388",
    "name": "platform/external/exoplayer",
    "path": "external/exoplayer",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "annotation-stubs",
      "tree_15dc86382f17a24a3e881e52e31a810c1ea44b49",
      "tree_8e57d3715f9092d5ec54ebe2e538f34bfcc34479"
    ]
  },
  {
    "commit": "c64468cb6397fb63bded0f549438b472f7e7cf88",
    "name": "platform/external/f2fs-tools",
    "path": "external/f2fs-tools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "fsck",
      "include",
      "lib",
      "mkfs",
      "tools"
    ]
  },
  {
    "commit": "90857deb7973c0ca24c79b9c1809fc9667f32c4f",
    "name": "platform/external/fec",
    "path": "external/fec",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "3ca3a393cca6a0594237ceeb3662671811c1d641",
    "name": "platform/external/federated-compute",
    "path": "external/federated-compute",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "fcp"
    ]
  },
  {
    "commit": "8feeb7dabdaf4b99434215b64a8295cf6fc0d0d0",
    "name": "platform/external/fhir/spec/r4",
    "path": "external/fhir/spec/r4",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "json_definitions"
    ]
  },
  {
    "commit": "97cf2c42d30e48e1e6f7432079544dcd8b0af23c",
    "name": "platform/external/fonttools",
    "path": "external/fonttools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Lib"
    ]
  },
  {
    "commit": "d229a02345e07b8105c805c7563b902a7d2f9206",
    "name": "platform/external/fsverity-utils",
    "path": "external/fsverity-utils",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "common",
      "include",
      "lib",
      "programs"
    ]
  },
  {
    "commit": "9304d9b673e827202f9526913d161e3cb49a1560",
    "name": "platform/external/gemmlowp",
    "path": "external/gemmlowp",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "eight_bit_int_gemm",
      "fixedpoint",
      "internal",
      "meta",
      "profiling",
      "public",
      "test"
    ]
  },
  {
    "commit": "63f7331819e1472b02edc5002a66d1d92a2ae912",
    "name": "platform/external/google-auth-library-java",
    "path": "external/google-auth-library-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "credentials",
      "oauth2_http"
    ]
  },
  {
    "commit": "f906bd1cc04bdfbe4bd821de3f9251401c9b094a",
    "name": "platform/external/google-breakpad",
    "path": "external/google-breakpad",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "34e696f9dd9272607c3089a24bdd19b9f0e99e3c",
    "name": "platform/external/google-fonts/carrois-gothic-sc",
    "path": "external/google-fonts/carrois-gothic-sc",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "d4dc7bbf8f7560c16016d920413bca6f0f62df81",
    "name": "platform/external/google-fonts/coming-soon",
    "path": "external/google-fonts/coming-soon",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "670e926c3f6f8a9f0dcfe0174f2ec138124424ed",
    "name": "platform/external/google-fonts/cutive-mono",
    "path": "external/google-fonts/cutive-mono",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "dc191e60cf6b573e4e280b75c39343a2a70b1175",
    "name": "platform/external/google-fonts/dancing-script",
    "path": "external/google-fonts/dancing-script",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "c099ab73c712ed9c67f87e1caa32a231c6897351",
    "name": "platform/external/google-fonts/source-sans-pro",
    "path": "external/google-fonts/source-sans-pro",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "fc3515ca5657a9f4f513fbf4a14ab8361ed9c672",
    "name": "platform/external/google-fruit",
    "path": "external/google-fruit",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "configuration",
      "examples",
      "include",
      "src",
      "tests"
    ]
  },
  {
    "commit": "e84eba8d574589a839c18f099c0f42ae7f55e204",
    "name": "platform/external/google-smali",
    "path": "external/google-smali",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "dexlib2",
      "scripts",
      "smali/Android.bp",
      "smali/manifest.txt",
      "smali/src/main/java",
      "third_party",
      "util"
    ]
  },
  {
    "commit": "e6867acc464878771f1cc139e14e058238ace238",
    "name": "platform/external/gptfdisk",
    "path": "external/gptfdisk",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "a7112f326a9df61597d1bfdbdad7ad9ef3f764b7",
    "name": "platform/external/grpc-grpc",
    "path": "external/grpc-grpc",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "etc",
      "examples",
      "include",
      "src",
      "test/core/address_utils",
      "test/core/bad_client",
      "test/core/bad_ssl",
      "test/core/call",
      "test/core/credentials",
      "test/core/end2end",
      "test/core/event_engine",
      "test/core/experiments",
      "test/core/ext",
      "test/core/filters",
      "test/core/handshake",
      "test/core/iomgr",
      "test/core/load_balancing",
      "test/core/memory_usage",
      "test/core/promise",
      "test/core/resource_quota",
      "test/core/test_util",
      "test/core/transport",
      "test/core/tsi/alts",
      "test/core/tsi/transport_security_test_lib.h",
      "test/core/util",
      "test/core/xds",
      "test/cpp",
      "test/csharp",
      "test/distrib/bazel/cpp/protos",
      "test/distrib/bazel/python/helloworld.proto",
      "test/distrib/bazel/python/in_subpackage",
      "test/distrib/bazel/python/namespaced",
      "test/distrib/bazel/python/subdir",
      "test/distrib/csharp",
      "third_party",
      "tools"
    ]
  },
  {
    "commit": "90a34c38cfdd92823eb332eeff0fd1270b6346c8",
    "name": "platform/external/grpc-grpc-java",
    "path": "external/grpc-grpc-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "annotation-stubs",
      "api",
      "auth",
      "compiler",
      "context",
      "core",
      "netty",
      "okhttp",
      "protobuf",
      "protobuf-lite",
      "services",
      "stub",
      "testing"
    ]
  },
  {
    "commit": "183ae373d36f0367d2215e513be237edca4b5977",
    "name": "platform/external/guice",
    "path": "external/guice",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "core",
      "lib"
    ]
  },
  {
    "commit": "487eaf7776fa0733d9835747032288ab0b549a70",
    "name": "platform/external/hyphenation-patterns",
    "path": "external/hyphenation-patterns",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "686f2a5d576144e52d9bae9e86d2be9b09a31aad",
    "name": "platform/external/iamf_tools",
    "path": "external/iamf_tools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "iamf"
    ]
  },
  {
    "commit": "3baefcdf2131527429d780b2f89bb2b845e44bb6",
    "name": "platform/external/icing",
    "path": "external/icing",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "icing",
      "isolated_storage_service",
      "java/Android.bp",
      "java/src",
      "proto"
    ]
  },
  {
    "commit": "e0534954b785ee366e228ca96ae05f86dfcc7feb",
    "name": "platform/external/ims",
    "path": "external/ims",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "rcs/presencepolling",
      "rcs/rcsmanager"
    ]
  },
  {
    "commit": "4587e3723df3ef0e440f14a65c29013ea340cbf5",
    "name": "platform/external/jackson-core",
    "path": "external/jackson-core",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "src"
    ]
  },
  {
    "commit": "b2918806063b27668501eb728168277a7fbc7944",
    "name": "platform/external/jacoco",
    "path": "external/jacoco",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "org.jacoco.agent",
      "org.jacoco.agent.rt",
      "org.jacoco.cli",
      "org.jacoco.core",
      "org.jacoco.report"
    ]
  },
  {
    "commit": "75b5356ec832b8306d8706eb7fae46fef9cbb1d3",
    "name": "platform/external/jakarta.inject",
    "path": "external/jakarta.inject",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "c65eac405e7a34754245921eb50b1ee3932cb0e2",
    "name": "platform/external/javaparser",
    "path": "external/javaparser",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "javaparser-core",
      "javaparser-symbol-solver-core"
    ]
  },
  {
    "commit": "21a7a89b822718efd3dc699586a431e844de7d4d",
    "name": "platform/external/javasqlite",
    "path": "external/javasqlite",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "93591c6475187cb709e85228c0dcb0d007fead13",
    "name": "platform/external/javassist",
    "path": "external/javassist",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "cd18acbf0036a7c6a3443e7e58b5091cacf327cf",
    "name": "platform/external/jimfs",
    "path": "external/jimfs",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "jimfs"
    ]
  },
  {
    "commit": "b5919080e114b31afbc1c9d51408371dc9d54a95",
    "name": "platform/external/jline",
    "path": "external/jline",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "347e976387aa0026cd584c7dafcaff8e25a694fe",
    "name": "platform/external/jsmn",
    "path": "external/jsmn",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "test"
    ]
  },
  {
    "commit": "35efb01f783ee767de7554aa663e7a47d1970faa",
    "name": "platform/external/jsoup",
    "path": "external/jsoup",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "1a5f3f8b0c829e257386c56cfda5e5a442377282",
    "name": "platform/external/junit-params",
    "path": "external/junit-params",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lib",
      "src"
    ]
  },
  {
    "commit": "41034538d81a8ee44e98dfaf6bd9d46f1f45adac",
    "name": "platform/external/kmod",
    "path": "external/kmod",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "libkmod",
      "shared",
      "testsuite/module-playground",
      "testsuite/stripped-module.h",
      "testsuite/testsuite.h",
      "tools"
    ]
  },
  {
    "commit": "aaaf5275f3b0b9cea18998bb08a24987c7f4dbce",
    "name": "platform/external/kotlin-compose-compiler",
    "path": "external/kotlin-compose-compiler",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "org"
    ]
  },
  {
    "commit": "1f60e73215577a48f66542ec09456cdc7f12f3d1",
    "name": "platform/external/kotlinpoet",
    "path": "external/kotlinpoet",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "interop",
      "kotlinpoet"
    ]
  },
  {
    "commit": "651f29118090eaa09418b84358ff5c5bc7fb2d6c",
    "name": "platform/external/ksoap2",
    "path": "external/ksoap2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "kobjects",
      "ksoap2-base",
      "ksoap2-j2se"
    ]
  },
  {
    "commit": "aa08926470a7d3afc856a08b0f40057293b8f437",
    "name": "platform/external/ksp",
    "path": "external/ksp",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "com"
    ]
  },
  {
    "commit": "7f2d1a769f8bfe3dda33bb0f2c437b7889f792ba",
    "name": "platform/external/leakcanary2",
    "path": "external/leakcanary2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "leakcanary-android",
      "shark",
      "shark-android",
      "shark-graph",
      "shark-hprof",
      "shark-log"
    ]
  },
  {
    "commit": "44ab4b0eaa3cc029cf101e00f1908aa4e7530c18",
    "name": "platform/external/leveldb",
    "path": "external/leveldb",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "db",
      "helpers",
      "include",
      "port",
      "table",
      "util"
    ]
  },
  {
    "commit": "6fee3c0be559ce785a5491d46e0b5eb3bd5f34b1",
    "name": "platform/external/libaom",
    "path": "external/libaom",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "aom",
      "aom_dsp",
      "aom_mem",
      "aom_ports",
      "aom_scale",
      "aom_util",
      "apps",
      "av1",
      "common",
      "config",
      "examples",
      "stats",
      "test",
      "third_party",
      "tools"
    ]
  },
  {
    "commit": "4275faf783bc1ce1eb67fe56043f6f052c0de355",
    "name": "platform/external/libavc",
    "path": "external/libavc",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "common",
      "decoder",
      "encoder",
      "examples",
      "tests"
    ]
  },
  {
    "commit": "eae502014c9048318fc1c072e66924bcd88267d6",
    "name": "platform/external/libbrillo",
    "path": "external/libbrillo",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "brillo",
      "install_attributes",
      "policy"
    ]
  },
  {
    "commit": "88894a62bb97313ed9bf79a546f1486de4b2e723",
    "name": "platform/external/libcxx",
    "path": "external/libcxx",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "lib",
      "src",
      "utils"
    ]
  },
  {
    "commit": "84450eba5a24fe5b7df77ed1307bfada05b14dc7",
    "name": "platform/external/libcxxabi",
    "path": "external/libcxxabi",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp",
      "include"
    ]
  },
  {
    "commit": "6c7f95fe604762ee0ed15d53fbcbf34c7d670e26",
    "name": "platform/external/libdav1d",
    "path": "external/libdav1d",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "config",
      "examples",
      "include",
      "src",
      "tests",
      "tools"
    ]
  },
  {
    "commit": "1aef56c457874c2f09abefe2949c1bd4ac17950f",
    "name": "platform/external/libdivsufsort",
    "path": "external/libdivsufsort",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android_include",
      "include",
      "lib"
    ]
  },
  {
    "commit": "e180c53a25cc0f26e6e0caf4a2708c41b8ec5214",
    "name": "platform/external/libexif",
    "path": "external/libexif",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "contrib",
      "libexif"
    ]
  },
  {
    "commit": "05b4080d903415b269d5145a4bbfa53d044fedd2",
    "name": "platform/external/libffi",
    "path": "external/libffi",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "linux-arm",
      "linux-arm64",
      "linux-riscv64",
      "linux-x86",
      "msvc_build",
      "src",
      "testsuite",
      "windows-msvc-x86_64"
    ]
  },
  {
    "commit": "47f83ca03e9ce8f8dc014605d059e3377ad2eafe",
    "name": "platform/external/libfuse",
    "path": "external/libfuse",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "lib"
    ]
  },
  {
    "commit": "2d513c5304d2224bb8109b54f60d2fc9da043c0c",
    "name": "platform/external/libgav1",
    "path": "external/libgav1",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "examples",
      "src",
      "tests"
    ]
  },
  {
    "commit": "1b7668b5cf638c85818176656842bf5ccd9a8369",
    "name": "platform/external/libhevc",
    "path": "external/libhevc",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "common",
      "decoder",
      "encoder",
      "test"
    ]
  },
  {
    "commit": "d4ada0ad25414490456e206da71f466bc2440da1",
    "name": "platform/external/liblc3",
    "path": "external/liblc3",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "fuzz",
      "include",
      "src",
      "test",
      "tools",
      "wasm"
    ]
  },
  {
    "commit": "6a46753fd39349b31ee01715204144f70b107dd0",
    "name": "platform/external/libldac",
    "path": "external/libldac",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "abr",
      "inc",
      "src"
    ]
  },
  {
    "commit": "f56ffa0d810eb127200cded0895c412a907dfa6d",
    "name": "platform/external/libmonet",
    "path": "external/libmonet",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "blend",
      "contrast",
      "dislike",
      "dynamiccolor",
      "energy",
      "hct",
      "palettes",
      "quantize",
      "scheme",
      "score",
      "temperature",
      "utils"
    ]
  },
  {
    "commit": "2c13bc536f823725e2035d89f40389af5f8e878f",
    "name": "platform/external/libmpeg2",
    "path": "external/libmpeg2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "common",
      "decoder"
    ]
  },
  {
    "commit": "2be7f4458cf7c7831df8fbac395e6a7222d0d13f",
    "name": "platform/external/libnl",
    "path": "external/libnl",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "lib",
      "python",
      "tests",
      "third_party"
    ]
  },
  {
    "commit": "1f7d75914d98c47ec2109d94c9561aa9718bd75c",
    "name": "platform/external/libopenapv",
    "path": "external/libopenapv",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "app",
      "inc",
      "src"
    ]
  },
  {
    "commit": "31712864928e8c681b383eddbc0e9b9d58596b0c",
    "name": "platform/external/libopus",
    "path": "external/libopus",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "celt",
      "dnn",
      "include",
      "silk",
      "src",
      "tests"
    ]
  },
  {
    "commit": "8fed07868a7efb8cad6467119c3de47bace7999f",
    "name": "platform/external/libpalmrejection",
    "path": "external/libpalmrejection",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "ui"
    ]
  },
  {
    "commit": "d50bbbacc6b05706a9f99e073eab8b251ce461fb",
    "name": "platform/external/libpcap",
    "path": "external/libpcap",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lbl",
      "missing",
      "msdos",
      "pcap",
      "rpcapd",
      "testprogs"
    ]
  },
  {
    "commit": "efc3e23145023945be5776c556f254155c027112",
    "name": "platform/external/libprotobuf-mutator",
    "path": "external/libprotobuf-mutator",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "examples",
      "port",
      "src"
    ]
  },
  {
    "commit": "f50e3237d9f6d20e95293ffce692aaa60b7c81be",
    "name": "platform/external/libsrtp2",
    "path": "external/libsrtp2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "crypto",
      "fuzzer",
      "include",
      "srtp",
      "test"
    ]
  },
  {
    "commit": "70460fc2b43c3948f9caae1fd4eacd2d666a872b",
    "name": "platform/external/libusb",
    "path": "external/libusb",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Xcode",
      "android/config.h",
      "android/examples",
      "darwin",
      "examples",
      "include",
      "libusb",
      "linux",
      "msvc",
      "tests",
      "windows"
    ]
  },
  {
    "commit": "abf38f0bc29916df7c239f4cee441ebd53fae3bc",
    "name": "platform/external/libutf",
    "path": "external/libutf",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "a928fb11c99d88c4daf3ee03b7c329bfde509535",
    "name": "platform/external/libvpx",
    "path": "external/libvpx",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "config",
      "examples",
      "test/acm_random.h",
      "test/bench.h",
      "test/buffer.h",
      "test/clear_system_state.h",
      "test/codec_factory.h",
      "test/decode_test_driver.h",
      "test/encode_test_driver.h",
      "test/i420_video_source.h",
      "test/init_vpx_test.h",
      "test/ivf_video_source.h",
      "test/md5_helper.h",
      "test/register_state_check.h",
      "test/svc_test.h",
      "test/test_vectors.h",
      "test/util.h",
      "test/video_source.h",
      "test/vpx_scale_test.h",
      "test/webm_video_source.h",
      "test/y4m_video_source.h",
      "test/yuv_video_source.h",
      "third_party",
      "tools",
      "vp8",
      "vp9",
      "vpx",
      "vpx_dsp",
      "vpx_mem",
      "vpx_ports",
      "vpx_scale",
      "vpx_util"
    ]
  },
  {
    "commit": "6e0215e85c6f3e59ef266e2e2167741980965e92",
    "name": "platform/external/libwebm",
    "path": "external/libwebm",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "common",
      "m2ts",
      "mkvmuxer",
      "mkvparser",
      "testing",
      "webm_parser",
      "webvtt"
    ]
  },
  {
    "commit": "428f94dc05f8405684ae647db5bf3db06ec722c5",
    "name": "platform/external/libwebsockets",
    "path": "external/libwebsockets",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "cmake",
      "include",
      "lib",
      "minimal-examples/embedded",
      "minimal-examples/http-client",
      "minimal-examples/http-server/minimal-http-server-eventlib-foreign",
      "minimal-examples/secure-streams",
      "plugins",
      "win32port"
    ]
  },
  {
    "commit": "8d9809f480fb56c68ff6b76927aceb382d55045e",
    "name": "platform/external/libxaac",
    "path": "external/libxaac",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "common",
      "decoder",
      "encoder",
      "test"
    ]
  },
  {
    "commit": "429d6c6097aea3326e49fc8e87cc7658b750c5d7",
    "name": "platform/external/llvm",
    "path": "external/llvm",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bindings",
      "device",
      "examples",
      "host",
      "include",
      "lib/Analysis",
      "lib/Android.bp",
      "lib/AsmParser",
      "lib/Bitcode",
      "lib/CodeGen",
      "lib/DebugInfo",
      "lib/ExecutionEngine",
      "lib/Fuzzer",
      "lib/IR",
      "lib/IRReader",
      "lib/LTO",
      "lib/LibDriver",
      "lib/Linker",
      "lib/MC",
      "lib/Object",
      "lib/Option",
      "lib/Passes",
      "lib/ProfileData",
      "lib/Support",
      "lib/TableGen",
      "lib/Target/AArch64/AArch64.h",
      "lib/Target/AArch64/AArch64A53Fix835769.cpp",
      "lib/Target/AArch64/AArch64A57FPLoadBalancing.cpp",
      "lib/Target/AArch64/AArch64AddressTypePromotion.cpp",
      "lib/Target/AArch64/AArch64AdvSIMDScalarPass.cpp",
      "lib/Target/AArch64/AArch64AsmPrinter.cpp",
      "lib/Target/AArch64/AArch64BranchRelaxation.cpp",
      "lib/Target/AArch64/AArch64CallLowering.cpp",
      "lib/Target/AArch64/AArch64CallLowering.h",
      "lib/Target/AArch64/AArch64CallingConvention.h",
      "lib/Target/AArch64/AArch64CleanupLocalDynamicTLSPass.cpp",
      "lib/Target/AArch64/AArch64CollectLOH.cpp",
      "lib/Target/AArch64/AArch64ConditionOptimizer.cpp",
      "lib/Target/AArch64/AArch64ConditionalCompares.cpp",
      "lib/Target/AArch64/AArch64DeadRegisterDefinitionsPass.cpp",
      "lib/Target/AArch64/AArch64ExpandPseudoInsts.cpp",
      "lib/Target/AArch64/AArch64FastISel.cpp",
      "lib/Target/AArch64/AArch64FrameLowering.cpp",
      "lib/Target/AArch64/AArch64FrameLowering.h",
      "lib/Target/AArch64/AArch64ISelDAGToDAG.cpp",
      "lib/Target/AArch64/AArch64ISelLowering.cpp",
      "lib/Target/AArch64/AArch64ISelLowering.h",
      "lib/Target/AArch64/AArch64InstrInfo.cpp",
      "lib/Target/AArch64/AArch64InstrInfo.h",
      "lib/Target/AArch64/AArch64LoadStoreOptimizer.cpp",
      "lib/Target/AArch64/AArch64MCInstLower.cpp",
      "lib/Target/AArch64/AArch64MCInstLower.h",
      "lib/Target/AArch64/AArch64MachineFunctionInfo.h",
      "lib/Target/AArch64/AArch64PBQPRegAlloc.cpp",
      "lib/Target/AArch64/AArch64PBQPRegAlloc.h",
      "lib/Target/AArch64/AArch64PerfectShuffle.h",
      "lib/Target/AArch64/AArch64PromoteConstant.cpp",
      "lib/Target/AArch64/AArch64RedundantCopyElimination.cpp",
      "lib/Target/AArch64/AArch64RegisterBankInfo.cpp",
      "lib/Target/AArch64/AArch64RegisterBankInfo.h",
      "lib/Target/AArch64/AArch64RegisterInfo.cpp",
      "lib/Target/AArch64/AArch64RegisterInfo.h",
      "lib/Target/AArch64/AArch64SelectionDAGInfo.cpp",
      "lib/Target/AArch64/AArch64SelectionDAGInfo.h",
      "lib/Target/AArch64/AArch64StorePairSuppress.cpp",
      "lib/Target/AArch64/AArch64Subtarget.cpp",
      "lib/Target/AArch64/AArch64Subtarget.h",
      "lib/Target/AArch64/AArch64TargetMachine.cpp",
      "lib/Target/AArch64/AArch64TargetMachine.h",
      "lib/Target/AArch64/AArch64TargetObjectFile.cpp",
      "lib/Target/AArch64/AArch64TargetObjectFile.h",
      "lib/Target/AArch64/AArch64TargetTransformInfo.cpp",
      "lib/Target/AArch64/AArch64TargetTransformInfo.h",
      "lib/Target/AArch64/Android.bp",
      "lib/Target/AArch64/Disassembler",
      "lib/Target/AArch64/InstPrinter",
      "lib/Target/AArch64/MCTargetDesc",
      "lib/Target/AArch64/Utils",
      "lib/Target/AMDGPU",
      "lib/Target/ARM/A15SDOptimizer.cpp",
      "lib/Target/ARM/ARM.h",
      "lib/Target/ARM/ARMAsmPrinter.cpp",
      "lib/Target/ARM/ARMAsmPrinter.h",
      "lib/Target/ARM/ARMBaseInstrInfo.cpp",
      "lib/Target/ARM/ARMBaseInstrInfo.h",
      "lib/Target/ARM/ARMBaseRegisterInfo.cpp",
      "lib/Target/ARM/ARMBaseRegisterInfo.h",
      "lib/Target/ARM/ARMCallingConv.h",
      "lib/Target/ARM/ARMConstantIslandPass.cpp",
      "lib/Target/ARM/ARMConstantPoolValue.cpp",
      "lib/Target/ARM/ARMConstantPoolValue.h",
      "lib/Target/ARM/ARMExpandPseudoInsts.cpp",
      "lib/Target/ARM/ARMFastISel.cpp",
      "lib/Target/ARM/ARMFeatures.h",
      "lib/Target/ARM/ARMFrameLowering.cpp",
      "lib/Target/ARM/ARMFrameLowering.h",
      "lib/Target/ARM/ARMHazardRecognizer.cpp",
      "lib/Target/ARM/ARMHazardRecognizer.h",
      "lib/Target/ARM/ARMISelDAGToDAG.cpp",
      "lib/Target/ARM/ARMISelLowering.cpp",
      "lib/Target/ARM/ARMISelLowering.h",
      "lib/Target/ARM/ARMInstrInfo.cpp",
      "lib/Target/ARM/ARMInstrInfo.h",
      "lib/Target/ARM/ARMLoadStoreOptimizer.cpp",
      "lib/Target/ARM/ARMMCInstLower.cpp",
      "lib/Target/ARM/ARMMachineFunctionInfo.cpp",
      "lib/Target/ARM/ARMMachineFunctionInfo.h",
      "lib/Target/ARM/ARMOptimizeBarriersPass.cpp",
      "lib/Target/ARM/ARMPerfectShuffle.h",
      "lib/Target/ARM/ARMRegisterInfo.cpp",
      "lib/Target/ARM/ARMRegisterInfo.h",
      "lib/Target/ARM/ARMSelectionDAGInfo.cpp",
      "lib/Target/ARM/ARMSelectionDAGInfo.h",
      "lib/Target/ARM/ARMSubtarget.cpp",
      "lib/Target/ARM/ARMSubtarget.h",
      "lib/Target/ARM/ARMTargetMachine.cpp",
      "lib/Target/ARM/ARMTargetMachine.h",
      "lib/Target/ARM/ARMTargetObjectFile.cpp",
      "lib/Target/ARM/ARMTargetObjectFile.h",
      "lib/Target/ARM/ARMTargetTransformInfo.cpp",
      "lib/Target/ARM/ARMTargetTransformInfo.h",
      "lib/Target/ARM/Android.bp",
      "lib/Target/ARM/InstPrinter",
      "lib/Target/ARM/LICENSE.TXT",
      "lib/Target/ARM/MCTargetDesc",
      "lib/Target/ARM/MLxExpansionPass.cpp",
      "lib/Target/ARM/Thumb1FrameLowering.cpp",
      "lib/Target/ARM/Thumb1FrameLowering.h",
      "lib/Target/ARM/Thumb1InstrInfo.cpp",
      "lib/Target/ARM/Thumb1InstrInfo.h",
      "lib/Target/ARM/Thumb2ITBlockPass.cpp",
      "lib/Target/ARM/Thumb2InstrInfo.cpp",
      "lib/Target/ARM/Thumb2InstrInfo.h",
      "lib/Target/ARM/Thumb2SizeReduction.cpp",
      "lib/Target/ARM/ThumbRegisterInfo.cpp",
      "lib/Target/ARM/ThumbRegisterInfo.h",
      "lib/Target/AVR",
      "lib/Target/Android.bp",
      "lib/Target/BPF",
      "lib/Target/Hexagon",
      "lib/Target/Lanai",
      "lib/Target/MSP430",
      "lib/Target/Mips/Android.bp",
      "lib/Target/Mips/InstPrinter",
      "lib/Target/Mips/MCTargetDesc",
      "lib/Target/Mips/Mips.h",
      "lib/Target/Mips/Mips16FrameLowering.cpp",
      "lib/Target/Mips/Mips16FrameLowering.h",
      "lib/Target/Mips/Mips16HardFloat.cpp",
      "lib/Target/Mips/Mips16HardFloatInfo.cpp",
      "lib/Target/Mips/Mips16HardFloatInfo.h",
      "lib/Target/Mips/Mips16ISelDAGToDAG.cpp",
      "lib/Target/Mips/Mips16ISelDAGToDAG.h",
      "lib/Target/Mips/Mips16ISelLowering.cpp",
      "lib/Target/Mips/Mips16ISelLowering.h",
      "lib/Target/Mips/Mips16InstrInfo.cpp",
      "lib/Target/Mips/Mips16InstrInfo.h",
      "lib/Target/Mips/Mips16RegisterInfo.cpp",
      "lib/Target/Mips/Mips16RegisterInfo.h",
      "lib/Target/Mips/MipsAnalyzeImmediate.cpp",
      "lib/Target/Mips/MipsAnalyzeImmediate.h",
      "lib/Target/Mips/MipsAsmPrinter.cpp",
      "lib/Target/Mips/MipsAsmPrinter.h",
      "lib/Target/Mips/MipsCCState.cpp",
      "lib/Target/Mips/MipsCCState.h",
      "lib/Target/Mips/MipsConstantIslandPass.cpp",
      "lib/Target/Mips/MipsDelaySlotFiller.cpp",
      "lib/Target/Mips/MipsFastISel.cpp",
      "lib/Target/Mips/MipsFrameLowering.cpp",
      "lib/Target/Mips/MipsFrameLowering.h",
      "lib/Target/Mips/MipsHazardSchedule.cpp",
      "lib/Target/Mips/MipsISelDAGToDAG.cpp",
      "lib/Target/Mips/MipsISelDAGToDAG.h",
      "lib/Target/Mips/MipsISelLowering.cpp",
      "lib/Target/Mips/MipsISelLowering.h",
      "lib/Target/Mips/MipsInstrInfo.cpp",
      "lib/Target/Mips/MipsInstrInfo.h",
      "lib/Target/Mips/MipsLongBranch.cpp",
      "lib/Target/Mips/MipsMCInstLower.cpp",
      "lib/Target/Mips/MipsMCInstLower.h",
      "lib/Target/Mips/MipsMachineFunction.cpp",
      "lib/Target/Mips/MipsMachineFunction.h",
      "lib/Target/Mips/MipsModuleISelDAGToDAG.cpp",
      "lib/Target/Mips/MipsOptimizePICCall.cpp",
      "lib/Target/Mips/MipsOptionRecord.h",
      "lib/Target/Mips/MipsOs16.cpp",
      "lib/Target/Mips/MipsRegisterInfo.cpp",
      "lib/Target/Mips/MipsRegisterInfo.h",
      "lib/Target/Mips/MipsSEFrameLowering.cpp",
      "lib/Target/Mips/MipsSEFrameLowering.h",
      "lib/Target/Mips/MipsSEISelDAGToDAG.cpp",
      "lib/Target/Mips/MipsSEISelDAGToDAG.h",
      "lib/Target/Mips/MipsSEISelLowering.cpp",
      "lib/Target/Mips/MipsSEISelLowering.h",
      "lib/Target/Mips/MipsSEInstrInfo.cpp",
      "lib/Target/Mips/MipsSEInstrInfo.h",
      "lib/Target/Mips/MipsSERegisterInfo.cpp",
      "lib/Target/Mips/MipsSERegisterInfo.h",
      "lib/Target/Mips/MipsSubtarget.cpp",
      "lib/Target/Mips/MipsSubtarget.h",
      "lib/Target/Mips/MipsTargetMachine.cpp",
      "lib/Target/Mips/MipsTargetMachine.h",
      "lib/Target/Mips/MipsTargetObjectFile.cpp",
      "lib/Target/Mips/MipsTargetObjectFile.h",
      "lib/Target/Mips/MipsTargetStreamer.h",
      "lib/Target/NVPTX",
      "lib/Target/PowerPC",
      "lib/Target/Sparc",
      "lib/Target/SystemZ",
      "lib/Target/Target.cpp",
      "lib/Target/TargetIntrinsicInfo.cpp",
      "lib/Target/TargetLoweringObjectFile.cpp",
      "lib/Target/TargetMachine.cpp",
      "lib/Target/TargetMachineC.cpp",
      "lib/Target/TargetRecip.cpp",
      "lib/Target/TargetSubtargetInfo.cpp",
      "lib/Target/WebAssembly",
      "lib/Target/X86/Android.bp",
      "lib/Target/X86/AsmParser",
      "lib/Target/X86/Disassembler",
      "lib/Target/X86/InstPrinter",
      "lib/Target/X86/MCTargetDesc",
      "lib/Target/X86/Utils",
      "lib/Target/X86/X86.h",
      "lib/Target/X86/X86AsmPrinter.cpp",
      "lib/Target/X86/X86AsmPrinter.h",
      "lib/Target/X86/X86CallFrameOptimization.cpp",
      "lib/Target/X86/X86CallingConv.h",
      "lib/Target/X86/X86ExpandPseudo.cpp",
      "lib/Target/X86/X86FastISel.cpp",
      "lib/Target/X86/X86FixupBWInsts.cpp",
      "lib/Target/X86/X86FixupLEAs.cpp",
      "lib/Target/X86/X86FixupSetCC.cpp",
      "lib/Target/X86/X86FloatingPoint.cpp",
      "lib/Target/X86/X86FrameLowering.cpp",
      "lib/Target/X86/X86FrameLowering.h",
      "lib/Target/X86/X86ISelDAGToDAG.cpp",
      "lib/Target/X86/X86ISelLowering.cpp",
      "lib/Target/X86/X86ISelLowering.h",
      "lib/Target/X86/X86InstrBuilder.h",
      "lib/Target/X86/X86InstrInfo.cpp",
      "lib/Target/X86/X86InstrInfo.h",
      "lib/Target/X86/X86IntrinsicsInfo.h",
      "lib/Target/X86/X86MCInstLower.cpp",
      "lib/Target/X86/X86MachineFunctionInfo.cpp",
      "lib/Target/X86/X86MachineFunctionInfo.h",
      "lib/Target/X86/X86OptimizeLEAs.cpp",
      "lib/Target/X86/X86PadShortFunction.cpp",
      "lib/Target/X86/X86RegisterInfo.cpp",
      "lib/Target/X86/X86RegisterInfo.h",
      "lib/Target/X86/X86SelectionDAGInfo.cpp",
      "lib/Target/X86/X86SelectionDAGInfo.h",
      "lib/Target/X86/X86ShuffleDecodeConstantPool.cpp",
      "lib/Target/X86/X86ShuffleDecodeConstantPool.h",
      "lib/Target/X86/X86Subtarget.cpp",
      "lib/Target/X86/X86Subtarget.h",
      "lib/Target/X86/X86TargetMachine.cpp",
      "lib/Target/X86/X86TargetMachine.h",
      "lib/Target/X86/X86TargetObjectFile.cpp",
      "lib/Target/X86/X86TargetObjectFile.h",
      "lib/Target/X86/X86TargetTransformInfo.cpp",
      "lib/Target/X86/X86TargetTransformInfo.h",
      "lib/Target/X86/X86VZeroUpper.cpp",
      "lib/Target/X86/X86WinAllocaExpander.cpp",
      "lib/Target/X86/X86WinEHState.cpp",
      "lib/Target/XCore",
      "lib/Transforms/Android.bp",
      "lib/Transforms/IPO",
      "lib/Transforms/InstCombine",
      "lib/Transforms/Instrumentation",
      "lib/Transforms/ObjCARC",
      "lib/Transforms/Scalar",
      "lib/Transforms/Utils",
      "lib/Transforms/Vectorize",
      "test",
      "tools",
      "unittests",
      "utils/TableGen",
      "utils/unittest",
      "soong",
      "lib/Target/AArch64/AsmParser",
      "lib/Target/AArch64/TargetInfo",
      "lib/Target/ARM/AsmParser",
      "lib/Target/ARM/Disassembler",
      "lib/Target/ARM/TargetInfo",
      "lib/Target/Mips/AsmParser",
      "lib/Target/Mips/Disassembler",
      "lib/Target/Mips/TargetInfo",
      "lib/Target/X86/TargetInfo"
    ]
  },
  {
    "commit": "f21c8dba91039320eeb9d964d8272d9a22f38d72",
    "name": "platform/external/lottie",
    "path": "external/lottie",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lottie",
      "lottie-compose"
    ]
  },
  {
    "commit": "32927b80c3fcba2cee73f03d1cc4a982a9426032",
    "name": "platform/external/lua",
    "path": "external/lua",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "82e515bcaac323a3f745567b65f25816ec931e9a",
    "name": "platform/external/marisa-trie",
    "path": "external/marisa-trie",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bindings",
      "include",
      "lib",
      "tests",
      "tools"
    ]
  },
  {
    "commit": "dd118e8e248588871479dd3b82fab993a58c99d6",
    "name": "platform/external/mbedtls",
    "path": "external/mbedtls",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "3rdparty",
      "configs",
      "doxygen",
      "include",
      "library",
      "programs",
      "tests"
    ]
  },
  {
    "commit": "3e0189c4d3be5272398b1ea6ad2f223a973d0ea2",
    "name": "platform/external/mdnsresponder",
    "path": "external/mdnsresponder",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Clients",
      "android",
      "mDNSCore",
      "mDNSPosix",
      "mDNSShared",
      "mDNSWindows"
    ]
  },
  {
    "commit": "875160ed32cc5bc32777fa04870a0a57ed38c987",
    "name": "platform/external/mesa3d",
    "path": "external/mesa3d",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bin/Android.bp",
      "bin/gen_vs_module_defs.py",
      "bin/git_sha1_gen.py",
      "docs",
      "fuchsia-build",
      "include",
      "src/Android.bp",
      "src/amd",
      "src/android_stub",
      "src/asahi",
      "src/broadcom",
      "src/c11",
      "src/compiler",
      "src/drm-shim",
      "src/egl",
      "src/etnaviv",
      "src/freedreno",
      "src/gallium/auxiliary",
      "src/gallium/drivers",
      "src/gallium/frontends",
      "src/gallium/include",
      "src/gallium/targets/d3d10umd",
      "src/gallium/targets/libgl-gdi",
      "src/gallium/targets/mediafoundation",
      "src/gallium/targets/teflon",
      "src/gallium/winsys",
      "src/gbm",
      "src/getopt",
      "src/gfxstream",
      "src/glx",
      "src/gtest",
      "src/imagination",
      "src/imgui",
      "src/intel",
      "src/kosmickrisp",
      "src/loader",
      "src/mesa",
      "src/microsoft",
      "src/nouveau",
      "src/panfrost",
      "src/poly",
      "src/tool",
      "src/util",
      "src/virtio",
      "src/vulkan",
      "src/x11"
    ]
  },
  {
    "commit": "26ff82bac9c77ef25d0a913ee09ed11ccdfdab78",
    "name": "platform/external/minijail",
    "path": "external/minijail",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "examples",
      "linux-x86",
      "rust",
      "test"
    ]
  },
  {
    "commit": "db9b110f0d59fcc70fe8f3c37230e0c4a55db3c3",
    "name": "platform/external/mobile-data-download",
    "path": "external/mobile-data-download",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android-annotation-stubs",
      "java",
      "javatests",
      "proto"
    ]
  },
  {
    "commit": "dcb370e6b35c036a8709fe17fe332449d872fa35",
    "name": "platform/external/mobly-bundled-snippets",
    "path": "external/mobly-bundled-snippets",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "fcbe611cef61ea47d55107c6d70ac1b4706a6217",
    "name": "platform/external/mobly-snippet-lib",
    "path": "external/mobly-snippet-lib",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "third_party"
    ]
  },
  {
    "commit": "455cd7f2c2b34bb2a1bbd8163e4a6c4368513a2b",
    "name": "platform/external/mockftpserver",
    "path": "external/mockftpserver",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "MockFtpServer"
    ]
  },
  {
    "commit": "709411a57d6b6d8aa7495d281e3f48b4f5f67796",
    "name": "platform/external/mockito-kotlin",
    "path": "external/mockito-kotlin",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "mockito-kotlin"
    ]
  },
  {
    "commit": "e63d64d845e3f12d5970fa66120a023aab9b23fe",
    "name": "platform/external/mockwebserver",
    "path": "external/mockwebserver",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "c5142d8e6c754b8512938cc57818dd9bc22f7dfb",
    "name": "platform/external/moshi",
    "path": "external/moshi",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "moshi"
    ]
  },
  {
    "commit": "ed7ca08a5e74aab5f0c5a15cbc08f2364dbe69a3",
    "name": "platform/external/mpdecimal",
    "path": "external/mpdecimal",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "libmpdec",
      "libmpdec++",
      "tests",
      "tests++"
    ]
  },
  {
    "commit": "fb134dfd4d859f3dbd389baf2a8f4420260282c2",
    "name": "platform/external/ms-tpm-20-ref",
    "path": "external/ms-tpm-20-ref",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Samples/ARM32-FirmwareTPM/optee_ta/fTPM/include",
      "Samples/ARM32-FirmwareTPM/optee_ta/fTPM/platform",
      "Samples/ARM32-FirmwareTPM/optee_ta/fTPM/reference",
      "Samples/ARM32-FirmwareTPM/optee_ta/fTPM/user_ta_header_defines.h",
      "Samples/Nucleo-TPM",
      "TPMCmd"
    ]
  },
  {
    "commit": "4711b67f075d8ed195ca46785b125dbea03982c3",
    "name": "platform/external/nanohttpd",
    "path": "external/nanohttpd",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "core",
      "webserver",
      "websocket"
    ]
  },
  {
    "commit": "80a68eefdccd99baeea4880baa1b4c25f2618725",
    "name": "platform/external/neon_2_sse",
    "path": "external/neon_2_sse",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      ".gitignore"
    ]
  },
  {
    "commit": "de62530b71e1f6c1cb2b80a4675fbdd4edda0990",
    "name": "platform/external/nist-pkits",
    "path": "external/nist-pkits",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src"
    ]
  },
  {
    "commit": "ccb4a70ee63245e2f48b15d188e408427bc8616d",
    "name": "platform/external/noto-fonts",
    "path": "external/noto-fonts",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "emoji-compat",
      "notonaskharabic",
      "notonaskharabicui",
      "notosansadlam",
      "notosansanatolianhieroglyphs",
      "notosansarmenian",
      "notosansavestan",
      "notosansbalinese",
      "notosansbamum",
      "notosansbassavah",
      "notosansbatak",
      "notosansbengali",
      "notosansbengaliui",
      "notosansbhaiksuki",
      "notosansbrahmi",
      "notosansbuginese",
      "notosansbuhid",
      "notosanscanadianaboriginal",
      "notosanscarian",
      "notosanschakma",
      "notosanscham",
      "notosanscherokee",
      "notosanscjk",
      "notosanscoptic",
      "notosanscuneiform",
      "notosanscypriot",
      "notosansdeseret",
      "notosansdevanagari",
      "notosansdevanagariui",
      "notosansegyptianhieroglyphs",
      "notosanselbasan",
      "notosansethiopic",
      "notosansgeorgian",
      "notosansglagolitic",
      "notosansgothic",
      "notosansgrantha",
      "notosansgujarati",
      "notosansgujaratiui",
      "notosansgunjalagondi",
      "notosansgurmukhi",
      "notosansgurmukhiui",
      "notosanshanifirohingya",
      "notosanshanunoo",
      "notosanshatran",
      "notosanshebrew",
      "notosansimperialaramaic",
      "notosansinscriptionalpahlavi",
      "notosansinscriptionalparthian",
      "notosansjavanese",
      "notosanskaithi",
      "notosanskannada",
      "notosanskannadaui",
      "notosanskayahli",
      "notosanskharoshthi",
      "notosanskhmer",
      "notosanskhmerui",
      "notosanskhojki",
      "notosanslao",
      "notosanslaoui",
      "notosanslepcha",
      "notosanslimbu",
      "notosanslineara",
      "notosanslinearb",
      "notosanslisu",
      "notosanslycian",
      "notosanslydian",
      "notosansmalayalam",
      "notosansmalayalamui",
      "notosansmandaic",
      "notosansmanichaean",
      "notosansmarchen",
      "notosansmasaramgondi",
      "notosansmedefaidrin",
      "notosansmeeteimayek",
      "notosansmeroitic",
      "notosansmiao",
      "notosansmodi",
      "notosansmongolian",
      "notosansmro",
      "notosansmultani",
      "notosansmyanmar",
      "notosansmyanmarui",
      "notosansnabataean",
      "notosansnewa",
      "notosansnewtailue",
      "notosansnko_todelist",
      "notosansogham",
      "notosansolchiki",
      "notosansolditalic",
      "notosansoldnortharabian",
      "notosansoldpermic",
      "notosansoldpersian",
      "notosansoldsoutharabian",
      "notosansoldturkic",
      "notosansoriya",
      "notosansoriyaui",
      "notosansosage",
      "notosansosmanya",
      "notosanspahawhhmong",
      "notosanspalmyrene",
      "notosanspaucinhau",
      "notosansphagspa",
      "notosansphoenician",
      "notosansrejang",
      "notosansrunic",
      "notosanssamaritan",
      "notosanssaurashtra",
      "notosanssharada",
      "notosansshavian",
      "notosanssinhala",
      "notosanssinhalaui",
      "notosanssorasompeng",
      "notosanssoyombo",
      "notosanssundanese",
      "notosanssylotinagri",
      "notosanssymbols",
      "notosanssyriac",
      "notosanstagalog",
      "notosanstagbanwa",
      "notosanstaile",
      "notosanstaitham",
      "notosanstaiviet",
      "notosanstakri",
      "notosanstamil",
      "notosanstamilui",
      "notosanstelugu",
      "notosansteluguui",
      "notosansthaana",
      "notosansthai",
      "notosansthaiui",
      "notosanstifinagh",
      "notosansugaritic",
      "notosansvai",
      "notosanswancho",
      "notosanswarangciti",
      "notosansyi",
      "notoserif",
      "notoserifahom",
      "notoserifarmenian",
      "notoserifbengali",
      "notoserifcjk",
      "notoserifdevanagari",
      "notoserifdogra",
      "notoserifethiopic",
      "notoserifgeorgian",
      "notoserifgujarati",
      "notoserifgurmukhi",
      "notoserifhebrew",
      "notoserifhentaigana",
      "notoserifkannada",
      "notoserifkhmer",
      "notoseriflao",
      "notoserifmalayalam",
      "notoserifmyanmar",
      "notoserifnyiakengpuachuehmong",
      "notoserifsinhala",
      "notoseriftamil",
      "notoseriftelugu",
      "notoserifthai",
      "notoseriftibetan",
      "notoserifyezidi"
    ]
  },
  {
    "commit": "a26e0fdf6b94bde54d9095d6fd93036c9d8d322d",
    "name": "platform/external/nullaway",
    "path": "external/nullaway",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "annotations",
      "nullaway"
    ]
  },
  {
    "commit": "1f2d427cdd6b022d2e8b713c6e449c2c162d112f",
    "name": "platform/external/obex",
    "path": "external/obex",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "0f51312ecdf768579447d49b4d74483f88bb2871",
    "name": "platform/external/oboe",
    "path": "external/oboe",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apps",
      "include",
      "samples",
      "src"
    ]
  },
  {
    "commit": "6544ec1ee31db50ad8a71e0550843a3156cb7341",
    "name": "platform/external/opencensus-java",
    "path": "external/opencensus-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "api",
      "contrib/grpc_metrics"
    ]
  },
  {
    "commit": "3f982cf4871df8771c9d4abe6e9a6f8d829b2736",
    "name": "platform/external/openscreen",
    "path": "external/openscreen",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "cast",
      "discovery",
      "osp",
      "platform",
      "testing",
      "third_party",
      "tools",
      "util"
    ]
  },
  {
    "commit": "39a30a1f966eebc95599d22550e904a6d2568d64",
    "name": "platform/external/openthread",
    "path": "external/openthread",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "doc",
      "examples",
      "include",
      "src",
      "tests",
      "third_party",
      "tools"
    ]
  },
  {
    "commit": "5822dc6ac2902f705cca5750a7250e463b197962",
    "name": "platform/external/opus-experimental",
    "path": "external/opus-experimental",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "celt",
      "dnn",
      "include",
      "silk",
      "src",
      "tests"
    ]
  },
  {
    "commit": "32f6548e4538288c334179ddc84fc56aab1a1c2b",
    "name": "platform/external/owasp/java-encoder",
    "path": "external/owasp/java-encoder",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "core"
    ]
  },
  {
    "commit": "46c6d3d1b654148dbfd5487fd0bc69a5ed8217c4",
    "name": "platform/external/perfmark",
    "path": "external/perfmark",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "api"
    ]
  },
  {
    "commit": "9bc003aef1c0c120735aeeb1098ef830c265c98c",
    "name": "platform/external/pffft",
    "path": "external/pffft",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "simd"
    ]
  },
  {
    "commit": "f262bde0610200d90934c00d647bf326e2a4a24e",
    "name": "platform/external/private-join-and-compute",
    "path": "external/private-join-and-compute",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "private_join_and_compute"
    ]
  },
  {
    "commit": "ca4de83d1bc260c5aa6be083ca7084dce5996026",
    "name": "platform/external/pthreadpool",
    "path": "external/pthreadpool",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "src",
      "test"
    ]
  },
  {
    "commit": "343e23db1b4d81045e91a10244244893f5acd73b",
    "name": "platform/external/puffin",
    "path": "external/puffin",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "puffin",
      "src"
    ]
  },
  {
    "commit": "0bd198a006d34d3d0a49eebd6c9edbfc0476c973",
    "name": "platform/external/python/absl-py",
    "path": "external/python/absl-py",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "absl"
    ]
  },
  {
    "commit": "ee1fb44f96ef0c7907bc7c07ea753853c68e7cce",
    "name": "platform/external/python/bumble",
    "path": "external/python/bumble",
    "purpose": "Pinned complete original source of a retained native pair literal provider project read in r20/r21",
    "sparse_paths": []
  },
  {
    "commit": "e7fc0ce906fa64166504aba2bd2b5ef96087f96d",
    "name": "platform/external/python/cachetools",
    "path": "external/python/cachetools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "bf1a5fdfa7b53b8b85ccab25f03091ae9193ac92",
    "name": "platform/external/python/cpplint",
    "path": "external/python/cpplint",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "122b02112f61db489ac6d741da60296e800d54a4",
    "name": "platform/external/python/cpython3",
    "path": "external/python/cpython3",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Doc",
      "Include",
      "Lib",
      "Mac",
      "Modules",
      "Objects",
      "PC",
      "Parser",
      "Programs",
      "Python",
      "Tools",
      "android",
      "iOS"
    ]
  },
  {
    "commit": "c5610d434bea5a449aff429d09ddc49d71369c94",
    "name": "platform/external/python/fdt",
    "path": "external/python/fdt",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "9bb5d18c9e8dcc25f8be6359e2dcffba23851acb",
    "name": "platform/external/python/google-api-python-client",
    "path": "external/python/google-api-python-client",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apiclient",
      "googleapiclient/__init__.py",
      "googleapiclient/_auth.py",
      "googleapiclient/_helpers.py",
      "googleapiclient/channel.py",
      "googleapiclient/discovery.py",
      "googleapiclient/discovery_cache/__init__.py",
      "googleapiclient/discovery_cache/appengine_memcache.py",
      "googleapiclient/discovery_cache/base.py",
      "googleapiclient/discovery_cache/file_cache.py",
      "googleapiclient/errors.py",
      "googleapiclient/http.py",
      "googleapiclient/mimeparse.py",
      "googleapiclient/model.py",
      "googleapiclient/sample_tools.py",
      "googleapiclient/schema.py",
      "googleapiclient/version.py"
    ]
  },
  {
    "commit": "46e96844758592ebba0935bbc7757a4d460b9920",
    "name": "platform/external/python/google-auth-library-python",
    "path": "external/python/google-auth-library-python",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "google"
    ]
  },
  {
    "commit": "d9d5963848fc2f3e6abf5c115166ebecdcd69484",
    "name": "platform/external/python/httplib2",
    "path": "external/python/httplib2",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "python3"
    ]
  },
  {
    "commit": "db4425b00090bad6d41aecc08ce24252d7ffd53d",
    "name": "platform/external/python/jinja",
    "path": "external/python/jinja",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "b0e8e2239f9f6b4cee9cf42cab82391dc24f600e",
    "name": "platform/external/python/mako",
    "path": "external/python/mako",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "mako"
    ]
  },
  {
    "commit": "eda387a01ffc563c29997d3021330e0d5586194c",
    "name": "platform/external/python/markupsafe",
    "path": "external/python/markupsafe",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "76a74eb1a96d005f13fcbe64964eb919bb14c548",
    "name": "platform/external/python/mobly",
    "path": "external/python/mobly",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "mobly"
    ]
  },
  {
    "commit": "7055ce09e3ed196a6da5365a86317046473a3374",
    "name": "platform/external/python/oauth2client",
    "path": "external/python/oauth2client",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "oauth2client"
    ]
  },
  {
    "commit": "5a15790dbdcaa7c47f1b5dcdfab55ee63983df65",
    "name": "platform/external/python/portpicker",
    "path": "external/python/portpicker",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "0071cbf57b52336b8261f3903612a2d4d81669af",
    "name": "platform/external/python/pyasn1",
    "path": "external/python/pyasn1",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "pyasn1"
    ]
  },
  {
    "commit": "98f5febb5f61c53f8d3831eafdbe0ec23cb97e32",
    "name": "platform/external/python/pyasn1-modules",
    "path": "external/python/pyasn1-modules",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "pyasn1_modules"
    ]
  },
  {
    "commit": "fb425ade1f96cbb1bed51732664358b1a16e90b4",
    "name": "platform/external/python/pyfakefs",
    "path": "external/python/pyfakefs",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "pyfakefs"
    ]
  },
  {
    "commit": "96a96b5f0d96f196f16e099c04f0785f1556f683",
    "name": "platform/external/python/pyserial",
    "path": "external/python/pyserial",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "serial"
    ]
  },
  {
    "commit": "57ebd58f04b400e908b44ff532db2c2cfc366e3a",
    "name": "platform/external/python/python-api-core",
    "path": "external/python/python-api-core",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "google"
    ]
  },
  {
    "commit": "8fe78f37a81c964bdafb69ecf1af9f0e47c9606b",
    "name": "platform/external/python/pyyaml",
    "path": "external/python/pyyaml",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lib"
    ]
  },
  {
    "commit": "b7be4df622ff5b8902da876cc39a379e569406ef",
    "name": "platform/external/python/rsa",
    "path": "external/python/rsa",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "rsa"
    ]
  },
  {
    "commit": "5dbbc2e9f543b88b6353b6d66f23dcb071f565a7",
    "name": "platform/external/python/snippet-uiautomator",
    "path": "external/python/snippet-uiautomator",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "snippet_uiautomator"
    ]
  },
  {
    "commit": "56d60bebfc3172ab4224c5a64136c9cf3ee2dc6f",
    "name": "platform/external/python/timeout-decorator",
    "path": "external/python/timeout-decorator",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "timeout_decorator"
    ]
  },
  {
    "commit": "3936369be2a971ef0b37742e8f9cf93cd10bcc41",
    "name": "platform/external/python/uritemplates",
    "path": "external/python/uritemplates",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "uritemplate"
    ]
  },
  {
    "commit": "0b66557116f53002852d98db711d5488e838c966",
    "name": "platform/external/python/watchdog",
    "path": "external/python/watchdog",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "1295d6828459cc82c3c29cc5d7d297215250a74b",
    "name": "platform/external/rnnoise",
    "path": "external/rnnoise",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "src"
    ]
  },
  {
    "commit": "458ec4e262a822f055206ae4630fd0cb7fab9ea9",
    "name": "platform/external/roboto-flex-fonts",
    "path": "external/roboto-flex-fonts",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "48287c08f5e74537296b9ddbfb98e4ff09139b9d",
    "name": "platform/external/roboto-fonts",
    "path": "external/roboto-fonts",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "font"
    ]
  },
  {
    "commit": "f635dd46089bcd5abb811828cb294470b6d5f15e",
    "name": "platform/external/roboto-mono",
    "path": "external/roboto-mono",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "7e58deea80bb81100bf42c5530f5038c0c4966f9",
    "name": "platform/external/rust/beto-rust",
    "path": "external/rust/beto-rust",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "betosync",
      "common",
      "nearby",
      "trust_token"
    ]
  },
  {
    "commit": "cb16254d4db8422ffe6cd00fba74be6b85f82b08",
    "name": "platform/external/rust/crates/v4l2r",
    "path": "external/rust/crates/v4l2r",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "lib",
      "utils"
    ]
  },
  {
    "commit": "1f181b0b3e4b821459f21fd9025cd4c408c4f9ec",
    "name": "platform/external/rust/rutabaga_gfx",
    "path": "external/rust/rutabaga_gfx",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "ffi",
      "kumquat",
      "src",
      "third_party"
    ]
  },
  {
    "commit": "a10958a1b10a93535328702c53a18df70dc6d188",
    "name": "platform/external/s2-geometry-library-java",
    "path": "external/s2-geometry-library-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src",
      "tests"
    ]
  },
  {
    "commit": "e0a83b9164067857cc294fa91c4e5b3e8b8e343f",
    "name": "platform/external/sandboxed-api",
    "path": "external/sandboxed-api",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "cmake",
      "contrib",
      "oss-internship-2020",
      "sandboxed_api"
    ]
  },
  {
    "commit": "825c73720a094ed76d5416e44bd387f6f4dd67fd",
    "name": "platform/external/scapy",
    "path": "external/scapy",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "scapy"
    ]
  },
  {
    "commit": "47a2844676ba1ef247aef2ab4faf4fbeed7bd227",
    "name": "platform/external/seccomp-tests",
    "path": "external/seccomp-tests",
    "purpose": "Pinned complete original source of a retained native pair literal provider project read in r20/r21",
    "sparse_paths": []
  },
  {
    "commit": "d4476639e7c7f9bda7bff68e810da2367b8626d2",
    "name": "platform/external/setupcompat",
    "path": "external/setupcompat",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bts",
      "main",
      "partnerconfig"
    ]
  },
  {
    "commit": "79dbf5860322236cd02e74e2ca0855591d95195c",
    "name": "platform/external/setupdesign",
    "path": "external/setupdesign",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lottie_animation_view",
      "lottie_loading_layout",
      "main",
      "strings"
    ]
  },
  {
    "commit": "6c115774a7a909719174fbebf6c404e56eb109da",
    "name": "platform/external/shflags",
    "path": "external/shflags",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "ad278ef33ec42d029a8e9f89aec5c407ab7295ef",
    "name": "platform/external/sl4a",
    "path": "external/sl4a",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Common",
      "InterpreterForAndroid",
      "ScriptingLayer",
      "ScriptingLayerForAndroid",
      "Utils"
    ]
  },
  {
    "commit": "657d9e5f71a92118f891d598dffd64163d8dbbbc",
    "name": "platform/external/slf4j",
    "path": "external/slf4j",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "slf4j-api",
      "slf4j-jdk14",
      "slf4j-nop"
    ]
  },
  {
    "commit": "c990de089156bad9b895a11f03c3fbb9978f37e9",
    "name": "platform/external/sonic",
    "path": "external/sonic",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "0f1afb009e699504301b3c670fe00a679c5192ad",
    "name": "platform/external/squashfs-tools",
    "path": "external/squashfs-tools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "squashfs-tools"
    ]
  },
  {
    "commit": "df1bfa7a40fa53bf7118a25733caf22ee765dd5b",
    "name": "platform/external/subsampling-scale-image-view",
    "path": "external/subsampling-scale-image-view",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "library"
    ]
  },
  {
    "commit": "9a22bb9de00f5d8ddf4fc5ba5c2f425c2816e679",
    "name": "platform/external/swiftshader",
    "path": "external/swiftshader",
    "purpose": "Pinned complete original source of a retained native pair literal provider project read in r20/r21",
    "sparse_paths": []
  },
  {
    "commit": "09146f4eadc469dcd62f494d5c963ab6d7ad112f",
    "name": "platform/external/testng",
    "path": "external/testng",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android-src",
      "kobalt",
      "src"
    ]
  },
  {
    "commit": "eb3d7debd9c042d5449efc1613eb61cc30877eb8",
    "name": "platform/external/tflite-support",
    "path": "external/tflite-support",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "tensorflow_lite_support",
      "third_party"
    ]
  },
  {
    "commit": "e73e85f387715b27ad2a2b4bf3683bb088e3fddb",
    "name": "platform/external/tink-java",
    "path": "external/tink-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "proto",
      "src",
      "src_android"
    ]
  },
  {
    "commit": "962f9d0777975da7dd508bbb8db9a09715b1f692",
    "name": "platform/external/toybox",
    "path": "external/toybox",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "kconfig",
      "lib",
      "scripts",
      "tests",
      "toys"
    ]
  },
  {
    "commit": "3b8b4cf06fdcfbd4c2d091ff74c77f41e97c289e",
    "name": "platform/external/tpm2-tss",
    "path": "external/tpm2-tss",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "lib",
      "src",
      "test"
    ]
  },
  {
    "commit": "100623061b6dd645e61a2431a35e9b5a2bd7e61e",
    "name": "platform/external/tremolo",
    "path": "external/tremolo",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Tremolo",
      "tests/Android.bp",
      "tests/AndroidTest.xml",
      "tests/VorbisDecoderTest.cpp",
      "tests/VorbisDecoderTestEnvironment.h"
    ]
  },
  {
    "commit": "1a7dc6816bbe464e400a3607bec02aeab51ee7af",
    "name": "trusty/external/trusted-firmware-a",
    "path": "external/trusty/arm-trusted-firmware",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "1b0e72282564b2176b673de4f703566a71e9e093",
    "name": "trusty/external/trusty",
    "path": "external/trusty/bootloader",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "adbfb1d942a19974bb5418cd12147eccb5d51138",
    "name": "trusty/external/headers",
    "path": "external/trusty/headers",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "88b0dd09802a19f07869d45dcd9a87a291803201",
    "name": "trusty/lk/common",
    "path": "external/trusty/lk",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "app/tests",
      "arch/arm/arm",
      "arch/arm/arm-m/include",
      "arch/arm/include",
      "arch/arm64",
      "arch/x86",
      "dev/cache",
      "dev/fbcon",
      "dev/interrupt",
      "dev/net/smc91c96",
      "dev/timer",
      "dev/usb",
      "dev/virtio",
      "external",
      "include",
      "kernel/vm",
      "lib/binary_search_tree/Android.bp",
      "lib/binary_search_tree/binary_search_tree.c",
      "lib/binary_search_tree/include",
      "lib/cbuf",
      "lib/device_tree",
      "lib/fixed_point",
      "lib/heap",
      "lib/io",
      "lib/klog",
      "lib/libc/Android.bp",
      "lib/libc/include",
      "lib/libc/include_common",
      "lib/libc/printf.c",
      "lib/libc/test_common",
      "lib/libc/test_includes",
      "lib/libhypervisor",
      "lib/rust_support",
      "tools"
    ]
  },
  {
    "commit": "1d82c49d30e1f5ad1dc1e78e9e20aa4c9b6fbc78",
    "name": "trusty/external/musl",
    "path": "external/trusty/musl",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "e5e6aea584863ff187b6f0d29a33bbd87c470143",
    "name": "platform/external/ublksrv",
    "path": "external/ublksrv",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "compat",
      "include",
      "lib",
      "nbd"
    ]
  },
  {
    "commit": "b6071a2fbc949f954cef5f679615cb9ea972fd79",
    "name": "platform/external/virtio-media",
    "path": "external/virtio-media",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "device"
    ]
  },
  {
    "commit": "591bd295dcd97362b58c4f6ee72d910761a49da9",
    "name": "platform/external/wayland",
    "path": "external/wayland",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "cursor",
      "egl",
      "protocol",
      "src",
      "tests"
    ]
  },
  {
    "commit": "2dabfe6879b25981e0340823eb1b6d037d21577f",
    "name": "platform/external/wayland-protocols",
    "path": "external/wayland-protocols",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "chromium.org",
      "freedesktop.org"
    ]
  },
  {
    "commit": "1895dc1134c158561e0ef668734d86d6bb20d993",
    "name": "platform/external/webrtc",
    "path": "external/webrtc",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "api",
      "audio",
      "base",
      "call",
      "common_audio",
      "common_video",
      "examples",
      "logging",
      "media",
      "modules",
      "net",
      "p2p",
      "pc",
      "rtc_base",
      "rtc_tools",
      "sdk",
      "stats",
      "system_wrappers",
      "test",
      "third_party",
      "video",
      "webrtc"
    ]
  },
  {
    "commit": "d2c16535d139cb185e89120452531bba6b36d3c6",
    "name": "platform/external/xz-embedded",
    "path": "external/xz-embedded",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "linux",
      "userspace"
    ]
  },
  {
    "commit": "c7be7f9413bfe9ccd270dd75c79c04ddef288550",
    "name": "platform/external/xz-java",
    "path": "external/xz-java",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "eef2dd4266802ab1b7f26cb72cb1fc9b8ed3f55b",
    "name": "platform/external/zopfli",
    "path": "external/zopfli",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "e256025d9d9c906caba814fd7b99a311ac8b8ec1",
    "name": "platform/external/zucchini",
    "path": "external/zucchini",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "aosp",
      "fuzzers"
    ]
  },
  {
    "commit": "d89286b7d32c7860f796e95380b22e99618d00c1",
    "name": "platform/external/zxing",
    "path": "external/zxing",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "core"
    ]
  },
  {
    "commit": "943016fade3dbbb725c363d0dc60a6e962bd88e5",
    "name": "platform/frameworks/compile/libbcc",
    "path": "frameworks/compile/libbcc",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bcinfo/Android.bp",
      "bcinfo/BitReader_2_7",
      "bcinfo/BitReader_3_0",
      "bcinfo/BitcodeTranslator.cpp",
      "bcinfo/BitcodeWrapper.cpp",
      "bcinfo/MetadataExtractor.cpp",
      "bcinfo/Wrap",
      "bcinfo/include",
      "bcinfo/libbcinfo.map",
      "include",
      "lib",
      "tools/bcc_compat"
    ]
  },
  {
    "commit": "4080160ebeff7fef5d5ce7062b571830c8cc937e",
    "name": "platform/frameworks/compile/slang",
    "path": "frameworks/compile/slang",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "BitWriter_2_9",
      "BitWriter_2_9_func",
      "BitWriter_3_2",
      "StripUnkAttr"
    ]
  },
  {
    "commit": "4080c2d3e5a6387e0d064ce5744d56fc6a7c9bb7",
    "name": "platform/frameworks/ex",
    "path": "frameworks/ex",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "camera2/extensions/stub",
      "camera2/public",
      "common/Android.bp",
      "common/java"
    ]
  },
  {
    "commit": "c3c4a033756be7157925a288c9678f54b598d212",
    "name": "platform/frameworks/libs/service_entitlement",
    "path": "frameworks/libs/service_entitlement",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "java"
    ]
  },
  {
    "commit": "05dcdbfcff3e74a73b7047f3f90c625e41392481",
    "name": "platform/frameworks/opt/calendar",
    "path": "frameworks/opt/calendar",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "62e43ce168adf3938f77961e856ff8a218ff811c",
    "name": "platform/frameworks/opt/chips",
    "path": "frameworks/opt/chips",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src"
    ]
  },
  {
    "commit": "1ccf7a77e726d2c6f526fc9c7e1cd11141039bc0",
    "name": "platform/frameworks/opt/colorpicker",
    "path": "frameworks/opt/colorpicker",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src"
    ]
  },
  {
    "commit": "12e5aa5f7224b05b6046613967c6d1de75aeaf26",
    "name": "platform/frameworks/opt/net/wifi",
    "path": "frameworks/opt/net/wifi",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "libs/WifiTrackerLib/Android.bp",
      "libs/WifiTrackerLib/TEST_MAPPING",
      "libs/WifiTrackerLib/lint-baseline.xml",
      "libs/WifiTrackerLib/lint-baseline2.xml",
      "libs/WifiTrackerLib/res",
      "libs/WifiTrackerLib/sdk_src",
      "libs/WifiTrackerLib/src",
      "libwifi_hal",
      "libwifi_system",
      "libwifi_system_iface"
    ]
  },
  {
    "commit": "776f9d8f9e72df725d7059c03e7270b0132c39d7",
    "name": "platform/frameworks/opt/setupwizard",
    "path": "frameworks/opt/setupwizard",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "library"
    ]
  },
  {
    "commit": "32f38a793edf8659b21055e16cadd6e912fefcff",
    "name": "platform/frameworks/opt/timezonepicker",
    "path": "frameworks/opt/timezonepicker",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src"
    ]
  },
  {
    "commit": "cedcb3021237950b50a40b14ea4bfd2816c46508",
    "name": "platform/frameworks/opt/tv/tvsystem",
    "path": "frameworks/opt/tv/tvsystem",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "api",
      "java"
    ]
  },
  {
    "commit": "e33e498766f7860fb58fca9f2757123ec78c983e",
    "name": "platform/frameworks/opt/vcard",
    "path": "frameworks/opt/vcard",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "java",
      "tests"
    ]
  },
  {
    "commit": "2efe31da05c6075dd280c9f1b1ea18108971798e",
    "name": "platform/frameworks/rs",
    "path": "frameworks/rs",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "cpp",
      "cpu_ref",
      "driver",
      "script_api",
      "tests/java_api/ImageProcessing",
      "tests/java_api/ImageProcessing_jb",
      "tests/java_api/RSUnitTests",
      "tests/java_api/RsBLAS_Benchmark",
      "tests/java_api/RsTest",
      "toolkit/Android.bp",
      "toolkit/Blend.cpp",
      "toolkit/Blend_advsimd.S",
      "toolkit/Blend_neon.S",
      "toolkit/Blur.cpp",
      "toolkit/Blur_advsimd.S",
      "toolkit/Blur_neon.S",
      "toolkit/ColorMatrix.cpp",
      "toolkit/ColorMatrix_advsimd.S",
      "toolkit/ColorMatrix_neon.S",
      "toolkit/Convolve3x3.cpp",
      "toolkit/Convolve5x5.cpp",
      "toolkit/Convolve_advsimd.S",
      "toolkit/Convolve_neon.S",
      "toolkit/Histogram.cpp",
      "toolkit/Lut.cpp",
      "toolkit/Lut3d.cpp",
      "toolkit/Lut3d_advsimd.S",
      "toolkit/Lut3d_neon.S",
      "toolkit/RenderScriptToolkit.cpp",
      "toolkit/RenderScriptToolkit.h",
      "toolkit/Resize.cpp",
      "toolkit/Resize_advsimd.S",
      "toolkit/Resize_neon.S",
      "toolkit/TaskProcessor.cpp",
      "toolkit/TaskProcessor.h",
      "toolkit/TestTaskProcessor.cpp",
      "toolkit/Utils.cpp",
      "toolkit/Utils.h",
      "toolkit/YuvToRgb.cpp",
      "toolkit/YuvToRgb_advsimd.S",
      "toolkit/YuvToRgb_neon.S",
      "toolkit/x86.cpp"
    ]
  },
  {
    "commit": "cbc8f246cd0c18d3c286ab39620846badd0676fb",
    "name": "platform/frameworks/wilhelm",
    "path": "frameworks/wilhelm",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "src",
      "tests/Android.bp",
      "tests/examples",
      "tests/mimeUri_test.cpp",
      "tests/sandbox/Android.bp",
      "tests/sandbox/configbq.c",
      "tests/sandbox/dim.c",
      "tests/sandbox/dual.c",
      "tests/sandbox/engine.c",
      "tests/sandbox/getch.c",
      "tests/sandbox/getch.h",
      "tests/sandbox/intbufq.c",
      "tests/sandbox/monkey.c",
      "tests/sandbox/multiplay.c",
      "tests/sandbox/multithread.c",
      "tests/sandbox/nativewindow.cpp",
      "tests/sandbox/nativewindow.h",
      "tests/sandbox/object.c",
      "tests/sandbox/outputmix.c",
      "tests/sandbox/playbq.cpp",
      "tests/sandbox/reverb.c",
      "tests/sandbox/srcsink.c",
      "tests/sandbox/urimime.c",
      "tests/sandbox/xa.c",
      "tests/sandbox/xaplay.c",
      "tools"
    ]
  },
  {
    "commit": "ed844b2ed7997f2e5599db9a52321e7c5fdb96de",
    "name": "platform/hardware/google/apf",
    "path": "hardware/google/apf",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "next",
      "testdata",
      "v2",
      "v4",
      "v6",
      "v6.1"
    ]
  },
  {
    "commit": "b46f0d4b4545def09bdf30651d4bf848b2ba0c34",
    "name": "platform/hardware/google/gfxstream",
    "path": "hardware/google/gfxstream",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "codegen",
      "common",
      "guest",
      "host",
      "tests",
      "third_party"
    ]
  },
  {
    "commit": "a36774a8665b72a64cb495501984e8fa0cbb0e53",
    "name": "platform/hardware/google/interfaces",
    "path": "hardware/google/interfaces",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bluetooth/bt_channel_avoidance/aidl/Android.bp",
      "bluetooth/bt_channel_avoidance/aidl/aidl_api",
      "bluetooth/bt_channel_avoidance/aidl/hardware",
      "bluetooth/ccc/aidl/Android.bp",
      "bluetooth/ccc/aidl/aidl_api",
      "bluetooth/ccc/aidl/hardware",
      "bluetooth/ext/aidl/Android.bp",
      "bluetooth/ext/aidl/aidl_api",
      "bluetooth/ext/aidl/hardware",
      "bluetooth/sar/aidl/Android.bp",
      "bluetooth/sar/aidl/aidl_api",
      "bluetooth/sar/aidl/hardware"
    ]
  },
  {
    "commit": "35d736e2410f8b49e3b6f3a5649dc9e9d24ccd3c",
    "name": "platform/hardware/ril",
    "path": "hardware/ril",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "libril",
      "librilutils",
      "reference-ril"
    ]
  },
  {
    "commit": "318576752b27af3d328e6deb5e6aa29b08f762c9",
    "name": "kernel/prebuilts/6.12/arm64",
    "path": "kernel/prebuilts/6.12/arm64",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "cb8e8ee3babf4a27b742f59dcb92f59cf186299c",
    "name": "kernel/prebuilts/6.12/x86-64",
    "path": "kernel/prebuilts/6.12/x86_64",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "350899556b7cae26d5981c7055759428aef7598d",
    "name": "kernel/prebuilts/6.6/arm64",
    "path": "kernel/prebuilts/6.6/arm64",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "b87e9b115da5dd1ed94b423657279c766057d5b3",
    "name": "kernel/prebuilts/6.6/x86-64",
    "path": "kernel/prebuilts/6.6/x86_64",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "7a9e63dea83dfdab46db04fed58642bd8856dede",
    "name": "platform/packages/apps/Calendar",
    "path": "packages/apps/Calendar",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "assets",
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "c9f82c3de8293731d4230758dc258916c12335a6",
    "name": "platform/packages/apps/CarrierConfig",
    "path": "packages/apps/CarrierConfig",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "assets",
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "f0a9f0e262e8f250b87acc2ef0c9844e94950111",
    "name": "platform/packages/apps/CellBroadcastReceiver",
    "path": "packages/apps/CellBroadcastReceiver",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "flags",
      "proto",
      "res",
      "src",
      "sysconfig",
      "tests/testapp",
      "tests/unit"
    ]
  },
  {
    "commit": "4568ed0bc0a62f71d4126503ef92a91f42a22c4e",
    "name": "platform/packages/apps/DocumentsUI",
    "path": "packages/apps/DocumentsUI",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "app-perf-tests",
      "recyclerview_selection/Android.bp",
      "recyclerview_selection/AndroidManifest.xml",
      "recyclerview_selection/TEST_MAPPING",
      "recyclerview_selection/res",
      "recyclerview_selection/src",
      "res",
      "src",
      "tests/Android.bp",
      "tests/AndroidManifest.xml",
      "tests/AndroidManifestUnitTests.xml",
      "tests/AndroidTest.xml",
      "tests/assets",
      "tests/common",
      "tests/functional",
      "tests/jarjar-rules.txt",
      "tests/lint-baseline-unit.xml",
      "tests/lint-baseline.xml",
      "tests/res",
      "tests/unit"
    ]
  },
  {
    "commit": "1e17ffd9ab78c743dd2690ae73439db17c759ead",
    "name": "platform/packages/apps/EmergencyInfo",
    "path": "packages/apps/EmergencyInfo",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "EmergencyGestureAction",
      "EmergencyGestureContentProvider",
      "res",
      "src",
      "tests/common",
      "tests/unit"
    ]
  },
  {
    "commit": "dcb981579cbbe74a817ecbaf97e7b924be0cdaa0",
    "name": "platform/packages/apps/ManagedProvisioning",
    "path": "packages/apps/ManagedProvisioning",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "aconfig",
      "proto",
      "res",
      "src",
      "tests/instrumentation"
    ]
  },
  {
    "commit": "c024bf5d7505001a59c904e96cd1b9b70dce31b3",
    "name": "platform/packages/apps/PhoneCommon",
    "path": "packages/apps/PhoneCommon",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src"
    ]
  },
  {
    "commit": "fe8d01bb832962ecda95df428cf3271c2f5edd60",
    "name": "platform/packages/apps/Test/connectivity",
    "path": "packages/apps/Test/connectivity",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "PMC",
      "UID"
    ]
  },
  {
    "commit": "958957ee3011541f2622b93223abd38071147d3f",
    "name": "platform/packages/apps/Traceur",
    "path": "packages/apps/Traceur",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src",
      "src_common",
      "uitests"
    ]
  },
  {
    "commit": "d726afd01e0189180f2e4c61b6c47c556db372da",
    "name": "platform/packages/apps/TvSettings",
    "path": "packages/apps/TvSettings",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Settings/Android.bp",
      "Settings/AndroidManifest-debug.xml",
      "Settings/AndroidManifest-lib.xml",
      "Settings/AndroidManifest.xml",
      "Settings/NOTICE",
      "Settings/com.android.tv.settings.xml",
      "Settings/proguard.flags",
      "Settings/res",
      "Settings/res-twopanel",
      "Settings/src",
      "SettingsAPI",
      "TwoPanelSettingsLib/Android.bp",
      "TwoPanelSettingsLib/AndroidManifest.xml",
      "TwoPanelSettingsLib/res",
      "TwoPanelSettingsLib/src"
    ]
  },
  {
    "commit": "0425e08d6e51719b4f582150b9950d2c2cd43cb0",
    "name": "platform/packages/apps/TvSystemUI",
    "path": "packages/apps/TvSystemUI",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src",
      "tests/Android.bp",
      "tests/AndroidManifest.xml",
      "tests/AndroidTest.xml",
      "tests/src"
    ]
  },
  {
    "commit": "4bf3dbecdfbe7a8d7b1f9721aae72565bed1dedd",
    "name": "platform/packages/modules/AdServices",
    "path": "packages/modules/AdServices",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "adservices/apk/AdExtServicesManifest.xml",
      "adservices/apk/Android.bp",
      "adservices/apk/AndroidManifest.xml",
      "adservices/apk/EmptyManifest.xml",
      "adservices/apk/assets",
      "adservices/apk/com.android.adservices.api.pk8",
      "adservices/apk/com.android.adservices.api.x509.pem",
      "adservices/apk/jarjar_rules.txt",
      "adservices/apk/java",
      "adservices/apk/lint-baseline-AdServices-core.xml",
      "adservices/apk/lint-baseline-AdServicesLib.xml",
      "adservices/apk/preinstalled-packages-com.android.adservices.api.xml",
      "adservices/apk/publicres",
      "adservices/apk/res",
      "adservices/clients",
      "adservices/flags",
      "adservices/framework",
      "adservices/libraries/cobalt/Android.bp",
      "adservices/libraries/cobalt/AndroidManifest.xml",
      "adservices/libraries/cobalt/java",
      "adservices/libraries/cobalt/proto",
      "adservices/libraries/cobalt/schemas",
      "adservices/libraries/collectors-helper/adservices/Android.bp",
      "adservices/libraries/collectors-helper/adservices/src",
      "adservices/libraries/device-collectors",
      "adservices/libraries/health",
      "adservices/linter",
      "adservices/service",
      "adservices/service-core",
      "adservices/tests/Android.bp",
      "adservices/tests/cts/Android.bp",
      "adservices/tests/cts/AndroidManifest.xml",
      "adservices/tests/cts/AndroidManifestDebuggable.xml",
      "adservices/tests/cts/AndroidManifestDebuggableExtServices.xml",
      "adservices/tests/cts/AndroidManifestExtServices.xml",
      "adservices/tests/cts/AndroidManifestExtServicesRvc.xml",
      "adservices/tests/cts/AndroidManifestRoot.xml",
      "adservices/tests/cts/AndroidTest.ExtServices.xml",
      "adservices/tests/cts/AndroidTest.ExtServicesRvc.xml",
      "adservices/tests/cts/AndroidTest.Root.xml",
      "adservices/tests/cts/AndroidTest.xml",
      "adservices/tests/cts/AndroidTestDebuggable.ExtServices.xml",
      "adservices/tests/cts/AndroidTestDebuggable.xml",
      "adservices/tests/cts/EmptyManifest.xml",
      "adservices/tests/cts/assets",
      "adservices/tests/cts/lint-baseline-adextservices-debuggabletestcases.xml",
      "adservices/tests/cts/lint-baseline-adextservices-devicetestcases.xml",
      "adservices/tests/cts/lint-baseline-testutility.xml",
      "adservices/tests/cts/src",
      "adservices/tests/cts/ui/libs",
      "adservices/tests/perf",
      "adservices/tests/test-util",
      "adservices/tests/unittest/fixtures",
      "apex/Android.bp",
      "apex/com.android.adservices.avbpubkey",
      "apex/com.android.adservices.pem",
      "apex/com.android.adservices.pk8",
      "apex/com.android.adservices.x509.pem",
      "apex/manifest.json",
      "sdksandbox/Android.bp",
      "sdksandbox/SdkSandbox",
      "sdksandbox/TEST_MAPPING",
      "sdksandbox/flags",
      "sdksandbox/framework",
      "sdksandbox/service",
      "sdksandbox/tests/Android.bp",
      "sdksandbox/tests/keys",
      "sdksandbox/tests/manual-test-apps/SdkSandboxClient",
      "sdksandbox/tests/manual-test-apps/SdkSandboxCodeProvider",
      "sdksandbox/tests/manual-test-apps/sdkinterfaces",
      "sdksandbox/tests/perf",
      "sdksandbox/tests/test-apps/EmptyProvider",
      "sdksandbox/tests/test_service_jarjar_rules.txt",
      "sdksandbox/tests/testutils/Android.bp",
      "sdksandbox/tests/testutils/device-side",
      "sdksandbox/tests/testutils/host-side",
      "sdksandbox/tests/testutils/side-less",
      "shared/libraries",
      "shared/testing-libraries",
      "apex/permissions"
    ]
  },
  {
    "commit": "85ee215beafd0236559a12b8764d6f78421db215",
    "name": "platform/packages/modules/AppSearch",
    "path": "packages/modules/AppSearch",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apk",
      "flags",
      "framework",
      "safeparcel-processor",
      "service"
    ]
  },
  {
    "commit": "4a67922f3276adcdd46642957ba6e53114a3625a",
    "name": "platform/packages/modules/DeviceLock",
    "path": "packages/modules/DeviceLock",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex",
      "flags",
      "framework",
      "DeviceLockController/Android.bp",
      "DeviceLockController/AndroidManifest.xml",
      "DeviceLockController/AndroidManifestBase.xml",
      "DeviceLockController/NOTICE",
      "DeviceLockController/lint-baseline.xml",
      "DeviceLockController/proguard.flags",
      "DeviceLockController/proto",
      "DeviceLockController/res",
      "DeviceLockController/src",
      "DeviceLockController/sysconfig",
      "permissions",
      "service"
    ]
  },
  {
    "commit": "694f4c1a10811ed8873e79cf88df009731797469",
    "name": "platform/packages/modules/ExtServices",
    "path": "packages/modules/ExtServices",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "flags",
      "java/res",
      "java/src",
      "java/tests/Android.bp",
      "java/tests/AndroidManifest.xml",
      "java/tests/AndroidTest-sminus.xml",
      "java/tests/AndroidTest-tplus.xml",
      "java/tests/src",
      "jni",
      "native/Android.bp",
      "native/ImageHashManager.cpp",
      "native/ImageHashManager.h",
      "native/pHash/array2d.h",
      "native/pHash/fast_dct-inl.h",
      "native/pHash/fast_dct.h",
      "native/pHash/phash_config.h",
      "native/pHash/phash_fingerprinter.cpp",
      "native/pHash/phash_fingerprinter.h"
    ]
  },
  {
    "commit": "65992e2d6687807024f1d7d8dbae1f5c02c032b3",
    "name": "platform/packages/modules/GeoTZ",
    "path": "packages/modules/GeoTZ",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "s2storage/Android.bp",
      "s2storage/src"
    ]
  },
  {
    "commit": "a292a16a8ac82667b65d763c00fa935cc44e9925",
    "name": "platform/packages/modules/HealthFitness",
    "path": "packages/modules/HealthFitness",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex/Android.bp",
      "apex/com.android.healthfitness.avbpubkey",
      "apex/com.android.healthfitness.pem",
      "apex/com.android.healthfitness.pk8",
      "apex/com.android.healthfitness.x509.pem",
      "apex/manifest.json",
      "flags",
      "framework/Android.bp",
      "framework/api",
      "framework/jarjar-rules.txt",
      "framework/java",
      "framework/lint-baseline.xml",
      "service/Android.bp",
      "service/api",
      "service/jarjar-rules.txt",
      "service/java",
      "service/proguard.flags",
      "service/proto/backuprestore",
      "service/proto/phr/Android.bp",
      "service/proto/phr/fhir_spec_extractor.py",
      "service/proto/phr/fhir_spec_utils.py",
      "service/proto/phr/fhirspec.proto",
      "service/proto/phr/generate_fhir_spec.py",
      "service/proto/serialization",
      "apex/permissions",
      "apk/.gitignore",
      "apk/Android.bp",
      "apk/AndroidManifest.xml",
      "apk/HealthPermissionsManifest.xml",
      "apk/ManageHealthDataManifest.xml",
      "apk/ManageHealthPermissionsManifest.xml",
      "apk/OWNERS",
      "apk/StartCloudBackupAndRestoreSettingsManifest.xml",
      "apk/StartOnboardingManifest.xml",
      "apk/com.android.healthconnect.controller.pk8",
      "apk/com.android.healthconnect.controller.x509.pem",
      "apk/lint-baseline.xml",
      "apk/proguard.flags",
      "apk/res",
      "apk/src",
      "apk/sysconfig",
      "backuprestore/Android.bp",
      "backuprestore/AndroidManifest.xml",
      "backuprestore/OWNERS",
      "backuprestore/PermissionsManifest.xml",
      "backuprestore/com.android.health.connect.backuprestore.pk8",
      "backuprestore/com.android.health.connect.backuprestore.x509.pem",
      "backuprestore/src",
      "backuprestore/sysconfig"
    ]
  },
  {
    "commit": "5c58f82cc230a9a4e22c80d6eaec62dffaec4444",
    "name": "platform/packages/modules/IPsec",
    "path": "packages/modules/IPsec",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex/Android.bp",
      "apex/apex_manifest.json",
      "apex/com.android.ipsec.avbpubkey",
      "apex/com.android.ipsec.pem",
      "apex/com.android.ipsec.pk8",
      "apex/com.android.ipsec.x509.pem",
      "api",
      "flags",
      "src",
      "tests/iketests"
    ]
  },
  {
    "commit": "d194f8ada2cab31b8487fb3aaac6fd383fc7e07f",
    "name": "platform/packages/modules/NpuManager",
    "path": "packages/modules/NpuManager",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "flags",
      "framework",
      "ndk",
      "apex",
      "service"
    ]
  },
  {
    "commit": "cc93f1e4164d0a4bb76dd277abc221f4eaf32efb",
    "name": "platform/packages/modules/OnDevicePersonalization",
    "path": "packages/modules/OnDevicePersonalization",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex",
      "common",
      "federatedcompute/Android.bp",
      "federatedcompute/jni",
      "federatedcompute/src",
      "flags",
      "framework",
      "pluginlib",
      "src",
      "systemservice",
      "federatedcompute/apk"
    ]
  },
  {
    "commit": "8b3abe8eebc0e97890977d9658038f4966aa7df6",
    "name": "platform/packages/modules/Profiling",
    "path": "packages/modules/Profiling",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "aidl",
      "anomaly-detector/aidl",
      "anomaly-detector/flags",
      "anomaly-detector/framework",
      "anomaly-detector/proto",
      "anomaly-detector/service",
      "flags",
      "framework",
      "util",
      "apex",
      "service"
    ]
  },
  {
    "commit": "d88e2305f9186661fe75ee2f00c8b250a76fdabe",
    "name": "platform/packages/modules/RemoteKeyProvisioning",
    "path": "packages/modules/RemoteKeyProvisioning",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "app/Android.bp",
      "app/AndroidManifest.xml",
      "app/TEST_MAPPING",
      "app/aidl",
      "app/lint-baseline.xml",
      "app/proguard.flags",
      "app/res",
      "app/src",
      "app/sysconfig",
      "flags",
      "system-server/Android.bp",
      "system-server/TEST_MAPPING",
      "system-server/api",
      "system-server/src",
      "util",
      "apex"
    ]
  },
  {
    "commit": "f48a4ddf92701d4dfba1b27d244a4a1e74c2d3ad",
    "name": "platform/packages/modules/RuntimeI18n",
    "path": "packages/modules/RuntimeI18n",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex"
    ]
  },
  {
    "commit": "5ff13b504b9c011408cbb7bdf044e9595267a3e0",
    "name": "platform/packages/modules/Scheduling",
    "path": "packages/modules/Scheduling",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex",
      "framework",
      "service"
    ]
  },
  {
    "commit": "3d78a2fea79f2a17831e6fad8c257deaeb8dee85",
    "name": "platform/packages/modules/SdkExtensions",
    "path": "packages/modules/SdkExtensions",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "derive_classpath",
      "derive_sdk",
      "gen_sdk",
      "java",
      "javatests/Android.bp",
      "javatests/com/android/sdkext/extensions/Android.bp",
      "javatests/com/android/sdkext/extensions/SdkExtensionsHostTest.java",
      "javatests/com/android/sdkext/extensions/apexes",
      "javatests/com/android/sdkext/extensions/sdkextensions-e2e-tests.xml",
      "javatests/com/android/sdkext/extensions/apps"
    ]
  },
  {
    "commit": "d83f23a96fbe6d68942d8d7245dbd3db91e9c711",
    "name": "platform/packages/modules/Telephony",
    "path": "packages/modules/Telephony",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex",
      "flags",
      "framework",
      "libs/libphonenumber",
      "telecom/flags",
      "telecom/framework",
      "telecom/service",
      "tests/mcts"
    ]
  },
  {
    "commit": "7cffa93ccbe6c25182cf27a46eeba75f4f9f551f",
    "name": "platform/packages/modules/UprobeStats",
    "path": "packages/modules/UprobeStats",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "bpf",
      "config",
      "daemon",
      "flags",
      "framework",
      "lib",
      "service",
      "apex",
      "bpfloader",
      "bpf_progs"
    ]
  },
  {
    "commit": "551872e35de50df9fa39fa871129db512c18565b",
    "name": "platform/packages/modules/WebApp",
    "path": "packages/modules/WebApp",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "flags",
      "framework",
      "apex",
      "service",
      "template"
    ]
  },
  {
    "commit": "3dd6a7c4014223aa13b787c82c7cbd14d989aca3",
    "name": "platform/packages/providers/BlockedNumberProvider",
    "path": "packages/providers/BlockedNumberProvider",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "5c74ede4c4573d0843968f067f58fcecac3c4f0d",
    "name": "platform/packages/providers/CalendarProvider",
    "path": "packages/providers/CalendarProvider",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "3788ede92ad2ab5f69d7d5da740c1e449980949c",
    "name": "platform/packages/providers/ContactsProvider",
    "path": "packages/providers/ContactsProvider",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "res",
      "src",
      "test_common",
      "tests"
    ]
  },
  {
    "commit": "20f95c184971841ba7c7fa9a74eeb0bb8cd5d8b2",
    "name": "platform/packages/providers/DownloadProvider",
    "path": "packages/providers/DownloadProvider",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "flags",
      "res",
      "src",
      "tests/Android.bp",
      "tests/AndroidManifest.xml",
      "tests/AndroidTest.xml",
      "tests/src"
    ]
  },
  {
    "commit": "773ea53100eeb1e97c223826ca59054a58cd74ff",
    "name": "platform/packages/providers/MediaProvider",
    "path": "packages/providers/MediaProvider",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "apex/Android.bp",
      "apex/apex_manifest.json",
      "apex/com.android.mediaprovider.avbpubkey",
      "apex/com.android.mediaprovider.pem",
      "apex/com.android.mediaprovider.pk8",
      "apex/com.android.mediaprovider.x509.pem",
      "apex/framework",
      "cli",
      "errorprone",
      "jni",
      "legacy",
      "pdf/framework",
      "pdf/framework-v",
      "photopicker/Android.bp",
      "photopicker/AndroidManifest.xml",
      "photopicker/TEST_MAPPING",
      "photopicker/framework",
      "photopicker/lint",
      "photopicker/lint-baseline.xml",
      "photopicker/res",
      "photopicker/schemas",
      "photopicker/src",
      "photopicker/sysconfig",
      "res",
      "src",
      "tests/Android.bp",
      "tests/AndroidManifest.xml",
      "tests/AndroidTest.xml",
      "tests/client",
      "tests/jarjar-rules.txt",
      "tests/main_res",
      "tests/photopicker_res",
      "tests/res",
      "tests/src",
      "tests/test_app",
      "tests/utils",
      "apex/permissions"
    ]
  },
  {
    "commit": "013b803626164c026025897b7dec45521c2cccab",
    "name": "platform/packages/providers/TelephonyProvider",
    "path": "packages/providers/TelephonyProvider",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "assets",
      "proto",
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "e11258b65bdf0091dfc440c2b2e2c782778688c3",
    "name": "platform/packages/services/CrossDeviceSync",
    "path": "packages/services/CrossDeviceSync",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lib",
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "11439f93ca71ab87be387f24eff40b2c506fda0c",
    "name": "platform/packages/services/DeviceAsWebcam",
    "path": "packages/services/DeviceAsWebcam",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "tests"
    ]
  },
  {
    "commit": "45cd4c9d78a5eabb5a40c7d4e665ff6e534e4ca5",
    "name": "platform/packages/services/Mtp",
    "path": "packages/services/Mtp",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "perf_tests",
      "res",
      "src",
      "tests"
    ]
  },
  {
    "commit": "2353977dc28ff88d3cdc1ec636fa9c3251d2ff86",
    "name": "platform/packages/services/Telecomm",
    "path": "packages/services/Telecomm",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "TelecomUi",
      "legacy-src",
      "proto",
      "res",
      "shim",
      "src",
      "tests",
      "flags"
    ]
  },
  {
    "commit": "d4d262fa07952995d9fa4913d10365d878c8fdcf",
    "name": "platform/prebuilts/android-emulator",
    "path": "prebuilts/android-emulator",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "trusty-x86_64"
    ]
  },
  {
    "commit": "4d55b55cd444c97bc021d35316010f57f62d7844",
    "name": "platform/prebuilts/bundletool",
    "path": "prebuilts/bundletool",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "6d1683899a1fbb8e46424a231412b7cfe0151e28",
    "name": "platform/prebuilts/clang-tools",
    "path": "prebuilts/clang-tools",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "509a65c09c81464e0d1a29d9d7d6d0ab3cec8655",
    "name": "platform/prebuilts/maven_repo/bumptech",
    "path": "prebuilts/maven_repo/bumptech",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "com"
    ]
  },
  {
    "commit": "07e4c9cedacc5d60276ab061f52684f57d7dc87e",
    "name": "platform/prebuilts/ndk",
    "path": "prebuilts/ndk",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "current"
    ]
  },
  {
    "commit": "65fe8f9f5c6769d35f91fe67b786b767a2db5249",
    "name": "platform/prebuilts/r8",
    "path": "prebuilts/r8",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "src"
    ]
  },
  {
    "commit": "9158169c8c48a3f16dae517b8a44318ce3e0890a",
    "name": "platform/prebuilts/remoteexecution-client",
    "path": "prebuilts/remoteexecution-client",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "live"
    ]
  },
  {
    "commit": "ee8b48b5344dd3a50eae5a87cdc1f46b7afd4263",
    "name": "platform/system/authgraph",
    "path": "system/authgraph",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "boringssl",
      "core",
      "derive",
      "hal",
      "tests",
      "wire"
    ]
  },
  {
    "commit": "60f086effe11d1afb248ff3c9a2a780b66a34506",
    "name": "platform/system/bpfprogs",
    "path": "system/bpfprogs",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "locks"
    ]
  },
  {
    "commit": "0499c160c1c1d6ffa6b3fe3019de692bc8875458",
    "name": "platform/system/ca-certificates",
    "path": "system/ca-certificates",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "files",
      "wfa_certs"
    ]
  },
  {
    "commit": "827aad0d89d0615bcdebc3dd93d1e8ae1c19f36d",
    "name": "platform/system/fs/casefolding_remover",
    "path": "system/fs/casefolding_remover",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "android",
      "src"
    ]
  },
  {
    "commit": "5b5e75b5bda9fccbc3132e9624cb25286babdaac",
    "name": "platform/system/gatekeeper",
    "path": "system/gatekeeper",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "rust"
    ]
  },
  {
    "commit": "43f41cd5506656e937d332d60cd725764dfca716",
    "name": "platform/system/libueventd-rs",
    "path": "system/libueventd-rs",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "examples",
      "src"
    ]
  },
  {
    "commit": "3d6286bdd07ec68ee6a411381e56c1aaa6e11247",
    "name": "platform/system/liburingutils",
    "path": "system/liburingutils",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "src"
    ]
  },
  {
    "commit": "c3601e823bd07c9c190f67e2f9bc7486e4978328",
    "name": "platform/system/memory/lmkd",
    "path": "system/memory/lmkd",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "include",
      "libpsi",
      "libpsi_rs",
      "tests"
    ]
  },
  {
    "commit": "cf66bc31a4002e6f786da7c5a45e4088d19530ed",
    "name": "platform/system/memory/mmd",
    "path": "system/memory/mmd",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "aidl",
      "src"
    ]
  },
  {
    "commit": "c074ff08c0a82e1fdc04178d5b7ffc15c791d3a7",
    "name": "platform/system/secretkeeper",
    "path": "system/secretkeeper",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "client",
      "comm",
      "core",
      "dice_policy/Android.bp",
      "dice_policy/building",
      "dice_policy/src",
      "hal"
    ]
  },
  {
    "commit": "8e67454ae22607f22d289d7458d383eabc7c2db2",
    "name": "platform/system/see/authmgr",
    "path": "system/see/authmgr",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "e3011285b9883a300491d7bc45a12581e281287c",
    "name": "platform/system/teeui",
    "path": "system/teeui",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "libteeui"
    ]
  },
  {
    "commit": "4a27dd13adf9846e12d585d6fe99a375ebb58396",
    "name": "platform/system/tools/mkbootimg",
    "path": "system/tools/mkbootimg",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "gki",
      "include",
      "rust",
      "tests"
    ]
  },
  {
    "commit": "4617f7e28793f979153f3b088a79ba796e0268b3",
    "name": "platform/test/mlts/benchmark",
    "path": "test/mlts/benchmark",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "crashtest",
      "dogfood",
      "jni",
      "res",
      "sl_prebuilt",
      "src"
    ]
  },
  {
    "commit": "cbb1ae5cfde49ed06ccf4afaa2fae1054364d4f3",
    "name": "platform/test/mlts/models",
    "path": "test/mlts/models",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "assets"
    ]
  },
  {
    "commit": "886725543e4078f87fc87aabb90b1871c7536b03",
    "name": "platform/test/vts",
    "path": "test/vts",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "libvtswidevine",
      "vts_hal_hidl_target",
      "tools/vts-core-tradefed"
    ]
  },
  {
    "commit": "61df1bdbc6b596dafeee213c04f5d2c8d7131b98",
    "name": "platform/test/vts-testcase/hal",
    "path": "test/vts-testcase/hal",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "treble/Android.bp",
      "treble/vintf"
    ]
  },
  {
    "commit": "973ab5876b89b0bf4b93a1620397b27183afaa6d",
    "name": "platform/tools/content_addressed_storage/prebuilts",
    "path": "tools/content_addressed_storage/prebuilts",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "bb2d5f519bd0bf57641d74f40c12bab281423781",
    "name": "platform/tools/deviceinfra/prebuilts",
    "path": "tools/deviceinfra/prebuilts",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "08aac91132a0b7109130271c27717b07f80ff8c3",
    "name": "platform/tools/doc_generation",
    "path": "tools/doc_generation",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": []
  },
  {
    "commit": "559446380c3e2cf01c82608897ba5a246996fe5c",
    "name": "platform/tools/rootcanal",
    "path": "tools/rootcanal",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "desktop",
      "hal",
      "include",
      "lib",
      "model",
      "net",
      "packets",
      "proto",
      "py",
      "rust",
      "test"
    ]
  },
  {
    "commit": "e4e7ba1dabe64f33b9894624e43763bd8a3cbca5",
    "name": "platform/tools/security",
    "path": "tools/security",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "remote_provisioning/hwtrust",
      "fuzzing/libFuzzer_mte_crash_handler"
    ]
  },
  {
    "commit": "fc6621351d8d17286870813678c96bf81555c1ad",
    "name": "platform/tools/test/mobly_extensions",
    "path": "tools/test/mobly_extensions",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "coverage",
      "mobly_sponge_converter",
      "resultdb_uploader/Android.bp",
      "resultdb_uploader/prebuilt",
      "resultdb_uploader/resultdb_uploader_wrapper.py",
      "tools"
    ]
  },
  {
    "commit": "9f80db7a085746f38c9fd5c2f79cd3adc9a1d709",
    "name": "trusty/device/arm/generic-arm64",
    "path": "trusty/device/arm/generic-arm64",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "project/avf"
    ]
  },
  {
    "commit": "6b48a3e39a94093a693914779e9f9aa9859f5366",
    "name": "trusty/device/common",
    "path": "trusty/device/common",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "f8d8267f8b20d05b1d3620bdcaffb5692f142b0d",
    "name": "trusty/device/desktop",
    "path": "trusty/device/desktop",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "e9e36b2fc426938011f5bfb9ee8f018bf541c864",
    "name": "trusty/device/x86/generic-x86_64",
    "path": "trusty/device/x86/generic-x86_64",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "7fe664f48ae35c1d13bbdc67ed94d3ed6627b91e",
    "name": "trusty/host/common",
    "path": "trusty/host/common",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "scripts"
    ]
  },
  {
    "commit": "837ece72a3c50f454dfaf3bb86d5ac2e843c142b",
    "name": "trusty/lk/trusty",
    "path": "trusty/kernel",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "app/btitest",
      "app/pacbench",
      "app/pactest",
      "app/stdcalltest",
      "include",
      "lib/app_manifest/include",
      "lib/arm_ffa",
      "lib/arm_trng",
      "lib/backtrace/elf_sym.h",
      "lib/backtrace/include",
      "lib/dtb_embedded",
      "lib/dtb_service",
      "lib/extmem",
      "lib/ktipc/include",
      "lib/ktipc/test/include",
      "lib/libc-ext",
      "lib/libc-trusty/include",
      "lib/memlog",
      "lib/mmutest",
      "lib/pmu",
      "lib/psci_boot",
      "lib/rand",
      "lib/shared/binder_discover",
      "lib/shared/device_tree/client/include",
      "lib/shared/device_tree/service/include",
      "lib/shared/ibinder",
      "lib/shared/peer_id",
      "lib/sm/include",
      "lib/sm/rust",
      "lib/sm/test",
      "lib/smc/include",
      "lib/syscall/include",
      "lib/tcrypto",
      "lib/trusty",
      "lib/ubsan",
      "lib/unittest",
      "lib/version",
      "lib/vmm_obj_service/include",
      "platform/generic-arm64/debug.h",
      "platform/generic-arm64/include",
      "platform/generic-arm64/smc.h",
      "platform/vexpress-a15",
      "services/smc"
    ]
  },
  {
    "commit": "b53363e45aad47c92ec1ecc4b94881727c13ad8d",
    "name": "trusty/app/authmgr",
    "path": "trusty/user/app/authmgr",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "5381caec069f0c7059fae0b6985806e53e4b887b",
    "name": "trusty/app/avb",
    "path": "trusty/user/app/avb",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "ipc",
      "test"
    ]
  },
  {
    "commit": "df8e46e3f6fc866fe366970b33df407d465777b9",
    "name": "trusty/app/cast-auth",
    "path": "trusty/user/app/cast-auth",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "ff29a3a01fb0d0ea1e4eea76ab58a0168c54c45d",
    "name": "trusty/app/confirmationui",
    "path": "trusty/user/app/confirmationui",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "7ac7c2862317c448ba88ce2d7dfcae0db4765174",
    "name": "trusty/app/gatekeeper",
    "path": "trusty/user/app/gatekeeper",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "71fa167a63842d10d26cc4f51537de54b6eec3eb",
    "name": "trusty/app/keymaster",
    "path": "trusty/user/app/keymaster",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "48faccf3fd79ef3bc23171ed9373965e8c302b4c",
    "name": "trusty/app/keymint",
    "path": "trusty/user/app/keymint",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "see/keymint/libs/lib-hwcrypto-thal"
    ]
  },
  {
    "commit": "78e3bcb17ec4a0fc56af8f95c8db8e3983b52d1c",
    "name": "trusty/app/sample",
    "path": "trusty/user/app/sample",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "hwcryptohal/common"
    ]
  },
  {
    "commit": "fadb44b38b58a203a2d3e751e97b2dfbcf6a4861",
    "name": "trusty/app/secretkeeper",
    "path": "trusty/user/app/secretkeeper",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "Android.bp"
    ]
  },
  {
    "commit": "da6843dc5aaf97dfce448415a4c943186a8c65f7",
    "name": "trusty/app/storage",
    "path": "trusty/user/app/storage",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lib_internal",
      "rpmb_dev",
      "rpmb_super_block_mac",
      "scudo",
      "test/block_host_test",
      "test/common",
      "test/storage_host_test"
    ]
  },
  {
    "commit": "165d46c463bd22524a7d33d177bf7f35dad46bf5",
    "name": "trusty/lib",
    "path": "trusty/user/base",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "app/acvp",
      "app/apploader/app_manifest_parser.h",
      "app/apploader/app_version.h",
      "app/cfi-test/include",
      "app/coverage",
      "app/crash-test",
      "app/hwaes-benchmark",
      "app/line-coverage",
      "app/metrics/client.h",
      "app/metrics/consumer.h",
      "app/swaes-benchmark",
      "experimental/interface",
      "experimental/lib/dmaimporter",
      "experimental/lib/membuffshare/include",
      "experimental/lib/tidl/include",
      "host/unittest",
      "include",
      "interface/acvp",
      "interface/apploader",
      "interface/arm_ffa",
      "interface/authmgr-dice-policy-matching",
      "interface/authmgr-handover/aidl",
      "interface/binder_accessor",
      "interface/boot_done/IBootDone.aidl",
      "interface/boot_done/generated",
      "interface/commservice",
      "interface/coverage",
      "interface/device_tree",
      "interface/hwaes",
      "interface/hwbcc",
      "interface/hwkey",
      "interface/hwrng",
      "interface/hwwsk",
      "interface/keybox",
      "interface/keymaster",
      "interface/line-coverage",
      "interface/metrics",
      "interface/provisioning",
      "interface/secure_dpu",
      "interface/secure_fb",
      "interface/secure_storage/cpp",
      "interface/smc",
      "interface/spi",
      "interface/stats/tz",
      "interface/stats_setter",
      "interface/storage",
      "interface/system_state",
      "interface/trusty_cli",
      "interface/vm_attestation",
      "lib/apploader_package",
      "lib/apploader_policy_engine",
      "lib/coverage",
      "lib/dlmalloc/include",
      "lib/dlmalloc/test/include",
      "lib/googletest",
      "lib/hwaes",
      "lib/hwasan/hwasan.h",
      "lib/hwasan/include",
      "lib/hwbcc/client",
      "lib/hwbcc/common",
      "lib/hwbcc/rust",
      "lib/hwbcc/srv",
      "lib/hwkey",
      "lib/hwwsk",
      "lib/keybox",
      "lib/keymaster/include",
      "lib/libc-trusty/Android.bp",
      "lib/libc-trusty/host",
      "lib/libc-trusty/include",
      "lib/libc-trusty/time.c",
      "lib/libstdc++-trusty/Android.bp",
      "lib/libstdc++-trusty/include",
      "lib/line-coverage",
      "lib/metrics_atoms",
      "lib/protobuf",
      "lib/pvmdice",
      "lib/rng",
      "lib/scudo/test/include",
      "lib/secure_dpu",
      "lib/secure_fb/include",
      "lib/secure_fb/srv",
      "lib/service_manager/tests/aidl",
      "lib/smc/include",
      "lib/spi",
      "lib/stats",
      "lib/storage",
      "lib/system_state",
      "lib/tipc/Android.bp",
      "lib/tipc/include",
      "lib/tipc/rust",
      "lib/tipc/test/include",
      "lib/tipc/tipc.c",
      "lib/tipc/tipc_priv.h",
      "lib/tipc/tipc_srv.c",
      "lib/tipc/uds",
      "lib/trusted_hal_stability_ext/cpp",
      "lib/trusty-sys",
      "lib/trusty-types-sys",
      "lib/uirq/include",
      "lib/unittest",
      "lib/vmm_obj"
    ]
  },
  {
    "commit": "b9615896a07dfe0c227cdc8f6a522b9a3788d086",
    "name": "trusty/user/desktop",
    "path": "trusty/user/desktop",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "lib/desktop_trusty_build_params/Android.bp",
      "lib/desktop_trusty_build_params/desktop_trusty_build_params_rules.mk"
    ]
  },
  {
    "commit": "93e3ca36bc59e5d357b226e4e5254f8e478213f2",
    "name": "trusty/vendor/google/aosp",
    "path": "trusty/vendor/google/aosp",
    "purpose": "Pinned original provider and physical source inputs for the retained ordinary native pair graph",
    "sparse_paths": [
      "scripts"
    ]
  },
  {
    "commit": "9d71d482603aac054815958c9834ae1cd036f024",
    "name": "platform/external/mime-support",
    "path": "external/mime-support",
    "purpose": "Pinned Debian MIME data and original generators required by framework MIME inputs",
    "sparse_paths": [
      "Android.bp",
      "LICENSE",
      "mime.types",
      "mime.types-alt"
    ]
  },
  {
    "commit": "87b8030626b04e16a7efbe2e15c673e2548eef52",
    "name": "platform/external/android-key-attestation",
    "path": "external/android-key-attestation",
    "purpose": "Pinned key attestation library required by the selected original CTS device-info and keystore modules",
    "sparse_paths": [
      "Android.bp",
      "LICENSE",
      "server/src/main/java"
    ]
  },
  {
    "commit": "d2f888409e224dae9e9d4b02fa3d1b2e8b72d374",
    "name": "platform/external/wycheproof",
    "path": "external/wycheproof",
    "purpose": "Pinned original Wycheproof Java and keystore data required by the selected CTS keystore provider",
    "sparse_paths": [
      "Android.bp",
      "LICENSE",
      "java",
      "keystore-cts"
    ]
  },
  {
    "commit": "d67e4b09ff002069a025bfb232836eecab6dab52",
    "name": "platform/external/python/pyee",
    "path": "external/python/pyee",
    "purpose": "Pinned original pyee provider and implementation required by the retained bumble module",
    "sparse_paths": [
      "Android.bp",
      "LICENSE",
      "pyee"
    ]
  },
  {
    "commit": "225af0c6253316198738699de9041d1f28d0df44",
    "name": "platform/packages/apps/EyeDropper",
    "path": "packages/apps/EyeDropper",
    "purpose": "Pinned original framework aconfig provider and complete retained EyeDropper library inputs",
    "sparse_paths": [
      "flags",
      "res",
      "src"
    ]
  },
  {
    "commit": "71d564487c9b34f65961570073f037658e07eb06",
    "name": "platform/external/mksh",
    "path": "external/mksh",
    "purpose": "Exact Android 17 original shell and mkshrc providers required by the retained microdroid system image"
  },
  {
    "commit": "4da9987aca2eedf386d1e22e19994a1b0de53c45",
    "name": "platform/external/strace",
    "path": "external/strace",
    "purpose": "Exact Android 17 original strace provider and complete source tree required by the retained microdroid system image"
  },
  {
    "commit": "ac781dac6cf4026016f2dacf824b2f0b0fba91c2",
    "name": "platform/external/jmustache",
    "path": "external/jmustache",
    "purpose": "Exact original same-superproject JMustache provider and full source required by the retained WebApp production service",
    "sparse_paths": []
  },
  {
    "commit": "f91e18ccc73c0cce1194f3aef4a841c1a15003b3",
    "name": "platform/system/memory/libwrapfd",
    "path": "system/memory/libwrapfd",
    "purpose": "Exact original same-superproject wrapfd Rust and native buffer providers required by the retained NpuManager service",
    "sparse_paths": []
  },
  {
    "commit": "49d155f26586a540266fd854c868a067f6db9204",
    "name": "platform/external/android-browser-helper",
    "path": "external/android-browser-helper",
    "purpose": "Exact original same-superproject Android Browser Helper sources required by the retained WebApp production template",
    "sparse_paths": [
      "androidbrowserhelper/src/main"
    ]
  }
]"#;

fn validate_source_extension607(base: &Value, extended: &Value) -> Result<()> {
    let mut expected = base.clone();
    let projects = expected["projects"].as_array_mut().ok_or("pair source projects absent")?;
    if projects.len() != 225 {
        return fail("ordinary pair requires the exact 225-project base closure");
    }
    for (path, commit, subtree) in [
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/CameraITS"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/CtsVerifier"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/ForceStopHelperApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/SecurePlaybackTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "backported_fixes"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/activitycontext"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/dpmwrapper"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/eventlib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/harrier"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/accounts"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/adb"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/bluetooth"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/enterprise"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/multiuser"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/permissions"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/root"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/testapps"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/modules/usb"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/nene"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/performanceanalyzer"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/queryable"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/remoteaccountauthenticator"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/remotedpc"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/remoteframeworkclasses"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/testapisparser"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/testapisreflection"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/testapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/interactive/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/interactive/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/interactive/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/interactive/steps"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/util"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/util-axt/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/util-axt/lint-baseline.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/util-axt/protobuf-jarjar-rules.txt"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/util-axt/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/host-side"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "flags/tests"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "helpers"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appcompat/host"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/AdoptableTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/AppDataIsolationTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/AppSecurityHostTestCases.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/AppSecurityHostUnitTestCases.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/CorruptApkTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/DirectBootTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/InstantAppsTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/OverlayTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/PackageManagerTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/PermissionsTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/ResumeOnRebootTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/StorageTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/UseEmbeddedDexTests.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/assets"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/certs"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PackageInstallerPermissionRequestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps/StorageApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/CompilationTestCases.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/CtsCompilationTestCases.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/app_used_by_other_app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/assets"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/certs"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/scripts"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/status_checker_app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/app/SuspensionChecker"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/app/TestIme"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/inputmethodservice/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/inputmethodservice/deviceside/ime1"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/inputmethodservice/deviceside/lib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/test-apps/StaticSharedLibConsumerApp1"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/test-apps/StaticSharedLibConsumerApp3"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/test-apps/StaticSharedLibProviderApp1"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/test-apps/StaticSharedLibProviderApp7"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/test-apps/StaticSharedLibProviderAppRecursive"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/testdata/apex"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/testdata/apk/StagedInstallTestAppSamePackageNameAsApex.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/stagedinstall/testdata/apk/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/configs"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/express"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/lib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/statsd"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/telecom"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/utils"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/deviceutillegacy"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/hardware"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/helpers/core/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/helpers/core/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/helpers/interfaces"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/input"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/install"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/midi"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/rollback"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/runner"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/shim"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/testserver"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/usb"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "libs/vogar-expect"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibility"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/accessibilityservice/test-apps"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/AndroidManifest-lib.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/libctscamera2jni"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/lint-baseline.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/propertyTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/camera/utils"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/core"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/devicestate"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/fragment/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/fragment/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/fragment/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/fragment/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/fragment/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/fragment/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/AndroidTestTemplate.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/backgroundactivity"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/intent_tests"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/jetpack"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/shared"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/test-apps"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/testsdk35"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/framework/base/windowmanager/util"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/hiddenfrompickerime"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/legacyimeclienttestlib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/mocka11yime"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/mockime"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/mockimewithsubtypes"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/mocklargeresourceime"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/mockspellchecker"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/spellcheckingime"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/testapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/testlauncher"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/inputmethod/util"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/jdwp/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/jdwp/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/jdwp/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/jdwp/runner/device-side"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/media"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/jni"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/requirements"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/mediapc/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/net"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/security"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/sensor/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/sensor/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/sensor/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/sensor/jni"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/sensor/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/sensor/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/surfacecontrol"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/AssociationRevokedTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/CompanionDeviceTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/core"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/multidevice/client"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/multiprocess"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/noservices"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/uiautomation"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/companion/uicommon"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/AndroidManifest-pcc.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/AndroidTest-pcc.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/AppLockSupportedTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/BinderPermissionTestService"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/ContentUriTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsContentTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsDocumentContentTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsHeadlessApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsPackageManagerBroadcastTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsPackageManagerTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsResourcesTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/CtsWindowManagerTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/DeviceAdminTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/DirectBootUnawareTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/HelloWorldApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/IntentResolutionTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/MockLauncherApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/MockRestrictedApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/MotionPhotoCaptureApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/MultiArchApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/OnlyForLocationButtonApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/PackageChangedBroadcastReceiverApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/PackageChangedSharedUserIdTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/PackageChangedTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/PackagePropertyTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/PartiallyDirectBootAwareTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/QueryPackagesTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/SyncAccountAccessStubs"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/TestInstallerApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/TestShortcutApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/assets"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/data"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/emptytestapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/lib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/lint-baseline.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/content/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/LICENSE_CC_BY"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/AndroidManifest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/AndroidTest.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/TEST_MAPPING"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/helper"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/media/projection/src"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/os/assets"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/print"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/time"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/virtualdevice/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed/DynamicConfig.xml"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed/README"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-v-host/Android.bp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-v-host/README"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-v-host/res"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/lint"),
        ("external/apache-xml", "81c0feea7cb0987ae36811db43392c703576fb8f", "test"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "bl1"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "bl2"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "bl32/sp_min"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "bl32/tsp"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/arm"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/brcm"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/imx"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/marvell"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/nxp/ddr/phy-gen2"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/nxp/flexspi"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/renesas"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "drivers/scmi-msg"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/compiler-rt"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/debugfs"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/extensions"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/gpt_rme"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/psci"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/xlat_mpu"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/xlat_tables"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "lib/xlat_tables_v2"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/allwinner"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/amlogic"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/a5ds/a5ds_private.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/a5ds/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/arm_fpga"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/corstone700/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/diphda"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp/fvp_def.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp/fvp_private.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp_r"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp_ve/fvp_ve_def.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp_ve/fvp_ve_private.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/fvp_ve/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/juno/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/juno/juno_def.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/juno/juno_tzmp1_def.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/morello"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/n1sdp"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/rde1edge"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/rdn1edge"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/rdn2"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/rdv1"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/rdv1mc"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/sgi575"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/sgm775/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/board/tc"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/css/sgi"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/arm/css/sgm/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/brcm"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/hisilicon"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/imx7/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/imx7/picopi"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/imx7/warp7"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/imx8m"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/imx8qm"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/imx/imx8qx"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/intel"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/layerscape/board/ls1043/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/layerscape/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a3k"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/a70x0"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/a70x0_amc"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/a70x0_mochabin"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/a80x0"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/a80x0_mcbin"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/a80x0_puzzle"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/common/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/a8k/common/mss"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/armada/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/marvell/octeontx/otx2/t91/t9130"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/mediatek"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nvidia/tegra/drivers"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nvidia/tegra/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nvidia/tegra/soc"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/fip_handler"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/img_loadr"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/nv_storage"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/ocram"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/psci"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/setup"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/sip_svc"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/soc_errata"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/common/warm_reset"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/soc-ls1028a"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/nxp/soc-lx2160a"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/qemu/common/qemu_private.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/qemu/qemu"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/qemu/qemu_sbsa"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/qti"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/renesas/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/px30"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/rk3288/drivers"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/rk3288/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/rk3288/rk3288_def.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/rk3328"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/rk3368"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rockchip/rk3399"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/rpi"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/socionext/synquacer"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/socionext/uniphier/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/socionext/uniphier/uniphier.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/socionext/uniphier/uniphier_console.h"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/ti"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/xilinx/common"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/xilinx/versal"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/xilinx/zynqmp/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "plat/xilinx/zynqmp/pm_service"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "services"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "tools/cert_create/include"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "tools/encrypt_fw"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "tools/fiptool"),
        ("external/arm-trusted-firmware", "54fd6939e177f8ff529b10183254802c76df6d08", "tools/nxp/cert_create_helper"),
        ("external/auto", "d97ec6e9cc1ad7f282cdc14bddcbe4dd64cc0d1c", "factory"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "bcpkix"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "bcprov"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "repackaged"),
        ("external/bouncycastle", "c404048739e9a35cd51ad82906aadf910cca09dd", "repackaged_platform"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/flags"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/tools/classes_collector"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "tot"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/src"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/tests"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/base"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/build"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/buildtools"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/chrome"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/components"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/crypto"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/ipc"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/net"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/testing"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/abseil-cpp"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/anonymous_tokens"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/apache-portable-runtime"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/boringssl"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/brotli"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/ced"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/compiler-rt"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/cpu_features"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/fuzztest"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/google_benchmark"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/googletest"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/Android.bp"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/LICENSE"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/android"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/fuzzers"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/common"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/extra"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/i18n"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/io"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/samples"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/stubdata"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/test"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/icu/source/tools"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/jni_zero"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/libc++"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/libc++abi"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/libxml"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/llvm-libc"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/lss"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/metrics_proto"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/modp_b64"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/netty-tcnative"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/netty4"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/Android.bp"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/LICENSE"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/buildtools"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/contrib/rust-sdk/perfetto-sys"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/examples"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/gn"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/include"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/protos"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/src"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/perfetto/test"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/protobuf"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/quic_trace"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/re2/Android.bp"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/re2/LICENSE"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/re2/src/re2"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/re2/src/util"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/rust"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/simdutf"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zlib"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/Android.bp"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/LICENSE"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/build"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/contrib"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/doc"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/examples"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/lib"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/programs"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/tests/external_matchfinder.h"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/tests/fuzz"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/tests/loremOut.h"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/tests/regression"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/tests/seqgen.h"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/third_party/zstd/src/zlibWrapper"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/tools"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "stable/url"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "test_runner"),
        ("external/cronet", "e184145f12ee023d07372bd6db33341b671cee27", "android/java/shims"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "contrib"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "debugfs"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "e2fsck"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "ext2ed"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "include"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "lib"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "misc"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "resize"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "tests"),
        ("external/e2fsprogs", "3eb17241db7cd4408cc1bce9d25b602465ace8ff", "util"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "backends"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "config"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "debuginfod"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "libasm"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "libdw"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "libdwelf"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "libdwfl"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "libdwfl_stacktrace"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "libebl"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "src"),
        ("external/elfutils", "219c3a368b121307f2e05593cee89b8591cc40b9", "tests"),
        ("external/googleapis", "53efb8a56baa3b802407e7c0d1050328aeb31671", "gapic"),
        ("external/googleapis", "53efb8a56baa3b802407e7c0d1050328aeb31671", "google"),
        ("external/googleapis", "53efb8a56baa3b802407e7c0d1050328aeb31671", "grafeas"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/data"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/extra"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/io"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/layoutex"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/samples"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/test"),
        ("external/icu", "00c713278f65a4db343c388f0c4f8501f70387b9", "icu4c/source/tools"),
        ("external/jsoncpp", "97cca484243e0dadc1da054e63823a5ce7478e54", "src"),
        ("external/jsr330", "2360bfd8d364aa446599981df8cf83cdc5eafb34", "tck"),
        ("external/libbpf", "9723b4de6459ab48b361aed3bae5df3c1bd20cb8", ".github"),
        ("external/libbpf", "9723b4de6459ab48b361aed3bae5df3c1bd20cb8", "android"),
        ("external/libbpf", "9723b4de6459ab48b361aed3bae5df3c1bd20cb8", "include"),
        ("external/libcap", "9a2ead0b5a377a75849cb0656aa553b5452a7080", "contrib"),
        ("external/libcap", "9a2ead0b5a377a75849cb0656aa553b5452a7080", "progs"),
        ("external/libcap", "9a2ead0b5a377a75849cb0656aa553b5452a7080", "psx"),
        ("external/libchrome", "0aba0dccfcd93d8303678a4beb61594f7582c73c", "components"),
        ("external/libchrome", "0aba0dccfcd93d8303678a4beb61594f7582c73c", "dbus"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "etnaviv"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "exynos"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "freedreno"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/intel_aub.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/intel_bufmgr.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/intel_bufmgr_priv.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/intel_chipset.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/intel_debug.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/mm.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "intel/uthash.h"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "libkms"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "nouveau"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "omap"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "radeon"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tegra"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/amdgpu"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/etnaviv"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/kms"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/modetest"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/radeon"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/tegra"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/ttmtest"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "tests/util"),
        ("external/libdrm", "12b44e2c3b5186a7e84a5f21830b077cb8587861", "vc4"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "WIN32-Code"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "compat"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "include"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "sample"),
        ("external/libevent", "44754c0dfee5dc81723013498398034176e6d81e", "test"),
        ("external/libxml2", "e57cff8da55134774646a521a797bb03d46babd8", "codegen"),
        ("external/libxml2", "e57cff8da55134774646a521a797bb03d46babd8", "python"),
        ("external/libxml2", "e57cff8da55134774646a521a797bb03d46babd8", "test"),
        ("external/minigbm", "ce79bbee67b3e2ea7abb110e1415e9ceceaa6471", "cros_gralloc/aidl"),
        ("external/minigbm", "ce79bbee67b3e2ea7abb110e1415e9ceceaa6471", "cros_gralloc/gralloc0"),
        ("external/minigbm", "ce79bbee67b3e2ea7abb110e1415e9ceceaa6471", "cros_gralloc/gralloc4"),
        ("external/minigbm", "ce79bbee67b3e2ea7abb110e1415e9ceceaa6471", "rust"),
        ("external/modp_b64", "5dac538059455079c873d306d25e0c6c75ea3845", "modp_b64"),
        ("external/objenesis", "26a2fb53712b58f59c7d42edf9ae6df1ab27d469", "tck"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "android"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "mockwebserver"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-android-support"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-android-util-log"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-testing-support"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-tests"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-urlconnection"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-ws"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okhttp-ws-tests"),
        ("external/okhttp", "7fec69d8a7874ed20e11a9211d04b9fca71dcd72", "okio"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "include"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/agent"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/android/aidl"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/backbone_router"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/border_agent"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/common"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/dbus"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/host"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/mdns"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/openwrt"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/proto"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/rest"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/sdp_proxy"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/trel_dnssd"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/utils"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "src/web"),
        ("external/ot-br-posix", "03168f06007263a05c2ae3d171a959f40dc6b178", "third_party"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "python/google"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "benchmarks"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "compatibility"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "conformance"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "csharp"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "editions"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "examples"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "go"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "hpb"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "hpb_generator"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "java"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "javamicro"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "javanano"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "lua"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "objectivec"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "php"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "pkg"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "ruby"),
        ("external/protobuf", "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab", "rust"),
        ("external/vulkan-headers", "ee4343a1f27d9faca189b9ac2c064254e23ba2e2", "LICENSES"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "wpa_supplicant/wpa_gui-qt4/icons/LICENSE"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "hostapd"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "hs20"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "src"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "wpa_supplicant/aidl"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "wpa_supplicant/dbus"),
        ("external/wpa_supplicant_8", "3396e8b8365817b3a24b78b534b04bb9dcea330a", "wpa_supplicant/wpa_client_include"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/display/1.0"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/display/aidl/Android.bp"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/display/aidl/aidl_api"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/display/aidl/android"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "cameraservice/common"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "cameraservice/device"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "cameraservice/service"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "sensorservice/1.0/Android.bp"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "sensorservice/1.0/IDirectReportChannel.hal"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "sensorservice/1.0/IEventQueue.hal"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "sensorservice/1.0/IEventQueueCallback.hal"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "sensorservice/1.0/ISensorManager.hal"),
        ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "sensorservice/1.0/types.hal"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "modules/camera"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "modules/gralloc"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "modules/input"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "modules/sensors"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "modules/usbcamera"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "tests/camera3"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "tests/fingerprint"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "tests/hwc"),
        ("hardware/libhardware", "97ee3e33ec5ba48c0eca8341ed377ac4497a0678", "tests/input"),
        ("hardware/st/nfc", "55055c3a3a9ba8d8664dbc3ff6eb49563d4875ca", "st21nfc"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "aconfig"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "checks"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "dagger"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "go"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "modules/appfunctions"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "modules/concurrent"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "modules/widgetpicker/Android.bp"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "modules/widgetpicker/AndroidManifest.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "modules/widgetpicker/res"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "modules/widgetpicker/src"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "protos"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "protos_overrides"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/Android.bp"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/AndroidManifest-launcher.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/AndroidManifest.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/dagger"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/protos_overrides"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/res"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/src"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/src_protolog"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/tests/multivalentScreenshotTests"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/tests/multivalentTests"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "quickstep/tests/src"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "res"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "shared"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "src"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "src_no_quickstep"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "src_plugins"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/Android.bp"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/AndroidManifest-common.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/AndroidManifest.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/Launcher3Tests.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/assets"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/lint-baseline.xml"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/multivalentTests/src"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/res"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/shared"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/src"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/src_deviceless"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/src_e2e"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tests/tapl"),
        ("packages/apps/Launcher3", "c612e6ece389f21c40f8cb9cd9a4b44239f00009", "tools"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "aconfig"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "assets"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "libs"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "protos"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "res"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "res-export"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "res-product"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "src"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "tests/perftests"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "tests/robotests"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "tests/shared"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "tests/spa_unit"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "tests/uitests"),
        ("packages/apps/Settings", "213829fb67f5e070029e0513a088f31bc8f5c1ed", "tests/unit"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "android/app/aidl"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "common/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "common/bluetooth/constants"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "framework/java"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "service/aidl"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tools/lint"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "android/app"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "apex/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "apex/boot-image-profile.txt"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "apex/key"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "apex/manifest.json"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "common"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/android-base"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/libflags"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/mmc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/bindings"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/btav"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/btav_sink"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/btif"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/common"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/controller"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/csis"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/gatt"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/hf_client"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/hfp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/hh"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/le_audio"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/metrics"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/sdp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/socket"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "floss/rust/topshim/vc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "offload"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "service/fake_app"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "service/src"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "sysprop"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/a2dp_encoding.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/a2dp_encoding.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/a2dp_encoding_host.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/a2dp_encoding_host.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/aidl"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/audio_linux.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hal_version_manager.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hal_version_manager.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hal_version_manager_host.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hearing_aid_software_encoding.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hearing_aid_software_encoding.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hearing_aid_software_encoding_host.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hfp_client_interface.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hfp_client_interface.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hfp_client_interface_host.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hfp_client_interface_unittest.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/hidl"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_peripheral.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_peripheral.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_peripheral_host.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software_host.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software_host.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software_host_transport.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software_host_transport.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/le_audio_software_unittest.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/audio_hal_interface/test"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/bta"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/btcore"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/btif"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/common"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/conf"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/device/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/device/include"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/device/src"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/device/test"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/encoder_for_aptx"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/encoder_for_aptxhd"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/g722/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/g722/g722_decode.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/g722/g722_enc_dec.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/g722/g722_encode.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/g722/g722_typedefs.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/embdrv/sbc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/gd"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/hci"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/include"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/internal_include"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/log"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/main"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/metrics"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/include"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/include_internal"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/src"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/alarm_mock.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/alarm_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/allocator_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/config_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/fixed_queue_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/future_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/fuzzers/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/fuzzers/include"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/hash_map_utils_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/internal"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/list_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/properties_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/reactor_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/test_stubs.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/thread_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/osi/test/wakelock_test.cc"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/Android.bp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/avrcp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/base"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/include"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/tests/avrcp"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/tests/base"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/tests/packet_test_helper.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/packet/tests/test_packets.h"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/pdl"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/profile"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/rust"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/stack"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/types"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "system/udrv"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tests/pandora/interfaces/pandora"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tests/pandora/test"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "aconfigd"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "aflags"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "apex"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/Android.bp"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/api"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/flags.aconfig"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/framework-configinfrastructure-ravenwood-policies.txt"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/jarjar-rules.txt"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/java"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "framework/lint-baseline.xml"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "service/Android.bp"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "service/api"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "service/flags.aconfig"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "service/jarjar-rules.txt"),
        ("packages/modules/ConfigInfrastructure", "333bc8067efc529ef4d197fec2f4f2cae1ad2ece", "service/java"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "nearby/framework/Android.bp"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "nearby/framework/java"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "thread/framework/Android.bp"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "thread/framework/java"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/apex/hiddenapi"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/jni"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/res"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/src"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/tests/Android.bp"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/tests/integration"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/tests/jarjar-rules.txt"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/tests/unit"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Vcn/service-b"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "clatd"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "commercial"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "nearby/service"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "networksecurity/service"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "service-t"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "staticlibs"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "thread/apex"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "thread/service"),
        ("packages/modules/DnsResolver", "0aeaf9d222ec761b9e0443a01c7a06590b9d1b4f", "include"),
        ("packages/modules/DnsResolver", "0aeaf9d222ec761b9e0443a01c7a06590b9d1b4f", "tests"),
        ("packages/modules/Gki", "968142477afa61c98b9f7a1b9f4cce2d1ed5ca91", "sysprop"),
        ("packages/modules/Media", "efe6c6621fe6a6faee106a1230b010c32cb30c35", "apex"),
        ("packages/modules/Media", "efe6c6621fe6a6faee106a1230b010c32cb30c35", "flags"),
        ("packages/modules/Media", "efe6c6621fe6a6faee106a1230b010c32cb30c35", "mediametrics"),
        ("packages/modules/NetworkStack", "928a826ae4887ce0e5d3c7209870e238cacbf548", "common"),
        ("packages/modules/NetworkStack", "928a826ae4887ce0e5d3c7209870e238cacbf548", "jni"),
        ("packages/modules/NetworkStack", "928a826ae4887ce0e5d3c7209870e238cacbf548", "res"),
        ("packages/modules/NetworkStack", "928a826ae4887ce0e5d3c7209870e238cacbf548", "src"),
        ("packages/modules/NetworkStack", "928a826ae4887ce0e5d3c7209870e238cacbf548", "tests/hostlib"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "framework/Android.bp"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "framework/api"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "framework/java"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/Android.bp"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/AndroidManifest.xml"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/TEST_MAPPING"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/assets"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/com.android.nfc.xml"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/flags"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/jarjar-rules.txt"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/lint-baseline-nfcnci.xml"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/lint-baseline.xml"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/nci"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/preinstalled-packages-com.android.nfc.xml"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/proguard.flags"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/proto"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/res"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/shim_src"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "NfcNci/src"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "libnfc-nci/flags"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "libnfc-nci/src"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "libnfc-nci/tests"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "libnfc-nci/tools"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "libnfc-nci/utils"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "flags"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/Android.bp"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/AndroidManifest-lib.xml"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/AndroidManifest.xml"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/NOTICE"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/TEST_MAPPING"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/appfunctionslib"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/assets"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/flags"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/iconloaderlib"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/jarjar-rules.txt"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/lint-baseline.xml"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/lint-baseline2.xml"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/proguard.flags"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/res"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/role-controller"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/src"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "PermissionController/wear-permission-components"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Annotations"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Config/Android.bp"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Config/TEST_MAPPING"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Config/java"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/InternalData"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/PendingIntents"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Persistence/Android.bp"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Persistence/TEST_MAPPING"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Persistence/java"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/ResourcesLib/Android.bp"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/ResourcesLib/TEST_MAPPING"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/ResourcesLib/java"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyLabel/Android.bp"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyLabel/TEST_MAPPING"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyLabel/java"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "service"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "aidl"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "apex"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "flags"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "framework"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "jni"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/Android.bp"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/ServiceWifiResources"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/TEST_MAPPING"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/coex-table-parser"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/java"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/lint-baseline.xml"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/proto"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/tests/wifitests/Android.bp"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/tests/wifitests/AndroidManifest.xml"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/tests/wifitests/AndroidTest.xml"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/tests/wifitests/assets"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/tests/wifitests/jarjar_rules.txt"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/tests/wifitests/src"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "service/wifi.rc"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/com.google.snippet.wifi"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/Android.bp"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/AndroidTest.xml"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/aware_lib_utils.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/aware_snippet_utils.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/constants.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/cts_wifi_aware_test_suite.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/wifi_aware_discovery_ranging_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/wifi_aware_network_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/aware/wifi_aware_pairing_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/connection"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/AndroidTest.xml"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/constants.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/cts_wifi_direct_test_suite.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/group_owner_negotiation_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/group_owner_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/group_owner_with_config_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/p2p_utils.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/service_discovery_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/snippet"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/direct/wifi_direct_test.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/sniffer_helper.py"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/softap"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/usd"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "tests/hostsidetests/multidevices/test/wifi_test_utils.py"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "client"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "crypto/Android.bp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "crypto/include"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "crypto/key.cpp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "crypto/rsa_2048_key.cpp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "crypto/x509_generator.cpp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "daemon"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "fastdeploy"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "fdevent"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "libs"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "pairing_auth/Android.bp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "pairing_auth/aes_128_gcm.cpp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "pairing_auth/include"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "pairing_auth/libadb_pairing_auth.map.txt"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "pairing_auth/pairing_auth.cpp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "pairing_connection"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "sysdeps"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "test_utils"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "tls/Android.bp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "tls/adb_ca_list.cpp"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "tls/include"),
        ("packages/modules/adb", "9084198a2d4b0f6a0f174260fb42da33485b684d", "tls/tls_connection.cpp"),
        ("packages/modules/common", "2c5d816b30e439bdfaf3a52a94e4ee8fbf6d739c", "proto"),
        ("packages/modules/common", "2c5d816b30e439bdfaf3a52a94e4ee8fbf6d739c", "tools/Android.bp"),
        ("packages/modules/common", "2c5d816b30e439bdfaf3a52a94e4ee8fbf6d739c", "tools/gen_sdkinfo.py"),
        ("packages/modules/common", "2c5d816b30e439bdfaf3a52a94e4ee8fbf6d739c", "tools/conv_classpaths_proto.py"),
        ("packages/modules/common", "2c5d816b30e439bdfaf3a52a94e4ee8fbf6d739c", "tools/check_derive_classpath.py"),
        ("packages/modules/common", "2c5d816b30e439bdfaf3a52a94e4ee8fbf6d739c", "java"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/androidbuildinternal"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/app-helpers"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/automotive-helpers/auto-default-config"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/automotive-helpers/dial-app-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/automotive-helpers/utility-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/collectors-helper/statsd/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/collectors-helper/statsd/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/desktop-test-lib/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/desktop-test-lib/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/desktop-test-lib/interactive"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/desktop-test-lib/lint-baseline.xml"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/desktop-test-lib/mobly"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/desktop-test-lib/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/device-collectors/src/main"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flag-helpers/junit/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flag-helpers/junit/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flag-helpers/junit/src_base"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flag-helpers/junit/src_host"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flag-helpers/junit/src_util"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flag-helpers/libflagtest"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/AndroidManifest.xml"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/appHelpers"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/collector/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/collector/AndroidManifest.xml"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/collector/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/collector/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/test"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/flicker/utils"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/composers/host/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/composers/host/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/composers/platform/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/composers/platform/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/options/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/options/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/rules/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/rules/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/rules/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/longevity/host/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/longevity/host/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/longevity/platform/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/longevity/platform/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/longevity/platform/tests"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/microbenchmark/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/microbenchmark/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/runners/microbenchmark/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/utils/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/health/utils/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/launcher-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/metrics-helper/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/metrics-helper/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/notes-role-test-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/power-helper/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/power-helper/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/screenshot/utils"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/device-side/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/device-side/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/device-side/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/res"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/host-side/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/util/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/util/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/sts-common-util/util/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/system-helpers"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/systemui-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/systemui-tapl/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/systemui-tapl/TEST_MAPPING"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/systemui-tapl/src"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/tapl-common"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/timeresult-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "libraries/uinput-device-test-helper"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "scripts/Android.bp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "scripts/androidx-perf-setup"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "scripts/test-utils-script"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/apphealth"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/automotive/health/dial"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/automotive/health/rules"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/example/instrumentation"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/example/native"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/functional/devicehealthchecks"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/functional/downloadapp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/functional/overviewtests"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/functional/permission"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/functional/testapks/permissiontestappmv1"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/health"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/jank"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/microbenchmarks/LauncherIconsApp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/microbenchmarks/uibench"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/perf/BootHelperApp"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/perf/PerfTransitionTest"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/perf/PerformanceAppTest"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/perf/PerformanceLaunch"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "tests/perf/PowerPerfTest"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "utils/dpad"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "utils/permissions"),
        ("platform_testing", "6abefd291d50dee240ed2b22572d273175f070da", "utils/wifistrengthscanner"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-3289846"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r547379"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r563880c"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948/include"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948/lib/clang"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948/lib/libear"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948/prebuilt_include"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948/python3/include"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r584948/share"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r596125/include"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r596125/lib/clang"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r596125/lib/libear"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r596125/prebuilt_include"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r596125/python3/include"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-r596125/share"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-stable/lib/libclang.so"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "clang-stable/lib/python3"),
        ("prebuilts/clang/host/linux-x86", "29182889399818f97baa65ea238c80e8117981eb", "embedded-sysroots"),
        ("prebuilts/cmdline-tools", "744a1b7a5649dfb8f51760f4c348c3f77fe5dbcd", "tools"),
        ("prebuilts/gcc/linux-x86/host/x86_64-w64-mingw32-4.8", "a6c64a6502e0a89ee8ad3e3f8be97223a69e5bd7", "include"),
        ("prebuilts/gcc/linux-x86/host/x86_64-w64-mingw32-4.8", "a6c64a6502e0a89ee8ad3e3f8be97223a69e5bd7", "lib"),
        ("prebuilts/gcc/linux-x86/host/x86_64-w64-mingw32-4.8", "a6c64a6502e0a89ee8ad3e3f8be97223a69e5bd7", "x86_64-w64-mingw32"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/androidx-test"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "darwin-x86/yasm/COPYING"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "darwin-x86_64/sdl2/include/SDL2/NOTICE"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "linux-x86/yasm/COPYING"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/android-support-test"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/androidx-media3"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/args4j"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/devtools-annotations"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/incfs"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/tools-common"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/ub-janktesthelper"),
        ("prebuilts/rust-toolchain/linux-x86", "fa2b1777b1f5c0471bb54ad4026feb1f6e94ea70", "1.91.1"),
        ("prebuilts/rust-toolchain/linux-x86", "fa2b1777b1f5c0471bb54ad4026feb1f6e94ea70", "1.92.0"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "current/extras/material-design-x"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/public/api/framework-ondeviceintelligence.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/public/api/framework-ondeviceintelligence-removed.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/system/api/framework-ondeviceintelligence.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/system/api/framework-ondeviceintelligence-removed.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/module-lib/api/framework-ondeviceintelligence.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36/module-lib/api/framework-ondeviceintelligence-removed.txt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "1"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "10"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "11"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "12"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "13"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "14"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "15"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "16"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "17"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "19"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "2"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "20"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "21"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "22"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "23"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "24"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "25"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "26"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "27"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "28"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "29"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "3"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "30"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "31"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "32"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "33"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "34"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "35"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "36.1"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "37-prefinalized"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "37.0"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "4"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "5"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "6"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "7"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "current"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "extensions"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "opt"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "perm"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "renderscript"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "sdk-annotations"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "tools"),
        ("prebuilts/sdk", "0f07e8d60ab0aba46129e427101f96ba459a95c1", "vendor"),
        ("prebuilts/tools", "b157d1c3bff39161f34ccc44dffbe9568f3bece2", "common/google-api-java-client"),
        ("prebuilts/tools", "b157d1c3bff39161f34ccc44dffbe9568f3bece2", "common/google-api-services-compute"),
        ("prebuilts/tools", "b157d1c3bff39161f34ccc44dffbe9568f3bece2", "common/google-api-services-storage"),
        ("prebuilts/tools", "b157d1c3bff39161f34ccc44dffbe9568f3bece2", "common/google-java-format"),
        ("prebuilts/tools", "b157d1c3bff39161f34ccc44dffbe9568f3bece2", "linux-x86_64"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "apexd"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "shim"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/Android.bp"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/TEST_MAPPING"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/apex-revert-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/apex-targetprep-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/apex_compression_platform_tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/apexd-host-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/apk-in-apex-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/app"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/max-sdk-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/media-e2e-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/media-swcodec-e2e-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/src"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/AndroidManifest.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/apex_manifest.json"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/com.android.apex.test.avbpubkey"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/com.android.apex.test.pem"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/init.rc"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/ld.config.txt"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/maxsdk/app"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/sample_prebuilt_file"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/testcert.pk8"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/testcert.x509.pem"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/trigger_reboot.sh"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/trigger_watchdog.rc"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/trigger_watchdog.sh"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/testdata/vendorapex"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/timezone-data-e2e-tests.xml"),
        ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8", "tests/vendor-apex-tests.xml"),
        ("system/bpf", "d68a263039127dc709114802395e57537a02babf", "progs"),
        ("system/bpf", "d68a263039127dc709114802395e57537a02babf", "loader"),
        ("system/connectivity/wificond", "fefad78738af9d9753bb0acbafcf458691f8627c", "client"),
        ("system/connectivity/wificond", "fefad78738af9d9753bb0acbafcf458691f8627c", "net"),
        ("system/connectivity/wificond", "fefad78738af9d9753bb0acbafcf458691f8627c", "scanning"),
        ("system/connectivity/wificond", "fefad78738af9d9753bb0acbafcf458691f8627c", "tests"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "f2fs_utils"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libatrace_rust/Android.bp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libatrace_rust/benchmark"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libatrace_rust/bindgen"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libatrace_rust/src"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/Android.bp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/NOTICE"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/avb_utils.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/avb_utils.h"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/avb_utils_stub.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/fec_open.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/fec_private.h"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/fec_process.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/fec_read.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/fec_verity.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfec/include"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfscrypt/Android.bp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfscrypt/NOTICE"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfscrypt/fscrypt.cpp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "libfscrypt/include"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "mmap-perf"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "partition_tools"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "profcollectd"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/app_api"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/demo"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/doc"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/include"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/nonlinux_support"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/runtest"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "simpleperf/rust"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "squashfs_utils"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "tests/Android.bp"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "tests/NOTICE"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "tests/binder"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "tests/kernel.config"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "tests/lib"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "tests/timetest"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "verity"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "module_ndk_libs"),
        ("system/extras", "1289e9b3f282909eec6e80414e14dcc207bda439", "module_ndk_libs/libnativehelper"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "aidl"),
        ("system/gsid", "35a92d40f529b605fad8ff622691e76901044cc8", "fuzzers"),
        ("system/hardware/interfaces", "9c3469aa3d4aeec5b2bc8e8ae8fdb4437dab4edb", "wifi/keystore/1.0/Android.bp"),
        ("system/hardware/interfaces", "9c3469aa3d4aeec5b2bc8e8ae8fdb4437dab4edb", "wifi/keystore/1.0/IKeystore.hal"),
        ("system/hardware/interfaces", "9c3469aa3d4aeec5b2bc8e8ae8fdb4437dab4edb", "wifi/keystore/1.0/default/Android.bp"),
        ("system/hardware/interfaces", "9c3469aa3d4aeec5b2bc8e8ae8fdb4437dab4edb", "wifi/keystore/1.0/default/include"),
        ("system/hardware/interfaces", "9c3469aa3d4aeec5b2bc8e8ae8fdb4437dab4edb", "wifi/keystore/1.0/default/keystore.cpp"),
        ("system/hardware/interfaces", "9c3469aa3d4aeec5b2bc8e8ae8fdb4437dab4edb", "wifi/keystore/1.0/default/wifikeystorehal_utils.h"),
        ("system/libhwbinder", "2f5282448223b97c541181a5b94a05c2ac17ff17", "vts"),
        ("system/linkerconfig", "f6b4bd983b909a907cf7e9fae8a6365d827638b6", "contents"),
        ("system/linkerconfig", "f6b4bd983b909a907cf7e9fae8a6365d827638b6", "generator"),
        ("system/linkerconfig", "f6b4bd983b909a907cf7e9fae8a6365d827638b6", "modules"),
        ("system/linkerconfig", "f6b4bd983b909a907cf7e9fae8a6365d827638b6", "testdata"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logcat"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/Android.bp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/CommandListener.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/CommandListener.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/CompressionEngine.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/CompressionEngine.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogAudit.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogAudit.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBuffer.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBufferElement.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBufferElement.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBufferTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogBufferTest.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogKlog.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogKlog.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogListener.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogListener.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogPermissions.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogPermissions.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReader.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReader.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReaderList.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReaderList.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReaderThread.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogReaderThread.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogSize.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogSize.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogStatistics.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogStatistics.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogTags.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogTags.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogUtils.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogWriter.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogdLock.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogdLock.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogdNativeService.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/LogdNativeService.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/PkgIds.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/PruneList.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/PruneList.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/RecordedLogMessage.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/RecordingLogBuffer.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/ReplayMessages.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedData.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedFlushToState.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedFlushToState.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedFlushToStateTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogBuffer.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogBuffer.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogBufferTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogChunk.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogChunk.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogChunkTest.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SerializedLogEntry.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SimpleLogBuffer.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/SimpleLogBuffer.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/TrustyLog.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/TrustyLog.h"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/auditctl.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/binder"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/device_test_config.xml"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/flags"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/libaudit"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/logd.rc"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/logd_test.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/logtagd.rc"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logd/main.cpp"),
        ("system/logging", "d35ba620451b28512f46ebb5421f783fd77968d5", "logwrapper"),
        ("system/memory/libdmabufheap", "09fe72b6ce0feead1b97c2859979b125f815d9b0", "configs"),
        ("system/memory/libdmabufheap", "09fe72b6ce0feead1b97c2859979b125f815d9b0", "tests"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "include"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "libmemevents/Android.bp"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "libmemevents/TEST_MAPPING"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "libmemevents/include"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "libmemevents/memevents.cpp"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "libmemevents/memevents_test.cpp"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "libsmapinfo"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "testdata1"),
        ("system/memory/libmeminfo", "d59c960b1fb93377bf68664918031ea5fe709f89", "testdata2"),
        ("system/netd", "43c893c7f33de178d6edaf5be49aed0794b3a917", "netutils_wrappers"),
        ("system/netd", "43c893c7f33de178d6edaf5be49aed0794b3a917", "server"),
        ("system/netd", "43c893c7f33de178d6edaf5be49aed0794b3a917", "tests"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "hals/Android.bp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "hals/derive"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "hals/wire"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore-engine"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/aaid"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/apc_compat"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/legacykeystore"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/message_macro"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/postprocessor_client"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/rkpd_client"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/selinux"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/src"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/test_utils"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/tests/keystore-engine"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/tests/wrapper.h"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "keystore2/watchdog"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/Android.bp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/CertUtils.cpp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/KeyConstants.h"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/KeystoreHmacKey.cpp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/KeystoreHmacKey.h"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/KeystoreKey.cpp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/KeystoreKey.h"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/StatsReporter.cpp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/StatsReporter.h"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/TEST_MAPPING"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/VerityUtils.cpp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/include"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/odsign.rc"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/odsign_main.cpp"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "ondevice-signing/proto"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "provisioner"),
        ("system/security", "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb", "prng_seeder"),
        ("system/server_configurable_flags", "5069ba739faebf91ae72096577ae17e13061af72", "aconfigd/src"),
        ("system/server_configurable_flags", "5069ba739faebf91ae72096577ae17e13061af72", "aconfigd/srcs"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "aosp"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "binder_bindings"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "client_library"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "common"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "libbinderwrapper"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "lz4diff"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "payload_consumer"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "payload_generator"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "sample_images"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "scripts"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "stable"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "testdata"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "update_engine"),
        ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "flags"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "aconfig/flags.aconfig"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "binder"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "fs"),
        ("system/vold", "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e", "model"),
        ("tools/lint_checks", "d260e8254709bb2884c072dd595f63c9c8d22527", "fix"),
        ("tools/platform-compat", "19ce1c9d406cec9feaf76618e7d772113883d73f", "java/android/compat/testing/Android.bp"),
        ("tools/platform-compat", "19ce1c9d406cec9feaf76618e7d772113883d73f", "java/android/compat/testing/Classpaths.java"),
        ("tools/platform-compat", "19ce1c9d406cec9feaf76618e7d772113883d73f", "java/android/compat/testing/SharedLibraryInfo.java"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "include"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/BlocksRuntime"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/asan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/absvdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/absvsi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/absvti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/adddf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/addsf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/addtf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/addvdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/addvsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/addvti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/arm"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ashldi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ashlti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ashrdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ashrti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/assembly.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/clear_cache.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/clzdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/clzsi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/clzti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/cmpdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/cmpti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/comparedf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/comparesf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/comparetf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ctzdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ctzsi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ctzti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divdc3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divdf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divmoddi4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divmodsi4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divsc3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divsf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divtf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/divxc3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/enable_execute_stack.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/eprintf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/extenddftf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/extendhfsf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/extendsfdf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/extendsftf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ffsdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ffsti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixdfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixdfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixdfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixsfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixsfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixsfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixtfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixtfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixtfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunsdfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunsdfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunsdfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunssfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunssfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunssfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunstfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunstfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunstfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunsxfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunsxfsi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixunsxfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixxfdi.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fixxfti.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatdidf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatdisf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatdixf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatsidf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatsisf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatsitf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floattidf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floattisf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floattixf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatundidf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatundisf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatundixf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatunsidf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatunsisf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatunsitf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatuntidf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatuntisf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/floatuntixf.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_add_impl.inc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_extend.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_extend_impl.inc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_fixint_impl.inc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_fixuint_impl.inc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_lib.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_mul_impl.inc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_trunc.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/fp_trunc_impl.inc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/gcc_personality_v0.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/i386"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/int_endianness.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/int_lib.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/int_math.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/int_types.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/int_util.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/int_util.h"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/lshrdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/lshrti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/moddi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/modsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/modti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/muldc3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/muldf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/muldi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulodi4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulosi4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/muloti4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulsc3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulsf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/multf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/multi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulvdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulvsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulvti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/mulxc3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negdf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negsf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negvdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negvsi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/negvti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/paritydi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/paritysi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/parityti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/popcountdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/popcountsi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/popcountti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/powidf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/powisf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/powitf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/powixf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ppc"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/subdf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/subsf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/subtf3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/subvdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/subvsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/subvti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/trampoline_setup.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/truncdfhf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/truncdfsf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/truncsfhf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/trunctfdf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/trunctfsf2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ucmpdi2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/ucmpti2.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/udivdi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/udivmoddi4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/udivmodsi4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/udivmodti4.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/udivsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/udivti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/umoddi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/umodsi3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/umodti3.c"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/builtins/x86_64"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/dfsan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/esan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/interception"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/lsan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/msan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/profile"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/sanitizer_common"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/scudo"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/stats"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/tsan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "lib/ubsan"),
        ("external/compiler-rt", "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7", "test"),
        ("hardware/libhardware_legacy", "2a073cd42ec822914ed4e680e7b708485d3a172b", "audio"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "MutableDagger"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "ace"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "aconfig"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "animationlib"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "contextualeducationlib"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "cuebarlib"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "displaylib/Android.bp"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "displaylib/TEST_MAPPING"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "displaylib/src"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "dynamiccolors"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "iconloaderlib/Android.bp"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "iconloaderlib/AndroidManifest.xml"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "iconloaderlib/lint-baseline.xml"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "iconloaderlib/res"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "iconloaderlib/src"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "iconloaderlib/src_full_lib"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/Android.bp"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/AndroidManifest.xml"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/TEST_MAPPING"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/compose/Android.bp"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/compose/AndroidManifest.xml"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/compose/src"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/lint-baseline.xml"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/src"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "mechanics/testing"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "monet/Android.bp"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "monet/TEST_MAPPING"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "monet/src"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "msdllib"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "surfaceeffects"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "tracinglib/benchmark"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "usertypelib"),
        ("frameworks/libs/systemui", "11e04f60f563aed48e4ec080bd7bde06bae1b2f3", "viewcapturelib"),
        ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "car-lib/api"),
        ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/car_binder_lib"),
        ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/watchdog/aidl"),
        ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "packages/CarDeveloperOptions"),
        ("system/timezone", "cbd571efcf6b551ba83a31147ec7a06182f8ec31", "testing/Android.bp"),
        ("system/timezone", "cbd571efcf6b551ba83a31147ec7a06182f8ec31", "testing/src"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/acme"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/asuite_lib_test"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/coverage"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/crystalball"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/Android.bp"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/adevice_command_success_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/adevice_integration_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/atest_command_success_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/atest_command_verification_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/atest_dry_run_diff_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/atest_integration_test.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/atest_integration_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/atest_test_archetype_integration_tests.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/deviceless_python_test_host"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/deviceless_python_test_host_multiclass"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/snapshot.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/snapshot_unittest.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/split_build_test_script.py"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/integration_tests/split_build_test_script_config.xml"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/java"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/logstorage"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/metrics"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/mobly"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/test_finders"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/test_runners"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/tf_proto"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/tools"),
        ("tools/asuite", "744998cb744c401a5daa77170039ab6337ed7adb", "atest/unittest_data"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "flags"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "framework"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "common"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "driver"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "extensions"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "runtime"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "service"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "shim_and_sl"),
        ("packages/modules/NeuralNetworks", "a44a9032ab9a8438c0e13aca765d6ee4edebba2c", "tools/test_generator"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/CameraFeatureCombinationVerifier"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/CarWatchdogCompanionApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/CrossProfileTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/CtsVerifierUSBCompanion"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/DeviceControlsApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/EmptyDeviceAdmin"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/EmptyDeviceOwner"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/NotesApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/NotificationBot"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/PermissionApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/TileServiceApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/TtsTestApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "apps/VpnApp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/deviceadminapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/bedstead/metricsrecorder"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/device-info"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "common/device-side/util-axt/tests"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/appsecurity/test-apps"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/compilation/app_using_other_app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/devicepolicy/app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/app"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/os/test-apps"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/scopedstorage/libs/ScopedStorageTestLib"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/apps/adpfapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/apps/expressloghelperapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "hostsidetests/statsdatom/apps/statsdapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/jdwp/runner/host-side"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/signature/api"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/keystore"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/os/jni"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/packageinstaller/test-apps/emptytestapp"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ConnectionServiceVoipAppClone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ConnectionServiceVoipAppMain"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ManagedConnectionService"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/ManagedConnectionServiceClone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/TransactionalVoipAppClone"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/TransactionalVoipAppMain"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-apps/Utils"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom-cuj"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom2"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/tests/telecom3"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-dynamic-config"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tests/signature/lib/common"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed"),
        ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-v-host"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "apex/permissions"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "framework/tests/util"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tests/pandora/android_server"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tests/pandora/bumble_server"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tests/pandora/interfaces/python"),
        ("packages/modules/Bluetooth", "c77db469de80f86660bc053bec4dee0c5d4b947c", "tests/pandora/mmi2grpc"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "Tethering/apex/permissions"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "nearby/flags"),
        ("packages/modules/Connectivity", "347fbd34b368d19f0d87e908ea101eed3601a731", "remoteauth/service"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "SafetyCenter/Resources"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "permissions"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "sysconfig"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "tests/cts/permission/permissionTestUtilLib"),
        ("packages/modules/Permission", "1093eca7407576c72e51b1a88550ee0667a6e5dc", "tests/cts/permission/jni"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "OsuLogin"),
        ("packages/modules/Wifi", "67beff9acf0e91046d2a9a36a68cb06ef263d1f1", "WifiDialog"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "apex"),
        ("packages/modules/Nfc", "940212c440f57032a19cf0f90c7faa8eca48d546", "libnfc-nci/conf"),
        ("system/memory/libdmabufheap", "09fe72b6ce0feead1b97c2859979b125f815d9b0", "rust"),
    ] {
        let matches: Vec<usize> = projects.iter().enumerate()
            .filter_map(|(index, row)| (row["path"] == path).then_some(index)).collect();
        if matches.len() != 1 || projects[matches[0]]["commit"] != commit {
            return fail("ordinary pair provider project or pinned revision changed");
        }
        let paths = projects[matches[0]]["sparse_paths"].as_array_mut()
            .ok_or("ordinary pair provider sparse paths absent")?;
        if paths.iter().any(|value| value == subtree) {
            return fail("ordinary pair base unexpectedly already includes the added provider subtree");
        }
        paths.push(json!(subtree));
    }
    let additions: Vec<Value> = serde_json::from_str(PAIR_ADDITIONS_JSON)?;
    for addition in additions {
        if projects.iter().any(|project| project["path"] == addition["path"]
            || project["name"] == addition["name"]) {
            return fail("ordinary pair provider project already exists in the base closure");
        }
        projects.push(addition);
    }
    if &expected != extended {
        return fail("ordinary pair source closure differs beyond the exact provider subtrees and authenticated projects");
    }
    Ok(())
}

// The previous complete 607 contract remains a pure immutable predecessor.
// This route accepts only the concrete same-SP generic-provider extension.
fn validate_source_extension642(base: &Value, extended: &Value) -> Result<()> {
    const SOURCE_LOCK_SHA: &str = "f8663e08af2e28f2a5bd1b9b9c0d183c5b9fa2a6521d2c97fbc2ed1d3e62165a";
    let previous_raw = include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json");
    if previous_raw.len() != 357293 || digest(previous_raw) != "2c57d50f68aa8db89dcbd6beaaba2057bd61fca881dcfbbf8873d0a4047fb7eb" {
        return fail("immutable original607 source fixture changed");
    }
    let previous: Value = serde_json::from_slice(previous_raw)?;
    validate_source_extension607(base, &previous)?;
    let delta_raw = include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/selection-delta.json");
    if delta_raw.len() != 30872 || digest(delta_raw) != "cc6513436440c1975fc8be78905b69c556c374143f31604323f682a3773fb28e" {
        return fail("exact generic59 source delta changed");
    }
    let delta: Value = serde_json::from_slice(delta_raw)?;
    if delta["schema"] != "native642-exact-generic59-source-extension-v1"
        || delta["previous_projects"] != 607 || delta["current_projects"] != 642
        || delta["previous_lock_sha256"] != "2c57d50f68aa8db89dcbd6beaaba2057bd61fca881dcfbbf8873d0a4047fb7eb"
        || delta["current_lock_sha256"] != SOURCE_LOCK_SHA
        || delta["source_and_full_qualified"] != false {
        return fail("generic59 source delta identity changed");
    }
    let mut expected = previous;
    let projects = expected["projects"].as_array_mut().ok_or("original607 projects absent")?;
    for (path, change) in delta["added_sparse_cones"].as_object().ok_or("generic provider cone delta absent")? {
        let indices: Vec<usize> = projects.iter().enumerate().filter_map(|(index, row)| (row["path"] == path.as_str()).then_some(index)).collect();
        if indices.len() != 1 || projects[indices[0]]["sparse_paths"] != change["old"] {
            return fail("original607 provider cone predecessor changed");
        }
        projects[indices[0]]["sparse_paths"] = change["new"].clone();
    }
    let additions = delta["added_projects"].as_array().ok_or("generic provider additions absent")?;
    if additions.len() != 35 { return fail("exact35 original provider projects required"); }
    for addition in additions {
        if projects.iter().any(|project| project["path"] == addition["path"] || project["name"] == addition["name"]) {
            return fail("generic original provider project collides with predecessor");
        }
        projects.push(addition.clone());
    }
    if projects.len() != 642 || expected != *extended {
        return fail("source differs beyond exact35 original projects and exact17 monotone cone additions");
    }
    Ok(())
}


// Retain the exact 642 predecessor, then admit only the original SDK producer.
fn validate_source_extension643_sdk(base: &Value, extended: &Value) -> Result<()> {
    const SOURCE_LOCK_SHA: &str = "e9326b795fd142f8b07a8536a3d96e7f3a957d7ec965030753720d609f9d87b4";
    let previous_raw = include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/original642-source-lock.json");
    if previous_raw.len() != 368342 || digest(previous_raw) != "f8663e08af2e28f2a5bd1b9b9c0d183c5b9fa2a6521d2c97fbc2ed1d3e62165a" {
        return fail("immutable actual642 source fixture changed");
    }
    let previous: Value = serde_json::from_slice(previous_raw)?;
    validate_source_extension642(base, &previous)?;
    let delta_raw = include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/selection-delta.json");
    if delta_raw.len() != 862 || digest(delta_raw) != "b7ed5fef21572cb5ab04eb15d7521ff80185b8cc9a200d5c2d1fcc22f551ea50" {
        return fail("exact SDK samples source delta changed");
    }
    let delta: Value = serde_json::from_slice(delta_raw)?;
    if delta["schema"] != "native643-exact-sdk-samples-original-producer-extension-v1"
        || delta["previous_projects"] != 642 || delta["current_projects"] != 643
        || delta["previous_lock_sha256"] != "f8663e08af2e28f2a5bd1b9b9c0d183c5b9fa2a6521d2c97fbc2ed1d3e62165a"
        || delta["current_lock_sha256"] != SOURCE_LOCK_SHA
        || delta["new_original_files"] != 8044 || delta["new_primary_BP"] != 1
        || delta["source_and_full_qualified"] != false
        || !delta["added_sparse_cones"].as_object().ok_or("SDK cone delta absent")?.is_empty() {
        return fail("SDK samples source delta identity changed");
    }
    let additions = delta["added_projects"].as_array().ok_or("SDK project delta absent")?;
    if additions.len() != 1
        || additions[0]["path"] != "developers/build"
        || additions[0]["name"] != "platform/developers/build"
        || additions[0]["commit"] != "31d9b329ddc56636a279c7340e154e0d67d9a6fb"
        || additions[0]["sparse_paths"] != json!(["prebuilts/gradle", "prebuilts/androidtv"]) {
        return fail("one exact original SDK producer project required");
    }
    let mut expected = previous;
    let projects = expected["projects"].as_array_mut().ok_or("original642 projects absent")?;
    if projects.iter().any(|p| p["path"] == additions[0]["path"] || p["name"] == additions[0]["name"]) {
        return fail("SDK producer collides with original642 project");
    }
    projects.push(additions[0].clone());
    if projects.len() != 643 || expected != *extended {
        return fail("source differs beyond the exact original SDK producer and its two complete cones");
    }
    Ok(())
}

// Retain actual643 SDK history, then admit only the original path-tag providers.
fn validate_source_extension643_path_data(base: &Value, extended: &Value) -> Result<()> {
    const SOURCE_LOCK_SHA: &str = "7866f9c66e6b9dc418b0f9998c6d7724402e4a51a3cf51453087a8dad7b84b42";
    let old_raw = include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original643-source-lock.json");
    if old_raw.len() != 368740 || digest(old_raw) != "e9326b795fd142f8b07a8536a3d96e7f3a957d7ec965030753720d609f9d87b4" { return fail("immutable actual643 source fixture changed"); }
    let previous: Value = serde_json::from_slice(old_raw)?;
    validate_source_extension643_sdk(base, &previous)?;
    let delta_raw = include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/selection-delta.json");
    if delta_raw.len() != 991 || digest(delta_raw) != "0408f7c7aaea0a19c2fd929db4eb376555f5ee76f015886d9d3d7041e391470a" { return fail("exact path-tag source delta changed"); }
    let delta: Value = serde_json::from_slice(delta_raw)?;
    if delta["schema"] != "native643-exact-path-tag-original-provider-cone-extension-v1"
        || delta["previous_projects"] != 643 || delta["current_projects"] != 643
        || delta["previous_lock_sha256"] != "e9326b795fd142f8b07a8536a3d96e7f3a957d7ec965030753720d609f9d87b4" || delta["current_lock_sha256"] != SOURCE_LOCK_SHA
        || delta["new_original_files"] != 63 || delta["new_primary_BP"] != 8
        || delta["source_and_full_qualified"] != false
        || !delta["added_projects"].as_array().ok_or("path-tag project delta absent")?.is_empty() {
        return fail("path-tag source delta identity changed");
    }
    let cones=delta["added_sparse_cones"].as_object().ok_or("path-tag cone delta absent")?;
    if cones.len()!=3 { return fail("exact three existing original projects required"); }
    let mut expected=previous;
    let projects=expected["projects"].as_array_mut().ok_or("actual643 predecessor projects absent")?;
    for (path, additions) in cones {
        let matches: Vec<usize>=projects.iter().enumerate().filter_map(|(i,p)| (p["path"]==path.as_str()).then_some(i)).collect();
        if matches.len()!=1 { return fail("path-tag project missing or duplicated"); }
        let sparse=projects[matches[0]]["sparse_paths"].as_array_mut().ok_or("original sparse cones absent")?;
        for addition in additions.as_array().ok_or("exact path-tag additions absent")? {
            if sparse.contains(addition) { return fail("path-tag cone already present"); }
            sparse.push(addition.clone());
        }
    }
    if projects.len()!=643 || expected!=*extended { return fail("source differs beyond exact original path-tag provider cones"); }
    Ok(())
}


// The ordinary producer retains both complete original cones at the same SP commits.
// Generated API modules continue to come from the original Soong prebuilt_apis hook.
fn validate_source_extension643_compose_car(base: &Value, extended: &Value) -> Result<()> {
    const SOURCE_LOCK_SHA: &str = "6aacafd0aed644837e5616c658153f3ec6fa44c0e7ca2810e254f9fd0a2003a0";
    let old_raw = include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original643-path-data-source-lock.json");
    if old_raw.len() != 369125 || digest(old_raw) != "7866f9c66e6b9dc418b0f9998c6d7724402e4a51a3cf51453087a8dad7b84b42" {
        return fail("immutable complete path-data643 predecessor changed");
    }
    let previous: Value = serde_json::from_slice(old_raw)?;
    validate_source_extension643_path_data(base, &previous)?;
    let delta_raw = include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/selection-delta.json");
    if delta_raw.len() != 583 || digest(delta_raw) != "ee1e94bf6eade56fb5be2b2ebd69d76ebd66b78f8ac99c03d5e74801ba76c333" {
        return fail("exact Compose and Car original provider delta changed");
    }
    let delta: Value = serde_json::from_slice(delta_raw)?;
    if delta["schema"] != "native643-exact-compose-car-original-provider-cone-extension-v1"
        || delta["previous_projects"] != 643 || delta["current_projects"] != 643
        || delta["previous_lock_sha256"] != "7866f9c66e6b9dc418b0f9998c6d7724402e4a51a3cf51453087a8dad7b84b42"
        || delta["current_lock_sha256"] != SOURCE_LOCK_SHA
        || delta["new_original_files"] != 17 || delta["new_primary_BP"] != 2
        || delta["source_and_full_qualified"] != false
        || delta["added_projects"] != json!([])
        || delta["added_sparse_cones"] != json!({"packages/services/Car": ["prebuilts"], "prebuilts/misc": ["common/androidx-perf"]}) {
        return fail("Compose and Car exact provider scope changed");
    }
    let mut expected = previous;
    let projects = expected["projects"].as_array_mut().ok_or("path-data643 projects absent")?;
    for (path, commit, cone) in [
        ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "prebuilts"),
        ("prebuilts/misc", "be7c3a630b5dc5eb3260035d77a81b2f322754f8", "common/androidx-perf"),
    ] {
        let indices: Vec<usize> = projects.iter().enumerate().filter_map(|(i, p)| (p["path"] == path).then_some(i)).collect();
        if indices.len() != 1 || projects[indices[0]]["commit"] != commit {
            return fail("original Compose or Car project identity differs");
        }
        let sparse = projects[indices[0]]["sparse_paths"].as_array_mut().ok_or("original provider cones absent")?;
        if sparse.contains(&json!(cone)) { return fail("original provider cone already selected"); }
        sparse.push(json!(cone));
    }
    if projects.len() != 643 || expected != *extended {
        return fail("source differs beyond the two exact original Compose and Car provider cones");
    }
    Ok(())
}


// All three current multidevice consumers use the original complete Uwb snippet.
fn validate_source_extension643_ranging(base: &Value, extended: &Value) -> Result<()> {
    const SOURCE_LOCK_SHA: &str = "714a3542c632c50c1516a033bcde13426d67177934dbdbfc8006efc2190f5aec";
    let old_raw = include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original643-compose-car-source-lock.json");
    if old_raw.len() != 369178 || digest(old_raw) != "6aacafd0aed644837e5616c658153f3ec6fa44c0e7ca2810e254f9fd0a2003a0" {
        return fail("immutable Compose/Car643 predecessor changed");
    }
    let previous: Value = serde_json::from_slice(old_raw)?;
    validate_source_extension643_compose_car(base, &previous)?;
    let raw = include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/selection-delta.json");
    if raw.len() != 554 || digest(raw) != "5d2b3a71e2c091a8045db7885dfa1eb13d29e8468cb2e7d0caa3c966260a896f" { return fail("exact ranging source delta changed"); }
    let delta: Value = serde_json::from_slice(raw)?;
    if delta["schema"] != "native643-exact-ranging-snippet-original-provider-cone-extension-v1"
        || delta["previous_projects"] != 643 || delta["current_projects"] != 643
        || delta["previous_lock_sha256"] != "6aacafd0aed644837e5616c658153f3ec6fa44c0e7ca2810e254f9fd0a2003a0"
        || delta["current_lock_sha256"] != SOURCE_LOCK_SHA
        || delta["added_projects"] != json!([])
        || delta["added_sparse_cones"] != json!({"packages/modules/Uwb": ["ranging/tests/multidevices/snippet/uwb"]})
        || delta["new_original_files"] != 5 || delta["new_primary_BP"] != 1
        || delta["source_and_full_qualified"] != false {
        return fail("only the exact original ranging snippet cone is admitted");
    }
    let mut expected = previous;
    let projects = expected["projects"].as_array_mut().ok_or("previous643 projects absent")?;
    let matches: Vec<usize> = projects.iter().enumerate().filter_map(|(i,p)| (p["path"] == "packages/modules/Uwb").then_some(i)).collect();
    if matches.len() != 1 || projects[matches[0]]["commit"] != "7c9e03046ff41cc28cf794cc2eda306fbc40279e" {
        return fail("original fixed Uwb project differs");
    }
    let paths = projects[matches[0]]["sparse_paths"].as_array_mut().ok_or("original Uwb sparse cones absent")?;
    let cone = json!("ranging/tests/multidevices/snippet/uwb");
    if paths.contains(&cone) { return fail("ranging provider was already selected"); }
    paths.push(cone);
    if projects.len() != 643 || expected != *extended { return fail("source differs beyond one exact original ranging provider cone"); }
    Ok(())
}


// ApiDocs consumes the original merged compatibility config and host generator.
fn validate_source_extension643_global_compat(base: &Value, extended: &Value) -> Result<()> {
    const SOURCE_LOCK_SHA: &str = "e8b359276e49d6f520344284cbf2876f403d03150018d286ab8b0df362817e71";
    let old_raw = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original643-ranging-source-lock.json");
    if old_raw.len() != 369228 || digest(old_raw) != "714a3542c632c50c1516a033bcde13426d67177934dbdbfc8006efc2190f5aec" {
        return fail("immutable ranging643 predecessor changed");
    }
    let previous: Value = serde_json::from_slice(old_raw)?;
    validate_source_extension643_ranging(base, &previous)?;
    let raw = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/selection-delta.json");
    if raw.len() != 520 || digest(raw) != "2fdc8c5fc4e539df918c27af2fcdc71fba7e21ddb5e9befe8b64de59a33d3dfd" { return fail("exact global compatibility source delta changed"); }
    let delta: Value = serde_json::from_slice(raw)?;
    if delta["schema"] != "native643-exact-global-compat-original-provider-cone-extension-v1"
        || delta["previous_projects"] != 643 || delta["current_projects"] != 643
        || delta["previous_lock_sha256"] != "714a3542c632c50c1516a033bcde13426d67177934dbdbfc8006efc2190f5aec"
        || delta["current_lock_sha256"] != SOURCE_LOCK_SHA
        || delta["added_projects"] != json!([])
        || delta["added_sparse_cones"] != json!({"tools/platform-compat": ["build"]})
        || delta["new_original_files"] != 3 || delta["new_primary_BP"] != 1
        || delta["source_and_full_qualified"] != false {
        return fail("only the exact original global compatibility provider cone is admitted");
    }
    let mut expected = previous;
    let projects = expected["projects"].as_array_mut().ok_or("previous643 projects absent")?;
    let matches: Vec<usize> = projects.iter().enumerate().filter_map(|(i,p)| (p["path"] == "tools/platform-compat").then_some(i)).collect();
    if matches.len() != 1 || projects[matches[0]]["commit"] != "19ce1c9d406cec9feaf76618e7d772113883d73f" {
        return fail("original fixed platform compatibility project differs");
    }
    let paths = projects[matches[0]]["sparse_paths"].as_array_mut().ok_or("original platform compatibility sparse cones absent")?;
    let cone = json!("build");
    if paths.contains(&cone) { return fail("global compatibility provider was already selected"); }
    paths.push(cone);
    if projects.len() != 643 || expected != *extended { return fail("source differs beyond one exact original compatibility provider cone"); }
    Ok(())
}


// Select the complete original helper of the already selected graphics tests.
fn validate_source_extension(base: &Value, extended: &Value) -> Result<()> {
    let old_raw = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/original643-global-compat-source-lock.json");
    if old_raw.len() != 369245 || digest(old_raw) != "e8b359276e49d6f520344284cbf2876f403d03150018d286ab8b0df362817e71" { return fail("immutable global compatibility643 predecessor changed"); }
    let previous: Value = serde_json::from_slice(old_raw)?;
    validate_source_extension643_global_compat(base, &previous)?;
    let raw = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/selection-delta.json");
    if raw.len() != 536 || digest(raw) != "0e6e8f3d7510ed77f1c86cf2d15ee793abbc77e92ff9e110c8485c27be42e609" { return fail("exact original hotplug source delta changed"); }
    let delta: Value = serde_json::from_slice(raw)?;
    if delta["schema"] != "native643-exact-cuttlefish-hotplug-original-cone-extension-v1"
        || delta["previous_projects"] != 643 || delta["current_projects"] != 643
        || delta["previous_lock_sha256"] != "e8b359276e49d6f520344284cbf2876f403d03150018d286ab8b0df362817e71"
        || delta["current_lock_sha256"] != SOURCE_LOCK_SHA || delta["added_projects"] != json!([])
        || delta["added_sparse_cones"] != json!({"device/google/cuttlefish": ["tests/graphics/hotplug"]})
        || delta["new_original_files"] != 3 || delta["new_primary_BP"] != 1 || delta["source_and_full_qualified"] != false { return fail("only the exact original complete hotplug provider cone is admitted"); }
    let mut expected = previous;
    let projects = expected["projects"].as_array_mut().ok_or("previous643 projects absent")?;
    let matches: Vec<usize> = projects.iter().enumerate().filter_map(|(i,p)| (p["path"] == "device/google/cuttlefish").then_some(i)).collect();
    if matches.len() != 1 || projects[matches[0]]["commit"] != "283645aacf6cdb56cc31a9362f54d412dbc132a1" { return fail("original fixed Cuttlefish project differs"); }
    let paths = projects[matches[0]]["sparse_paths"].as_array_mut().ok_or("original Cuttlefish sparse cones absent")?;
    let cone = json!("tests/graphics/hotplug");
    if paths.contains(&cone) { return fail("hotplug helper was already selected"); }
    paths.push(cone);
    if projects.len() != 643 || expected != *extended { return fail("source differs beyond one exact complete original hotplug cone"); }
    Ok(())
}

/// Only this complete pair command selects the monotonic provider extension.
/// Every historical typed lock and every existing project/revision remains exact.
pub fn source_lock_path(repo: &Path) -> Result<PathBuf> {
    let base_path = crate::native_role_ingress::source_lock_path(repo)?;
    let base = fixed_file(&base_path, 96957, BASE_SOURCE_LOCK_SHA)?;
    let path = repo.join(PAIR_SOURCE_LOCK);
    let extended = fixed_file(&path, SOURCE_LOCK_BYTES, SOURCE_LOCK_SHA)?;
    validate_source_extension(&serde_json::from_slice(&base)?, &serde_json::from_slice(&extended)?)?;
    let lock = droidloom_source::load_lock(&path)?;
    let plan = droidloom_source::build_plan(&lock)?;
    if plan.projects.len() != 643 || plan.links.len() != 8 || plan.unrestricted_repo_sync {
        return fail("ordinary pair source plan widened");
    }
    Ok(path)
}

/// Existing source must already be the normal materializer's exact new plan.
/// No previous/shared workspace is silently expanded by the pair command.
pub fn verify_source_workspace(
    lock_path: &Path,
    lock: &droidloom_source::SparseSourceLock,
    source: &Path,
) -> Result<()> {
    for parent in source.ancestors().skip(1) {
        let metadata = fs::symlink_metadata(parent)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return fail("ordinary pair source parent must be a real directory");
        }
    }
    match fs::symlink_metadata(source) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            let expected = droidloom_source::MaterializedManifest {
                schema_version: 1,
                source_lock_sha256: SOURCE_LOCK_SHA.to_owned(),
                plan: droidloom_source::build_plan(lock)?,
            };
            let bytes = serde_json::to_vec_pretty(&expected)?;
            fixed_file(&source.join(".droidloom-source-manifest.json"), bytes.len(), &digest(&bytes))?;
            droidloom_source::verify_materialized(lock_path, lock, source)?;
            Ok(())
        }
        Ok(_) => fail("ordinary pair source workspace must be a real directory"),
    }
}
const ENABLED: &str = "-DBERBERIS_PROCMAPS_RAW_METADATA_OWNER=1";
const ORIGINAL_DEFAULTS: &str = r#"cc_defaults {
    name: "berberis_arm64_defaults",
    defaults: ["berberis_guest_agnostic_defaults"],
    compile_multilib: "64",
    arch: {
        // TODO(b/123294366): disconnect guest arch from host arch!
        x86_64: {
            cflags: ["-DNATIVE_BRIDGE_GUEST_ARCH_ARM64"],
        },
        riscv64: {
            cflags: ["-DNATIVE_BRIDGE_GUEST_ARCH_ARM64"],
        },
    },
}"#;

fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }

fn fixed_file(path: &Path, bytes: usize, sha: &str) -> Result<Vec<u8>> {
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
    for parent in path.ancestors().skip(1) {
        if !fs::symlink_metadata(parent)?.is_dir() {
            return fail("generation pair input parent must be a real directory");
        }
    }
    let mut file=OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW|libc::O_CLOEXEC).open(path)?;
    let before = file.metadata()?;
    if !before.is_file() || before.nlink() != 1 || before.len() != bytes as u64 {
        return fail("generation pair fixed input type, link count or length changed");
    }
    let mut raw=Vec::new();Read::by_ref(&mut file).take(bytes as u64+1).read_to_end(&mut raw)?;
    let state=|m:&fs::Metadata|(m.dev(),m.ino(),m.mode(),m.uid(),m.gid(),m.nlink(),m.len(),
                                 m.mtime(),m.mtime_nsec(),m.ctime(),m.ctime_nsec());
    if raw.len()!=bytes || state(&before)!=state(&file.metadata()?)
        || state(&before)!=state(&fs::symlink_metadata(path)?) || digest(&raw) != sha {
        return fail("generation pair fixed input identity or content changed");
    }
    Ok(raw)
}

fn engine_files(repo: &Path) -> Result<BTreeMap<String, String>> {
    let raw = fixed_file(&repo.join(INPUTS).join("engine-source-files.json"),
                         ENGINE_FILES_BYTES, ENGINE_FILES_SHA)?;
    let files: BTreeMap<String,String> = serde_json::from_slice(&raw)?;
    if files.len() != 926 || files.get("Android.bp").map(String::as_str) != Some(ENGINE_BP_SHA) {
        return fail("complete frozen 926-file engine input set required");
    }
    Ok(files)
}

fn enabled_blueprint(text: &str) -> Result<String> {
    if text.len() != ENGINE_BP_BYTES || digest(text.as_bytes()) != ENGINE_BP_SHA
        || text.matches(ORIGINAL_DEFAULTS).count() != 1 || text.contains(ENABLED) {
        return fail("ordinary generation defaults must start from the exact disabled engine source");
    }
    let enabled = ORIGINAL_DEFAULTS.replacen(
        "cflags: [\"-DNATIVE_BRIDGE_GUEST_ARCH_ARM64\"],",
        "cflags: [\"-DNATIVE_BRIDGE_GUEST_ARCH_ARM64\", \"-DBERBERIS_PROCMAPS_RAW_METADATA_OWNER=1\"],", 1);
    Ok(text.replacen(ORIGINAL_DEFAULTS, &enabled, 1))
}

fn record(path: &Path, value: Value) -> Result<()> {
    let mut file = OpenOptions::new().create_new(true).write(true).open(path)?;
    file.write_all(&serde_json::to_vec_pretty(&value)?)?;
    file.write_all(b"\n")?; file.sync_all()?;
    fs::File::open(path.parent().ok_or("pair record lacks parent")?)?.sync_all()?;
    Ok(())
}

pub fn validate_scope(targets: &[&str], strict: bool,
                      flavor: Option<crate::native_generation_art::Flavor>,
                      typed_ingress: bool, resume: bool) -> Result<()> {
    if targets != TARGETS || !strict || typed_ingress || resume
        || flavor != Some(crate::native_generation_art::Flavor::EnabledBuildOnly) {
        return fail("ordinary generation pair requires two fixed targets, strict dependencies, enabled paired ART and no private-role projection");
    }
    Ok(())
}

pub fn begin_attempt(repo: &Path, work: &Path, out: &Path) -> Result<()> {
    crate::native_generation_art::validated_output(work, out)?;
    engine_files(repo)?;
    let blueprint = fixed_file(&repo.join(INPUTS).join("engine.Android.bp"),
                               ENGINE_BP_BYTES, ENGINE_BP_SHA)?;
    enabled_blueprint(std::str::from_utf8(&blueprint)?)?;
    let lock = source_lock_path(repo)?;
    if hash(&lock)? != SOURCE_LOCK_SHA { return fail("ordinary pair source lock changed"); }
    fs::create_dir(out)?;
    record(&out.join("droidloom-native-generation-build-attempt.json"), json!({
        "schema": 1, "state": "CLAIMED_BEFORE_SOURCE_PROJECTION",
        "scope": "ordinary-app-complete-engine-art-pair", "targets": TARGETS,
        "dependency_mode": "Strict", "source_lock_sha256": SOURCE_LOCK_SHA,
        "source_projection_journal": work.join("source-projection.json"),
        "engine_compiled_macro": 1, "ART_compiled_macro": 1,
        "private_AppZygote_role_authorized": false, "installation_performed": false,
        "runtime_qualified": false,
    }))
}

fn check_snapshot(snapshot: &Value, expected: &BTreeMap<String,String>) -> Result<()> {
    if snapshot["commit"] != ENGINE_HEAD || snapshot["working_tree"] != true
        || snapshot["files"] != serde_json::to_value(expected)? {
        return fail("ordinary generation engine snapshot differs from its frozen commit and full file set");
    }
    Ok(())
}

// The pinned public Cuttlefish package refers to an undefined maintenance team.
// Only its exact 49-byte ownership field is removed. The complete C++ and Java
// consumers, license, dependencies and strict target scope remain unchanged.
// package.go validates this name; all_teams.go serializes optional ownership
// metadata. Neither rule applies runtime policy or changes compiler flags.
const VKMS_BLUEPRINT: &str = "device/google/cuttlefish/guest/commands/vkms_controller/Android.bp";
const VKMS_ORIGINAL_BYTES: usize = 1522;
const VKMS_ORIGINAL_SHA: &str = "fad92f331030a22d22d989e4df4f7b6fdd90f2d11b702f90fd1d26304783b45d";
const VKMS_EFFECTIVE_BYTES: usize = 1473;
const VKMS_EFFECTIVE_SHA: &str = "bd556a4385b92f6808a8d9df94f118a8b2f93e35a0598fef636fe0f91c075b7f";
const VKMS_UNRESOLVED_TEAM: &str = "    default_team: \"trendy_team_desktop_display\",\n";

fn vkms_maintenance_metadata(text: &str) -> Result<String> {
    if text.len() != VKMS_ORIGINAL_BYTES || digest(text.as_bytes()) != VKMS_ORIGINAL_SHA
        || text.matches(VKMS_UNRESOLVED_TEAM).count() != 1 {
        return fail("exact pinned Cuttlefish ownership metadata required");
    }
    let updated = text.replacen(VKMS_UNRESOLVED_TEAM, "", 1);
    if updated.len() != VKMS_EFFECTIVE_BYTES || digest(updated.as_bytes()) != VKMS_EFFECTIVE_SHA {
        return fail("Cuttlefish maintenance metadata delta escaped the single ownership field");
    }
    Ok(updated)
}

pub(crate) fn project_vkms_maintenance_metadata(
    source: &Path, projection: &mut crate::android::Projection,
) -> Result<()> {
    let path = source.join(VKMS_BLUEPRINT);
    let original = fixed_file(&path, VKMS_ORIGINAL_BYTES, VKMS_ORIGINAL_SHA)?;
    projection.put(&path, vkms_maintenance_metadata(std::str::from_utf8(&original)?)?)
}

pub(crate) fn vkms_maintenance_metadata_inputs(source: &Path, projection: &Value) -> Result<Value> {
    fixed_file(&source.join(VKMS_BLUEPRINT), VKMS_EFFECTIVE_BYTES, VKMS_EFFECTIVE_SHA)?;
    if projection["files"][VKMS_BLUEPRINT].as_str() != Some(VKMS_EFFECTIVE_SHA) {
        return fail("Cuttlefish ownership metadata change must be in the normal recovery journal");
    }
    Ok(json!({
        "path": VKMS_BLUEPRINT,
        "original_commit": "283645aacf6cdb56cc31a9362f54d412dbc132a1",
        "original_git_blob": "98b0aa455ee364e7c5fdf34a1408b315a6023b22",
        "original": {"bytes": VKMS_ORIGINAL_BYTES, "sha256": VKMS_ORIGINAL_SHA},
        "effective": {"bytes": VKMS_EFFECTIVE_BYTES, "sha256": VKMS_EFFECTIVE_SHA},
        "only_unresolved_default_team_field_removed": true,
        "complete_consumer_modules_preserved": ["vkms_controller", "CfVkmsControllerTest"],
        "targets_or_compiler_flags_changed": false,
        "runtime_security_policy_changed": false,
    }))
}

pub fn project_engine(repo: &Path, source: &Path, projection: &mut crate::android::Projection,
                      snapshot: &Value) -> Result<()> {
    let files = engine_files(repo)?;
    check_snapshot(snapshot, &files)?;
    let root = source.join(ENGINE);
    if crate::native_bridge::source_inventory(&root)? != files {
        return fail("imported engine tree changed before ordinary generation projection");
    }
    let blueprint = fixed_file(&repo.join(INPUTS).join("engine.Android.bp"),
                               ENGINE_BP_BYTES, ENGINE_BP_SHA)?;
    let enabled = enabled_blueprint(std::str::from_utf8(&blueprint)?)?;
    project_vkms_maintenance_metadata(source, projection)?;
    projection.put(&root.join("Android.bp"), enabled)
}

pub fn write_inputs(repo: &Path, source: &Path, out: &Path, selected: &[PathBuf],
                    projection: Value, snapshot: &Value) -> Result<()> {
    if selected != TARGETS.iter().map(|name| PathBuf::from(*name)).collect::<Vec<_>>() {
        return fail("ordinary generation pair resolved targets were widened or substituted");
    }
    let original = engine_files(repo)?;
    check_snapshot(snapshot, &original)?;
    let blueprint = fixed_file(&repo.join(INPUTS).join("engine.Android.bp"),
                               ENGINE_BP_BYTES, ENGINE_BP_SHA)?;
    let observed = crate::native_bridge::source_inventory(&source.join(ENGINE))?;
    validate_effective_engine(&original, &observed, &projection, std::str::from_utf8(&blueprint)?)?;
    let ownership_metadata = vkms_maintenance_metadata_inputs(source, &projection)?;
    record(&out.join("droidloom-native-generation-build-inputs.json"), json!({
        "schema": 1, "scope": "ordinary-app-complete-engine-art-pair",
        "targets": TARGETS, "selected_targets": selected, "dependency_mode": "Strict",
        "source_lock_sha256": SOURCE_LOCK_SHA, "engine_source_snapshot": snapshot,
        "frozen_engine_files_sha256": ENGINE_FILES_SHA,
        "effective_engine_files": observed,
        "frozen_ART_inputs": crate::native_generation_art::frozen_input_inventory()?,
        "effective_source_projection": projection,
        "maintenance_ownership_metadata": ownership_metadata,
        "ninja_response_file_retention_inputs": frozen_ninja_retention_inputs(source)?,
        "required_actual_compile_sources": ["art/runtime/runtime.cc",
            "art/runtime/native_bridge_art_interface.cc", "art/libnativebridge/native_bridge.cc",
            "art/libnativebridge/droidloom_generation.cc",
            "frameworks/libs/binary_translation/kernel_api/proc_maps_generation.cc",
            "frameworks/libs/binary_translation/kernel_api/proc_maps_provenance.cc",
            "frameworks/libs/binary_translation/kernel_api/unistd_emulation.cc"],
        "full_translation_unit_qualification_verified": false,
        "signature_and_payload_verification_complete": false,
        "private_AppZygote_role_authorized": false, "installation_performed": false,
        "runtime_qualified": false,
    }))
}

/// The pinned upstream final Ninja invocation already preserves response files.
/// This input observation makes no claim that Ninja has executed yet.
fn frozen_ninja_retention_inputs(source: &Path) -> Result<Value> {
    const NINJA_BYTES: usize = 2_563_376;
    const NINJA_SHA: &str = "645edd9a2b0294290c1d8331d4e8698c93625673b01e33ef25b79754badb6ad8";
    const DRIVER_BYTES: usize = 15_156;
    const DRIVER_SHA: &str = "44dcf1bc2c8e6c3f9a598c61b36c0a4bafa66f941a717a9c599826afd1d5351f";
    let ninja = source.join("prebuilts/build-tools/linux-x86/bin/ninja");
    let driver = source.join("build/soong/ui/build/ninja.go");
    fixed_file(&ninja, NINJA_BYTES, NINJA_SHA)?;
    fixed_file(&driver, DRIVER_BYTES, DRIVER_SHA)?;
    Ok(json!({
        "ninja": {"path": ninja, "bytes": NINJA_BYTES, "sha256": NINJA_SHA},
        "final_invocation_source": {"path": driver, "bytes": DRIVER_BYTES, "sha256": DRIVER_SHA},
        "upstream_default_debug_options": ["keepdepfile", "keeprsp"],
        "compiler_or_linker_flags_changed": false,
        "actual_execution_verified": false,
    }))
}

fn validate_effective_engine(original: &BTreeMap<String,String>, observed: &BTreeMap<String,String>,
                             projection: &Value, blueprint: &str) -> Result<()> {
    if original.keys().collect::<Vec<_>>() != observed.keys().collect::<Vec<_>>() {
        return fail("ordinary pair engine file set changed during normal projection");
    }
    // The unchanged normal NativeBridge projection redirects only build-time
    // proxy link references and two compatibility declarations. Retain it;
    // its actual final bytes must appear in the same journal inventory.
    for (name,value) in observed {
        if original.get(name) == Some(value) { continue; }
        let normal = matches!(name.as_str(), "Android.bp" | "native_activity/Android.bp"
            | "android_api/Android.bp" | "interpreter/arm64/interpreter.h")
            || (name.starts_with("android_api/") && name.ends_with("/Android.bp")
                && name.split('/').count() == 3);
        let path = format!("{ENGINE}/{name}");
        if !normal || projection["files"][&path].as_str() != Some(value.as_str()) {
            return fail("unexpected or unjournaled engine projection change");
        }
    }
    let final_blueprint = enabled_blueprint(blueprint)?.replace(
        "\"libandroid\"", "\"droidloom_native_bridge_host_libandroid\"");
    if observed.get("Android.bp") != Some(&digest(final_blueprint.as_bytes())) {
        return fail("fixed ordinary generation defaults or normal link references changed");
    }
    Ok(())
}

pub fn write_command_completion(out: &Path, product: &str) -> Result<()> {
    // Pair creation re-extracts the real full APEX and checks all three compiled
    // ELF markers and hashes. It expressly does not claim signature validation.
    let pair = crate::native_generation::create_product_contract(
        &out.join("target/product").join(product))?;
    record(&out.join("droidloom-native-generation-build-command.json"), json!({
        "schema": 1, "state": "NORMAL_BUILD_SUCCEEDED_ACTUAL_PAIR_RECORDED",
        "targets": TARGETS, "dependency_mode": "Strict", "source_projection_restored": true,
        "compiled_engine_ART_pair": pair, "full_translation_unit_qualification_verified": false,
        "signature_and_payload_verification_complete": false,
        "private_AppZygote_role_authorized": false, "installation_performed": false,
        "runtime_qualified": false,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    // These unchanged tests continue authenticating the actual607 history.
    use super::validate_source_extension607 as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 357293;
    const SOURCE_LOCK_SHA: &str = "2c57d50f68aa8db89dcbd6beaaba2057bd61fca881dcfbbf8873d0a4047fb7eb";
    use crate::native_generation_art::Flavor;
    #[test]
    fn ordinary_pair_source_extension_is_exact_and_monotonic() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let raw = include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json");
        assert_eq!(raw.len(), SOURCE_LOCK_BYTES);
        assert_eq!(digest(raw), SOURCE_LOCK_SHA);
        let extended: Value = serde_json::from_slice(raw).unwrap();
        validate_source_extension(&base, &extended).unwrap();
        let lock: droidloom_source::SparseSourceLock = serde_json::from_slice(raw).unwrap();
        let plan = droidloom_source::build_plan(&lock).unwrap();
        assert_eq!((plan.projects.len(), plan.links.len(), plan.unrestricted_repo_sync), (607, 8, false));
        assert_eq!(base["status"], extended["status"]);
    }
    #[test]
    fn ordinary_pair_llvm_plugins_require_complete_original_cones() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        let mut previous_without_plugins = good.clone();
        for (path, commit) in [
            ("external/llvm", "429d6c6097aea3326e49fc8e87cc7658b750c5d7"),
            ("external/clang", "bdc4d062dc4550869e0825da19fe8fa720db860a"),
        ] {
            let project = good["projects"].as_array().unwrap().iter()
                .find(|p| p["path"] == path).unwrap();
            assert_eq!(project["commit"], commit);
            assert_eq!(project["sparse_paths"].as_array().unwrap().iter()
                .filter(|p| *p == "soong").count(), 1);
            // A Blueprint-only selection still omits the Go registration
            // sources and must not reproduce the observed full-build failure.
            let one_go_file = if path == "external/llvm" { "soong/llvm.go" } else { "soong/clang.go" };
            for replacement in [None, Some("soong/Android.bp"), Some(one_go_file)] {
                let mut incomplete = good.clone();
                let p = incomplete["projects"].as_array_mut().unwrap().iter_mut()
                    .find(|p| p["path"] == path).unwrap();
                let paths = p["sparse_paths"].as_array_mut().unwrap();
                paths.retain(|value| value != "soong");
                if let Some(value) = replacement { paths.push(json!(value)); }
                assert!(validate_source_extension(&base, &incomplete).is_err(),
                    "the complete original plugin cone is required: {path}");
            }
            let mut wrong_revision = good.clone();
            let p = wrong_revision["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            p["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &wrong_revision).is_err());
            let p = previous_without_plugins["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|value| value != "soong");
        }
        // Generic materialization can accept the old incomplete selection;
        // this complete-pair route must reject that exact omission.
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(previous_without_plugins.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &previous_without_plugins).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    #[test]
    fn ordinary_pair_r3_confirmed_providers_require_complete_original_inputs() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r3 = original606_for_history();
        remove_later_tradefed_cones(&mut actual_failed_r3);
        // Reconstruct historical bytes before the later complete signature provider selection.
        let cts = actual_failed_r3["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "cts").unwrap();
        let cts_paths = cts["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(cts_paths.iter().filter(|p| p.as_str() == Some("tests/signature/lib/common")).count(), 1);
        cts_paths.retain(|p| p != "tests/signature/lib/common");
        // Keep the original r3 failed bytes exact after the later RKPD input addition.
        let rkpd = actual_failed_r3["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "packages/modules/RemoteKeyProvisioning").unwrap();
        let rkpd_paths = rkpd["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(rkpd_paths.iter().filter(|p| p.as_str() == Some("apex")).count(), 1);
        rkpd_paths.retain(|p| p != "apex");
        actual_failed_r3["projects"].as_array_mut().unwrap().truncate(597);
        for (path, selection) in [
            ("cts", "apps/CameraFeatureCombinationVerifier"),
            ("cts", "apps/CarWatchdogCompanionApp"),
            ("cts", "apps/CrossProfileTestApp"),
            ("cts", "apps/CtsVerifierUSBCompanion"),
            ("cts", "apps/DeviceControlsApp"),
            ("cts", "apps/EmptyDeviceAdmin"),
            ("cts", "apps/EmptyDeviceOwner"),
            ("cts", "apps/NotesApp"),
            ("cts", "apps/NotificationBot"),
            ("cts", "apps/PermissionApp"),
            ("cts", "apps/TileServiceApp"),
            ("cts", "apps/TtsTestApp"),
            ("cts", "apps/VpnApp"),
            ("cts", "common/device-side/bedstead/deviceadminapp"),
            ("cts", "common/device-side/bedstead/metricsrecorder"),
            ("cts", "common/device-side/device-info"),
            ("cts", "common/device-side/util-axt/tests"),
            ("cts", "hostsidetests/appsecurity/test-apps"),
            ("cts", "hostsidetests/compilation/app_using_other_app"),
            ("cts", "hostsidetests/devicepolicy/app"),
            ("cts", "hostsidetests/os/app"),
            ("cts", "hostsidetests/os/test-apps"),
            ("cts", "hostsidetests/scopedstorage/libs/ScopedStorageTestLib"),
            ("cts", "hostsidetests/statsdatom/apps/adpfapp"),
            ("cts", "hostsidetests/statsdatom/apps/expressloghelperapp"),
            ("cts", "hostsidetests/statsdatom/apps/statsdapp"),
            ("cts", "tests/jdwp/runner/host-side"),
            ("cts", "tests/signature/api"),
            ("cts", "tests/tests/keystore"),
            ("cts", "tests/tests/os/jni"),
            ("cts", "tests/tests/packageinstaller/test-apps/emptytestapp"),
            ("cts", "tests/tests/telecom"),
            ("cts", "tests/tests/telecom-apps/ConnectionServiceVoipAppClone"),
            ("cts", "tests/tests/telecom-apps/ConnectionServiceVoipAppMain"),
            ("cts", "tests/tests/telecom-apps/ManagedConnectionService"),
            ("cts", "tests/tests/telecom-apps/ManagedConnectionServiceClone"),
            ("cts", "tests/tests/telecom-apps/TransactionalVoipAppClone"),
            ("cts", "tests/tests/telecom-apps/TransactionalVoipAppMain"),
            ("cts", "tests/tests/telecom-apps/Utils"),
            ("cts", "tests/tests/telecom-cuj"),
            ("cts", "tests/tests/telecom2"),
            ("cts", "tests/tests/telecom3"),
            ("cts", "tools/cts-dynamic-config"),
            ("external/llvm", "lib/Target/AArch64/AsmParser"),
            ("external/llvm", "lib/Target/AArch64/TargetInfo"),
            ("external/llvm", "lib/Target/ARM/AsmParser"),
            ("external/llvm", "lib/Target/ARM/Disassembler"),
            ("external/llvm", "lib/Target/ARM/TargetInfo"),
            ("external/llvm", "lib/Target/Mips/AsmParser"),
            ("external/llvm", "lib/Target/Mips/Disassembler"),
            ("external/llvm", "lib/Target/Mips/TargetInfo"),
            ("external/llvm", "lib/Target/X86/TargetInfo"),
            ("packages/modules/AdServices", "apex/permissions"),
            ("packages/modules/Bluetooth", "apex/permissions"),
            ("packages/modules/Bluetooth", "framework/tests/util"),
            ("packages/modules/Bluetooth", "tests/pandora/android_server"),
            ("packages/modules/Bluetooth", "tests/pandora/bumble_server"),
            ("packages/modules/Bluetooth", "tests/pandora/interfaces/python"),
            ("packages/modules/Bluetooth", "tests/pandora/mmi2grpc"),
            ("packages/modules/Connectivity", "Tethering/apex/permissions"),
            ("packages/modules/Connectivity", "nearby/flags"),
            ("packages/modules/Connectivity", "remoteauth/service"),
            ("packages/modules/DeviceLock", "DeviceLockController/Android.bp"),
            ("packages/modules/DeviceLock", "DeviceLockController/AndroidManifest.xml"),
            ("packages/modules/DeviceLock", "DeviceLockController/AndroidManifestBase.xml"),
            ("packages/modules/DeviceLock", "DeviceLockController/NOTICE"),
            ("packages/modules/DeviceLock", "DeviceLockController/lint-baseline.xml"),
            ("packages/modules/DeviceLock", "DeviceLockController/proguard.flags"),
            ("packages/modules/DeviceLock", "DeviceLockController/proto"),
            ("packages/modules/DeviceLock", "DeviceLockController/res"),
            ("packages/modules/DeviceLock", "DeviceLockController/src"),
            ("packages/modules/DeviceLock", "DeviceLockController/sysconfig"),
            ("packages/modules/DeviceLock", "permissions"),
            ("packages/modules/DeviceLock", "service"),
            ("packages/modules/HealthFitness", "apex/permissions"),
            ("packages/modules/HealthFitness", "apk/.gitignore"),
            ("packages/modules/HealthFitness", "apk/Android.bp"),
            ("packages/modules/HealthFitness", "apk/AndroidManifest.xml"),
            ("packages/modules/HealthFitness", "apk/HealthPermissionsManifest.xml"),
            ("packages/modules/HealthFitness", "apk/ManageHealthDataManifest.xml"),
            ("packages/modules/HealthFitness", "apk/ManageHealthPermissionsManifest.xml"),
            ("packages/modules/HealthFitness", "apk/OWNERS"),
            ("packages/modules/HealthFitness", "apk/StartCloudBackupAndRestoreSettingsManifest.xml"),
            ("packages/modules/HealthFitness", "apk/StartOnboardingManifest.xml"),
            ("packages/modules/HealthFitness", "apk/com.android.healthconnect.controller.pk8"),
            ("packages/modules/HealthFitness", "apk/com.android.healthconnect.controller.x509.pem"),
            ("packages/modules/HealthFitness", "apk/lint-baseline.xml"),
            ("packages/modules/HealthFitness", "apk/proguard.flags"),
            ("packages/modules/HealthFitness", "apk/res"),
            ("packages/modules/HealthFitness", "apk/src"),
            ("packages/modules/HealthFitness", "apk/sysconfig"),
            ("packages/modules/HealthFitness", "backuprestore/Android.bp"),
            ("packages/modules/HealthFitness", "backuprestore/AndroidManifest.xml"),
            ("packages/modules/HealthFitness", "backuprestore/OWNERS"),
            ("packages/modules/HealthFitness", "backuprestore/PermissionsManifest.xml"),
            ("packages/modules/HealthFitness", "backuprestore/com.android.health.connect.backuprestore.pk8"),
            ("packages/modules/HealthFitness", "backuprestore/com.android.health.connect.backuprestore.x509.pem"),
            ("packages/modules/HealthFitness", "backuprestore/src"),
            ("packages/modules/HealthFitness", "backuprestore/sysconfig"),
            ("packages/modules/OnDevicePersonalization", "federatedcompute/apk"),
            ("packages/modules/Permission", "SafetyCenter/Resources"),
            ("packages/modules/Permission", "permissions"),
            ("packages/modules/Permission", "sysconfig"),
            ("packages/modules/Permission", "tests/cts/permission/permissionTestUtilLib"),
            ("packages/modules/Scheduling", "service"),
            ("packages/modules/SdkExtensions", "javatests/com/android/sdkext/extensions/apps"),
            ("packages/modules/Telephony", "tests/mcts"),
            ("packages/modules/Uwb", "androidx_backend"),
            ("packages/modules/Uwb", "ranging/rtt_backend"),
            ("packages/modules/Uwb", "ranging/service"),
            ("packages/modules/Uwb", "ranging/tests/multidevices/snippet/bluetooth"),
            ("packages/modules/Uwb", "ranging/uwb_backend"),
            ("packages/modules/Wifi", "OsuLogin"),
            ("packages/modules/Wifi", "WifiDialog"),
            ("packages/providers/MediaProvider", "apex/permissions"),
            ("system/chre", "java/test/audio_concurrency"),
            ("system/chre", "java/test/ble_concurrency"),
            ("system/chre", "java/test/chqts"),
            ("system/chre", "java/test/chre_concurrency"),
            ("system/chre", "java/test/cross_validation"),
            ("system/chre", "java/test/endpoint"),
            ("system/chre", "java/test/permissions"),
            ("system/chre", "java/test/rpc_service"),
            ("system/chre", "java/test/settings"),
            ("system/chre", "java/test/stress"),
            ("system/chre", "java/test/utils"),
            ("system/chre", "java/utils/pigweed"),
        ] {
            let project = actual_failed_r3["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == selection).count(), 1);
            paths.retain(|p| p != selection);
        }
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r3).unwrap());
        assert_eq!(digest(failed_raw.as_bytes()), "b1fb40b9de4e2ab35407022862706b9d0a7e580a59e607b27bc9d99ec0a67fbb");
        let generic: droidloom_source::SparseSourceLock = serde_json::from_value(actual_failed_r3.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r3).is_err());
        for path in ["external/mime-support", "external/android-key-attestation", "external/wycheproof"] {
            let mut missing = good.clone();
            missing["projects"].as_array_mut().unwrap().retain(|p| p["path"] != path);
            assert!(validate_source_extension(&base, &missing).is_err());
        }
        // Android.bp alone omits the actual service and Controller source.
        for (path, selection) in [("packages/modules/DeviceLock", "service"),
                                  ("packages/modules/DeviceLock", "DeviceLockController/src"),
                                  ("packages/modules/Scheduling", "service")] {
            let mut partial = good.clone();
            let project = partial["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != selection);
            paths.push(json!(format!("{selection}/Android.bp")));
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }



    fn original606_for_history() -> Value {
        let raw = include_bytes!("../../../android/native-generation-pair/browser-helper-fixtures/original606-source-lock.json");
        assert_eq!(raw.len(), 356905);
        assert_eq!(digest(raw), "5e7d6e1a1bc8cb1151bf2312b1ca301f9b1f6070711474f464129b76dbf6eb61");
        serde_json::from_slice(raw).unwrap()
    }

    // Reconstruct immutable previous locks before testing their original failures.
    fn remove_later_five_apex_inputs(value: &mut Value) {
        {
            let project = value["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/Nfc").unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "apex").count(), 1);
            paths.retain(|p| p != "apex");
            assert_eq!(paths.iter().filter(|p| *p == "libnfc-nci/conf").count(), 1);
            paths.retain(|p| p != "libnfc-nci/conf");
        }
        {
            let project = value["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/NpuManager").unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "apex").count(), 1);
            paths.retain(|p| p != "apex");
            assert_eq!(paths.iter().filter(|p| *p == "service").count(), 1);
            paths.retain(|p| p != "service");
        }
        {
            let project = value["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/Profiling").unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "apex").count(), 1);
            paths.retain(|p| p != "apex");
            assert_eq!(paths.iter().filter(|p| *p == "service").count(), 1);
            paths.retain(|p| p != "service");
        }
        {
            let project = value["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/UprobeStats").unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "apex").count(), 1);
            paths.retain(|p| p != "apex");
            assert_eq!(paths.iter().filter(|p| *p == "bpfloader").count(), 1);
            paths.retain(|p| p != "bpfloader");
            assert_eq!(paths.iter().filter(|p| *p == "bpf_progs").count(), 1);
            paths.retain(|p| p != "bpf_progs");
        }
        {
            let project = value["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/WebApp").unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "apex").count(), 1);
            paths.retain(|p| p != "apex");
            assert_eq!(paths.iter().filter(|p| *p == "service").count(), 1);
            paths.retain(|p| p != "service");
            assert_eq!(paths.iter().filter(|p| *p == "template").count(), 1);
            paths.retain(|p| p != "template");
        }
        {
            let project = value["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "system/memory/libdmabufheap").unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "rust").count(), 1);
            paths.retain(|p| p != "rust");
        }
        assert_eq!(value["projects"].as_array().unwrap().iter().filter(|p| p["path"] == "external/jmustache").count(), 1);
        value["projects"].as_array_mut().unwrap().retain(|p| p["path"] != "external/jmustache");
        assert_eq!(value["projects"].as_array().unwrap().iter().filter(|p| p["path"] == "system/memory/libwrapfd").count(), 1);
        value["projects"].as_array_mut().unwrap().retain(|p| p["path"] != "system/memory/libwrapfd");
    }

    // The NDK library is an original provider distinct from the platform ART library.
    fn remove_later_nativehelper_ndk_cone(value: &mut Value) {
        remove_later_five_apex_inputs(value);
        let extras = value["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "system/extras").unwrap();
        assert_eq!(extras["commit"], "1289e9b3f282909eec6e80414e14dcc207bda439");
        let paths = extras["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "module_ndk_libs").count(), 1);
        assert_eq!(paths.iter().filter(|p| *p == "module_ndk_libs/libnativehelper").count(), 1);
        paths.retain(|p| p != "module_ndk_libs" && p != "module_ndk_libs/libnativehelper");
    }

    #[test]
    fn ordinary_pair_nativehelper_ndk_requires_complete_original_cone() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r4 = original606_for_history();
        remove_later_nativehelper_ndk_cone(&mut actual_failed_r4);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r4).unwrap());
        assert_eq!(failed_raw.len(), 355949);
        assert_eq!(digest(failed_raw.as_bytes()), "31cd9670543e4062f62dfd5c9e59c3700e541a158f6aee8a112b75b9cea70dfc");
        let generic: droidloom_source::SparseSourceLock = serde_json::from_value(actual_failed_r4.clone()).unwrap();
        assert_eq!(droidloom_source::build_plan(&generic).unwrap().projects.len(), 604);
        assert!(validate_source_extension(&base, &actual_failed_r4).is_err());
        let index = good["projects"].as_array().unwrap().iter().position(|p| p["path"] == "system/extras").unwrap();
        // H326 really published the parent cone. Retain it rather than weaken
        // the normal materializer's literal monotonic-plan requirement.
        let mut observed_quick = original606_for_history();
        remove_later_five_apex_inputs(&mut observed_quick);
        observed_quick["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .retain(|p| p != "module_ndk_libs/libnativehelper");
        let quick_raw = format!("{}\n", serde_json::to_string_pretty(&observed_quick).unwrap());
        assert_eq!(quick_raw.len(), 355976);
        assert_eq!(digest(quick_raw.as_bytes()), "a3437ed264c031774481270859d17bc995672a31f59b7ef293553f3b3fcaac7f");
        assert!(validate_source_extension(&base, &observed_quick).is_err());
        let mut previous_formal = original606_for_history();
        remove_later_five_apex_inputs(&mut previous_formal);
        previous_formal["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .retain(|p| p != "module_ndk_libs");
        let formal_raw = format!("{}\n", serde_json::to_string_pretty(&previous_formal).unwrap());
        assert_eq!(formal_raw.len(), 355992);
        assert_eq!(digest(formal_raw.as_bytes()), "a0bcdac2fb5dd496a2fdcd42baf9d99a80085d6279a2edf8ae29f750958a779c");
        assert!(validate_source_extension(&base, &previous_formal).is_err());
        let previous_paths = observed_quick["projects"][index]["sparse_paths"].as_array().unwrap();
        let current_paths = good["projects"][index]["sparse_paths"].as_array().unwrap();
        assert!(previous_paths.iter().all(|path| current_paths.contains(path)));
        assert_eq!(current_paths.len(), previous_paths.len() + 1);
        for invalid in [
            json!(["module_ndk_libs/libnativehelper/Android.bp"]),
            json!(["module_ndk_libs/libnativehelper/include", "module_ndk_libs/libnativehelper/include_jni"]),
            json!(["module_ndk_libs/libnativehelper/libnativehelper.map.txt"]),
            json!(["module_ndk_libs/libnativehelper/Android.bp", "module_ndk_libs/libnativehelper/include", "module_ndk_libs/libnativehelper/include_jni", "module_ndk_libs/libnativehelper/libnativehelper.map.txt"]),
            json!(["module_ndk_libs"]),
        ] {
            let mut changed = good.clone();
            let paths = changed["projects"][index]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "module_ndk_libs" && p != "module_ndk_libs/libnativehelper");
            paths.extend(invalid.as_array().unwrap().iter().cloned());
            assert!(validate_source_extension(&base, &changed).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut missing_old_input = good.clone();
        missing_old_input["projects"][index]["sparse_paths"].as_array_mut().unwrap().retain(|p| p != "ext4_utils");
        assert!(validate_source_extension(&base, &missing_old_input).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Retain exact older source generations while extending only the observed utility inputs.
    fn remove_later_microdroid_inputs(value: &mut Value) {
        remove_later_nativehelper_ndk_cone(value);
        for (path, commit) in [
            ("external/mksh", "71d564487c9b34f65961570073f037658e07eb06"),
            ("external/strace", "4da9987aca2eedf386d1e22e19994a1b0de53c45"),
        ] {
            let projects = value["projects"].as_array_mut().unwrap();
            let found: Vec<_> = projects.iter().filter(|p| p["path"] == path).collect();
            assert_eq!(found.len(), 1);
            assert_eq!(found[0]["commit"], commit);
            assert!(found[0].get("sparse_paths").is_none());
            projects.retain(|p| p["path"] != path);
        }
        let security = value["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "system/security").unwrap();
        assert_eq!(security["commit"], "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb");
        let paths = security["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "prng_seeder").count(), 1);
        paths.retain(|p| p != "prng_seeder");
    }

    #[test]
    fn ordinary_pair_microdroid_requires_exact_original_utilities() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        assert_eq!(good["superproject"]["commit"], "28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        let mut actual_failed_full = original606_for_history();
        remove_later_microdroid_inputs(&mut actual_failed_full);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_full).unwrap());
        assert_eq!(failed_raw.len(), 355378);
        assert_eq!(digest(failed_raw.as_bytes()), "dfee3de6092322f72d2278f5e87a07f2efa13de5c81467945018c1bcf083b3d2");
        let generic: droidloom_source::SparseSourceLock = serde_json::from_value(actual_failed_full.clone()).unwrap();
        assert_eq!(droidloom_source::build_plan(&generic).unwrap().projects.len(), 602);
        assert!(validate_source_extension(&base, &actual_failed_full).is_err());
        for path in ["external/mksh", "external/strace"] {
            let index = good["projects"].as_array().unwrap().iter().position(|p| p["path"] == path).unwrap();
            let mut missing = good.clone();
            missing["projects"].as_array_mut().unwrap().remove(index);
            assert!(validate_source_extension(&base, &missing).is_err());
            let mut wrong_commit = good.clone();
            wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &wrong_commit).is_err());
            let mut blueprint_only = good.clone();
            blueprint_only["projects"][index]["sparse_paths"] = json!(["Android.bp"]);
            assert!(validate_source_extension(&base, &blueprint_only).is_err());
        }
        let security = good["projects"].as_array().unwrap().iter().position(|p| p["path"] == "system/security").unwrap();
        for invalid in [
            json!(["prng_seeder/Android.bp"]),
            json!(["prng_seeder/src"]),
            json!(["prng_seeder/src/main.rs"]),
            json!(["prng_seeder/Android.bp", "prng_seeder/src", "prng_seeder/prng_seeder.rc"]),
        ] {
            let mut partial = good.clone();
            let paths = partial["projects"][security]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "prng_seeder");
            paths.extend(invalid.as_array().unwrap().iter().cloned());
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut wrong_security = good.clone();
        wrong_security["projects"][security]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_security).is_err());
        let mut lost_prior_security = good.clone();
        lost_prior_security["projects"][security]["sparse_paths"].as_array_mut().unwrap().retain(|p| p != "provisioner");
        assert!(validate_source_extension(&base, &lost_prior_security).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Preserve both CTS JNI modules and every original input at the same commit.
    fn remove_later_permission_jni_cone(value: &mut Value) {
        remove_later_microdroid_inputs(value);
        let project = value["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "packages/modules/Permission").unwrap();
        assert_eq!(project["commit"], "1093eca7407576c72e51b1a88550ee0667a6e5dc");
        let paths = project["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "tests/cts/permission/jni").count(), 1);
        paths.retain(|p| p != "tests/cts/permission/jni");
    }

    #[test]
    fn ordinary_pair_permission_jni_requires_complete_original_cone() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_full = original606_for_history();
        remove_later_permission_jni_cone(&mut actual_failed_full);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_full).unwrap());
        assert_eq!(failed_raw.len(), 355342);
        assert_eq!(digest(failed_raw.as_bytes()), "674d00a2721ed08e1d72709656c73f804950657ea007acf9dea20761a0b271a6");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_full.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_full).is_err());
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "packages/modules/Permission").unwrap();
        for invalid in [
            json!(["tests/cts/permission/jni/Android.bp"]),
            json!(["tests/cts/permission/jni/CtsPermissionsJniOnLoad.cpp"]),
            json!(["tests/cts/permission/jni/PermissionManagerNativeJniTest.cpp"]),
            json!(["tests/cts/permission/jni/android_permission_cts_FileUtils.cpp"]),
            json!(["tests/cts/permission/jni/Android.bp", "tests/cts/permission/jni/PermissionManagerNativeJniTest.cpp"]),
            json!(["tests/cts/permission"]),
        ] {
            let mut changed = good.clone();
            changed["projects"][index]["sparse_paths"].as_array_mut().unwrap()
                .retain(|p| p != "tests/cts/permission/jni");
            changed["projects"][index]["sparse_paths"].as_array_mut().unwrap()
                .extend(invalid.as_array().unwrap().iter().cloned());
            assert!(validate_source_extension(&base, &changed).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut lost_existing_provider = good.clone();
        lost_existing_provider["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .retain(|p| p != "tests/cts/permission/permissionTestUtilLib");
        assert!(validate_source_extension(&base, &lost_existing_provider).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Remove only the new cone when reconstructing historical source locks.
    // The ordinary pair keeps both original files at the locked tools/security commit.
    fn remove_later_libfuzzer_mte_cone(value: &mut Value) {
        remove_later_permission_jni_cone(value);
        let project = value["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "tools/security").unwrap();
        assert_eq!(project["commit"], "e4e7ba1dabe64f33b9894624e43763bd8a3cbca5");
        let paths = project["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "fuzzing/libFuzzer_mte_crash_handler").count(), 1);
        paths.retain(|p| p != "fuzzing/libFuzzer_mte_crash_handler");
    }

    #[test]
    fn ordinary_pair_libfuzzer_mte_requires_complete_original_cone() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r15 = original606_for_history();
        remove_later_libfuzzer_mte_cone(&mut actual_failed_r15);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r15).unwrap());
        assert_eq!(failed_raw.len(), 355295);
        assert_eq!(digest(failed_raw.as_bytes()), "3314ff8b2e1efae78c4a6ec656003cb21ef2faefe43cbbbe841dcac3032e2c3f");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r15.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r15).is_err());
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "tools/security").unwrap();
        // Either file alone loses an original build input. A parent selection
        // also imports unrelated fuzzers and is not the authenticated cone.
        for invalid in [
            json!(["fuzzing/libFuzzer_mte_crash_handler/Android.bp"]),
            json!(["fuzzing/libFuzzer_mte_crash_handler/crash_handler.cpp"]),
            json!(["fuzzing"]),
        ] {
            let mut changed = good.clone();
            changed["projects"][index]["sparse_paths"].as_array_mut().unwrap()
                .retain(|p| p != "fuzzing/libFuzzer_mte_crash_handler");
            changed["projects"][index]["sparse_paths"].as_array_mut().unwrap()
                .extend(invalid.as_array().unwrap().iter().cloned());
            assert!(validate_source_extension(&base, &changed).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut lost_existing_provider = good.clone();
        lost_existing_provider["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .retain(|p| p != "remote_provisioning/hwtrust");
        assert!(validate_source_extension(&base, &lost_existing_provider).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Reconstruct exact earlier locks without carrying this later provider cone.
    // The ordinary pair itself always requires every original shims input.
    fn remove_later_cronet_shims_cone(value: &mut Value) {
        remove_later_libfuzzer_mte_cone(value);
        let project = value["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "external/cronet").unwrap();
        assert_eq!(project["commit"], "e184145f12ee023d07372bd6db33341b671cee27");
        let paths = project["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "android/java/shims").count(), 1);
        paths.retain(|p| p != "android/java/shims");
    }

    #[test]
    fn ordinary_pair_cronet_shims_requires_complete_original_cone() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r14 = original606_for_history();
        remove_later_cronet_shims_cone(&mut actual_failed_r14);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r14).unwrap());
        assert_eq!(failed_raw.len(), 355265);
        assert_eq!(digest(failed_raw.as_bytes()), "b80751b1d878fa38a527f25eab4d6ea141cdcda1e5daf053792c152d782a64aa");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r14.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r14).is_err());
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "external/cronet").unwrap();
        // These retain old paths but omit the Blueprint, Java sources, jarjar
        // rules, or one original Java file. None is the complete original cone.
        for incomplete in [
            json!(["android/java/shims/Android.bp"]),
            json!(["android/java/shims/srcs"]),
            json!(["android/java/shims/Android.bp", "android/java/shims/srcs"]),
            json!(["android/java/shims/Android.bp", "android/java/shims/connectivity_jarjar_rules.txt",
                   "android/java/shims/srcs/org/chromium/base/ContextUtils.java",
                   "android/java/shims/srcs/org/chromium/base/Log.java"]),
        ] {
            let mut partial = good.clone();
            let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "android/java/shims");
            paths.extend(incomplete.as_array().unwrap().iter().cloned());
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut widened = good.clone();
        widened["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .push(json!("android/java"));
        assert!(validate_source_extension(&base, &widened).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Remove this latest project only when reconstructing exact historical
    // failed locks. The production pair always requires the whole selection.
    fn remove_later_eyedropper_project(value: &mut Value) {
        remove_later_cronet_shims_cone(value);
        let projects = value["projects"].as_array_mut().unwrap();
        assert_eq!(projects.iter().filter(|p| p["path"] == "packages/apps/EyeDropper").count(), 1);
        projects.retain(|p| p["path"] != "packages/apps/EyeDropper");
    }

    #[test]
    fn ordinary_pair_eyedropper_requires_original_declarations_and_retained_library() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r13 = original606_for_history();
        remove_later_eyedropper_project(&mut actual_failed_r13);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r13).unwrap());
        assert_eq!(failed_raw.len(), 354910);
        assert_eq!(digest(failed_raw.as_bytes()), "74372a62836ec16c30a6f24c6e13725831f90e13f2bbc4c9f9f56c74895b163d");
        let generic: droidloom_source::SparseSourceLock = serde_json::from_value(actual_failed_r13.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r13).is_err());
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "packages/apps/EyeDropper").unwrap();
        assert_eq!(good["projects"][index]["commit"], "225af0c6253316198738699de9041d1f28d0df44");
        for incomplete in [json!(["Android.bp"]), json!(["flags"]), json!(["src", "res"]),
                           json!(["flags/eye_dropper_flags.aconfig", "res", "src"])] {
            let mut partial = good.clone();
            partial["projects"][index]["sparse_paths"] = incomplete;
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut widened = good.clone();
        widened["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tests"));
        assert!(validate_source_extension(&base, &widened).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Historical fixtures remove only this later, exact flags extension.
    // Production keeps the original declarations and every referenced .aconfig.
    fn remove_later_flags_cones(value: &mut Value) {
        remove_later_eyedropper_project(value);
        for path in ["packages/services/Telecomm", "system/update_engine"] {
            let project = value["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == "flags").count(), 1);
            paths.retain(|p| p != "flags");
        }
    }

    #[test]
    fn ordinary_pair_flags_require_complete_original_declarations_and_inputs() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r12 = original606_for_history();
        remove_later_flags_cones(&mut actual_failed_r12);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r12).unwrap());
        assert_eq!(failed_raw.len(), 354876);
        assert_eq!(digest(failed_raw.as_bytes()), "34aa4c635fd8700c641641c5dbdf4ded4cd6a94b0a3ad369232fe1f287b691f0");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r12.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r12).is_err());
        for (path, commit, source) in [
            ("packages/services/Telecomm", "2353977dc28ff88d3cdc1ec636fa9c3251d2ff86", "telecom_platform_flags.aconfig"),
            ("system/update_engine", "4591637f51644f5429f9e2fe589ab22b92f61842", "update_engine_flags.aconfig"),
        ] {
            let index = good["projects"].as_array().unwrap().iter()
                .position(|p| p["path"] == path).unwrap();
            assert_eq!(good["projects"][index]["commit"], commit);
            for replacement in [None, Some("flags/Android.bp".to_owned()),
                                Some(format!("flags/{source}"))] {
                let mut partial = good.clone();
                let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
                paths.retain(|p| p != "flags");
                if let Some(value) = replacement { paths.push(json!(value)); }
                assert!(validate_source_extension(&base, &partial).is_err());
            }
            let mut wrong_commit = good.clone();
            wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &wrong_commit).is_err());
            let mut widened = good.clone();
            widened["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("unreviewed"));
            assert!(validate_source_extension(&base, &widened).is_err());
        }
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // This removes only the later complete host-tool cones from historical
    // failed-lock fixtures. Production always requires their full originals.
    fn remove_later_platform_tools_cones(value: &mut Value) {
        remove_later_flags_cones(value);
        for (path, selection) in [
            ("development", "tools/etc1tool"),
            ("dalvik", "tools/hprof-conv"),
        ] {
            let project = value["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == selection).count(), 1);
            paths.retain(|p| p != selection);
        }
    }

    #[test]
    fn ordinary_pair_platform_tools_require_complete_original_host_implementations() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r11 = original606_for_history();
        remove_later_platform_tools_cones(&mut actual_failed_r11);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r11).unwrap());
        assert_eq!(failed_raw.len(), 354822);
        assert_eq!(digest(failed_raw.as_bytes()), "9375d2850e830e6213556ab87693fb54df456096f5c455c87afb76d681436ed2");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r11.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r11).is_err());
        for (path, commit, selection, source) in [
            ("development", "4dafd114fab3c3d9543a5aff0ad097f479915176", "tools/etc1tool", "etc1tool.cpp"),
            ("dalvik", "5013071e756f89aa2cea97b437af12aacb8d4485", "tools/hprof-conv", "HprofConv.c"),
        ] {
            let index = good["projects"].as_array().unwrap().iter()
                .position(|p| p["path"] == path).unwrap();
            assert_eq!(good["projects"][index]["commit"], commit);
            for replacement in [None, Some(format!("{selection}/Android.bp")),
                                Some(format!("{selection}/{source}"))] {
                let mut partial = good.clone();
                let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
                paths.retain(|p| p != selection);
                if let Some(value) = replacement { paths.push(json!(value)); }
                assert!(validate_source_extension(&base, &partial).is_err());
            }
            let mut wrong_commit = good.clone();
            wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &wrong_commit).is_err());
            let mut widened = good.clone();
            widened["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tools"));
            assert!(validate_source_extension(&base, &widened).is_err());
        }
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Only historical fixtures remove these later original inputs. Production
    // validation always requires both the complete Java tool and Python library.
    fn remove_later_dexdeps_pyee_inputs(value: &mut Value) {
        remove_later_platform_tools_cones(value);
        let projects = value["projects"].as_array_mut().unwrap();
        assert_eq!(projects.iter().filter(|p| p["path"] == "external/python/pyee").count(), 1);
        projects.retain(|p| p["path"] != "external/python/pyee");
        let dalvik = projects.iter_mut().find(|p| p["path"] == "dalvik").unwrap();
        let paths = dalvik["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "tools/dexdeps").count(), 1);
        paths.retain(|p| p != "tools/dexdeps");
    }

    #[test]
    fn ordinary_pair_dexdeps_requires_original_java_wrapper_and_manifest_cone() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "dalvik").unwrap();
        assert_eq!(good["projects"][index]["commit"], "5013071e756f89aa2cea97b437af12aacb8d4485");
        let mut actual_failed_r10 = original606_for_history();
        remove_later_dexdeps_pyee_inputs(&mut actual_failed_r10);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r10).unwrap());
        assert_eq!(failed_raw.len(), 354443);
        assert_eq!(digest(failed_raw.as_bytes()), "86a215da1fed2945feccebe7878b95fe507114de6e3b8ee0fa673e830d9a7aba");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r10.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r10).is_err());
        for replacement in [None, Some("tools/dexdeps/Android.bp"), Some("tools/dexdeps/src"),
                            Some("tools/dexdeps/etc")] {
            let mut partial = good.clone();
            let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "tools/dexdeps");
            if let Some(path) = replacement { paths.push(json!(path)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut widened = good;
        widened["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tools"));
        assert!(validate_source_extension(&base, &widened).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    #[test]
    fn ordinary_pair_pyee_requires_exact_superproject_provider_and_existing_typing_dependency() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "external/python/pyee").unwrap();
        assert_eq!(good["projects"][index]["commit"], "d67e4b09ff002069a025bfb232836eecab6dab52");
        assert_eq!(good["projects"][index]["name"], "platform/external/python/pyee");
        assert_eq!(good["projects"][index]["sparse_paths"], json!(["Android.bp", "LICENSE", "pyee"]));
        let typing = good["projects"].as_array().unwrap().iter()
            .find(|p| p["path"] == "external/python/typing_extensions").unwrap();
        assert_eq!(typing["commit"], "8430d542d65e5607ece1e810e247b982384b32f9");
        let mut missing = good.clone();
        missing["projects"].as_array_mut().unwrap().remove(index);
        assert!(validate_source_extension(&base, &missing).is_err());
        for selection in [json!(["Android.bp"]), json!(["pyee"]),
                          json!(["Android.bp", "pyee"]), json!(["LICENSE", "pyee/asyncio.py"])] {
            let mut partial = good.clone();
            partial["projects"][index]["sparse_paths"] = selection;
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut widened = good;
        widened["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tests"));
        assert!(validate_source_extension(&base, &widened).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Reconstruct the actual r8 failed lock before adding the complete original
    // bcc_compat implementation. This helper changes test data only.
    fn remove_later_bcc_cone(value: &mut Value) {
        remove_later_dexdeps_pyee_inputs(value);
        let project = value["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "frameworks/compile/libbcc").unwrap();
        let paths = project["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(paths.iter().filter(|p| *p == "tools/bcc_compat").count(), 1);
        paths.retain(|p| p != "tools/bcc_compat");
    }

    #[test]
    fn ordinary_pair_renderscript_bcc_requires_complete_original_input() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "frameworks/compile/libbcc").unwrap();
        assert_eq!(good["projects"][index]["commit"], "943016fade3dbbb725c363d0dc60a6e962bd88e5");
        let mut actual_failed_r8 = original606_for_history();
        remove_later_bcc_cone(&mut actual_failed_r8);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r8).unwrap());
        assert_eq!(failed_raw.len(), 354415);
        assert_eq!(digest(failed_raw.as_bytes()), "02fd330466357ecf744d85f27d23b03fabde46f31fae3ef69a5f6634e66e8837");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r8.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r8).is_err());
        // Neither a Blueprint alone nor Main.cpp alone supplies the complete
        // original provider and implementation selected by the real SDK host.
        for suffix in ["Android.bp", "Main.cpp"] {
            let mut partial = good.clone();
            let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "tools/bcc_compat");
            paths.push(json!(format!("tools/bcc_compat/{suffix}")));
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut widened = good;
        widened["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tools"));
        assert!(validate_source_extension(&base, &widened).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    // Keep each earlier failed lock's bytes exact after the r7 finite Tradefed
    // input extension. This helper is only historical test reconstruction.
    fn remove_later_tradefed_cones(value: &mut Value) {
        remove_later_bcc_cone(value);
        for (path, cone) in [
            ("cts", "tools/cts-tradefed"),
            ("cts", "tools/cts-v-host"),
            ("system/chre", "java/test/chdts"),
            ("test/vts", "tools/vts-core-tradefed"),
            ("external/deqp", "android/cts"),
        ] {
            let project = value["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            assert_eq!(paths.iter().filter(|p| *p == cone).count(), 1);
            paths.retain(|p| p != cone);
        }
    }

    #[test]
    fn ordinary_pair_tradefed_providers_require_original_recursive_cones() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut actual_failed_r7 = original606_for_history();
        remove_later_tradefed_cones(&mut actual_failed_r7);
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r7).unwrap());
        assert_eq!(digest(failed_raw.as_bytes()), "fb05fce28e2541cc1c791350ede62d36579ac459922b6f394680930cba9f6d9d");
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(actual_failed_r7.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r7).is_err());
        for (path, commit, cone) in [
            ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-tradefed"),
            ("cts", "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd", "tools/cts-v-host"),
            ("system/chre", "17b4a35a8c2b9f27e7f1b382b7d714aced928ce4", "java/test/chdts"),
            ("test/vts", "886725543e4078f87fc87aabb90b1871c7536b03", "tools/vts-core-tradefed"),
            ("external/deqp", "eae519aaa6980b2a34ec07141bb19de3f6ddf69e", "android/cts"),
        ] {
            let index = good["projects"].as_array().unwrap().iter()
                .position(|p| p["path"] == path).unwrap();
            assert_eq!(good["projects"][index]["commit"], commit);
            assert_eq!(good["projects"][index]["sparse_paths"].as_array().unwrap()
                .iter().filter(|p| *p == cone).count(), 1);
            // A lone BP still omits Java implementations, wrappers, resources,
            // suite tests and the retained Deqp runner dependency.
            for suffix in ["Android.bp", "src"] {
                let mut partial = good.clone();
                let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
                paths.retain(|p| p != cone);
                paths.push(json!(format!("{cone}/{suffix}")));
                assert!(validate_source_extension(&base, &partial).is_err());
            }
            let mut wrong_commit = good.clone();
            wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &wrong_commit).is_err());
        }
        let mut widened = good;
        let cts = widened["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "cts").unwrap();
        cts["sparse_paths"].as_array_mut().unwrap().push(json!("tools"));
        assert!(validate_source_extension(&base, &widened).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    #[test]
    fn ordinary_pair_signature_common_requires_complete_original_input() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "cts").unwrap();
        assert_eq!(good["projects"][index]["commit"], "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd");
        assert_eq!(good["projects"][index]["sparse_paths"].as_array().unwrap().iter()
            .filter(|p| p.as_str() == Some("tests/signature/lib/common")).count(), 1);
        let mut actual_failed_r6 = original606_for_history();
        remove_later_tradefed_cones(&mut actual_failed_r6);
        actual_failed_r6["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .retain(|p| p != "tests/signature/lib/common");
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r6).unwrap());
        assert_eq!(digest(failed_raw.as_bytes()), "09a020b99c5f9f1876c69450d01ac99907cd6dda97cb4f69601f70151ea43d2b");
        let generic: droidloom_source::SparseSourceLock = serde_json::from_value(actual_failed_r6.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r6).is_err());
        for partial in ["tests/signature/lib/common/Android.bp", "tests/signature/lib/common/src"] {
            let mut candidate = good.clone();
            let paths = candidate["projects"][index]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "tests/signature/lib/common");
            paths.push(json!(partial));
            assert!(validate_source_extension(&base, &candidate).is_err());
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut wider = good;
        wider["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tests/signature/lib"));
        assert!(validate_source_extension(&base, &wider).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    #[test]
    fn ordinary_pair_rkpd_apex_requires_complete_original_input() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let index = good["projects"].as_array().unwrap().iter()
            .position(|p| p["path"] == "packages/modules/RemoteKeyProvisioning").unwrap();
        assert_eq!(good["projects"][index]["commit"], "d88e2305f9186661fe75ee2f00c8b250a76fdabe");
        assert_eq!(good["projects"][index]["sparse_paths"].as_array().unwrap().iter()
            .filter(|p| p.as_str() == Some("apex")).count(), 1);
        let mut actual_failed_r5 = original606_for_history();
        remove_later_tradefed_cones(&mut actual_failed_r5);
        // Reconstruct historical bytes before the later complete signature provider selection.
        let cts = actual_failed_r5["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "cts").unwrap();
        let cts_paths = cts["sparse_paths"].as_array_mut().unwrap();
        assert_eq!(cts_paths.iter().filter(|p| p.as_str() == Some("tests/signature/lib/common")).count(), 1);
        cts_paths.retain(|p| p != "tests/signature/lib/common");
        actual_failed_r5["projects"][index]["sparse_paths"].as_array_mut().unwrap()
            .retain(|p| p != "apex");
        let failed_raw = format!("{}\n", serde_json::to_string_pretty(&actual_failed_r5).unwrap());
        assert_eq!(digest(failed_raw.as_bytes()), "600dc00660af69b4b8eeb497fac8f2a83f0d8b24ad3d02c2774a4df96f5ec8cf");
        let generic: droidloom_source::SparseSourceLock = serde_json::from_value(actual_failed_r5.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok());
        assert!(validate_source_extension(&base, &actual_failed_r5).is_err());
        for replacement in ["apex/Android.bp", "apex/manifest.json"] {
            let mut partial = good.clone();
            let paths = partial["projects"][index]["sparse_paths"].as_array_mut().unwrap();
            paths.retain(|p| p != "apex");
            paths.push(json!(replacement));
            assert!(validate_source_extension(&base, &partial).is_err(),
                "the complete pinned APEX input must not collapse to a Blueprint or manifest: {replacement}");
        }
        let mut wrong_commit = good.clone();
        wrong_commit["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_commit).is_err());
        let mut wider = good;
        wider["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("app/tests"));
        assert!(validate_source_extension(&base, &wider).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }


    #[test]
    fn ordinary_pair_boot_apex_providers_require_full_original_production_cones() {
        let base: Value = serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        let mut original84e = original606_for_history();
        remove_later_five_apex_inputs(&mut original84e);
        let old_bytes = format!("{}\n", serde_json::to_string_pretty(&original84e).unwrap());
        assert_eq!(old_bytes.len(), 356019);
        assert_eq!(digest(old_bytes.as_bytes()), "d88549bc89076017baffcc28e39695431993cc12516238278e015f23325d9596");
        assert!(validate_source_extension(&base, &original84e).is_err());
        assert_eq!(droidloom_source::build_plan(&serde_json::from_value(original84e).unwrap()).unwrap().projects.len(), 604);
        for replacement in [None, Some("apex/Android.bp"), Some("apex/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/Nfc").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "apex");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("libnfc-nci/conf/Android.bp"), Some("libnfc-nci/conf/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/Nfc").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "libnfc-nci/conf");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("apex/Android.bp"), Some("apex/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/NpuManager").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "apex");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("service/Android.bp"), Some("service/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/NpuManager").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "service");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("apex/Android.bp"), Some("apex/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/Profiling").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "apex");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("service/Android.bp"), Some("service/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/Profiling").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "service");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("apex/Android.bp"), Some("apex/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/UprobeStats").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "apex");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("bpfloader/Android.bp"), Some("bpfloader/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/UprobeStats").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "bpfloader");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("bpf_progs/Android.bp"), Some("bpf_progs/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/UprobeStats").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "bpf_progs");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("apex/Android.bp"), Some("apex/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/WebApp").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "apex");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("service/Android.bp"), Some("service/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/WebApp").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "service");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("template/Android.bp"), Some("template/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "packages/modules/WebApp").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "template");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        for replacement in [None, Some("rust/Android.bp"), Some("rust/manifest.json")] {
            let mut partial = good.clone();
            let p = partial["projects"].as_array_mut().unwrap().iter_mut().find(|p| p["path"] == "system/memory/libdmabufheap").unwrap();
            p["sparse_paths"].as_array_mut().unwrap().retain(|v| v != "rust");
            if let Some(value) = replacement { p["sparse_paths"].as_array_mut().unwrap().push(json!(value)); }
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    #[test]
    fn ordinary_pair_boot_apex_blueprints_are_exact_upstream_inputs() {
        {
            let raw = include_bytes!("../../../android/native-generation-pair/apex-provider-fixtures/Nfc.Android.bp");
            assert_eq!(raw.len(), 5755);
            assert_eq!(digest(raw), "d4985ca345cac178a2e16d461172e7702c607c0855a14f4f5b8105a1f4a3f1b3");
            let text = std::str::from_utf8(raw).unwrap();
            assert!(text.contains("name: \"com.android.nfcservices\""));
        }
        {
            let raw = include_bytes!("../../../android/native-generation-pair/apex-provider-fixtures/NpuManager.Android.bp");
            assert_eq!(raw.len(), 3337);
            assert_eq!(digest(raw), "ed4c5087bf1d8f23b6a704dd593c187f57cb27187c2eb8e4daa3964d0dd6e5f3");
            let text = std::str::from_utf8(raw).unwrap();
            assert!(text.contains("name: \"com.android.npumanager\""));
        }
        {
            let raw = include_bytes!("../../../android/native-generation-pair/apex-provider-fixtures/Profiling.Android.bp");
            assert_eq!(raw.len(), 3308);
            assert_eq!(digest(raw), "9dc6ff30f147abdb4e5fb885aeddd7410cf22ede9405dc92a5a1694cb8ec6182");
            let text = std::str::from_utf8(raw).unwrap();
            assert!(text.contains("name: \"com.android.profiling\""));
        }
        {
            let raw = include_bytes!("../../../android/native-generation-pair/apex-provider-fixtures/UprobeStats.Android.bp");
            assert_eq!(raw.len(), 3788);
            assert_eq!(digest(raw), "8c23fdc0dc97844910f24c07e0abfd6f899bbcdf6f8fc921cd6bb60708270adb");
            let text = std::str::from_utf8(raw).unwrap();
            assert!(text.contains("name: \"com.android.uprobestats\""));
        }
        {
            let raw = include_bytes!("../../../android/native-generation-pair/apex-provider-fixtures/WebApp.Android.bp");
            assert_eq!(raw.len(), 3590);
            assert_eq!(digest(raw), "80c5e346b4a1050fdf17339b7a3d840b26f0411fd0ef1712a58e36627c840856");
            let text = std::str::from_utf8(raw).unwrap();
            assert!(text.contains("name: \"com.android.webapp\""));
        }
    }

    #[test]
    fn ordinary_pair_browser_helper_requires_complete_original_library() {
        let base: Value = serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        assert_eq!(good["projects"].as_array().unwrap().len(), 607);
        let mut previous = good.clone();
        previous["projects"].as_array_mut().unwrap().retain(|row| row["path"] != "external/android-browser-helper");
        assert_eq!(previous, original606_for_history());
        assert!(validate_source_extension(&base, &previous).is_err());
        let original = good["projects"].as_array().unwrap().iter().find(|row| row["path"] == "external/android-browser-helper").unwrap();
        assert_eq!(original["commit"], "49d155f26586a540266fd854c868a067f6db9204");
        assert_eq!(original["sparse_paths"], json!(["androidbrowserhelper/src/main"]));
        for selection in [json!([]), json!(["Android.bp"]), json!(["androidbrowserhelper/src/main/java"]), json!(["androidbrowserhelper/src/main/res"]), json!(["androidbrowserhelper/src/main/AndroidManifest.xml"])] {
            let mut partial = good.clone();
            let row = partial["projects"].as_array_mut().unwrap().iter_mut().find(|row| row["path"] == "external/android-browser-helper").unwrap();
            row["sparse_paths"] = selection;
            assert!(validate_source_extension(&base, &partial).is_err());
        }
        let mut changed = good.clone();
        changed["projects"].as_array_mut().unwrap().iter_mut().find(|row| row["path"] == "external/android-browser-helper").unwrap()["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &changed).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }

    #[test]
    fn ordinary_pair_browser_helper_blueprint_is_exact_original_input() {
        let raw = include_bytes!("../../../android/native-generation-pair/browser-helper-fixtures/BrowserHelper.Android.bp");
        assert_eq!(raw.len(), 1688);
        assert_eq!(digest(raw), "6aa0640a9704e1d9b0be9f8173780d67d8cb998cd06116231a30957ed8a16358");
        let text = std::str::from_utf8(raw).unwrap();
        for input in ["name: \"android-browser-helper\"", "androidbrowserhelper/src/main/java/**/*.java", "androidbrowserhelper/src/main/res", "androidbrowserhelper/src/main/AndroidManifest.xml", "BuildConfig.java"] {
            assert!(text.contains(input));
        }
        let origin: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/browser-helper-fixtures/origin.json")).unwrap();
        assert_eq!(origin["superproject"], "28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        assert_eq!(origin["project"]["commit"], "49d155f26586a540266fd854c868a067f6db9204");
        assert_eq!(origin["blueprint"]["git_blob"], "961ace166662ff1d027100b815658418084f6671");
        assert_eq!(origin["full_build_qualified"], false);
    }

    #[test]
    fn ordinary_pair_source_extension_rejects_revision_policy_and_path_drift() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base, &base).is_err());
        for path in ["prebuilts/misc", "prebuilts/sdk", "frameworks/hardware/interfaces"] {
            let mut bad = good.clone();
            let project = bad["projects"].as_array_mut().unwrap().iter_mut()
                .find(|project| project["path"] == path).unwrap();
            project["sparse_paths"].as_array_mut().unwrap().pop();
            assert!(validate_source_extension(&base, &bad).is_err());
        }
        let mut bad = good.clone();
        bad["projects"][0]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone();
        bad["policy"]["allow_unrestricted_repo_sync"] = json!(true);
        assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone();
        bad["status"] = json!("build_proven");
        assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone();
        bad["projects"].as_array_mut().unwrap().pop();
        assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good;
        bad["projects"][0]["sparse_paths"] = json!(["unrelated"]);
        assert!(validate_source_extension(&base, &bad).is_err());
    }
    #[test]
    fn ordinary_pair_provider_closure_rejects_unlisted_projects_and_prior_plan() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        let mut unlisted = good.clone();
        let mut extra = unlisted["projects"][0].clone();
        extra["path"] = json!("tools/unlisted_pair_source");
        extra["name"] = json!("platform/tools/unlisted_pair_source");
        let last = unlisted["projects"].as_array().unwrap().len() - 1;
        unlisted["projects"][last] = extra;
        let generic: droidloom_source::SparseSourceLock =
            serde_json::from_value(unlisted.clone()).unwrap();
        assert!(droidloom_source::build_plan(&generic).is_ok(),
            "this negative control must remain below the generic materializer bound");
        assert!(validate_source_extension(&base, &unlisted).is_err(),
            "an unlisted project never belongs to the exact ordinary pair");

        let mut prior = good.clone();
        prior["projects"].as_array_mut().unwrap().truncate(228);
        assert!(validate_source_extension(&base, &prior).is_err());

        for path in ["packages/modules/Nfc", "packages/modules/Permission",
                     "packages/modules/NeuralNetworks", "packages/modules/Bluetooth",
                     "packages/modules/Connectivity", "external/cronet", "system/bpf"] {
            let mut incomplete = good.clone();
            let project = incomplete["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            project["sparse_paths"].as_array_mut().unwrap().pop();
            assert!(validate_source_extension(&base, &incomplete).is_err(),
                "every original provider subtree is part of the authenticated lock: {path}");
        }
        for path in ["external/brotli", "external/pigweed", "packages/modules/CrashRecovery"] {
            let mut drift = good.clone();
            let project = drift["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            project["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &drift).is_err());
            let mut widened = good.clone();
            let project = widened["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            project["sparse_paths"].as_array_mut().unwrap().push(json!("unrequested"));
            assert!(validate_source_extension(&base, &widened).is_err());
        }
    }


    #[test]
    fn ordinary_pair_generator_provider_closure_rejects_partial_and_unrelated_inputs() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        validate_source_extension(&base, &good).unwrap();
        for (path, subtree) in [
            ("external/pigweed", "pw_elf"),
            ("external/pigweed", "pw_protobuf"),
            ("external/pigweed", "pw_protobuf_compiler"),
            ("external/pigweed", "pw_rpc"),
            ("external/pigweed", "pw_sync_baremetal"),
            ("external/nanopb-c", "generator"),
            ("system/vold", "aconfig/flags.aconfig"),
            ("packages/modules/CrashRecovery", "service/api"),
            ("external/libultrahdr", "adobe-hdr-gain-map-license"),
            ("external/vulkan-headers", "LICENSES"),
            ("external/wpa_supplicant_8", "wpa_supplicant/wpa_gui-qt4/icons/LICENSE"),
            ("prebuilts/misc", "darwin-x86/yasm/COPYING"),
            ("prebuilts/misc", "darwin-x86_64/sdl2/include/SDL2/NOTICE"),
            ("prebuilts/misc", "linux-x86/yasm/COPYING"),
            ("prebuilts/sdk", "36/public/api/framework-ondeviceintelligence.txt"),
            ("prebuilts/sdk", "36/public/api/framework-ondeviceintelligence-removed.txt"),
            ("prebuilts/sdk", "36/system/api/framework-ondeviceintelligence.txt"),
            ("prebuilts/sdk", "36/system/api/framework-ondeviceintelligence-removed.txt"),
            ("prebuilts/sdk", "36/module-lib/api/framework-ondeviceintelligence.txt"),
            ("prebuilts/sdk", "36/module-lib/api/framework-ondeviceintelligence-removed.txt"),
            ("external/protobuf", "python/google"),
            ("packages/modules/common", "proto"),
            ("packages/modules/common", "tools/Android.bp"),
            ("packages/modules/common", "tools/gen_sdkinfo.py"),
            ("packages/modules/common", "tools/conv_classpaths_proto.py"),
            ("packages/modules/common", "tools/check_derive_classpath.py"),
        ] {
            let mut missing = good.clone();
            let project = missing["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            let paths = project["sparse_paths"].as_array_mut().unwrap();
            let old_len = paths.len();
            paths.retain(|p| p != subtree);
            assert_eq!(paths.len() + 1, old_len);
            assert!(validate_source_extension(&base, &missing).is_err(), "missing {path}/{subtree}");
        }
        for (path, extra) in [
            ("external/pigweed", "third_party"),
            ("external/nanopb-c", "tests"),
            ("system/vold", "aconfig"),
            ("packages/modules/CrashRecovery", "service"),
            ("external/libultrahdr", "examples"),
            ("external/vulkan-headers", "tests"),
            ("external/wpa_supplicant_8", "wpa_supplicant/wpa_gui-qt4"),
            ("prebuilts/misc", "darwin-x86"),
            ("prebuilts/misc", "darwin-x86_64"),
            ("prebuilts/misc", "linux-x86"),
            ("prebuilts/sdk", "36"),
            ("prebuilts/sdk", "36/test/api"),
            ("packages/modules/common", "tools/mainline_beta"),
        ] {
            let mut wider = good.clone();
            let project = wider["projects"].as_array_mut().unwrap().iter_mut()
                .find(|p| p["path"] == path).unwrap();
            project["sparse_paths"].as_array_mut().unwrap().push(json!(extra));
            assert!(validate_source_extension(&base, &wider).is_err());
        }
        let mut wrong_revision = good.clone();
        let project = wrong_revision["projects"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["path"] == "external/nanopb-c").unwrap();
        project["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &wrong_revision).is_err());
        let mut prior = good;
        prior["projects"].as_array_mut().unwrap().retain(|p| p["path"] != "external/nanopb-c");
        assert!(validate_source_extension(&base, &prior).is_err());
    }

    #[test]
    fn ordinary_pair_display_extension_rejects_previous_and_wider_subtrees() {
        let base: Value = serde_json::from_slice(include_bytes!(
            "../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap();
        let good: Value = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        let index = good["projects"].as_array().unwrap().iter()
            .position(|project| project["path"] == "frameworks/hardware/interfaces").unwrap();
        let paths = good["projects"][index]["sparse_paths"].as_array().unwrap();
        assert_eq!(paths, &vec![json!("devicestate/aidl"), json!("location/altitude/aidl"), json!("sensorservice/aidl"), json!("stats/aidl"), json!("vibrator/aidl"), json!("automotive/display/1.0"), json!("automotive/display/aidl/Android.bp"), json!("automotive/display/aidl/aidl_api"), json!("automotive/display/aidl/android"), json!("cameraservice/common"), json!("cameraservice/device"), json!("cameraservice/service"), json!("sensorservice/1.0/Android.bp"), json!("sensorservice/1.0/IDirectReportChannel.hal"), json!("sensorservice/1.0/IEventQueue.hal"), json!("sensorservice/1.0/IEventQueueCallback.hal"), json!("sensorservice/1.0/ISensorManager.hal"), json!("sensorservice/1.0/types.hal")]);
        let display_index = paths.iter().position(|path| path == "automotive/display/1.0").unwrap();
        for replacement in ["automotive", "automotive/display", "automotive/display/2.0"] {
            let mut wider = good.clone();
            wider["projects"][index]["sparse_paths"][display_index] = json!(replacement);
            assert!(validate_source_extension(&base, &wider).is_err());
        }
        let mut previous = good;
        previous["projects"][index]["sparse_paths"].as_array_mut().unwrap().remove(display_index);
        assert!(validate_source_extension(&base, &previous).is_err());
    }
    #[test]
    fn ordinary_pair_source_workspace_rejects_previous_plan_and_alias() {
        let tmp = tempfile::tempdir().unwrap();
        let source = tmp.path().join("aosp-source");
        let lock: droidloom_source::SparseSourceLock = serde_json::from_slice(include_bytes!(
            "../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        let path = tmp.path().join("lock.json");
        assert!(verify_source_workspace(&path, &lock, &source).is_ok());
        fs::create_dir(&source).unwrap();
        let previous = droidloom_source::MaterializedManifest {
            schema_version: 1, source_lock_sha256: BASE_SOURCE_LOCK_SHA.to_owned(),
            plan: droidloom_source::build_plan(&lock).unwrap(),
        };
        fs::write(source.join(".droidloom-source-manifest.json"), serde_json::to_vec_pretty(&previous).unwrap()).unwrap();
        assert!(verify_source_workspace(&path, &lock, &source).is_err());
        let alias = tmp.path().join("alias");
        std::os::unix::fs::symlink(&source, &alias).unwrap();
        assert!(verify_source_workspace(&path, &lock, &alias).is_err());
    }
    #[test]
    fn ordinary_pair_accepts_only_complete_strict_scope() {
        assert!(validate_scope(TARGETS,true,Some(Flavor::EnabledBuildOnly),false,false).is_ok());
        for targets in [&[][..], &["libberberis_arm64"][..], &["com.android.art"][..],
                        &["libberberis_arm64","com.android.art","services"][..]] {
            assert!(validate_scope(targets,true,Some(Flavor::EnabledBuildOnly),false,false).is_err());
        }
        assert!(validate_scope(TARGETS,false,Some(Flavor::EnabledBuildOnly),false,false).is_err());
        assert!(validate_scope(TARGETS,true,Some(Flavor::Disabled),false,false).is_err());
        assert!(validate_scope(TARGETS,true,None,false,false).is_err());
        assert!(validate_scope(TARGETS,true,Some(Flavor::EnabledBuildOnly),true,false).is_err());
        assert!(validate_scope(TARGETS,true,Some(Flavor::EnabledBuildOnly),false,true).is_err());
    }
    #[test]
    fn ordinary_pair_projection_is_exact_and_only_x86_64_arm64() {
        let before=include_str!("../../../android/native-generation-pair/engine.Android.bp");
        let after=enabled_blueprint(before).unwrap();
        assert_eq!(after.matches(ENABLED).count(),1);
        assert_eq!(after.replace(", \"-DBERBERIS_PROCMAPS_RAW_METADATA_OWNER=1\"",""),before);
        let unchanged=ORIGINAL_DEFAULTS.split("        riscv64:").nth(1).unwrap();
        assert!(after.contains(unchanged));
        assert!(enabled_blueprint(&after).is_err());
        assert!(enabled_blueprint(&(before.to_owned()+"\n")).is_err());
    }
    #[test]
    fn ordinary_pair_rejects_wrong_or_partial_engine_snapshot() {
        let raw=include_bytes!("../../../android/native-generation-pair/engine-source-files.json");
        assert_eq!(raw.len(),ENGINE_FILES_BYTES);assert_eq!(digest(raw),ENGINE_FILES_SHA);
        let files:BTreeMap<String,String>=serde_json::from_slice(raw).unwrap();
        let good=json!({"commit":ENGINE_HEAD,"working_tree":true,"files":files});
        assert!(check_snapshot(&good,&files).is_ok());
        let mut bad=good.clone();bad["commit"]=json!("0000000000000000000000000000000000000000");
        assert!(check_snapshot(&bad,&files).is_err());
        let mut bad=good.clone();bad["working_tree"]=json!(false);assert!(check_snapshot(&bad,&files).is_err());
        let mut bad=good;bad["files"].as_object_mut().unwrap().remove("Android.bp");
        assert!(check_snapshot(&bad,&files).is_err());
    }
    #[test]
    fn ordinary_pair_records_are_create_only() {
        let tmp=tempfile::tempdir().unwrap();let path=tmp.path().join("record.json");
        record(&path,json!({"runtime_qualified":false})).unwrap();
        let first=fs::read(&path).unwrap();
        assert!(record(&path,json!({"runtime_qualified":true})).is_err());
        assert_eq!(fs::read(path).unwrap(),first);
    }
    #[test]
    fn ordinary_pair_effective_engine_rejects_untracked_or_unrelated_edits() {
        let blueprint=include_str!("../../../android/native-generation-pair/engine.Android.bp");
        let mut before=BTreeMap::from([("Android.bp".into(),ENGINE_BP_SHA.into()),
            ("kernel_api/proc_maps_generation.cc".into(),"original-generation".into()),
            ("native_activity/Android.bp".into(),"original-link".into())]);
        let mut after=before.clone();
        after.insert("Android.bp".into(),digest(enabled_blueprint(blueprint).unwrap().replace(
            "\"libandroid\"","\"droidloom_native_bridge_host_libandroid\"").as_bytes()));
        after.insert("native_activity/Android.bp".into(),"projected-link".into());
        let projection=json!({"files":{
            (format!("{ENGINE}/Android.bp")):after["Android.bp"],
            (format!("{ENGINE}/native_activity/Android.bp")):"projected-link"}});
        assert!(validate_effective_engine(&before,&after,&projection,blueprint).is_ok());
        assert!(validate_effective_engine(&before,&after,&json!({"files":{}}),blueprint).is_err());
        after.insert("kernel_api/proc_maps_generation.cc".into(),"unauthorized-code".into());
        assert!(validate_effective_engine(&before,&after,&projection,blueprint).is_err());
        before.remove("kernel_api/proc_maps_generation.cc");
        assert!(validate_effective_engine(&before,&after,&projection,blueprint).is_err());
    }
}

#[cfg(test)]
mod source642_tests {
    use super::*;
    // Keep the actual 642 tests bound to their immutable predecessor.
    use super::validate_source_extension642 as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 368342;
    const SOURCE_LOCK_SHA: &str = "f8663e08af2e28f2a5bd1b9b9c0d183c5b9fa2a6521d2c97fbc2ed1d3e62165a";

    fn base() -> Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current() -> Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/original642-source-lock.json")).unwrap() }
    #[test]
    fn generic642_requires_exact_monotone_original_provider_selection() {
        let raw = include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/original642-source-lock.json");
        assert_eq!(raw.len(), SOURCE_LOCK_BYTES); assert_eq!(digest(raw), SOURCE_LOCK_SHA);
        let good = current(); validate_source_extension(&base(), &good).unwrap();
        let parsed: droidloom_source::SparseSourceLock = serde_json::from_slice(raw).unwrap();
        let plan = droidloom_source::build_plan(&parsed).unwrap();
        assert_eq!((plan.projects.len(), plan.links.len(), plan.unrestricted_repo_sync), (642, 8, false));
        let old: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/original607-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(), &old).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }
    #[test]
    fn generic642_rejects_each_missing_provider_cone_and_revision_or_scope_drift() {
        let good = current(); let base = base();
        for index in 607..642 {
            let mut changed = good.clone(); changed["projects"].as_array_mut().unwrap().remove(index);
            assert!(validate_source_extension(&base, &changed).is_err());
            let mut changed = good.clone(); changed["projects"][index]["commit"] = json!("0000000000000000000000000000000000000000");
            assert!(validate_source_extension(&base, &changed).is_err());
            let mut changed = good.clone(); changed["projects"][index]["sparse_paths"] = json!(["Android.bp"]);
            assert!(validate_source_extension(&base, &changed).is_err());
        }
        let delta: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/selection-delta.json")).unwrap();
        for (path, change) in delta["added_sparse_cones"].as_object().unwrap() {
            for cone in change["added"].as_array().unwrap() {
                let mut changed = good.clone();
                let project = changed["projects"].as_array_mut().unwrap().iter_mut().find(|row| row["path"] == path.as_str()).unwrap();
                project["sparse_paths"].as_array_mut().unwrap().retain(|row| row != cone);
                assert!(validate_source_extension(&base, &changed).is_err());
            }
        }
        for key in ["status", "policy", "superproject", "links"] {
            let mut changed = good.clone(); changed[key] = json!(null);
            assert!(validate_source_extension(&base, &changed).is_err());
        }
        let mut changed = good.clone(); changed["projects"].as_array_mut().unwrap().swap(0,1);
        assert!(validate_source_extension(&base, &changed).is_err());
    }
    #[test]
    fn generic642_all_new_primary_blueprints_are_exact_original_fixtures() {
        let raw = include_bytes!("../../../android/native-generation-pair/generic-system-fixtures/origins.json");
        assert_eq!(raw.len(), 52635); assert_eq!(digest(raw), "3f13c8a56beec8cc71d0b07d090f7bedcc29cf6b6affb8302634b0174af8fd5c");
        let origin: Value = serde_json::from_slice(raw).unwrap();
        assert_eq!(origin["superproject"], "28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        assert_eq!(origin["source_and_full_qualified"], false);
        assert_eq!(origin["original_soong_missing_modules"].as_array().unwrap().len(), 59);
        let rows = origin["primary_blueprints"].as_array().unwrap(); assert_eq!(rows.len(), 131);
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        for row in rows {
            let relative = row["fixture"].as_str().unwrap();
            assert!(relative.starts_with("android/native-generation-pair/generic-system-fixtures/original-blueprints/") && !relative.split('/').any(|part| part == ".."));
            fixed_file(&repo.join(relative), row["bytes"].as_u64().unwrap() as usize, row["sha256"].as_str().unwrap()).unwrap();
            assert_eq!(row["git_blob"].as_str().unwrap().len(), 40);
        }
    }
}

#[cfg(test)]
mod source643_tests {
    use super::*;
    // Historical actual643 tests retain their original lock and validator.
    use super::validate_source_extension643_sdk as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 368740;
    const SOURCE_LOCK_SHA: &str = "e9326b795fd142f8b07a8536a3d96e7f3a957d7ec965030753720d609f9d87b4";

    fn base() -> Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current() -> Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original643-source-lock.json")).unwrap() }
    #[test]
    fn sdk643_requires_exact_original_producer_after_complete642() {
        let raw = include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original643-source-lock.json");
        assert_eq!(raw.len(), SOURCE_LOCK_BYTES); assert_eq!(digest(raw), SOURCE_LOCK_SHA);
        validate_source_extension(&base(), &current()).unwrap();
        let parsed: droidloom_source::SparseSourceLock = serde_json::from_slice(raw).unwrap();
        let plan = droidloom_source::build_plan(&parsed).unwrap();
        assert_eq!((plan.projects.len(), plan.links.len(), plan.unrestricted_repo_sync), (643,8,false));
        let old: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/original642-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(), &old).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }
    #[test]
    fn sdk643_rejects_missing_or_drifted_producer_cones_and_predecessor_scope() {
        let good = current(); let base = base();
        let mut bad=good.clone(); bad["projects"].as_array_mut().unwrap().pop();
        assert!(validate_source_extension(&base,&bad).is_err());
        for key in ["name","path","commit","purpose"] {
            let mut bad=good.clone(); bad["projects"][642][key]=json!("changed");
            assert!(validate_source_extension(&base,&bad).is_err());
        }
        for cones in [json!(["Android.bp"]),json!(["prebuilts/gradle"]),json!(["prebuilts/androidtv"]),json!(["prebuilts/gradle","prebuilts/androidtv","samples"])] {
            let mut bad=good.clone();bad["projects"][642]["sparse_paths"]=cones;
            assert!(validate_source_extension(&base,&bad).is_err());
        }
        for key in ["status","policy","superproject","links"] {
            let mut bad=good.clone(); bad[key]=json!(null);
            assert!(validate_source_extension(&base,&bad).is_err());
        }
        let mut bad=good.clone();bad["projects"][0]["commit"]=json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base,&bad).is_err());
        let mut bad=good.clone();bad["projects"].as_array_mut().unwrap().swap(0,1);
        assert!(validate_source_extension(&base,&bad).is_err());
    }
    #[test]
    fn sdk643_original_blueprint_and_complete_sample_cones_fixture_are_pinned() {
        let raw=include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/original-developers-build.Android.bp");
        assert_eq!(raw.len(),21439);
        assert_eq!(digest(raw),"4c2ffa4deb65af220fa81bc1ea474c391f080d2963b8d2e1ccc6517d60152ce9");
        let text=std::str::from_utf8(raw).unwrap();
        assert!(text.contains("name: \"sdk_repo_sample_new_zip\""));
        for name in ["\"sdk_clean\"","\"soong_zip\"","\"Android-Apache-2.0\""] { assert!(text.contains(name)); }
        let srcs=text.split("srcs: [").nth(1).unwrap().split("],").next().unwrap();
        let patterns: Vec<&str>=srcs.lines().map(str::trim).filter(|line|line.starts_with('"')).collect();
        assert_eq!(patterns.len(),111);
        for pattern in patterns { assert!(pattern.starts_with("\"prebuilts/gradle/") || pattern.starts_with("\"prebuilts/androidtv/")); }
        let origin_raw=include_bytes!("../../../android/native-generation-pair/sdk-samples-fixtures/origins.json");
        assert_eq!(origin_raw.len(),1002);assert_eq!(digest(origin_raw),"3b1deacf4f9c966d1b3ab3e65a74dcf639c778bbacd16d977218bdf3044e17db");
        let origin: Value=serde_json::from_slice(origin_raw).unwrap();
        assert_eq!(origin["source_and_full_qualified"],false);
        assert_eq!(origin["runtime_qualified"],false);
        assert_eq!(origin["selected_original_files"],8044);
        assert_eq!(origin["unique_matched_declared_source_files"],6227);
        assert_eq!(origin["project"]["commit"],"31d9b329ddc56636a279c7340e154e0d67d9a6fb");
    }
}

#[cfg(test)]
mod path_tag_provider_tests {
    use super::*;
    use super::validate_source_extension643_path_data as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 369125;
    const SOURCE_LOCK_SHA: &str = "7866f9c66e6b9dc418b0f9998c6d7724402e4a51a3cf51453087a8dad7b84b42";
    fn base()->Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current()->Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original643-path-data-source-lock.json")).unwrap() }
    #[test]
    fn exact_original_path_tag_providers_after_complete_sdk643() {
        let raw=include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original643-path-data-source-lock.json");
        assert_eq!(raw.len(),SOURCE_LOCK_BYTES);assert_eq!(digest(raw),SOURCE_LOCK_SHA);
        validate_source_extension(&base(),&current()).unwrap();
        let parsed:droidloom_source::SparseSourceLock=serde_json::from_slice(raw).unwrap();let plan=droidloom_source::build_plan(&parsed).unwrap();
        assert_eq!((plan.projects.len(),plan.links.len(),plan.unrestricted_repo_sync),(643,8,false));
        assert_eq!(TARGETS,&["libberberis_arm64","com.android.art"]);
        let predecessor:Value=serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original643-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(),&predecessor).is_err());
    }
    #[test]
    fn reject_missing_expanded_reordered_or_unrelated_path_tag_source_scope() {
        let good=current();let base=base();
        for name in ["packages/modules/adb","system/apex","system/timezone"] {
            let index=good["projects"].as_array().unwrap().iter().position(|p|p["path"]==name).unwrap();
            let mut bad=good.clone();bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().pop();assert!(validate_source_extension(&base,&bad).is_err());
            let mut bad=good.clone();bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("unrelated"));assert!(validate_source_extension(&base,&bad).is_err());
            let mut bad=good.clone();bad["projects"][index]["commit"]=json!("0000000000000000000000000000000000000000");assert!(validate_source_extension(&base,&bad).is_err());
        }
        for key in ["status","policy","superproject","links"]{let mut bad=good.clone();bad[key]=json!(null);assert!(validate_source_extension(&base,&bad).is_err());}
        let mut bad=good.clone();bad["projects"].as_array_mut().unwrap().swap(0,1);assert!(validate_source_extension(&base,&bad).is_err());
    }
    #[test]
    fn original_path_tags_producer_bps_and_finite63_content_are_pinned() {
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/packages/modules/adb/test_device_apks/Android.bp"); assert_eq!(b.len(),1084); assert_eq!(digest(b),"15897f373cc300a99d4afecb5c55903eb5afc4aa6e7944cf9153acfcd5d4c91e"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/apex/tests/testdata/apkinapex/com.android.apex.product.test/Android.bp"); assert_eq!(b.len(),1628); assert_eq!(digest(b),"afc83bd434990c16fd09b94e4a15a589a43fb67936c85b2f9d1a14eb9daa3f2a"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/apex/tests/testdata/apkinapex/com.android.apex.system.test/Android.bp"); assert_eq!(b.len(),1616); assert_eq!(digest(b),"8c29a71a1f67d56562f20d1c44bb5b5a15e721a5554ef5adfc6f6ee16fa4ce6e"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/apex/tests/testdata/apkinapex/com.android.apex.system_ext.test/Android.bp"); assert_eq!(b.len(),1664); assert_eq!(digest(b),"97ca4ab787245be5c69d0de881b93109eeedbe894441a869bc7d7f56b4bbacc7"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/apex/tests/testdata/apkinapex/com.android.apex.vendor.test/Android.bp"); assert_eq!(b.len(),1616); assert_eq!(digest(b),"781190bbd730e05a64a3a65af4a0f9b12158ee104f731a5aa121e7b966567d8f"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/apex/tests/testdata/maxsdk/com.android.apex.maxsdk.test/Android.bp"); assert_eq!(b.len(),2160); assert_eq!(digest(b),"642e3b8b7fe7ba13dfb1f50c7f7c8366e057892a3398993c8f94cf4ffc80b0d5"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/timezone/testing/data/test1/apex/Android.bp"); assert_eq!(b.len(),1941); assert_eq!(digest(b),"a0efdcfbfc590aca6247513fe2e163154d9e5345e45154a3dd0f86a772a27199"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-blueprints/system/timezone/testing/data/test1/output_data/Android.bp"); assert_eq!(b.len(),5489); assert_eq!(digest(b),"62fa69d8c8569e019e0b61a0bbe8a93f0425ec7eeedcd8c769fdb4aa9b9ed1f3"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/android/path_properties.go"); assert_eq!(b.len(),13357); assert_eq!(digest(b),"dcc5dd854a47c950af45aaf3dcaa568625941ad35c9827cc274a1a25cf5c9882"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/python/test.go"); assert_eq!(b.len(),10780); assert_eq!(digest(b),"58beaa2a5fd936ced5c99ae089250c0967b0ff48d28f3c26adb9396931ff5ead"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/android_sdk/sdk_repo_host.go"); assert_eq!(b.len(),10795); assert_eq!(digest(b),"da575345850684a38ead830ae9393316a9a3db426c91f482593f3b11abf851cb"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/java/base.go"); assert_eq!(b.len(),140615); assert_eq!(digest(b),"5c5a5c433656e6520579560f9559bf0e47a4a2fa91ca3af0252b993459a1dd7c"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/java/java.go"); assert_eq!(b.len(),158581); assert_eq!(digest(b),"d4996f03e12cd3b9572f86b1eff8c9a8dbb4d3567e3daad87e7068ed48fbfc42"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/blueprint/proptools/tag.go"); assert_eq!(b.len(),2155); assert_eq!(digest(b),"e53682e5ead6051a2b48ec306b2c2f5d8cd2b67802de641f0e3ffd99c2c2a6da"); }
        { let b=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/blueprint/proptools/proptools.go"); assert_eq!(b.len(),4798); assert_eq!(digest(b),"1049d50e193e2d5c2eaf1737cf096e02fd56713df43653291fd06064485b8a43"); }
        let raw=include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/origins.json");assert_eq!(raw.len(),37262);assert_eq!(digest(raw),"5b21d7b687a77d8eded4e1c64053fde67fcce9466b3430f05c2c366986208987");let value:Value=serde_json::from_slice(raw).unwrap();
        assert_eq!(value["selected_new_original_files"],63);assert_eq!(value["new_primary_BP"],8);assert_eq!(value["new_cones"],7);assert_eq!(value["new_files"].as_array().unwrap().len(),63);
        assert_eq!(value["raw_total_bytes"],819688);assert_eq!(value["max_raw_bytes"],409045);assert!(value["new_large_blob_exceptions"].as_array().unwrap().is_empty());
        assert_eq!(value["actual_Soong_qualified"],false);assert_eq!(value["all_other_unresolved_branches_qualified"],false);assert_eq!(value["runtime_qualified"],false);
        let python=std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/python/test.go")).unwrap();assert!(python.contains("Device_common_data []string `android:\"path_device_common\"`"));assert!(python.contains("p.AddProperties(&p.testProperties)"));
        let sdk=std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/android_sdk/sdk_repo_host.go")).unwrap();assert!(sdk.contains("Merge_zips []string `android:\"arch_variant,path\"`"));assert!(sdk.contains("s.AddProperties(&s.properties)"));
        let java=std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/path-tag-fixtures/original-go/build/soong/java/base.go")).unwrap();assert!(java.contains("Device_common_java_resources proptools.Configurable[[]string] `android:\"path_device_common\"`"));
    }
}


#[cfg(test)]
mod compose_car_provider_tests {
    use super::*;
    use super::validate_source_extension643_compose_car as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 369178;
    const SOURCE_LOCK_SHA: &str = "6aacafd0aed644837e5616c658153f3ec6fa44c0e7ca2810e254f9fd0a2003a0";
    fn base() -> Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current() -> Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original643-compose-car-source-lock.json")).unwrap() }
    fn origins() -> Value {
        let raw = include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/origins.json");
        assert_eq!(raw.len(), 17156);
        assert_eq!(digest(raw), "3521e8aadd6752dc706c630e0220cca80bbc34d98271166994b72d695d122ffa");
        serde_json::from_slice(raw).unwrap()
    }
    #[test]
    fn compose_car_accepts_only_complete_same643_original_provider_plan() {
        let raw = include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original643-compose-car-source-lock.json");
        assert_eq!(raw.len(), SOURCE_LOCK_BYTES); assert_eq!(digest(raw), SOURCE_LOCK_SHA);
        validate_source_extension(&base(), &current()).unwrap();
        let parsed: droidloom_source::SparseSourceLock = serde_json::from_slice(raw).unwrap();
        let plan = droidloom_source::build_plan(&parsed).unwrap();
        assert_eq!((plan.projects.len(), plan.links.len(), plan.unrestricted_repo_sync), (643, 8, false));
        assert_eq!(plan.superproject_commit, "28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
        let old: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original643-path-data-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(), &old).is_err());
    }
    #[test]
    fn compose_car_rejects_missing_extra_reordered_or_revision_drifted_sources() {
        let good = current(); let base = base();
        for name in ["packages/services/Car", "prebuilts/misc"] {
            let index = good["projects"].as_array().unwrap().iter().position(|p| p["path"] == name).unwrap();
            for key in ["name", "path", "purpose", "commit"] {
                let mut bad = good.clone(); bad["projects"][index][key] = json!("changed");
                assert!(validate_source_extension(&base, &bad).is_err());
            }
            let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().pop();
            assert!(validate_source_extension(&base, &bad).is_err());
            let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("unrelated"));
            assert!(validate_source_extension(&base, &bad).is_err());
            let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().swap(0, 1);
            assert!(validate_source_extension(&base, &bad).is_err());
        }
        for key in ["status", "policy", "superproject", "links"] {
            let mut bad = good.clone(); bad[key] = json!(null);
            assert!(validate_source_extension(&base, &bad).is_err());
        }
        let mut bad = good.clone(); bad["projects"].as_array_mut().unwrap().swap(0, 1);
        assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][0]["commit"] = json!("0000000000000000000000000000000000000000");
        assert!(validate_source_extension(&base, &bad).is_err());
    }
    #[test]
    fn compose_car_pins_complete_fifteen_car_files_and_real_compose_apk() {
        let value = origins(); let files = value["files"].as_array().unwrap();
        assert_eq!(files.len(), 17); assert_eq!(value["physical_bytes"], 6272262);
        assert_eq!(value["max_blob_bytes"], 6237245); assert_eq!(value["new_sparse_cones"], 2);
        assert_eq!(value["new_source_projects"], 0); assert_eq!(value["new_large_blob_exceptions"], json!([]));
        assert_eq!(value["actual_Soong_qualified"], false); assert_eq!(value["source_materialization_qualified"], false); assert_eq!(value["runtime_qualified"], false);
        let mut expected = std::collections::BTreeSet::new();
        expected.insert("packages/services/Car/prebuilts/Android.bp".to_owned());
        for (version, scopes) in [("1", &["public"][..]), ("2", &["public", "system"][..]), ("3", &["module-lib", "public", "system", "test"][..])] {
            for scope in scopes { for module in ["android.car", "android.car-removed"] {
                expected.insert(format!("packages/services/Car/prebuilts/{version}/{scope}/api/{module}.txt"));
            } }
        }
        assert_eq!(expected.len(), 15);
        expected.insert("prebuilts/misc/common/androidx-perf/Android.bp".to_owned());
        expected.insert("prebuilts/misc/common/androidx-perf/ui_apks_compose-integration-tests-demos_compose-demos-testapp-release.apk".to_owned());
        let mut found = std::collections::BTreeSet::new();
        for row in files {
            let path = row["aosp_path"].as_str().unwrap(); assert!(found.insert(path.to_owned()));
            assert_eq!(path, format!("{}/{}", row["project"].as_str().unwrap(), row["path"].as_str().unwrap()));
            assert_eq!(row["mode"], "100644"); assert_eq!(row["git_blob"].as_str().unwrap().len(), 40);
            assert_eq!(row["sha256"].as_str().unwrap().len(), 64);
            assert!(row["bytes"].as_u64().unwrap() <= 16 * 1024 * 1024);
        }
        assert_eq!(found, expected);
        let apk = files.iter().find(|row| row["path"].as_str().unwrap().ends_with(".apk")).unwrap();
        assert_eq!(apk["bytes"], 6237245); assert_eq!(apk["git_blob"], "46c5e7718aea0f01ab407a7c2b94d2d902f37c6f");
        assert_eq!(apk["sha256"], "d9da9100c0d7789fbf5e1e8c6acb1b7e21cac5fadf40e00daea9da0dc4241b93");
        let bp = include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original-androidx-perf.Android.bp");
        assert_eq!(bp.len(), 960); assert_eq!(digest(bp), "23b107a9ac2a92617a15cc707a6fa0af95800259b6c5d5313e87cdae2f8590e0");
        let text = std::str::from_utf8(bp).unwrap();
        assert!(text.contains("filegroup {")); assert!(text.contains("name: \"ui_apks_compose-integration-tests-demos.apk\""));
        assert!(text.contains("\"ui_apks_compose-integration-tests-demos_compose-demos-testapp-release.apk\""));
        assert!(text.contains("\"//platform_testing/scripts/androidx-perf-setup:__subpackages__\""));
    }
    #[test]
    fn compose_car_uses_original_api_generator_for_both_missing_combined_names() {
        let bp = include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original-Car-prebuilts.Android.bp");
        assert_eq!(bp.len(), 833); assert_eq!(digest(bp), "8487f952ee4b8ee2921d425186ca51699bcdb25a24204d8f9eb2b7b4d7871082");
        let text = std::str::from_utf8(bp).unwrap();
        assert!(text.contains("prebuilt_apis {")); assert!(text.contains("name: \"car_sdk\""));
        let dirs = text.split("api_dirs: [").nth(1).unwrap().split(']').next().unwrap();
        let dirs: Vec<&str> = dirs.lines().map(str::trim).filter(|s| !s.is_empty()).collect();
        assert_eq!(dirs, ["\"1\",", "\"2\",", "\"3\","]);
        let go = include_bytes!("../../../android/native-generation-pair/compose-car-fixtures/original-prebuilt_apis.go");
        assert_eq!(go.len(), 16590); assert_eq!(digest(go), "ac992ca42c67498bd1b3f5e54627f541e6ffa71de95135bd7bac511a2427272c");
        let text = std::str::from_utf8(go).unwrap();
        assert!(text.contains("return module + \".api.combined.\" + scope + \".\" + version"));
        assert!(text.contains("apiLevelFiles := globApiDirs(mctx, p, \"api/*.txt\")"));
        assert!(text.contains("name := PrebuiltApiCombinedModuleName(info.module, info.scope, \"latest\")"));
        assert!(text.contains("createCombinedApiFilegroupModule(mctx, name, srcs)"));
        let value = origins();
        for module in ["android.car", "android.car-removed"] {
            assert!(value["files"].as_array().unwrap().iter().any(|row| row["aosp_path"] == format!("packages/services/Car/prebuilts/3/public/api/{module}.txt")));
            assert!(value["original_missing_modules"].as_array().unwrap().contains(&json!(format!("{module}.api.combined.public.latest"))));
        }
    }
}


#[cfg(test)]
mod ranging_snippet_provider_tests {
    use super::*;
    use super::validate_source_extension643_ranging as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 369228;
    const SOURCE_LOCK_SHA: &str = "714a3542c632c50c1516a033bcde13426d67177934dbdbfc8006efc2190f5aec";
    fn base() -> Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current() -> Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original643-ranging-source-lock.json")).unwrap() }
    #[test]
    fn ranging_snippet_accepts_only_complete_same643_original_provider_plan() {
        let raw=include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original643-ranging-source-lock.json");
        assert_eq!(raw.len(),SOURCE_LOCK_BYTES);assert_eq!(digest(raw),SOURCE_LOCK_SHA);
        validate_source_extension(&base(),&current()).unwrap();
        let lock:droidloom_source::SparseSourceLock=serde_json::from_slice(raw).unwrap();
        let plan=droidloom_source::build_plan(&lock).unwrap();
        assert_eq!((plan.projects.len(),plan.links.len(),plan.unrestricted_repo_sync),(643,8,false));
        assert_eq!(plan.superproject_commit,"28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        let old:Value=serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original643-compose-car-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(),&old).is_err());
        assert_eq!(TARGETS,&["libberberis_arm64","com.android.art"]);
    }
    #[test]
    fn ranging_snippet_rejects_partial_cone_extra_or_revision_policy_drift() {
        let good=current();let base=base();let index=good["projects"].as_array().unwrap().iter().position(|p|p["path"]=="packages/modules/Uwb").unwrap();
        for key in["name","path","purpose","commit"] {
            let mut bad=good.clone();bad["projects"][index][key]=json!("changed");assert!(validate_source_extension(&base,&bad).is_err());
        }
        for suffix in["Android.bp","RangingSnippet.java","AndroidManifest.xml"] {
            let mut bad=good.clone();let paths=bad["projects"][index]["sparse_paths"].as_array_mut().unwrap();paths.pop();paths.push(json!(format!("ranging/tests/multidevices/snippet/uwb/{suffix}")));assert!(validate_source_extension(&base,&bad).is_err());
        }
        let mut bad=good.clone();bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().pop();assert!(validate_source_extension(&base,&bad).is_err());
        let mut bad=good.clone();bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("unrelated"));assert!(validate_source_extension(&base,&bad).is_err());
        let mut bad=good.clone();bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().swap(0,1);assert!(validate_source_extension(&base,&bad).is_err());
        for key in["status","policy","superproject","links"] {let mut bad=good.clone();bad[key]=json!(null);assert!(validate_source_extension(&base,&bad).is_err());}
        let mut bad=good.clone();bad["projects"].as_array_mut().unwrap().swap(0,1);assert!(validate_source_extension(&base,&bad).is_err());
    }
    #[test]
    fn ranging_snippet_pins_real_blueprint_manifest_and_all_three_java_sources() {
        let raw=include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/origins.json");
        assert_eq!(raw.len(),3019);assert_eq!(digest(raw),"d50334591ee8acbd79a8d7ddc5c362a41e6a136b7a2f13b8997bfd2df9991048");let origin:Value=serde_json::from_slice(raw).unwrap();
        assert_eq!(origin["file_count"],5);assert_eq!(origin["physical_bytes"],45332);assert_eq!(origin["max_blob_bytes"],24943);
        assert_eq!(origin["project_commit"],"7c9e03046ff41cc28cf794cc2eda306fbc40279e");assert_eq!(origin["new_source_projects"],0);assert_eq!(origin["new_sparse_cones"],1);assert_eq!(origin["new_large_blob_exceptions"],json!([]));
        assert_eq!(origin["actual_Soong_qualified"],false);assert_eq!(origin["source_materialization_qualified"],false);assert_eq!(origin["runtime_qualified"],false);
        { let b=include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original-Android.bp"); assert_eq!(b.len(),1341); assert_eq!(digest(b),"d7c4d29864cbf720e6318cf8b516219cd569d013d40e2350d9e68eb3a5241376"); }
        { let b=include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original-AndroidManifest.xml"); assert_eq!(b.len(),1853); assert_eq!(digest(b),"0f8438c0c8d337a769714c539cc91bcd76e205ccea9d886edf6abc74d347e4a3"); }
        { let b=include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original-RangingPreferenceConverter.java"); assert_eq!(b.len(),15353); assert_eq!(digest(b),"8aa527968d98ba050a2f2839cdd8df87ccde227750abdc1949d1a6d72cddbbac"); }
        { let b=include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original-RangingSnippet.java"); assert_eq!(b.len(),24943); assert_eq!(digest(b),"e75526da0ebe7c3b1c3c0f216c3760ad96fac5ea5fad4e584fc4b35ef6a3e4e3"); }
        { let b=include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original-Utils.java"); assert_eq!(b.len(),1842); assert_eq!(digest(b),"59c001549be1f3b882d47b8ea929f7b2c7ce9ba87df1e57586619e635c5370ef"); }
        let bp=std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/ranging-snippet-fixtures/original-Android.bp")).unwrap();
        assert!(bp.contains("android_test {"));assert!(bp.contains("name: \"ranging_snippet\""));assert!(bp.contains("sdk_version: \"system_34\""));
        for name in["RangingSnippet.java","RangingPreferenceConverter.java","Utils.java","AndroidManifest.xml","framework-ranging.impl","ranging_aconfig_flags_lib"] {assert!(bp.contains(name));}
        let names:std::collections::BTreeSet<&str>=origin["files"].as_array().unwrap().iter().map(|r|r["path"].as_str().unwrap().rsplit('/').next().unwrap()).collect();
        assert_eq!(names,std::collections::BTreeSet::from(["Android.bp","AndroidManifest.xml","RangingPreferenceConverter.java","RangingSnippet.java","Utils.java"]));
    }
}


#[cfg(test)]
mod global_compat_provider_tests {
    use super::*;
    use super::validate_source_extension643_global_compat as validate_source_extension;
    const SOURCE_LOCK_BYTES: usize = 369245;
    const SOURCE_LOCK_SHA: &str = "e8b359276e49d6f520344284cbf2876f403d03150018d286ab8b0df362817e71";
    fn base() -> Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current() -> Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/original643-global-compat-source-lock.json")).unwrap() }
    #[test]
    fn global_compat_accepts_only_complete_same643_original_generator_plan() {
        let raw = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/original643-global-compat-source-lock.json");
        assert_eq!(raw.len(), SOURCE_LOCK_BYTES); assert_eq!(digest(raw), SOURCE_LOCK_SHA);
        validate_source_extension(&base(), &current()).unwrap();
        let lock: droidloom_source::SparseSourceLock = serde_json::from_slice(raw).unwrap();
        let plan = droidloom_source::build_plan(&lock).unwrap();
        assert_eq!((plan.projects.len(), plan.links.len(), plan.unrestricted_repo_sync), (643,8,false));
        assert_eq!(plan.superproject_commit, "28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        let old: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original643-ranging-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(), &old).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }
    #[test]
    fn global_compat_rejects_partial_generator_extra_or_revision_policy_drift() {
        let good = current(); let base = base(); let index = good["projects"].as_array().unwrap().iter().position(|p| p["path"] == "tools/platform-compat").unwrap();
        for key in ["name", "path", "purpose", "commit"] {
            let mut bad = good.clone(); bad["projects"][index][key] = json!("changed"); assert!(validate_source_extension(&base, &bad).is_err());
        }
        for suffix in ["Android.bp", "process_compat_config.py", "process-compat-config-test.py"] {
            let mut bad = good.clone(); let paths = bad["projects"][index]["sparse_paths"].as_array_mut().unwrap(); paths.pop(); paths.push(json!(format!("build/{suffix}"))); assert!(validate_source_extension(&base, &bad).is_err());
        }
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().pop(); assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("hiddenapi")); assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().swap(0,1); assert!(validate_source_extension(&base, &bad).is_err());
        for key in ["status", "policy", "superproject", "links"] { let mut bad = good.clone(); bad[key] = json!(null); assert!(validate_source_extension(&base, &bad).is_err()); }
        let mut bad = good.clone(); bad["projects"].as_array_mut().unwrap().swap(0,1); assert!(validate_source_extension(&base, &bad).is_err());
    }
    #[test]
    fn global_compat_pins_real_blueprint_host_generator_tests_and_consumers() {
        let raw = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/origins.json");
        assert_eq!(raw.len(), 2552); assert_eq!(digest(raw), "c111f2c79253c0c8f9a203e216fcb76ceca9f93367efd1796bce5a06b23647b9"); let origin: Value = serde_json::from_slice(raw).unwrap();
        assert_eq!(origin["file_count"],3); assert_eq!(origin["physical_bytes"],13390); assert_eq!(origin["max_blob_bytes"],6497);
        assert_eq!(origin["project_commit"],"19ce1c9d406cec9feaf76618e7d772113883d73f"); assert_eq!(origin["new_source_projects"],0); assert_eq!(origin["new_sparse_cones"],1); assert_eq!(origin["new_large_blob_exceptions"],json!([]));
        assert_eq!(origin["actual_Soong_qualified"],false); assert_eq!(origin["source_materialization_qualified"],false); assert_eq!(origin["runtime_qualified"],false);
        { let b = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-Android.bp"); assert_eq!(b.len(), 1236); assert_eq!(digest(b), "3520228b56a83b4941e8ee493bb9b35c029fa5421b0d9aeebda6e4a3072b646f"); }
        { let b = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-process-compat-config-test.py"); assert_eq!(b.len(), 6497); assert_eq!(digest(b), "df8d13102e89f5243cb1291bd9198586c4b11fefc93ded3ab7b4985fd2d57215"); }
        { let b = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-process_compat_config.py"); assert_eq!(b.len(), 5657); assert_eq!(digest(b), "b0081c5257dd250aa7f053355be247ea68ae05b9638ee4a9a862fdafe530a2a7"); }
        { let b = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-ApiDocs.bp"); assert_eq!(b.len(), 17045); assert_eq!(digest(b), "bc08714a21c1e9f7f0f5a09653eb285bd40f335225d57aafd5df59487b85fa9d"); }
        { let b = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-platform_compat_config.go"); assert_eq!(b.len(), 11713); assert_eq!(digest(b), "e7f7d5bfcc601b580ad40c4ae3905047213f330b0396fe716dbb3565c7b9d311"); }
        let graph_raw = include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/raw-git-graph.json");
        assert_eq!(graph_raw.len(), 1452); assert_eq!(digest(graph_raw), "c43f0aac1ec9b7512b9d2303906d87208e1197defa50842bd10a6ca8a3f71908");
        let graph: Value = serde_json::from_slice(graph_raw).unwrap(); assert_eq!(graph["commit"],origin["project_commit"]); assert_eq!(graph["selected_cone"],"build");
        let bp = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-Android.bp")).unwrap();
        for text in ["python_binary_host {", "name: \"process-compat-config\"", "main: \"process_compat_config.py\"", "srcs: [\"process_compat_config.py\"]", "python_test_host {", "main: \"process-compat-config-test.py\"", "global_compat_config {", "name: \"global-compat-config\"", "filename: \"all_compat_config.xml\""] { assert!(bp.contains(text), "{text}"); }
        let consumer = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-ApiDocs.bp")).unwrap();
        assert!(consumer.contains("compat_config: \":global-compat-config\""));
        let generator = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/global-compat-fixtures/original-platform_compat_config.go")).unwrap();
        assert!(generator.contains("RegisterModuleType(\"global_compat_config\"")); assert!(generator.contains("BuiltTool(\"process-compat-config\")"));
        let names: std::collections::BTreeSet<&str> = origin["files"].as_array().unwrap().iter().map(|r| r["path"].as_str().unwrap().rsplit('/').next().unwrap()).collect();
        assert_eq!(names, std::collections::BTreeSet::from(["Android.bp", "process_compat_config.py", "process-compat-config-test.py"]));
    }
}


#[cfg(test)]
mod cuttlefish_hotplug_provider_tests {
    use super::*;
    fn base() -> Value { serde_json::from_slice(include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json")).unwrap() }
    fn current() -> Value { serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/source-lock.json")).unwrap() }
    #[test]
    fn cuttlefish_hotplug_accepts_only_complete_same643_original_plan() {
        let raw = include_bytes!("../../../android/native-generation-pair/source-lock.json");
        assert_eq!(raw.len(), SOURCE_LOCK_BYTES); assert_eq!(digest(raw), SOURCE_LOCK_SHA);
        validate_source_extension(&base(), &current()).unwrap();
        let lock: droidloom_source::SparseSourceLock = serde_json::from_slice(raw).unwrap();
        let plan = droidloom_source::build_plan(&lock).unwrap();
        assert_eq!((plan.projects.len(), plan.links.len(), plan.unrestricted_repo_sync), (643,8,false));
        assert_eq!(plan.superproject_commit, "28f0bbddc24d56c8ec5a8df5342ac7a292184039");
        let old: Value = serde_json::from_slice(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/original643-global-compat-source-lock.json")).unwrap();
        assert!(validate_source_extension(&base(), &old).is_err());
        assert_eq!(TARGETS, &["libberberis_arm64", "com.android.art"]);
    }
    #[test]
    fn cuttlefish_hotplug_rejects_partial_source_extra_sibling_or_pin_drift() {
        let good = current(); let base = base(); let index = good["projects"].as_array().unwrap().iter().position(|p| p["path"] == "device/google/cuttlefish").unwrap();
        for key in ["name", "path", "purpose", "commit"] { let mut bad = good.clone(); bad["projects"][index][key] = json!("changed"); assert!(validate_source_extension(&base, &bad).is_err()); }
        for path in ["tests/graphics/hotplug/Android.bp", "tests/graphics/hotplug/AndroidManifest.xml", "tests/graphics/hotplug/src", "tests/graphics/display", "tests/graphics"] { let mut bad = good.clone(); let paths = bad["projects"][index]["sparse_paths"].as_array_mut().unwrap(); paths.pop(); paths.push(json!(path)); assert!(validate_source_extension(&base, &bad).is_err()); }
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().pop(); assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().push(json!("tests/graphics/display")); assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().swap(0,1); assert!(validate_source_extension(&base, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][index]["sparse_paths"].as_array_mut().unwrap().retain(|p| p != "tests/graphics/vulkan"); assert!(validate_source_extension(&base, &bad).is_err());
        for key in ["status", "policy", "superproject", "links"] { let mut bad = good.clone(); bad[key] = json!(null); assert!(validate_source_extension(&base, &bad).is_err()); }
        let mut bad = good.clone(); bad["projects"].as_array_mut().unwrap().swap(0,1); assert!(validate_source_extension(&base, &bad).is_err());
    }
    #[test]
    fn cuttlefish_hotplug_pins_complete_graphics57_and_real_dependency_providers() {
        let raw = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/origins.json");
        assert_eq!(raw.len(), 33787); assert_eq!(digest(raw), "16850c21c477e426f478ee0662dae188ce42d981e9677dc304c1d41d51a9e3d9"); let origin: Value = serde_json::from_slice(raw).unwrap();
        assert_eq!(origin["complete_graphics_files"],57); assert_eq!(origin["complete_graphics_bytes"],298980); assert_eq!(origin["retained_files"],43); assert_eq!(origin["new_files"],3); assert_eq!(origin["new_physical_bytes"],6021); assert_eq!(origin["unselected_independent_display_files"],11);
        assert_eq!(origin["project_commit"],"283645aacf6cdb56cc31a9362f54d412dbc132a1"); assert_eq!(origin["new_source_projects"],0); assert_eq!(origin["new_sparse_cones"],1); assert_eq!(origin["new_large_blob_exceptions"],json!([]));
        assert_eq!(origin["actual_Soong_qualified"],false); assert_eq!(origin["source_materialization_qualified"],false); assert_eq!(origin["runtime_qualified"],false);
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/existing-providers/cts/Android.bp"); assert_eq!(b.len(), 4835); assert_eq!(digest(b), "ca508162aaee017ef0bc52ca275e8bc93fd48ef10ee2b3ff46468535408397df"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/existing-providers/cts/common/device-side/util-axt/Android.bp"); assert_eq!(b.len(), 2458); assert_eq!(digest(b), "db2eb3ded3316f9157983155ed49b369fc43ef29e1331bd9b3f6c5317406dc8e"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/existing-providers/device/google/cuttlefish/Android.bp"); assert_eq!(b.len(), 5664); assert_eq!(digest(b), "2580299ebf86ef24dbf06e497dae23ae91d8db61262fd9aea07721dee234143b"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/existing-providers/device/google/cuttlefish/tests/utils/Android.bp"); assert_eq!(b.len(), 1091); assert_eq!(digest(b), "d1975a1a7dcd6657cb87f50ffcf93724bf255205cd3624f0f2e2008225be125c"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/existing-providers/prebuilts/misc/common/androidx-test/Android.bp"); assert_eq!(b.len(), 18643); assert_eq!(digest(b), "1ca774316a87df2136bcb1a0a8cfc5720ccf18ac7e206de2ca78332b3eafad38"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/existing-providers/prebuilts/sdk/current/androidx/m2repository/androidx/appcompat/appcompat/1.8.0-alpha01/Android.bp"); assert_eq!(b.len(), 1759); assert_eq!(digest(b), "245ab693b1938c9e7122ac26a19cc81d75820ccbdc10af8bb84671737ff45b74"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/Android.bp"); assert_eq!(b.len(), 2779); assert_eq!(digest(b), "8420e5342d930d1b4b7fbd3011f2dc33246dc5805f66f9ba87b55f1850a46038"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/Android.bp"); assert_eq!(b.len(), 3067); assert_eq!(digest(b), "48ffb3925817c7be477dfbe9d75b3f135505508b0a1a91f28e3dc20782c5c3d7"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/CfVkmsConnectorsTest.java"); assert_eq!(b.len(), 7762); assert_eq!(digest(b), "e8c5f1637d7e1e845fa99fbe5fba92b4759fee55380404c18d624b8154158a37"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/CfVkmsCursorTest.java"); assert_eq!(b.len(), 6001); assert_eq!(digest(b), "6a5697f01a4f0fcf426478896241630ad072a8fc3b36a755140f5b9e608c3e06"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/CfVkmsDisplaysTest.java"); assert_eq!(b.len(), 27872); assert_eq!(digest(b), "635c2753234c9f8c0c43578a18461bdf888cc76db1e42423d90a794af3f6bbf7"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/CfWritebackTest.java"); assert_eq!(b.len(), 5583); assert_eq!(digest(b), "ad9a1962ada5e3b402c9e19763e820b5b9c857061c9ff59614028a3abeb4a4e3"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/OWNERS"); assert_eq!(b.len(), 44); assert_eq!(digest(b), "8765b1884920ebd310c162f0982462271f5b9e3e49febdf9aa5a8d3b273940a3"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/TEST_MAPPING"); assert_eq!(b.len(), 141); assert_eq!(digest(b), "9ad6dfcdcf2ee68e4755fe57f661f6be8f0dcd4ad9210d5b810f19a8f5783a11"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/display_config_template.xml"); assert_eq!(b.len(), 1915); assert_eq!(digest(b), "d9bdfa53cd87a1e842a432625e321ef33bfc107d59c7b8bf1f1e4db0d7d85fc3"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/utils/Android.bp"); assert_eq!(b.len(), 855); assert_eq!(digest(b), "8b4ce1e8f600f2378cfcc41e59295b097226db46beea329015a8c6eca8d23a39"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/utils/CfVkmsEdidHelper.java"); assert_eq!(b.len(), 9284); assert_eq!(digest(b), "c9be1e0eafd9518665983ddcedd0c8b1251b076f3c0585c76a4ada979ec2150e"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/utils/CfVkmsTester.java"); assert_eq!(b.len(), 27608); assert_eq!(digest(b), "b02d2bcade559d93ac6a310c16f445a16d1f1e8152a1f07cd23879c8442685bc"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/hotplug/Android.bp"); assert_eq!(b.len(), 1385); assert_eq!(digest(b), "9bc5b4fcd503d454d5900e9849db2751e6cc6463054a837d419383db2a04f8f9"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/hotplug/AndroidManifest.xml"); assert_eq!(b.len(), 1374); assert_eq!(digest(b), "18bdf6c6747eebf5dae9d1aaff891bda8e60e0f3c0c04dfa319794d7455c5572"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/hotplug/src/com/android/cuttlefish/DisplayHotplugHelperApp.java"); assert_eq!(b.len(), 3262); assert_eq!(digest(b), "ca13c3f7ed39c418786ff336341030aabb040c13a12008f51848a50b8edaf7cb"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/src/com/android/cuttlefish/tests/CuttlefishDisplayHotplugTest.java"); assert_eq!(b.len(), 18957); assert_eq!(digest(b), "4a15ec5bb9e8d309a2b5961e15545578686ba951cfb85026629a89d35e3825c4"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/src/com/android/cuttlefish/tests/CuttlefishDisplayTests.java"); assert_eq!(b.len(), 2956); assert_eq!(digest(b), "87bae4bf842c6f2de2a158f2d0534a885126bab62461d68f5d5f265ab2450a05"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/src/com/android/cuttlefish/tests/CuttlefishGraphicsConfigurationTest.java"); assert_eq!(b.len(), 2346); assert_eq!(digest(b), "90b696cf6bfe92d42957c35e191f5d9dcd8b5be77cedc79c469bd5e45fd20db9"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/src/com/android/cuttlefish/tests/CuttlefishVulkanSnapshotTests.java"); assert_eq!(b.len(), 6737); assert_eq!(digest(b), "a0dea39118d865b95a22a2cc856d7ffc7b839dea948e79fb5b3e83687456e965"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/Android.bp"); assert_eq!(b.len(), 1630); assert_eq!(digest(b), "0bc9f45f02fa0dd6a0d8eeb259ffdcbe167f8ca8ae697fed405d44fe61c5b650"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/common.h"); assert_eq!(b.len(), 716); assert_eq!(digest(b), "d554d7a0760d157796d13ad3eb78b2542ba0b8f195ecafaf0bba4665aa447b17"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/Android.bp"); assert_eq!(b.len(), 1028); assert_eq!(digest(b), "0a9580fc913002adfd5d24ead7cf0f412fb06f21a4a3def9411d025a0b3b1273"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/AndroidManifest.xml"); assert_eq!(b.len(), 1651); assert_eq!(digest(b), "526333064b32d74d5b1f1746be979e47972e6bf298fe9cdc0894d9763a0cb28b"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.cpp"); assert_eq!(b.len(), 12627); assert_eq!(digest(b), "e07a09bd0d3e926f9a94b2b1c50e819c1d235a8b07334ff927dae8f54ea17ecc"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.frag"); assert_eq!(b.len(), 108); assert_eq!(digest(b), "354e1b71fd3a20c249af7cc5ceb6014c6b521ed7aeccc1a0865faef811e55238"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.frag.inl"); assert_eq!(b.len(), 2786); assert_eq!(digest(b), "528e8a49cced2ee3325be6f73273941ad128dfef79d509e71f6d9b62ef82b493"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.frag.spv"); assert_eq!(b.len(), 420); assert_eq!(digest(b), "e998e2db9e47c9f54803dfa1db97cce06d53a14c2b9325d8bda029a3c820fea4"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.h"); assert_eq!(b.len(), 1524); assert_eq!(digest(b), "1d5843ebf1427fc09b74338c78d7cdfdc92a923dd70b591cb1b557eec905c3eb"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.vert"); assert_eq!(b.len(), 212); assert_eq!(digest(b), "23100e368252a661c2f26b8809dfe89c4b535c38fb3783fdb617e5c2f69a492c"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.vert.inl"); assert_eq!(b.len(), 7511); assert_eq!(digest(b), "4a60ee4b29d4cb8c6985f8ef0b02ed85fe35c4e1901957aeb1846a08449a40c2"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_color/fullscreen_color.vert.spv"); assert_eq!(b.len(), 1172); assert_eq!(digest(b), "04f8b6012f36eddc556a173ceb1b1264e546b5ac85df462be0f329b7266f35ea"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/Android.bp"); assert_eq!(b.len(), 1036); assert_eq!(digest(b), "2364f2c1b8ee61483b1363da20e016b9f5f54cd38ee121a87c693cbc2bff34ac"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/AndroidManifest.xml"); assert_eq!(b.len(), 1657); assert_eq!(digest(b), "24dc014207ef215457a6691af1d65b286d606d9c451784f624b8e7d8fc335aa9"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.cpp"); assert_eq!(b.len(), 17857); assert_eq!(digest(b), "d0f922e8532db08b47bc579c760debef54b917418ec119d233fd92499fb20bf7"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.frag"); assert_eq!(b.len(), 213); assert_eq!(digest(b), "f2554fb100bc9c782abb750cf143f54e070c6e57e3c99faa19f1e6f7ff065ca0"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.frag.inl"); assert_eq!(b.len(), 4227); assert_eq!(digest(b), "10102edf2fa9965917d13ab6548009da9c38ea7caaeb712a2bba23267c1c201b"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.frag.spv"); assert_eq!(b.len(), 636); assert_eq!(digest(b), "50845f815841da6f9f12e3664c4be727bd002d0befbbb66ba50831356faae178"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.h"); assert_eq!(b.len(), 1751); assert_eq!(digest(b), "467d8a36a0a2ee8d73811903b00572a7d3c13ca050fe4b0c547a2bffb7ee9c66"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.vert"); assert_eq!(b.len(), 386); assert_eq!(digest(b), "35751e944e2e5be86805a3d6743cc8c3363133e78451a01f8a09779a2b8eb405"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.vert.inl"); assert_eq!(b.len(), 9310); assert_eq!(digest(b), "f5b9511fee169c78337467e3d4276052029fdc922bced5f4be2e01aee060a95a"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/fullscreen_texture/fullscreen_texture.vert.spv"); assert_eq!(b.len(), 1432); assert_eq!(digest(b), "82af35bc8839d8364f89e23f0deab2c6710173ed3becd1c8e77af6706a9102ca"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/image.cpp"); assert_eq!(b.len(), 1492); assert_eq!(digest(b), "2b7441d7397c9ff3028b31592d80ab839f9b58b081fbbe2d383679a71e03f391"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/image.h"); assert_eq!(b.len(), 1495); assert_eq!(digest(b), "949f7a2cb11d62e870be6e0b627427dff0d53147c35cd6d8c0cb67ff214e6291"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/main.cpp"); assert_eq!(b.len(), 2657); assert_eq!(digest(b), "1ab967e1c723f26116a7134d4b90a384b82bc79c0306a6173d2692d1b68ce9ee"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/process_shaders.sh"); assert_eq!(b.len(), 796); assert_eq!(digest(b), "29a008afc3678a2d5d7168417bd4ce5201dedd6ad45cb0c016a00ce60313fbcb"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/sample_base.cpp"); assert_eq!(b.len(), 52041); assert_eq!(digest(b), "ab82e161de1b94477a8b7e4364bffce72e01cbaa0669ff79a816fb62f1ee5ec1"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/sample_base.h"); assert_eq!(b.len(), 9898); assert_eq!(digest(b), "da842632a91d0747ceb65068768c5a2671362b58dafe9a117f37d85de7dce546"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/Android.bp"); assert_eq!(b.len(), 1059); assert_eq!(digest(b), "faab3131bd91476fc2edb691638c5ddc2dbe86a2227f6f7413b17cc287bab934"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/AndroidManifest.xml"); assert_eq!(b.len(), 1675); assert_eq!(digest(b), "18b65891680fcff39fa98eeb66ee9489eb9fe5fc4cd9794a048b3c5307339f01"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.cpp"); assert_eq!(b.len(), 14182); assert_eq!(digest(b), "57e85692c97828cee3a2c49fb30bf99bd1f5583a5570299585f8d390ae44c523"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.frag"); assert_eq!(b.len(), 108); assert_eq!(digest(b), "354e1b71fd3a20c249af7cc5ceb6014c6b521ed7aeccc1a0865faef811e55238"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.frag.inl"); assert_eq!(b.len(), 2793); assert_eq!(digest(b), "adc7f4858b20ec78c17e999eb5fae7765dacb314a5a36c91c7c8ff59ce7d5f0f"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.frag.spv"); assert_eq!(b.len(), 420); assert_eq!(digest(b), "e998e2db9e47c9f54803dfa1db97cce06d53a14c2b9325d8bda029a3c820fea4"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.h"); assert_eq!(b.len(), 1644); assert_eq!(digest(b), "a9eab3aad4255cc7ab21d60fd049a3b9173651cd4d863e0b25bd401d1256586a"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.vert"); assert_eq!(b.len(), 212); assert_eq!(digest(b), "23100e368252a661c2f26b8809dfe89c4b535c38fb3783fdb617e5c2f69a492c"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.vert.inl"); assert_eq!(b.len(), 7518); assert_eq!(digest(b), "e8cf6ba07025a0334525f0fe4427f1ed6c98b46d8608735b32f80c5ba28c3b1c"); }
        { let b = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/vulkan/secondary_command_buffer/secondary_command_buffer.vert.spv"); assert_eq!(b.len(), 1172); assert_eq!(digest(b), "04f8b6012f36eddc556a173ceb1b1264e546b5ac85df462be0f329b7266f35ea"); }
        let graph_raw = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/raw-git-graph.json"); assert_eq!(graph_raw.len(), 9229); assert_eq!(digest(graph_raw), "dfb3690ea0d8f865963480fb3aad27587b2b154efe8689d2cc3468ac3fdabf4a");
        let graph: Value = serde_json::from_slice(graph_raw).unwrap(); assert_eq!(graph["commit"],origin["project_commit"]); assert_eq!(graph["new_provider_cone"],"tests/graphics/hotplug");
        let deps_raw = include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/dependencies.json"); assert_eq!(deps_raw.len(), 3952); assert_eq!(digest(deps_raw), "15ba120c23f3b03c929e85163d4e3ccc75c3f348da4343dcdec840648ae0a5bb");
        let deps: Value = serde_json::from_slice(deps_raw).unwrap(); assert_eq!(deps["modules"].as_array().unwrap().len(),6); assert_eq!(deps["actual_Soong_qualified"],false); assert_eq!(deps["runtime_qualified"],false);
        let bp = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/hotplug/Android.bp")).unwrap();
        for text in ["android_test_helper_app {", "name: \"CuttlefishDisplayHotplugHelperApp\"", "defaults: [\"cts_defaults\"]", "sdk_version: \"test_current\"", "\"androidx.appcompat_appcompat\"", "\"androidx.test.rules\"", "\"compatibility-device-util-axt\"", "\"src/com/android/cuttlefish/DisplayHotplugHelperApp.java\""] { assert!(bp.contains(text), "{text}"); }
        let root_bp = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/Android.bp")).unwrap();
        for text in ["\":CuttlefishDisplayHotplugHelperApp\"", "\":CuttlefishVulkanSamplesFullscreenColor\"", "\":CuttlefishVulkanSamplesFullscreenTexture\"", "\":CuttlefishVulkanSamplesSecondaryCommandBuffer\""] { assert!(root_bp.contains(text), "{text}"); }
        let manifest = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/hotplug/AndroidManifest.xml")).unwrap(); assert!(manifest.contains("package=\"com.android.cuttlefish.displayhotplughelper\"")); assert!(manifest.contains("android:name=\"DisplayHotplugHelperApp\"")); assert!(manifest.contains("@android:style/Theme.DeviceDefault"));
        let java = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/hotplug/src/com/android/cuttlefish/DisplayHotplugHelperApp.java")).unwrap(); assert!(java.contains("package com.android.cuttlefish.displayhotplughelper;")); assert!(java.contains("public class DisplayHotplugHelperApp extends Activity"));
        let current = current(); let project = current["projects"].as_array().unwrap().iter().find(|p| p["path"] == "device/google/cuttlefish").unwrap(); let cones = project["sparse_paths"].as_array().unwrap(); assert!(cones.contains(&json!("tests/graphics/hotplug"))); assert!(!cones.contains(&json!("tests/graphics/display"))); assert!(!cones.contains(&json!("tests/graphics")));
        let sibling_bp = std::str::from_utf8(include_bytes!("../../../android/native-generation-pair/cuttlefish-graphics-fixtures/originals/tests/graphics/display/Android.bp")).unwrap(); assert!(sibling_bp.contains("name: \"CfVkmsConnectorsTest\"")); assert!(!sibling_bp.contains("CuttlefishDisplayHotplugHelperApp"));
    }
}
