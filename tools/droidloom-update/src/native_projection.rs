//! Native generation projections kept separate from the Audio source scope.
//! Every selected original provider and strict graph guard remains authenticated.
use super::*;

const TYPED_INGRESS_HAL_BLUEPRINTS: &[&str] = &[
    "packages/services/Car/cpp/vhal/client/Android.bp",
    "packages/services/Car/cpp/car_binder_lib/largeParcelable/Android.bp",
    "packages/modules/NeuralNetworks/Android.bp",
    "packages/modules/NeuralNetworks/common/Android.bp",
    "packages/modules/NeuralNetworks/common/types/Android.bp",
];

const TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT: &str =
    "frameworks/base/packages/SystemUI/tests/Android.bp";

const TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT: &str =
    "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp";

const ORDINARY_PAIR_REQUIRED_TEST_TREES: &[&str] = &[
    "frameworks/base/core/tests",
    "frameworks/base/media/tests",
    "frameworks/base/services/tests",
    "frameworks/base/tools/aapt2/integration-tests",
    "packages/modules/Virtualization/guest/trusty/test_vm",
];

pub(super) fn original_sdkextensions_provider(source: &Path) -> Result<bool> {
    // The ordinary native pair adds this official snapshot to its source lock.
    // Other build scopes can omit it and must retain their SDK jar fallbacks.
    // A selected but incomplete or changed snapshot must fail before projection.
    let project = source.join("prebuilts/module_sdk/SdkExtensions");
    if !project.try_exists()? {
        return Ok(false);
    }
    let original = fs::read(project.join("current/Android.bp"))?;
    use sha2::{Digest, Sha256};
    if original.len() != 3247
        || format!("{:x}", Sha256::digest(&original))
            != "733a15d52927e70b1dcc4c6df212ce8e63e32cd733a794afee68a56dccff714a"
    {
        return fail("exact pinned SdkExtensions SDK provider changed");
    }
    Ok(true)
}

pub(super) fn typed_ingress_shared_blueprint(relative: &str, original: &str) -> Result<String> {
    use sha2::{Digest, Sha256};
    let (bytes, sha, modules): (usize, &str, &[(&str, &str)]) = match relative {
        "frameworks/native/services/serialservice/Android.bp" => (2441,
            "9f1f577d4c747e85e765d43c72ff8bfa25ec6d21c951e6d19e3d62b4ca583f30",
            &[("rust_defaults", "serialservice_defaults"),
              ("rust_library", "libserialservice"),
              ("rust_fuzz", "serialservice_fuzzer")]),
        "frameworks/base/packages/SystemUI/Android.bp" => (49535,
            "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3",
            &[("soong_config_module_type", "systemui_optimized_java_defaults"),
              ("systemui_optimized_java_defaults", "SystemUI_optimized_defaults"),
              ("filegroup", "sysui_proguard_common_and_kotlin"),
              ("java_defaults", "SystemUI_compile_dagger")]),
        "frameworks/base/packages/SystemUI/tests/Android.bp" => (3392,
            "f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da",
            &[]),
        "hardware/interfaces/automotive/audiocontrol/aidl/default/Android.bp" => (1869,
            "9c8a0aecfa46ce0f1874362fa9dfff6a34326f9bf569b6fe7206dd6db1b3c9a6",
            &[]),
        "platform_testing/libraries/motion/Android.bp" => (2098,
            "a29bc25117f71e6acac6722f98950831a16a00f382c3ee0f9e991a36ecba5440",
            &[("filegroup", "motion_test_template"),
              ("java_defaults", "MotionTestDefaults"),
              ("filegroup", "PlatformMotionTesting-srcs"),
              ("android_library", "PlatformMotionTesting")]),
        "platform_testing/libraries/screenshot/Android.bp" => (2403,
            "53ba33c12075d68266d9c90620b2a0e04934e7d0b9eb73c1faf6c06cde689032",
            &[("android_library", "platform-screenshot-diff-core"),
              ("java_library", "platform-screenshot-diff-proto")]),
        "platform_testing/libraries/runner/Android.bp" => (2088,
            "e3b51cb5bc9ca15951a4da4b2ab711bfedd084eba95e2434060126accca8f5aa",
            &[("java_defaults", "platform-parametric-runner-lib_defaults"),
              ("android_library", "platform-parametric-runner-lib"),
              ("android_library", "platform-parametric-runner-lib-no-robo")]),
        "external/robolectric/Android.bp" => (12618,
            "5491a0f3918f8c5e89276ce13437b29bbd9b64aa2334e81717566e446bb6e1a4",
            &[("robolectric_build_props", "robolectric_build_props"),
              ("java_genrule", "libandroid_runtime_jar"),
              ("java_genrule", "robolectric_props_jar"),
              ("java_genrule", "robolectric_framework_res"),
              ("java_device_for_host", "robolectric_android-all-device-deps"),
              ("java_library", "robolectric-host-android_all"),
              ("java_library_host", "Robolectric_all"),
              ("java_host_for_device", "ClearcutJunitListenerAar"),
              ("java_host_for_device", "Robolectric_all-target"),
              ("java_device_for_host", "robolectric-host-androidx-test-core"),
              ("java_device_for_host", "robolectric-host-androidx-test-ext-junit"),
              ("java_device_for_host", "robolectric-host-androidx-test-monitor"),
              ("java_device_for_host", "robolectric-host-androidx-test-ext-truth"),
              ("java_device_for_host", "robolectric-host-androidx-test-runner"),
              ("java_device_for_host", "robolectric-host-androidx"),
              ("java_device_for_host", "robolectric-host-androidx_test_espresso"),
              ("java_device_for_host", "robolectric-host-android-support-multidex"),
              ("java_device_for_host", "robolectric-host-org_apache_http_legacy")]),
        "external/TestParameterInjector/Android.bp" => (2832,
            "3c39d19867e60e6f45ae39b3ee910b986de4cc158042519facaca18720d4ecf8",
            &[("java_library", "TestParameterInjector")]),
        "test/robolectric-extensions/Android.bp" => (1751,
            "cfbff8817cd8eb06cbd02bffa253ce0a2eb266e93fec6c8ab1894316e8ca6ab8",
            &[("java_library_host", "Robolectric-aosp-plugins")]),
        "packages/services/Car/car-lib/Android.bp" => (12547,
            "e88e92f8113c3c05f71999adfde6c50612d9d15d6454fbb0db9b98aba26fc6a2",
            &[("filegroup", "android.car-full-src"),
              ("java_defaults", "android.car-defaults"),
              ("java_library", "android.car")]),
        "packages/services/Car/car-builtin-lib/Android.bp" => (3748,
            "b7e38fdc5a873a7cd2607759d4eff2b560db218ea14c6a137da5bde70b4e9ceb",
            &[("java_defaults", "android.car.builtin-defaults"),
              ("java_sdk_library", "android.car.builtin")]),
        "packages/services/Car/car-lib/jni/large-parcelable/Android.bp" => (1590,
            "7f20480832afc1c33d54c846c2cab1a8cd6598278cd30f00b2a96b75932cbdb9",
            &[("cc_library", "liblargeparcelablejni")]),
        "external/icu/icu4j/Android.bp" => (5919,
            "e5a8137f19dbb133bdfa451c42493dbb481b1745a390817876b4636028a6014b",
            &[("java_defaults", "icu4j-defaults"),
              ("java_library", "icu4j"),
              ("java_import", "icu4j-icudata"),
              ("java_import", "icu4j-icutzdata"),
              ("java_library", "icu4j-icudata-jarjar"),
              ("java_library", "icu4j-icutzdata-jarjar"),
              ("java_library_host", "icu4j-host")]),
        "external/robolectric/pluginapi/Android.bp" => (1131,
            "b85704354df39ea533d97c8d6a2d51ef148889668d2c08d89fb59dd703e4aa15",
            &[("java_library_host", "Robolectric_pluginapi")]),
        "external/robolectric/resources/Android.bp" => (1395,
            "83e1f8f513e4c8dc9d3e9896e832cf6d5044f64a950dbb40b3d0ad8da9831bef",
            &[("java_library_host", "Robolectric_resources")]),
        "external/robolectric/robolectric/Android.bp" => (3390,
            "c9ae9050c080977591fa239ef37623826a5c7ffc125c78055059e375573feba4",
            &[("java_library_host", "Robolectric_robolectric"),
              ("genrule", "robolectric-version-upstream.properties")]),
        "external/robolectric/sandbox/Android.bp" => (1820,
            "0f35d9e221672dc164bd38e9c262fa5b38e892679f659e7e82b7dc5b50cd5e74",
            &[("java_library_host", "Robolectric_sandbox")]),
        "external/robolectric/shadowapi/Android.bp" => (1218,
            "36f67c55ad95f649e8a17a0770b8141d653c96c15f5213721b027154f9a21e69",
            &[("java_library_host", "Robolectric_shadowapi")]),
        "external/robolectric/utils/Android.bp" => (1491,
            "582130b938654da15b073bd6c8a616ad366358d125a0a53d14cc9d30e020b323",
            &[("java_library_host", "Robolectric_utils")]),
        "external/robolectric/shadows/httpclient/Android.bp" => (2446,
            "c1d4d324a0e0218c175e2f2e85806ccbeb398d797da57baf5221cf542f3d1268",
            &[("java_library_host", "Robolectric_shadows_httpclient")]),
        "external/robolectric/shadows/versioning/Android.bp" => (1647,
            "71262635df4c0b9aff77b4b8d5b3f80587d3a5d3d30a2941867c4e15dd398485",
            &[("java_library_host", "Robolectric_shadows_versioning")]),
        "external/robolectric/utils/reflector/Android.bp" => (1169,
            "82ed73680ad4eda143f6a38bb62198565e9b3a3b8211d9d3c5da6b5703ddae25",
            &[("java_library_host", "Robolectric_utils_reflector")]),
        "external/robolectric/processor/Android.bp" => (2723,
            "557bec83e3e684a6d9b6466827466043b0b1a1d61605aafaf35e581e974bea00",
            &[("java_library", "libRobolectric_processor"),
              ("java_plugin", "Robolectric_processor")]),
        "test/robolectric-extensions/clearcut-junit-listener/Android.bp" => (1132,
            "703b73b507250735b532c3c5f9eb4a0662606110e9a499632804136c0047c941",
            &[("java_library_host", "ClearcutJunitListener")]),
        "tools/asuite/Android.bp" => (1960,
            "04118667724a0433770f8d913207c510b5103a41d44600da62c337434ed2c5ae",
            &[("java_library_host", "asuite_proto_java_lite")]),
        "tools/asuite/atest/Android.bp" => (4006,
            "c38865f4312919d6452897db8e2e9341919ccb659c7a537ae20690a866e891e1",
            &[]),
        "packages/services/Car/cpp/vhal/client/Android.bp" => (1705,
            "d27df8040413d7575e066bded28bf04c72a62436dab9659b553eb1ae88819098",
            &[("cc_defaults", "vhalclient_defaults"),
              ("cc_library", "libvhalclient")]),
        "packages/services/Car/cpp/car_binder_lib/largeParcelable/Android.bp" => (1355,
            "66b33bf0a2234c0f301dfabed4e5ab7e69562d4bed111cedc6cd81ffa68ecfb8",
            &[("cc_defaults", "android-automotive-large-parcelable-defaults"),
              ("cc_library", "android-automotive-large-parcelable-lib")]),
        "packages/modules/NeuralNetworks/Android.bp" => (1726,
            "f408846ebf2fcbf1fc3075a312b2c388888bedd5bd7be96efb07301a9085ad08",
            &[("cc_defaults", "neuralnetworks_defaults")]),
        "packages/modules/NeuralNetworks/common/Android.bp" => (13060,
            "4153fd69cfeabb40bcefa51456a6b3747d835e96698150ed4e8bb950eba1f265",
            &[("cc_defaults", "neuralnetworks_cl_defaults")]),
        "packages/modules/NeuralNetworks/common/types/Android.bp" => (3279,
            "f3a14a68f3d0c918f44099b318fc22c8ff0067b4ddbc55b6c8e29177dff6487d",
            &[("cc_defaults", "neuralnetworks_utils_defaults"),
              ("cc_library_headers", "neuralnetworks_types_headers"),
              ("cc_defaults", "neuralnetworks_types_defaults"),
              ("cc_library_static", "neuralnetworks_types"),
              ("cc_library_static", "neuralnetworks_types_experimental"),
              ("cc_library_static", "neuralnetworks_types_cl")]),
        _ => return metadata_only(original),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != sha {
        return fail(format!("typed ingress shared provider source changed: {relative}"));
    }
    let mut projected = metadata_only(original)?;
    for (kind, name) in modules {
        let marker = format!("{kind} {{\n    name: \"{name}\",");
        if original.matches(&marker).count() != 1 {
            return fail(format!("typed ingress shared provider declaration changed: {relative}: {name}"));
        }
        let start = original.find(&marker).ok_or("shared provider marker missing")?;
        let end = start + original[start..].find("\n}\n")
            .ok_or("shared provider stanza unterminated")? + 3;
        projected.push('\n');
        projected.push_str(&original[start..end]);
    }
    Ok(projected)
}

pub(super) fn ordinary_pair_provider_blueprint(
    relative: &str, original: &str, ordinary_pair: bool,
) -> Result<Option<String>> {
    if !ordinary_pair {
        return Ok(None);
    }
    use sha2::{Digest, Sha256};
    let (bytes, sha) = match relative {
        "frameworks/base/libs/WindowManager/Shell/Android.bp" => (6272,
            "fc3a3c4de8e8ffbfc4832125b6a7b448a50fea1e0b5c6bad8ceb767b55679738"),
        "frameworks/base/packages/SystemUI/Android.bp" => (49535,
            "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3"),
        "frameworks/base/packages/SystemUI/tests/Android.bp" => (3392,
            "f1b2422c693a8f8c52034369ded585a3a93ac861f9dd6dd73f0801a77e6be4da"),
        "packages/apps/Launcher3/Android.bp" => (18026,
            "5c214bfc624650323ae51f0d1f6685a37e596a7d66796f5063a8d73103a0dc20"),
        "packages/apps/Settings/Android.bp" => (6448,
            "a2f9de37f38ce72b44adfff18e8553640e7255f80de3f00b248ec7c2f537e115"),
        "packages/modules/NeuralNetworks/common/Android.bp" => (13060,
            "4153fd69cfeabb40bcefa51456a6b3747d835e96698150ed4e8bb950eba1f265"),
        "packages/services/Car/car-lib/Android.bp" => (12547,
            "e88e92f8113c3c05f71999adfde6c50612d9d15d6454fbb0db9b98aba26fc6a2"),
        "tools/asuite/Android.bp" => (1960,
            "04118667724a0433770f8d913207c510b5103a41d44600da62c337434ed2c5ae"),
        "tools/asuite/atest/Android.bp" => (4006,
            "c38865f4312919d6452897db8e2e9341919ccb659c7a537ae20690a866e891e1"),
        "packages/modules/ConfigInfrastructure/aconfigd/Android.bp" => (3011,
            "da512bd47cdd87afa503d88cddb0b2aa83d3bee62f6506fdcb072327947d898d"),
        _ => return Ok(None),
    };
    if original.len() != bytes || format!("{:x}", Sha256::digest(original.as_bytes())) != sha {
        return fail(format!("ordinary pair original provider source changed: {relative}"));
    }
    Ok(Some(original.to_owned()))
}

pub(super) fn shared_root_blueprint(relative: &str, original: &str, typed_ingress: bool) -> Result<String> {
    if typed_ingress || matches!(relative,
        "frameworks/base/packages/SystemUI/Android.bp" |
        "frameworks/native/services/serialservice/Android.bp") {
        typed_ingress_shared_blueprint(relative, original)
    } else {
        metadata_only(original)
    }
}

pub(super) fn project_typed_ingress_hal_blueprints(p: &mut Projection, source: &Path, ordinary_pair: bool) -> Result<()> {
    for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
        let path = source.join(relative);
        let original = fs::read_to_string(&path)?;
        // Only new upstream providers are projected. The existing hardware
        // consumers remain byte-for-byte intact, including all defaults edges.
        let projected = match ordinary_pair_provider_blueprint(relative, &original, ordinary_pair)? {
            Some(original) => original,
            None => typed_ingress_shared_blueprint(relative, &original)?,
        };
        p.put(&path, projected)?;
    }
    Ok(())
}

pub(super) fn project_typed_ingress_systemui_tests(p: &mut Projection, source: &Path, ordinary_pair: bool) -> Result<()> {
    // The typed route retains three providers in SystemUI/Android.bp, not the
    // SystemUI application/test build. Match that boundary for these five
    // exact test modules only; other subdirectories are not traversed.
    // A complete upstream body is required before the original is journaled.
    let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
    let original = fs::read_to_string(&path)?;
    let projected = match ordinary_pair_provider_blueprint(
        TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT, &original, ordinary_pair)? {
        Some(original) => original,
        None => typed_ingress_shared_blueprint(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT, &original)?,
    };
    p.put(&path, projected)
}

pub(super) fn project_typed_ingress_audiocontrol_example(p: &mut Projection, source: &Path) -> Result<()> {
    // This route requests framework-minus-apex and libandroid_runtime only.
    // The single observed vendor example binary is outside that fixed scope.
    // Preserve its package/license metadata and journal its entire preimage;
    // keep parent AIDL providers, sibling sources, and the source lock intact.
    // This fixed leaf does not assert a complete generated Soong variant graph.
    let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
    let original = fs::read_to_string(&path)?;
    p.put(&path, typed_ingress_shared_blueprint(
        TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT, &original)?)
}

pub(super) fn project_ordinary_pair_graph_resources(
    repo: &Path, source: &Path, projection: &mut Projection,
    ordinary_pair: bool, dependency_mode: SoongDependencyMode,
) -> Result<()> {
    if !ordinary_pair {
        return Ok(());
    }
    if dependency_mode != SoongDependencyMode::Strict {
        return fail("ordinary pair graph resources require strict dependencies");
    }
    let context = source.join("build/blueprint/context.go");
    let soong = source.join("build/soong/ui/build/soong.go");
    let bootstrap = source.join("build/blueprint/bootstrap/command.go");
    if hash(&context)? != "1559969a55db1b682401c01264dd8ba96fa224781c3af277f0996a5050f7c9fa"
        || hash(&soong)? != "4e6fb778c1aee7bfc9b3206940364edbf3502912fe692fa91b612ab389ed07d9"
        || hash(&bootstrap)? != "bb681356afa58932692866c41086e122509dc65d36edabc22c7bb154be5c8f38" {
        return fail("ordinary pair expected its exact existing writer and Go memory projections");
    }
    projection.patch(source, "build/blueprint", &repo.join(
        "android/apex-compat/0010-blueprint-native-pair-provider-bound.patch"))?;
    projection.patch(source, "build/blueprint", &repo.join(
        "android/apex-compat/0011-blueprint-ordinary-pair-go-budget.patch"))?;
    let prior = fs::read_to_string(&soong)?;
    let setting = "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n";
    if prior.matches(setting).count() != 1 {
        return fail("ordinary pair analyzer memory setting changed");
    }
    // env -i requires the GC observation setting on the actual analyzer.
    projection.put(&soong, prior.replacen(setting,
        &(setting.to_owned() + "\tinvocationEnv[\"GODEBUG\"] = \"gctrace=1\"\n\tinvocationEnv[\"GOMAXPROCS\"] = \"2\"\n\tinvocationEnv[\"GOGC\"] = \"50\"\n"), 1))?;
    if hash(&context)? != "38f6ae2fa339f04834241b20d4185bc091aa9e16cb894030927bdc58a8f67182"
        || hash(&soong)? != "0b855ddee1c4e62203968104f22e949b50bf0ba323f7d2f7335cf84c9f9ec2a8"
        || hash(&bootstrap)? != "705fa207568d27eaeeeb825646956934b63c6a4d5240c6d6caf57a0978e3837c" {
        return fail("ordinary pair graph resource projection differs");
    }
    Ok(())
}

// This optional budget belongs only to the ordinary Vendor graph. The Native
// phase must retain its original exact projection so retained native output is
// still compared against the same source bytes under the normal source locks.
pub(super) const VENDOR_GRAPH_PROFILE_ENV: &str = "DROIDLOOM_OFFICIAL_VENDOR_GRAPH_PROFILE";
pub(super) fn project_official_vendor_graph_profile(
    source: &Path,
    projection: &mut Projection,
    vendor: bool,
    profile: Option<&str>,
) -> Result<()> {
    if !vendor || profile.is_none() {
        return Ok(());
    }
    if profile != Some("4x16g") {
        return fail("unsupported official Vendor graph resource profile");
    }
    let soong = source.join("build/soong/ui/build/soong.go");
    if hash(&soong)? != "0b855ddee1c4e62203968104f22e949b50bf0ba323f7d2f7335cf84c9f9ec2a8" {
        return fail("official Vendor graph profile requires the exact ordinary projection");
    }
    let prior = fs::read_to_string(&soong)?;
    let memory = "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n";
    let threads = "\tinvocationEnv[\"GOMAXPROCS\"] = \"2\"\n";
    if prior.matches(memory).count() != 1 || prior.matches(threads).count() != 1 {
        return fail("official Vendor graph resource settings changed");
    }
    projection.put(&soong, prior
        .replacen(memory, "\tinvocationEnv[\"GOMEMLIMIT\"] = \"16GiB\"\n", 1)
        .replacen(threads, "\tinvocationEnv[\"GOMAXPROCS\"] = \"4\"\n", 1))
}

pub(super) fn configure_ordinary_pair_graph_observation(command: &mut Command, ordinary_pair: bool) {
    if ordinary_pair {
        // Console mode exposes GC trace lines before graph generation exits.
        command.env("SOONG_UNBUFFERED_OUTPUT", "1");
    }
}

pub(super) fn project_test_fixture_exclusions(p: &mut Projection, source: &Path,
    ordinary_pair: bool, dependency_mode: SoongDependencyMode) -> Result<()> {
    if ordinary_pair {
        if dependency_mode != SoongDependencyMode::Strict {
            return fail("ordinary pair test provider discovery requires strict dependencies");
        }
        // Never remove or adopt an existing marker. A foreign/stale discovery
        // marker must be resolved before a normal build can claim visibility.
        for relative in ORDINARY_PAIR_REQUIRED_TEST_TREES {
            let marker = source.join(relative).join(".find-ignore");
            match fs::symlink_metadata(&marker) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                Err(error) => return Err(error.into()),
                Ok(_) => return fail(format!("ordinary pair required test tree is hidden: {}", marker.display())),
            }
        }
    }
    for relative in SOONG_EXCLUDED_TEST_FIXTURES {
        if ordinary_pair && ORDINARY_PAIR_REQUIRED_TEST_TREES.contains(relative) {
            continue;
        }
        p.put(&source.join(relative).join(".find-ignore"), b"")?;
    }
    Ok(())
}

pub(super) fn ordinary_pair_local_signer_blueprint(original: &str) -> Result<String> {
    use sha2::{Digest, Sha256};
    if original.len() != 5010 ||
       format!("{:x}", Sha256::digest(original.as_bytes())) !=
       "22f86ab11f2470d9e34861f7273dd92c0ba4e9b914710a71c22dc374ebbac2fb" {
        return fail("ordinary pair local signing provider source changed");
    }
    audio_without_unselected_cloud_kms(original)
}

pub(super) fn project_fallback_sdk_import(stem: &str, scope: &str, sdkextensions_provider: bool) -> bool {
    // Only these three scopes are supplied by the pinned java_sdk_library_import.
    // Keep any system-server fallback and every absent-snapshot build unchanged.
    if sdkextensions_provider
        && stem == "framework-sdkextensions"
        && matches!(scope, "public" | "system" | "module-lib")
    {
        return false;
    }
    // Preserve the original upstream java_sdk_library and
    // java_sdk_library_import providers. The prebuilt Connectivity Module
    // SDK supplies their stubs; sparse-build java_import fallbacks otherwise
    // duplicate prebuilt_*.stubs.module_lib variants.
    !matches!(
        stem,
        "framework-permission-s"
            | "framework-connectivity"
            | "framework-connectivity-b"
            | "framework-connectivity-t"
            | "framework-tethering"
    )
}

pub(super) fn project_blueprints(
    p: &mut Projection, source: &Path, typed_ingress: bool,
    ordinary_pair: bool, mode: SoongDependencyMode,
) -> Result<()> {
    super::project_blueprints_with_native(p, source, mode, Some((typed_ingress, ordinary_pair)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unified_native_requests_keep_exact_targets_and_audio_authority_separate() {
        let pair = FixedProductionRequest::NativePair;
        let audio = FixedProductionRequest::Existing(
            SoongDependencyMode::AudioApexTargetClosure,
            &["com.android.hardware.audio.droidloom"],
        );
        assert_eq!(pair.source_mode(), SoongDependencyMode::Strict);
        assert_eq!(pair.requested_targets(), crate::native_generation_pair_build::TARGETS);
        assert_eq!(pair.projection_targets(), pair.requested_targets());
        assert_eq!(audio.source_mode(), SoongDependencyMode::AudioApexTargetClosure);
        assert_ne!(pair.requested_targets(), audio.requested_targets());
        assert!(pair.validate("droidloom_arm64").is_err());
        assert!(pair.validate("droidloom_x86_64").is_ok());
        assert!(pair.policy_receipt_names().is_none());
        let mut command = Command::new("not-executed");
        pair.configure_dependencies(&mut command, "droidloom_x86_64").unwrap();
        assert!(command.get_envs().any(|(key, value)| key == "ALLOW_MISSING_DEPENDENCIES" && value == Some(std::ffi::OsStr::new("false"))));
        let description = pair.description("droidloom_x86_64").unwrap();
        assert_eq!(description["runtime_qualified"], false);
        assert_eq!(description["Audio_APEX_qualified"], false);
    }

    const SHARED_PROVIDER_FIXTURES: &[(&str, &str, &str)] = &[
        ("frameworks/base/packages/SystemUI/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp"),
         "d6e2c5813cd1b8e5823fb11a29612ba0369c843f17b226ec076894a6c7a1451c"),
        (TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT,
         include_str!("../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp"),
         "42118873220b0cc4d07e21a961052ddd5d81ab67be8df5d7c9dba9bd966aaeb5"),
        (TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT,
         include_str!("../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp"),
         "d73b00f17a80375d2d59e408088c5e875c3311bd0f7487b117d4b8d28f7cff93"),
        ("platform_testing/libraries/motion/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/motion.Android.bp"),
         "23e1392f716fbf78efb7b0ea5281c3cf70b4547b6aa41af8cf79df495eace098"),
        ("platform_testing/libraries/screenshot/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/screenshot.Android.bp"),
         "6249d22918a5c2d02a5efc6e20013e75f0eabb0c8e492f40d1e83d4009409007"),
        ("platform_testing/libraries/runner/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/runner.Android.bp"),
         "fcc2907dfabd23aafa5c63c4b2825769b85884a7f6feab3e3ffeb33e07cb9dfd"),
        ("external/robolectric/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-root.Android.bp"),
         "0c1dbf256397da0814954949ae33b53952ad2c2ae97980a7947ea262e4619359"),
        ("external/TestParameterInjector/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/test-parameter.Android.bp"),
         "8c968ba42fd26a4fca996740f91164c5d339616ed04b69b34c79bd3464d1b744"),
        ("test/robolectric-extensions/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-aosp-plugins.Android.bp"),
         "7f784da6379787a862ecd71c32d5f021314bc6705e9e7a6d4bb8360c3ebb5c30"),
        ("packages/services/Car/car-lib/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-lib.Android.bp"),
         "690a87d0a8ce5f3bd628770c7c8d25691290ccc7a85dfbdeeece69facb04647d"),
        ("packages/services/Car/car-builtin-lib/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-builtin.Android.bp"),
         "a9b66992fe7484f49d6c809f87f6dc481aba9aef75a797bb7e7638f02199cfc8"),
        ("packages/services/Car/car-lib/jni/large-parcelable/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-jni.Android.bp"),
         "8baf86d459edd9e216e9d6b5649b1bc560d65c9b8b9a8f30eb44581079466c8a"),
        ("external/icu/icu4j/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/icu4j.Android.bp"),
         "fa4314ac6dead0e1138631c6649c5980e0222e5a54cb523ac2db27809b2b7dc6"),
        ("external/robolectric/pluginapi/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-pluginapi.Android.bp"),
         "2c4d145186abf766583c132dcfb902ce21bb409ab5f5ee3904fcae5214ad518a"),
        ("external/robolectric/resources/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-resources.Android.bp"),
         "881e27bf7db87b8eec7e6236d3a871d84b12af26c53b9a9fb3f74a418e8b9a66"),
        ("external/robolectric/robolectric/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-robolectric.Android.bp"),
         "cabde3f0683d9515a10e155b778c3805122d07a8a6d3d94a71367abac63bfc36"),
        ("external/robolectric/sandbox/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-sandbox.Android.bp"),
         "7f1364ab109bec260809fa92a9d2a767128179f0986dc609bce8f56d669bdb14"),
        ("external/robolectric/shadowapi/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-shadowapi.Android.bp"),
         "76f38523ee0b8684edcb22c508b329f1e55b93ff3316047fe0ce57efc2b035ad"),
        ("external/robolectric/utils/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-utils.Android.bp"),
         "a8b6af937d2d67d7f1ee3ecd2032976f6c93264ed5dad438f75560ff16df9111"),
        ("external/robolectric/shadows/httpclient/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-shadows-httpclient.Android.bp"),
         "75572b9618806850fc596f36356316879b0ed2b9ec57376b459b357d5c3dc006"),
        ("external/robolectric/shadows/versioning/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-shadows-versioning.Android.bp"),
         "8de2263cf57483ae007f85835f6401bdb40eb061d8dff62ac8ae206b03d33d28"),
        ("external/robolectric/utils/reflector/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-utils-reflector.Android.bp"),
         "71eb852c68f73ec03daae1a7b0d5a40aae2ca3ed64d19c3f941452f84b034fca"),
        ("external/robolectric/processor/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/robolectric-processor.Android.bp"),
         "a371760f74de15214ff0c13db200d09231b00472e87c8784aaf40d5ca423829b"),
        ("test/robolectric-extensions/clearcut-junit-listener/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/clearcut-junit-listener.Android.bp"),
         "2bd33a3e44d8b60dd8296aa892791f85cf128ba31bf3547cc8a796f476b138dc"),
        ("tools/asuite/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/asuite-proto.Android.bp"),
         "8d8ed13a96c779c96ce59c848c189a3fdfad5202371ad4317d9f36675b4843ab"),
        ("tools/asuite/atest/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/asuite-atest-metadata.Android.bp"),
         "cf7439663957b768c8a14064f65637122fb4ad5788216a67d8bd9dad8d7215ca"),
        ("packages/services/Car/cpp/vhal/client/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-vhal-client.Android.bp"),
         "19c13fe0d2c46091266998a8a39dd8eee9235b05abb8b4772db026ec4290d12d"),
        ("packages/services/Car/cpp/car_binder_lib/largeParcelable/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/car-large-parcelable.Android.bp"),
         "7d1e2ed8e52279903ab3f15ef4e4ff3ede2d41a03fc3903006bf73685167f8d9"),
        ("packages/modules/NeuralNetworks/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/neuralnetworks-root.Android.bp"),
         "e063e7c1b86cf20657d591f83432371ff9465c3706edf56fbd0686f0753c0d12"),
        ("packages/modules/NeuralNetworks/common/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/neuralnetworks-common.Android.bp"),
         "9e4477760e24bc5c7c5b44cf0bf20010bab8e09eee282dde4fd114d1b76a3dad"),
        ("packages/modules/NeuralNetworks/common/types/Android.bp",
         include_str!("../../../android/native-role-ingress/provider-fixtures/neuralnetworks-types.Android.bp"),
         "3c4f7ac57497efa7e5f7a40b20a8cb5ea70a8587258fcc89b1472f026ca824d1"),
    ];

    const REAL_SERIALSERVICE_BLUEPRINT: &str = r###"// Copyright 2025 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package {
    default_team: "trendy_team_webapps_cros_android",
}

rust_defaults {
    name: "serialservice_defaults",
    proc_macros: [
        "libasync_trait",
    ],
    rustlibs: [
        "android.hardware.serialservice-rust",
        "libanyhow",
        "libatrace_rust",
        "libbinder_rs",
        "libbinder_tokio_rs",
        "libfutures",
        "liblog_rust",
        "liblogger",
        "libmockall",
        "libnix",
        "librustutils",
        "libtokio",
        "libtokio_stream",
        "libtracing",
        "libueventd",
    ],
}

rust_binary {
    name: "serialservice",
    srcs: ["rust/service.rs"],
    system_ext_specific: true,
    defaults: ["serialservice_defaults"],
    init_rc: ["serialservice.rc"],
    rustlibs: [
        "libandroid_hardware_serial_flags_rust",
        "libatrace_tracing_subscriber",
        "libserialservice",
        "libtracing_subscriber",
    ],
    prefer_rlib: true,
    required: ["serialservice_overlay"],
}

rust_library {
    name: "libserialservice",
    crate_name: "serialservice",
    crate_root: "rust/lib.rs",
    system_ext_specific: true,
    defaults: ["serialservice_defaults"],
    init_rc: ["serialservice.rc"],
}

rust_test {
    name: "serialservice_test",
    crate_name: "serialservice",
    crate_root: "rust/lib.rs",
    defaults: ["serialservice_defaults"],
    srcs: ["rust/*.rs"],
    test_options: {
        unit_test: true,
    },
    test_suites: ["device-tests"],
    rustlibs: [
        "libandroid_logger",
        "libserialservice",
        "libtempfile",
        "libtokio_test",
    ],
}

rust_fuzz {
    name: "serialservice_fuzzer",
    srcs: ["rust/service_fuzzer.rs"],
    defaults: [
        "serialservice_defaults",
        "service_fuzzer_defaults_rs",
    ],
    rustlibs: [
        "libserialservice",
    ],
}
"###;

    const REAL_PAIR_APKSIG_BLUEPRINT: &str =
        include_str!("../tests/fixtures/production-apksig-original.Android.bp");

    const REAL_SDKEXTENSIONS_BLUEPRINT: &str = r###"// This is auto-generated. DO NOT EDIT.

package {
    // A default list here prevents the license LSC from adding its own list which would
    // be unnecessary as every module in the sdk already has its own licenses property.
    default_applicable_licenses: ["Android-Apache-2.0"],
}

apex_contributions_defaults {
    name: "sdkextensions-sdk.contributions",
    contents: ["prebuilt_framework-sdkextensions"],
}

prebuilt_bootclasspath_fragment {
    name: "com.android.sdkext-bootclasspath-fragment",
    visibility: ["//visibility:public"],
    apex_available: ["com.android.sdkext"],
    licenses: ["sdkextensions-sdk_Android-Apache-2.0"],
    contents: ["framework-sdkextensions"],
    fragments: [
        {
            apex: "com.android.art",
            module: "art-bootclasspath-fragment",
        },
    ],
    hidden_api: {
        annotation_flags: "hiddenapi/annotation-flags.csv",
        metadata: "hiddenapi/metadata.csv",
        index: "hiddenapi/index.csv",
        signature_patterns: "hiddenapi/signature-patterns.csv",
        filtered_stub_flags: "hiddenapi/filtered-stub-flags.csv",
        filtered_flags: "hiddenapi/filtered-flags.csv",
    },
}

java_sdk_library_import {
    name: "framework-sdkextensions",
    visibility: ["//visibility:public"],
    apex_available: [
        "com.android.sdkext",
        "test_com.android.sdkext",
    ],
    licenses: ["sdkextensions-sdk_Android-Apache-2.0"],
    shared_library: false,
    permitted_packages: ["android.os.ext"],
    public: {
        jars: ["sdk_library/public/framework-sdkextensions-stubs.jar"],
        stub_srcs: ["sdk_library/public/framework-sdkextensions.srcjar"],
        current_api: "sdk_library/public/framework-sdkextensions.txt",
        removed_api: "sdk_library/public/framework-sdkextensions-removed.txt",
        annotations: "sdk_library/public/framework-sdkextensions_annotations.zip",
        sdk_version: "module_current",
    },
    system: {
        jars: ["sdk_library/system/framework-sdkextensions-stubs.jar"],
        stub_srcs: ["sdk_library/system/framework-sdkextensions.srcjar"],
        current_api: "sdk_library/system/framework-sdkextensions.txt",
        removed_api: "sdk_library/system/framework-sdkextensions-removed.txt",
        annotations: "sdk_library/system/framework-sdkextensions_annotations.zip",
        sdk_version: "module_current",
    },
    module_lib: {
        jars: ["sdk_library/module-lib/framework-sdkextensions-stubs.jar"],
        stub_srcs: ["sdk_library/module-lib/framework-sdkextensions.srcjar"],
        current_api: "sdk_library/module-lib/framework-sdkextensions.txt",
        removed_api: "sdk_library/module-lib/framework-sdkextensions-removed.txt",
        annotations: "sdk_library/module-lib/framework-sdkextensions_annotations.zip",
        sdk_version: "module_current",
    },
}

license {
    name: "sdkextensions-sdk_Android-Apache-2.0",
    visibility: ["//visibility:private"],
    license_kinds: ["SPDX-license-identifier-Apache-2.0"],
    license_text: ["licenses/build/soong/licenses/LICENSE"],
}

license {
    name: "sdkextensions-sdk_opensourcerequest",
    visibility: ["//visibility:private"],
    license_text: ["licenses/build/soong/licenses/opensourcerequest"],
}
"###;

    #[test]
    fn ordinary_pair_vkms_maintenance_metadata_preserves_consumers_and_recovers() {
        let original = include_bytes!("../../../android/native-generation-pair/original-vkms-controller.Android.bp");
        assert_eq!(original.len(), 1522);
        for interrupted in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let path = source.join("device/google/cuttlefish/guest/commands/vkms_controller/Android.bp");
            let unselected = source.join("device/google/cuttlefish/tests/graphics/display/Android.bp");
            write(&path, original).unwrap();
            write(&unselected, b"unselected sibling must remain unchanged\n").unwrap();
            let before_time = fs::metadata(&path).unwrap().modified().unwrap();
            assert_eq!(hash(&path).unwrap(), "fad92f331030a22d22d989e4df4f7b6fdd90f2d11b702f90fd1d26304783b45d");
            let journal = temp.path().join("projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            crate::native_generation_pair_build::project_vkms_maintenance_metadata(
                &source, &mut projection).unwrap();
            let effective = fs::read_to_string(&path).unwrap();
            let original_text = std::str::from_utf8(original).unwrap();
            assert_eq!(effective.len(), 1473);
            assert_eq!(hash(&path).unwrap(), "bd556a4385b92f6808a8d9df94f118a8b2f93e35a0598fef636fe0f91c075b7f");
            let consumer_start = original_text.find("cc_binary {").unwrap();
            assert!(effective.ends_with(&original_text[consumer_start..]));
            assert_eq!(effective, original_text.replacen(
                "    default_team: \"trendy_team_desktop_display\",\n", "", 1));
            let inventory = projection.effective_inventory(temp.path(), &source).unwrap();
            assert_eq!(inventory["files"].as_object().unwrap().len(), 1);
            assert!(inventory["patches"].as_object().unwrap().is_empty());
            let metadata = crate::native_generation_pair_build::vkms_maintenance_metadata_inputs(
                &source, &inventory).unwrap();
            assert_eq!(metadata["runtime_security_policy_changed"], false);
            assert!(crate::native_generation_pair_build::vkms_maintenance_metadata_inputs(
                &source, &serde_json::json!({"files": {}})).is_err());
            if interrupted {
                // Preserve a real interrupted journal for the normal recovery API.
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            } else {
                projection.restore().unwrap();
            }
            assert_eq!(fs::read(&path).unwrap(), original);
            assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), before_time);
            assert_eq!(fs::read(&unselected).unwrap(), b"unselected sibling must remain unchanged\n");
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_vkms_maintenance_metadata_rejects_untrusted_input_without_mutation() {
        let original = include_bytes!("../../../android/native-generation-pair/original-vkms-controller.Android.bp");
        let before = std::str::from_utf8(original).unwrap();
        for variant in ["edited-source", "already-projected", "symlink", "hardlink"] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let path = source.join("device/google/cuttlefish/guest/commands/vkms_controller/Android.bp");
            let target = temp.path().join("protected-original.bp");
            write(&target, original).unwrap();
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            match variant {
                "edited-source" => write(&path, before.replace("main.cpp", "evil.cpp")).unwrap(),
                "already-projected" => write(&path, before.replacen(
                    "    default_team: \"trendy_team_desktop_display\",\n", "", 1)).unwrap(),
                "symlink" => std::os::unix::fs::symlink(&target, &path).unwrap(),
                "hardlink" => fs::hard_link(&target, &path).unwrap(),
                _ => unreachable!(),
            }
            let snapshot = fs::read(&path).unwrap();
            let journal = temp.path().join("projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            assert!(crate::native_generation_pair_build::project_vkms_maintenance_metadata(
                &source, &mut projection).is_err(), "{variant}");
            assert_eq!(fs::read(&path).unwrap(), snapshot);
            assert_eq!(fs::read(&target).unwrap(), original);
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_provider_bound_preserves_existing_writer_and_restores() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let original = include_bytes!("../tests/fixtures/native-pair-graph/context.original.go");
        let soong_original = include_bytes!("../tests/fixtures/native-pair-graph/soong.original.go");
        let bootstrap_original = include_bytes!("../tests/fixtures/native-pair-graph/bootstrap-command.original.go");
        for ordinary_pair in [false, true] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let context = source.join("build/blueprint/context.go");
            let soong = source.join("build/soong/ui/build/soong.go");
            let bootstrap = source.join("build/blueprint/bootstrap/command.go");
            write(&context, original).unwrap();
            write(&soong, soong_original).unwrap();
            write(&bootstrap, bootstrap_original).unwrap();
            let context_time = fs::metadata(&context).unwrap().modified().unwrap();
            let soong_time = fs::metadata(&soong).unwrap().modified().unwrap();
            let bootstrap_time = fs::metadata(&bootstrap).unwrap().modified().unwrap();
            let journal = temp.path().join("projection.json");
            let mut p = Projection::new(journal.clone()).unwrap();
            // Reproduce the exact pre-existing ordinary pair projection order.
            p.patch(&source, "build/soong", &repo.join(
                "android/native-generation-pair/0008-soong-leaf-go-memory-budget.patch")).unwrap();
            p.patch(&source, "build/blueprint", &repo.join(
                "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch")).unwrap();
            let before_context = fs::read(&context).unwrap();
            let before_soong = fs::read(&soong).unwrap();
            assert_eq!(hash(&context).unwrap(), "1559969a55db1b682401c01264dd8ba96fa224781c3af277f0996a5050f7c9fa");
            project_ordinary_pair_graph_resources(&repo, &source, &mut p,
                ordinary_pair, SoongDependencyMode::Strict).unwrap();
            let inventory = p.effective_inventory(&repo, &source).unwrap();
            assert_eq!(inventory["files"].as_object().unwrap().len(), if ordinary_pair { 3 } else { 2 });
            assert_eq!(inventory["patches"].as_object().unwrap().len(), if ordinary_pair { 4 } else { 2 });
            if ordinary_pair {
                assert_eq!(hash(&context).unwrap(), "38f6ae2fa339f04834241b20d4185bc091aa9e16cb894030927bdc58a8f67182");
                assert_eq!(hash(&soong).unwrap(), "0b855ddee1c4e62203968104f22e949b50bf0ba323f7d2f7335cf84c9f9ec2a8");
                assert_eq!(hash(&bootstrap).unwrap(), "705fa207568d27eaeeeb825646956934b63c6a4d5240c6d6caf57a0978e3837c");
                let expected = String::from_utf8(before_context).unwrap().replacen(
                    "parallelVisitSimple(c.iterateAllVariants(), 1000,",
                    "parallelVisitSimple(c.iterateAllVariants(), parallelVisitLimit,", 1);
                assert_eq!(fs::read_to_string(&context).unwrap(), expected);
                let expected = String::from_utf8(before_soong).unwrap().replacen(
                    "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n",
                    "\tinvocationEnv[\"GOMEMLIMIT\"] = \"5GiB\"\n\tinvocationEnv[\"GODEBUG\"] = \"gctrace=1\"\n\tinvocationEnv[\"GOMAXPROCS\"] = \"2\"\n\tinvocationEnv[\"GOGC\"] = \"50\"\n", 1);
                assert_eq!(fs::read_to_string(&soong).unwrap(), expected);
                assert!(project_ordinary_pair_graph_resources(&repo, &source, &mut p,
                    true, SoongDependencyMode::Strict).is_err());
            } else {
                assert_eq!(fs::read(&context).unwrap(), before_context);
                assert_eq!(fs::read(&soong).unwrap(), before_soong);
                assert_eq!(fs::read(&bootstrap).unwrap(), bootstrap_original);
            }
            p.restore().unwrap();
            assert_eq!(fs::read(&context).unwrap(), original);
            assert_eq!(fs::read(&soong).unwrap(), soong_original);
            assert_eq!(fs::read(&bootstrap).unwrap(), bootstrap_original);
            assert_eq!(fs::metadata(&context).unwrap().modified().unwrap(), context_time);
            assert_eq!(fs::metadata(&soong).unwrap().modified().unwrap(), soong_time);
            assert_eq!(fs::metadata(&bootstrap).unwrap().modified().unwrap(), bootstrap_time);
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_provider_bound_rejects_wrong_mode_and_drift_before_writes() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let original = include_bytes!("../tests/fixtures/native-pair-graph/context.original.go");
        let soong_original = include_bytes!("../tests/fixtures/native-pair-graph/soong.original.go");
        let bootstrap_original = include_bytes!("../tests/fixtures/native-pair-graph/bootstrap-command.original.go");
        for mode in [SoongDependencyMode::NativeBridgeTargetClosure,
            SoongDependencyMode::NativeEngineTargetClosure, SoongDependencyMode::AudioApexTargetClosure,
            SoongDependencyMode::MinigbmTargetClosure] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let journal = temp.path().join("projection.json");
            let mut p = Projection::new(journal.clone()).unwrap();
            project_ordinary_pair_graph_resources(&repo, &source, &mut p, false, mode).unwrap();
            assert!(p.originals.is_empty());
            assert!(!journal.exists());
            assert!(project_ordinary_pair_graph_resources(&repo, &source, &mut p, true, mode).is_err());
            assert!(p.originals.is_empty());
            assert!(!journal.exists());
        }
        for drift in ["context", "soong", "bootstrap"] {
            let temp = tempfile::tempdir().unwrap();
            let source = temp.path().join("source");
            let context = source.join("build/blueprint/context.go");
            let soong = source.join("build/soong/ui/build/soong.go");
            let bootstrap = source.join("build/blueprint/bootstrap/command.go");
            write(&context, original).unwrap();
            write(&soong, soong_original).unwrap();
            write(&bootstrap, bootstrap_original).unwrap();
            let journal = temp.path().join("projection.json");
            let mut prior = Projection::new(journal.clone()).unwrap();
            prior.patch(&source, "build/soong", &repo.join(
                "android/native-generation-pair/0008-soong-leaf-go-memory-budget.patch")).unwrap();
            prior.patch(&source, "build/blueprint", &repo.join(
                "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch")).unwrap();
            let path = match drift { "context" => &context, "soong" => &soong, _ => &bootstrap };
            write(path, fs::read_to_string(path).unwrap() + "\n// drift\n").unwrap();
            let changed = fs::read(path).unwrap();
            let before = fs::read(&journal).unwrap();
            assert!(project_ordinary_pair_graph_resources(&repo, &source, &mut prior,
                true, SoongDependencyMode::Strict).is_err());
            assert_eq!(fs::read(path).unwrap(), changed);
            assert_eq!(fs::read(&journal).unwrap(), before);
            prior.restore().unwrap();
            assert_eq!(fs::read(&context).unwrap(), original);
            assert_eq!(fs::read(&soong).unwrap(), soong_original);
            if drift == "bootstrap" {
                assert_eq!(fs::read(&bootstrap).unwrap(), changed);
            } else {
                assert_eq!(fs::read(&bootstrap).unwrap(), bootstrap_original);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn ordinary_pair_gc_observation_keeps_target_and_dependency_configuration() {
        for ordinary_pair in [false, true] {
            let mut command = Command::new("fixture-soong");
            command.args(["--make-mode", "-j2", "libberberis_arm64", "com.android.art"]);
            configure_soong_dependencies(&mut command, SoongDependencyMode::Strict,
                crate::native_generation_pair_build::TARGETS).unwrap();
            let before_args: Vec<_> = command.get_args().map(|s| s.to_owned()).collect();
            configure_ordinary_pair_graph_observation(&mut command, ordinary_pair);
            let after_args: Vec<_> = command.get_args().map(|s| s.to_owned()).collect();
            assert_eq!(before_args, after_args);
            let envs: std::collections::BTreeMap<_, _> = command.get_envs()
                .map(|(k,v)| (k.to_string_lossy().into_owned(), v.map(|x| x.to_string_lossy().into_owned()))).collect();
            assert_eq!(envs.get("ALLOW_MISSING_DEPENDENCIES"), Some(&Some("false".to_owned())));
            let expected = if ordinary_pair { Some(Some("1".to_owned())) } else { None };
            assert_eq!(envs.get("SOONG_UNBUFFERED_OUTPUT"), expected.as_ref());
            assert!(!envs.contains_key("SOONG_PARTIAL_ANALYSIS"));
        }
    }

    #[test]
    fn normal_serialservice_projection_preserves_real_fuzzer_and_dependencies() {
        let original = REAL_SERIALSERVICE_BLUEPRINT;
        let expected_bodies = [
            r###"rust_defaults {
    name: "serialservice_defaults",
    proc_macros: [
        "libasync_trait",
    ],
    rustlibs: [
        "android.hardware.serialservice-rust",
        "libanyhow",
        "libatrace_rust",
        "libbinder_rs",
        "libbinder_tokio_rs",
        "libfutures",
        "liblog_rust",
        "liblogger",
        "libmockall",
        "libnix",
        "librustutils",
        "libtokio",
        "libtokio_stream",
        "libtracing",
        "libueventd",
    ],
}
"###,
            r###"rust_library {
    name: "libserialservice",
    crate_name: "serialservice",
    crate_root: "rust/lib.rs",
    system_ext_specific: true,
    defaults: ["serialservice_defaults"],
    init_rc: ["serialservice.rc"],
}
"###,
            r###"rust_fuzz {
    name: "serialservice_fuzzer",
    srcs: ["rust/service_fuzzer.rs"],
    defaults: [
        "serialservice_defaults",
        "service_fuzzer_defaults_rs",
    ],
    rustlibs: [
        "libserialservice",
    ],
}
"###,
        ];
        for typed in [false, true] {
            let projected = shared_root_blueprint(
                "frameworks/native/services/serialservice/Android.bp", original, typed).unwrap();
            let mut expected = metadata_only(original).unwrap();
            for body in expected_bodies {
                expected.push('\n');
                expected.push_str(body);
            }
            assert_eq!(projected, expected);
            assert!(!projected.contains("rust_binary {\n    name: \"serialservice\","));
            assert!(!projected.contains("rust_test {\n    name: \"serialservice_test\","));
            assert!(projected.contains("\"service_fuzzer_defaults_rs\""));
            assert!(projected.contains("\"android.hardware.serialservice-rust\""));
        }
    }

    #[test]
    fn normal_serialservice_projection_rejects_source_drift() {
        for changed in [
            REAL_SERIALSERVICE_BLUEPRINT.replace("serialservice_fuzzer", "changed_fuzzer"),
            format!("{}\n", REAL_SERIALSERVICE_BLUEPRINT),
        ] {
            assert!(shared_root_blueprint(
                "frameworks/native/services/serialservice/Android.bp", &changed, false).is_err());
        }
    }

    #[test]
    fn normal_systemui_projection_keeps_real_dagger_defaults() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp");
        let expected = r#"java_defaults {
    name: "SystemUI_compile_dagger",

    plugins: ["dagger2-compiler"],

    annotation_processor_flags: [
        "dagger.fastInit=ENABLED",
        "dagger.explicitBindingConflictsWithInject=ERROR",
        "dagger.useBindingGraphFix=ENABLED",
    ],

    defaults_visibility: ["//visibility:public"],
}
"#;
        for typed in [false, true] {
            let projected = shared_root_blueprint(
                "frameworks/base/packages/SystemUI/Android.bp", original, typed).unwrap();
            assert!(projected.starts_with(metadata_only(original).unwrap().as_str()));
            assert_eq!(projected.matches(expected).count(), 1);
            assert!(!projected.contains("name: \"SystemUI-core\""));
        }
    }

    #[test]
    fn normal_systemui_projection_rejects_drift_and_keeps_other_roots() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp");
        let changed = original.replace("dagger.fastInit=ENABLED", "dagger.fastInit=DISABLED");
        assert!(shared_root_blueprint(
            "frameworks/base/packages/SystemUI/Android.bp", &changed, false).is_err());
        let other = "package {\n    default_applicable_licenses: [\"license\"],\n}\njava_defaults {\n    name: \"other\",\n}\n";
        assert_eq!(shared_root_blueprint("packages/apps/Settings/Android.bp", other, false).unwrap(),
                   metadata_only(other).unwrap());
    }

    #[test]
    fn typed_shared_provider_projection_keeps_exact_upstream_bodies_and_metadata() {
        use sha2::{Digest, Sha256};
        for (relative, original, expected_sha) in SHARED_PROVIDER_FIXTURES {
            let projected = typed_ingress_shared_blueprint(relative, original).unwrap();
            assert!(projected.starts_with(metadata_only(original).unwrap().as_str()));
            assert_eq!(&format!("{:x}", Sha256::digest(projected.as_bytes())), expected_sha);
            assert!(!projected.contains("name: \"SystemUI-core\""));
            assert!(!projected.contains("name: \"PlatformMotionTestingRoboApplication\""));
            assert!(!projected.contains("name: \"platform-screenshot-diff-test\""));
        }
    }

    fn ordinary_pair_provider_fixtures() -> Vec<(&'static str, &'static str)> {
        let mut fixtures: Vec<_> = SHARED_PROVIDER_FIXTURES.iter()
            .filter(|row| matches!(row.0,
                "frameworks/base/packages/SystemUI/Android.bp" |
                "frameworks/base/packages/SystemUI/tests/Android.bp" |
                "packages/modules/NeuralNetworks/common/Android.bp" |
                "packages/services/Car/car-lib/Android.bp" |
                "tools/asuite/Android.bp" |
                "tools/asuite/atest/Android.bp"))
            .map(|row| (row.0, row.1)).collect();
        fixtures.extend([
            ("frameworks/base/libs/WindowManager/Shell/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/Shell.Android.bp")),
            ("packages/apps/Launcher3/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/Launcher3.Android.bp")),
            ("packages/apps/Settings/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/Settings.Android.bp")),
            ("packages/modules/ConfigInfrastructure/aconfigd/Android.bp", include_str!("../../../android/native-generation-pair/provider-fixtures/aconfigd.Android.bp")),
        ]);
        assert_eq!(fixtures.len(), 10);
        fixtures
    }

    #[test]
    fn ordinary_pair_providers_keep_all_ten_original_bodies_only_for_the_pair() {
        for (relative, original) in ordinary_pair_provider_fixtures() {
            assert_eq!(ordinary_pair_provider_blueprint(relative, original, true).unwrap(),
                Some(original.to_owned()));
            assert_eq!(ordinary_pair_provider_blueprint(relative, original, false).unwrap(), None);
        }
        for (relative, original, expected) in SHARED_PROVIDER_FIXTURES {
            use sha2::{Digest, Sha256};
            let projected = typed_ingress_shared_blueprint(relative, original).unwrap();
            assert_eq!(format!("{:x}", Sha256::digest(projected.as_bytes())), *expected);
        }
        assert_eq!(ordinary_pair_provider_blueprint("other/Android.bp", "unrelated", true).unwrap(), None);
    }

    #[test]
    fn ordinary_pair_provider_drift_is_rejected_and_normal_projection_restores_bytes_and_time() {
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("source");
        let journal = fixture.path().join("projection.json");
        let before = std::time::UNIX_EPOCH + std::time::Duration::from_secs(1_600_000_000);
        for (relative, original) in ordinary_pair_provider_fixtures() {
            let path = source.join(relative);
            write(&path, original).unwrap();
            fs::File::open(&path).unwrap().set_modified(before).unwrap();
            for changed in [format!("{original}\n"), original.replacen("name:", "renamed:", 1)] {
                assert!(ordinary_pair_provider_blueprint(relative, &changed, true).is_err());
            }
        }
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            for (relative, original) in ordinary_pair_provider_fixtures() {
                let text = ordinary_pair_provider_blueprint(relative, original, true).unwrap().unwrap();
                projection.put(&source.join(relative), text).unwrap();
            }
            assert_eq!(projection.originals.len(), 10);
            assert!(journal.exists());
        }
        assert!(!journal.exists());
        for (relative, original) in ordinary_pair_provider_fixtures() {
            let path = source.join(relative);
            assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
            assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), before);
        }
    }

    #[test]
    fn ordinary_pair_test_discovery_preserves_other_routes_and_restores_its_markers() {
        for ordinary_pair in [false, true] {
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("source");
            let journal = fixture.path().join("projection.json");
            let consumer = source.join("platform_testing/Android.bp");
            write(&consumer, "unchanged upstream consumer bytes\n").unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                project_test_fixture_exclusions(&mut projection, &source,
                    ordinary_pair, SoongDependencyMode::Strict).unwrap();
                for relative in SOONG_EXCLUDED_TEST_FIXTURES {
                    let visible = ordinary_pair && ORDINARY_PAIR_REQUIRED_TEST_TREES.contains(relative);
                    assert_eq!(source.join(relative).join(".find-ignore").exists(), !visible);
                }
                assert_eq!(fs::read(&consumer).unwrap(), b"unchanged upstream consumer bytes\n");
            }
            assert!(!journal.exists());
            for relative in SOONG_EXCLUDED_TEST_FIXTURES {
                assert!(!source.join(relative).join(".find-ignore").exists());
            }
        }
    }

    #[test]
    fn ordinary_pair_existing_test_markers_and_wrong_modes_fail_before_any_new_marker() {
        use std::os::unix::fs::symlink;
        for is_link in [false, true] {
            for relative in ORDINARY_PAIR_REQUIRED_TEST_TREES {
                let fixture = tempfile::tempdir().unwrap();
                let source = fixture.path().join("source");
                let journal = fixture.path().join("projection.json");
                let marker = source.join(relative).join(".find-ignore");
                fs::create_dir_all(marker.parent().unwrap()).unwrap();
                if is_link { symlink("nonexistent", &marker).unwrap(); }
                else { write(&marker, b"foreign marker\n").unwrap(); }
                let mut projection = Projection::new(journal.clone()).unwrap();
                assert!(project_test_fixture_exclusions(&mut projection, &source,
                    true, SoongDependencyMode::Strict).is_err());
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert!(fs::symlink_metadata(&marker).is_ok());
                if !is_link { assert_eq!(fs::read(&marker).unwrap(), b"foreign marker\n"); }
            }
        }
        let fixture = tempfile::tempdir().unwrap();
        let journal = fixture.path().join("projection.json");
        let mut projection = Projection::new(journal.clone()).unwrap();
        assert!(project_test_fixture_exclusions(&mut projection, fixture.path(),
            true, SoongDependencyMode::NativeBridgeTargetClosure).is_err());
        assert!(project_blueprints(&mut projection, fixture.path(), true,
            true, SoongDependencyMode::NativeBridgeTargetClosure).is_err());
        assert!(!journal.exists());
    }

    #[test]
    fn typed_shared_provider_projection_rejects_changed_missing_or_duplicate_stanzas() {
        for (relative, original, _) in SHARED_PROVIDER_FIXTURES {
            for changed in [original.replacen("name:", "renamed:", 1),
                            format!("{original}\n"),
                            format!("{original}{original}")] {
                assert!(typed_ingress_shared_blueprint(relative, &changed).is_err());
            }
        }
    }

    #[test]
    fn typed_shared_provider_projection_keeps_other_root_projection_unchanged() {
        let source = "package {\n    default_applicable_licenses: [\"license\"],\n}\njava_defaults {\n    name: \"other\",\n}\n";
        assert_eq!(typed_ingress_shared_blueprint("packages/apps/Settings/Android.bp", source).unwrap(),
                   metadata_only(source).unwrap());
    }

    #[test]
    fn typed_hal_provider_projection_restores_real_sources_and_keeps_consumers() {
        use sha2::{Digest, Sha256};
        assert_eq!(TYPED_INGRESS_HAL_BLUEPRINTS.len(), 5);
        assert_eq!(SHARED_PROVIDER_FIXTURES.len(), 31);
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let journal = fixture.path().join("projection.json");
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            write(&source.join(relative), original.as_bytes()).unwrap();
        }
        let consumers = [
            ("hardware/interfaces/automotive/remoteaccess/hal/default/Android.bp",
             include_str!("../../../android/native-role-ingress/provider-fixtures/hardware-remote-access.Android.bp")),
            ("hardware/interfaces/neuralnetworks/utils/common/Android.bp",
             include_str!("../../../android/native-role-ingress/provider-fixtures/hardware-neural-common.Android.bp")),
        ];
        for (relative, original) in consumers {
            write(&source.join(relative), original.as_bytes()).unwrap();
        }
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_hal_blueprints(&mut projection, &source, false).unwrap();
        assert!(journal.exists());
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, _, expected_sha) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            let projected = fs::read(source.join(relative)).unwrap();
            assert_eq!(&format!("{:x}", Sha256::digest(&projected)), expected_sha);
        }
        for (relative, original) in consumers {
            assert_eq!(fs::read(source.join(relative)).unwrap(), original.as_bytes());
        }
        projection.restore().unwrap();
        assert!(!journal.exists());
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            assert_eq!(fs::read(source.join(relative)).unwrap(), original.as_bytes());
        }
    }

    #[test]
    fn typed_hal_provider_late_source_drift_restores_earlier_projections() {
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let journal = fixture.path().join("projection.json");
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            write(&source.join(relative), original.as_bytes()).unwrap();
        }
        let bad_path = *TYPED_INGRESS_HAL_BLUEPRINTS.last().unwrap();
        let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
            .find(|row| row.0 == bad_path).unwrap();
        let changed = format!("{original}\n");
        write(&source.join(bad_path), changed.as_bytes()).unwrap();
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            let error = project_typed_ingress_hal_blueprints(&mut projection, &source, false)
                .unwrap_err().to_string();
            assert!(error.contains("typed ingress shared provider source changed"));
            assert!(error.contains(bad_path));
            assert!(journal.exists());
        }
        assert!(!journal.exists());
        for relative in TYPED_INGRESS_HAL_BLUEPRINTS {
            let (_, original, _) = SHARED_PROVIDER_FIXTURES.iter()
                .find(|row| row.0 == *relative).unwrap();
            let expected = if *relative == bad_path { changed.as_bytes() } else { original.as_bytes() };
            assert_eq!(fs::read(source.join(relative)).unwrap(), expected);
        }
    }

    #[test]
    fn typed_systemui_test_projection_keeps_metadata_parent_providers_and_other_paths() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        let parent_original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI.Android.bp");
        let names = [
            "SystemUITests_defaults", "SystemUITests",
            "SystemUITests_systemui_accessibility", "SystemUITests_presubmit",
            "SystemUI_test_fixtures",
        ];
        assert_eq!(original.matches("    name: \"").count(), names.len());
        for name in names {
            assert_eq!(original.matches(&format!("    name: \"{name}\",")).count(), 1);
        }
        let expected = concat!(
            "package {\n",
            "    default_team: \"trendy_team_system_ui_please_use_a_more_specific_subteam_if_possible_\",\n",
            "    default_applicable_licenses: [\"frameworks_base_packages_SystemUI_license\"],\n",
            "}\n",
        );
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
        let parent = source.join("frameworks/base/packages/SystemUI/Android.bp");
        let untouched = source.join("frameworks/base/packages/SystemUI/tests/other/Android.bp");
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        write(&parent, parent_original).unwrap();
        write(&untouched, "unrelated exact bytes\n").unwrap();
        let parent_projected = typed_ingress_shared_blueprint(
            "frameworks/base/packages/SystemUI/Android.bp", parent_original).unwrap();
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            projection.put(&parent, &parent_projected).unwrap();
            project_typed_ingress_systemui_tests(&mut projection, &source, false).unwrap();
            assert_eq!(fs::read(&path).unwrap(), expected.as_bytes());
            assert_eq!(fs::read(&parent).unwrap(), parent_projected.as_bytes());
            assert_eq!(fs::read(&untouched).unwrap(), b"unrelated exact bytes\n");
            let originals: Vec<Original> = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
            assert_eq!(originals.len(), 2);
            assert_eq!(originals[0].path, parent);
            assert_eq!(originals[0].bytes.as_deref(), Some(parent_original.as_bytes()));
            assert_eq!(originals[1].path, path);
            assert_eq!(originals[1].bytes.as_deref(), Some(original.as_bytes()));
        }
        assert!(!journal.exists());
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert_eq!(fs::read(&parent).unwrap(), parent_original.as_bytes());
        assert_eq!(fs::read(&untouched).unwrap(), b"unrelated exact bytes\n");
    }

    #[test]
    fn typed_systemui_test_projection_rejects_wrong_source_before_journal_or_write() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        for changed in [
            original.replacen("SystemUITests_defaults", "SystemUITests_defaultX", 1),
            format!("{original}\n"),
        ] {
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("aosp-source");
            let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
            let journal = fixture.path().join("projection.json");
            write(&path, &changed).unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                let error = project_typed_ingress_systemui_tests(&mut projection, &source, false)
                    .unwrap_err().to_string();
                assert!(error.contains("typed ingress shared provider source changed"));
                assert!(error.contains(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT));
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
            }
            assert!(!journal.exists());
            assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
        }
    }

    #[test]
    fn typed_systemui_test_projection_recovers_complete_original_from_durable_journal() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/SystemUI-tests.Android.bp");
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_SYSTEMUI_TESTS_BLUEPRINT);
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_systemui_tests(&mut projection, &source, false).unwrap();
        assert_ne!(fs::read(&path).unwrap(), original.as_bytes());
        let originals: Vec<Original> = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
        assert_eq!(originals.len(), 1);
        assert_eq!(originals[0].path, path);
        assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        // Model an interrupted process while exercising the real recover entry.
        std::mem::forget(projection);
        assert!(Projection::new(journal.clone()).is_err());
        recover(&journal, &source).unwrap();
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert!(!journal.exists());
    }

    #[test]
    fn typed_audiocontrol_example_projection_keeps_metadata_and_sibling_sources() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        assert_eq!(original.matches("cc_binary {").count(), 1);
        assert_eq!(original.matches("    name: \"").count(), 1);
        assert_eq!(original.matches(
            "    name: \"android.hardware.automotive.audiocontrol-service.example\",").count(), 1);
        for name in [
            "latest_android_hardware_audio_common_ndk_shared",
            "latest_android_hardware_automotive_audiocontrol_ndk_shared",
            "powerpolicyclient_defaults",
            "car.audio.configuration.xsd.default",
            "car.fade.configuration.xsd.default",
        ] {
            assert_eq!(original.matches(&format!("        \"{name}\",")).count(), 1);
        }
        let expected = concat!(
            "package {\n",
            "    // See: http://go/android-license-faq\n",
            "    // A large-scale-change added 'default_applicable_licenses' to import\n",
            "    // all of the 'license_kinds' from \"hardware_interfaces_license\"\n",
            "    // to get the below license kinds:\n",
            "    //   SPDX-license-identifier-Apache-2.0\n",
            "    default_applicable_licenses: [\"hardware_interfaces_license\"],\n",
            "}\n",
        );
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
        let parent = source.join("hardware/interfaces/automotive/audiocontrol/aidl/Android.bp");
        let sibling = source.join("hardware/interfaces/automotive/audiocontrol/aidl/default/AudioControl.cpp");
        let manifest = source.join(".droidloom-source-manifest.json");
        let journal = fixture.path().join("projection.json");
        // Explicit sentinels test write scope, not the content of real providers.
        let sentinels = [
            (&parent, "unchanged parent AIDL provider sentinel\n"),
            (&sibling, "unchanged sibling implementation sentinel\n"),
            (&manifest, "unchanged source manifest sentinel\n"),
        ];
        write(&path, original).unwrap();
        for (p, value) in sentinels { write(p, value).unwrap(); }
        {
            let mut projection = Projection::new(journal.clone()).unwrap();
            project_typed_ingress_audiocontrol_example(&mut projection, &source).unwrap();
            assert_eq!(fs::read(&path).unwrap(), expected.as_bytes());
            for (p, value) in sentinels {
                assert_eq!(fs::read(p).unwrap(), value.as_bytes());
            }
            let originals: Vec<Original> =
                decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
            assert_eq!(originals.len(), 1);
            assert_eq!(originals[0].path, path);
            assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        }
        assert!(!journal.exists());
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        for (p, value) in sentinels { assert_eq!(fs::read(p).unwrap(), value.as_bytes()); }
    }

    #[test]
    fn typed_audiocontrol_example_projection_rejects_source_drift_before_write() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        for changed in [
            original.replacen("powerpolicyclient_defaults", "powerpolicyclient_changed", 1),
            original.replacen("car.fade.configuration.xsd.default", "car.fade.configuration.xsd.changed", 1),
            format!("{original}\n"),
        ] {
            assert_ne!(changed.as_bytes(), original.as_bytes());
            let fixture = tempfile::tempdir().unwrap();
            let source = fixture.path().join("aosp-source");
            let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
            let journal = fixture.path().join("projection.json");
            write(&path, &changed).unwrap();
            {
                let mut projection = Projection::new(journal.clone()).unwrap();
                let error = project_typed_ingress_audiocontrol_example(&mut projection, &source)
                    .unwrap_err().to_string();
                assert!(error.contains("typed ingress shared provider source changed"));
                assert!(error.contains(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT));
                assert!(projection.originals.is_empty());
                assert!(!journal.exists());
                assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
            }
            assert!(!journal.exists());
            assert_eq!(fs::read(&path).unwrap(), changed.as_bytes());
        }
    }

    #[test]
    fn typed_audiocontrol_example_projection_recovers_full_observed_original() {
        let original = include_str!(
            "../../../android/native-role-ingress/provider-fixtures/audiocontrol-example.Android.bp");
        let fixture = tempfile::tempdir().unwrap();
        let source = fixture.path().join("aosp-source");
        let path = source.join(TYPED_INGRESS_AUDIOCONTROL_EXAMPLE_BLUEPRINT);
        let journal = fixture.path().join("projection.json");
        write(&path, original).unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        project_typed_ingress_audiocontrol_example(&mut projection, &source).unwrap();
        assert_ne!(fs::read(&path).unwrap(), original.as_bytes());
        let originals: Vec<Original> =
            decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
        assert_eq!(originals.len(), 1);
        assert_eq!(originals[0].path, path);
        assert_eq!(originals[0].bytes.as_deref(), Some(original.as_bytes()));
        std::mem::forget(projection);
        assert!(Projection::new(journal.clone()).is_err());
        recover(&journal, &source).unwrap();
        assert_eq!(fs::read(&path).unwrap(), original.as_bytes());
        assert!(!journal.exists());
    }

    #[test]
    fn ordinary_pair_local_signer_keeps_exact_real_upstream_modules() {
        let original = REAL_PAIR_APKSIG_BLUEPRINT;
        let projected = ordinary_pair_local_signer_blueprint(original).unwrap();
        for required in [
            r###"java_library {
    name: "apksig",
    srcs: ["src/main/java/**/*.java"],
    exclude_srcs: [
        "src/main/java/com/android/apksig/kms/aws/**/*.java",
        "src/main/java/com/android/apksig/kms/gcp/**/*.java",
    ],
    java_version: "1.8",
    host_supported: true,
    target: {
        windows: {
            enabled: true,
        },
    },
    sdk_version: "current",
    min_sdk_version: "36",
    apex_available: ["com.android.webapp"],
}
"###,
            r###"java_defaults {
    name: "apksigner-defaults",
    srcs: ["src/apksigner/java/**/*.java"],
    java_resource_dirs: ["src/apksigner/java"],
    manifest: "src/apksigner/apksigner.mf",
    static_libs: ["conscrypt-unbundled"],
    java_version: "1.8",
    target: {
        not_windows: {
            jni_libs: ["libconscrypt_openjdk_jni"],
        },
    },
}
"###,
            r###"java_binary_host {
    name: "apksigner",
    defaults: ["apksigner-defaults"],
    wrapper: "etc/apksigner",
    static_libs: ["apksig"],
    target: {
        windows: {
            enabled: true,
            wrapper: "etc/apksigner.bat",
        },
    },
}
"###,
        ] {
            assert_eq!(projected.matches(required).count(), 1);
        }
        assert!(projected.contains("tools_apksig_license"));
        for omitted in ["apksig-kms-provider-aws", "apksig-kms-provider-gcp", "apksigner-kms", "apksig-test"] {
            assert!(!projected.contains(&format!("name: \"{omitted}\"")));
        }
        assert_eq!(projected, audio_without_unselected_cloud_kms(original).unwrap());
    }

    #[test]
    fn ordinary_pair_local_signer_rejects_unpinned_or_reprojected_source() {
        assert!(ordinary_pair_local_signer_blueprint(
            &format!("{}\n", REAL_PAIR_APKSIG_BLUEPRINT)).is_err());
        let projected = ordinary_pair_local_signer_blueprint(REAL_PAIR_APKSIG_BLUEPRINT).unwrap();
        assert!(ordinary_pair_local_signer_blueprint(&projected).is_err());
    }

    #[test]
    fn sdkextensions_provider_requires_complete_pinned_snapshot() {
        let source = tempfile::tempdir().unwrap();
        assert!(!original_sdkextensions_provider(source.path()).unwrap());
        let path = source.path().join("prebuilts/module_sdk/SdkExtensions/current/Android.bp");
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        assert!(original_sdkextensions_provider(source.path()).is_err());
        fs::write(&path, REAL_SDKEXTENSIONS_BLUEPRINT).unwrap();
        assert!(original_sdkextensions_provider(source.path()).unwrap());
        assert_eq!(fs::read_to_string(&path).unwrap(), REAL_SDKEXTENSIONS_BLUEPRINT);
        fs::write(&path, REAL_SDKEXTENSIONS_BLUEPRINT.replace(
            "name: \"framework-sdkextensions\"", "name: \"unrelated-provider\"" )).unwrap();
        assert!(original_sdkextensions_provider(source.path()).is_err());
        fs::write(&path, format!("{REAL_SDKEXTENSIONS_BLUEPRINT}\n")).unwrap();
        assert!(original_sdkextensions_provider(source.path()).is_err());
    }

    #[test]
    fn sdkextensions_fallbacks_preserve_original_scope_and_legacy_builds() {
        let source = tempfile::tempdir().unwrap();
        let absent = original_sdkextensions_provider(source.path()).unwrap();
        for scope in ["public", "system", "module-lib", "system-server"] {
            assert!(project_fallback_sdk_import("framework-sdkextensions", scope, absent));
        }
        let path = source.path().join("prebuilts/module_sdk/SdkExtensions/current/Android.bp");
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, REAL_SDKEXTENSIONS_BLUEPRINT).unwrap();
        let present = original_sdkextensions_provider(source.path()).unwrap();
        for scope in ["public", "system", "module-lib"] {
            assert!(!project_fallback_sdk_import("framework-sdkextensions", scope, present));
            assert!(project_fallback_sdk_import("framework-media", scope, present));
            assert!(!project_fallback_sdk_import("framework-connectivity-b", scope, present));
            assert!(!project_fallback_sdk_import("framework-permission-s", scope, present));
        }
        assert!(project_fallback_sdk_import("framework-sdkextensions", "system-server", present));
        assert_eq!(fs::read_to_string(&path).unwrap(), REAL_SDKEXTENSIONS_BLUEPRINT);
    }
    #[test]
    fn full_projection_preserves_original_shared_providers_and_test_trees() {
        use std::os::unix::fs::PermissionsExt;
        let d=tempfile::tempdir().unwrap();let source=d.path().join("source");
        let journal=d.path().join("projection.json");
        let mut fixtures:Vec<_>=ordinary_pair_provider_fixtures().into_iter()
            .filter(|(path,_)|super::super::SHARED_PRODUCT_BLUEPRINTS.contains(path)).collect();
        fixtures.push(("frameworks/native/services/serialservice/Android.bp",REAL_SERIALSERVICE_BLUEPRINT));
        assert_eq!(fixtures.len(),super::super::SHARED_PRODUCT_BLUEPRINTS.len());
        let modified=std::time::UNIX_EPOCH+std::time::Duration::from_secs(1_600_000_000);
        for(name,body)in &fixtures {
            let path=source.join(name);write(&path,body.as_bytes()).unwrap();
            fs::set_permissions(&path,fs::Permissions::from_mode(0o640)).unwrap();
            fs::File::open(&path).unwrap().set_modified(modified).unwrap();
        }
        for recovery in [false,true] {
            let mut projection=Projection::new(journal.clone()).unwrap();
            super::super::project_shared_root_blueprints(&mut projection,&source,
                SoongDependencyMode::Strict,Some((false,false)),true).unwrap();
            super::super::project_build_fixture_discovery(&mut projection,&source,
                false,false,true,SoongDependencyMode::Strict).unwrap();
            for(name,body)in &fixtures {
                assert_eq!(fs::read(source.join(name)).unwrap(),body.as_bytes());
            }
            for path in SOONG_EXCLUDED_TEST_FIXTURES {
                assert!(!source.join(path).join(".find-ignore").exists());
            }
            assert_eq!(projection.originals.len(),fixtures.len());
            if recovery {std::mem::forget(projection);super::super::recover(&journal,&source).unwrap();}
            else {projection.restore().unwrap();}
            for(name,body)in &fixtures {
                let path=source.join(name);assert_eq!(fs::read(&path).unwrap(),body.as_bytes());
                let metadata=fs::metadata(&path).unwrap();
                assert_eq!(metadata.permissions().mode()&0o777,0o640);
                assert_eq!(metadata.modified().unwrap(),modified);
            }
            assert!(!journal.exists());
        }
    }

}


#[cfg(test)]
mod official_vendor_graph_profile_tests {
    use super::*;

    #[test]
    fn official_vendor_graph_profile_changes_only_vendor_and_restores_original_source() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let d = tempfile::tempdir().unwrap();
        let source = d.path().join("source");
        let originals = [
            ("build/blueprint/context.go", include_bytes!("../tests/fixtures/audio-resources/context.go").as_slice()),
            ("build/soong/ui/build/soong.go", include_bytes!("../tests/fixtures/audio-resources/soong.go").as_slice()),
            ("build/blueprint/bootstrap/command.go", include_bytes!("../tests/fixtures/audio-resources/bootstrap-command.go").as_slice()),
        ];
        let mtime = std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_000, 123_456_789);
        for (name, bytes) in originals {
            write(&source.join(name), bytes).unwrap();
            fs::File::open(source.join(name)).unwrap().set_modified(mtime).unwrap();
        }
        let journal = d.path().join("source-projection.json");
        let mut p = Projection::new(journal.clone()).unwrap();
        p.patch(&source, "build/soong", &repo.join(
            "android/native-generation-pair/0008-soong-leaf-go-memory-budget.patch")).unwrap();
        p.patch(&source, "build/blueprint", &repo.join(
            "android/apex-compat/0009-blueprint-stream-uncached-module-actions.patch")).unwrap();
        project_ordinary_pair_graph_resources(
            repo, &source, &mut p, true, SoongDependencyMode::Strict,
        ).unwrap();
        let soong = source.join("build/soong/ui/build/soong.go");
        let baseline = fs::read(&soong).unwrap();
        assert_eq!(hash(&soong).unwrap(), "0b855ddee1c4e62203968104f22e949b50bf0ba323f7d2f7335cf84c9f9ec2a8");
        project_official_vendor_graph_profile(&source, &mut p, false, Some("4x16g")).unwrap();
        project_official_vendor_graph_profile(&source, &mut p, true, None).unwrap();
        assert_eq!(fs::read(&soong).unwrap(), baseline);
        assert!(project_official_vendor_graph_profile(&source, &mut p, true, Some("8x32g")).is_err());
        assert_eq!(fs::read(&soong).unwrap(), baseline);
        project_official_vendor_graph_profile(&source, &mut p, true, Some("4x16g")).unwrap();
        let actual = fs::read_to_string(&soong).unwrap();
        for line in [
            "invocationEnv[\"GOMEMLIMIT\"] = \"16GiB\"",
            "invocationEnv[\"GOMAXPROCS\"] = \"4\"",
            "invocationEnv[\"GOGC\"] = \"50\"",
            "invocationEnv[\"GODEBUG\"] = \"gctrace=1\"",
        ] { assert!(actual.contains(line), "{line}"); }
        assert_eq!(p.originals.len(), 3);
        assert!(project_official_vendor_graph_profile(&source, &mut p, true, Some("4x16g")).is_err());
        assert_eq!(fs::read_to_string(&soong).unwrap(), actual);
        p.restore().unwrap();
        assert!(!journal.exists());
        for (name, bytes) in originals {
            let path = source.join(name);
            assert_eq!(fs::read(&path).unwrap(), bytes);
            assert_eq!(fs::metadata(path).unwrap().modified().unwrap(), mtime);
        }
    }
}
